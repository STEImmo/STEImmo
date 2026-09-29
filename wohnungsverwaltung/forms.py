from django import forms
from django.forms import inlineformset_factory

from .models import Schluessel, Stellplatz, StellplatzZuordnung, Wohnung


class UIkitFormMixin:
    """Apply the project-wide UIkit classes to Django form widgets."""

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
