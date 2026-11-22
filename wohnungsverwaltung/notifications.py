"""Process mail uses existing Django mail and viewing events, with per-recipient state."""

import logging
from smtplib import SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.mail_settings import send_repliable_mail

from .access import APPLICANT_ACCESS_PERMISSION, EMPLOYEE_ACCESS_PERMISSION
from .models import Bewerbung, ProcessNotification, ViewingAppointmentEvent
from .notification_locks import application_notification_handoff
from .notification_preferences import STAFF_MAIL_TYPES, USER_MAIL_TYPES, mail_allowed

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
STAFF_KINDS = {"pre_task", "main_task", "viewing_response", "viewing_proposal"}
MAIL_TYPES = {
    "pre_receipt": "pre_application_received",
    "main_receipt": "main_application_received",
    "pre_task": "pre_application_submitted",
    "main_task": "main_application_submitted",
    "viewing_response": "viewing_accepted",
    "viewing_proposal": "viewing_proposal_changed",
    "viewing_created": "viewing_invited",
    "viewing_rescheduled": "viewing_rescheduled",
    "viewing_cancelled": "viewing_cancelled",
}
CATEGORIES = {
    kind: STAFF_MAIL_TYPES[mail_type]
    if mail_type in STAFF_MAIL_TYPES
    else USER_MAIL_TYPES[mail_type][0]
    for kind, mail_type in MAIL_TYPES.items()
}


def notification_allowed(user, kind):
    return mail_allowed(user, MAIL_TYPES[kind])


def suppress_process_notifications(*, recipient=None, groups=(), mail_types=()):
    kinds = [
        kind
        for kind, group in CATEGORIES.items()
        if group in groups or MAIL_TYPES[kind] in mail_types
    ]
    pending = ProcessNotification.objects.filter(kind__in=kinds, status__in=("pending", "failed"))
    if recipient is not None:
        pending = pending.filter(recipient=recipient)
    pending.update(status="suppressed", updated_at=timezone.now())


def staff_recipients():
    # No per-apartment assignment exists in this single-property MVP. The same
    # employee permission protects every application detail, including direct grants.
    return (
        get_user_model()
        .objects.with_perm(EMPLOYEE_ACCESS_PERMISSION)
        .filter(is_active=True)
        .exclude(email="")
    )


def _recipient_address(notice, application, user):
    if not user.is_active:
        return ""
    if notice.kind in STAFF_KINDS:
        return user.email if user.has_perm(EMPLOYEE_ACCESS_PERMISSION) else ""
    if application.person.user_id != user.pk or not user.has_perm(APPLICANT_ACCESS_PERMISSION):
        return ""
    return user.email


def _queue(application, kind, source, url, *, event=None, dispatch=True):
    if event and event.recipient_results:
        recipients = get_user_model().objects.filter(pk__in=event.recipient_results)
    elif kind in STAFF_KINDS:
        recipients = staff_recipients()
    else:
        recipients = get_user_model().objects.filter(pk=application.person.user_id)
    for user in recipients:
        notice, created = ProcessNotification.objects.get_or_create(
            application=application,
            recipient=user,
            kind=kind,
            source=source,
            defaults={
                "url": url,
                "viewing_event": event,
                "status": (
                    event.recipient_results.get(str(user.pk), "pending") if event else "pending"
                ),
            },
        )
        if created and notice.status in ("pending", "failed"):
            if not _recipient_address(notice, application, user) or not notification_allowed(
                user, kind
            ):
                notice.status = "suppressed"
                notice.save(update_fields=("status", "updated_at"))
            elif dispatch:
                transaction.on_commit(
                    lambda pk=notice.pk: send_process_notification(pk), robust=True
                )


def queue_submission_notifications(application, stage, base_url):
    for suffix, route in (
        ("receipt", "main_application_status" if stage == "main" else "pre_application_list"),
        ("task", "employee_application_detail"),
    ):
        args = [] if route == "pre_application_list" else [application.pk]
        _queue(
            application,
            f"{stage}_{suffix}",
            stage,
            base_url.rstrip("/")
            + reverse(f"wohnungsverwaltung:{route}", args=args)
            + (f"#application-{application.pk}" if route == "pre_application_list" else ""),
        )


