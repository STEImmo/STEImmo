"""Fachliche Rollen und wiederverwendbarer Zugriffsschutz für STEImmo."""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import redirect_to_login
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

APP_LABEL = "immobilien"

APPLICANT_ACCESS_PERMISSION = f"{APP_LABEL}.access_applicant_area"
TENANT_ACCESS_PERMISSION = f"{APP_LABEL}.access_tenant_area"
EMPLOYEE_ACCESS_PERMISSION = f"{APP_LABEL}.access_employee_area"
USER_MANAGEMENT_PERMISSION = f"{APP_LABEL}.manage_user_accounts"
SYSTEM_SETTINGS_CODENAME = "manage_system_settings"
SYSTEM_SETTINGS_SESSION_KEY = "system_settings_verified_user"

ACCESS_PERMISSION_CODENAMES = (
    "access_applicant_area",
    "access_tenant_area",
    "access_employee_area",
    "manage_user_accounts",
)

ROLE_APPLICANT = "Bewerber"
ROLE_TENANT = "Mieter"
ROLE_EMPLOYEE = "Mitarbeiter"
ROLE_USER_MANAGEMENT = "Benutzerverwaltung"
ROLE_NAMES = (ROLE_APPLICANT, ROLE_TENANT, ROLE_EMPLOYEE, ROLE_USER_MANAGEMENT)

ROLE_PERMISSION_CODENAMES = {
    ROLE_APPLICANT: ("access_applicant_area",),
    ROLE_TENANT: ("access_tenant_area",),
    ROLE_EMPLOYEE: ("access_employee_area",),
    ROLE_USER_MANAGEMENT: ("access_employee_area", "manage_user_accounts"),
}

PERMISSION_NAMES = {
    "access_applicant_area": "Kann auf den Bewerberbereich zugreifen",
    "access_tenant_area": "Kann auf den vorbereiteten Mieterbereich zugreifen",
    "access_employee_area": "Kann auf den Mitarbeiterbereich zugreifen",
    "manage_user_accounts": "Kann Konten und Zugriffsrechte verwalten",
    SYSTEM_SETTINGS_CODENAME: "Kann Systemeinstellungen verwalten",
}

P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponse)


def _access_required(permission: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Require a login first and then return 403 for missing business permissions."""

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        protected_view = permission_required(permission, raise_exception=True)(view)
        return login_required(protected_view)

    return decorator


applicant_required = _access_required(APPLICANT_ACCESS_PERMISSION)
tenant_required = _access_required(TENANT_ACCESS_PERMISSION)


def handover_reader_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not any(
            request.user.has_perm(p) for p in (EMPLOYEE_ACCESS_PERMISSION, TENANT_ACCESS_PERMISSION)
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


employee_required = _access_required(EMPLOYEE_ACCESS_PERMISSION)
user_management_required = _access_required(USER_MANAGEMENT_PERMISSION)


def system_settings_permission():
    return Permission.objects.get(
        content_type__app_label=APP_LABEL,
        content_type__model="person",
        codename=SYSTEM_SETTINGS_CODENAME,
    )


def has_system_settings_grant(user) -> bool:
    return user.user_permissions.filter(
        content_type__app_label=APP_LABEL,
        content_type__model="person",
        codename=SYSTEM_SETTINGS_CODENAME,
    ).exists()


def requires_email_mfa(user) -> bool:
    return (
        user.has_perm(EMPLOYEE_ACCESS_PERMISSION)
        or user.has_perm(USER_MANAGEMENT_PERMISSION)
        or has_system_settings_grant(user)
    )


def system_settings_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not has_system_settings_grant(request.user):
            raise PermissionDenied
        if request.session.get(SYSTEM_SETTINGS_SESSION_KEY) != request.user.pk:
            return redirect_to_login(request.get_full_path())
        return view(request, *args, **kwargs)

    return wrapped


def lock_account_administration():
    # Keep authentication's foreign-key references to the stable role available.
    Group.objects.select_for_update(no_key=True).get(name=ROLE_USER_MANAGEMENT)


def revoke_account_sessions(account):
    # Authentication saves sessions under the same account-row lock.
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(account.pk):
            session.delete()


def login_identifier_filter(user_model, identifier):
    lookup = user_model.USERNAME_FIELD
    identifiers = Q(**{lookup: identifier})
    if "@" in identifier:
        lookup += "__iexact"
        # Keep the raw legacy spelling and Python's Unicode lowercase form.
        identifiers |= Q(**{lookup: identifier}) | Q(**{lookup: identifier.lower()})
    return identifiers


def has_permission(request: HttpRequest, permission: str) -> bool:
    """Return whether the current request user has a project permission."""

    return request.user.is_authenticated and request.user.has_perm(permission)


def ensure_access_roles(**kwargs) -> None:
    """Create the fixed access permissions and groups after migrations or a test flush."""

    content_type, _created = ContentType.objects.get_or_create(app_label=APP_LABEL, model="person")
    permissions = {}
    for codename in PERMISSION_NAMES:
        permission, created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": PERMISSION_NAMES[codename]},
        )
        if not created and permission.name != PERMISSION_NAMES[codename]:
            permission.name = PERMISSION_NAMES[codename]
            permission.save(update_fields=["name"])
        permissions[codename] = permission
    for role_name, codenames in ROLE_PERMISSION_CODENAMES.items():
        group, _created = Group.objects.get_or_create(name=role_name)
        group.permissions.set([permissions[codename] for codename in codenames])
