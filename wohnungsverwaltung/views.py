import json
import logging
from collections import Counter
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from PIL import Image

from .access import (
    APPLICANT_ACCESS_PERMISSION,
    EMPLOYEE_ACCESS_PERMISSION,
    applicant_required,
    employee_required,
    has_permission,
    user_management_required,
)
from .building_plans import (
    FLOOR_SHAPES,
    PLAN_REFERENCES,
    floor_label,
)
from .forms import (
    ACCEPTANCE_STATUS_LABELS,
    HANDOVER_STATUS_LABELS,
    HANDOVER_TYPE_LABELS,
    METER_READING_FIELDS,
    ApartmentPhotoForm,
    ApartmentSearchForm,
    ApplicationProofStorageError,
    BewerbungForm,
    HandoverKeyForm,
    HandoverKeyFormSet,
    HandoverProtocolForm,
    InlineRoomChecklistFormSet,
    MainApplicationForm,
    MerkmalForm,
    MerkmalOptionFormSet,
    RaumForm,
    RoomChecklistItemForm,
    RoomChecklistPhotoUploadForm,
    RoomProtocolForm,
    SchluesselFormSet,
    StellplatzForm,
    StellplatzZuordnungForm,
    UserAccountForm,
    WohnungForm,
    photo_content_type_from_format,
    verified_photo_content_type,
)
from .handover_lock import protocol_mutation
from .handover_photos import (
    PHOTO_SAVE_ERROR,
    HandoverPhotoStorageError,
    delete_apartment_photo,
    delete_handover_photo,
    handover_photo_upload,
    photo_upload,
    save_apartment_photo,
    save_handover_photo,
)
from .models import (
    ApartmentPhoto,
    ApplicationProof,
    ApplicationProofCategory,
    ApplicationProofCleanup,
    Bewerbung,
    BewerbungStatus,
    Merkmal,
    Person,
    Protokoll,
    ProtokollEntwurf,
    ProtokollSchluessel,
    ProtokollStatus,
    ProtokollTyp,
    Raum,
    RaumMerkmal,
    RaumMerkmalFoto,
    Raumprotokoll,
    Stellplatz,
    StellplatzZuordnung,
    Wohnung,
    WohnungStatus,
    calculate_photo_checksum,
)
from .upload_limits import upload_too_large_response

PROTOCOL_STATUS_LABELS = {
    ProtokollStatus.OPEN: "In Bearbeitung",
    ProtokollStatus.SIGNED: "Bestätigt",
    ProtokollStatus.BLOCKED: "Gesperrt",
}
logger = logging.getLogger(__name__)

DRAFT_MAXIMUM_SIZE = 512_000
APPLICATION_PROOF_GROUPS = (
    (ApplicationProofCategory.INCOME, "income_proof", "Gehaltsnachweise"),
    (ApplicationProofCategory.IDENTITY, "identity_proof", "Identitätsnachweis"),
    (ApplicationProofCategory.CREDIT_REPORT, "credit_report_proof", "SCHUFA-Unterlage"),
)


def _can_manage_handover_photos(request: HttpRequest) -> bool:
    """Use the same employee permission for photo UI and all photo endpoints."""

    return has_permission(request, EMPLOYEE_ACCESS_PERMISSION)


def _stored_photo_content_type(photo: RaumMerkmalFoto) -> str:
    """Derive a safe response MIME type from the stored image content."""

    try:
        photo.datei.open("rb")
        with Image.open(photo.datei) as image:
            image_format = image.format
            image.verify()
    except (OSError, ValueError) as error:
        raise Http404("Das gespeicherte Foto ist kein unterstütztes Bild.") from error
    finally:
        photo.datei.close()

    content_type = photo_content_type_from_format(image_format)
    if content_type is None:
        raise Http404("Das gespeicherte Foto ist kein unterstütztes Bild.")
    return content_type


def _valid_wohnung_id(wohnung_id: str | UUID | None) -> UUID | None:
    try:
        return UUID(str(wohnung_id))
    except (TypeError, ValueError):
        return None


def _valid_person_id(person_id: str | UUID | None) -> UUID | None:
    return _valid_wohnung_id(person_id)


