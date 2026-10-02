from django.urls import path

from . import views

app_name = "wohnungsverwaltung_public"

urlpatterns = [
    path(
        "<uuid:unit_id>/",
        views.apartment_detail_placeholder,
        name="apartment_detail_placeholder",
    ),
    path("", views.apartment_search, name="apartment_search"),
]
