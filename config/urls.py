from django.urls import include, path

urlpatterns = [
    path(
        "wohnungen/",
        include("wohnungsverwaltung.public_urls"),
    ),
    path("verwaltung/", include("wohnungsverwaltung.verwaltung_urls")),
    path("", include("core.urls")),
    path("uebergaben/", include("wohnungsverwaltung.urls")),
]
