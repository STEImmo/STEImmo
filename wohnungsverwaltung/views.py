from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    SchluesselFormSet,
    StellplatzForm,
    StellplatzZuordnungForm,
    WohnungForm,
)
from .models import Stellplatz, StellplatzZuordnung, Wohnung


@staff_member_required
def wohnung_list(request: HttpRequest) -> HttpResponse:
    wohnungen = Wohnung.objects.order_by("etage", "wohnungsnummer")
    return render(request, "wohnungsverwaltung/wohnung_list.html", {"wohnungen": wohnungen})


@staff_member_required
def wohnung_create(request: HttpRequest) -> HttpResponse:
    return _wohnung_form(request, Wohnung(), "Wohnung anlegen")


@staff_member_required
def wohnung_edit(request: HttpRequest, wohnung_id) -> HttpResponse:
    wohnung = get_object_or_404(Wohnung, pk=wohnung_id)
    return _wohnung_form(request, wohnung, "Wohnung bearbeiten")


def _wohnung_form(request: HttpRequest, wohnung: Wohnung, title: str) -> HttpResponse:
    if request.method == "POST":
        form = WohnungForm(request.POST, instance=wohnung)
        schluessel_formset = SchluesselFormSet(
            request.POST,
            instance=wohnung,
            prefix="schluessel",
        )
        if form.is_valid() and schluessel_formset.is_valid():
            with transaction.atomic():
                wohnung = form.save()
                schluessel_formset.instance = wohnung
                schluessel_formset.save()
            messages.success(request, "Die Wohnungsstammdaten wurden gespeichert.")
            return redirect("wohnungsverwaltung:wohnung_edit", wohnung_id=wohnung.pk)
    else:
        form = WohnungForm(instance=wohnung)
        schluessel_formset = SchluesselFormSet(instance=wohnung, prefix="schluessel")

    return render(
        request,
        "wohnungsverwaltung/wohnung_form.html",
        {
            "form": form,
            "schluessel_formset": schluessel_formset,
            "title": title,
            "wohnung": wohnung,
        },
    )


@staff_member_required
def stellplatz_list(request: HttpRequest) -> HttpResponse:
    stellplaetze = Stellplatz.objects.order_by("name").prefetch_related("zuordnungen__wohnung")
    return render(
        request,
        "wohnungsverwaltung/stellplatz_list.html",
        {"stellplaetze": stellplaetze},
    )


@staff_member_required
def stellplatz_create(request: HttpRequest) -> HttpResponse:
    return _stellplatz_form(request, Stellplatz(), "Stellplatz anlegen")


@staff_member_required
def stellplatz_edit(request: HttpRequest, stellplatz_id) -> HttpResponse:
    stellplatz = get_object_or_404(Stellplatz, pk=stellplatz_id)
    return _stellplatz_form(request, stellplatz, "Stellplatz bearbeiten")


def _stellplatz_form(request: HttpRequest, stellplatz: Stellplatz, title: str) -> HttpResponse:
    zuordnung = (
        StellplatzZuordnung.objects.filter(stellplatz=stellplatz).first()
        if not stellplatz._state.adding
        else None
    ) or StellplatzZuordnung(stellplatz=stellplatz)
    if request.method == "POST":
        form = StellplatzForm(request.POST, instance=stellplatz)
        zuordnung_form = StellplatzZuordnungForm(request.POST, instance=zuordnung)
        if form.is_valid() and zuordnung_form.is_valid():
            with transaction.atomic():
                stellplatz = form.save()
                if zuordnung_form.cleaned_data["wohnung"] is None:
                    if not zuordnung._state.adding:
                        zuordnung.delete()
                else:
                    zuordnung = zuordnung_form.save(commit=False)
                    zuordnung.stellplatz = stellplatz
                    zuordnung.save()
            messages.success(request, "Der Stellplatz und seine Zuordnung wurden gespeichert.")
            return redirect("wohnungsverwaltung:stellplatz_edit", stellplatz_id=stellplatz.pk)
    else:
        form = StellplatzForm(instance=stellplatz)
        zuordnung_form = StellplatzZuordnungForm(instance=zuordnung)

    return render(
        request,
        "wohnungsverwaltung/stellplatz_form.html",
        {
            "form": form,
            "stellplatz": stellplatz,
            "title": title,
            "zuordnung_form": zuordnung_form,
        },
    )
