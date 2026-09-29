from uuid import UUID

from django import forms
from django.forms.formsets import BaseFormSet
from django.forms.models import inlineformset_factory

from .models import (
    AbnahmeStatus,
    Merkmal,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollTyp,
    RaumMerkmal,
    Raumprotokoll,
    Schluessel,
    Stellplatz,
    StellplatzZuordnung,
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
    vermieter_name = forms.ChoiceField(
        label="Anwesend für den Vermieter",
        choices=(),
        widget=forms.Select(attrs={"class": "uk-select"}),
    )

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
        self.fields["vermieter_name"].choices = [
            ("", "Bitte auswählen"),
            *[
                (str(employee), str(employee))
                for employee in Person.objects.filter(is_employee=True).order_by(
                    "nachname", "vorname"
                )
            ],
        ]
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


def _feature_area_choices() -> list[tuple[str, str]]:
    areas = Merkmal.objects.order_by("bereich").values_list("bereich", flat=True).distinct()
    return [("", "Bereich wählen"), *((area, area) for area in areas)]


class FeatureSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        feature = getattr(value, "instance", None)
        if feature is not None:
            option["attrs"]["data-feature-area"] = feature.bereich
        return option


class FeatureChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Merkmal) -> str:
        return obj.bezeichnung


class RoomChecklistItemForm(forms.Form):
    bereich = forms.ChoiceField(
        choices=(),
        label="Bereich",
        widget=forms.Select(attrs={"class": "uk-select", "data-feature-area-select": ""}),
    )
    merkmal = FeatureChoiceField(
        queryset=Merkmal.objects.none(),
        label="Bezeichnung",
        widget=FeatureSelect(attrs={"class": "uk-select", "data-feature-name-select": ""}),
    )
    wert = forms.CharField(
        label="Feststellung",
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["bereich"].choices = _feature_area_choices()
        self.fields["merkmal"].queryset = Merkmal.objects.order_by("bereich", "bezeichnung")

    def clean(self) -> dict:
        cleaned_data = super().clean()
        feature = cleaned_data.get("merkmal")
        if feature is not None and feature.bereich != cleaned_data.get("bereich"):
            self.add_error("merkmal", "Die Bezeichnung gehört nicht zum gewählten Bereich.")
        return cleaned_data

    def save(self, room: Raumprotokoll) -> RaumMerkmal:
        return RaumMerkmal.objects.create(
            raumprotokoll=room,
            merkmal=self.cleaned_data["merkmal"],
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
        label="Raum",
        required=False,
        widget=forms.TextInput(attrs={"class": "uk-input", "data-room-name-source": ""}),
    )
    bereich = forms.ChoiceField(
        choices=(),
        label="Bereich",
        required=False,
        widget=forms.Select(attrs={"class": "uk-select", "data-feature-area-select": ""}),
    )
    merkmal = FeatureChoiceField(
        queryset=Merkmal.objects.none(),
        label="Bezeichnung",
        required=False,
        widget=FeatureSelect(attrs={"class": "uk-select", "data-feature-name-select": ""}),
    )
    wert = forms.CharField(
        label="Feststellung",
        required=False,
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 5}),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["bereich"].choices = _feature_area_choices()
        self.fields["merkmal"].queryset = Merkmal.objects.order_by("bereich", "bezeichnung")

    def clean(self) -> dict:
        cleaned_data = super().clean()
        values = {
            "raum": cleaned_data.get("raum", "").strip(),
            "bereich": cleaned_data.get("bereich", "").strip(),
            "merkmal": cleaned_data.get("merkmal"),
            "wert": cleaned_data.get("wert", "").strip(),
        }
        if not any((values["bereich"], values["merkmal"], values["wert"])):
            return cleaned_data
        for field_name in ("bereich", "merkmal", "wert"):
            value = values[field_name]
            if not value:
                self.add_error(field_name, "Bitte vervollständigen Sie diese Raumprüfung.")
        feature = cleaned_data.get("merkmal")
        if feature is not None and feature.bereich != cleaned_data.get("bereich"):
            self.add_error("merkmal", "Die Bezeichnung gehört nicht zum gewählten Bereich.")
        return cleaned_data

    def has_entry(self) -> bool:
        return self.cleaned_data.get("merkmal") is not None

    def save(self, protocol: Protokoll) -> RaumMerkmal:
        room, _created = Raumprotokoll.objects.get_or_create(
            protokoll=protocol,
            name=self.cleaned_data["raum"],
        )
        return RaumMerkmal.objects.create(
            raumprotokoll=room,
            merkmal=self.cleaned_data["merkmal"],
            wert={"text": self.cleaned_data["wert"]},
        )


