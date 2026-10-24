"""Authenticated self-service account changes, serialized with account administration."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from wohnungsverwaltung.forms import (
    AccountEmailChangeForm,
    AccountEmailConfirmationForm,
    AccountPasswordChangeForm,
    account_email_in_use,
)
from wohnungsverwaltung.models import (
    AccountEmailChangeThrottle,
    EmployeeLoginVerification,
    PendingEmailChange,
    Person,
    RegistrationVerification,
)

from . import views


def credentials_hash(account):
    return salted_hmac(
        "account-email-change",
        f"{account.pk}:{account.password}:{account.username}:{account.email}",
        algorithm="sha256",
    ).hexdigest()


def revoke_sessions(account):
    views._clear_account_login_throttle(account)
    EmployeeLoginVerification.objects.filter(user=account).delete()
    RegistrationVerification.objects.filter(user=account).delete()
    PendingEmailChange.objects.filter(user=account).delete()
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(account.pk):
            session.delete()


def credential_form_valid(form, account, request, password_field):
    fingerprint = views._client_ip_fingerprint(request)
    if views._is_login_throttled(account, fingerprint):
        form.add_error(None, "Bitte versuchen Sie es später erneut.")
        return False
    valid = form.is_valid()
    if any(
        error.code == "password_incorrect"
        for error in form.errors.as_data().get(password_field, [])
    ):
        views._record_failed_login(account, fingerprint)
    return valid


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def password_change(request):
    changed = False
    with transaction.atomic():
        account = views._locked_profile_account(request)
        person = Person.objects.select_for_update().filter(user=account).first()
        form = (
            AccountPasswordChangeForm(account, request.POST if request.method == "POST" else None)
            if person
            else None
        )
        if (
            request.method == "POST"
            and form is not None
            and credential_form_valid(form, account, request, "old_password")
        ):
            form.save()
            revoke_sessions(account)
            changed = True
    if changed:
        logout(request)
        messages.success(request, "Ihr Passwort wurde geändert. Bitte melden Sie sich erneut an.")
        return redirect("login")
    return render(
        request,
        "core/account_change.html",
        {
            "person": person,
            "form": form,
            "title": "Passwort ändern",
            "intro": (
                "Wählen Sie ein neues Passwort für Ihr Konto. "
                "Anschließend werden Sie auf allen Geräten abgemeldet."
            ),
            "action_label": "Passwort ändern",
        },
    )


def send_email_code(email, code):
    return views.send_mail(
        "Neue E-Mail-Adresse bestätigen – STE Immobilien",
        (
            f"Ihr Bestätigungscode lautet: {code}\n\nDer Code gilt 15 Minuten. "
            "Ihre bisherige E-Mail-Adresse bleibt bis zur Bestätigung gültig. "
            "Wenn Sie diese Änderung nicht angefordert haben, ignorieren Sie "
            "diese Nachricht."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def email_change(request):
    code = None
    with transaction.atomic():
        account = views._locked_profile_account(request)
        person = Person.objects.select_for_update().filter(user=account).first()
        form = (
            AccountEmailChangeForm(request.POST if request.method == "POST" else None, user=account)
            if person
            else None
        )
        if (
            request.method == "POST"
            and form is not None
            and credential_form_valid(form, account, request, "current_password")
        ):
            pending = PendingEmailChange.objects.select_for_update().filter(user=account).first()
            throttle = AccountEmailChangeThrottle.objects.filter(user=account).first()
            if throttle and throttle.last_sent_at + timedelta(minutes=1) > timezone.now():
                form.add_error(
                    None, "Bitte warten Sie eine Minute, bevor Sie einen neuen Code anfordern."
                )
            else:
                pending = pending or PendingEmailChange(user=account)
                pending.new_email = form.cleaned_data["new_email"]
                pending.credentials_hash = credentials_hash(account)
                code = pending.issue_code()
                pending.save()
                AccountEmailChangeThrottle.objects.update_or_create(
                    user=account, defaults={"last_sent_at": pending.last_sent_at}
                )
    # Deliver after releasing the account/person row locks.
    if code is not None:
        if views._deliver_verification_code(send_email_code, pending.new_email, code):
            messages.success(
                request, "Wir haben einen Bestätigungscode an Ihre neue E-Mail-Adresse gesendet."
            )
            return redirect("profile:email_confirm")
        form.add_error(
            None,
            (
                "Der Bestätigungscode konnte nicht gesendet werden. Bitte "
                "versuchen Sie es nach einer Minute erneut."
            ),
        )
    return render(
        request,
        "core/account_change.html",
        {
            "person": person,
            "form": form,
            "title": "E-Mail-Adresse ändern",
            "intro": (
                "Bestätigen Sie Ihre neue Adresse per E-Mail. Bis dahin "
                "melden Sie sich weiterhin mit Ihrer bisherigen Adresse an."
            ),
            "action_label": "Bestätigungscode senden",
            "email_change": True,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def email_confirm(request):
    changed = False
    with transaction.atomic():
        account = views._locked_profile_account(request)
        person = Person.objects.select_for_update().filter(user=account).first()
        pending = PendingEmailChange.objects.select_for_update().filter(user=account).first()
        form = (
            AccountEmailConfirmationForm(
                request.POST if request.method == "POST" else None,
                initial={"challenge": pending.challenge if pending else None},
            )
            if person
            else None
        )
        if form is not None and request.method == "POST" and form.is_valid():
            if pending is None or not constant_time_compare(
                pending.credentials_hash, credentials_hash(account)
            ):
                form.add_error(
                    None,
                    (
                        "Diese E-Mail-Änderung ist nicht mehr gültig. Bitte fordern Sie "
                        "einen neuen Code an."
                    ),
                )
            elif (
                pending.expires_at < timezone.now()
                or pending.attempts >= 5
                or pending.challenge != form.cleaned_data["challenge"]
            ):
                form.add_error(
                    "code",
                    (
                        "Dieser Code ist abgelaufen oder nicht mehr gültig. Bitte fordern "
                        "Sie einen neuen Code an."
                    ),
                )
            elif not check_password(form.cleaned_data["code"], pending.code_hash):
                pending.attempts += 1
                pending.save(update_fields=["attempts"])
                form.add_error(
                    "code",
                    (
                        "Der Code ist nicht korrekt. Nach fünf Fehlversuchen benötigen "
                        "Sie einen neuen Code."
                    ),
                )
            elif account_email_in_use(pending.new_email, account):
                form.add_error(
                    None,
                    (
                        "Diese E-Mail-Adresse wird bereits verwendet. Bitte wählen Sie "
                        "eine andere Adresse."
                    ),
                )
            else:
                try:
                    with transaction.atomic():
                        account.username = pending.new_email
                        account.email = pending.new_email
                        account.save(update_fields=["username", "email"])
                        person.email = pending.new_email
                        person.save(update_fields=["email", "updated_at"])
                except IntegrityError:
                    form.add_error(
                        None,
                        (
                            "Diese E-Mail-Adresse wird bereits verwendet. Bitte wählen Sie "
                            "eine andere Adresse."
                        ),
                    )
                else:
                    revoke_sessions(account)
                    changed = True
    if changed:
        logout(request)
        messages.success(
            request,
            "Ihre E-Mail-Adresse wurde geändert. Bitte melden Sie sich mit der neuen Adresse an.",
        )
        return redirect("login")
    return render(
        request,
        "core/account_change.html",
        {
            "person": person,
            "form": form,
            "pending_email": pending.new_email if pending else None,
            "title": "Neue E-Mail-Adresse bestätigen",
            "intro": "Geben Sie den sechsstelligen Code aus Ihrer E-Mail ein. Er gilt 15 Minuten.",
            "action_label": "E-Mail-Adresse bestätigen",
            "email_confirmation": True,
        },
    )


@never_cache
@login_required
@require_http_methods(["POST"])
def email_cancel(request):
    with transaction.atomic():
        account = views._locked_profile_account(request)
        PendingEmailChange.objects.filter(user=account).delete()
    messages.info(
        request, "Die E-Mail-Änderung wurde verworfen. Ihre bisherige Adresse bleibt gültig."
    )
    return redirect("profile:detail")
