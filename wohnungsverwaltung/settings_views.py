from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .access import employee_required, global_settings_required
from .models import GlobalSettings, GlobalSettingsChange


class GlobalSettingsForm(forms.Form):
    version = forms.IntegerField(min_value=0, max_value=2**63 - 1, widget=forms.HiddenInput)
    optional_user_emails_enabled = forms.BooleanField(
        label="Optionale E-Mails an Nutzer aktivieren",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )

    def clean(self):
        cleaned = super().clean()
        if self.data.getlist("optional_user_emails_enabled") not in ([], ["on"]):
            self.add_error("optional_user_emails_enabled", "Ungültige Auswahl.")
        if len(self.data.getlist("version")) != 1:
            self.add_error("version", "Ungültige Formularversion.")
        return cleaned


@employee_required
@global_settings_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def global_settings(request):
    status = 200
    current = None
    if request.method == "POST":
        form = GlobalSettingsForm(request.POST)
        if form.is_valid():
            enabled = form.cleaned_data["optional_user_emails_enabled"]
            with transaction.atomic():
                current, _ = GlobalSettings.objects.select_for_update().get_or_create(pk=1)
                if current.version != form.cleaned_data["version"]:
                    form.add_error(None, "Die Einstellungen wurden inzwischen geändert.")
                    status = 409
                elif current.optional_user_emails_enabled != enabled:
                    current.optional_user_emails_enabled = enabled
                    current.version += 1
                    current.save(update_fields=["optional_user_emails_enabled", "version"])
                    GlobalSettingsChange.objects.create(
                        actor_account_id=request.user.pk,
                        changed_fields=["optional_user_emails_enabled"],
                    )
            if status != 409:
                messages.success(request, "Einstellungen gespeichert.")
                return redirect("verwaltung:global_settings")
        else:
            status = 400
    else:
        settings = GlobalSettings.objects.filter(pk=1).first() or GlobalSettings()
        form = GlobalSettingsForm(
            initial={
                "version": settings.version,
                "optional_user_emails_enabled": settings.optional_user_emails_enabled,
            }
        )

    return render(
        request,
        "wohnungsverwaltung/global_settings.html",
        {"form": form, "conflict": status == 409, "current": current},
        status=status,
    )
