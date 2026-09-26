from uuid import UUID

from django import forms

from .models import (
    AbnahmeStatus,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollTyp,
    RaumMerkmal,
    Raumprotokoll,
    UebergabeStatus,
    Wohnung,
)

HANDOVER_TYPE_LABELS = {
    ProtokollTyp.MOVE_IN: "Einzug",
    ProtokollTyp.MOVE_OUT: "Auszug",
}

HANDOVER_STATUS_LABELS = {
    UebergabeStatus.RENOVATED: "Renoviert",
    UebergabeStatus.UNRENOVATED: "Unrenoviert",
}

ACCEPTANCE_STATUS_LABELS = {
    AbnahmeStatus.ACCEPTED: "Abgenommen",
    AbnahmeStatus.ACCEPTED_WITH_RESERVATION: "Mit Vorbehalt abgenommen",
    AbnahmeStatus.NOT_FULLY_ACCEPTED: "Nicht vollständig abgenommen",
}

METER_NUMBER_FIELDS = (
    ("zaehlernummer_wasser_kalt", "Kaltwasser"),
    ("zaehlernummer_wasser_warm", "Warmwasser"),
    ("zaehlernummer_heizung", "Heizung"),
    ("zaehlernummer_strom", "Strom"),
)


class HandoverProtocolForm(forms.ModelForm):
    class Meta:
        model = Protokoll
        fields = [
            "wohnung",
            "person",
            "protokoll_typ",
            "uebergabe_zeitpunkt",
            "vermieter_name",
            "mieter_zukuenftige_anschrift",
            "uebergabe_status",
            "abnahme_status",
            "zaehlerstand_wasser_kalt",
            "zaehlerstand_wasser_warm",
            "zaehlerstand_heizung",
            "heizungsablesungen",
            "zaehlerstand_strom",
            "kaution_nachweis_vorhanden",
            "erste_miete_nachweis_vorhanden",
            "nachbesserung_bis",
            "nachbesserung_beschreibung",
        ]
        labels = {
            "wohnung": "Wohnung",
            "person": "Beteiligte Person",
            "protokoll_typ": "Übergabeart",
            "uebergabe_zeitpunkt": "Datum und Uhrzeit",
            "vermieter_name": "Anwesend für den Vermieter",
            "mieter_zukuenftige_anschrift": "Zukünftige Anschrift der beteiligten Person",
            "uebergabe_status": "Zustand bei Übergabe",
            "abnahme_status": "Abnahmestatus",
            "zaehlerstand_wasser_kalt": "Zählerstand Kaltwasser",
            "zaehlerstand_wasser_warm": "Zählerstand Warmwasser",
            "zaehlerstand_heizung": "Zählerstand Heizung",
            "heizungsablesungen": "Zusatzablesungen Heizung (IE, IA, Ib)",
            "zaehlerstand_strom": "Zählerstand Strom",
            "kaution_nachweis_vorhanden": "Überweisungsbeleg Kaution liegt vor",
            "erste_miete_nachweis_vorhanden": "Überweisungsbeleg erste Miete liegt vor",
            "nachbesserung_bis": "Nachbesserung bis",
            "nachbesserung_beschreibung": "Vereinbarte Nachbesserungen",
        }
        widgets = {
            "wohnung": forms.Select(attrs={"class": "uk-select"}),
            "person": forms.Select(attrs={"class": "uk-select"}),
            "protokoll_typ": forms.Select(attrs={"class": "uk-select"}),
            "uebergabe_zeitpunkt": forms.DateTimeInput(
                attrs={"class": "uk-input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "vermieter_name": forms.TextInput(attrs={"class": "uk-input"}),
            "mieter_zukuenftige_anschrift": forms.Textarea(
                attrs={"class": "uk-textarea", "rows": 3}
            ),
            "uebergabe_status": forms.Select(attrs={"class": "uk-select"}),
            "abnahme_status": forms.Select(attrs={"class": "uk-select"}),
            "zaehlerstand_wasser_kalt": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "zaehlerstand_wasser_warm": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "zaehlerstand_heizung": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "heizungsablesungen": forms.Textarea(attrs={"class": "uk-textarea", "rows": 2}),
            "zaehlerstand_strom": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "kaution_nachweis_vorhanden": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            "erste_miete_nachweis_vorhanden": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            "nachbesserung_bis": forms.DateInput(attrs={"class": "uk-input", "type": "date"}),
            "nachbesserung_beschreibung": forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
        }

    def __init__(self, *args, wohnung_id: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["wohnung"].queryset = Wohnung.objects.order_by(
            "gebaeudenummer", "wohnungsnummer"
        )
        selected_wohnung_id = _valid_wohnung_id(wohnung_id)
        if selected_wohnung_id is None and self.instance.pk:
            selected_wohnung_id = self.instance.wohnung_id
        self.selected_wohnung = None
        self.fields["person"].queryset = Person.objects.none()
        if selected_wohnung_id is not None:
            self.selected_wohnung = Wohnung.objects.filter(pk=selected_wohnung_id).first()
            self.fields["person"].queryset = Person.objects.filter(
                wohnung_id=selected_wohnung_id
            ).order_by("nachname", "vorname")
            if not self.is_bound:
                self.initial["wohnung"] = selected_wohnung_id
        self.fields["mieter_zukuenftige_anschrift"].required = False
        self.fields["protokoll_typ"].choices = HANDOVER_TYPE_LABELS.items()
        self.fields["uebergabe_status"].choices = HANDOVER_STATUS_LABELS.items()
        self.fields["abnahme_status"].choices = ACCEPTANCE_STATUS_LABELS.items()

    def clean(self) -> dict:
        cleaned_data = super().clean()
        handover_type = cleaned_data.get("protokoll_typ")
        apartment = cleaned_data.get("wohnung")
        if apartment is not None:
            for field_name, label in METER_NUMBER_FIELDS:
                if not getattr(apartment, field_name).strip():
                    self.add_error(
                        "wohnung",
                        f"Die Zählernummer für {label} fehlt in den Wohnungsstammdaten.",
                    )

        future_address = cleaned_data.get("mieter_zukuenftige_anschrift", "").strip()
        remediation_due_date = cleaned_data.get("nachbesserung_bis")
        remediation_description = cleaned_data.get("nachbesserung_beschreibung")
        if handover_type == ProtokollTyp.MOVE_OUT and not future_address:
            self.add_error(
                "mieter_zukuenftige_anschrift",
                "Bitte erfassen Sie die zukünftige Anschrift für den Auszug.",
            )
        if (
            handover_type == ProtokollTyp.MOVE_OUT
            and remediation_description
            and not remediation_due_date
        ):
            self.add_error(
                "nachbesserung_bis", "Bitte erfassen Sie die Frist für die Nachbesserung."
            )
        if (
            handover_type == ProtokollTyp.MOVE_OUT
            and remediation_due_date
            and not remediation_description
        ):
            self.add_error(
                "nachbesserung_beschreibung",
                "Bitte beschreiben Sie die vereinbarte Nachbesserung.",
            )
        if handover_type == ProtokollTyp.MOVE_IN:
            cleaned_data["mieter_zukuenftige_anschrift"] = ""
            cleaned_data["nachbesserung_bis"] = None
            cleaned_data["nachbesserung_beschreibung"] = ""
            cleaned_data["kaution_nachweis_vorhanden"] = cleaned_data.get(
                "kaution_nachweis_vorhanden", False
            )
            cleaned_data["erste_miete_nachweis_vorhanden"] = cleaned_data.get(
                "erste_miete_nachweis_vorhanden", False
            )
        elif handover_type == ProtokollTyp.MOVE_OUT:
            cleaned_data["kaution_nachweis_vorhanden"] = False
            cleaned_data["erste_miete_nachweis_vorhanden"] = False
        return cleaned_data

    @property
    def meter_numbers(self) -> tuple[tuple[str, str], ...]:
        if self.selected_wohnung is None:
            return ()
        return tuple(
            (label, getattr(self.selected_wohnung, field_name) or "Nicht gepflegt")
            for field_name, label in METER_NUMBER_FIELDS
        )

    @property
    def main_fields(self):
        return tuple(
            self[field_name]
            for field_name in (
                "wohnung",
                "person",
                "protokoll_typ",
                "uebergabe_zeitpunkt",
                "vermieter_name",
                "uebergabe_status",
                "abnahme_status",
            )
        )

    @property
    def meter_reading_fields(self):
        return tuple(
            self[field_name]
            for field_name in (
                "zaehlerstand_wasser_kalt",
                "zaehlerstand_wasser_warm",
                "zaehlerstand_heizung",
                "heizungsablesungen",
                "zaehlerstand_strom",
            )
        )

    @property
    def move_in_fields(self):
        return tuple(
            self[field_name]
            for field_name in ("kaution_nachweis_vorhanden", "erste_miete_nachweis_vorhanden")
        )

    @property
    def move_out_fields(self):
        return tuple(
            self[field_name] for field_name in ("nachbesserung_bis", "nachbesserung_beschreibung")
        )

    def save(self, commit: bool = True) -> Protokoll:
        protocol = super().save(commit=False)
        for field_name, _label in METER_NUMBER_FIELDS:
            setattr(protocol, field_name, getattr(protocol.wohnung, field_name))
        if protocol.protokoll_typ == ProtokollTyp.MOVE_IN:
            protocol.mieter_zukuenftige_anschrift = ""
            protocol.nachbesserung_bis = None
            protocol.nachbesserung_beschreibung = ""
        else:
            protocol.kaution_nachweis_vorhanden = False
            protocol.erste_miete_nachweis_vorhanden = False
        if commit:
            protocol.save()
        return protocol


def _valid_wohnung_id(wohnung_id: str | None) -> UUID | None:
    try:
        return UUID(str(wohnung_id))
    except (TypeError, ValueError):
        return None


class RoomProtocolForm(forms.ModelForm):
    class Meta:
        model = Raumprotokoll
        fields = ["name"]
        labels = {"name": "Raum / Bereich"}
        widgets = {"name": forms.TextInput(attrs={"class": "uk-input"})}


class RoomChecklistItemForm(forms.Form):
    bereich = forms.CharField(
        label="Bereich",
        widget=forms.TextInput(attrs={"class": "uk-input"}),
    )
    bezeichnung = forms.CharField(
        label="Prüfpunkt",
        widget=forms.TextInput(attrs={"class": "uk-input"}),
    )
    wert = forms.CharField(
        label="Feststellung",
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
    )

    def save(self, room: Raumprotokoll) -> RaumMerkmal:
        merkmal = Merkmal.objects.create(
            bereich=self.cleaned_data["bereich"],
            bezeichnung=self.cleaned_data["bezeichnung"],
            datentyp=MerkmalDatentyp.OK,
        )
        return RaumMerkmal.objects.create(
            raumprotokoll=room,
            merkmal=merkmal,
            wert={"text": self.cleaned_data["wert"]},
        )


class HandoverKeyForm(forms.ModelForm):
    class Meta:
        model = ProtokollSchluessel
        fields = [
            "anzahl",
            "raum_bezeichnung",
            "aufschrift",
            "schluesselnummer",
            "fehlt",
            "fehlgrund",
            "nachlieferung_am",
        ]
        labels = {
            "anzahl": "Stück",
            "raum_bezeichnung": "Raum / Bezeichnung",
            "aufschrift": "Schlüsselaufschrift",
            "schluesselnummer": "Schlüsselnummer",
            "fehlt": "Schlüssel fehlt",
            "fehlgrund": "Grund für das Fehlen / Vereinbarung",
            "nachlieferung_am": "Nachlieferung am",
        }
        widgets = {
            "anzahl": forms.NumberInput(attrs={"class": "uk-input", "min": "1", "step": "1"}),
            "raum_bezeichnung": forms.TextInput(attrs={"class": "uk-input"}),
            "aufschrift": forms.TextInput(attrs={"class": "uk-input"}),
            "schluesselnummer": forms.TextInput(attrs={"class": "uk-input"}),
            "fehlt": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            "fehlgrund": forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
            "nachlieferung_am": forms.DateInput(attrs={"class": "uk-input", "type": "date"}),
        }

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if cleaned_data.get("anzahl") is not None and cleaned_data["anzahl"] < 1:
            self.add_error("anzahl", "Bitte erfassen Sie mindestens einen Schlüssel.")
        if cleaned_data.get("fehlt") and not cleaned_data.get("fehlgrund"):
            self.add_error("fehlgrund", "Bitte begründen Sie den fehlenden Schlüssel.")
        return cleaned_data


class ProtocolConfirmationForm(forms.Form):
    schluessel_ueberprueft = forms.BooleanField(
        label="Die Schlüsselübergabe wurde einschließlich fehlender Schlüssel geprüft.",
        error_messages={"required": "Bitte bestätigen Sie die Prüfung der Schlüsselübergabe."},
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )
    bestaetigung_erklaert = forms.BooleanField(
        label="Die Angaben entsprechen nach bestem Wissen dem tatsächlichen Zustand der Mieträume.",
        error_messages={"required": "Bitte bestätigen Sie die Richtigkeit der Angaben."},
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )


class InlineRoomChecklistForm(forms.Form):
    raum = forms.CharField(
        label="Raum / Bereich",
        required=False,
        widget=forms.TextInput(attrs={"class": "uk-input"}),
    )
    bezeichnung = forms.CharField(
        label="Prüfpunkt",
        required=False,
        widget=forms.TextInput(attrs={"class": "uk-input"}),
    )
    wert = forms.CharField(
        label="Feststellung",
        required=False,
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 2}),
    )

    def clean(self) -> dict:
        cleaned_data = super().clean()
        field_names = ("raum", "bezeichnung", "wert")
        values = {
            field_name: cleaned_data.get(field_name, "").strip() for field_name in field_names
        }
        if not any(values.values()):
            return cleaned_data
        for field_name, value in values.items():
            if not value:
                self.add_error(field_name, "Bitte vervollständigen Sie diese Raumprüfung.")
        return cleaned_data

    def has_entry(self) -> bool:
        return bool(self.cleaned_data.get("raum", "").strip())

    def save(self, protocol: Protokoll) -> RaumMerkmal:
        room, _created = Raumprotokoll.objects.get_or_create(
            protokoll=protocol,
            name=self.cleaned_data["raum"],
        )
        merkmal = Merkmal.objects.create(
            bereich=room.name,
            bezeichnung=self.cleaned_data["bezeichnung"],
            datentyp=MerkmalDatentyp.OK,
        )
        return RaumMerkmal.objects.create(
            raumprotokoll=room,
            merkmal=merkmal,
            wert={"text": self.cleaned_data["wert"]},
        )


InlineRoomChecklistFormSet = forms.formset_factory(
    InlineRoomChecklistForm,
    extra=1,
    can_delete=True,
)
HandoverKeyFormSet = forms.formset_factory(HandoverKeyForm, extra=1, can_delete=True)
