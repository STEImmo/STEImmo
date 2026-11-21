from django.conf import settings
from django.core.mail import EmailMessage

from wohnungsverwaltung.models import GlobalSettings


def callback_recipients(mail_settings):
    if mail_settings.callback_recipients is None:
        return settings.CALLBACK_RECIPIENTS
    return mail_settings.callback_recipients


def get_mail_settings():
    return GlobalSettings.objects.filter(pk=1).first() or GlobalSettings()


def send_repliable_mail(subject, message, recipient_list, *, mail_settings=None, connection=None):
    if mail_settings is None:
        mail_settings = get_mail_settings()
    return EmailMessage(
        subject=subject,
        body=message,
        to=recipient_list,
        reply_to=[mail_settings.reply_to] if mail_settings.reply_to else None,
        connection=connection,
    ).send()
