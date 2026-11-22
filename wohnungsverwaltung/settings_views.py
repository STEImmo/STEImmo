from datetime import timedelta
from smtplib import SMTPException

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import get_connection
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from core.mail_settings import callback_recipients, get_mail_settings, send_repliable_mail

from .access import employee_required, global_settings_required
from .models import GlobalSettings, GlobalSettingsChange, MailTestAttempt
from .notification_forms import GlobalNotificationForm
from .notification_preferences import USER_MAIL_TYPES, suppress_pending_notifications


@employee_required
@global_settings_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def global_settings(request):
    status = 200
    if request.method == "POST":
        form = GlobalNotificationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                current, _ = GlobalSettings.objects.select_for_update().get_or_create(pk=1)
                if current.version != form.cleaned_data["version"]:
                    status = 409
                else:
                    choices = {key: form.cleaned_data[key] for key in USER_MAIL_TYPES}
                    changed = [
                        key
                        for key, value in choices.items()
                        if current.user_mail_types.get(key, True) != value
                    ]
                    if changed:
                        current.user_mail_types = choices
                        current.version += 1
                        current.save(update_fields=["user_mail_types", "version"])
                        disabled = [key for key in changed if not choices[key]]
                        if disabled:
                            suppress_pending_notifications(disabled)
                        GlobalSettingsChange.objects.create(
                            actor_account_id=request.user.pk, changed_fields=changed
                        )
            if status != 409:
                messages.success(request, "Einstellungen gespeichert.")
                return redirect("verwaltung:global_settings")
        else:
            status = 400
    if request.method == "GET" or status == 409:
        current = GlobalSettings.objects.filter(pk=1).first() or GlobalSettings()
        form = GlobalNotificationForm(
            initial={
                "version": current.version,
                **{key: current.user_mail_types.get(key, True) for key in USER_MAIL_TYPES},
            }
        )
    return render(
        request,
        "wohnungsverwaltung/global_settings.html",
        {
            "form": form,
            "conflict": status == 409,
        },
        status=status,
    )


class MailSettingsForm(forms.Form):
    version = forms.IntegerField(min_value=0, max_value=2**63 - 1, widget=forms.HiddenInput)
    callback_recipients = forms.CharField(
        label="Empfänger für Rückrufwünsche",
        help_text=(
            "Diese Adressen erhalten neue Rückrufwünsche aus dem Kontaktformular. "
            "Mindestens eine Adresse, bei mehreren eine pro Zeile."
        ),
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 2}),
    )
    reply_to = forms.EmailField(
        label="Antwortadresse (optional)",
        help_text=(
            "An diese Adresse gehen Antworten auf Rückrufmails, Besichtigungseinladungen, "
            "Einladungen zur Hauptbewerbung und Testmails. "
            "Bleibt das Feld leer, gehen Antworten an den Standardabsender."
        ),
        required=False,
        max_length=254,
        widget=forms.EmailInput(attrs={"class": "uk-input"}),
    )

    def clean_callback_recipients(self):
        recipients = [
            line.strip()
            for line in self.cleaned_data["callback_recipients"].splitlines()
            if line.strip()
        ]
        for recipient in recipients:
            validate_email(recipient)
        return list(dict.fromkeys(recipients))

    def clean_reply_to(self):
        if any(character in self.data.get("reply_to", "") for character in "\r\n"):
            raise forms.ValidationError("Die Antwortadresse darf keinen Zeilenumbruch enthalten.")
        return self.cleaned_data["reply_to"]

    def clean(self):
        cleaned = super().clean()
        for field in self.fields:
            if len(self.data.getlist(field)) > 1:
                self.add_error(field, "Dieses Feld darf nur einmal übermittelt werden.")
        return cleaned


@employee_required
@global_settings_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def mail_settings(request):
    status = 200
    current = get_mail_settings()
    recipients = callback_recipients(current)
    if request.method == "POST":
        form = MailSettingsForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                current, _ = GlobalSettings.objects.select_for_update().get_or_create(pk=1)
                if current.version != form.cleaned_data["version"]:
                    form.add_error(None, "Die Einstellungen wurden inzwischen geändert.")
                    status = 409
                else:
                    changed_fields = []
                    for field in ("callback_recipients", "reply_to"):
                        value = form.cleaned_data[field]
                        if getattr(current, field) != value:
                            setattr(current, field, value)
                            changed_fields.append(field)
                    if changed_fields:
                        current.version += 1
                        current.save(update_fields=[*changed_fields, "version"])
                        GlobalSettingsChange.objects.create(
                            actor_account_id=request.user.pk, changed_fields=changed_fields
                        )
            if status != 409:
                messages.success(request, "Mailadressen gespeichert.")
                return redirect("verwaltung:mail_settings")
        else:
            status = 400
    else:
        form = MailSettingsForm(
            initial={
                "version": current.version,
                "callback_recipients": "\n".join(recipients),
                "reply_to": current.reply_to,
            }
        )
    return render(
        request,
        "wohnungsverwaltung/mail_settings.html",
        {
            "form": form,
            "conflict": status == 409,
            "default_sender": settings.DEFAULT_FROM_EMAIL,
            "needs_recipients": not recipients,
        },
        status=status,
    )


@transaction.atomic
def _reserve_mail_test(account):
    now = timezone.now()
    attempt, created = MailTestAttempt.objects.select_for_update().get_or_create(
        account=account, defaults={"next_allowed_at": now + timedelta(minutes=1)}
    )
    if created:
        return True
    now = timezone.now()
    if attempt.next_allowed_at > now:
        return False
    attempt.next_allowed_at = now + timedelta(minutes=1)
    attempt.save(update_fields=["next_allowed_at"])
    return True


@employee_required
@global_settings_required
@require_POST
@csrf_protect
def test_mail(request):
    recipient = request.user.email or ""
    try:
        validate_email(recipient)
    except ValidationError:
        messages.error(
            request, "Hinterlegen Sie zuerst eine gültige E-Mail-Adresse in Ihrem Konto."
        )
        return redirect("verwaltung:mail_settings")
    if not _reserve_mail_test(request.user):
        messages.warning(request, "Bitte warten Sie eine Minute zwischen zwei Testversuchen.")
        return redirect("verwaltung:mail_settings")
    if settings.DEMO_MODE:
        messages.info(request, "Demo: Der Testversand wurde simuliert.")
        return redirect("verwaltung:mail_settings")

    try:
        connection = get_connection()
        smtp = isinstance(connection, SMTPBackend)
        if smtp:
            connection.timeout = 10
        sent = send_repliable_mail(
            "[STEImmo-Test] Mailversand prüfen",
            "Dies ist eine Testmail aus den STEImmo-Einstellungen.",
            [recipient],
            connection=connection,
        )
    except (SMTPException, OSError, ValueError):
        sent = 0
    if not sent:
        messages.error(
            request, "Die Testmail konnte nicht versendet werden. Bitte versuchen Sie es erneut."
        )
    elif smtp:
        messages.success(request, "Die Testmail wurde vom Mailserver angenommen.")
    else:
        messages.info(request, "Das konfigurierte Mail-Backend hat die Testmail verarbeitet.")
    return redirect("verwaltung:mail_settings")
