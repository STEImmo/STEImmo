from django import forms

from .forms import ProtocolConfirmationForm
from .handover_export import clean_signature


class ProtocolSigningForm(ProtocolConfirmationForm):
    content_token = forms.CharField(widget=forms.HiddenInput)
    mitarbeiter = forms.FileField(label="Mitarbeiterunterschrift")
    mieter = forms.FileField(label="Mieterunterschrift", required=False)
    tenant_mode = forms.ChoiceField(
        choices=[("signed", "Mieter unterschreibt"), ("missing", "Mieterunterschrift fehlt")]
    )
    reason = forms.CharField(
        label="Begründung",
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
    )

    def clean_mitarbeiter(self):
        return clean_signature(self.cleaned_data["mitarbeiter"])

    def clean(self):
        data = super().clean()
        if data.get("tenant_mode") == "signed":
            try:
                data["mieter"] = clean_signature(data.get("mieter"))
            except forms.ValidationError as error:
                self.add_error("mieter", error)
            data["reason"] = ""
        elif data.get("tenant_mode") == "missing":
            if not data.get("reason", "").strip():
                self.add_error("reason", "Bitte begründen Sie die fehlende Mieterunterschrift.")
            data["mieter"] = None
        return data
