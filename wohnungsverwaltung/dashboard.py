"""Read-only staff overview, derived from existing application and protocol states."""

from datetime import date, datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Case, Count, Exists, F, OuterRef, Q, Subquery, Value, When, Window
from django.db.models.functions import RowNumber, TruncDate
from django.urls import reverse
from django.utils import timezone

from .models import ApplicationReviewEvent, Bewerbung, Protokoll, ViewingAppointment, Wohnung
from .viewings import BERLIN

STEP_LABELS = {
    "decision": "Hauptbewerbung prüfen und final entscheiden",
    "waiting_main": "Warten auf Hauptbewerbung",
    "result": "Besichtigungsergebnis nachtragen",
    "viewing": "Besichtigung geplant",
    "eligibility": "Auswahlvoraussetzungen prüfen",
    "unlock": "Freischaltung der Hauptbewerbung prüfen",
    "review": "Bewerbung bewerten",
    "schedule": "Besichtigung planen",
    "handover": "Übergabeprotokoll fortsetzen",
}
LIST_TITLES = {
    "aufgaben": "Jetzt bearbeiten",
    "termine": "Anstehende Besichtigungen",
}
ENTRY_FIELDS = (
    "pk",
    "person__vorname",
    "person__nachname",
    "wohnung__gebaeudenummer",
    "wohnung__wohnungsnummer",
    "wohnung__etage",
    "dashboard_step",
    "dashboard_reason",
    "task_rank",
    "task_since",
    "entry_kind",
)


def dashboard_links():
    applications = reverse("wohnungsverwaltung:employee_application_list")
    return {
        "bewerbungen": applications + "?workflow=open&segment=all",
        "rueckmeldungen": applications + "?workflow=waiting&segment=all",
        "uebergaben": reverse("wohnungsverwaltung:handover_protocol_list") + "?status=open",
        "termine": reverse("verwaltung:dashboard") + "#dashboard-calendar-title",
    }


def filter_application_workflow(applications, workflow, now):
    """Keep dashboard counts and both levels of the application workspace consistent."""
    if workflow not in ("open", "waiting"):
        return applications
    applications = applications.filter(status="open", interest_withdrawn_at__isnull=True)
    if workflow == "waiting":
        applications = applications.annotate(
            waiting_for_main=Case(
                When(main_application_unlocked=True, submitted_at__isnull=True, then=Value(True)),
                default=Value(False),
            ),
            waiting_for_confirmation=Exists(
                ViewingAppointment.objects.filter(
                    application_id=OuterRef("pk"),
                    status="planned",
                    starts_at__gt=now,
                )
            ),
        ).filter(Q(waiting_for_main=True) | Q(waiting_for_confirmation=True))
    return applications


def application_rows(now):
    open_viewings = ViewingAppointment.objects.filter(
        application_id=OuterRef("pk"), status__in=("planned", "confirmed")
    )
    applications = filter_application_workflow(Bewerbung.objects.all(), "open", now)
    applications = (
        applications.annotate(
            open_viewing_start=Subquery(open_viewings.values("starts_at")[:1]),
            open_viewing_end=Subquery(open_viewings.values("ends_at")[:1]),
            open_viewing_status=Subquery(open_viewings.values("status")[:1]),
            has_completed_viewing=Exists(
                ViewingAppointment.objects.filter(application_id=OuterRef("pk"), status="completed")
            ),
            has_current_approval=Exists(
                ApplicationReviewEvent.objects.filter(
                    application_id=OuterRef("pk"),
                    kind="eligibility_approved",
                    requirements_version=OuterRef("wohnung__requirements_version"),
                )
            ),
        )
        .annotate(
            dashboard_reason=Case(
                When(
                    personenanzahl__gt=F("wohnung__max_occupants"),
                    then=Value("Die Personenhöchstzahl der Wohnung wird überschritten."),
                ),
                When(
                    wohnung__pet_review_required=True,
                    haustiere=True,
                    has_current_approval=False,
                    then=Value("Tierhaltung muss geprüft werden"),
                ),
                default=Value(""),
            ),
        )
        .annotate(
            dashboard_step=Case(
                When(submitted_at__isnull=False, then=Value("decision")),
                When(main_application_unlocked=True, then=Value("waiting_main")),
                When(open_viewing_end__lte=now, then=Value("result")),
                When(open_viewing_end__gt=now, then=Value("viewing")),
                When(~Q(dashboard_reason=""), then=Value("eligibility")),
                When(has_completed_viewing=True, then=Value("unlock")),
                When(review_priority=0, then=Value("review")),
                default=Value("schedule"),
            ),
        )
        .annotate(
            task_rank=Case(
                When(dashboard_step="result", then=Value(0)),
                When(dashboard_step="decision", then=Value(1)),
                default=Value(2),
            ),
            task_since=Case(
                When(dashboard_step="result", then=F("open_viewing_end")),
                When(dashboard_step="decision", then=F("submitted_at")),
                default=F("created_at"),
            ),
            entry_kind=Value("application"),
        )
    )
    return applications


