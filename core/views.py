from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, connection
from django.db.utils import OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from wohnungsverwaltung.access import APPLICANT_ACCESS_PERMISSION, EMPLOYEE_ACCESS_PERMISSION
from wohnungsverwaltung.forms import ACCOUNT_CREATION_ERROR, RegistrationForm


def home(request: HttpRequest):
    return render(request, "core/home.html")


def health(request: HttpRequest) -> JsonResponse:
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"service": "steimmo", "status": "unhealthy"}, status=503)
    return JsonResponse({"service": "steimmo", "status": "ok"})


class RoleAwareLoginView(LoginView):
    template_name = "registration/login.html"

    def get_default_redirect_url(self) -> str:
        if self.request.user.has_perm(EMPLOYEE_ACCESS_PERMISSION):
            return reverse("verwaltung:wohnung_list")
        if self.request.user.has_perm(APPLICANT_ACCESS_PERMISSION):
            return reverse("wohnungsverwaltung:pre_application_list")
        return reverse("home")


def register(request: HttpRequest) -> HttpResponse:
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error("email", ACCOUNT_CREATION_ERROR)
        else:
            messages.success(request, "Ihr Bewerberkonto wurde angelegt. Bitte melden Sie sich an.")
            return redirect("login")
    return render(request, "registration/register.html", {"form": form})
