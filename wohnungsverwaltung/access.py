"""Fachliche Rollen und wiederverwendbarer Zugriffsschutz für STEImmo."""

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest, HttpResponse

APP_LABEL = "immobilien"

APPLICANT_ACCESS_PERMISSION = f"{APP_LABEL}.access_applicant_area"
TENANT_ACCESS_PERMISSION = f"{APP_LABEL}.access_tenant_area"
EMPLOYEE_ACCESS_PERMISSION = f"{APP_LABEL}.access_employee_area"
USER_MANAGEMENT_PERMISSION = f"{APP_LABEL}.manage_user_accounts"

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
employee_required = _access_required(EMPLOYEE_ACCESS_PERMISSION)
user_management_required = _access_required(USER_MANAGEMENT_PERMISSION)


def has_permission(request: HttpRequest, permission: str) -> bool:
    """Return whether the current request user has a project permission."""

    return request.user.is_authenticated and request.user.has_perm(permission)


def ensure_access_roles(**kwargs) -> None:
    """Create the fixed access permissions and groups after migrations or a test flush."""

    content_type, _created = ContentType.objects.get_or_create(app_label=APP_LABEL, model="person")
    permissions = {}
    for codename in ACCESS_PERMISSION_CODENAMES:
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
