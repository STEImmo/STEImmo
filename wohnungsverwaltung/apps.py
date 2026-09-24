from django.apps import AppConfig


class WohnungsverwaltungConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wohnungsverwaltung"
    # Keep the original label so existing databases retain their migration history.
    label = "immobilien"
