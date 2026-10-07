import json
import unicodedata
import warnings
from uuid import UUID

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.files.storage import Storage
from django.db import transaction
from django.db.models import Q
from django.forms.formsets import BaseFormSet
from django.forms.models import inlineformset_factory
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError

from .access import (
    ACCESS_PERMISSION_CODENAMES,
    APP_LABEL,
    EMPLOYEE_ACCESS_PERMISSION,
    ROLE_NAMES,
    ROLE_USER_MANAGEMENT,
    USER_MANAGEMENT_PERMISSION,
)
from .models import (
    AbnahmeStatus,
    ApplicationProof,
    ApplicationProofCategory,
    Bewerbung,
    BewerbungStatus,
    EmployeeLoginVerification,
    Merkmal,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollTyp,
    Raum,
    RaumMerkmal,
    RaumMerkmalFoto,
    Raumprotokoll,
    RegistrationVerification,
    Schluessel,
    Stellplatz,
    StellplatzZuordnung,
    UebergabeStatus,
    Wohnung,
    WohnungStatus,
    calculate_photo_checksum,
)

HANDOVER_TYPE_LABELS = {
    ProtokollTyp.MOVE_IN: "Einzug",
    ProtokollTyp.MOVE_OUT: "Auszug",
}

HANDOVER_STATUS_LABELS = {
    UebergabeStatus.RENOVATED: "Renoviert",
    UebergabeStatus.UNRENOVATED: "Unrenoviert",
}

ACCEPTANCE_STATUS_LABELS = {
    AbnahmeStatus.ACCEPTED: "Abgenommen",
    AbnahmeStatus.ACCEPTED_WITH_RESERVATION: "Mit Vorbehalt abgenommen",
    AbnahmeStatus.NOT_FULLY_ACCEPTED: "Nicht vollständig abgenommen",
}

METER_NUMBER_FIELDS = (
    ("zaehlernummer_wasser_kalt", "Kaltwasser"),
    ("zaehlernummer_wasser_warm", "Warmwasser"),
    ("zaehlernummer_heizung", "Heizung"),
    ("zaehlernummer_strom", "Strom"),
)

METER_READING_FIELDS = (
    ("zaehlerstand_wasser_kalt", "zaehlernummer_wasser_kalt", "Kaltwasser"),
    ("zaehlerstand_wasser_warm", "zaehlernummer_wasser_warm", "Warmwasser"),
    ("zaehlerstand_heizung", "zaehlernummer_heizung", "Heizung"),
    ("zaehlerstand_strom", "zaehlernummer_strom", "Strom"),
)

ACCOUNT_CREATION_ERROR = "Mit diesen Angaben kann kein Konto erstellt werden."
PHOTO_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def photo_content_type_from_format(image_format: str) -> str | None:
    """Return the allowed MIME type for a Pillow-verified image format."""

    return PHOTO_CONTENT_TYPES.get(image_format)


def verified_photo_content_type(photo) -> str:
    """Return the MIME type derived from an ImageField-validated upload."""

    image_format = getattr(getattr(photo, "image", None), "format", "")
    content_type = photo_content_type_from_format(image_format)
    if content_type is None:
        raise ValidationError("Erlaubt sind nur JPEG-, PNG- und WebP-Bilder.")
    return content_type


class RegistrationForm(forms.Form):
    vorname = forms.CharField(
        label="Vorname",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "uk-input", "autocomplete": "given-name"}),
    )
    nachname = forms.CharField(
        label="Nachname",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "uk-input", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        label="E-Mail-Adresse",
        max_length=255,
        widget=forms.EmailInput(attrs={"class": "uk-input", "autocomplete": "username"}),
    )
    password1 = forms.CharField(
        label="Passwort",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "uk-input", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Passwort wiederholen",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "uk-input", "autocomplete": "new-password"}),
    )

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        if (
            Person.objects.filter(email__iexact=email).exists()
            or user_model.objects.filter(
                Q(username__iexact=email) | Q(email__iexact=email)
            ).exists()
        ):
            raise forms.ValidationError(ACCOUNT_CREATION_ERROR)
        return email

    def clean(self) -> dict:
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Die Passwörter stimmen nicht überein.")
            return cleaned_data
        if password1 and cleaned_data.get("email"):
            user = get_user_model()(
                username=cleaned_data["email"],
                email=cleaned_data["email"],
                first_name=cleaned_data.get("vorname", ""),
                last_name=cleaned_data.get("nachname", ""),
            )
            try:
                validate_password(password1, user)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned_data

    def save(self):
        user_model = get_user_model()
        with transaction.atomic():
            user = user_model(
                username=self.cleaned_data["email"],
                email=self.cleaned_data["email"],
                first_name=self.cleaned_data["vorname"],
                last_name=self.cleaned_data["nachname"],
                is_active=False,
            )
            user.set_password(self.cleaned_data["password1"])
            user.save()
            Person.objects.create(
                user=user,
                vorname=self.cleaned_data["vorname"],
                nachname=self.cleaned_data["nachname"],
                email=self.cleaned_data["email"],
            )
            user.groups.add(Group.objects.get(name="Bewerber"))
        return user


class RegistrationVerificationForm(forms.Form):
    email = forms.EmailField(
        label="E-Mail-Adresse",
        max_length=255,
        widget=forms.EmailInput(attrs={"class": "uk-input", "autocomplete": "username"}),
    )
    code = forms.CharField(
        label="Bestätigungscode",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "uk-input",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
            }
        ),
    )

    def clean_code(self) -> str:
        code = self.cleaned_data["code"].strip()
        if not code.isascii() or not code.isdigit():
            raise forms.ValidationError("Bitte geben Sie den sechsstelligen Code ein.")
        return code


class ResendRegistrationCodeForm(forms.Form):
    email = forms.EmailField(
        label="E-Mail-Adresse",
        max_length=255,
        widget=forms.EmailInput(attrs={"class": "uk-input", "autocomplete": "username"}),
    )


class EmployeeMfaCodeForm(forms.Form):
    code = forms.CharField(
        label="Einmalcode",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "uk-input",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
            }
        ),
    )

    def clean_code(self) -> str:
        code = self.cleaned_data["code"].strip()
        if not code.isascii() or not code.isdigit():
            raise forms.ValidationError("Bitte geben Sie den sechsstelligen Code ein.")
        return code


