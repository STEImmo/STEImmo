from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
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
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
]
