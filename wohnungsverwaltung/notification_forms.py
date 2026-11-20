from django import forms

from .access import (
    APPLICANT_ACCESS_PERMISSION,
    EMPLOYEE_ACCESS_PERMISSION,
    TENANT_ACCESS_PERMISSION,
)
from .notification_preferences import STAFF_GROUPS, USER_GROUPS, USER_MAIL_TYPES


class VersionedNotificationForm(forms.Form):
    version = forms.IntegerField(min_value=0, max_value=2**63 - 1, widget=forms.HiddenInput)

    def clean(self):
        cleaned = super().clean()
        allowed = self.fields.keys() | {"csrfmiddlewaretoken"}
        for key, values in self.data.lists():
            if key not in allowed or len(values) != 1:
                raise forms.ValidationError("Das Formular enthält unzulässige Angaben.")
            field = self.fields.get(key)
            if isinstance(field, forms.BooleanField) and values != ["on"]:
                self.add_error(key, "Ungültige Auswahl.")
        return cleaned


class GlobalNotificationForm(VersionedNotificationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, (_, label) in USER_MAIL_TYPES.items():
            self.fields[key] = forms.BooleanField(
                label=label,
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            )

    def sections(self):
        return [
            (label, [self[key] for key, (group, _) in USER_MAIL_TYPES.items() if group == category])
            for category, (label, _) in USER_GROUPS.items()
        ]


class PersonalNotificationForm(VersionedNotificationForm):
    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        if any(
            account.has_perm(p) for p in (APPLICANT_ACCESS_PERMISSION, TENANT_ACCESS_PERMISSION)
        ):
            for key, (label, help_text) in USER_GROUPS.items():
                self.fields[key] = forms.ChoiceField(
                    label=label,
                    help_text=help_text,
                    choices=(("default", "Verwaltungsstandard"), ("on", "An"), ("off", "Aus")),
                    widget=forms.Select(attrs={"class": "uk-select"}),
                )
        if account.has_perm(EMPLOYEE_ACCESS_PERMISSION):
            for key, (label, help_text) in STAFF_GROUPS.items():
                self.fields[key] = forms.BooleanField(
                    label=label,
                    help_text=help_text,
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
                )

    def sections(self):
        return [
            (label, fields)
            for label, groups in (
                ("Bewerbung und Mietverhältnis", USER_GROUPS),
                ("Verwaltung", STAFF_GROUPS),
            )
            if (fields := [self[key] for key in groups if key in self.fields])
        ]

    def preferences(self):
        return {
            key: ("on" if value else "off") if key in STAFF_GROUPS else value
            for key, value in self.cleaned_data.items()
            if key != "version"
        }
