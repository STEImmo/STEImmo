import json
from uuid import UUID

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    ACCEPTANCE_STATUS_LABELS,
    HANDOVER_STATUS_LABELS,
    HANDOVER_TYPE_LABELS,
    HandoverKeyForm,
    HandoverKeyFormSet,
    HandoverProtocolForm,
    InlineRoomChecklistFormSet,
    ProtocolConfirmationForm,
    RoomChecklistItemForm,
    RoomProtocolForm,
)
from .models import (
    Protokoll,
    ProtokollEntwurf,
    ProtokollSchluessel,
    ProtokollStatus,
    ProtokollTyp,
    RaumMerkmal,
    Raumprotokoll,
    Wohnung,
)

PROTOCOL_STATUS_LABELS = {
    ProtokollStatus.OPEN: "In Bearbeitung",
    ProtokollStatus.SIGNED: "Bestätigt",
    ProtokollStatus.BLOCKED: "Gesperrt",
}

DRAFT_MAXIMUM_SIZE = 512_000


def _draft_session_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _protocol_id_from_draft_scope(draft_scope: str) -> UUID | None:
    if not draft_scope.startswith("edit:"):
        return None
    try:
        return UUID(draft_scope.removeprefix("edit:"))
    except ValueError:
        return None


def _is_valid_draft_scope(draft_scope: str) -> bool:
    if draft_scope == "create":
        return True
    protocol_id = _protocol_id_from_draft_scope(draft_scope)
    return (
        protocol_id is not None
        and Protokoll.objects.filter(pk=protocol_id, status=ProtokollStatus.OPEN).exists()
    )


def _draft_for_form(request: HttpRequest, draft_scope: str) -> ProtokollEntwurf | None:
    drafts = ProtokollEntwurf.objects.filter(
        sitzungsschluessel=_draft_session_key(request),
        entwurfsbereich=draft_scope,
    )
    requested_draft_id = request.GET.get("draft")
    if requested_draft_id:
        try:
            return drafts.filter(pk=UUID(requested_draft_id)).first()
        except ValueError:
            return None
    return drafts.order_by("-updated_at").first()


def _draft_form_context(draft: ProtokollEntwurf | None) -> dict[str, object]:
    if draft is None:
        return {"server_draft": None, "server_draft_delete_url": ""}
    return {
        "server_draft": draft.daten,
        "server_draft_delete_url": reverse(
            "wohnungsverwaltung:handover_protocol_draft_delete",
            kwargs={"draft_id": draft.pk},
        ),
    }


def _delete_draft(request: HttpRequest, draft_scope: str) -> None:
    ProtokollEntwurf.objects.filter(
        sitzungsschluessel=_draft_session_key(request),
        entwurfsbereich=draft_scope,
    ).delete()


def _draft_field_value(draft: ProtokollEntwurf, field_name: str) -> str:
    fields = draft.daten.get("fields", {}) if isinstance(draft.daten, dict) else {}
    field = fields.get(field_name, {}) if isinstance(fields, dict) else {}
    value = field.get("value", "") if isinstance(field, dict) else ""
    return str(value)


def _draft_overview_entries(request: HttpRequest) -> list[dict[str, object]]:
    drafts = list(
        ProtokollEntwurf.objects.filter(sitzungsschluessel=_draft_session_key(request)).order_by(
            "-updated_at"
        )
    )
    apartment_ids = []
    for draft in drafts:
        try:
            apartment_ids.append(UUID(_draft_field_value(draft, "wohnung")))
        except ValueError:
            continue
    apartments = {
        str(pk): apartment for pk, apartment in Wohnung.objects.in_bulk(apartment_ids).items()
    }
    entries: list[dict[str, object]] = []
    for draft in drafts:
        draft_scope = draft.entwurfsbereich
        if draft_scope == "create":
            continue_url = (
                f"{reverse('wohnungsverwaltung:handover_protocol_create')}?draft={draft.pk}"
            )
        else:
            protocol_id = _protocol_id_from_draft_scope(draft_scope)
            if protocol_id is None:
                continue
            edit_url = reverse(
                "wohnungsverwaltung:handover_protocol_edit",
                kwargs={"protocol_id": protocol_id},
            )
            continue_url = f"{edit_url}?draft={draft.pk}"
        handover_type = _draft_field_value(draft, "protokoll_typ")
        entries.append(
            {
                "draft": draft,
                "wohnung": apartments.get(_draft_field_value(draft, "wohnung")),
                "protokoll_typ": HANDOVER_TYPE_LABELS.get(handover_type, "Noch nicht ausgewählt"),
                "continue_url": continue_url,
            }
        )
    return entries


