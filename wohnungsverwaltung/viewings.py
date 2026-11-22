"""Shared appointment history and notifications for staff and applicant actions."""

from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import (
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    ViewingAppointment,
    ViewingAppointmentEvent,
)

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
        from .notifications import queue_viewing_notifications

        queue_viewing_notifications(event)
        transaction.on_commit(lambda: send_viewing_notification(event.pk), robust=True)
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
    from .notifications import (
        _sync_viewing_status,
        queue_viewing_notifications,
        send_process_notification,
    )

    event = (
        ViewingAppointmentEvent.objects.select_related("appointment__application__person")
        .filter(pk=event_id)
        .first()
    )
    if event is None:
        return False
    if not notification_is_current(event, event.appointment):
        if event.notification_status != "none":
            event.notification_status = "obsolete"
            event.save(update_fields=("notification_status",))
        event.deliveries.filter(status__in=("pending", "failed")).update(status="obsolete")
        return False
    # Migrate a still-pending legacy event only when explicitly processed. Sent,
    # suppressed and uncertain messages must never produce new recipient intents.
    if not event.deliveries.exists() and event.notification_status in ("pending", "failed"):
        from .notification_locks import application_notification_handoff

        with application_notification_handoff(event.appointment.application_id):
            with transaction.atomic():
                application = Bewerbung.objects.select_for_update().get(
                    pk=event.appointment.application_id
                )
                event.appointment.application = application
                queue_viewing_notifications(event)
    sent = False
    for notice_id in event.deliveries.values_list("pk", flat=True):
        sent = send_process_notification(notice_id) or sent
    _sync_viewing_status(event.pk)
    event.refresh_from_db()
    if not event.deliveries.exists():
        event.notification_status = "suppressed"
        event.save(update_fields=("notification_status",))
    return sent


def cancel_open_viewings(application_id, *, reason, actor=None, notify=False):
    # Caller holds the application row lock inside its existing transaction.
    for appointment in ViewingAppointment.objects.select_for_update().filter(
        application_id=application_id, status__in=("planned", "confirmed")
    ):
        before = appointment.snapshot()
        # Responses and proposals point to the staff area. A cancellation sent to
        # the applicant must retain the applicant link from the invitation.
        previous_notice = (
            appointment.events.filter(kind__in=("created", "rescheduled"))
            .exclude(notification_url="")
            .first()
        )
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