def queue_viewing_notifications(event, *, response=False):
    appointment = event.appointment
    if response:
        kind = "viewing_response"
    elif event.kind == "proposal_changed":
        kind = "viewing_proposal"
    elif appointment.status == "cancelled":
        kind = "viewing_cancelled"
    else:
        kind = "viewing_rescheduled" if event.kind == "rescheduled" else "viewing_created"
    _queue(
        appointment.application,
        kind,
        str(event.pk),
        event.notification_url,
        event=event,
        dispatch=response,
    )
    _sync_viewing_status(event.pk)


def _current(notice, application):
    if not notice.url:
        return False
    active = application.status == "open" and application.interest_withdrawn_at is None
    if notice.viewing_event_id:
        event = ViewingAppointmentEvent.objects.select_related("appointment").get(
            pk=notice.viewing_event_id
        )
        appointment = event.appointment
        appointment.application = application
        if notice.kind == "viewing_response":
            return (
                active
                and not application.main_application_unlocked
                and appointment.pk == application.viewings.values_list("pk", flat=True).first()
                and appointment.version == event.appointment_version
                and appointment.status in ("confirmed", "applicant_declined")
                and appointment.starts_at > timezone.now()
            )
        from .viewings import notification_is_current

        return notification_is_current(event, appointment)
    if not active or application.accepted_at or hasattr(application, "rental"):
        return False
    if notice.kind.startswith("pre_"):
        return (
            not application.main_application_unlocked
            and not application.viewings.exists()
            and (
                notice.kind != "pre_task"
                or application.review_priority == Bewerbung.Priority.UNRATED
            )
        )
    return application.submitted_at is not None


def _message(notice, application):
    if notice.kind.endswith("receipt"):
        stage = "Hauptbewerbung" if notice.kind == "main_receipt" else "Besichtigungsanfrage"
        return f"Eingang Ihrer {stage} bei STEImmo", (
            f"Ihre {stage} für {application.wohnung} ist eingegangen.\n"
            "Die Verwaltung prüft; aktuell ist keine weitere Aktion erforderlich.\n"
            "Die Einreichung ist keine Zusage.\n\n"
            f"Ihre Bewerbung: {notice.url}\n"
        )
    if notice.kind in ("pre_task", "main_task"):
        action = "Hauptbewerbung prüfen" if notice.kind == "main_task" else "Neue Bewerbung prüfen"
        return (
            action,
            f"{action}. Die Verwaltung ist am Zug.\n\nGeschützter Vorgang: {notice.url}\n",
        )
    event = notice.viewing_event
    if notice.kind == "viewing_response":
        if event.after.get("status") == "confirmed":
            action = "Terminzusage berücksichtigen"
            detail = "Die Verwaltung berücksichtigt die Zusage zur geplanten Besichtigung."
        else:
            action = (
                "Terminzusage zurückgezogen"
                if event.before.get("status") == "confirmed"
                else "Besichtigung abgesagt"
            )
            detail = (
                "Die Bewerbung bleibt aktiv. "
                "Die Verwaltung prüft, ob ein neuer Termin zu planen ist."
            )
        return action, f"{action}.\n{detail}\n\nGeschützter Vorgang: {notice.url}\n"
    from .viewings import BERLIN

    appointment = event.appointment
    if notice.kind == "viewing_proposal":
        proposed = timezone.localtime(appointment.proposed_start, BERLIN)
        return "Neuer Alternativtermin für eine Besichtigung", (
            f"Wunschdatum: {proposed:%d.%m.%Y}, Beginn: {proposed:%H:%M} Uhr (Europe/Berlin).\n"
            "Der Vorschlag ist keine verbindliche Buchung. Die Verwaltung ist am Zug.\n"
            f"Bewerbung prüfen und verbindlichen Termin planen: {notice.url}\n"
        )
    start = timezone.localtime(appointment.starts_at, BERLIN)
    end = timezone.localtime(appointment.ends_at, BERLIN)
    action = (
        "Bitte sagen Sie zu oder ab."
        if appointment.status != "cancelled"
        else "Der Termin entfällt. Den aktuellen Bewerbungsstatus finden Sie im Vorgang."
    )
    return "Ihr Besichtigungstermin bei STEImmo", (
        f"Besichtigung für {application.wohnung}\nDatum: {start:%d.%m.%Y}\n"
        f"Beginn: {start:%H:%M} Uhr\nEnde: {end:%H:%M} Uhr\n"
        f"Status: {appointment.get_status_display()}\n{action}\n\n"
        f"Ihre Termine und Rückmeldung: {notice.url}\n"
    )