def format_rows(rows, *, waiting=False):
    entries = []
    for row in rows:
        apartment = Wohnung(
            gebaeudenummer=row["wohnung__gebaeudenummer"],
            wohnungsnummer=row["wohnung__wohnungsnummer"],
            etage=row["wohnung__etage"],
        )
        kind = row["entry_kind"]
        route = "handover_protocol_detail" if kind == "handover" else "employee_application_detail"
        entries.append(
            {
                "id": row["pk"],
                "person": f"{row['person__vorname']} {row['person__nachname']}",
                "apartment": str(apartment),
                "label": (
                    "Warten auf Terminbestätigung"
                    if waiting and row["dashboard_step"] != "waiting_main"
                    else STEP_LABELS[row["dashboard_step"]]
                ),
                "reason": row["dashboard_reason"] if row["dashboard_step"] == "eligibility" else "",
                "since": row["task_since"],
                "since_label": "Offen seit"
                if row["dashboard_step"] in ("result", "decision", "handover")
                else "Bewerbung eingegangen am",
                "url": reverse(f"wohnungsverwaltung:{route}", args=[row["pk"]]),
            }
        )
    return entries


def format_appointments(appointments):
    return [
        {
            "id": appointment.pk,
            "person": str(appointment.application.person),
            "apartment": str(appointment.application.wohnung),
            "label": appointment.get_status_display(),
            "starts_at": appointment.starts_at,
            "ends_at": appointment.ends_at,
            "url": reverse(
                "wohnungsverwaltung:employee_application_detail", args=[appointment.application_id]
            ),
        }
        for appointment in appointments
    ]


def midnight(day):
    return datetime.combine(day, time.min, tzinfo=BERLIN)


def selected_date(value):
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            return None
        # Leave room for normalising and advancing a full calendar week.
        return day if date.min + timedelta(days=7) <= day <= date.max - timedelta(days=14) else None
    except (ValueError, TypeError):
        return None