class UserAccountForm(forms.Form):
    person = forms.ModelChoiceField(
        label="Bestehende Person",
        queryset=Person.objects.none(),
        required=False,
        empty_label="Neue Person erfassen",
        widget=forms.Select(attrs={"class": "uk-select"}),
    )
    vorname = forms.CharField(
        label="Neue Person: Vorname",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "uk-input", "autocomplete": "given-name"}),
    )
    nachname = forms.CharField(
        label="Neue Person: Nachname",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "uk-input", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        label="Neue Person: E-Mail-Adresse",
        max_length=255,
        required=False,
        widget=forms.EmailInput(attrs={"class": "uk-input", "autocomplete": "username"}),
    )
    roles = forms.ModelMultipleChoiceField(
        label="Rollen",
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    direct_permissions = forms.ModelMultipleChoiceField(
        label="Zusätzliche Seitenrechte",
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    is_active = forms.BooleanField(
        label="Konto ist aktiv",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )
    password1 = forms.CharField(
        label="Neues Passwort",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "uk-input", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Neues Passwort wiederholen",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "uk-input", "autocomplete": "new-password"}),
    )

    def __init__(self, *args, account=None, actor=None, **kwargs) -> None:
        self.account = account
        self.actor = actor
        super().__init__(*args, **kwargs)
        current_person = getattr(account, "person_profile", None) if account is not None else None
        person_filter = Q(user__isnull=True)
        if current_person is not None:
            person_filter |= Q(pk=current_person.pk)
        self.fields["person"].queryset = Person.objects.filter(person_filter).order_by(
            "nachname", "vorname"
        )
        self.fields["roles"].queryset = Group.objects.filter(name__in=ROLE_NAMES).order_by("name")
        self.fields["direct_permissions"].queryset = Permission.objects.filter(
            content_type__app_label=APP_LABEL,
            content_type__model="person",
            codename__in=ACCESS_PERMISSION_CODENAMES,
        ).order_by("name")
        self.fields["roles"].widget.attrs["class"] = "uk-checkbox"
        self.fields["direct_permissions"].widget.attrs["class"] = "uk-checkbox"
        if account is not None and not self.is_bound:
            self.initial.update(
                {
                    "person": current_person,
                    "roles": account.groups.filter(name__in=ROLE_NAMES),
                    "direct_permissions": account.user_permissions.filter(
                        content_type__app_label=APP_LABEL,
                        content_type__model="person",
                        codename__in=ACCESS_PERMISSION_CODENAMES,
                    ),
                    "is_active": account.is_active,
                }
            )

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()

    def clean(self) -> dict:
        cleaned_data = super().clean()
        selected_person = cleaned_data.get("person")
        inline_values = {
            field_name: cleaned_data.get(field_name, "").strip()
            for field_name in ("vorname", "nachname", "email")
        }
        if selected_person is not None and any(inline_values.values()):
            self.add_error(
                None,
                "Wählen Sie eine bestehende Person oder erfassen Sie eine neue Person.",
            )
        elif selected_person is None:
            for field_name, value in inline_values.items():
                if not value:
                    self.add_error(field_name, "Bitte erfassen Sie die neue Person vollständig.")
            email = inline_values["email"]
            if email and Person.objects.filter(email__iexact=email).exists():
                self.add_error("email", "Für diese E-Mail-Adresse existiert bereits eine Person.")

        target_email = (
            selected_person.email if selected_person is not None else inline_values["email"]
        )
        if target_email:
            user_model = get_user_model()
            existing_accounts = user_model.objects.filter(
                Q(username__iexact=target_email) | Q(email__iexact=target_email)
            )
            if self.account is not None:
                existing_accounts = existing_accounts.exclude(pk=self.account.pk)
            if existing_accounts.exists():
                self.add_error(
                    "person" if selected_person is not None else "email",
                    ACCOUNT_CREATION_ERROR,
                )
        cleaned_data["target_email"] = target_email

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if self.account is None and not password1:
            self.add_error("password1", "Bitte vergeben Sie ein Passwort für das neue Konto.")
        if self.account is not None:
            current_person = getattr(self.account, "person_profile", None)
            person_changed = selected_person is None or selected_person != current_person
            if person_changed and (not password1 or self.account.check_password(password1)):
                self.add_error(
                    "password1",
                    "Bei einem Personenwechsel muss ein neues Passwort vergeben werden.",
                )
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Die Passwörter stimmen nicht überein.")
            elif target_email:
                user = self.account or get_user_model()()
                user.username = target_email
                user.email = target_email
                try:
                    validate_password(password1, user)
                except ValidationError as error:
                    self.add_error("password1", error)

        self._validate_actor_lockout(cleaned_data)
        return cleaned_data

    def _validate_actor_lockout(self, cleaned_data: dict) -> None:
        if self.account is None or self.actor is None or self.account.pk != self.actor.pk:
            return
        if not cleaned_data.get("is_active"):
            self.add_error("is_active", "Sie können Ihr eigenes Konto nicht deaktivieren.")
            return
        roles = cleaned_data.get("roles") or []
        direct_permissions = cleaned_data.get("direct_permissions") or []
        will_manage_accounts = any(role.name == ROLE_USER_MANAGEMENT for role in roles) or any(
            permission.codename == "manage_user_accounts" for permission in direct_permissions
        )
        if self.account.has_perm(USER_MANAGEMENT_PERMISSION) and not will_manage_accounts:
            user_model = get_user_model()
            has_other_manager = any(
                user.has_perm(USER_MANAGEMENT_PERMISSION)
                for user in user_model.objects.filter(is_active=True).exclude(pk=self.account.pk)
            )
            if not has_other_manager:
                self.add_error(
                    "roles",
                    "Der letzte aktive Benutzerverwalter darf seine Berechtigung nicht entfernen.",
                )

    def save(self):
        user_model = get_user_model()
        selected_person = self.cleaned_data["person"]
        privileged_permissions = (EMPLOYEE_ACCESS_PERMISSION, USER_MANAGEMENT_PERMISSION)
        with transaction.atomic():
            original_account = (
                user_model.objects.get(pk=self.account.pk) if self.account is not None else None
            )
            previously_privileged = original_account is not None and any(
                original_account.has_perm(permission) for permission in privileged_permissions
            )
            if selected_person is None:
                person = Person(
                    vorname=self.cleaned_data["vorname"],
                    nachname=self.cleaned_data["nachname"],
                    email=self.cleaned_data["target_email"],
                )
            else:
                person = Person.objects.select_for_update().get(pk=selected_person.pk)
                if person.user_id not in (None, self.account.pk if self.account else None):
                    raise ValidationError(
                        "Die ausgewählte Person ist inzwischen einem Konto zugeordnet."
                    )

            if self.account is None:
                account = user_model()
            else:
                account = self.account
            account.username = self.cleaned_data["target_email"]
            account.email = self.cleaned_data["target_email"]
            account.first_name = person.vorname
            account.last_name = person.nachname
            account.is_active = self.cleaned_data["is_active"]
            if self.cleaned_data["password1"]:
                account.set_password(self.cleaned_data["password1"])
            account.save()

            previous_person = Person.objects.select_for_update().filter(user=account).first()
            if previous_person is not None and previous_person != person:
                previous_person.user = None
                previous_person.save(update_fields=["user", "updated_at"])
            person.user = account
            person.save()

            role_groups = list(self.cleaned_data["roles"])
            other_groups = list(account.groups.exclude(name__in=ROLE_NAMES))
            account.groups.set([*other_groups, *role_groups])

            custom_permissions = Permission.objects.filter(
                content_type__app_label=APP_LABEL,
                content_type__model="person",
                codename__in=ACCESS_PERMISSION_CODENAMES,
            )
            other_permissions = list(account.user_permissions.exclude(pk__in=custom_permissions))
            account.user_permissions.set(
                [*other_permissions, *self.cleaned_data["direct_permissions"]]
            )
            # Read fresh permissions: the form's account may cache its previous rights.
            updated_account = user_model.objects.get(pk=account.pk)
            newly_privileged = not previously_privileged and any(
                updated_account.has_perm(permission) for permission in privileged_permissions
            )
            credentials_changed = bool(self.cleaned_data["password1"]) or (
                original_account is not None and original_account.email != account.email
            )
            if newly_privileged or credentials_changed or not account.is_active:
                # A pending code was issued for the previous credentials or access state.
                EmployeeLoginVerification.objects.filter(user=account).delete()
                RegistrationVerification.objects.filter(user=account).delete()
                # End only this account's active sessions. A privileged account must
                # enter the normal password/MFA flow with its current credentials.
                for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
                    if session.get_decoded().get("_auth_user_id") == str(account.pk):
                        session.delete()
        return account


class BewerbungForm(forms.ModelForm):
    personenanzahl = forms.IntegerField(
        initial=1,
        min_value=1,
        label="Personen im Haushalt",
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "1", "step": "1"}),
    )
    haustiere = forms.TypedChoiceField(
        choices=(("true", "Ja"), ("false", "Nein")),
        coerce=lambda value: value == "true",
        empty_value=None,
        label="Ziehen Haustiere mit ein?",
        error_messages={"required": "Bitte wählen Sie aus, ob Haustiere mit einziehen."},
        widget=forms.RadioSelect(attrs={"class": "uk-radio"}),
    )

    class Meta:
        model = Bewerbung
        fields = ["wohnung", "personenanzahl", "haustiere", "ueber_mich"]
        labels = {
            "wohnung": "Gewünschte Wohnung",
            "personenanzahl": "Personen im Haushalt",
            "ueber_mich": "Über mich",
        }
        widgets = {
            "wohnung": forms.Select(attrs={"class": "uk-select"}),
            "ueber_mich": forms.Textarea(attrs={"class": "uk-textarea", "rows": 5}),
        }

    def __init__(self, *args, applicant: Person, unit: Wohnung | None = None, **kwargs) -> None:
        self.applicant = applicant
        super().__init__(*args, **kwargs)
        available_units = Wohnung.objects.available().order_by("gebaeudenummer", "wohnungsnummer")
        self.fields["wohnung"].queryset = available_units
        if unit is not None:
            self.fields["wohnung"].queryset = available_units.filter(pk=unit.pk)
            self.fields["wohnung"].initial = unit.pk
            self.fields["wohnung"].disabled = True

    def save(self, commit: bool = True) -> Bewerbung:
        application = super().save(commit=False)
        application.person = self.applicant
        if commit:
            application.save()
        return application


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        uploads = data if isinstance(data, (list, tuple)) else [data]
        cleaned_uploads = []
        for upload in uploads:
            if upload not in (None, ""):
                cleaned_uploads.append(super().clean(upload, initial))
        return cleaned_uploads