def handover_protocol_draft_save(request: HttpRequest) -> JsonResponse | HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if len(request.body) > DRAFT_MAXIMUM_SIZE:
        return JsonResponse({"error": "Der Entwurf ist zu groß."}, status=400)
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungültige Entwurfsdaten."}, status=400)

    draft_scope = payload.get("scope") if isinstance(payload, dict) else None
    draft_data = payload.get("draft") if isinstance(payload, dict) else None
    if (
        not isinstance(draft_scope, str)
        or not isinstance(draft_data, dict)
        or draft_data.get("version") != 1
        or not isinstance(draft_data.get("fields"), dict)
        or not isinstance(draft_data.get("rooms"), list)
        or not isinstance(draft_data.get("keys"), list)
        or not _is_valid_draft_scope(draft_scope)
    ):
        return JsonResponse({"error": "Ungültige Entwurfsdaten."}, status=400)

    draft, _created = ProtokollEntwurf.objects.update_or_create(
        sitzungsschluessel=_draft_session_key(request),
        entwurfsbereich=draft_scope,
        defaults={"daten": draft_data},
    )
    return JsonResponse(
        {
            "delete_url": reverse(
                "wohnungsverwaltung:handover_protocol_draft_delete",
                kwargs={"draft_id": draft.pk},
            )
        }
    )


def handover_protocol_draft_delete(request: HttpRequest, draft_id) -> JsonResponse | HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    draft = get_object_or_404(
        ProtokollEntwurf,
        pk=draft_id,
        sitzungsschluessel=_draft_session_key(request),
    )
    draft.delete()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"deleted": True})
    messages.success(request, "Der Entwurf wurde gelöscht.")
    return redirect("wohnungsverwaltung:handover_protocol_list")


def handover_protocol_list(request: HttpRequest) -> HttpResponse:
    protocols = Protokoll.objects.select_related("wohnung", "person").order_by("-updated_at")
    return render(
        request,
        "wohnungsverwaltung/handover_protocol_list.html",
        {"protocols": protocols, "draft_entries": _draft_overview_entries(request)},
    )


def handover_protocol_create(request: HttpRequest) -> HttpResponse:
    draft_scope = "create"
    server_draft = _draft_for_form(request, draft_scope)
    selected_wohnung_id = (
        request.POST.get("wohnung")
        or request.GET.get("wohnung")
        or (_draft_field_value(server_draft, "wohnung") if server_draft else None)
    )
    form = HandoverProtocolForm(request.POST or None, wohnung_id=selected_wohnung_id)
    room_formset = InlineRoomChecklistFormSet(request.POST or None, prefix="rooms")
    key_formset = HandoverKeyFormSet(
        request.POST or None,
        prefix="keys",
        initial=_key_form_initial(form.selected_wohnung) if request.method != "POST" else None,
    )
    if (
        request.method == "POST"
        and form.is_valid()
        and room_formset.is_valid()
        and key_formset.is_valid()
    ):
        with transaction.atomic():
            protocol = form.save()
            _save_inline_protocol_entries(protocol, room_formset, key_formset)
        _delete_draft(request, draft_scope)
        request.session["handover_protocol_draft_key_to_clear"] = "handover-protocol-draft:create"
        messages.success(request, "Das Übergabeprotokoll wurde angelegt.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    return render(
        request,
        "wohnungsverwaltung/handover_protocol_form.html",
        {
            "form": form,
            "page_title": "Übergabeprotokoll anlegen",
            "submit_label": "Protokoll anlegen",
            "room_formset": room_formset,
            "room_form_groups": _room_form_groups(room_formset),
            "key_formset": key_formset,
            "draft_scope": draft_scope,
            **_draft_form_context(server_draft),
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
            "draft_key_to_clear": request.session.pop("handover_protocol_draft_key_to_clear", ""),
        },
    )