def apartment_search(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    form = ApartmentSearchForm(request.GET)
    wohnungen = Wohnung.objects.available()
    if form.is_valid():
        filter_fields = {
            "groesse_min": "groesse_qm__gte",
            "groesse_max": "groesse_qm__lte",
            "kaltmiete_min": "kaltmiete__gte",
            "kaltmiete_max": "kaltmiete__lte",
            "zimmer_min": "zimmeranzahl__gte",
            "zimmer_max": "zimmeranzahl__lte",
            "etage": "etage",
        }
        filters = {
            lookup: form.cleaned_data[field_name]
            for field_name, lookup in filter_fields.items()
            if form.cleaned_data[field_name] not in (None, "")
        }
        wohnungen = wohnungen.filter(**filters)
        if any(form.cleaned_data[field] is not None for field in ("zimmer_min", "zimmer_max")):
            wohnungen = wohnungen.filter(zimmeranzahl__gt=0)
        if any(
            form.cleaned_data[field] is not None for field in ("kaltmiete_min", "kaltmiete_max")
        ):
            wohnungen = wohnungen.filter(kaltmiete__gt=0)
    else:
        wohnungen = wohnungen.none()

    return render(
        request,
        "wohnungsverwaltung/apartment_search.html",
        {
            "form": form,
            "wohnungen": wohnungen.order_by("etage", "wohnungsnummer"),
        },
    )


def building_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    floors_by_number = {}
    for unit in Wohnung.objects.filter(etage__in=FLOOR_SHAPES).order_by("-etage", "wohnungsnummer"):
        floor = floors_by_number.setdefault(
            unit.etage,
            {
                "number": unit.etage,
                "label": floor_label(unit.etage),
                "units": [],
                "available_count": 0,
                "facade_y": 244 + (3 - unit.etage) * 112,
            },
        )
        floor["units"].append(unit)
        if unit.status == WohnungStatus.FREE:
            floor["available_count"] += 1
    return render(
        request,
        "wohnungsverwaltung/building_view.html",
        {
            "floors": list(floors_by_number.values()),
            "total_units": sum(len(f["units"]) for f in floors_by_number.values()),
            "total_available": sum(f["available_count"] for f in floors_by_number.values()),
        },
    )


def floor_view(request: HttpRequest, floor_number: int) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    if floor_number not in FLOOR_SHAPES:
        raise Http404("Diese Etage ist nicht vorhanden.")
    units = list(Wohnung.objects.filter(etage=floor_number).order_by("wohnungsnummer"))
    if not units:
        raise Http404("Diese Etage ist nicht vorhanden.")
    shapes = FLOOR_SHAPES[floor_number]
    number_counts = Counter(unit.display_number for unit in units)
    plan_units = []
    for unit in units:
        shape = shapes.get(unit.display_number)
        if shape is None or number_counts[unit.display_number] != 1:
            continue
        points, x, y = shape
        plan_units.append({"unit": unit, "points": points, "x": x, "y": y})
    return render(
        request,
        "wohnungsverwaltung/floor_view.html",
        {
            "floor_number": floor_number,
            "floor_label": floor_label(floor_number),
            "floor_numbers": [
                (number, floor_label(number))
                for number in Wohnung.objects.filter(etage__in=FLOOR_SHAPES)
                .order_by("etage")
                .values_list("etage", flat=True)
                .distinct()
            ],
            "units": units,
            "plan_units": plan_units,
            "has_unmapped_units": len(plan_units) != len(units),
            "plan_reference": PLAN_REFERENCES[
                "ground" if floor_number == 0 else "attic" if floor_number == 4 else "regular"
            ],
        },
    )


def apartment_detail_placeholder(request: HttpRequest, unit_id: UUID) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    wohnung = get_object_or_404(Wohnung.objects.available(), pk=unit_id)
    return render(
        request,
        "wohnungsverwaltung/apartment_detail_placeholder.html",
        {
            "wohnung": wohnung,
            "photos": list(wohnung.photos.all()),
            "floor_label": floor_label(wohnung.etage),
            "has_floor_plan": wohnung.etage in FLOOR_SHAPES,
        },
    )


def apartment_photo(request: HttpRequest, photo_id: UUID) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    photos = ApartmentPhoto.objects.select_related("apartment")
    if not has_permission(request, EMPLOYEE_ACCESS_PERMISSION):
        photos = photos.filter(apartment__status=WohnungStatus.FREE)
    photo = get_object_or_404(photos, pk=photo_id)
    try:
        response = FileResponse(photo.image.open("rb"), content_type="image/jpeg")
    except OSError as error:
        raise Http404("Foto nicht verfügbar.") from error
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@employee_required
def apartment_photos(request: HttpRequest, wohnung_id: UUID) -> HttpResponse:
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    apartment = get_object_or_404(Wohnung, pk=wohnung_id)
    form = ApartmentPhotoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        saved = False
        try:
            with photo_upload() as stored_files:
                apartment = Wohnung.objects.select_for_update().get(pk=wohnung_id)
                if apartment.photos.count() >= settings.APARTMENT_PHOTO_MAX_COUNT:
                    form.add_error("image", "Pro Wohnung sind höchstens 12 Fotos erlaubt.")
                else:
                    photo = form.save(commit=False)
                    photo.apartment = apartment
                    save_apartment_photo(photo, stored_files)
                    saved = True
        except (HandoverPhotoStorageError, DatabaseError):
            logger.warning("Wohnungsfoto konnte nicht gespeichert werden.")
            form.add_error(
                "image", "Das Wohnungsfoto konnte nicht gespeichert werden. Bitte erneut auswählen."
            )
        else:
            if saved:
                messages.success(request, "Das Wohnungsfoto wurde gespeichert.")
                return redirect("verwaltung:apartment_photos", wohnung_id=apartment.pk)
    return render(
        request,
        "wohnungsverwaltung/apartment_photos.html",
        {
            "wohnung": apartment,
            "form": form,
            "photos": apartment.photos.all(),
        },
    )


@employee_required
def apartment_photo_delete(request: HttpRequest, wohnung_id: UUID, photo_id: UUID) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        with transaction.atomic():
            photo = get_object_or_404(
                ApartmentPhoto.objects.select_for_update(), pk=photo_id, apartment_id=wohnung_id
            )
            delete_apartment_photo(photo)
    except (OSError, DatabaseError):
        logger.warning("Wohnungsfoto konnte nicht entfernt werden.")
        messages.error(
            request, "Das Foto konnte nicht entfernt werden. Bitte versuchen Sie es erneut."
        )
    else:
        messages.success(request, "Das Wohnungsfoto wurde entfernt.")
    return redirect("verwaltung:apartment_photos", wohnung_id=wohnung_id)


def pre_application_preview(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return render(
        request,
        "wohnungsverwaltung/pre_application_preview.html",
        {"form": BewerbungForm(applicant=Person())},
    )


@login_required
def viewing_request(request: HttpRequest, unit_id: UUID) -> HttpResponse:
    unit = get_object_or_404(Wohnung.objects.available(), pk=unit_id)
    if (
        request.user.has_perm(APPLICANT_ACCESS_PERMISSION)
        and getattr(request.user, "person_profile", None) is not None
    ):
        return redirect("wohnungsverwaltung:pre_application_create_for_unit", unit_id=unit.pk)
    return render(
        request,
        "wohnungsverwaltung/viewing_request_unavailable.html",
        {
            "wohnung": unit,
            "missing_profile": request.user.has_perm(APPLICANT_ACCESS_PERMISSION),
        },
    )


def _applicant_for_user(request: HttpRequest) -> Person:
    applicant = getattr(request.user, "person_profile", None)
    if applicant is None:
        raise PermissionDenied("Dem Benutzerkonto ist keine Person zugeordnet.")
    return applicant


@applicant_required
def pre_application_create(request: HttpRequest, unit_id: UUID | None = None) -> HttpResponse:
    applicant = _applicant_for_user(request)
    unit = None
    if unit_id is not None:
        unit = get_object_or_404(Wohnung.objects.available(), pk=unit_id)

    form = BewerbungForm(request.POST or None, applicant=applicant, unit=unit)
    application_created = False
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                selected_unit = (
                    Wohnung.objects.select_for_update()
                    .available()
                    .filter(pk=form.cleaned_data["wohnung"].pk)
                    .first()
                )
                if selected_unit is None:
                    form.add_error("wohnung", "Die Wohnung ist nicht mehr verfügbar.")
                else:
                    form.instance.wohnung = selected_unit
                    form.save()
                    application_created = True
        except IntegrityError:
            form.add_error(
                None,
                "Sie haben bereits eine offene Pre-Bewerbung. Bitte warten Sie deren Abschluss ab.",
            )
        if application_created:
            messages.success(
                request,
                "Ihre Besichtigungsanfrage wurde gespeichert. Ein Termin wird separat bestätigt."
                if unit is not None
                else "Ihre Pre-Bewerbung wurde erfolgreich gespeichert.",
            )
            return redirect("wohnungsverwaltung:pre_application_list")

    return render(
        request,
        "wohnungsverwaltung/pre_application_form.html",
        {"form": form, "unit_is_preselected": unit is not None},
    )


@applicant_required
def pre_application_list(request: HttpRequest) -> HttpResponse:
    applicant = _applicant_for_user(request)
    applications = (
        Bewerbung.objects.filter(person=applicant).select_related("wohnung").order_by("-created_at")
    )
    return render(
        request,
        "wohnungsverwaltung/pre_application_list.html",
        {
            "applications": applications,
            "has_open_application": applications.filter(
                status=BewerbungStatus.OPEN,
                interest_withdrawn_at__isnull=True,
            ).exists(),
        },
    )


def _stored_file_size_display(file_field) -> str:
    try:
        size = file_field.size
    except (NotImplementedError, OSError):
        return "Größe nicht verfügbar"

    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.1f} MiB"


def _application_proof_groups(
    application: Bewerbung,
    *,
    employee: bool = False,
) -> list[dict]:
    legacy_download_view = (
        "wohnungsverwaltung:employee_application_document"
        if employee
        else "wohnungsverwaltung:applicant_application_document"
    )
    proof_download_view = (
        "wohnungsverwaltung:employee_application_proof_download"
        if employee
        else "wohnungsverwaltung:applicant_application_proof_download"
    )
    uploaded_by_category = {
        category: [] for category, _field_name, _label in APPLICATION_PROOF_GROUPS
    }
    for proof in application.proof_files.all():
        uploaded_by_category[proof.category].append(proof)

    groups = []
    for category, legacy_field, label in APPLICATION_PROOF_GROUPS:
        documents = []
        legacy_file = getattr(application, legacy_field)
        if legacy_file:
            original_name = getattr(application, f"{legacy_field}_original_name")
            documents.append(
                {
                    "name": original_name or "Dateiname dieses älteren Uploads nicht erfasst",
                    "size_display": _stored_file_size_display(legacy_file),
                    "delete_id": f"legacy:{legacy_field}",
                    "download_url": reverse(
                        legacy_download_view,
                        args=(application.pk, legacy_field),
                    ),
                    "can_remove": application.submitted_at is None,
                }
            )

        for proof in uploaded_by_category[category]:
            documents.append(
                {
                    "name": proof.original_name,
                    "size_display": _stored_file_size_display(proof.file),
                    "delete_id": str(proof.pk),
                    "download_url": reverse(
                        proof_download_view,
                        args=(application.pk, proof.pk),
                    ),
                    "can_remove": application.submitted_at is None,
                }
            )

        groups.append(
            {
                "field_name": legacy_field,
                "label": label,
                "documents": documents,
            }
        )
    return groups


def _application_proof_count(application: Bewerbung, category: str, legacy_field: str) -> int:
    return (
        int(bool(getattr(application, legacy_field)))
        + application.proof_files.filter(category=category).count()
    )


def _remove_application_proof(
    request: HttpRequest,
    application: Bewerbung,
    application_id: UUID,
) -> HttpResponse:
    reference = request.POST.get("remove_proof", "")
    if reference.startswith("legacy:"):
        legacy_field = reference.removeprefix("legacy:")
        category = next(
            (
                category
                for category, field_name, _label in APPLICATION_PROOF_GROUPS
                if field_name == legacy_field
            ),
            None,
        )
        if category is None:
            raise Http404("Dieser Nachweis existiert nicht.")

        proof_file = getattr(application, legacy_field)
        if not proof_file:
            raise Http404("Dieser Nachweis wurde bereits entfernt.")
        if (
            application.submitted_at is not None
            and _application_proof_count(application, category, legacy_field) <= 1
        ):
            messages.error(
                request,
                "Nach der Einreichung muss pro Kategorie mindestens ein Nachweis vorliegen. "
                "Laden Sie zuerst eine Ersatzdatei hoch.",
            )
            return redirect(
                "wohnungsverwaltung:main_application_status", application_id=application_id
            )

        storage, stored_name = proof_file.storage, proof_file.name
        original_name_field = f"{legacy_field}_original_name"
        with transaction.atomic():
            setattr(application, legacy_field, "")
            setattr(application, original_name_field, "")
            application.save(update_fields=(legacy_field, original_name_field, "updated_at"))
            _queue_application_proof_deletion(storage, stored_name)
    else:
        try:
            proof_id = UUID(reference)
        except ValueError as error:
            raise Http404("Dieser Nachweis existiert nicht.") from error
        proof = get_object_or_404(
            ApplicationProof.objects.filter(application=application),
            pk=proof_id,
        )
        if (
            application.submitted_at is not None
            and _application_proof_count(
                application,
                proof.category,
                next(
                    field_name
                    for category, field_name, _label in APPLICATION_PROOF_GROUPS
                    if category == proof.category
                ),
            )
            <= 1
        ):
            messages.error(
                request,
                "Nach der Einreichung muss pro Kategorie mindestens ein Nachweis vorliegen. "
                "Laden Sie zuerst eine Ersatzdatei hoch.",
            )
            return redirect(
                "wohnungsverwaltung:main_application_status", application_id=application_id
            )

        storage, stored_name = proof.file.storage, proof.file.name
        with transaction.atomic():
            proof.delete()
            _queue_application_proof_deletion(storage, stored_name)

    return redirect("wohnungsverwaltung:main_application_status", application_id=application_id)


def _queue_application_proof_deletion(storage, stored_name: str) -> None:
    """Persist deletion intent together with removal of the document reference."""
    cleanup, _created = ApplicationProofCleanup.objects.get_or_create(storage_name=stored_name)

    def delete_after_commit():
        try:
            storage.delete(stored_name)
            cleanup.delete()
        except Exception as error:
            logger.error(
                "Could not delete stored application proof %s (%s); cleanup remains queued.",
                stored_name,
                type(error).__name__,
            )

    transaction.on_commit(delete_after_commit)


@applicant_required
def main_application_status(request: HttpRequest, application_id: UUID) -> HttpResponse:
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])

    applicant = _applicant_for_user(request)
    eligible_applications = Bewerbung.objects.filter(
        person=applicant,
        status=BewerbungStatus.OPEN,
        interest_withdrawn_at__isnull=True,
        main_application_unlocked=True,
    )

    if request.method == "GET":
        application = get_object_or_404(
            eligible_applications.select_related("wohnung"),
            pk=application_id,
        )
        form = MainApplicationForm(instance=application)
    else:
        post_data = request.POST
        uploaded_files = request.FILES
        upload_error = getattr(request, "_main_application_upload_error", None)
        form = None
        application = None
        action = None
        form_is_valid = False

        try:
            with transaction.atomic():
                # All mutations of this application serialize on the same row. Recheck
                # access and submission state only after acquiring the lock.
                application = get_object_or_404(
                    eligible_applications.select_for_update(),
                    pk=application_id,
                )
                if application.submitted_at is not None:
                    raise PermissionDenied(
                        "Eine eingereichte Main-Bewerbung kann nicht mehr geändert werden."
                    )
                if upload_error:
                    return upload_too_large_response(upload_error)
                if "remove_proof" in post_data:
                    removal_response = _remove_application_proof(
                        request, application, application_id
                    )
                else:
                    form = MainApplicationForm(
                        post_data,
                        uploaded_files,
                        instance=application,
                    )
                    form_is_valid = form.is_valid()
                    if form_is_valid:
                        action = form.cleaned_data["action"]
                        form.save_uploaded_proofs()
                        if action == "submit":
                            application.submitted_at = timezone.now()
                            application.save(update_fields=("submitted_at", "updated_at"))
                        else:
                            application.save(update_fields=("updated_at",))
            if "remove_proof" in post_data:
                messages.success(request, "Der Nachweis wurde aus dem Entwurf entfernt.")
                return removal_response

        except (ApplicationProofStorageError, DatabaseError) as error:
            if form is None or application is None:
                if application is not None and "remove_proof" in post_data:
                    logger.error(
                        "Main application proof removal failed (%s).", type(error).__name__
                    )
                    messages.error(
                        request,
                        "Der Nachweis konnte nicht entfernt werden. Bitte versuchen Sie es erneut.",
                    )
                    return redirect(
                        "wohnungsverwaltung:main_application_status", application_id=application_id
                    )
                raise

            cleanup_failures = form.cleanup_stored_proof_files()
            for storage, stored_name in cleanup_failures:
                try:
                    ApplicationProofCleanup.objects.get_or_create(storage_name=stored_name)
                except DatabaseError as cleanup_error:
                    logger.error(
                        "Could not persist cleanup job for application proof %s (%s).",
                        stored_name,
                        type(cleanup_error).__name__,
                    )
            logger.error(
                "Main application proof persistence failed (%s).",
                type(error).__name__,
            )
            application.refresh_from_db()
            form.instance = application
            form.add_error(
                None,
                "Dateien konnten nicht sicher gespeichert werden. Bitte versuchen Sie es erneut.",
            )
            return render(
                request,
                "wohnungsverwaltung/main_application_status.html",
                {
                    "application": application,
                    "form": form,
                    "proof_groups": _application_proof_groups(application),
                },
            )

        if not form_is_valid:
            return render(
                request,
                "wohnungsverwaltung/main_application_status.html",
                {
                    "application": application,
                    "form": form,
                    "proof_groups": _application_proof_groups(application),
                },
            )

        if action == "submit":
            messages.success(request, "Ihre Main-Bewerbung wurde erfolgreich eingereicht.")
        else:
            messages.success(request, "Ihr Entwurf wurde gespeichert.")
        return redirect(
            "wohnungsverwaltung:main_application_status",
            application_id=application.pk,
        )

    proof_groups = _application_proof_groups(application)

    return render(
        request,
        "wohnungsverwaltung/main_application_status.html",
        {
            "application": application,
            "form": form,
            "proof_groups": proof_groups,
        },
    )


