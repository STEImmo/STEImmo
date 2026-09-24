from django import forms

from .models import (
    AbnahmeStatus,
    Person,
    Protokoll,
    ProtokollTyp,
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


class HandoverProtocolForm(forms.ModelForm):
    class Meta:
        model = Protokoll
        fields = [
            "wohnung",
            "person",
            "protokoll_typ",
            "uebergabe_status",
            "abnahme_status",
            "zaehlerstand_wasser_kalt",
            "zaehlerstand_wasser_warm",
            "zaehlerstand_heizung",
            "zaehlerstand_strom",
        ]
        labels = {
            "wohnung": "Wohnung",
            "person": "Beteiligte Person",
            "protokoll_typ": "Übergabeart",
            "uebergabe_status": "Zustand bei Übergabe",
            "abnahme_status": "Abnahmestatus",
            "zaehlerstand_wasser_kalt": "Zählerstand Kaltwasser",
            "zaehlerstand_wasser_warm": "Zählerstand Warmwasser",
            "zaehlerstand_heizung": "Zählerstand Heizung",
            "zaehlerstand_strom": "Zählerstand Strom",
        }
        widgets = {
            "wohnung": forms.Select(attrs={"class": "uk-select"}),
            "person": forms.Select(attrs={"class": "uk-select"}),
            "protokoll_typ": forms.Select(attrs={"class": "uk-select"}),
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
            "zaehlerstand_strom": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["wohnung"].queryset = Wohnung.objects.order_by(
            "gebaeudenummer", "wohnungsnummer"
        )
        self.fields["person"].queryset = Person.objects.order_by("nachname", "vorname")
        self.fields["protokoll_typ"].choices = HANDOVER_TYPE_LABELS.items()
        self.fields["uebergabe_status"].choices = HANDOVER_STATUS_LABELS.items()
        self.fields["abnahme_status"].choices = ACCEPTANCE_STATUS_LABELS.items()