def handover_protocol_edit(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    draft_scope = f"edit:{protocol.pk}"
    server_draft = _draft_for_form(request, draft_scope)
    selected_wohnung_id = request.POST.get("wohnung") or request.GET.get("wohnung")
    form = HandoverProtocolForm(
        request.POST or None,
        instance=protocol,
        wohnung_id=selected_wohnung_id or protocol.wohnung_id,
    )
    room_formset = InlineRoomChecklistFormSet(request.POST or None, prefix="rooms")
    key_formset = HandoverKeyFormSet(request.POST or None, prefix="keys")
    if (
        request.method == "POST"
        and form.is_valid()
        and room_formset.is_valid()
        and key_formset.is_valid()
    ):
        with transaction.atomic():
            protocol = form.save()
            _save_inline_protocol_entries(protocol, room_formset, key_formset)
        _delete_draft(request, draft_scope)
        request.session["handover_protocol_draft_key_to_clear"] = (
            f"handover-protocol-draft:edit:{protocol.pk}"
        )
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
            "room_formset": room_formset,
            "room_form_groups": _room_form_groups(room_formset),
            "key_formset": key_formset,
            "draft_scope": draft_scope,
            **_draft_form_context(server_draft),
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


def handover_protocol_room_delete(request: HttpRequest, protocol_id, room_id) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    room = get_object_or_404(Raumprotokoll, pk=room_id, protokoll=protocol)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    room.delete()
    messages.success(request, "Der Raum wurde aus dem Übergabeprotokoll entfernt.")
    return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)


def handover_protocol_checklist_item_delete(
    request: HttpRequest, protocol_id, room_id, item_id
) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    room = get_object_or_404(Raumprotokoll, pk=room_id, protokoll=protocol)
    checklist_item = get_object_or_404(RaumMerkmal, pk=item_id, raumprotokoll=room)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    checklist_item.delete()
    messages.success(request, "Der Prüfpunkt wurde aus dem Raum entfernt.")
    return redirect(
        "wohnungsverwaltung:handover_protocol_room_detail",
        protocol_id=protocol.pk,
        room_id=room.pk,
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


def handover_protocol_key_delete(request: HttpRequest, protocol_id, key_id) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    key = get_object_or_404(ProtokollSchluessel, pk=key_id, protokoll=protocol)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    key.delete()
    messages.success(request, "Die Schlüsselposition wurde aus dem Übergabeprotokoll entfernt.")
    return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)


def handover_protocol_confirm(request: HttpRequest, protocol_id) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(
        Protokoll.objects.prefetch_related("raeume__raum_merkmale", "protokoll_schluessel"),
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
        "zaehlernummer_wasser_kalt": "die Zählernummer für Kaltwasser",
        "zaehlernummer_wasser_warm": "die Zählernummer für Warmwasser",
        "zaehlernummer_heizung": "die Zählernummer für Heizung",
        "heizungsablesungen": "die Zusatzablesungen der Heizung",
        "zaehlernummer_strom": "die Zählernummer für Strom",
    }
    for field_name, label in required_text_fields.items():
        if not getattr(protocol, field_name).strip():
            errors.append(f"Für die Bestätigung fehlt {label}.")

    if (
        protocol.protokoll_typ == ProtokollTyp.MOVE_OUT
        and not protocol.mieter_zukuenftige_anschrift.strip()
    ):
        errors.append("Für den Auszug fehlt die zukünftige Anschrift.")

    if not list(protocol.protokoll_schluessel.all()):
        errors.append("Für die Bestätigung muss mindestens eine Schlüsselposition erfasst sein.")

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


def _key_form_initial(wohnung) -> list[dict[str, object]]:
    if wohnung is None:
        return []
    return [
        {
            "anzahl": key.anzahl,
            "raum_bezeichnung": key.bezeichnung,
            "aufschrift": key.aufschrift,
        }
        for key in wohnung.schluessel.order_by("bezeichnung")
    ]


def _save_inline_protocol_entries(protocol, room_formset, key_formset) -> None:
    for room_form in room_formset:
        if (
            room_form.cleaned_data
            and not room_form.cleaned_data.get("DELETE")
            and room_form.has_entry()
        ):
            room_form.save(protocol)

    for key_form in key_formset:
        if not key_form.cleaned_data or key_form.cleaned_data.get("DELETE"):
            continue
        key = key_form.save(commit=False)
        key.protokoll = protocol
        key.save()


def _room_form_groups(room_formset) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for room_form in room_formset:
        cleaned_data = getattr(room_form, "cleaned_data", {})
        room_name = cleaned_data.get("raum") or room_form["raum"].value() or ""
        if not groups or groups[-1]["name"] != room_name:
            groups.append(
                {"name": room_name, "room_form": room_form, "checklist_forms": [room_form]}
            )
            continue
        groups[-1]["checklist_forms"].append(room_form)
    return groups