@never_cache
@employee_required
def employee_application_list(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    context = {}
    if "wohnung" in request.GET:
        unit_id = _valid_wohnung_id(request.GET.get("wohnung"))
        if unit_id is None:
            raise Http404("Diese Wohnung existiert nicht.")
        unit = get_object_or_404(Wohnung, pk=unit_id)
        applications = (
            Bewerbung.objects.filter(wohnung=unit)
            .select_related("person", "wohnung")
            .order_by("-created_at", "pk")
        )
        page = Paginator(applications, 20).get_page(request.GET.get("page"))
        context.update(unit=unit, applications=page, page_obj=page)
    else:
        context["units"] = Wohnung.objects.annotate(
            application_count=Count("bewerbungen")
        ).order_by("gebaeudenummer", "wohnungsnummer", "pk")

    return render(
        request,
        "wohnungsverwaltung/employee_application_list.html",
        context,
    )


@never_cache
@employee_required
def employee_application_detail(request: HttpRequest, application_id: UUID) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    application = get_object_or_404(
        Bewerbung.objects.select_related("person", "wohnung").prefetch_related(
            "bewerbung_stellplaetze__stellplatz"
        ),
        pk=application_id,
    )
    return render(
        request,
        "wohnungsverwaltung/employee_application_detail.html",
        {
            "application": application,
            "proof_groups": (
                _application_proof_groups(application, employee=True)
                if application.submitted_at is not None
                else []
            ),
        },
    )


def _application_document_response(proof_file, download_label: str) -> FileResponse:
    try:
        stream = proof_file.open("rb")
        header = stream.read(8)
        # Upload validation already checks the full file. Here the signature only
        # selects the download extension, including for older private proofs.
        if header.startswith(b"%PDF-"):
            extension = "pdf"
        elif header.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        else:
            raise Http404("Der gespeicherte Nachweis hat ein ungültiges Dateiformat.")
        stream.seek(0)
        # Keep this descriptor open: removing the path concurrently must not
        # force a second open between checking and streaming the document.
        response = FileResponse(
            stream,
            as_attachment=True,
            filename=f"{download_label}.{extension}",
            content_type="application/octet-stream",
        )
    except (OSError, ValueError) as error:
        proof_file.close()
        raise Http404("Der gespeicherte Nachweis kann nicht geöffnet werden.") from error
    except Exception:
        proof_file.close()
        raise

    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@employee_required
def employee_application_document(
    request: HttpRequest,
    application_id: UUID,
    document_type: str,
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    document_labels = {
        "income_proof": ("Gehaltsnachweise", "Gehaltsnachweis"),
        "identity_proof": ("Identitätsnachweis", "Identitaetsnachweis"),
        "credit_report_proof": ("SCHUFA-Unterlage", "SCHUFA-Unterlage"),
    }
    if document_type not in document_labels:
        raise Http404("Dieser Nachweis existiert nicht.")

    application = get_object_or_404(
        Bewerbung.objects.filter(submitted_at__isnull=False),
        pk=application_id,
    )
    proof = getattr(application, document_type)
    if not proof:
        raise Http404("Dieser Nachweis wurde noch nicht hochgeladen.")

    return _application_document_response(proof, document_labels[document_type][1])


@employee_required
def employee_application_proof_download(
    request: HttpRequest,
    application_id: UUID,
    proof_id: UUID,
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    proof = get_object_or_404(
        ApplicationProof.objects.filter(
            application__pk=application_id,
            application__submitted_at__isnull=False,
        ),
        pk=proof_id,
    )
    download_labels = {
        ApplicationProofCategory.INCOME: "Gehaltsnachweis",
        ApplicationProofCategory.IDENTITY: "Identitaetsnachweis",
        ApplicationProofCategory.CREDIT_REPORT: "SCHUFA-Unterlage",
    }
    return _application_document_response(proof.file, download_labels[proof.category])


@applicant_required
def applicant_application_document(
    request: HttpRequest,
    application_id: UUID,
    document_type: str,
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    applicant = _applicant_for_user(request)
    application = get_object_or_404(
        Bewerbung.objects.filter(
            person=applicant,
            status=BewerbungStatus.OPEN,
            interest_withdrawn_at__isnull=True,
            main_application_unlocked=True,
        ),
        pk=application_id,
    )
    document_labels = {
        "income_proof": ("Gehaltsnachweise", "Gehaltsnachweis"),
        "identity_proof": ("Identitätsnachweis", "Identitaetsnachweis"),
        "credit_report_proof": ("SCHUFA-Unterlage", "SCHUFA-Unterlage"),
    }
    if document_type not in document_labels:
        raise Http404("Dieser Nachweis existiert nicht.")

    proof_file = getattr(application, document_type)
    if not proof_file:
        raise Http404("Dieser Nachweis wurde nicht hochgeladen.")

    return _application_document_response(proof_file, document_labels[document_type][1])


@applicant_required
def applicant_application_proof_download(
    request: HttpRequest,
    application_id: UUID,
    proof_id: UUID,
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    applicant = _applicant_for_user(request)
    application = get_object_or_404(
        Bewerbung.objects.filter(
            person=applicant,
            status=BewerbungStatus.OPEN,
            interest_withdrawn_at__isnull=True,
            main_application_unlocked=True,
        ),
        pk=application_id,
    )
    proof = get_object_or_404(application.proof_files.all(), pk=proof_id)
    download_labels = {
        ApplicationProofCategory.INCOME: "Gehaltsnachweis",
        ApplicationProofCategory.IDENTITY: "Identitaetsnachweis",
        ApplicationProofCategory.CREDIT_REPORT: "SCHUFA-Unterlage",
    }
    return _application_document_response(proof.file, download_labels[proof.category])


@applicant_required
def application_withdraw(request: HttpRequest, application_id: UUID) -> HttpResponse:
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])

    applicant = _applicant_for_user(request)
    eligible_applications = Bewerbung.objects.filter(
        person=applicant,
        status=BewerbungStatus.OPEN,
        interest_withdrawn_at__isnull=True,
        main_application_unlocked=True,
    )

    if request.method == "GET":
        application = get_object_or_404(
            eligible_applications.select_related("wohnung"),
            pk=application_id,
        )
        return render(
            request,
            "wohnungsverwaltung/application_withdraw_confirm.html",
            {"application": application},
        )

    with transaction.atomic():
        application = get_object_or_404(
            eligible_applications.select_for_update(),
            pk=application_id,
        )
        application.interest_withdrawn_at = timezone.now()
        application.save(update_fields=["interest_withdrawn_at", "updated_at"])

    messages.success(request, "Ihr Interesse an dieser Bewerbung wurde zurückgezogen.")
    return redirect("wohnungsverwaltung:pre_application_list")


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


def _validate_draft_storage_values(payload):
    # PostgreSQL JSONB cannot store nonfinite numbers, null characters or
    # unpaired Unicode surrogates. Validate before touching an existing draft.
    json.dumps(payload, allow_nan=False, ensure_ascii=False).encode("utf-8")
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str) and "\x00" in value:
            raise ValueError("JSONB does not support null characters.")


@employee_required
def handover_protocol_draft_save(request: HttpRequest) -> JsonResponse | HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if len(request.body) > DRAFT_MAXIMUM_SIZE:
        return JsonResponse({"error": "Der Entwurf ist zu groß."}, status=400)
    try:
        payload = json.loads(request.body.decode("utf-8"))
        _validate_draft_storage_values(payload)
    except (ValueError, RecursionError):
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


@employee_required
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


@employee_required
def handover_protocol_list(request: HttpRequest) -> HttpResponse:
    protocols = Protokoll.objects.select_related("wohnung", "person").order_by("-updated_at")
    return render(
        request,
        "wohnungsverwaltung/handover_protocol_list.html",
        {"protocols": protocols, "draft_entries": _draft_overview_entries(request)},
    )


@employee_required
def handover_protocol_create(request: HttpRequest) -> HttpResponse:
    draft_scope = "create"
    server_draft = _draft_for_form(request, draft_scope)
    selected_wohnung_id = (
        request.POST.get("wohnung")
        or request.GET.get("wohnung")
        or (_draft_field_value(server_draft, "wohnung") if server_draft else None)
    )
    selected_person_id = (
        request.POST.get("person")
        or request.GET.get("person")
        or (_draft_field_value(server_draft, "person") if server_draft else None)
    )
    form = HandoverProtocolForm(
        request.POST or None, wohnung_id=selected_wohnung_id, employee=request.user
    )
    _set_selected_person_initial(form, selected_person_id)
    can_manage_handover_photos = _can_manage_handover_photos(request)
    room_formset = InlineRoomChecklistFormSet(
        data=request.POST or None,
        files=request.FILES or None,
        prefix="rooms",
        form_kwargs={
            "wohnung_id": _valid_wohnung_id(selected_wohnung_id),
            "allow_photo_upload": can_manage_handover_photos,
        },
    )
    key_formset = HandoverKeyFormSet(
        request.POST or None,
        prefix="keys",
        initial=_key_form_initial(form.selected_wohnung) if request.method != "POST" else None,
    )
    move_in_reference = None
    if can_manage_handover_photos:
        move_in_reference = _move_in_reference_for_apartment(
            _valid_wohnung_id(selected_wohnung_id),
            person_id=_valid_person_id(selected_person_id),
        )
    if (
        request.method == "POST"
        and form.is_valid()
        and room_formset.is_valid()
        and key_formset.is_valid()
    ):
        try:
            with handover_photo_upload() as stored_photo_files:
                protocol = form.save()
                _save_inline_protocol_entries(
                    protocol,
                    room_formset,
                    key_formset,
                    stored_photo_files,
                    removed_rooms=form.cleaned_data["removed_rooms"],
                )
                _delete_draft(request, draft_scope)
        except (HandoverPhotoStorageError, DatabaseError) as error:
            logger.error("Protocol creation failed (%s).", type(error).__name__)
            form.add_error(None, PHOTO_SAVE_ERROR)
        else:
            request.session["handover_protocol_draft_key_to_clear"] = (
                "handover-protocol-draft:create"
            )
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
            "room_form_groups": _room_form_groups(
                room_formset, request.POST.getlist("removed_rooms")
            ),
            "key_formset": key_formset,
            "move_in_reference": move_in_reference,
            "meter_comparison_rows": _meter_comparison_rows(form, move_in_reference),
            "can_manage_handover_photos": can_manage_handover_photos,
            **_move_in_reference_context(move_in_reference),
            "draft_scope": draft_scope,
            **_draft_form_context(server_draft),
        },
    )


