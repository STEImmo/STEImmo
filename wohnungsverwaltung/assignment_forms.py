from django import forms

from .models import Person, ProtokollStatus


class PersonSelectionForm(forms.Form):
    person = forms.ModelChoiceField(
        label="Vorhandene Person",
        queryset=Person.objects.none(),
        widget=forms.Select(attrs={"class": "uk-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = Person.objects.select_related("wohnung").order_by(
            "nachname", "vorname", "email"
        )
        self.fields["person"].label_from_instance = lambda person: (
            f"{person} ({person.email}) – {person.wohnung or 'ohne Wohnung'}"
        )


class PersonAssignmentForm(forms.Form):
    previous_wohnung = forms.CharField(required=False, widget=forms.HiddenInput)
    confirmed = forms.BooleanField(
        label="Die fachliche Einzugsentscheidung ist getroffen. "
        "Ich bestätige die angezeigte Wohnungszuordnung.",
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )

    def __init__(self, *args, person, wohnung, **kwargs):
        super().__init__(*args, **kwargs)
        self.person = person
        self.wohnung = wohnung
        self.initial["previous_wohnung"] = str(person.wohnung_id or "")

    def clean(self):
        data = super().clean()
        if data.get("previous_wohnung", "") != str(self.person.wohnung_id or ""):
            raise forms.ValidationError(
                "Die Zuordnung wurde zwischenzeitlich geändert. Bitte laden Sie die Seite neu."
            )
        if (
            self.person.wohnung_id != self.wohnung.pk
            and self.person.protokolle.exclude(status=ProtokollStatus.SIGNED).exists()
        ):
            raise forms.ValidationError(
                "Die Person hat noch offene oder gesperrte Protokolle. "
                "Bitte klären und schließen Sie diese vor einem Wohnungswechsel ab."
            )
        return data
