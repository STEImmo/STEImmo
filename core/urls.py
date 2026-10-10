from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    # The real public building route takes precedence once issue #16 is merged.
    path(
        "wohnungen/gebaeude/",
        TemplateView.as_view(template_name="core/building_pending.html"),
        name="building_view_pending",
    ),
    path("impressum/", TemplateView.as_view(template_name="core/imprint.html"), name="imprint"),
    path("datenschutz/", TemplateView.as_view(template_name="core/privacy.html"), name="privacy"),
    path("health/", views.health, name="health"),
    path(
        "accounts/login/",
        views.RoleAwareLoginView.as_view(),
        name="login",
    ),
    path("accounts/registrieren/", views.register, name="register"),
    path("accounts/registrieren/bestaetigen/", views.register_verify, name="register_verify"),
    path(
        "accounts/registrieren/code-erneut-senden/",
        views.resend_registration_code,
        name="resend_registration_code",
    ),
    path(
        "accounts/mitarbeiter-mfa/",
        views.employee_mfa_verify,
        name="employee_mfa_verify",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
]
