from django.db import connection
from django.db.utils import OperationalError
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render


def home(request: HttpRequest):
    return render(request, "core/home.html")


def health(request: HttpRequest) -> JsonResponse:
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"service": "steimmo", "status": "unhealthy"}, status=503)
    return JsonResponse({"service": "steimmo", "status": "ok"})
