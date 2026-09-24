from django.urls import path

from . import views

app_name = "wohnungsverwaltung"

urlpatterns = [
    path("", views.handover_protocol_list, name="handover_protocol_list"),
    path("neu/", views.handover_protocol_create, name="handover_protocol_create"),
    path("<uuid:protocol_id>/", views.handover_protocol_detail, name="handover_protocol_detail"),
    path(
        "<uuid:protocol_id>/bearbeiten/",
        views.handover_protocol_edit,
        name="handover_protocol_edit",
    ),
]
