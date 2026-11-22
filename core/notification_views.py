from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from wohnungsverwaltung.models import NotificationPreference
from wohnungsverwaltung.notification_forms import PersonalNotificationForm
from wohnungsverwaltung.notification_preferences import (
    STAFF_GROUPS,
    USER_GROUPS,
    suppress_personal_decision_notifications,
)
from wohnungsverwaltung.notifications import suppress_process_notifications


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def notifications(request):
    account = request.user
    status = 200
    if request.method == "POST":
        form = PersonalNotificationForm(request.POST, account=account)
        if form.is_valid():
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=account.pk)
                current, _ = NotificationPreference.objects.select_for_update().get_or_create(
                    account=account
                )
                if current.version != form.cleaned_data["version"]:
                    status = 409
                else:
                    choices = current.choices.copy()
                    submitted = form.preferences()
                    disabled_groups = {key for key, value in submitted.items() if value == "off"}
                    if disabled_groups:
                        suppress_process_notifications(recipient=account, groups=disabled_groups)
                        suppress_personal_decision_notifications(account, disabled_groups)
                    for key, value in submitted.items():
                        if value == ("on" if key in STAFF_GROUPS else "default"):
                            choices.pop(key, None)
                        else:
                            choices[key] = value
                    if choices != current.choices:
                        if choices.get("user_reminders") != current.choices.get("user_reminders"):
                            current.reminders_changed_at = timezone.now()
                        current.choices = choices
                        current.version += 1
                        current.save(update_fields=["choices", "version", "reminders_changed_at"])
            if status != 409:
                messages.success(request, "Einstellungen gespeichert.")
                return redirect("profile:notifications")
        else:
            status = 400
    if request.method == "GET" or status == 409:
        current = (
            NotificationPreference.objects.filter(account=account).first()
            or NotificationPreference()
        )
        initial = {key: current.choices.get(key, "default") for key in USER_GROUPS}
        initial.update({key: current.choices.get(key) != "off" for key in STAFF_GROUPS})
        form = PersonalNotificationForm(
            account=account, initial={"version": current.version, **initial}
        )
    return render(
        request,
        "core/notifications.html",
        {
            "form": form,
            "conflict": status == 409,
        },
        status=status,
    )
