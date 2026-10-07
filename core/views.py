import ipaddress
import logging
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, connection, transaction
from django.db.utils import OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme

from wohnungsverwaltung.access import (
    APPLICANT_ACCESS_PERMISSION,
    EMPLOYEE_ACCESS_PERMISSION,
    USER_MANAGEMENT_PERMISSION,
)
from wohnungsverwaltung.forms import (
    ACCOUNT_CREATION_ERROR,
    EmployeeMfaCodeForm,
    RegistrationForm,
    RegistrationVerificationForm,
    ResendRegistrationCodeForm,
)
from wohnungsverwaltung.models import (
    AccountLoginThrottle,
    EmployeeLoginVerification,
    LoginIpThrottle,
    RegistrationVerification,
)

EMPLOYEE_MFA_USER_SESSION_KEY = "employee_mfa_user_id"
EMPLOYEE_MFA_REDIRECT_SESSION_KEY = "employee_mfa_redirect_url"
EMPLOYEE_MFA_CHALLENGE_SESSION_KEY = "employee_mfa_challenge"
LOGIN_FAILURE_MESSAGE = "Bitte überprüfen Sie Ihre Zugangsdaten und versuchen Sie es später erneut."
logger = logging.getLogger(__name__)


def _deliver_verification_code(sender, email: str, code: str) -> bool:
    try:
        delivered = sender(email, code)
    except (SMTPException, OSError) as error:
        # Do not log recipient addresses, codes or server error details.
        logger.warning("Verification email delivery failed (%s).", type(error).__name__)
        return False
    if not delivered:
        logger.warning("Verification email delivery failed (no delivery).")
    return bool(delivered)


def _discard_employee_code_after_delivery_failure(user_id: int, challenge: str) -> None:
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(pk=user_id).first()
        if user is not None:
            EmployeeLoginVerification.objects.filter(user=user, code_hash=challenge).delete()


def _clear_pending_employee_login(request: HttpRequest) -> None:
    for key in (
        EMPLOYEE_MFA_USER_SESSION_KEY,
        EMPLOYEE_MFA_REDIRECT_SESSION_KEY,
        EMPLOYEE_MFA_CHALLENGE_SESSION_KEY,
    ):
        request.session.pop(key, None)


def _login_lockout_duration() -> timedelta:
    return timedelta(seconds=settings.LOGIN_ACCOUNT_LOCKOUT_SECONDS)


def _ip_failure_window() -> timedelta:
    return timedelta(seconds=settings.LOGIN_IP_FAILURE_WINDOW_SECONDS)


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _client_ip_fingerprint(request: HttpRequest) -> str | None:
    remote_ip = _valid_ip(request.META.get("REMOTE_ADDR", ""))
    if remote_ip is None:
        return None
    client_ip = remote_ip
    if remote_ip in settings.LOGIN_THROTTLE_TRUSTED_PROXY_IPS:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        forwarded_ip = _valid_ip(forwarded_for.split(",")[0].strip())
        if forwarded_ip is not None:
            client_ip = forwarded_ip
    return salted_hmac("login-ip-throttle", client_ip, algorithm="sha256").hexdigest()


def _account_for_login_identifier(identifier: str):
    user_model = get_user_model()
    try:
        return user_model._default_manager.select_for_update().get(
            **{user_model.USERNAME_FIELD: identifier}
        )
    except user_model.DoesNotExist:
        return None


def _clear_expired_account_throttle(user, now) -> bool:
    try:
        throttle = AccountLoginThrottle.objects.select_for_update().get(user=user)
    except AccountLoginThrottle.DoesNotExist:
        return False
    if throttle.locked_until is None:
        return False
    if throttle.locked_until is not None and throttle.locked_until > now:
        return True
    throttle.delete()
    return False


def _clear_expired_ip_throttle(ip_fingerprint: str | None, now) -> bool:
    if ip_fingerprint is None:
        return False
    try:
        throttle = LoginIpThrottle.objects.select_for_update().get(ip_fingerprint=ip_fingerprint)
    except LoginIpThrottle.DoesNotExist:
        return False
    if throttle.locked_until is not None and throttle.locked_until > now:
        return True
    if throttle.window_started_at + _ip_failure_window() > now:
        return False
    throttle.delete()
    return False


