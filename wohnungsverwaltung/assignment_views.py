from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .access import employee_required
from .assignment_forms import PersonAssignmentForm, PersonSelectionForm
from .models import Person, Wohnung


@employee_required
@require_http_methods(["GET"])
def wohnung_personen(request, wohnung_id):
    wohnung = get_object_or_404(Wohnung, pk=wohnung_id)
    form = PersonSelectionForm(request.GET or None)
    if form.is_bound and form.is_valid():
        return redirect(
            "verwaltung:person_assignment",
            wohnung_id=wohnung.pk,
            person_id=form.cleaned_data["person"].pk,
        )
    return render(
        request,
        "wohnungsverwaltung/wohnung_personen.html",
        {
            "wohnung": wohnung,
            "form": form,
            "personen": wohnung.personen.select_related("user").order_by("nachname", "vorname"),
        },
    )


@employee_required
@require_http_methods(["GET", "POST"])
def person_assignment(request, wohnung_id, person_id):
    wohnung = get_object_or_404(Wohnung, pk=wohnung_id)
    # Serialize concurrent assignments and recheck the current relationship under the lock.
    with transaction.atomic():
        person = get_object_or_404(Person.objects.select_for_update(), pk=person_id)
        form = PersonAssignmentForm(
            request.POST if request.method == "POST" else None,
            person=person,
            wohnung=wohnung,
        )
        if request.method == "POST" and form.is_valid():
            person.wohnung = wohnung
            person.save(update_fields=["wohnung", "updated_at"])
            messages.success(
                request, "Die Person wurde der Wohnung zugeordnet. Rollen bleiben unverändert."
            )
            return redirect("verwaltung:wohnung_personen", wohnung_id=wohnung.pk)
    return render(
        request,
        "wohnungsverwaltung/person_assignment.html",
        {
            "wohnung": wohnung,
            "person": person,
            "form": form,
            "protocols": person.protokolle.select_related("wohnung").order_by(
                "-uebergabe_zeitpunkt"
            ),
        },
    )