class RoomChecklistFormSet(BaseFormSet):
    def clean(self) -> None:
        super().clean()
        current_room = ""
        for room_form in self.forms:
            if (
                not getattr(room_form, "cleaned_data", None)
                or room_form.cleaned_data.get("DELETE")
                or not room_form.has_entry()
            ):
                continue
            room_name = room_form.cleaned_data.get("raum", "").strip()
            if room_name:
                current_room = room_name
                continue
            if current_room:
                room_form.cleaned_data["raum"] = current_room
                continue
            room_form.add_error("raum", "Bitte geben Sie für den ersten Prüfpunkt einen Raum an.")


InlineRoomChecklistFormSet = forms.formset_factory(
    InlineRoomChecklistForm,
    extra=1,
    can_delete=True,
    formset=RoomChecklistFormSet,
)
HandoverKeyFormSet = forms.formset_factory(HandoverKeyForm, extra=1, can_delete=True)


class UIkitFormMixin:
    """Apply the project-wide UIkit classes to management form widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "uk-checkbox")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "uk-select")
            else:
                widget.attrs.setdefault("class", "uk-input")


class WohnungForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Wohnung
        fields = [
            "gebaeudenummer",
            "wohnungsnummer",
            "etage",
            "groesse_qm",
            "zimmeranzahl",
            "kaltmiete",
            "warmmiete",
            "kaution",
            "barrierefrei",
            "zaehlernummer_wasser_kalt",
            "zaehlernummer_wasser_warm",
            "zaehlernummer_heizung",
            "zaehlernummer_strom",
        ]
        labels = {
            "gebaeudenummer": "Gebäudenummer",
            "wohnungsnummer": "Wohnungsnummer",
            "etage": "Etage",
            "groesse_qm": "Größe (m²)",
            "zimmeranzahl": "Zimmeranzahl",
            "kaltmiete": "Kaltmiete (€)",
            "warmmiete": "Warmmiete (€)",
            "kaution": "Kaution (€)",
            "barrierefrei": "Barrierefrei",
            "zaehlernummer_wasser_kalt": "Zählernummer Kaltwasser",
            "zaehlernummer_wasser_warm": "Zählernummer Warmwasser",
            "zaehlernummer_heizung": "Zählernummer Heizung",
            "zaehlernummer_strom": "Zählernummer Strom",
        }


class SchluesselForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Schluessel
        fields = ["bezeichnung", "anzahl", "aufschrift", "status"]
        labels = {
            "bezeichnung": "Bezeichnung",
            "anzahl": "Sollbestand",
            "aufschrift": "Aufschrift",
            "status": "Status",
        }


class StellplatzForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Stellplatz
        fields = ["name", "stellplatz_typ", "miete"]
        labels = {"name": "Name", "stellplatz_typ": "Typ", "miete": "Miete (€)"}


class StellplatzZuordnungForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = StellplatzZuordnung
        fields = ["wohnung"]
        labels = {"wohnung": "Wohnung"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wohnung"].queryset = Wohnung.objects.order_by("etage", "wohnungsnummer")
        self.fields["wohnung"].empty_label = "Nicht zugeordnet"
        self.fields["wohnung"].required = False


SchluesselFormSet = inlineformset_factory(
    Wohnung,
    Schluessel,
    form=SchluesselForm,
    extra=1,
    can_delete=True,
)