class ApplicationProofStorageError(Exception):
    """Raised when an uploaded proof cannot be written to private storage."""


class MainApplicationForm(forms.Form):
    MAX_FILES_PER_CATEGORY = 10
    MULTIPART_OVERHEAD_RESERVE = 64 * 1024
    PROOF_FIELDS = (
        (ApplicationProofCategory.INCOME, "income_proof", "Gehaltsnachweise"),
        (ApplicationProofCategory.IDENTITY, "identity_proof", "Identitätsnachweis"),
        (ApplicationProofCategory.CREDIT_REPORT, "credit_report_proof", "SCHUFA-Unterlage"),
    )

    action = forms.CharField(required=False, widget=forms.HiddenInput)
    income_proof = MultipleFileField(
        label="Gehaltsabrechnungen",
        required=False,
        widget=MultipleFileInput(
            attrs={"class": "uk-input", "accept": ".png,.pdf,image/png,application/pdf"}
        ),
    )
    identity_proof = MultipleFileField(
        label="Identitätsnachweis",
        required=False,
        widget=MultipleFileInput(
            attrs={"class": "uk-input", "accept": ".png,.pdf,image/png,application/pdf"}
        ),
    )
    credit_report_proof = MultipleFileField(
        label="SCHUFA-Unterlage",
        required=False,
        widget=MultipleFileInput(
            attrs={"class": "uk-input", "accept": ".png,.pdf,image/png,application/pdf"}
        ),
    )

    def __init__(self, *args, instance: Bewerbung, **kwargs):
        self.instance = instance
        self.stored_proof_files: list[tuple[Storage, str]] = []
        super().__init__(*args, **kwargs)
        for _category, field_name, label in self.PROOF_FIELDS:
            self.fields[field_name].widget.attrs["data-proof-upload-input"] = ""
            self.fields[field_name].widget.attrs["data-max-files"] = str(
                self.MAX_FILES_PER_CATEGORY
            )
            self.fields[field_name].widget.attrs["data-max-file-size"] = str(
                settings.MAIN_APPLICATION_PROOF_MAX_SIZE
            )
            self.fields[field_name].widget.attrs["data-max-total-size"] = str(
                max(
                    0,
                    settings.MAIN_APPLICATION_MAX_REQUEST_SIZE - self.MULTIPART_OVERHEAD_RESERVE,
                )
            )
            self.fields[field_name].help_text = (
                f"Sie können Dateien für {label} auch nacheinander auswählen; "
                f"die bisherige Auswahl bleibt erhalten. Maximal "
                f"{self.MAX_FILES_PER_CATEGORY} Dateien pro Nachweiskategorie."
            )

    def clean(self) -> dict:
        cleaned_data = super().clean()
        action = self.data.get("action") or "save_draft"
        if action not in {"save_draft", "submit"}:
            raise forms.ValidationError("Bitte wählen Sie eine gültige Aktion.")
        cleaned_data["action"] = action

        existing_names = {
            self._normalized_file_name(name)
            for name in self.instance.proof_files.values_list("original_name", flat=True)
        }
        for _category, field_name, _label in self.PROOF_FIELDS:
            if getattr(self.instance, field_name):
                legacy_name = getattr(self.instance, f"{field_name}_original_name", "")
                if legacy_name:
                    existing_names.add(self._normalized_file_name(legacy_name))

        submitted_names = set()
        for category, field_name, _label in self.PROOF_FIELDS:
            existing_count = int(bool(getattr(self.instance, field_name)))
            existing_count += self.instance.proof_files.filter(category=category).count()
            uploads = cleaned_data.get(field_name) or []
            uploaded_count = len(uploads)

            has_duplicate_name = False
            for upload in uploads:
                normalized_name = self._normalized_file_name(upload.name)
                if normalized_name in existing_names or normalized_name in submitted_names:
                    has_duplicate_name = True
                submitted_names.add(normalized_name)

            if has_duplicate_name:
                self.add_error(
                    field_name,
                    "Eine Datei mit dieser Bezeichnung wird bereits in dieser Main-Bewerbung "
                    "verwendet. Bitte benennen Sie sie um.",
                )

            if existing_count + uploaded_count > self.MAX_FILES_PER_CATEGORY:
                self.add_error(
                    field_name,
                    f"Pro Nachweiskategorie sind höchstens {self.MAX_FILES_PER_CATEGORY} "
                    "Dateien erlaubt.",
                )
            if action == "submit" and existing_count + uploaded_count == 0:
                self.add_error(
                    field_name,
                    "Mindestens eine Datei dieses Nachweises ist für die Einreichung erforderlich.",
                )
        return cleaned_data

    def save_uploaded_proofs(self) -> None:
        for category, field_name, _label in self.PROOF_FIELDS:
            for upload in self.cleaned_data.get(field_name, []):
                proof = ApplicationProof(
                    application=self.instance,
                    category=category,
                    original_name=self._display_filename(upload.name),
                )
                file_field = proof._meta.get_field("file")
                storage = proof.file.storage
                try:
                    stored_name = file_field.generate_filename(proof, upload.name)
                    while storage.exists(stored_name):
                        stored_name = file_field.generate_filename(proof, upload.name)

                    # Track the unique candidate before writing: storage backends can raise
                    # after creating the object, in which case no name is returned.
                    self.stored_proof_files.append((storage, stored_name))
                    saved_name = storage.save(
                        stored_name,
                        upload,
                        max_length=file_field.max_length,
                    )
                except Exception as error:
                    raise ApplicationProofStorageError from error

                if saved_name != stored_name:
                    self.stored_proof_files.append((storage, saved_name))
                proof.file.name = saved_name
                proof.save()

    def cleanup_stored_proof_files(self) -> list[tuple[Storage, str]]:
        failures: list[tuple[Storage, str]] = []
        for storage, stored_name in reversed(self.stored_proof_files):
            try:
                storage.delete(stored_name)
            except Exception:
                failures.append((storage, stored_name))
        self.stored_proof_files = failures
        return failures

    @staticmethod
    def _display_filename(filename: str) -> str:
        display_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
        display_name = "".join(character for character in display_name if character.isprintable())
        return display_name.strip()[:255] or "Datei"

    @classmethod
    def _normalized_file_name(cls, filename: str) -> str:
        return unicodedata.normalize("NFKC", cls._display_filename(filename)).casefold()

    def _clean_proof(self, upload):
        if upload.size > settings.MAIN_APPLICATION_PROOF_MAX_SIZE:
            maximum_mib = settings.MAIN_APPLICATION_PROOF_MAX_SIZE / (1024 * 1024)
            raise forms.ValidationError(f"Die Datei darf höchstens {maximum_mib:g} MiB groß sein.")

        original_position = upload.tell()
        try:
            upload.seek(0)
            header = upload.read(1024)
            if header.startswith(b"%PDF-"):
                upload.seek(0)
                try:
                    reader = PdfReader(upload, strict=True)
                    if not reader.pages:
                        raise forms.ValidationError("Das PDF enthält keine Seiten.")
                except (
                    AttributeError,
                    KeyError,
                    TypeError,
                    RecursionError,
                    OverflowError,
                ) as error:
                    raise forms.ValidationError("Das PDF kann nicht verarbeitet werden.") from error
                return upload

            upload.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(upload) as image:
                    if image.format != "PNG":
                        raise forms.ValidationError("Erlaubt sind nur PNG- oder PDF-Dateien.")
                    image.verify()
                upload.seek(0)
                with Image.open(upload) as image:
                    if image.format != "PNG":
                        raise forms.ValidationError("Erlaubt sind nur PNG- oder PDF-Dateien.")
                    image.load()
            return upload
        except forms.ValidationError:
            raise
        except (DependencyError, NotImplementedError) as error:
            raise forms.ValidationError(
                "Dieses verschlüsselte PDF kann nicht verarbeitet werden. "
                "Bitte laden Sie ein unverschlüsseltes PDF hoch."
            ) from error
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            PyPdfError,
            SyntaxError,
            UnidentifiedImageError,
            ValueError,
        ) as error:
            raise forms.ValidationError(
                "Erlaubt sind nur gültige PNG- oder PDF-Dateien."
            ) from error
        finally:
            upload.seek(original_position)

    def _clean_proof_files(self, field_name: str):
        return [self._clean_proof(upload) for upload in self.cleaned_data.get(field_name, [])]

    def clean_income_proof(self):
        return self._clean_proof_files("income_proof")

    def clean_identity_proof(self):
        return self._clean_proof_files("identity_proof")

    def clean_credit_report_proof(self):
        return self._clean_proof_files("credit_report_proof")


