"""Serialize all existing protocol mutations with finalization."""

from functools import wraps

from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Protokoll


def protocol_mutation(view):
    @wraps(view)
    def wrapped(request, protocol_id, *args, **kwargs):
        if request.method != "POST":
            return view(request, protocol_id, *args, **kwargs)
        with transaction.atomic():
            get_object_or_404(Protokoll.objects.select_for_update(), pk=protocol_id)
            return view(request, protocol_id, *args, **kwargs)

    return wrapped
