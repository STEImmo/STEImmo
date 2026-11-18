from django.conf import settings

from wohnungsverwaltung.access import SYSTEM_SETTINGS_SESSION_KEY, has_system_settings_grant


def demo_mode(request):
    return {"demo_mode": settings.DEMO_MODE}


def system_settings_access(request):
    user = getattr(request, "user", None)
    return {
        "can_open_system_settings": (
            user is not None
            and user.is_authenticated
            and user.is_active
            and request.session.get(SYSTEM_SETTINGS_SESSION_KEY) == user.pk
            and has_system_settings_grant(user)
        )
    }
