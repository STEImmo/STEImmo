from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("verwaltung/", include("wohnungsverwaltung.verwaltung_urls")),
    path("", include("core.urls")),
    path("uebergaben/", include("wohnungsverwaltung.urls")),
]
