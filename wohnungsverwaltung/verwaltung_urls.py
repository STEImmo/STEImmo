from django.urls import path

from . import views

app_name = "verwaltung"

urlpatterns = [
    path("benutzer/", views.user_account_list, name="user_account_list"),
    path("benutzer/neu/", views.user_account_create, name="user_account_create"),
    path("benutzer/<int:user_id>/", views.user_account_edit, name="user_account_edit"),
    path("wohnungen/", views.wohnung_list, name="wohnung_list"),
    path("wohnungen/neu/", views.wohnung_create, name="wohnung_create"),
    path("wohnungen/<uuid:wohnung_id>/", views.wohnung_edit, name="wohnung_edit"),
    path("wohnungen/<uuid:wohnung_id>/raeume/neu/", views.raum_create, name="raum_create"),
    path("wohnungen/<uuid:wohnung_id>/raeume/<uuid:raum_id>/", views.raum_edit, name="raum_edit"),
    path(
        "wohnungen/<uuid:wohnung_id>/raeume/<uuid:raum_id>/loeschen/",
        views.raum_delete,
        name="raum_delete",
    ),
    path("merkmale/", views.merkmal_list, name="merkmal_list"),
    path("merkmale/neu/", views.merkmal_create, name="merkmal_create"),
    path("merkmale/<uuid:merkmal_id>/", views.merkmal_edit, name="merkmal_edit"),
    path("stellplaetze/", views.stellplatz_list, name="stellplatz_list"),
    path("stellplaetze/neu/", views.stellplatz_create, name="stellplatz_create"),
    path("stellplaetze/<uuid:stellplatz_id>/", views.stellplatz_edit, name="stellplatz_edit"),
]
