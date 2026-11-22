"""Daily, role-scoped reminders derived from the staff application workflow."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .dashboard import application_rows
from .models import DecisionNotification, ProcessNotification, ViewingAppointment
from .notification_preferences import mail_allowed
from .notifications import staff_recipients
from .viewings import BERLIN

DIGEST_KIND = "staff_daily_digest"
DIGEST_OBJECT = UUID(int=0)
SEND_TIME = time(9)


@dataclass(frozen=True)
class StaffTask:
    application_id: UUID
    reason: str
    since: datetime
    source: str
    instant_kind: str = ""
    deadline: datetime | None = None

    @property
    def key(self):
        return f"{self.application_id}/{self.reason}/{self.source}/{self.since.isoformat()}"


def weekday_shift(day, count):
    step = 1 if count > 0 else -1
    for _ in range(abs(count)):
        day += timedelta(days=step)
        while day.weekday() >= 5:
            day += timedelta(days=step)
    return day


def send_slot(now):
    local = now.astimezone(BERLIN)
    if local.weekday() < 5 and local.time() >= SEND_TIME:
        return datetime.combine(local.date(), SEND_TIME, BERLIN)
    return None


def is_due(task, now, slot):
    since = task.since.astimezone(BERLIN)
    regular_due = datetime.combine(weekday_shift(since.date(), 2), since.time(), BERLIN)
    if task.deadline is None:
        return regular_due <= slot
    deadline_day = task.deadline.astimezone(BERLIN).date()
    last_day = weekday_shift(deadline_day, -1)
    return task.since <= now < task.deadline and (regular_due <= slot or slot.date() >= last_day)


def current_staff_task(application, now):
    if application.dashboard_reason or application.accepted_at:
        return None
    if application.dashboard_step == "decision" and application.main_application_accessible:
        return StaffTask(
            application.pk, "Hauptbewerbung prüfen", application.submitted_at, "main", "main_task"
        )
    if application.main_application_unlocked:
        return None

    viewing = application.viewings.first()
    if viewing is None:
        if application.dashboard_step == "review":
            return StaffTask(
                application.pk, "Erstbewerbung prüfen", application.created_at, "pre", "pre_task"
            )
        return None

    events = viewing.events.filter(appointment_version=viewing.version).order_by(
        "-created_at", "-event_id"
    )
    if (
        application.dashboard_step == "unlock"
        and viewing.status == ViewingAppointment.Status.COMPLETED
    ):
        completed = events.filter(
            kind__in=("recorded", "status_changed"), after__status="completed"
        ).first()
        if completed:
            return StaffTask(
                application.pk,
                "Über Hauptbewerbungsfreigabe entscheiden",
                completed.created_at,
                str(completed.pk),
            )
    if viewing.status == ViewingAppointment.Status.APPLICANT_DECLINED:
        if viewing.proposed_start and viewing.proposed_start <= now:
            return None
        response = events.filter(
            kind__in=("proposal_changed", "status_changed"),
            after__status="applicant_declined",
        ).first()
        if response and response.actor_id == application.person.user_id and response.actor_id:
            proposal = response.kind == "proposal_changed"
            return StaffTask(
                application.pk,
                "Alternativtermin prüfen" if proposal else "Besichtigung neu planen",
                response.created_at,
                str(response.pk),
                "viewing_proposal" if proposal else "viewing_response",
                viewing.proposed_start or (viewing.starts_at if viewing.starts_at > now else None),
            )
    return None


def due_tasks(now, slot, application_ids=None):
    applications = application_rows(now).select_related("person")
    if application_ids is not None:
        applications = applications.filter(pk__in=application_ids)
    tasks = (current_staff_task(application, now) for application in applications.iterator())
    return sorted(
        (task for task in tasks if task and is_due(task, now, slot)),
        key=lambda task: (task.since, task.key),
    )


def unsent_tasks(tasks, recipient, slot):
    sent = set(
        ProcessNotification.objects.filter(
            recipient=recipient,
            application_id__in=[task.application_id for task in tasks],
            kind__in=("pre_task", "main_task", "viewing_response", "viewing_proposal"),
            status=ProcessNotification.Status.SENT,
            updated_at__gte=slot,
        ).values_list("application_id", "kind", "source")
    )
    return [
        task for task in tasks if (task.application_id, task.instant_kind, task.source) not in sent
    ]


def digest_candidates(now):
    slot = send_slot(now)
    if slot is None:
        return
    day = slot.date().isoformat()
    existing = DecisionNotification.objects.filter(
        kind=DIGEST_KIND, object_id=DIGEST_OBJECT, version=day
    ).values_list("recipient_id", flat=True)
    tasks = due_tasks(now, slot)
    if tasks:
        for recipient in staff_recipients().exclude(pk__in=existing):
            if mail_allowed(recipient, DIGEST_KIND):
                entries = unsent_tasks(tasks, recipient, slot)
                if entries:
                    yield recipient, day, entries


@transaction.atomic
def queue_digest(recipient, day, entries):
    recipient = type(recipient).objects.select_for_update().filter(pk=recipient.pk).first()
    now = timezone.now()
    slot = send_slot(now)
    if slot is None or slot.date().isoformat() != day or not mail_allowed(recipient, DIGEST_KIND):
        return False
    versions = {task.application_id: task.key for task in entries}
    tasks = due_tasks(now, slot, versions)
    current = {
        str(task.application_id): task.key
        for task in unsent_tasks(tasks, recipient, slot)
        if versions.get(task.application_id) == task.key
    }
    if not current:
        return False
    _, created = DecisionNotification.objects.get_or_create(
        kind=DIGEST_KIND,
        object_id=DIGEST_OBJECT,
        version=day,
        recipient=recipient,
        defaults={"task_versions": current},
    )
    return created


def digest_message(notice, recipient):
    now = timezone.now()
    slot = send_slot(now)
    if (
        slot is None
        or slot.date().isoformat() != notice.version
        or not mail_allowed(recipient, DIGEST_KIND)
    ):
        return None

    tasks = due_tasks(now, slot, notice.task_versions)
    entries = [
        task
        for task in unsent_tasks(tasks, recipient, slot)
        if notice.task_versions.get(str(task.application_id)) == task.key
    ]
    # Persist pruning so a retry cannot reintroduce an entry removed from this digest.
    retained = {str(task.application_id): task.key for task in entries}
    if retained != notice.task_versions:
        notice.task_versions = retained
        notice.save(update_fields=["task_versions"])
    if not entries:
        return None

    origin = (notice.origin or settings.DECISION_NOTIFICATION_ORIGIN).rstrip("/")
    lines = ["Für diese Vorgänge steht eine Bearbeitung durch die Verwaltung aus.", ""]
    for task in entries:
        path = reverse("wohnungsverwaltung:employee_application_detail", args=[task.application_id])
        since = task.since.astimezone(BERLIN).strftime("%d.%m.%Y, %H:%M Uhr")
        lines.extend([f"{task.reason} (offen seit {since})", f"{origin}{path}", ""])
    return "Offene Verwaltungsaufgaben", "\n".join(lines).rstrip(), "", ""