def dashboard_context(query):
    now = timezone.now()
    today = timezone.localdate(now, BERLIN)
    current_week = today - timedelta(days=today.weekday())
    requested_week = selected_date(query.get("woche")) or current_week
    week_start = max(current_week, requested_week - timedelta(days=requested_week.weekday()))
    week_end = week_start + timedelta(days=7)

    applications = application_rows(now)
    application_tasks = applications.exclude(dashboard_step__in=("waiting_main", "viewing"))
    waiting = filter_application_workflow(applications, "waiting", now)
    protocols = Protokoll.objects.filter(status="open").annotate(
        dashboard_step=Value("handover"),
        dashboard_reason=Value(""),
        task_rank=Value(2),
        task_since=F("created_at"),
        entry_kind=Value("handover"),
    )
    tasks = (
        application_tasks.order_by()
        .values(*ENTRY_FIELDS)
        .union(protocols.order_by().values(*ENTRY_FIELDS))
        .order_by("task_rank", "task_since", "pk")
    )
    appointments = (
        ViewingAppointment.objects.filter(
            status__in=("planned", "confirmed"),
            ends_at__gt=now,
            application__status="open",
            application__interest_withdrawn_at__isnull=True,
        )
        .select_related("application__person", "application__wohnung")
        .order_by("starts_at", "pk")
    )
    upcoming = appointments.filter(starts_at__lt=midnight(today + timedelta(days=8)))
    counts = {
        "applications": applications.count(),
        "appointments": upcoming.count(),
        "waiting": waiting.count(),
        "handovers": protocols.count(),
    }
    metrics = [
        {
            "section": "bewerbungen",
            "label": "Offene Bewerbungen",
            "count": counts["applications"],
            "description": "Aktiv und nicht zurückgezogen · gesamter Bestand",
        },
        {
            "section": "termine",
            "label": "Anstehende Besichtigungen",
            "count": counts["appointments"],
            "description": "Heute und nächste sieben Tage · einschließlich laufender Termine",
        },
        {
            "section": "rueckmeldungen",
            "label": "Ausstehende Rückmeldungen",
            "count": counts["waiting"],
            "description": (
                "Bewerbungen mit fehlender Terminbestätigung oder Hauptbewerbung · ohne Frist"
            ),
        },
        {
            "section": "uebergaben",
            "label": "Offene Übergabeprotokolle",
            "count": counts["handovers"],
            "description": "In Bearbeitung · ohne Formularentwürfe · gesamter Bestand",
        },
    ]
    links = dashboard_links()
    for metric in metrics:
        metric["href"] = links[metric["section"]]
    section = query.get("bereich", "")
    context = {
        "counts": counts,
        "metrics": metrics,
        "section": section,
        "today": today,
        "week_start": week_start,
        "week_last": week_end - timedelta(days=1),
        "waiting_list_url": links["rueckmeldungen"],
    }
    if section in LIST_TITLES:
        day = selected_date(query.get("datum")) if section == "termine" else None
        listing = {
            "aufgaben": tasks,
            "termine": appointments.filter(
                starts_at__gte=midnight(day), starts_at__lt=midnight(day + timedelta(days=1))
            )
            if day
            else upcoming,
        }[section]
        page = Paginator(listing, 20).get_page(query.get("page"))
        context.update(
            list_title=LIST_TITLES[section],
            page_obj=page,
            selected_day=day,
            entries=format_appointments(page) if section == "termine" else format_rows(page),
        )
        return context

    calendar = appointments.filter(
        starts_at__gte=midnight(week_start), starts_at__lt=midnight(week_end)
    ).annotate(calendar_day=TruncDate("starts_at", tzinfo=BERLIN))
    day_counts = dict(
        calendar.order_by()
        .values("calendar_day")
        .annotate(total=Count("pk"))
        .values_list("calendar_day", "total")
    )
    previews = calendar.annotate(
        day_row=Window(
            expression=RowNumber(),
            partition_by=[F("calendar_day")],
            order_by=[F("starts_at").asc(), F("pk").asc()],
        )
    ).filter(day_row__lte=3)
    by_day = {}
    for appointment in previews:
        by_day.setdefault(appointment.calendar_day, []).append(appointment)
    context.update(
        task_entries=format_rows(tasks[:3]),
        task_count=tasks.count(),
        waiting_entries=format_rows(
            waiting.order_by("created_at", "pk").values(*ENTRY_FIELDS)[:5], waiting=True
        ),
        calendar_days=[
            {
                "date": day,
                "is_today": day == today,
                "count": day_counts.get(day, 0),
                "entries": format_appointments(by_day.get(day, [])),
            }
            for day in (week_start + timedelta(days=offset) for offset in range(7))
        ],
        previous_week=week_start - timedelta(days=7) if week_start > current_week else None,
        next_week=week_end if week_end <= date.max - timedelta(days=14) else None,
    )
    return context
