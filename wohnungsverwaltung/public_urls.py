from django.urls import path

from . import views

app_name = "wohnungsverwaltung_public"

urlpatterns = [
    path("", views.apartment_search, name="apartment_search"),
]