def _archived_assignment_label(protocol, label):
    if protocol.status != ProtokollStatus.SIGNED or not isinstance(protocol.export_snapshot, dict):
        return ""
    sections = protocol.export_snapshot.get("sections")
    if not isinstance(sections, list):
        return ""
    for section in sections:
        if not isinstance(section, dict) or section.get("title") != "Zuordnung":
            continue
        rows = section.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if (
                isinstance(row, list)
                and len(row) == 2
                and row[0] == label
                and isinstance(row[1], str)
                and row[1].strip()
            ):
                return row[1]
    return ""


def _archived_tenant_name(protocol):
    if protocol.status != ProtokollStatus.SIGNED or not isinstance(protocol.export_snapshot, dict):
        return ""
    name = protocol.export_snapshot.get("tenant")
    if isinstance(name, str) and name.strip():
        return name
    return _archived_assignment_label(protocol, "Mieter")


@employee_required
def handover_protocol_detail(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(
        Protokoll.objects.select_related("wohnung", "person").prefetch_related(
            "protokoll_schluessel",
            "raeume__raum_merkmale__merkmal",
            "raeume__raum_merkmale__fotos",
        ),
        pk=protocol_id,
    )
    can_manage_handover_photos = _can_manage_handover_photos(request)
    move_in_reference = None
    if can_manage_handover_photos:
        move_in_reference = _attach_move_in_photo_references(protocol, protocol.raeume.all())
    archived_snapshot = None
    if (
        protocol.status == ProtokollStatus.SIGNED
        and isinstance(protocol.export_snapshot, dict)
        and isinstance(protocol.export_snapshot.get("rooms"), list)
    ):
        archived_snapshot = protocol.export_snapshot
    archived_apartment_label = _archived_assignment_label(protocol, "Wohnung")
    archived_tenant_name = _archived_tenant_name(protocol)
    return render(
        request,
        "wohnungsverwaltung/handover_protocol_detail.html",
        {
            "protocol": protocol,
            "representative_name": _representative_name(protocol, request.user),
            "protocol_type_label": HANDOVER_TYPE_LABELS[protocol.protokoll_typ],
            "handover_status_label": HANDOVER_STATUS_LABELS[protocol.uebergabe_status],
            "acceptance_status_label": ACCEPTANCE_STATUS_LABELS[protocol.abnahme_status],
            "protocol_status_label": PROTOCOL_STATUS_LABELS[protocol.status],
            "archived_snapshot": archived_snapshot,
            "apartment_label": archived_apartment_label or str(protocol.wohnung),
            "uses_current_apartment_label": protocol.status == ProtokollStatus.SIGNED
            and not archived_apartment_label,
            "tenant_name": archived_tenant_name or str(protocol.person),
            "uses_current_tenant_name": protocol.status == ProtokollStatus.SIGNED
            and not archived_tenant_name,
            "can_manage_handover_photos": can_manage_handover_photos,
            "move_in_reference": move_in_reference,
            **_move_in_reference_context(move_in_reference),
            "draft_key_to_clear": request.session.pop("handover_protocol_draft_key_to_clear", ""),
        },
    )


@employee_required
@protocol_mutation
def handover_protocol_edit(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    draft_scope = f"edit:{protocol.pk}"
    server_draft = _draft_for_form(request, draft_scope)
    selected_wohnung_id = request.POST.get("wohnung") or request.GET.get("wohnung")
    selected_person_id = (
        request.POST.get("person") or request.GET.get("person") or protocol.person_id
    )
    form = HandoverProtocolForm(
        request.POST or None,
        instance=protocol,
        wohnung_id=selected_wohnung_id or protocol.wohnung_id,
        employee=request.user,
    )
    _set_selected_person_initial(form, selected_person_id)
    form_valid = request.method == "POST" and form.is_valid()
    can_manage_handover_photos = _can_manage_handover_photos(request)
    room_formset = InlineRoomChecklistFormSet(
        data=request.POST or None,
        files=request.FILES or None,
        prefix="rooms",
        initial=_protocol_room_initial(protocol) if request.method != "POST" else None,
        form_kwargs={
            "wohnung_id": _valid_wohnung_id(selected_wohnung_id or protocol.wohnung_id),
            "allow_photo_upload": can_manage_handover_photos,
            "protocol": protocol,
            "removed_rooms": getattr(form, "cleaned_data", {}).get("removed_rooms", ()),
        },
    )
    key_formset = HandoverKeyFormSet(
        request.POST or None,
        prefix="keys",
        initial=_protocol_key_initial(protocol) if request.method != "POST" else None,
        form_kwargs={"protocol": protocol},
    )
    move_in_reference = None
    if can_manage_handover_photos:
        move_in_reference = _move_in_reference_for_apartment(
            _valid_wohnung_id(selected_wohnung_id or protocol.wohnung_id),
            person_id=_valid_person_id(selected_person_id),
        )
    if (
        request.method == "POST"
        and form_valid
        and room_formset.is_valid()
        and key_formset.is_valid()
    ):
        try:
            with handover_photo_upload() as stored_photo_files:
                protocol = form.save()
                _save_inline_protocol_entries(
                    protocol,
                    room_formset,
                    key_formset,
                    stored_photo_files,
                    removed_rooms=form.cleaned_data["removed_rooms"],
                )
                _delete_draft(request, draft_scope)
        except (HandoverPhotoStorageError, DatabaseError) as error:
            logger.error("Protocol edit failed (%s).", type(error).__name__)
            protocol.refresh_from_db()
            form.add_error(None, PHOTO_SAVE_ERROR)
        else:
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
            "room_form_groups": _room_form_groups(
                room_formset, request.POST.getlist("removed_rooms")
            ),
            "key_formset": key_formset,
            "move_in_reference": move_in_reference,
            "meter_comparison_rows": _meter_comparison_rows(form, move_in_reference),
            "can_manage_handover_photos": can_manage_handover_photos,
            **_move_in_reference_context(move_in_reference),
            "draft_scope": draft_scope,
            **_draft_form_context(server_draft),
        },
    )


