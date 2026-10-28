import re

from django import forms

# Shared by server validation and the browser's native input validation.
PHONE_PATTERN = r"(?=(?:[^0-9]*[0-9]){6,15}[^0-9]*$)\+?[0-9 \(\)\/\.\-]+"


class CallbackForm(forms.Form):
    phone = forms.CharField(
        label="Telefonnummer",
        max_length=40,
        help_text="Unter welcher Nummer dürfen wir Sie zurückrufen?",
        widget=forms.TextInput(
            attrs={
                "class": "uk-input",
                "type": "tel",
                "autocomplete": "tel",
                "pattern": PHONE_PATTERN,
                "title": "Telefonnummer mit 6 bis 15 Ziffern, zum Beispiel +49 931 5550123",
            }
        ),
    )
    availability = forms.CharField(
        label="Erreichbarkeit",
        max_length=500,
        help_text="Geben Sie passende Tage und Uhrzeiten an, zum Beispiel werktags ab 17 Uhr.",
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 4}),
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if not re.fullmatch(PHONE_PATTERN, phone):
            raise forms.ValidationError(
                "Bitte geben Sie eine gültige Telefonnummer mit 6 bis 15 Ziffern an."
            )
        return phone

    def clean_website(self):
        if self.cleaned_data["website"]:
            raise forms.ValidationError("Die Anfrage konnte nicht verarbeitet werden.")
        return ""
