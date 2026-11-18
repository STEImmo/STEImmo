import unicodedata

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import identify_hasher
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from .access import (
    SYSTEM_SETTINGS_SESSION_KEY,
    has_system_settings_grant,
    lock_account_administration,
    login_identifier_filter,
    revoke_account_sessions,
    system_settings_permission,
    system_settings_required,
)
from .models import EmployeeLoginVerification, PendingEmailChange


class SettingsAccessForm(forms.Form):
    username = forms.CharField(
        label="Anmeldename",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "uk-input"}),
    )
    action = forms.ChoiceField(choices=(("grant", "Erteilen"), ("revoke", "Entziehen")))


def _can_sign_in(account):
    if not account.is_active:
        return False
    try:
        identify_hasher(account.password)
        validate_email(account.email)
    except (ValueError, ValidationError):
        return False
    user_model = get_user_model()
    identifier = unicodedata.normalize("NFKC", account.get_username().strip())
    if not identifier:
        return False
    return list(
        user_model.objects.filter(login_identifier_filter(user_model, identifier)).values_list(
            "pk", flat=True
        )[:2]
    ) == [account.pk]


def _authorize_change(request):
    actor = (
        get_user_model()
        .objects.select_for_update()
        .filter(pk=request.user.pk, is_active=True)
        .first()
    )
    session_key = request.session.session_key
    session = (
        Session.objects.select_for_update()
        .filter(session_key=session_key, expire_date__gt=timezone.now())
        .first()
    )
    session_data = session.get_decoded() if session is not None else {}
    if (
        actor is None
        or not has_system_settings_grant(actor)
        or session_data.get("_auth_user_id") != str(actor.pk)
        or session_data.get(SYSTEM_SETTINGS_SESSION_KEY) != actor.pk
        or any(
            getattr(actor, field) != getattr(request.user, field)
            for field in ("password", "username", "email")
        )
    ):
        raise PermissionDenied


@transaction.atomic
def change_system_settings_access(username, *, grant, request=None):
    lock_account_administration()
    if request is not None:
        _authorize_change(request)

    permission = system_settings_permission()
    users = get_user_model().objects
    account = users.select_for_update().filter(username=username).first()
    if account is None:
        raise ValidationError("Für diesen Anmeldenamen wurde kein Konto gefunden.")

    current_grant = account.user_permissions.filter(pk=permission.pk).exists()
    if grant == current_grant:
        return account

    if grant:
        if not _can_sign_in(account):
            raise ValidationError(
                "Das Konto braucht eine eindeutige Anmeldung, ein verwendbares Passwort "
                "und eine gültige E-Mail-Adresse."
            )
        account.user_permissions.add(permission)
    else:
        other_admins = users.filter(is_active=True, user_permissions=permission).exclude(
            pk=account.pk
        )
        if not any(_can_sign_in(other) for other in other_admins):
            raise ValidationError(
                "Es muss mindestens ein funktionsfähiges berechtigtes Konto bleiben."
            )
        account.user_permissions.remove(permission)

    EmployeeLoginVerification.objects.filter(user=account).delete()
    PendingEmailChange.objects.filter(user=account).delete()
    revoke_account_sessions(account)
    return account


def _render_settings(request, form, status=200):
    admins = (
        get_user_model()
        .objects.filter(user_permissions=system_settings_permission())
        .order_by("username")
    )
    return render(
        request,
        "wohnungsverwaltung/system_settings.html",
        {"form": form, "admins": admins},
        status=status,
    )


@never_cache
@system_settings_required
@require_safe
def system_settings(request):
    return _render_settings(request, SettingsAccessForm())


@never_cache
@system_settings_required
@require_POST
def system_settings_access(request):
    form = SettingsAccessForm(request.POST)
    if form.is_valid():
        grant = form.cleaned_data["action"] == "grant"
        try:
            account = change_system_settings_access(
                form.cleaned_data["username"], grant=grant, request=request
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            if not grant and account.pk == request.user.pk:
                logout(request)
                messages.info(request, "Ihr Zugriff auf die Systemeinstellungen wurde entzogen.")
                return redirect("login")
            messages.success(request, "Die Zugriffsrechte wurden gespeichert.")
            return redirect("verwaltung:system_settings")
    return _render_settings(request, form, status=400)