@employee_required
@protocol_mutation
def handover_protocol_room_create(request: HttpRequest, protocol_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    form = RoomProtocolForm(request.POST or None, protocol=protocol)
    if request.method == "POST" and form.is_valid():
        master_room = form.cleaned_data["raum"]
        room = Raumprotokoll.objects.create(
            protokoll=protocol,
            raum=master_room,
            name=master_room.name,
        )
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


@employee_required
@protocol_mutation
def handover_protocol_room_detail(request: HttpRequest, protocol_id, room_id) -> HttpResponse:
    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    room = get_object_or_404(
        Raumprotokoll.objects.prefetch_related("raum_merkmale__merkmal", "raum_merkmale__fotos"),
        pk=room_id,
        protokoll=protocol,
    )
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    can_manage_handover_photos = _can_manage_handover_photos(request)
    move_in_reference = None
    if can_manage_handover_photos:
        move_in_reference = _attach_move_in_photo_references(protocol, [room])

    form = RoomChecklistItemForm(request.POST or None, initial={"bereich": room.name}, room=room)
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
        {
            "form": form,
            "protocol": protocol,
            "room": room,
            "move_in_reference": move_in_reference,
            "can_manage_handover_photos": can_manage_handover_photos,
        },
    )


@employee_required
@protocol_mutation
def handover_protocol_room_delete(request: HttpRequest, protocol_id, room_id) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    room = get_object_or_404(Raumprotokoll, pk=room_id, protokoll=protocol)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    with transaction.atomic():
        _delete_checklist_photos(RaumMerkmalFoto.objects.filter(raum_merkmal__raumprotokoll=room))
        room.delete()
    messages.success(request, "Der Raum wurde aus dem Übergabeprotokoll entfernt.")
    return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)