def _sync_viewing_status(event_id):
    if not event_id:
        return
    statuses = set(
        ProcessNotification.objects.filter(viewing_event_id=event_id).values_list(
            "status", flat=True
        )
    )
    status = next(
        (
            s
            for s in ("uncertain", "sending", "failed", "pending", "sent", "suppressed", "obsolete")
            if s in statuses
        ),
        "suppressed",
    )
    results = dict(
        ProcessNotification.objects.filter(viewing_event_id=event_id).values_list(
            "recipient_id", "status"
        )
    )
    ViewingAppointmentEvent.objects.filter(pk=event_id).update(
        notification_status=status,
        recipient_results={str(key): value for key, value in results.items()},
    )


def send_process_notification(notice_id):
    initial = ProcessNotification.objects.filter(pk=notice_id).values("application_id").first()
    if not initial:
        return False
    with application_notification_handoff(initial["application_id"]):
        with transaction.atomic():
            notice = (
                ProcessNotification.objects.select_for_update(of=("self",))
                .select_related("recipient", "viewing_event__appointment")
                .get(pk=notice_id)
            )
            # A crashed/uncertain reservation is deliberately terminal. No blind retry.
            if notice.status not in ("pending", "failed"):
                return False
            # Read related recipient data only after this short application lock,
            # so a relation changed while waiting is read from the new snapshot.
            application = Bewerbung.objects.select_for_update().get(pk=notice.application_id)
            address = _recipient_address(notice, application, notice.recipient)
            if not address or not notification_allowed(notice.recipient, notice.kind):
                notice.status = "suppressed"
            elif not _current(notice, application):
                notice.status = "obsolete"
            elif notice.attempts >= MAX_ATTEMPTS:
                return False
            else:
                notice.status = "sending"
                notice.attempts += 1
            notice.save(update_fields=("status", "attempts", "updated_at"))
        if notice.status != "sending":
            _sync_viewing_status(notice.viewing_event_id)
            return False
        subject, body = _message(notice, application)
        # Re-read after the claim commit and body preparation as well. Settings,
        # account roles or contact data can change independently of the application.
        user = get_user_model().objects.get(pk=notice.recipient_id)
        application = Bewerbung.objects.select_related("person", "wohnung").get(
            pk=notice.application_id
        )
        address = _recipient_address(notice, application, user)
        try:
            # Demo is enforced here as well as by its dummy backend.
            if settings.DEMO_MODE or not address or not notification_allowed(user, notice.kind):
                status = "suppressed"
            elif not _current(notice, application):
                status = "obsolete"
            else:
                status = "sent" if send_repliable_mail(subject, body, [address]) else "failed"
        except (
            ConnectionRefusedError,
            SMTPConnectError,
            SMTPRecipientsRefused,
            SMTPSenderRefused,
            SMTPDataError,
        ):
            status = "failed"
            logger.warning(
                "Prozessbenachrichtigung nicht an Maildienst übergeben (ID %s).", notice.pk
            )
        except Exception:
            status = "uncertain"
            logger.warning(
                "Unklares Versandergebnis einer Prozessbenachrichtigung (ID %s).", notice.pk
            )
        ProcessNotification.objects.filter(pk=notice.pk, status="sending").update(
            status=status, updated_at=timezone.now()
        )
        _sync_viewing_status(notice.viewing_event_id)
        if (
            notice.viewing_event_id
            and notice.kind != "viewing_response"
            and status in ("sent", "failed")
        ):
            from .viewings import record_viewing_event

            record_viewing_event(
                notice.viewing_event.appointment,
                kind="mail_sent" if status == "sent" else "mail_failed",
                actor=notice.viewing_event.actor,
            )
        return status == "sent"
