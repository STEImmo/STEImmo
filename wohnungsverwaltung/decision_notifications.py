"""Delivery of committed decision and completion notifications."""

import logging
from functools import partial
from smtplib import SMTPRecipientsRefused, SMTPResponseException
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from .access import EMPLOYEE_ACCESS_PERMISSION, TENANT_ACCESS_PERMISSION
from .handover_export import read_archived_pdf
from .models import (
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    DecisionNotification,
    GlobalSettings,
    NotificationPreference,
    Protokoll,
    ProtokollStatus,
    Rental,
)
from .notification_preferences import USER_MAIL_TYPES, mail_allowed

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
INACTIVE_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
}


def _application_message(notice, recipient):
    application = Bewerbung.objects.filter(pk=notice.object_id).select_related("person").first()
    if application is None:
        return None
    if notice.kind == "application_withdrawn":
        if str(application.interest_withdrawn_at) == notice.version and recipient.has_perm(
            EMPLOYEE_ACCESS_PERMISSION
        ):
            name = str(application.person).strip()
            withdrawal = (
                f"{name} hat die Bewerbung zurückgezogen."
                if name
                else "Die Bewerbung wurde zurückgezogen."
            )
            return (
                "Bewerbung zurückgezogen",
                f"{withdrawal} Prüfen Sie den Vorgang, "
                "falls bereits weitere Schritte für diese Bewerbung geplant waren.",
                "Bewerbung in der Verwaltung öffnen",
                reverse("wohnungsverwaltung:employee_application_detail", args=[application.pk]),
            )
        return None
    if application.person.user_id != recipient.pk or application.interest_withdrawn_at:
        return None
    if notice.kind == "application_rejected":
        rejection = application.review_events.filter(
            kind=ApplicationReviewEvent.Kind.OCCUPANCY_DECLINED
        ).first()
        if (
            application.status == BewerbungStatus.DECLINED
            and str(rejection.pk if rejection else "") == notice.version
        ):
            return (
                "Entscheidung zu Ihrer Bewerbung",
                "Ihre Bewerbung wurde abgelehnt. Für diese Bewerbung müssen Sie nichts tun. "
                "Den Status sehen Sie unter „Meine Bewerbungen“.",
                "Meine Bewerbungen öffnen",
                reverse("wohnungsverwaltung:pre_application_list"),
            )
        return None
    if (
        application.acceptance_eligible
        and application.main_application_accessible
        and str(application.accepted_at) == notice.version
        and not Rental.objects.filter(application=application).exists()
        and not application.review_events.filter(
            kind=ApplicationReviewEvent.Kind.CONTRACT_SENT,
            created_at__gte=application.accepted_at,
        ).exists()
    ):
        return (
            "Ihre Bewerbung wurde angenommen",
            "Die Verwaltung hat Ihre Bewerbung angenommen. Warten Sie auf den Mietvertrag. "
            "Den aktuellen Stand können Sie in Ihrer Bewerbung einsehen.",
            "Eigene Hauptbewerbung öffnen",
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk]),
        )
    return None


def _message(notice, recipient):
    if notice.kind != "handover_finalized":
        return _application_message(notice, recipient)
    if not recipient.has_perm(TENANT_ACCESS_PERMISSION):
        return None
    protocol = Protokoll.objects.filter(
        pk=notice.object_id, status=ProtokollStatus.SIGNED, person__user=recipient
    ).first()
    if (
        not protocol
        or not protocol.dokument_pfad
        or protocol.dokument_hash_sha256 != notice.version
    ):
        return None
    try:
        read_archived_pdf(protocol)
    except (OSError, ValueError):
        return None
    return (
        "Ihr Übergabeprotokoll ist verfügbar",
        "Das Übergabeprotokoll wurde abgeschlossen. Sie können jetzt Ihr PDF abrufen.",
        "Übergabeprotokoll als PDF öffnen",
        reverse("wohnungsverwaltung:handover_protocol_pdf", args=[protocol.pk]),
    )


def _eligible_message(notice, recipient):
    if settings.EMAIL_BACKEND in INACTIVE_BACKENDS or not mail_allowed(recipient, notice.kind):
        return None
    return _message(notice, recipient)