class ApartmentSearchForm(forms.Form):
    groesse_min = forms.DecimalField(
        label="Wohnfläche ab (m²)",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "0", "step": "1"}),
    )
    groesse_max = forms.DecimalField(
        label="Wohnfläche bis (m²)",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "0", "step": "1"}),
    )
    kaltmiete_min = forms.DecimalField(
        label="Kaltmiete ab (€)",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "0", "step": "10"}),
    )
    kaltmiete_max = forms.DecimalField(
        label="Kaltmiete bis (€)",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "0", "step": "10"}),
    )
    zimmer_min = forms.DecimalField(
        label="Zimmer ab",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "0", "step": "0.5"}),
    )
    zimmer_max = forms.DecimalField(
        label="Zimmer bis",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "uk-input", "min": "0", "step": "0.5"}),
    )
    etage = forms.ChoiceField(
        label="Etage",
        required=False,
        choices=(("", "Alle Etagen"),),
        widget=forms.Select(attrs={"class": "uk-select"}),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        floors = Wohnung.objects.order_by("etage").values_list("etage", flat=True).distinct()
        self.fields["etage"].choices = (("", "Alle Etagen"),) + tuple(
            (str(floor), "Erdgeschoss" if floor == 0 else f"Etage {floor}") for floor in floors
        )

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        ranges = (
            ("groesse_min", "groesse_max"),
            ("kaltmiete_min", "kaltmiete_max"),
            ("zimmer_min", "zimmer_max"),
        )
        for minimum_field, maximum_field in ranges:
            minimum = cleaned_data.get(minimum_field)
            maximum = cleaned_data.get(maximum_field)
            if minimum is not None and maximum is not None and minimum > maximum:
                self.add_error(
                    maximum_field,
                    "Der Höchstwert muss mindestens dem Mindestwert entsprechen.",
                )
        return cleaned_data


class HandoverProtocolForm(forms.ModelForm):
    vermieter_name = forms.ChoiceField(
        label="Anwesend für den Vermieter",
        choices=(),
        widget=forms.Select(attrs={"class": "uk-select"}),
    )

    class Meta:
        model = Protokoll
        fields = [
            "wohnung",
            "person",
            "protokoll_typ",
            "uebergabe_zeitpunkt",
            "vermieter_name",
            "mieter_zukuenftige_anschrift",
            "uebergabe_status",
            "abnahme_status",
            "zaehlerstand_wasser_kalt",
            "zaehlerstand_wasser_warm",
            "zaehlerstand_heizung",
            "heizungsablesungen",
            "zaehlerstand_strom",
            "kaution_nachweis_vorhanden",
            "erste_miete_nachweis_vorhanden",
            "nachbesserung_bis",
            "nachbesserung_beschreibung",
        ]
        labels = {
            "wohnung": "Wohnung",
            "person": "Beteiligte Person",
            "protokoll_typ": "Übergabeart",
            "uebergabe_zeitpunkt": "Datum und Uhrzeit",
            "mieter_zukuenftige_anschrift": "Zukünftige Anschrift der beteiligten Person",
            "uebergabe_status": "Zustand bei Übergabe",
            "abnahme_status": "Abnahmestatus",
            "zaehlerstand_wasser_kalt": "Zählerstand Kaltwasser",
            "zaehlerstand_wasser_warm": "Zählerstand Warmwasser",
            "zaehlerstand_heizung": "Zählerstand Heizung",
            "heizungsablesungen": "Zusatzablesungen Heizung (IE, IA, Ib)",
            "zaehlerstand_strom": "Zählerstand Strom",
            "kaution_nachweis_vorhanden": "Überweisungsbeleg Kaution liegt vor",
            "erste_miete_nachweis_vorhanden": "Überweisungsbeleg erste Miete liegt vor",
            "nachbesserung_bis": "Nachbesserung bis",
            "nachbesserung_beschreibung": "Vereinbarte Nachbesserungen",
        }
        widgets = {
            "wohnung": forms.Select(attrs={"class": "uk-select"}),
            "person": forms.Select(attrs={"class": "uk-select"}),
            "protokoll_typ": forms.Select(attrs={"class": "uk-select"}),
            "uebergabe_zeitpunkt": forms.DateTimeInput(
                attrs={"class": "uk-input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "mieter_zukuenftige_anschrift": forms.Textarea(
                attrs={"class": "uk-textarea", "rows": 3}
            ),
            "uebergabe_status": forms.Select(attrs={"class": "uk-select"}),
            "abnahme_status": forms.Select(attrs={"class": "uk-select"}),
            "zaehlerstand_wasser_kalt": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "zaehlerstand_wasser_warm": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "zaehlerstand_heizung": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "heizungsablesungen": forms.TextInput(attrs={"class": "uk-input"}),
            "zaehlerstand_strom": forms.NumberInput(
                attrs={"class": "uk-input", "min": "0", "step": "0.01"}
            ),
            "kaution_nachweis_vorhanden": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            "erste_miete_nachweis_vorhanden": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            "nachbesserung_bis": forms.DateInput(
                attrs={"class": "uk-input", "type": "date"}, format="%Y-%m-%d"
            ),
            "nachbesserung_beschreibung": forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
        }

    def __init__(self, *args, wohnung_id: str | None = None, employee=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["wohnung"].queryset = Wohnung.objects.order_by(
            "gebaeudenummer", "wohnungsnummer"
        )
        selected_wohnung_id = _valid_wohnung_id(wohnung_id)
        if selected_wohnung_id is None and self.instance.pk:
            selected_wohnung_id = self.instance.wohnung_id
        self.selected_wohnung = None
        self.fields["person"].queryset = Person.objects.none()
        if selected_wohnung_id is not None:
            self.selected_wohnung = Wohnung.objects.filter(pk=selected_wohnung_id).first()
            self.fields["person"].queryset = Person.objects.filter(
                wohnung_id=selected_wohnung_id
            ).order_by("nachname", "vorname")
            if not self.is_bound:
                self.initial["wohnung"] = selected_wohnung_id
        self.fields["vermieter_name"].choices = [
            ("", "Bitte auswählen"),
            *[
                (str(employee), str(employee))
                for employee in Person.objects.filter(is_employee=True).order_by(
                    "nachname", "vorname"
                )
            ],
        ]
        if employee is not None:
            from .handover_export import employee_name

            name = employee_name(employee)
            self.fields["vermieter_name"].choices = [(name, name)] if name else [("", "Name fehlt")]
            self.fields["vermieter_name"].disabled = True
            self.fields["vermieter_name"].label = "Vertretung des Unternehmens"
            self.initial["vermieter_name"] = name
            self.fields["vermieter_name"].help_text = "Diese Person unterschreibt das Protokoll."
        self.fields["mieter_zukuenftige_anschrift"].required = False
        self.fields["protokoll_typ"].choices = HANDOVER_TYPE_LABELS.items()
        self.fields["uebergabe_status"].choices = HANDOVER_STATUS_LABELS.items()
        self.fields["abnahme_status"].choices = ACCEPTANCE_STATUS_LABELS.items()
        for field_name, _number_field, label in METER_READING_FIELDS:
            self.fields[field_name].widget.attrs["data-meter-reading"] = ""
            self.fields[field_name].widget.attrs["aria-label"] = f"{label}, Auszug neu"

    def clean(self) -> dict:
        cleaned_data = super().clean()
        handover_type = cleaned_data.get("protokoll_typ")
        apartment = cleaned_data.get("wohnung")
        if (
            self.instance.pk
            and apartment is not None
            and apartment.pk != self.instance.wohnung_id
            and self.instance.raeume.exists()
        ):
            self.add_error(
                "wohnung",
                "Die Wohnung kann nicht geändert werden, weil das Protokoll bereits Räume enthält.",
            )
        if apartment is not None:
            for field_name, label in METER_NUMBER_FIELDS:
                if not getattr(apartment, field_name).strip():
                    self.add_error(
                        "wohnung",
                        f"Die Zählernummer für {label} fehlt in den Wohnungsstammdaten.",
                    )

        future_address = cleaned_data.get("mieter_zukuenftige_anschrift", "").strip()
        remediation_due_date = cleaned_data.get("nachbesserung_bis")
        remediation_description = cleaned_data.get("nachbesserung_beschreibung")
        if handover_type == ProtokollTyp.MOVE_OUT and not future_address:
            self.add_error(
                "mieter_zukuenftige_anschrift",
                "Bitte erfassen Sie die zukünftige Anschrift für den Auszug.",
            )
        if (
            handover_type == ProtokollTyp.MOVE_OUT
            and remediation_description
            and not remediation_due_date
        ):
            self.add_error(
                "nachbesserung_bis", "Bitte erfassen Sie die Frist für die Nachbesserung."
            )
        if (
            handover_type == ProtokollTyp.MOVE_OUT
            and remediation_due_date
            and not remediation_description
        ):
            self.add_error(
                "nachbesserung_beschreibung",
                "Bitte beschreiben Sie die vereinbarte Nachbesserung.",
            )
        if handover_type == ProtokollTyp.MOVE_IN:
            cleaned_data["mieter_zukuenftige_anschrift"] = ""
            cleaned_data["nachbesserung_bis"] = None
            cleaned_data["nachbesserung_beschreibung"] = ""
            cleaned_data["kaution_nachweis_vorhanden"] = cleaned_data.get(
                "kaution_nachweis_vorhanden", False
            )
            cleaned_data["erste_miete_nachweis_vorhanden"] = cleaned_data.get(
                "erste_miete_nachweis_vorhanden", False
            )
        elif handover_type == ProtokollTyp.MOVE_OUT:
            cleaned_data["kaution_nachweis_vorhanden"] = False
            cleaned_data["erste_miete_nachweis_vorhanden"] = False
        return cleaned_data

    @property
    def meter_numbers(self) -> tuple[tuple[str, str], ...]:
        if self.selected_wohnung is None:
            return ()
        return tuple(
            (label, getattr(self.selected_wohnung, field_name) or "Nicht gepflegt")
            for field_name, label in METER_NUMBER_FIELDS
        )

    @property
    def main_fields(self):
        return tuple(
            self[field_name]
            for field_name in (
                "wohnung",
                "person",
                "protokoll_typ",
                "uebergabe_zeitpunkt",
                "vermieter_name",
                "uebergabe_status",
                "abnahme_status",
            )
        )

    @property
    def meter_reading_fields(self):
        return tuple(
            self[field_name]
            for field_name in (
                *[field_name for field_name, *_rest in METER_READING_FIELDS],
                "heizungsablesungen",
            )
        )

    @property
    def move_in_fields(self):
        return tuple(
            self[field_name]
            for field_name in ("kaution_nachweis_vorhanden", "erste_miete_nachweis_vorhanden")
        )

    @property
    def move_out_fields(self):
        return tuple(
            self[field_name] for field_name in ("nachbesserung_bis", "nachbesserung_beschreibung")
        )

    def save(self, commit: bool = True) -> Protokoll:
        protocol = super().save(commit=False)
        for field_name, _label in METER_NUMBER_FIELDS:
            setattr(protocol, field_name, getattr(protocol.wohnung, field_name))
        if protocol.protokoll_typ == ProtokollTyp.MOVE_IN:
            protocol.mieter_zukuenftige_anschrift = ""
            protocol.nachbesserung_bis = None
            protocol.nachbesserung_beschreibung = ""
        else:
            protocol.kaution_nachweis_vorhanden = False
            protocol.erste_miete_nachweis_vorhanden = False
        if commit:
            protocol.save()
        return protocol


def _valid_wohnung_id(wohnung_id: str | None) -> UUID | None:
    try:
        return UUID(str(wohnung_id))
    except (TypeError, ValueError):
        return None


class RoomProtocolForm(forms.ModelForm):
    class Meta:
        model = Raumprotokoll
        fields = ["raum"]
        labels = {"raum": "Raum"}
        widgets = {"raum": forms.Select(attrs={"class": "uk-select"})}

    def __init__(self, *args, protocol: Protokoll, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.protocol = protocol
        self.fields["raum"].queryset = Raum.objects.filter(wohnung=protocol.wohnung).order_by(
            "name"
        )

    def clean_raum(self) -> Raum:
        raum = self.cleaned_data["raum"]
        if Raumprotokoll.objects.filter(protokoll=self.protocol, raum=raum).exists():
            raise forms.ValidationError("Dieser Raum wurde im Übergabeprotokoll bereits erfasst.")
        return raum


def _feature_area_choices() -> list[tuple[str, str]]:
    areas = Merkmal.objects.order_by("bereich").values_list("bereich", flat=True).distinct()
    return [("", "Bereich wählen"), *((area, area) for area in areas)]


class FeatureSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        feature = getattr(value, "instance", None)
        if feature is not None:
            option["attrs"]["data-feature-area"] = feature.bereich
            option["attrs"]["data-feature-options"] = json.dumps(_feature_options(feature))
        return option


class FeatureChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Merkmal) -> str:
        return obj.bezeichnung


def _feature_options(feature: Merkmal) -> list[str]:
    options: list[str] = []
    for value in feature.optionen:
        if not isinstance(value, str):
            continue
        option = value.strip()
        if option and option not in options:
            options.append(option)
    return options


def _clean_additional_details(raw_value: str, feature: Merkmal | None) -> dict[str, str]:
    if not raw_value:
        return {}
    try:
        details = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise forms.ValidationError("Die zusätzlichen Angaben sind ungültig.") from error
    if not isinstance(details, dict):
        raise forms.ValidationError("Die zusätzlichen Angaben sind ungültig.")

    permitted_labels = set(_feature_options(feature)) if feature is not None else set()
    cleaned_details: dict[str, str] = {}
    for label, value in details.items():
        if not isinstance(label, str) or label not in permitted_labels:
            raise forms.ValidationError(
                "Diese zusätzliche Angabe gehört nicht zum gewählten Prüfpunkt."
            )
        if not isinstance(value, str):
            raise forms.ValidationError("Die zusätzlichen Angaben sind ungültig.")
        if cleaned_value := value.strip():
            cleaned_details[label] = cleaned_value
    return cleaned_details


def _finding_value(text: str, additional_details: dict[str, str]) -> dict[str, object]:
    value: dict[str, object] = {"text": text}
    if additional_details:
        value["angaben"] = additional_details
    return value


class RoomChecklistItemForm(forms.Form):
    bereich = forms.ChoiceField(
        choices=(),
        label="Wo wird geprüft?",
        widget=forms.Select(attrs={"class": "uk-select", "data-feature-area-select": ""}),
    )
    merkmal = FeatureChoiceField(
        queryset=Merkmal.objects.none(),
        label="Was wird geprüft?",
        widget=FeatureSelect(attrs={"class": "uk-select", "data-feature-name-select": ""}),
    )
    wert = forms.CharField(
        label="Was wurde festgestellt?",
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
    )
    zusatzangaben = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-additional-details-value": ""}),
    )

    def __init__(self, *args, room: Raumprotokoll | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.room = room
        self.fields["bereich"].choices = _feature_area_choices()
        self.fields["merkmal"].queryset = Merkmal.objects.order_by("bereich", "bezeichnung")

    def clean(self) -> dict:
        cleaned_data = super().clean()
        feature = cleaned_data.get("merkmal")
        if feature is not None and feature.bereich != cleaned_data.get("bereich"):
            self.add_error("merkmal", "Die Bezeichnung gehört nicht zum gewählten Bereich.")
        if (
            feature is not None
            and self.room is not None
            and self.room.raum_merkmale.filter(merkmal=feature).exists()
        ):
            self.add_error("merkmal", "Dieser Prüfpunkt ist in diesem Raum bereits erfasst.")
        try:
            cleaned_data["zusatzangaben"] = _clean_additional_details(
                cleaned_data.get("zusatzangaben", ""), feature
            )
        except forms.ValidationError as error:
            self.add_error("zusatzangaben", error)
        return cleaned_data

    def save(self, room: Raumprotokoll) -> RaumMerkmal:
        return RaumMerkmal.objects.create(
            raumprotokoll=room,
            merkmal=self.cleaned_data["merkmal"],
            wert=_finding_value(self.cleaned_data["wert"], self.cleaned_data["zusatzangaben"]),
        )


class MultiplePhotoInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiplePhotoField(forms.ImageField):
    allowed_formats = frozenset(PHOTO_CONTENT_TYPES)

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                return super().clean(data, initial)
            return []
        single_photo_clean = super().clean
        photos = data if isinstance(data, (list, tuple)) else [data]
        cleaned_photos = [single_photo_clean(photo, initial) for photo in photos]
        checksums = [calculate_photo_checksum(photo) for photo in cleaned_photos]
        if len(checksums) != len(set(checksums)):
            raise forms.ValidationError("Dasselbe Foto kann nur einmal ausgewählt werden.")
        return cleaned_photos

    def validate(self, value) -> None:
        super().validate(value)
        if value.size > settings.HANDOVER_PHOTO_MAX_SIZE:
            maximum_mebibytes = settings.HANDOVER_PHOTO_MAX_SIZE // (1024 * 1024)
            raise forms.ValidationError(
                f"Ein Foto darf höchstens {maximum_mebibytes} MiB groß sein."
            )
        image_format = getattr(getattr(value, "image", None), "format", "")
        if photo_content_type_from_format(image_format) is None:
            raise forms.ValidationError("Erlaubt sind nur JPEG-, PNG- und WebP-Bilder.")


class RoomChecklistPhotoUploadForm(forms.Form):
    fotos = MultiplePhotoField(
        label="Fotos",
        widget=MultiplePhotoInput(
            attrs={
                "class": "uk-input",
                "accept": "image/jpeg,image/png,image/webp",
                "multiple": True,
            }
        ),
    )

    def __init__(self, *args, existing_photo_count: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.existing_photo_count = existing_photo_count

    def clean_fotos(self):
        photos = self.cleaned_data["fotos"]
        maximum = settings.HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM
        if self.existing_photo_count + len(photos) > maximum:
            raise forms.ValidationError(
                f"Für einen Prüfpunkt sind höchstens {maximum} Fotos erlaubt."
            )
        return photos


class HandoverKeyForm(forms.ModelForm):
    schluessel = forms.ModelChoiceField(
        queryset=ProtokollSchluessel.objects.none(), required=False, widget=forms.HiddenInput
    )

    def __init__(self, *args, protocol=None, **kwargs):
        super().__init__(*args, **kwargs)
        if protocol is not None:
            self.fields["schluessel"].queryset = protocol.protokoll_schluessel.all()
            try:
                existing = (
                    self.fields["schluessel"].queryset.filter(pk=self["schluessel"].value()).first()
                )
            except (ValueError, ValidationError):
                existing = None
            if existing is not None:
                self.instance = existing

    class Meta:
        model = ProtokollSchluessel
        fields = [
            "anzahl",
            "raum_bezeichnung",
            "aufschrift",
            "schluesselnummer",
            "fehlt",
            "fehlgrund",
            "nachlieferung_am",
        ]
        labels = {
            "anzahl": "Stück",
            "raum_bezeichnung": "Raum / Bezeichnung",
            "aufschrift": "Schlüsselaufschrift",
            "schluesselnummer": "Schlüsselnummer",
            "fehlt": "Schlüssel fehlt",
            "fehlgrund": "Grund für das Fehlen / Vereinbarung",
            "nachlieferung_am": "Nachlieferung am",
        }
        widgets = {
            "anzahl": forms.NumberInput(attrs={"class": "uk-input", "min": "1", "step": "1"}),
            "raum_bezeichnung": forms.TextInput(attrs={"class": "uk-input"}),
            "aufschrift": forms.TextInput(attrs={"class": "uk-input"}),
            "schluesselnummer": forms.TextInput(attrs={"class": "uk-input"}),
            "fehlt": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
            "fehlgrund": forms.Textarea(attrs={"class": "uk-textarea", "rows": 3}),
            "nachlieferung_am": forms.DateInput(
                attrs={"class": "uk-input", "type": "date"}, format="%Y-%m-%d"
            ),
        }

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if cleaned_data.get("anzahl") is not None and cleaned_data["anzahl"] < 1:
            self.add_error("anzahl", "Bitte erfassen Sie mindestens einen Schlüssel.")
        if cleaned_data.get("fehlt") and not cleaned_data.get("fehlgrund"):
            self.add_error("fehlgrund", "Bitte begründen Sie den fehlenden Schlüssel.")
        return cleaned_data


class ProtocolConfirmationForm(forms.Form):
    schluessel_ueberprueft = forms.BooleanField(
        label="Die Schlüsselübergabe wurde einschließlich fehlender Schlüssel geprüft.",
        error_messages={"required": "Bitte bestätigen Sie die Prüfung der Schlüsselübergabe."},
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )
    bestaetigung_erklaert = forms.BooleanField(
        label="Die Angaben entsprechen nach bestem Wissen dem tatsächlichen Zustand der Mieträume.",
        error_messages={"required": "Bitte bestätigen Sie die Richtigkeit der Angaben."},
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )


class InlineRoomChecklistForm(forms.Form):
    pruefpunkt = forms.ModelChoiceField(
        queryset=RaumMerkmal.objects.none(), required=False, widget=forms.HiddenInput
    )
    raum = forms.ModelChoiceField(
        queryset=Raum.objects.none(),
        label="Raum",
        required=False,
        widget=forms.Select(attrs={"class": "uk-select", "data-room-source": ""}),
    )
    bereich = forms.ChoiceField(
        choices=(),
        label="Wo wird geprüft?",
        required=False,
        widget=forms.Select(attrs={"class": "uk-select", "data-feature-area-select": ""}),
    )
    merkmal = FeatureChoiceField(
        queryset=Merkmal.objects.none(),
        label="Was wird geprüft?",
        required=False,
        widget=FeatureSelect(attrs={"class": "uk-select", "data-feature-name-select": ""}),
    )
    wert = forms.CharField(
        label="Was wurde festgestellt?",
        required=False,
        widget=forms.Textarea(attrs={"class": "uk-textarea", "rows": 5}),
    )
    fotos = MultiplePhotoField(
        label="Fotos zur Feststellung",
        required=False,
        widget=MultiplePhotoInput(
            attrs={
                "class": "uk-input",
                "accept": "image/jpeg,image/png,image/webp",
                "multiple": True,
            }
        ),
    )
    zusatzangaben = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-additional-details-value": ""}),
    )

    def __init__(
        self,
        *args,
        wohnung_id: UUID | None = None,
        allow_photo_upload: bool = False,
        protocol=None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.allow_photo_upload = allow_photo_upload
        self.protocol = protocol
        self.existing_item = None
        if protocol is not None:
            self.fields["pruefpunkt"].queryset = RaumMerkmal.objects.filter(
                raumprotokoll__protokoll=protocol
            ).prefetch_related("fotos")
            try:
                self.existing_item = (
                    self.fields["pruefpunkt"].queryset.filter(pk=self["pruefpunkt"].value()).first()
                )
            except (ValueError, ValidationError):
                pass
        if wohnung_id is not None:
            self.fields["raum"].queryset = Raum.objects.filter(wohnung_id=wohnung_id).order_by(
                "name"
            )
        self.fields["bereich"].choices = _feature_area_choices()
        self.fields["merkmal"].queryset = Merkmal.objects.order_by("bereich", "bezeichnung")

    def clean(self) -> dict:
        cleaned_data = super().clean()
        photos = cleaned_data.get("fotos", [])
        values = {
            "raum": cleaned_data.get("raum"),
            "bereich": cleaned_data.get("bereich", "").strip(),
            "merkmal": cleaned_data.get("merkmal"),
            "wert": cleaned_data.get("wert", "").strip(),
        }
        if not any((values["bereich"], values["merkmal"], values["wert"])):
            if cleaned_data.get("pruefpunkt"):
                self.add_error("wert", "Bitte vervollständigen Sie den vorhandenen Prüfpunkt.")
            if photos:
                self.add_error("fotos", "Bitte erfassen Sie den zugehörigen Prüfpunkt vollständig.")
            return cleaned_data
        for field_name in ("bereich", "merkmal", "wert"):
            value = values[field_name]
            if not value:
                self.add_error(field_name, "Bitte vervollständigen Sie diese Raumprüfung.")
        feature = cleaned_data.get("merkmal")
        if feature is not None and feature.bereich != cleaned_data.get("bereich"):
            self.add_error("merkmal", "Die Bezeichnung gehört nicht zum gewählten Bereich.")
        try:
            cleaned_data["zusatzangaben"] = _clean_additional_details(
                cleaned_data.get("zusatzangaben", ""), feature
            )
        except forms.ValidationError as error:
            self.add_error("zusatzangaben", error)
        if photos and not self.allow_photo_upload:
            self.add_error("fotos", "Nur die Verwaltung darf Fotos hochladen.")
        existing = cleaned_data.get("pruefpunkt")
        if existing is None and self.protocol and values["raum"] and feature:
            existing = (
                self.fields["pruefpunkt"]
                .queryset.filter(raumprotokoll__raum=values["raum"], merkmal=feature)
                .first()
            )
        if existing and not cleaned_data.get("DELETE") and not values["wert"]:
            self.add_error("wert", "Ein vorhandener Prüfpunkt darf nicht leer gespeichert werden.")
        if existing and values["raum"] and feature:
            collision = (
                self.fields["pruefpunkt"]
                .queryset.filter(raumprotokoll__raum=values["raum"], merkmal=feature)
                .exclude(pk=existing.pk)
            )
            if collision.exists():
                self.add_error("merkmal", "Dieser Prüfpunkt ist in diesem Raum bereits erfasst.")
        existing_count = existing.fotos.count() if existing else 0
        if existing_count + len(photos) > settings.HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM:
            maximum = settings.HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM
            self.add_error("fotos", f"Für einen Prüfpunkt sind höchstens {maximum} Fotos erlaubt.")
        return cleaned_data

    def has_entry(self) -> bool:
        return self.cleaned_data.get("merkmal") is not None

    def save(self, protocol: Protokoll) -> RaumMerkmal:
        raum = self.cleaned_data["raum"]
        room, _created = Raumprotokoll.objects.get_or_create(
            protokoll=protocol,
            raum=raum,
            defaults={"name": raum.name},
        )
        values = {
            "wert": _finding_value(self.cleaned_data["wert"], self.cleaned_data["zusatzangaben"])
        }
        checklist_item = self.cleaned_data.get("pruefpunkt")
        if checklist_item is not None:
            checklist_item.raumprotokoll = room
            checklist_item.merkmal = self.cleaned_data["merkmal"]
            checklist_item.wert = values["wert"]
            checklist_item.save()
        else:
            checklist_item, _ = RaumMerkmal.objects.update_or_create(
                raumprotokoll=room, merkmal=self.cleaned_data["merkmal"], defaults=values
            )
        for photo in self.cleaned_data["fotos"]:
            checksum = calculate_photo_checksum(photo)
            if checklist_item.fotos.filter(inhalt_hash_sha256=checksum).exists():
                continue
            RaumMerkmalFoto.objects.create(
                raum_merkmal=checklist_item,
                datei=photo,
                content_type=verified_photo_content_type(photo),
                dateigroesse=photo.size,
                inhalt_hash_sha256=checksum,
            )
        return checklist_item


class RoomChecklistFormSet(BaseFormSet):
    def clean(self) -> None:
        super().clean()
        current_room = None
        checklist_entries = []
        for room_form in self.forms:
            if (
                not getattr(room_form, "cleaned_data", None)
                or room_form.cleaned_data.get("DELETE")
                or not room_form.has_entry()
            ):
                continue
            room = room_form.cleaned_data.get("raum")
            if room is not None:
                current_room = room
            elif current_room is not None:
                room_form.cleaned_data["raum"] = current_room
            else:
                room_form.add_error("raum", "Bitte wählen Sie für den ersten Prüfpunkt einen Raum.")
                continue
            checklist_entries.append(room_form)

        seen_checkpoints = set()
        seen_items = set()
        for room_form in checklist_entries:
            existing = room_form.cleaned_data.get("pruefpunkt")
            if existing is not None:
                if existing.pk in seen_items:
                    room_form.add_error("pruefpunkt", "Der Prüfpunkt wurde mehrfach übertragen.")
                seen_items.add(existing.pk)
            checkpoint = (
                room_form.cleaned_data["raum"].pk,
                room_form.cleaned_data["merkmal"].pk,
            )
            if checkpoint in seen_checkpoints:
                room_form.add_error(
                    "merkmal", "Dieser Prüfpunkt ist in diesem Raum bereits erfasst."
                )
            seen_checkpoints.add(checkpoint)


InlineRoomChecklistFormSet = forms.formset_factory(
    InlineRoomChecklistForm,
    extra=1,
    can_delete=True,
    formset=RoomChecklistFormSet,
)
HandoverKeyFormSet = forms.formset_factory(HandoverKeyForm, extra=1, can_delete=True)


class UIkitFormMixin:
    """Apply the project-wide UIkit classes to management form widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "uk-checkbox")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "uk-select")
            else:
                widget.attrs.setdefault("class", "uk-input")


class WohnungForm(UIkitFormMixin, forms.ModelForm):
    status = forms.ChoiceField(
        choices=(
            (WohnungStatus.FREE, "Verfügbar"),
            (WohnungStatus.TAKEN, "Vermietet"),
            (WohnungStatus.BLOCKED, "Gesperrt"),
        ),
        label="Verfügbarkeitsstatus",
        widget=forms.Select(attrs={"class": "uk-select"}),
    )
    max_occupants = forms.IntegerField(
        required=False,
        min_value=1,
        label="Höchstzahl einziehender Personen",
        widget=forms.NumberInput(attrs={"min": "1", "step": "1"}),
    )
    pet_review_required = forms.TypedChoiceField(
        required=False,
        choices=(
            ("", "Noch nicht festgelegt"),
            ("true", "Ja, Tierhaltungsangaben einzeln prüfen"),
            ("false", "Nein, keine gesonderte Tierhaltungsprüfung"),
        ),
        coerce=lambda value: {"true": True, "false": False}.get(value),
        empty_value=None,
        label="Gesonderte Tierhaltungsprüfung",
        widget=forms.Select(attrs={"class": "uk-select"}),
    )

    class Meta:
        model = Wohnung
        fields = [
            "gebaeudenummer",
            "wohnungsnummer",
            "etage",
            "groesse_qm",
            "zimmeranzahl",
            "max_occupants",
            "occupancy_requirement_reason",
            "pet_review_required",
            "pet_review_reason",
            "kaltmiete",
            "warmmiete",
            "kaution",
            "status",
            "zaehlernummer_wasser_kalt",
            "zaehlernummer_wasser_warm",
            "zaehlernummer_heizung",
            "zaehlernummer_strom",
        ]
        labels = {
            "gebaeudenummer": "Gebäudenummer",
            "wohnungsnummer": "Wohnungsnummer",
            "etage": "Etage",
            "groesse_qm": "Größe (m²)",
            "zimmeranzahl": "Zimmeranzahl",
            "occupancy_requirement_reason": "Begründung der Belegungsanforderung",
            "pet_review_reason": "Begründung der Tierhaltungsregel",
            "kaltmiete": "Kaltmiete (€)",
            "warmmiete": "Warmmiete (€)",
            "kaution": "Kaution (€)",
            "zaehlernummer_wasser_kalt": "Zählernummer Kaltwasser",
            "zaehlernummer_wasser_warm": "Zählernummer Warmwasser",
            "zaehlernummer_heizung": "Zählernummer Heizung",
            "zaehlernummer_strom": "Zählernummer Strom",
        }

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("max_occupants") is not None
            and not cleaned_data.get("occupancy_requirement_reason", "").strip()
        ):
            self.add_error(
                "occupancy_requirement_reason",
                "Bitte begründen Sie die Höchstzahl einziehender Personen.",
            )
        if (
            cleaned_data.get("pet_review_required") is not None
            and not cleaned_data.get("pet_review_reason", "").strip()
        ):
            self.add_error("pet_review_reason", "Bitte begründen Sie die Tierhaltungsregel.")
        return cleaned_data


class EmployeeApplicationFilterForm(UIkitFormMixin, forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Alle Bearbeitungsstatus"),
            (BewerbungStatus.OPEN, "Offen"),
            (BewerbungStatus.DECLINED, "Abgelehnt"),
            (BewerbungStatus.BLOCKED, "Gesperrt"),
            ("withdrawn", "Zurückgezogen"),
        ),
        label="Bearbeitungsstatus",
    )
    main_status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Alle Main-Status"),
            ("pending", "Noch nicht freigeschaltet"),
            ("unlocked", "Freigeschaltet"),
            ("submitted", "Eingereicht"),
        ),
        label="Main-Status",
    )
    priority = forms.ChoiceField(
        required=False,
        choices=(("", "Alle Prioritäten"), *Bewerbung.Priority.choices),
        label="Priorität",
    )
    people = forms.IntegerField(required=False, min_value=1, label="Personenanzahl")
    q = forms.CharField(required=False, strip=True, label="Name oder E-Mail")
    created_from = forms.DateField(
        required=False, label="Eingang ab", widget=forms.DateInput(attrs={"type": "date"})
    )
    created_to = forms.DateField(
        required=False, label="Eingang bis", widget=forms.DateInput(attrs={"type": "date"})
    )
    sort = forms.ChoiceField(
        required=False,
        choices=(("newest", "Neueste zuerst"), ("priority", "Priorität zuerst")),
        initial="newest",
        label="Sortierung",
    )

    def clean(self):
        cleaned_data = super().clean()
        created_from = cleaned_data.get("created_from")
        created_to = cleaned_data.get("created_to")
        if created_from and created_to and created_from > created_to:
            self.add_error("created_to", "Das Enddatum muss nach dem Anfangsdatum liegen.")
        return cleaned_data


class ApplicationPriorityForm(UIkitFormMixin, forms.Form):
    priority = forms.ChoiceField(choices=Bewerbung.Priority.choices, label="Priorität")
    reason = forms.CharField(
        label="Begründung",
        strip=True,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class EligibilityApprovalForm(UIkitFormMixin, forms.Form):
    reason = forms.CharField(
        label="Begründung der Einzelfallfreigabe",
        strip=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class MainApplicationInvitationForm(UIkitFormMixin, forms.Form):
    confirm_positive_decision = forms.BooleanField(
        label="Ich bestätige die positive Entscheidung nach persönlicher Prüfung.",
    )
    reason = forms.CharField(
        label="Begründung der Freischaltung",
        strip=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class RaumForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Raum
        fields = ["name"]
        labels = {"name": "Raumname"}


class MerkmalForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Merkmal
        fields = ["bereich", "bezeichnung", "datentyp"]
        labels = {
            "bereich": "Wo wird geprüft?",
            "bezeichnung": "Was wird geprüft?",
            "datentyp": "Vorgegebene Bewertung",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datentyp"].help_text = (
            "Wählen Sie den typischen Wert, der diesen Prüfpunkt beschreibt, "
            "zum Beispiel „OK“ oder „Fliesen“."
        )


class MerkmalOptionForm(UIkitFormMixin, forms.Form):
    wert = forms.CharField(label="Zusätzliche Angabe", required=False)


MerkmalOptionFormSet = forms.formset_factory(MerkmalOptionForm, extra=1, can_delete=True)


class SchluesselForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Schluessel
        fields = ["bezeichnung", "anzahl", "aufschrift", "status"]
        labels = {
            "bezeichnung": "Bezeichnung",
            "anzahl": "Sollbestand",
            "aufschrift": "Aufschrift",
            "status": "Status",
        }


class StellplatzForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = Stellplatz
        fields = ["name", "stellplatz_typ", "miete"]
        labels = {"name": "Name", "stellplatz_typ": "Typ", "miete": "Miete (€)"}


class StellplatzZuordnungForm(UIkitFormMixin, forms.ModelForm):
    class Meta:
        model = StellplatzZuordnung
        fields = ["wohnung"]
        labels = {"wohnung": "Wohnung"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wohnung"].queryset = Wohnung.objects.order_by("etage", "wohnungsnummer")
        self.fields["wohnung"].empty_label = "Nicht zugeordnet"
        self.fields["wohnung"].required = False


SchluesselFormSet = inlineformset_factory(
    Wohnung,
    Schluessel,
    form=SchluesselForm,
    extra=1,
    can_delete=True,
)
