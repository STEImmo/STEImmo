"""Mail categories and the delivery decision for an eligible recipient."""

from .access import (
    APPLICANT_ACCESS_PERMISSION,
    EMPLOYEE_ACCESS_PERMISSION,
    TENANT_ACCESS_PERMISSION,
)
from .models import DecisionNotification, GlobalSettings, NotificationPreference

USER_GROUPS = {
    "application_receipts": (
        "Eingangsbestätigungen meiner Bewerbungen",
        "Bestätigung nach verbindlicher Abgabe einer Vor- oder Hauptbewerbung.",
    ),
    "viewing_changes": (
        "Besichtigungstermine und Änderungen",
        "Einladungen, Verschiebungen und Absagen.",
    ),
    "application_decisions": (
        "Freischaltung und Entscheidungen zu meiner Bewerbung",
        "Freischaltung der Hauptbewerbung, Annahme und Ablehnung.",
    ),
    "documents": (
        "Bereitgestellte Dokumente und abgeschlossene Vorgänge",
        "Hinweise auf Unterlagen, den Vermietungsabschluss und finale Übergabeprotokolle.",
    ),
    "user_reminders": (
        "Erinnerungen an meine offenen Schritte",
        "Hinweise auf noch ausstehende Antworten oder Einreichungen.",
    ),
}
STAFF_GROUPS = {
    "new_applications": (
        "Neue und eingereichte Bewerbungen",
        "Neue Vorbewerbungen und verbindlich eingereichte Hauptbewerbungen.",
    ),
    "viewing_responses": (
        "Terminrückmeldungen und Alternativvorschläge",
        "Zu- und Absagen, zurückgezogene Zusagen und Gegenvorschläge.",
    ),
    "application_changes": (
        "Rückzüge und dokumentierte Vertragsrückläufe",
        "Vorgänge, die eine erneute Bearbeitung erfordern können.",
    ),
    "staff_digest": (
        "Gebündelte Erinnerungen an offene Bearbeitung",
        "Tageszusammenfassung der offenen Aufgaben.",
    ),
}
USER_MAIL_TYPES = {
    "pre_application_received": ("application_receipts", "Eingang der Vorbewerbung"),
    "main_application_received": ("application_receipts", "Eingang der Hauptbewerbung"),
    "viewing_invited": ("viewing_changes", "Einladung zur Besichtigung"),
    "viewing_rescheduled": ("viewing_changes", "Besichtigung verschoben"),
    "viewing_cancelled": ("viewing_changes", "Besichtigung abgesagt"),
    "main_application_invited": ("application_decisions", "Einladung zur Hauptbewerbung"),
    "application_accepted": ("application_decisions", "Bewerbung angenommen"),
    "application_rejected": ("application_decisions", "Bewerbung abgelehnt"),
    "contract_documents_ready": ("documents", "Vertragsunterlagen bereitgestellt"),
    "unit_documents_ready": ("documents", "Wohnungsunterlagen bereitgestellt"),
    "rental_completed": ("documents", "Vermietung abgeschlossen"),
    "handover_finalized": ("documents", "Finales Übergabeprotokoll bereitgestellt"),
    "viewing_response_due": ("user_reminders", "Terminantwort ausstehend"),
    "main_application_due": ("user_reminders", "Hauptbewerbung ausstehend"),
}
STAFF_MAIL_TYPES = {
    "pre_application_submitted": "new_applications",
    "main_application_submitted": "new_applications",
    "viewing_accepted": "viewing_responses",
    "viewing_declined": "viewing_responses",
    "viewing_acceptance_withdrawn": "viewing_responses",
    "viewing_proposal_changed": "viewing_responses",
    "application_withdrawn": "application_changes",
    "contract_return_recorded": "application_changes",
    "staff_daily_digest": "staff_digest",
}


def suppress_decision_notifications(*, mail_types, account=None):
    """Record delivery opt-outs in the same transaction as the settings change."""
    states = DecisionNotification.Status
    notices = DecisionNotification.objects.filter(
        kind__in=mail_types, status__in=(states.PENDING, states.RETRY, states.SENDING)
    )
    if account is not None:
        notices = notices.filter(recipient=account)
    notices.update(status=states.SUPPRESSED)


def suppress_personal_decision_notifications(account, disabled_groups):
    mail_types = {kind for kind, (group, _) in USER_MAIL_TYPES.items() if group in disabled_groups}
    mail_types.update(kind for kind, group in STAFF_MAIL_TYPES.items() if group in disabled_groups)
    suppress_decision_notifications(mail_types=mail_types, account=account)


def mail_allowed(account, mail_type):
    """Apply preferences after the caller checks the current event and object access."""
    if account is None or not account.is_active or not account.email:
        return False
    if mail_type in USER_MAIL_TYPES:
        group = USER_MAIL_TYPES[mail_type][0]
        permissions = (
            (APPLICANT_ACCESS_PERMISSION, TENANT_ACCESS_PERMISSION)
            if group == "documents"
            else (APPLICANT_ACCESS_PERMISSION,)
        )
        if not any(account.has_perm(permission) for permission in permissions):
            return False
        policy = (
            GlobalSettings.objects.filter(pk=1).values_list("user_mail_types", flat=True).first()
        )
        if not (policy or {}).get(mail_type, True):
            return False
    else:
        group = STAFF_MAIL_TYPES[mail_type]
        if not account.has_perm(EMPLOYEE_ACCESS_PERMISSION):
            return False
    choices = (
        NotificationPreference.objects.filter(account=account)
        .values_list("choices", flat=True)
        .first()
    )
    return (choices or {}).get(group) != "off"
