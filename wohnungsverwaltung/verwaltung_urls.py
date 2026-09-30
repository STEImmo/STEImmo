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
    path("stellplaetze/", views.stellplatz_list, name="stellplatz_list"),
    path("stellplaetze/neu/", views.stellplatz_create, name="stellplatz_create"),
    path("stellplaetze/<uuid:stellplatz_id>/", views.stellplatz_edit, name="stellplatz_edit"),
]