def _is_login_throttled(user, ip_fingerprint: str | None) -> bool:
    now = timezone.now()
    with transaction.atomic():
        if user is not None and _clear_expired_account_throttle(user, now):
            return True
        return _clear_expired_ip_throttle(ip_fingerprint, now)


def _record_failed_login(user, ip_fingerprint: str | None) -> None:
    now = timezone.now()
    with transaction.atomic():
        if user is not None:
            # Keep the same lock order as password authentication, including
            # throttle creation (whose user foreign key also needs a row lock).
            get_user_model().objects.select_for_update().get(pk=user.pk)
            throttle, _created = AccountLoginThrottle.objects.get_or_create(user=user)
            throttle = AccountLoginThrottle.objects.select_for_update().get(pk=throttle.pk)
            if throttle.locked_until is None or throttle.locked_until <= now:
                if throttle.locked_until is not None:
                    throttle.failed_attempts = 0
                    throttle.locked_until = None
                throttle.failed_attempts += 1
                if throttle.failed_attempts >= settings.LOGIN_ACCOUNT_FAILURE_LIMIT:
                    throttle.locked_until = now + _login_lockout_duration()
                throttle.save(update_fields=["failed_attempts", "locked_until", "updated_at"])
        if ip_fingerprint is not None:
            throttle, _created = LoginIpThrottle.objects.get_or_create(
                ip_fingerprint=ip_fingerprint,
                defaults={"window_started_at": now},
            )
            throttle = LoginIpThrottle.objects.select_for_update().get(pk=throttle.pk)
            if throttle.locked_until is None or throttle.locked_until <= now:
                if throttle.window_started_at + _ip_failure_window() <= now:
                    throttle.failed_attempts = 0
                    throttle.window_started_at = now
                throttle.failed_attempts += 1
                if throttle.failed_attempts >= settings.LOGIN_IP_FAILURE_LIMIT:
                    throttle.locked_until = now + _ip_failure_window()
                throttle.save(
                    update_fields=[
                        "failed_attempts",
                        "window_started_at",
                        "locked_until",
                        "updated_at",
                    ]
                )


def _clear_account_login_throttle(user) -> None:
    AccountLoginThrottle.objects.filter(user=user).delete()


class ThrottledAuthenticationForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        self.login_user = None
        self.ip_fingerprint = _client_ip_fingerprint(request) if request is not None else None
        self.login_was_throttled = False

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        with transaction.atomic():
            if username and password:
                self.login_user = _account_for_login_identifier(username)
                if _is_login_throttled(self.login_user, self.ip_fingerprint):
                    self.login_was_throttled = True
                    raise self.get_invalid_login_error()
            # Django may write an upgraded password hash during authentication.
            # The user lock prevents that write from overwriting a password reset.
            return super().clean()

    def get_invalid_login_error(self):
        return ValidationError(LOGIN_FAILURE_MESSAGE, code="invalid_login")

    @property
    def should_record_failure(self) -> bool:
        return (
            not self.login_was_throttled
            and bool(self.cleaned_data.get("username"))
            and bool(self.cleaned_data.get("password"))
        )


def home(request: HttpRequest):
    return render(request, "core/home.html")


def health(request: HttpRequest) -> JsonResponse:
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"service": "steimmo", "status": "unhealthy"}, status=503)
    return JsonResponse({"service": "steimmo", "status": "ok"})


class RoleAwareLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = ThrottledAuthenticationForm

    def form_invalid(self, form):
        if form.should_record_failure:
            _record_failed_login(form.login_user, form.ip_fingerprint)
        return super().form_invalid(form)

    def form_valid(self, form):
        authenticated_user = form.get_user()
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(pk=authenticated_user.pk)
                .first()
            )
            if (
                user is None
                or not user.is_active
                or any(
                    getattr(user, field) != getattr(authenticated_user, field)
                    for field in ("password", "username", "email")
                )
            ):
                form.add_error(None, form.get_invalid_login_error())
                return super().form_invalid(form)
            # Authentication checked this credential snapshot. Rights must be read
            # afresh while account changes are excluded by the same user-row lock.
            user.backend = authenticated_user.backend
            form.user_cache = user
            _clear_account_login_throttle(user)
            if user.has_perm(EMPLOYEE_ACCESS_PERMISSION) or user.has_perm(
                USER_MANAGEMENT_PERMISSION
            ):
                verification, _created = (
                    EmployeeLoginVerification.objects.select_for_update().get_or_create(
                        user=user,
                        defaults={"code_hash": "", "expires_at": timezone.now()},
                    )
                )
                code = verification.issue_code()
                verification.save()
                self.request.session[EMPLOYEE_MFA_USER_SESSION_KEY] = user.pk
                self.request.session[EMPLOYEE_MFA_CHALLENGE_SESSION_KEY] = verification.code_hash
                self.request.session[EMPLOYEE_MFA_REDIRECT_SESSION_KEY] = (
                    self.get_redirect_url() or self.get_default_redirect_url_for_user(user)
                )
            else:
                response = super().form_valid(form)
                # SessionMiddleware runs after this transaction. Persist now so a
                # subsequent account change can revoke even this unfinished response.
                self.request.session.save()
                return response
        # SMTP must not hold a database lock. A concurrent account change can
        # invalidate the issued code even if delivery has not completed yet.
        if not _deliver_verification_code(send_employee_mfa_code, user.email, code):
            _discard_employee_code_after_delivery_failure(user.pk, verification.code_hash)
            _clear_pending_employee_login(self.request)
            form.add_error(
                None,
                "Der Einmalcode konnte nicht gesendet werden. "
                "Bitte versuchen Sie die Anmeldung erneut.",
            )
            return super().form_invalid(form)
        messages.success(self.request, "Wir haben Ihnen einen Einmalcode gesendet.")
        return redirect("employee_mfa_verify")

    def get_default_redirect_url_for_user(self, user) -> str:
        if user.has_perm(EMPLOYEE_ACCESS_PERMISSION):
            return reverse("verwaltung:wohnung_list")
        if user.has_perm(USER_MANAGEMENT_PERMISSION):
            return reverse("verwaltung:user_account_list")
        if user.has_perm(APPLICANT_ACCESS_PERMISSION):
            return reverse("wohnungsverwaltung:pre_application_list")
        return reverse("home")

    def get_default_redirect_url(self) -> str:
        return self.get_default_redirect_url_for_user(self.request.user)


def register(request: HttpRequest) -> HttpResponse:
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                verification = RegistrationVerification(user=user)
                code = verification.issue_code()
                verification.save()
        except IntegrityError:
            form.add_error("email", ACCOUNT_CREATION_ERROR)
        else:
            request.session["registration_verification_email"] = user.email
            if _deliver_verification_code(send_registration_code, user.email, code):
                messages.success(request, "Wir haben Ihnen einen Bestätigungscode gesendet.")
            else:
                messages.error(
                    request,
                    "Der Bestätigungscode konnte nicht gesendet werden. "
                    "Sie können ihn frühestens eine Minute nach dem letzten "
                    "Versandversuch erneut anfordern.",
                )
            return redirect("register_verify")
    return render(request, "registration/register.html", {"form": form})


def send_registration_code(email: str, code: str) -> bool:
    return (
        send_mail(
            subject="STEImmo: Bestätigungscode für Ihre Registrierung",
            message=(
                "Ihr Bestätigungscode lautet: "
                f"{code}\n\n"
                "Der Code ist 15 Minuten gültig. Falls Sie kein Konto angelegt haben, "
                "können Sie diese E-Mail ignorieren."
            ),
            from_email=None,
            recipient_list=[email],
        )
        == 1
    )


def send_employee_mfa_code(email: str, code: str) -> bool:
    return (
        send_mail(
            subject="STEImmo: Einmalcode für die Mitarbeiteranmeldung",
            message=(
                "Ihr Einmalcode lautet: "
                f"{code}\n\n"
                "Der Code ist 15 Minuten gültig. Falls Sie diese Anmeldung nicht gestartet haben, "
                "ignorieren Sie diese E-Mail."
            ),
            from_email=None,
            recipient_list=[email],
        )
        == 1
    )


