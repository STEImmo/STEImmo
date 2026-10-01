from django.apps import AppConfig


class WohnungsverwaltungConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wohnungsverwaltung"
    # Keep the original label so existing databases retain their migration history.
    label = "immobilien"

    def ready(self) -> None:
        from django.db.models.signals import post_migrate

        from .access import ensure_access_roles

        post_migrate.connect(ensure_access_roles, sender=self)
