"""Shared appointment history and notifications for staff and applicant actions."""

import logging
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .access import EMPLOYEE_ACCESS_PERMISSION
from .models import (
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    ViewingAppointment,
    ViewingAppointmentEvent,
)
from .notification_preferences import mail_allowed

logger = logging.getLogger(__name__)
BERLIN = ZoneInfo("Europe/Berlin")


def viewing_eligibility_error(application):
    if application.status != BewerbungStatus.OPEN or application.interest_withdrawn_at:
        return "Die Bewerbung ist nicht mehr aktiv."
    if application.review_priority == Bewerbung.Priority.UNRATED:
        return "Bitte bewerten Sie zunächst die Priorität der Bewerbung."
    unit = application.wohnung
    if unit.max_occupants is not None and application.personenanzahl > unit.max_occupants:
        return "Die Personenhöchstzahl der Wohnung wird überschritten."
    if (
        application.suitability_review_flags
        and not application.review_events.filter(
            kind=ApplicationReviewEvent.Kind.ELIGIBILITY_APPROVED,
            requirements_version=unit.requirements_version,
        ).exists()
    ):
        return "Bitte geben Sie zuerst die aktuelle Haustierprüfung frei."
    return ""


def record_viewing_event(
    appointment, *, kind, actor=None, reason="", before=None, notify=False, notification_url=""
):
    event = ViewingAppointmentEvent.objects.create(
        appointment=appointment,
        kind=kind,
        actor=actor,
        reason=reason,
        before=before or {},
        after=appointment.snapshot(),
        appointment_version=appointment.version,
        notification_status="pending" if notify else "none",
        notification_url=notification_url,
    )
    if notify:
        transaction.on_commit(lambda: send_viewing_notification(event.pk))
    return event


def notification_is_current(event, appointment, *, latest_appointment_id=None):
    if latest_appointment_id is None:
        latest_appointment_id = appointment.application.viewings.values_list(
            "pk", flat=True
        ).first()
    if latest_appointment_id != appointment.pk:
        return False
    if event.appointment_version != appointment.version or not event.notification_url:
        return False
    if event.kind == "proposal_changed":
        return (
            appointment.can_propose
            and appointment.proposed_start is not None
            and appointment.proposed_start > timezone.now()
        )
    if appointment.status == ViewingAppointment.Status.CANCELLED:
        return True
    return (
        appointment.can_respond
        and appointment.application.status == BewerbungStatus.OPEN
        and appointment.application.interest_withdrawn_at is None
    )


def send_viewing_notification(event_id, actor=None):
    # Lock the application first, like all applicant mutations. Holding these
    # locks during the bounded SMTP call prevents sending a superseded notice.
    initial = (
        ViewingAppointmentEvent.objects.filter(pk=event_id)
        .values("appointment__application_id", "appointment_id")
        .first()
    )
    if initial is None:
        return False
    with transaction.atomic():
        application = (
            Bewerbung.objects.select_for_update(of=("self",))
            .select_related("person", "wohnung")
            .get(pk=initial["appointment__application_id"])
        )
        appointment = ViewingAppointment.objects.select_for_update().get(
            pk=initial["appointment_id"]
        )
        appointment.application = application
        event = ViewingAppointmentEvent.objects.select_for_update().get(pk=event_id)
        if event.notification_status not in ("pending", "failed"):
            return False
        if not notification_is_current(event, appointment):
            if event.notification_status != "none":
                event.notification_status = "obsolete"
                event.save(update_fields=("notification_status",))
            return False
        start = timezone.localtime(appointment.starts_at, BERLIN)
        end = timezone.localtime(appointment.ends_at, BERLIN)
        body = (
            f"Guten Tag {application.person.vorname} {application.person.nachname},\n\n"
            f"Besichtigung für {application.wohnung}\n"
            f"Datum: {start:%d.%m.%Y}\nBeginn: {start:%H:%M} Uhr\nEnde: {end:%H:%M} Uhr\n"
            f"Status: {appointment.get_status_display()}\n\n"
            f"Ihre Termine und Rückmeldung: {event.notification_url}\n"
        )
        account_id = application.person.user_id
        recipient_ids = [str(account_id)] if account_id else []
        if appointment.status == ViewingAppointment.Status.CANCELLED:
            mail_type = "viewing_cancelled"
        elif event.kind == "rescheduled":
            mail_type = "viewing_rescheduled"
        else:
            mail_type = "viewing_invited"
        subject = "Ihr Besichtigungstermin bei STEImmo"
        if event.kind == "proposal_changed":
            proposed = timezone.localtime(appointment.proposed_start, BERLIN)
            subject = "Neuer Alternativtermin für eine Besichtigung"
            body = (
                f"Für die Besichtigung zu {application.wohnung} "
                "wurde ein Alternativtermin vorgeschlagen.\n"
                f"Wunschdatum: {proposed:%d.%m.%Y}\n"
                f"Beginn: {proposed:%H:%M} Uhr (Europe/Berlin)\n\n"
                f"Bewerbung prüfen und verbindlichen Termin planen: {event.notification_url}\n"
                "Der Vorschlag ist keine verbindliche Buchung.\n"
            )
            mail_type = "viewing_proposal_changed"
            recipient_ids = [
                str(account_id)
                for account_id in get_user_model()
                .objects.with_perm(EMPLOYEE_ACCESS_PERMISSION)
                .values_list("pk", flat=True)
            ]
        results = event.recipient_results
        pending = (
            [key for key, outcome in results.items() if outcome == "failed"]
            if results
            else recipient_ids
        )
        for key in pending:
            recipient = (
                get_user_model().objects.filter(pk=key).first() if key in recipient_ids else None
            )
            if not mail_allowed(recipient, mail_type):
                results[key] = "suppressed"
                continue
            try:
                sent = send_mail(subject, body, None, [recipient.email], fail_silently=False)
            except Exception:
                logger.warning("Terminbenachrichtigung konnte nicht versendet werden.")
                sent = False
            results[key] = "sent" if sent else "failed"

        if "failed" in results.values():
            status = "failed"
        elif "sent" in results.values():
            status = "sent"
        else:
            status = "suppressed"
        event.notification_status = status
        event.save(update_fields=("notification_status", "recipient_results"))
        if status != "suppressed":
            record_viewing_event(
                appointment,
                kind="mail_sent" if status == "sent" else "mail_failed",
                actor=actor or event.actor,
            )
        return status == "sent"


def cancel_open_viewings(application_id, *, reason, actor=None, notify=False):
    # Caller holds the application row lock inside its existing transaction.
    for appointment in ViewingAppointment.objects.select_for_update().filter(
        application_id=application_id, status__in=("planned", "confirmed")
    ):
        before = appointment.snapshot()
        previous_notice = appointment.events.exclude(notification_url="").first()
        appointment.status = "cancelled"
        appointment.version += 1
        appointment.save(update_fields=("status", "version", "updated_at"))
        record_viewing_event(
            appointment,
            kind="status_changed",
            actor=actor,
            reason=reason,
            before=before,
            notify=notify,
            notification_url=previous_notice.notification_url if previous_notice else "",
        )