def register_verify(request: HttpRequest) -> HttpResponse:
    initial = {"email": request.session.get("registration_verification_email", "")}
    form = RegistrationVerificationForm(request.POST or None, initial=initial)
    resend_form = ResendRegistrationCodeForm(initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = (
                    get_user_model()
                    .objects.select_for_update()
                    .get(email__iexact=form.cleaned_data["email"], is_active=False)
                )
                verification = RegistrationVerification.objects.select_for_update().get(user=user)
                if verification.matches(form.cleaned_data["code"]):
                    user.is_active = True
                    user.save(update_fields=["is_active"])
                    verification.delete()
                    request.session.pop("registration_verification_email", None)
                    if user.has_perm(EMPLOYEE_ACCESS_PERMISSION) or user.has_perm(
                        USER_MANAGEMENT_PERMISSION
                    ):
                        messages.success(
                            request,
                            "Ihr Konto wurde bestätigt. Bitte melden Sie sich mit Passwort und "
                            "Mitarbeiter-Einmalcode an.",
                        )
                        return redirect("login")
                    login(request, user)
                    request.session.save()
                    messages.success(request, "Ihr Konto wurde bestätigt.")
                    return redirect("wohnungsverwaltung:pre_application_list")
                else:
                    verification.attempts += 1
                    verification.save(update_fields=["attempts"])
        except (RegistrationVerification.DoesNotExist, get_user_model().DoesNotExist):
            form.add_error(None, "Der Code konnte nicht bestätigt werden.")
        else:
            form.add_error(None, "Der Code konnte nicht bestätigt werden.")
    return render(
        request,
        "registration/verify_registration.html",
        {"form": form, "resend_form": resend_form},
    )


def resend_registration_code(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("register_verify")

    form = ResendRegistrationCodeForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                user = (
                    get_user_model()
                    .objects.select_for_update()
                    .get(email__iexact=form.cleaned_data["email"], is_active=False)
                )
                verification = RegistrationVerification.objects.select_for_update().get(user=user)
                if verification.can_resend():
                    code = verification.issue_code()
                    verification.save(
                        update_fields=["code_hash", "expires_at", "attempts", "last_sent_at"]
                    )
                else:
                    code = None
        except (RegistrationVerification.DoesNotExist, get_user_model().DoesNotExist):
            code = None
        else:
            if code is not None:
                _deliver_verification_code(send_registration_code, user.email, code)
        request.session["registration_verification_email"] = form.cleaned_data["email"]
    messages.success(
        request,
        "Falls eine offene Registrierung vorliegt und der Versand möglich ist, "
        "erhalten Sie einen neuen Bestätigungscode. "
        "Wenn keine E-Mail ankommt, können Sie den Code frühestens eine Minute "
        "nach dem letzten Versandversuch erneut anfordern.",
    )
    return redirect("register_verify")


def employee_mfa_verify(request: HttpRequest) -> HttpResponse:
    pending_user_id = request.session.get(EMPLOYEE_MFA_USER_SESSION_KEY)
    pending_challenge = request.session.get(EMPLOYEE_MFA_CHALLENGE_SESSION_KEY, "")
    if pending_user_id is None or not pending_challenge:
        return redirect("login")

    form = EmployeeMfaCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = (
                    get_user_model()
                    .objects.select_for_update()
                    .get(pk=pending_user_id, is_active=True)
                )
                verification = EmployeeLoginVerification.objects.select_for_update().get(user=user)
                if not constant_time_compare(pending_challenge, verification.code_hash):
                    raise EmployeeLoginVerification.DoesNotExist
                if verification.matches(form.cleaned_data["code"]):
                    verification.delete()
                    redirect_url = request.session.pop(EMPLOYEE_MFA_REDIRECT_SESSION_KEY, "")
                    # Switching accounts flushes the old session, so capture the
                    # checked destination before login() changes the session.
                    login(request, user)
                    _clear_pending_employee_login(request)
                    request.session.save()
                    if url_has_allowed_host_and_scheme(
                        url=redirect_url,
                        allowed_hosts={request.get_host()},
                        require_https=request.is_secure(),
                    ):
                        return redirect(redirect_url)
                    return redirect(RoleAwareLoginView().get_default_redirect_url_for_user(user))
                else:
                    verification.attempts += 1
                    verification.save(update_fields=["attempts"])
        except (EmployeeLoginVerification.DoesNotExist, get_user_model().DoesNotExist):
            _clear_pending_employee_login(request)
            return redirect("login")
        else:
            form.add_error(None, "Der Code konnte nicht bestätigt werden.")
    return render(request, "registration/employee_mfa_verify.html", {"form": form})
