from django.urls import path

from . import export_views, views

app_name = "wohnungsverwaltung"

urlpatterns = [
    path("meine/", export_views.handover_protocol_mine, name="handover_protocol_mine"),
    path(
        "<uuid:protocol_id>/abschluss/",
        export_views.handover_protocol_finalize,
        name="handover_protocol_finalize",
    ),
    path(
        "<uuid:protocol_id>/pdf/", export_views.handover_protocol_pdf, name="handover_protocol_pdf"
    ),
    path(
        "<uuid:protocol_id>/pdf/erstellen/",
        export_views.handover_protocol_pdf_create,
        name="handover_protocol_pdf_create",
    ),
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
        export_views.handover_protocol_confirm,
        name="handover_protocol_confirm",
    ),
    path("<uuid:protocol_id>/", views.handover_protocol_detail, name="handover_protocol_detail"),
    path(
        "<uuid:protocol_id>/bearbeiten/",
        views.handover_protocol_edit,
        name="handover_protocol_edit",
    ),
]
