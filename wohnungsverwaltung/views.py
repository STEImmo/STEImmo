from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ACCEPTANCE_STATUS_LABELS,
    HANDOVER_STATUS_LABELS,
    HANDOVER_TYPE_LABELS,
    HandoverProtocolForm,
)
from .models import Protokoll, ProtokollStatus

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
        Protokoll.objects.select_related("wohnung", "person"),
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
        },
    )


def handover_protocol_edit(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
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