@employee_required
@protocol_mutation
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

    with transaction.atomic():
        _delete_checklist_photos(checklist_item.fotos.all())
        checklist_item.delete()
    messages.success(request, "Der Prüfpunkt wurde aus dem Raum entfernt.")
    return redirect(
        "wohnungsverwaltung:handover_protocol_room_detail",
        protocol_id=protocol.pk,
        room_id=room.pk,
    )


@employee_required
@protocol_mutation
def handover_protocol_checklist_item_photo_upload(
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

    form = RoomChecklistPhotoUploadForm(
        request.POST,
        request.FILES,
        existing_photos=checklist_item.fotos.all(),
    )
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(_photo_return_url(request, protocol, room, checklist_item))

    photos_to_save = [
        (photo, calculate_photo_checksum(photo)) for photo in form.cleaned_data["fotos"]
    ]

    if not photos_to_save:
        messages.info(request, "Dieses Foto ist für den Prüfpunkt bereits gespeichert.")
        return redirect(_photo_return_url(request, protocol, room, checklist_item))

    try:
        with handover_photo_upload() as stored_photo_files:
            for photo, checksum in photos_to_save:
                save_handover_photo(
                    RaumMerkmalFoto(
                        raum_merkmal=checklist_item,
                        datei=photo,
                        content_type=verified_photo_content_type(photo),
                        dateigroesse=photo.size,
                        inhalt_hash_sha256=checksum,
                    ),
                    stored_photo_files,
                )
    except IntegrityError:
        messages.info(request, "Dieses Foto ist für den Prüfpunkt bereits gespeichert.")
    except (HandoverPhotoStorageError, DatabaseError) as error:
        logger.error("Protocol photo upload failed (%s).", type(error).__name__)
        messages.error(request, PHOTO_SAVE_ERROR)
    else:
        messages.success(request, "Die Fotos wurden am Prüfpunkt gespeichert.")
    return redirect(_photo_return_url(request, protocol, room, checklist_item))


@employee_required
def handover_protocol_checklist_item_photo_view(
    request: HttpRequest, protocol_id, room_id, item_id, photo_id
) -> FileResponse:
    photo = get_object_or_404(
        RaumMerkmalFoto.objects.select_related("raum_merkmal__raumprotokoll__protokoll"),
        pk=photo_id,
        raum_merkmal_id=item_id,
        raum_merkmal__raumprotokoll_id=room_id,
        raum_merkmal__raumprotokoll__protokoll_id=protocol_id,
    )
    content_type = _stored_photo_content_type(photo)
    response = FileResponse(photo.datei.open("rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@employee_required
@protocol_mutation
def handover_protocol_checklist_item_photo_delete(
    request: HttpRequest, protocol_id, room_id, item_id, photo_id
) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    protocol = get_object_or_404(Protokoll, pk=protocol_id)
    room = get_object_or_404(Raumprotokoll, pk=room_id, protokoll=protocol)
    checklist_item = get_object_or_404(RaumMerkmal, pk=item_id, raumprotokoll=room)
    photo = get_object_or_404(RaumMerkmalFoto, pk=photo_id, raum_merkmal=checklist_item)
    if protocol.status != ProtokollStatus.OPEN:
        messages.warning(request, "Bestätigte Protokolle können nicht mehr bearbeitet werden.")
        return redirect("wohnungsverwaltung:handover_protocol_detail", protocol_id=protocol.pk)

    _delete_checklist_photos([photo])
    messages.success(request, "Das Foto wurde vom Prüfpunkt entfernt.")
    return redirect(_photo_return_url(request, protocol, room, checklist_item))


def _delete_checklist_photos(photos) -> None:
    for photo in list(photos):
        delete_handover_photo(photo)


def _photo_return_url(
    request: HttpRequest,
    protocol: Protokoll,
    room: Raumprotokoll,
    checklist_item: RaumMerkmal,
) -> str:
    if request.POST.get("return_to") == "overview":
        detail_url = reverse("wohnungsverwaltung:handover_protocol_detail", args=[protocol.pk])
        return f"{detail_url}#pruefpunkt-{checklist_item.pk}"
    return reverse(
        "wohnungsverwaltung:handover_protocol_room_detail",
        kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
    )


def _move_in_reference_for_apartment(
    wohnung_id,
    before=None,
    person_id=None,
) -> Protokoll | None:
    if wohnung_id is None:
        return None
    references = Protokoll.objects.filter(
        wohnung_id=wohnung_id,
        protokoll_typ=ProtokollTyp.MOVE_IN,
        status=ProtokollStatus.SIGNED,
    )
    if person_id is not None:
        references = references.filter(person_id=person_id)
    if before is not None:
        historical_reference = _latest_move_in_reference(
            references.filter(uebergabe_zeitpunkt__lte=before)
        )
        if historical_reference is not None or person_id is None:
            return historical_reference
    return _latest_move_in_reference(references)


def _latest_move_in_reference(references) -> Protokoll | None:
    return (
        references.select_related("person")
        .prefetch_related(
            "raeume__raum_merkmale__merkmal",
            "raeume__raum_merkmale__fotos",
        )
        .order_by("-uebergabe_zeitpunkt", "-created_at")
        .first()
    )


def _move_in_reference_context(move_in_reference: Protokoll | None) -> dict[str, str]:
    if move_in_reference is None:
        return {
            "reference_handover_status_label": "",
            "reference_acceptance_status_label": "",
        }
    return {
        "reference_handover_status_label": HANDOVER_STATUS_LABELS[
            move_in_reference.uebergabe_status
        ],
        "reference_acceptance_status_label": ACCEPTANCE_STATUS_LABELS[
            move_in_reference.abnahme_status
        ],
    }


def _meter_comparison_rows(
    form: HandoverProtocolForm, move_in_reference: Protokoll | None
) -> list[dict[str, object]]:
    return [
        {
            "label": label,
            "number": (
                getattr(form.selected_wohnung, number_field)
                if form.selected_wohnung is not None
                else ""
            ),
            "old_reading": (
                getattr(move_in_reference, reading_field) if move_in_reference is not None else None
            ),
            "field": form[reading_field],
        }
        for reading_field, number_field, label in METER_READING_FIELDS
    ]


def _set_selected_person_initial(form: HandoverProtocolForm, person_id: str | UUID | None) -> None:
    """Keep the selected tenant visible after dynamic form fields reload."""
    if form.is_bound:
        return
    selected_person_id = _valid_person_id(person_id)
    if selected_person_id is None:
        return
    if form.fields["person"].queryset.filter(pk=selected_person_id).exists():
        form.initial["person"] = selected_person_id


def _attach_move_in_photo_references(protocol: Protokoll, rooms) -> Protokoll | None:
    """Attach photos from the latest signed move-in to matching move-out items."""
    if protocol.protokoll_typ != ProtokollTyp.MOVE_OUT:
        return None

    move_in_protocol = _move_in_reference_for_apartment(
        protocol.wohnung_id,
        before=protocol.uebergabe_zeitpunkt,
        person_id=protocol.person_id,
    )
    if move_in_protocol is None:
        return None

    move_in_rooms_by_id = {
        move_in_room.raum_id: move_in_room for move_in_room in move_in_protocol.raeume.all()
    }
    move_in_items_by_checkpoint = {}
    for move_in_room in move_in_protocol.raeume.all():
        for move_in_item in move_in_room.raum_merkmale.all():
            checkpoint_key = (move_in_room.raum_id, move_in_item.merkmal_id)
            move_in_items_by_checkpoint[checkpoint_key] = move_in_item

    for room in rooms:
        move_in_room = move_in_rooms_by_id.get(room.raum_id)
        current_feature_ids = {
            checklist_item.merkmal_id for checklist_item in room.raum_merkmale.all()
        }
        room.einzugspruefpunkte_ohne_match = (
            [
                move_in_item
                for move_in_item in move_in_room.raum_merkmale.all()
                if move_in_item.merkmal_id not in current_feature_ids
            ]
            if move_in_room
            else []
        )
        for checklist_item in room.raum_merkmale.all():
            checkpoint_key = (room.raum_id, checklist_item.merkmal_id)
            move_in_item = move_in_items_by_checkpoint.get(checkpoint_key)
            checklist_item.einzugspruefpunkt = move_in_item
            checklist_item.einzugsfotos = list(move_in_item.fotos.all()) if move_in_item else []
            checklist_item.einzugsprotokoll = move_in_protocol if move_in_item else None
    return move_in_protocol


@employee_required
@protocol_mutation
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


@employee_required
@protocol_mutation
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


def _representative_name(protocol, user):
    from .handover_export import employee_name

    if protocol.status == ProtokollStatus.OPEN:
        return employee_name(user) or protocol.vermieter_name
    signature = protocol.unterschriften.filter(rolle="mitarbeiter").first()
    return signature.name if signature else protocol.vermieter_name


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


def _save_inline_protocol_entries(
    protocol, room_formset, key_formset, stored_photo_files, *, removed_rooms=()
) -> None:
    removed_rooms = list(removed_rooms)
    removed_ids = {room.pk for room in removed_rooms}
    for room in removed_rooms:
        _delete_checklist_photos(RaumMerkmalFoto.objects.filter(raum_merkmal__raumprotokoll=room))
        room.delete()
    for room_form in room_formset.deleted_forms:
        item = room_form.cleaned_data.get("pruefpunkt")
        if item is not None and item.raumprotokoll_id not in removed_ids:
            _delete_checklist_photos(item.fotos.all())
            item.delete()
    for room_form in room_formset:
        source_room = room_form.cleaned_data.get("raumprotokoll")
        item = room_form.cleaned_data.get("pruefpunkt")
        if (source_room is not None and source_room.pk in removed_ids) or (
            item is not None and item.raumprotokoll_id in removed_ids
        ):
            continue
        if (
            room_form.cleaned_data
            and not room_form.cleaned_data.get("DELETE")
            and room_form.has_entry()
        ):
            room_form.save(protocol, stored_photo_files)

    for key_form in key_formset:
        if key_form.cleaned_data.get("DELETE"):
            key = key_form.cleaned_data.get("schluessel")
            if key is not None:
                key.delete()
            continue
        if not key_form.cleaned_data:
            continue
        key = key_form.save(commit=False)
        key.protokoll = protocol
        key.save()


def _protocol_room_initial(protocol):
    values = []
    for room in protocol.raeume.prefetch_related("raum_merkmale__merkmal").order_by("name", "pk"):
        items = list(room.raum_merkmale.all())
        if not items:
            values.append({"raum": room.raum_id, "raumprotokoll": room.pk})
        for item in items:
            value = item.wert if isinstance(item.wert, dict) else {}
            values.append(
                {
                    "raumprotokoll": room.pk,
                    "pruefpunkt": item.pk,
                    "raum": room.raum_id,
                    "bereich": item.merkmal.bereich,
                    "merkmal": item.merkmal_id,
                    "wert": value.get("text", ""),
                    "zusatzangaben": json.dumps(value.get("angaben", {}), ensure_ascii=False),
                }
            )
    return values


def _protocol_key_initial(protocol):
    fields = HandoverKeyForm._meta.fields
    return [
        {"schluessel": key.pk, **{field: getattr(key, field) for field in fields}}
        for key in protocol.protokoll_schluessel.order_by("raum_bezeichnung", "pk")
    ]


def _room_form_groups(room_formset, removed_rooms=()) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    removed_ids = set(removed_rooms)
    for room_form in room_formset:
        cleaned_data = getattr(room_form, "cleaned_data", {})
        room_name = cleaned_data.get("raum") or room_form["raum"].value() or ""
        room_protocol_id = str(room_form["raumprotokoll"].value() or "")
        if (
            not groups
            or groups[-1]["name"] != room_name
            or groups[-1]["room_protocol_id"] != room_protocol_id
        ):
            groups.append(
                {
                    "name": room_name,
                    "room_form": room_form,
                    "checklist_forms": [room_form],
                    "room_protocol_id": room_protocol_id,
                    "remove_room": room_protocol_id in removed_ids,
                }
            )
            continue
        groups[-1]["checklist_forms"].append(room_form)
    return groups


@employee_required
def wohnung_list(request: HttpRequest) -> HttpResponse:
    wohnungen = Wohnung.objects.order_by("etage", "wohnungsnummer")
    return render(request, "wohnungsverwaltung/wohnung_list.html", {"wohnungen": wohnungen})


@employee_required
def wohnung_create(request: HttpRequest) -> HttpResponse:
    return _wohnung_form(request, Wohnung(), "Wohnung anlegen")


@employee_required
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
            return redirect("verwaltung:wohnung_edit", wohnung_id=wohnung.pk)
    else:
        form = WohnungForm(instance=wohnung)
        schluessel_formset = SchluesselFormSet(instance=wohnung, prefix="schluessel")

    return render(
        request,
        "wohnungsverwaltung/wohnung_form.html",
        {
            "form": form,
            "raeume": wohnung.raeume.order_by("name") if wohnung.pk else (),
            "schluessel_formset": schluessel_formset,
            "title": title,
            "wohnung": wohnung,
        },
    )


@employee_required
def raum_create(request: HttpRequest, wohnung_id) -> HttpResponse:
    wohnung = get_object_or_404(Wohnung, pk=wohnung_id)
    return _raum_form(request, wohnung, Raum(wohnung=wohnung), "Raum anlegen")


@employee_required
def raum_edit(request: HttpRequest, wohnung_id, raum_id) -> HttpResponse:
    wohnung = get_object_or_404(Wohnung, pk=wohnung_id)
    raum = get_object_or_404(Raum, pk=raum_id, wohnung=wohnung)
    return _raum_form(request, wohnung, raum, "Raum bearbeiten")


def _raum_form(request: HttpRequest, wohnung: Wohnung, raum: Raum, title: str) -> HttpResponse:
    form = RaumForm(request.POST or None, instance=raum)
    if request.method == "POST" and form.is_valid():
        saved_room = form.save(commit=False)
        saved_room.wohnung = wohnung
        try:
            with transaction.atomic():
                saved_room.save()
        except IntegrityError:
            form.add_error("name", "Diese Raumbezeichnung gibt es in der Wohnung bereits.")
        else:
            messages.success(request, "Der Raum wurde gespeichert.")
            return redirect("verwaltung:wohnung_edit", wohnung_id=wohnung.pk)
    return render(
        request,
        "wohnungsverwaltung/raum_form.html",
        {"form": form, "wohnung": wohnung, "title": title},
    )


@employee_required
def raum_delete(request: HttpRequest, wohnung_id, raum_id) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    wohnung = get_object_or_404(Wohnung, pk=wohnung_id)
    raum = get_object_or_404(Raum, pk=raum_id, wohnung=wohnung)
    try:
        raum.delete()
    except ProtectedError:
        messages.error(request, "Der Raum wird bereits in einem Übergabeprotokoll verwendet.")
    else:
        messages.success(request, "Der Raum wurde gelöscht.")
    return redirect("verwaltung:wohnung_edit", wohnung_id=wohnung.pk)


@employee_required
def merkmal_list(request: HttpRequest) -> HttpResponse:
    merkmale = Merkmal.objects.order_by("bereich", "bezeichnung")
    return render(request, "wohnungsverwaltung/merkmal_list.html", {"merkmale": merkmale})


@employee_required
def merkmal_create(request: HttpRequest) -> HttpResponse:
    return _merkmal_form(request, Merkmal(), "Merkmalvorlage anlegen")


@employee_required
def merkmal_edit(request: HttpRequest, merkmal_id) -> HttpResponse:
    merkmal = get_object_or_404(Merkmal, pk=merkmal_id)
    return _merkmal_form(request, merkmal, "Merkmalvorlage bearbeiten")


def _merkmal_form(request: HttpRequest, merkmal: Merkmal, title: str) -> HttpResponse:
    if request.method == "POST":
        form = MerkmalForm(request.POST, instance=merkmal)
        option_formset = MerkmalOptionFormSet(request.POST, prefix="optionen")
        if form.is_valid() and option_formset.is_valid():
            saved_feature = form.save(commit=False)
            saved_feature.optionen = [
                option_form.cleaned_data["wert"].strip()
                for option_form in option_formset
                if option_form.cleaned_data
                and not option_form.cleaned_data.get("DELETE")
                and option_form.cleaned_data["wert"].strip()
            ]
            saved_feature.save()
            messages.success(request, "Die Merkmalvorlage wurde gespeichert.")
            return redirect("verwaltung:merkmal_edit", merkmal_id=saved_feature.pk)
    else:
        form = MerkmalForm(instance=merkmal)
        existing_options = merkmal.optionen if isinstance(merkmal.optionen, list) else []
        option_formset = MerkmalOptionFormSet(
            initial=[{"wert": option} for option in existing_options],
            prefix="optionen",
        )
    return render(
        request,
        "wohnungsverwaltung/merkmal_form.html",
        {"form": form, "option_formset": option_formset, "title": title},
    )


@employee_required
def stellplatz_list(request: HttpRequest) -> HttpResponse:
    stellplaetze = Stellplatz.objects.order_by("name").prefetch_related("zuordnungen__wohnung")
    return render(
        request,
        "wohnungsverwaltung/stellplatz_list.html",
        {"stellplaetze": stellplaetze},
    )


@employee_required
def stellplatz_create(request: HttpRequest) -> HttpResponse:
    return _stellplatz_form(request, Stellplatz(), "Stellplatz anlegen")


@employee_required
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
            try:
                with transaction.atomic():
                    if not stellplatz._state.adding:
                        get_object_or_404(Stellplatz.objects.select_for_update(), pk=stellplatz.pk)
                        # The relation may have changed while these forms were validated.
                        zuordnung = StellplatzZuordnung.objects.filter(
                            stellplatz=stellplatz
                        ).first()
                        if zuordnung is None:
                            zuordnung = StellplatzZuordnung(stellplatz=stellplatz)
                    stellplatz = form.save()
                    selected_unit = zuordnung_form.cleaned_data["wohnung"]
                    if selected_unit is None:
                        if not zuordnung._state.adding:
                            zuordnung.delete()
                    else:
                        zuordnung.stellplatz = stellplatz
                        zuordnung.wohnung = selected_unit
                        zuordnung.save()
            except IntegrityError:
                zuordnung_form.add_error(
                    "wohnung",
                    "Die Stellplatzzuordnung konnte nicht gespeichert werden. "
                    "Bitte prüfen Sie die aktuelle Zuordnung und versuchen Sie es erneut.",
                )
            else:
                messages.success(request, "Der Stellplatz und seine Zuordnung wurden gespeichert.")
                return redirect("verwaltung:stellplatz_edit", stellplatz_id=stellplatz.pk)
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


@user_management_required
def user_account_list(request: HttpRequest) -> HttpResponse:
    user_model = get_user_model()
    accounts = (
        user_model.objects.select_related("person_profile")
        .prefetch_related("groups", "user_permissions")
        .order_by("username")
    )
    return render(request, "wohnungsverwaltung/user_account_list.html", {"accounts": accounts})


@user_management_required
def user_account_create(request: HttpRequest) -> HttpResponse:
    form = UserAccountForm(request.POST or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = form.save()
        except (IntegrityError, ValidationError):
            form.add_error(
                None,
                "Das Konto konnte nicht gespeichert werden. Bitte prüfen Sie die Angaben.",
            )
        else:
            messages.success(request, "Das Benutzerkonto wurde angelegt.")
            return redirect("verwaltung:user_account_edit", user_id=account.pk)
    return render(
        request,
        "wohnungsverwaltung/user_account_form.html",
        {"form": form, "title": "Benutzerkonto anlegen", "submit_label": "Konto anlegen"},
    )


@user_management_required
def user_account_edit(request: HttpRequest, user_id: int) -> HttpResponse:
    account = get_object_or_404(get_user_model(), pk=user_id)
    form = UserAccountForm(request.POST or None, account=account, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except (IntegrityError, ValidationError):
            form.add_error(
                None,
                "Das Konto konnte nicht gespeichert werden. Bitte prüfen Sie die Angaben.",
            )
        else:
            messages.success(request, "Das Benutzerkonto wurde aktualisiert.")
            return redirect("verwaltung:user_account_edit", user_id=account.pk)
    return render(
        request,
        "wohnungsverwaltung/user_account_form.html",
        {
            "form": form,
            "account": account,
            "title": "Benutzerkonto bearbeiten",
            "submit_label": "Änderungen speichern",
        },
    )
