from django.urls import path

from . import views

app_name = "wohnungsverwaltung_public"

urlpatterns = [
    path("gebaeude/", views.building_view, name="building_view"),
    path("etagen/<int:floor_number>/", views.floor_view, name="floor_view"),
    path("fotos/<uuid:photo_id>/", views.apartment_photo, name="apartment_photo"),
    path(
        "<uuid:unit_id>/",
        views.apartment_detail_placeholder,
        name="apartment_detail_placeholder",
    ),
    path("", views.apartment_search, name="apartment_search"),
]
