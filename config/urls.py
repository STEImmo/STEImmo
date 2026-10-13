from django.urls import include, path

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"

urlpatterns = [
    path(
        "wohnungen/",
        include("wohnungsverwaltung.public_urls"),
    ),
    path("verwaltung/", include("wohnungsverwaltung.verwaltung_urls")),
    path("", include("core.urls")),
    path("uebergaben/", include("wohnungsverwaltung.urls")),
]
