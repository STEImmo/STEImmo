from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    ACCEPTANCE_STATUS_LABELS,
    HANDOVER_STATUS_LABELS,
    HANDOVER_TYPE_LABELS,
    HandoverKeyForm,
    HandoverProtocolForm,
    ProtocolConfirmationForm,
    RoomChecklistItemForm,
    RoomProtocolForm,
)
from .models import Protokoll, ProtokollStatus, Raumprotokoll

PROTOCOL_STATUS_LABELS = {
    ProtokollStatus.OPEN: "In Bearbeitung",
    ProtokollStatus.SIGNED: "Bestätigt",
    ProtokollStatus.BLOCKED: "Gesperrt",
}


def handover_protocol_list(request: HttpRequest) -> HttpResponse:
    protocols = Protokoll.objects.select_related("wohnung", "person").order_by("-updated_at")
    return render(
        request, "wohnungsverwaltung/handover_protocol_list.html", {"protocols": protocols}
    )


def handover_protocol_create(request: HttpRequest) -> HttpResponse:
    form = HandoverProtocolForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        protocol = form.save()
        messages.success(request, "Das Übergabeprotokoll wurde angelegt.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    return render(
        request,
        "wohnungsverwaltung/handover_protocol_form.html",
        {
            "form": form,
            "page_title": "Übergabeprotokoll anlegen",
            "submit_label": "Protokoll anlegen",
        },
    )


def handover_protocol_detail(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(
        Protokoll.objects.select_related("wohnung", "person").prefetch_related(
            "protokoll_schluessel", "raeume__raum_merkmale__merkmal"
        ),
        pk=protocol_id,
    )
    return render(
        request,
        "wohnungsverwaltung/handover_protocol_detail.html",
        {
            "protocol": protocol,
            "protocol_type_label": HANDOVER_TYPE_LABELS[protocol.protokoll_typ],
            "handover_status_label": HANDOVER_STATUS_LABELS[protocol.uebergabe_status],
            "acceptance_status_label": ACCEPTANCE_STATUS_LABELS[protocol.abnahme_status],
            "protocol_status_label": PROTOCOL_STATUS_LABELS[protocol.status],
            "confirmation_form": ProtocolConfirmationForm(),
        },
    )


def handover_protocol_edit(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    form = HandoverProtocolForm(request.POST or None, instance=protocol)
    if request.method == "POST" and form.is_valid():
        protocol = form.save()
        messages.success(request, "Das Übergabeprotokoll wurde aktualisiert.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    return render(
        request,
        "wohnungsverwaltung/handover_protocol_form.html",
        {
            "form": form,
            "page_title": "Übergabeprotokoll bearbeiten",
            "submit_label": "Änderungen speichern",
            "protocol": protocol,
        },
    )


def handover_protocol_room_create(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    form = RoomProtocolForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        room = form.save(commit=False)
        room.protokoll = protocol
        room.save()
        messages.success(request, "Der Raum wurde für das Übergabeprotokoll angelegt.")
        return redirect(
            "wohnungsverwaltung:handover_protocol_room_detail",
            protocol_id=protocol.pk,
            room_id=room.pk,
        )

    return render(
        request,
        "wohnungsverwaltung/handover_protocol_room_form.html",
        {"form": form, "protocol": protocol},
    )


def handover_protocol_room_detail(request: HttpRequest, protocol_id, room_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    room = get_object_or_404(
        Raumprotokoll.objects.prefetch_related("raum_merkmale__merkmal"),
        pk=room_id,
        protokoll=protocol,
    )
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    form = RoomChecklistItemForm(request.POST or None, initial={"bereich": room.name})
    if request.method == "POST" and form.is_valid():
        form.save(room)
        messages.success(request, "Der Prüfpunkt wurde erfasst.")
        return redirect(
            "wohnungsverwaltung:handover_protocol_room_detail",
            protocol_id=protocol.pk,
            room_id=room.pk,
        )

    return render(
        request,
        "wohnungsverwaltung/handover_protocol_room_detail.html",
        {"form": form, "protocol": protocol, "room": room},
    )


def handover_protocol_key_create(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    form = HandoverKeyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        key = form.save(commit=False)
        key.protokoll = protocol
        key.save()
        messages.success(request, "Der Schlüssel wurde im Übergabeprotokoll erfasst.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    return render(
        request,
        "wohnungsverwaltung/handover_protocol_key_form.html",
        {"form": form, "protocol": protocol},
    )


def handover_protocol_confirm(request: HttpRequest, protocol_id) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(
        Protokoll.objects.prefetch_related("raeume__raum_merkmale"),
        pk=protocol_id,
    )
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Das Protokoll wurde bereits bestätigt.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    form = ProtocolConfirmationForm(request.POST)
    completion_errors = _protocol_completion_errors(protocol)
    if not form.is_valid() or completion_errors:
        for error in completion_errors:
            messages.error(request, error)
        if not form.is_valid():
            messages.error(request, "Bitte bestätigen Sie die beiden Erklärungen vor Abschluss.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    protocol.status = ProtokollStatus.SIGNED
    protocol.bestaetigt_am = timezone.now()
    protocol.schluessel_ueberprueft = form.cleaned_data["schluessel_ueberprueft"]
    protocol.bestaetigung_erklaert = form.cleaned_data["bestaetigung_erklaert"]
    protocol.save(
        update_fields=[
            "status",
            "bestaetigt_am",
            "schluessel_ueberprueft",
            "bestaetigung_erklaert",
            "updated_at",
        ]
    )
    messages.success(
        request, "Das Übergabeprotokoll wurde bestätigt und gegen Änderungen gesperrt."
    )
    return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)


def _protocol_completion_errors(protocol: Protokoll) -> list[str]:
    errors = []
    required_text_fields = {
        "vermieter_name": "die Vertretung des Vermieters",
        "mieter_zukuenftige_anschrift": "die zukünftige Anschrift",
        "zaehlernummer_wasser_kalt": "die Zählernummer für Kaltwasser",
        "zaehlernummer_wasser_warm": "die Zählernummer für Warmwasser",
        "zaehlernummer_heizung": "die Zählernummer für Heizung",
        "heizungsablesungen": "die Zusatzablesungen der Heizung",
        "zaehlernummer_strom": "die Zählernummer für Strom",
    }
    for field_name, label in required_text_fields.items():
        if not getattr(protocol, field_name).strip():
            errors.append(f"Für die Bestätigung fehlt {label}.")

    rooms = list(protocol.raeume.all())
    if not rooms:
        errors.append("Für die Bestätigung muss mindestens ein Raum mit Prüfpunkten erfasst sein.")

    for room in rooms:
        checklist_items = list(room.raum_merkmale.all())
        if not checklist_items:
            errors.append(f"Für den Raum „{room.name}“ fehlt mindestens ein Prüfpunkt.")
            continue
        for checklist_item in checklist_items:
            value = checklist_item.wert if isinstance(checklist_item.wert, dict) else {}
            if not str(value.get("text", "")).strip():
                errors.append(f"Für den Prüfpunkt in „{room.name}“ fehlt eine Feststellung.")
    return errors
