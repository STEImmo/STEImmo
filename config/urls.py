from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("verwaltung/", include("wohnungsverwaltung.urls")),
    path("", include("core.urls")),
]
