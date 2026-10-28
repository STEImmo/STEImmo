from django.contrib.auth.views import LogoutView
from django.urls import include, path
from django.views.generic import TemplateView

from . import account_views, contact, views

urlpatterns = [
    path("", views.home, name="home"),
    path("kontakt/", contact.contact, name="contact"),
    path("impressum/", TemplateView.as_view(template_name="core/imprint.html"), name="imprint"),
    path("datenschutz/", TemplateView.as_view(template_name="core/privacy.html"), name="privacy"),
    path(
        "bildnachweise/",
        TemplateView.as_view(template_name="core/image_credits.html"),
        name="image_credits",
    ),
    path("health/", views.health, name="health"),
    path(
        "accounts/profil/",
        include(
            (
                [
                    path("", views.personal_profile, name="detail"),
                    path("bearbeiten/", views.personal_profile_edit, name="edit"),
                    path("passwort/", account_views.password_change, name="password"),
                    path("email/", account_views.email_change, name="email"),
                    path("email/bestaetigen/", account_views.email_confirm, name="email_confirm"),
                    path("email/abbrechen/", account_views.email_cancel, name="email_cancel"),
                ],
                "profile",
            ),
            namespace="profile",
        ),
    ),
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
