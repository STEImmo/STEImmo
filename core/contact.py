import ipaddress
import logging
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import CallbackForm
from .models import CallbackThrottle

logger = logging.getLogger(__name__)


def _client_hash(request):
    # Use the same explicitly trusted proxy addresses as the existing login protection.
    address = request.META.get("REMOTE_ADDR", "")
    if address in settings.LOGIN_THROTTLE_TRUSTED_PROXY_IPS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if forwarded:
            address = forwarded
    try:
        address = str(ipaddress.ip_address(address))
    except ValueError:
        address = "unknown"
    return salted_hmac("callback-throttle", address, algorithm="sha256").hexdigest()


@transaction.atomic
def _reserve_attempt(request):
    now = timezone.now()
    # Expired counters are removed on the next submission; no background job is needed.
    CallbackThrottle.objects.filter(expires_at__lte=now).delete()
    counter, _ = CallbackThrottle.objects.get_or_create(
        client_hash=_client_hash(request), defaults={"expires_at": now + timedelta(minutes=15)}
    )
    counter = CallbackThrottle.objects.select_for_update().get(pk=counter.pk)
    if counter.attempts >= 5:
        return max(1, int((counter.expires_at - now).total_seconds()) + 1)
    counter.attempts += 1
    counter.save(update_fields=["attempts"])
    return 0


def _send_callback(form):
    recipients = settings.CALLBACK_RECIPIENTS
    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        logger.warning("Rückrufversand benötigt ein Mail-Backend ohne Konsolenausgabe.")
        return False
    try:
        if not recipients:
            raise ValidationError("Missing callback recipients")
        for recipient in recipients:
            validate_email(recipient)
        return (
            send_mail(
                subject="STE Immobilien eGbR: Neuer Rückrufwunsch",
                message=(
                    "Über das Kontaktformular wurde ein Rückruf gewünscht.\n\n"
                    f"Telefonnummer: {form.cleaned_data['phone']}\n"
                    f"Erreichbarkeit: {form.cleaned_data['availability']}\n\n"
                    "Bitte rufen Sie zu den angegebenen Zeiten zurück."
                ),
                from_email=None,
                recipient_list=recipients,
                fail_silently=False,
            )
            == 1
        )
    except (SMTPException, OSError, ValidationError):
        # Exception messages from mail providers can contain private request details.
        logger.warning("Rückrufwunsch konnte nicht versendet werden.")
        return False


@never_cache
@require_http_methods(["GET", "POST"])
def contact(request):
    form = CallbackForm(request.POST if request.method == "POST" else None)
    status = 200
    if request.method == "POST":
        retry_after = _reserve_attempt(request)
        if retry_after:
            form.add_error(None, "Zu viele Anfragen. Bitte versuchen Sie es in 15 Minuten erneut.")
            response = render(request, "core/contact.html", {"form": form}, status=429)
            response["Retry-After"] = str(retry_after)
            return response
        if form.is_valid():
            if settings.DEMO_MODE:
                messages.info(
                    request,
                    "Demo: Ihr Rückrufwunsch wurde nur simuliert. "
                    "Es wurde keine E-Mail versendet und es erfolgt kein Rückruf.",
                )
                return redirect("contact")
            if _send_callback(form):
                messages.success(request, "Ihr Rückrufwunsch wurde versendet.")
                return redirect("contact")
            form.add_error(
                None,
                "Ihr Rückrufwunsch konnte gerade nicht versendet werden. "
                "Bitte versuchen Sie es erneut.",
            )
            status = 503
    return render(request, "core/contact.html", {"form": form}, status=status)
