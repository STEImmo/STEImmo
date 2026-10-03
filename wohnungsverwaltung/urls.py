from django.urls import path

from . import views

app_name = "wohnungsverwaltung"

urlpatterns = [
    path("bewerbung/meine/", views.pre_application_list, name="pre_application_list"),
    path("bewerbung/neu/", views.pre_application_create, name="pre_application_create"),
    path(
        "bewerbung/neu/<uuid:unit_id>/",
        views.pre_application_create,
        name="pre_application_create_for_unit",
    ),
    path(
        "bewerbung/vorschau/",
        views.pre_application_preview,
        name="pre_application_preview",
    ),
    path(
        "bewerbung/<uuid:application_id>/main/",
        views.main_application_status,
        name="main_application_status",
    ),
    path(
        "bewerbung/<uuid:application_id>/zurueckziehen/",
        views.application_withdraw,
        name="application_withdraw",
    ),
    path("", views.handover_protocol_list, name="handover_protocol_list"),
    path("neu/", views.handover_protocol_create, name="handover_protocol_create"),
    path(
        "entwuerfe/speichern/",
        views.handover_protocol_draft_save,
        name="handover_protocol_draft_save",
    ),
    path(
        "entwuerfe/<uuid:draft_id>/loeschen/",
        views.handover_protocol_draft_delete,
        name="handover_protocol_draft_delete",
    ),
    path(
        "<uuid:protocol_id>/raeume/neu/",
        views.handover_protocol_room_create,
        name="handover_protocol_room_create",
    ),
    path(
        "<uuid:protocol_id>/raeume/<uuid:room_id>/loeschen/",
        views.handover_protocol_room_delete,
        name="handover_protocol_room_delete",
    ),
    path(
        "<uuid:protocol_id>/raeume/<uuid:room_id>/pruefpunkte/<uuid:item_id>/loeschen/",
        views.handover_protocol_checklist_item_delete,
        name="handover_protocol_checklist_item_delete",
    ),
    path(
        "<uuid:protocol_id>/raeume/<uuid:room_id>/pruefpunkte/<uuid:item_id>/fotos/",
        views.handover_protocol_checklist_item_photo_upload,
        name="handover_protocol_checklist_item_photo_upload",
    ),
    path(
        "<uuid:protocol_id>/raeume/<uuid:room_id>/pruefpunkte/<uuid:item_id>/fotos/<uuid:photo_id>/",
        views.handover_protocol_checklist_item_photo_view,
        name="handover_protocol_checklist_item_photo_view",
    ),
    path(
        "<uuid:protocol_id>/raeume/<uuid:room_id>/pruefpunkte/<uuid:item_id>/fotos/<uuid:photo_id>/loeschen/",
        views.handover_protocol_checklist_item_photo_delete,
        name="handover_protocol_checklist_item_photo_delete",
    ),
    path(
        "<uuid:protocol_id>/raeume/<uuid:room_id>/",
        views.handover_protocol_room_detail,
        name="handover_protocol_room_detail",
    ),
    path(
        "<uuid:protocol_id>/schluessel/neu/",
        views.handover_protocol_key_create,
        name="handover_protocol_key_create",
    ),
    path(
        "<uuid:protocol_id>/schluessel/<uuid:key_id>/loeschen/",
        views.handover_protocol_key_delete,
        name="handover_protocol_key_delete",
    ),
    path(
        "<uuid:protocol_id>/bestaetigen/",
        views.handover_protocol_confirm,
        name="handover_protocol_confirm",
    ),
    path("<uuid:protocol_id>/", views.handover_protocol_detail, name="handover_protocol_detail"),
    path(
        "<uuid:protocol_id>/bearbeiten/",
        views.handover_protocol_edit,
        name="handover_protocol_edit",
    ),
]