def queue_decision_notification(kind, object_id, version, recipient_id=None, *, origin=""):
    """Call inside the transaction that records the business event."""
    accounts = get_user_model().objects
    recipients = (
        accounts.with_perm(EMPLOYEE_ACCESS_PERMISSION)
        if kind == "application_withdrawn"
        else accounts.filter(pk=recipient_id)
    )
    if kind in USER_MAIL_TYPES:
        GlobalSettings.objects.select_for_update().get_or_create(pk=1)
    for recipient in recipients.order_by("pk"):
        # Serialize the initial preference check and insertion with explicit opt-outs.
        NotificationPreference.objects.select_for_update().get_or_create(account=recipient)
        notice = DecisionNotification(
            kind=kind,
            object_id=object_id,
            version=str(version),
            recipient=recipient,
            origin=origin,
        )
        if not _eligible_message(notice, recipient):
            notice.status = DecisionNotification.Status.SUPPRESSED
        notice, created = DecisionNotification.objects.get_or_create(
            kind=kind,
            object_id=object_id,
            version=notice.version,
            recipient=recipient,
            defaults={"origin": notice.origin, "status": notice.status},
        )
        if created and notice.status == DecisionNotification.Status.PENDING:
            transaction.on_commit(partial(deliver_decision_notification, notice.pk), robust=True)


def deliver_decision_notification(notice_id):
    states = DecisionNotification.Status
    with transaction.atomic():
        notice = DecisionNotification.objects.select_for_update().filter(pk=notice_id).first()
        if not notice or notice.status not in (states.PENDING, states.RETRY):
            return
        recipient = notice.recipient
        message = _eligible_message(notice, recipient)
        origin = (notice.origin or settings.DECISION_NOTIFICATION_ORIGIN).rstrip("/")
        if not message:
            notice.status = states.SUPPRESSED
            notice.save(update_fields=["status"])
            return
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return
        notice.status = states.SENDING
        notice.attempts += 1
        notice.save(update_fields=["status", "attempts"])

    subject, body, link_label, path = message
    link_url = f"{origin}{path}"
    html = render_to_string(
        "wohnungsverwaltung/email/notification_link.html",
        {"body": body, "link_label": link_label, "link_url": link_url},
    )
    # HTML rendering can outlast a reassignment, address change or opt-out.
    # Read current access and settings outside the reservation transaction.
    current = (
        DecisionNotification.objects.filter(pk=notice.pk, status=states.SENDING)
        .select_related("recipient")
        .first()
    )
    if current is None:
        return
    if _eligible_message(current, current.recipient) != message:
        DecisionNotification.objects.filter(pk=notice.pk, status=states.SENDING).update(
            status=states.SUPPRESSED
        )
        return
    if not DecisionNotification.objects.filter(pk=notice.pk, status=states.SENDING).exists():
        return

    outcome = states.FAILED
    try:
        if send_mail(
            subject,
            f"{body}\n\n{link_label}: {link_url}",
            None,
            [current.recipient.email],
            html_message=html,
        ):
            outcome = states.SENT
    except (SMTPRecipientsRefused, SMTPResponseException, ConnectionRefusedError) as error:
        if _temporary_rejection(error) and notice.attempts < MAX_ATTEMPTS:
            outcome = states.RETRY
    except (OSError, ValueError):
        # A disconnect can occur after acceptance. Leave ambiguous outcomes for manual review.
        pass
    if outcome != states.SENT:
        logger.warning("Entscheidungsbenachrichtigung %s: %s", notice.pk, outcome)
    # Keep an opt-out terminal on failure. Record successful handoffs even if the
    # settings changed after SMTP had already started.
    statuses = (states.SENDING, states.SUPPRESSED) if outcome == states.SENT else (states.SENDING,)
    DecisionNotification.objects.filter(pk=notice.pk, status__in=statuses).update(status=outcome)


def _temporary_rejection(error):
    if isinstance(error, SMTPRecipientsRefused):
        return bool(error.recipients) and all(
            400 <= code < 500 for code, _ in error.recipients.values()
        )
    if isinstance(error, SMTPResponseException):
        return 400 <= error.smtp_code < 500
    return isinstance(error, ConnectionRefusedError)
