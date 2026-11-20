from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .access import employee_required, global_settings_required
from .models import GlobalSettings, GlobalSettingsChange
from .notification_forms import GlobalNotificationForm
from .notification_preferences import USER_MAIL_TYPES


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
