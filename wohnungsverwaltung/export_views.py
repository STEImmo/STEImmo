import logging
from io import BytesIO

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .access import (
    EMPLOYEE_ACCESS_PERMISSION,
    employee_required,
    handover_reader_required,
    tenant_required,
)
from .export_forms import ProtocolSigningForm
from .handover_archive_files import cleanup_archive_files
from .handover_export import (
    ExportLimitExceeded,
    archive_protocol,
    build_snapshot,
    content_token,
    digest,
    employee_name,
    load_protocol,
    token_matches,
)
from .models import Protokoll, ProtokollStatus, ProtokollTyp, Wohnung, WohnungStatus

logger = logging.getLogger(__name__)


def _detail_url(pk):
    return reverse("wohnungsverwaltung:handover_protocol_detail", args=[pk])


def _allowed_protocol(request, pk):
    queryset = Protokoll.objects.filter(status=ProtokollStatus.SIGNED)
    if not request.user.has_perm(EMPLOYEE_ACCESS_PERMISSION):
        queryset = queryset.filter(person__user=request.user)
    return get_object_or_404(queryset, pk=pk)


@employee_required
@never_cache
@require_GET
def handover_protocol_finalize(request, protocol_id):
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        return redirect(_detail_url(protocol.pk))
    from .views import _protocol_completion_errors

    protocol = load_protocol(protocol.pk)
    errors = _protocol_completion_errors(protocol)
    name = employee_name(request.user)
    if not name or not str(protocol.person).strip():
        errors.append("Bitte hinterlegen Sie zuerst vollständige Namen für Mitarbeiter und Mieter.")
    try:
        snapshot = build_snapshot(protocol, name)
    except ExportLimitExceeded as error:
        messages.error(request, str(error))
        return redirect(_detail_url(protocol.pk))
    except (OSError, ValueError):
        messages.error(
            request, "Ein Protokollfoto kann nicht gelesen werden. Bitte prüfen Sie die Fotos."
        )
        return redirect(_detail_url(protocol.pk))
    form = ProtocolSigningForm(
        initial={"content_token": content_token(snapshot, request.user), "tenant_mode": "signed"}
    )
    return render(
        request,
        "wohnungsverwaltung/handover_protocol_finalize.html",
        {"protocol": protocol, "snapshot": snapshot, "form": form, "completion_errors": errors},
    )


@employee_required
@never_cache
@require_POST
def handover_protocol_confirm(request, protocol_id):
    from .views import _protocol_completion_errors

    stored = []
    try:
        with transaction.atomic():
            protocol = get_object_or_404(Protokoll.objects.select_for_update(), pk=protocol_id)
            if protocol.status == ProtokollStatus.SIGNED:
                return JsonResponse({"redirect": _detail_url(protocol.pk)})
            if protocol.status != ProtokollStatus.OPEN:
                raise Http404
            protocol = load_protocol(protocol.pk)
            name = employee_name(request.user)
            snapshot = build_snapshot(protocol, name)
            if not token_matches(request.POST.get("content_token", ""), snapshot, request.user):
                return JsonResponse(
                    {
                        "error": (
                            "Der Protokollstand hat sich geändert. "
                            "Bitte erneut prüfen und unterschreiben."
                        ),
                        "reload": True,
                    },
                    status=409,
                )
            form = ProtocolSigningForm(request.POST, request.FILES)
            valid = form.is_valid()
            errors = _protocol_completion_errors(protocol)
            if not name or not snapshot["tenant"]:
                errors.append("Vollständige Namen für Mitarbeiter und Mieter sind erforderlich.")
            if not valid or errors:
                errors.extend(
                    f"{form.fields[field].label or field}: {message}"
                    for field, values in form.errors.items()
                    for message in values
                )
                return JsonResponse({"error": "\n".join(errors)}, status=400)
            signatures = {"mitarbeiter": {"name": name, "data": form.cleaned_data["mitarbeiter"]}}
            if form.cleaned_data.get("mieter"):
                signatures["mieter"] = {
                    "name": snapshot["tenant"],
                    "data": form.cleaned_data["mieter"],
                }
            Wohnung.objects.filter(pk=protocol.wohnung_id).update(
                status=WohnungStatus.TAKEN
                if protocol.protokoll_typ == ProtokollTyp.MOVE_IN
                else WohnungStatus.FREE
            )
            archive_protocol(
                protocol,
                snapshot,
                signatures,
                timezone.now(),
                stored,
                reason=form.cleaned_data["reason"],
                user=request.user,
            )
    except ExportLimitExceeded as error:
        cleanup_archive_files(stored)
        return JsonResponse({"error": str(error)}, status=413)
    except (OSError, ValueError):
        cleanup_archive_files(stored)
        logger.error("Übergabeabschluss wegen Export- oder Speicherfehler abgebrochen.")
        return JsonResponse(
            {
                "error": (
                    "PDF konnte nicht vollständig gespeichert werden. "
                    "Das Protokoll bleibt offen; bitte erneut versuchen."
                )
            },
            status=503,
        )
    except Exception:
        cleanup_archive_files(stored)
        raise
    return JsonResponse({"redirect": _detail_url(protocol.pk)})


@tenant_required
@never_cache
@require_GET
def handover_protocol_mine(request):
    protocols = (
        Protokoll.objects.filter(status=ProtokollStatus.SIGNED, person__user=request.user)
        .select_related("wohnung")
        .order_by("-uebergabe_zeitpunkt")
    )
    return render(
        request, "wohnungsverwaltung/handover_protocol_mine.html", {"protocols": protocols}
    )


@handover_reader_required
@never_cache
@require_GET
def handover_protocol_pdf(request, protocol_id):
    protocol = _allowed_protocol(request, protocol_id)
    if not protocol.dokument_pfad:
        raise Http404("Für dieses Protokoll wurde noch kein PDF gesichert.")
    try:
        with default_storage.open(protocol.dokument_pfad, "rb") as source:
            data = source.read()
        if digest(data) != protocol.dokument_hash_sha256:
            raise OSError
    except OSError:
        return render(request, "wohnungsverwaltung/handover_export_error.html", status=503)
    response = FileResponse(
        BytesIO(data),
        as_attachment=True,
        filename=f"uebergabe-{protocol.pk}.pdf",
        content_type="application/pdf",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@handover_reader_required
@never_cache
@require_POST
def handover_protocol_pdf_create(request, protocol_id):
    stored = []
    try:
        with transaction.atomic():
            get_object_or_404(Protokoll.objects.select_for_update(), pk=protocol_id)
            protocol = _allowed_protocol(request, protocol_id)
            if not protocol.dokument_pfad:
                if (
                    protocol.export_snapshot
                    or protocol.gesichert_am
                    or protocol.unterschriften.exists()
                ):
                    return render(
                        request, "wohnungsverwaltung/handover_export_error.html", status=503
                    )
                protocol = load_protocol(protocol.pk)
                archive_protocol(
                    protocol, build_snapshot(protocol), {}, timezone.now(), stored, legacy=True
                )
    except ExportLimitExceeded as error:
        cleanup_archive_files(stored)
        messages.error(request, str(error))
        return render(request, "wohnungsverwaltung/handover_export_error.html", status=413)
    except (OSError, ValueError):
        cleanup_archive_files(stored)
        return render(request, "wohnungsverwaltung/handover_export_error.html", status=503)
    except Exception:
        cleanup_archive_files(stored)
        raise
    return redirect("wohnungsverwaltung:handover_protocol_pdf", protocol_id=protocol_id)
