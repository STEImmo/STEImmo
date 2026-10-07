import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .fields import PostgreSQLEnumField


def handover_photo_upload_path(instance, _filename: str) -> str:
    """Return an opaque, protocol-scoped storage name for a checklist photo."""
    checklist_item = instance.raum_merkmal
    protocol_id = checklist_item.raumprotokoll.protokoll_id
    return f"u/{protocol_id.hex}/{checklist_item.pk.hex}/{uuid.uuid4().hex}"


def _application_proof_upload_path(instance, category: str) -> str:
    return f"bewerbungen/{instance.pk.hex}/{category}/{uuid.uuid4().hex}"


def income_proof_upload_path(instance, _filename: str) -> str:
    return _application_proof_upload_path(instance, "einkommen")


def identity_proof_upload_path(instance, _filename: str) -> str:
    return _application_proof_upload_path(instance, "identitaet")


def credit_report_proof_upload_path(instance, _filename: str) -> str:
    return _application_proof_upload_path(instance, "bonitaet")


def application_proof_upload_path(instance, _filename: str) -> str:
    category_directories = {
        ApplicationProofCategory.INCOME: "einkommen",
        ApplicationProofCategory.IDENTITY: "identitaet",
        ApplicationProofCategory.CREDIT_REPORT: "bonitaet",
    }
    return _application_proof_upload_path(
        instance.application,
        category_directories[instance.category],
    )


def calculate_photo_checksum(photo) -> str:
    """Return the SHA-256 checksum while preserving the current file position."""
    position = photo.tell()
    digest = hashlib.sha256()
    try:
        photo.seek(0)
        for chunk in photo.chunks():
            digest.update(chunk)
    finally:
        photo.seek(position)
    return digest.hexdigest()


class Geschlecht(models.TextChoices):
    MALE = "male", "male"
    FEMALE = "female", "female"
    DIVERS = "divers", "divers"


class WohnungStatus(models.TextChoices):
    TAKEN = "taken", "taken"
    FREE = "free", "free"
    BLOCKED = "blocked", "blocked"


class BewerbungStatus(models.TextChoices):
    OPEN = "open", "open"
    DECLINED = "declined", "declined"
    BLOCKED = "blocked", "blocked"


class ApplicationProofCategory(models.TextChoices):
    INCOME = "income", "Gehaltsnachweise"
    IDENTITY = "identity", "Identitätsnachweis"
    CREDIT_REPORT = "credit_report", "SCHUFA-Unterlage"


class StellplatzTyp(models.TextChoices):
    CAR = "car", "car"
    EV = "ev", "ev"
    BIKE = "bike", "bike"
    EBIKE = "ebike", "ebike"


class SchluesselStatus(models.TextChoices):
    LOST = "lost", "lost"
    IN_USE = "in_use", "in_use"
    BLOCKED = "blocked", "blocked"


class ProtokollTyp(models.TextChoices):
    MOVE_IN = "move_in", "move_in"
    MOVE_OUT = "move_out", "move_out"


class ProtokollStatus(models.TextChoices):
    OPEN = "open", "open"
    SIGNED = "signed", "signed"
    BLOCKED = "blocked", "blocked"


class MerkmalDatentyp(models.TextChoices):
    REIBEPUTZ = "Reibeputz", "Reibeputz"
    GEKALKT = "gekalkt", "gekalkt"
    OHNE_TAPETE = "ohne Tapete", "ohne Tapete"
    TAPEZIERFAEHIG = "tapezierfähig", "tapezierfähig"
    RAUFASER = "Raufaser", "Raufaser"
    TEXTILTAPETE = "Textiltapete", "Textiltapete"
    GEMUSTERTE_TAPETE = "gemusterte Tapete", "gemusterte Tapete"
    HOLZVERKLEIDUNG = "Holzverkleidung", "Holzverkleidung"
    GESTRICHEN = "gestrichen", "gestrichen"
    FLIESEN = "Fliesen", "Fliesen"
    STEIN = "Stein", "Stein"
    ORDENTLICH = "ordentlich", "ordentlich"
    UNSAUBER = "unsauber", "unsauber"
    NEU = "neu", "neu"
    NEUWERTIG = "neuwertig", "neuwertig"
    GEBRAUCHSSPUREN = "Gebrauchsspuren", "Gebrauchsspuren"
    SEHR_ABGENUTZT = "sehr abgenutzt", "sehr abgenutzt"
    GLATT_ZUGEGIPST = "glatt zugegipst", "glatt zugegipst"
    UNSAUBER_ZUGEGIPST = "unsauber zugegipst", "unsauber zugegipst"
    NICHT_ZUGEGIPST = "nicht zugegipst", "nicht zugegipst"
    TEPPICHBODEN = "Teppichboden", "Teppichboden"
    LAMINAT = "Laminat", "Laminat"
    PARKETT = "Parkett", "Parkett"
    PVC = "PVC", "PVC"
    KORK = "Kork", "Kork"
    ESTRICH_KEIN_BODEN = "Estrich / kein Boden", "Estrich / kein Boden"
    SAUBER = "sauber", "sauber"
    NICHT_SAUBER = "nicht sauber", "nicht sauber"
    OK = "OK", "OK"
    NICHT_OK = "nicht OK", "nicht OK"
    NICHT_TESTBAR = "nicht testbar", "nicht testbar"
    LAUT_MIETER_OK = "laut Mieter OK", "laut Mieter OK"
    VERFAERBUNGEN = "Verfärbungen", "Verfärbungen"
    BESENREIN = "besenrein", "besenrein"
    SAUBER_GEREINIGT = "sauber gereinigt", "sauber gereinigt"
    NICHT_BESENREIN = "nicht besenrein", "nicht besenrein"


class UebergabeStatus(models.TextChoices):
    RENOVATED = "renovated", "renovated"
    UNRENOVATED = "unrenovated", "unrenovated"


class AbnahmeStatus(models.TextChoices):
    ACCEPTED = "accepted", "accepted"
    ACCEPTED_WITH_RESERVATION = "accepted_with_reservation", "accepted_with_reservation"
    NOT_FULLY_ACCEPTED = "not_fully_accepted", "not_fully_accepted"


class Person(models.Model):
    person_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="person_profile",
        blank=True,
        null=True,
    )
    is_employee = models.BooleanField(default=False)
    wohnung = models.ForeignKey(
        "Wohnung",
        on_delete=models.SET_NULL,
        related_name="personen",
        blank=True,
        null=True,
    )
    vorname = models.CharField(max_length=255)
    nachname = models.CharField(max_length=255)
    titel = models.CharField(max_length=255, blank=True, default="")
    geschlecht = PostgreSQLEnumField(
        enum_type="geschlecht_enum",
        choices=Geschlecht.choices,
        max_length=255,
        blank=True,
        null=True,
    )
    email = models.EmailField(max_length=255, unique=True)
    telefonnummer = models.CharField(max_length=255, blank=True, default="")
    geburtsdatum = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "person"
        permissions = [
            ("access_applicant_area", "Kann auf den Bewerberbereich zugreifen"),
            ("access_tenant_area", "Kann auf den vorbereiteten Mieterbereich zugreifen"),
            ("access_employee_area", "Kann auf den Mitarbeiterbereich zugreifen"),
            ("manage_user_accounts", "Kann Konten und Zugriffsrechte verwalten"),
        ]

    def __str__(self) -> str:
        return f"{self.vorname} {self.nachname}"


class RegistrationVerification(models.Model):
    CODE_LENGTH = 6
    CODE_VALIDITY = timedelta(minutes=15)
    MAX_ATTEMPTS = 5
    RESEND_DELAY = timedelta(minutes=1)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registration_verification",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField()

    class Meta:
        db_table = "registration_verification"

    def issue_code(self) -> str:
        code = f"{secrets.randbelow(10**self.CODE_LENGTH):0{self.CODE_LENGTH}d}"
        while self.code_hash and check_password(code, self.code_hash):
            code = f"{secrets.randbelow(10**self.CODE_LENGTH):0{self.CODE_LENGTH}d}"
        now = timezone.now()
        self.code_hash = make_password(code)
        self.expires_at = now + self.CODE_VALIDITY
        self.attempts = 0
        self.last_sent_at = now
        return code

    def matches(self, code: str) -> bool:
        return (
            self.attempts < self.MAX_ATTEMPTS
            and self.expires_at >= timezone.now()
            and check_password(code, self.code_hash)
        )

    def can_resend(self) -> bool:
        return self.last_sent_at + self.RESEND_DELAY <= timezone.now()


class EmployeeLoginVerification(models.Model):
    CODE_LENGTH = 6
    CODE_VALIDITY = timedelta(minutes=15)
    MAX_ATTEMPTS = 5

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_login_verification",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "employee_login_verification"

    def issue_code(self) -> str:
        code = f"{secrets.randbelow(10**self.CODE_LENGTH):0{self.CODE_LENGTH}d}"
        while self.code_hash and check_password(code, self.code_hash):
            code = f"{secrets.randbelow(10**self.CODE_LENGTH):0{self.CODE_LENGTH}d}"
        self.code_hash = make_password(code)
        self.expires_at = timezone.now() + self.CODE_VALIDITY
        self.attempts = 0
        return code

    def matches(self, code: str) -> bool:
        return (
            self.attempts < self.MAX_ATTEMPTS
            and self.expires_at >= timezone.now()
            and check_password(code, self.code_hash)
        )


class AccountLoginThrottle(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_throttle",
    )
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "account_login_throttle"


class LoginIpThrottle(models.Model):
    ip_fingerprint = models.CharField(max_length=64, unique=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    window_started_at = models.DateTimeField()
    locked_until = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "login_ip_throttle"


class WohnungQuerySet(models.QuerySet):
    def available(self) -> "WohnungQuerySet":
        return self.filter(status=WohnungStatus.FREE)


class Wohnung(models.Model):
    objects = WohnungQuerySet.as_manager()

    wohnung_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    etage = models.SmallIntegerField(default=0)
    wohnungsnummer = models.CharField(max_length=255)
    gebaeudenummer = models.CharField(max_length=255)
    groesse_qm = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zimmeranzahl = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    kaltmiete = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warmmiete = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    kaution = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    barrierefrei = models.BooleanField(default=False)
    status = PostgreSQLEnumField(
        enum_type="wohnung_status_enum",
        choices=WohnungStatus.choices,
        default=WohnungStatus.FREE,
        max_length=255,
    )
    zaehlernummer_wasser_kalt = models.CharField(max_length=255, blank=True, default="")
    zaehlernummer_wasser_warm = models.CharField(max_length=255, blank=True, default="")
    zaehlernummer_heizung = models.CharField(max_length=255, blank=True, default="")
    zaehlernummer_strom = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wohnung"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(groesse_qm__gte=0), name="wohnung_groesse_nicht_negativ"
            ),
            models.CheckConstraint(
                condition=models.Q(zimmeranzahl__gte=0), name="wohnung_zimmer_nicht_negativ"
            ),
            models.CheckConstraint(
                condition=models.Q(kaltmiete__gte=0), name="wohnung_kaltmiete_nicht_negativ"
            ),
            models.CheckConstraint(
                condition=models.Q(warmmiete__gte=0), name="wohnung_warmmiete_nicht_negativ"
            ),
            models.CheckConstraint(
                condition=models.Q(kaution__gte=0), name="wohnung_kaution_nicht_negativ"
            ),
        ]

    def __str__(self) -> str:
        return f"Gebäude {self.gebaeudenummer}, Wohnung {self.wohnungsnummer}"


class Bewerbung(models.Model):
    bewerbung_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="bewerbungen")
    wohnung = models.ForeignKey(Wohnung, on_delete=models.CASCADE, related_name="bewerbungen")
    score = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    personenanzahl = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    ueber_mich = models.TextField()
    haustiere = models.BooleanField(default=False)
    barrierefreiheit_benoetigt = models.BooleanField(default=False)
    alternative_wohnung_akzeptiert = models.BooleanField(default=False)
    status = PostgreSQLEnumField(
        enum_type="bewerbung_status_enum",
        choices=BewerbungStatus.choices,
        default=BewerbungStatus.OPEN,
        max_length=255,
    )
    main_application_unlocked = models.BooleanField(
        default=False,
        help_text=(
            "Wird durch die Mitarbeiterseite nach Besichtigung und positiver Eignungsentscheidung "
            "gesetzt."
        ),
    )
    interest_withdrawn_at = models.DateTimeField(blank=True, null=True, editable=False)
    income_proof = models.FileField(upload_to=income_proof_upload_path, blank=True)
    income_proof_original_name = models.CharField(max_length=255, blank=True, default="")
    identity_proof = models.FileField(upload_to=identity_proof_upload_path, blank=True)
    identity_proof_original_name = models.CharField(max_length=255, blank=True, default="")
    credit_report_proof = models.FileField(
        upload_to=credit_report_proof_upload_path,
        blank=True,
    )
    credit_report_proof_original_name = models.CharField(max_length=255, blank=True, default="")
    submitted_at = models.DateTimeField(blank=True, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bewerbung"
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(
                    status=BewerbungStatus.OPEN,
                    interest_withdrawn_at__isnull=True,
                ),
                fields=("person",),
                name="bewerbung_eine_offene_pro_person",
            ),
            models.CheckConstraint(
                condition=models.Q(personenanzahl__gte=1),
                name="bewerbung_personenanzahl_mindestens_eins",
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=0), name="bewerbung_score_nicht_negativ"
            ),
        ]

    @property
    def main_application_accessible(self) -> bool:
        return (
            self.main_application_unlocked
            and self.status == BewerbungStatus.OPEN
            and self.interest_withdrawn_at is None
        )

    def get_applicant_status_display(self) -> str:
        if self.interest_withdrawn_at is not None:
            return "Zurückgezogen"
        if self.status == BewerbungStatus.DECLINED:
            return "Abgelehnt"
        if self.status == BewerbungStatus.BLOCKED:
            return "Gesperrt"
        if self.submitted_at is not None:
            return "Main-Bewerbung eingereicht"
        if self.main_application_unlocked:
            return "Main-Bewerbung freigeschaltet"
        return "In Bearbeitung"

    def get_applicant_next_step(self) -> str:
        if self.interest_withdrawn_at is not None:
            return "Für diese Bewerbung sind keine weiteren Schritte möglich."
        if self.status == BewerbungStatus.DECLINED:
            return "Die Bewerbung wurde beendet."
        if self.status == BewerbungStatus.BLOCKED:
            return "Die Bewerbung ist derzeit gesperrt."
        if self.submitted_at is not None:
            return "Bitte warten Sie auf die Rückmeldung des Mitarbeiters."
        if self.main_application_unlocked:
            return "Bitte reichen Sie die Main-Bewerbung mit allen drei Nachweisen ein."
        return "Warten Sie auf die nächste Rückmeldung zu Ihrer Bewerbung."


class ApplicationProof(models.Model):
    proof_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        Bewerbung,
        on_delete=models.CASCADE,
        related_name="proof_files",
    )
    category = models.CharField(max_length=32, choices=ApplicationProofCategory.choices)
    file = models.FileField(upload_to=application_proof_upload_path)
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "application_proof"
        ordering = ("uploaded_at", "proof_id")
        indexes = [
            models.Index(fields=("application", "category"), name="app_proof_category_idx"),
        ]


class ApplicationProofCleanup(models.Model):
    cleanup_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    storage_name = models.CharField(max_length=512, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "application_proof_cleanup"
        ordering = ("created_at", "cleanup_id")


class Stellplatz(models.Model):
    stellplatz_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    stellplatz_typ = PostgreSQLEnumField(
        enum_type="stellplatz_typ_enum",
        choices=StellplatzTyp.choices,
        max_length=255,
    )
    miete = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stellplatz"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(miete__gte=0), name="stellplatz_miete_nicht_negativ"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class StellplatzZuordnung(models.Model):
    stellplatz_zuordnung_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stellplatz = models.ForeignKey(Stellplatz, on_delete=models.CASCADE, related_name="zuordnungen")
    wohnung = models.ForeignKey(
        Wohnung, on_delete=models.CASCADE, related_name="stellplatz_zuordnungen"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stellplatz_zuordnung"
        constraints = [
            models.UniqueConstraint(fields=("stellplatz",), name="stellplatz_nur_einer_wohnung"),
        ]


class BewerbungStellplatz(models.Model):
    pk = models.CompositePrimaryKey("bewerbung_id", "stellplatz_id")
    bewerbung = models.ForeignKey(
        Bewerbung, on_delete=models.CASCADE, related_name="bewerbung_stellplaetze"
    )
    stellplatz = models.ForeignKey(
        Stellplatz, on_delete=models.CASCADE, related_name="bewerbung_stellplaetze"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bewerbung_stellplatz"


class Schluessel(models.Model):
    schluessel_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wohnung = models.ForeignKey(Wohnung, on_delete=models.CASCADE, related_name="schluessel")
    bezeichnung = models.CharField(max_length=255)
    anzahl = models.PositiveSmallIntegerField(default=0)
    aufschrift = models.CharField(max_length=255, blank=True, default="")
    status = PostgreSQLEnumField(
        enum_type="schluessel_status_enum",
        choices=SchluesselStatus.choices,
        max_length=255,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "schluessel"


class Protokoll(models.Model):
    protokoll_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wohnung = models.ForeignKey(Wohnung, on_delete=models.CASCADE, related_name="protokolle")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="protokolle")
    uebergabe_zeitpunkt = models.DateTimeField(default=timezone.now)
    vermieter_name = models.CharField(max_length=255, default="")
    mieter_zukuenftige_anschrift = models.TextField(blank=True, default="")
    protokoll_typ = PostgreSQLEnumField(
        enum_type="protokoll_typ_enum",
        choices=ProtokollTyp.choices,
        max_length=255,
    )
    status = PostgreSQLEnumField(
        enum_type="protokoll_status_enum",
        choices=ProtokollStatus.choices,
        default=ProtokollStatus.OPEN,
        max_length=255,
    )
    uebergabe_status = PostgreSQLEnumField(
        enum_type="uebergabe_status_enum",
        choices=UebergabeStatus.choices,
        max_length=255,
    )
    abnahme_status = PostgreSQLEnumField(
        enum_type="abnahme_status_enum",
        choices=AbnahmeStatus.choices,
        max_length=255,
    )
    zaehlerstand_wasser_kalt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zaehlerstand_wasser_warm = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zaehlerstand_heizung = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zaehlerstand_strom = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zaehlernummer_wasser_kalt = models.CharField(max_length=255, default="")
    zaehlernummer_wasser_warm = models.CharField(max_length=255, default="")
    zaehlernummer_heizung = models.CharField(max_length=255, default="")
    zaehlernummer_strom = models.CharField(max_length=255, default="")
    heizungsablesungen = models.TextField(default="")
    anlagenblaetter_anzahl = models.PositiveSmallIntegerField(default=0)
    kaution_nachweis_vorhanden = models.BooleanField(default=False)
    erste_miete_nachweis_vorhanden = models.BooleanField(default=False)
    nachbesserung_bis = models.DateField(blank=True, null=True)
    nachbesserung_beschreibung = models.TextField(blank=True, default="")
    schluessel_ueberprueft = models.BooleanField(default=False)
    bestaetigung_erklaert = models.BooleanField(default=False)
    bestaetigt_am = models.DateTimeField(blank=True, null=True)
    dokument_pfad = models.TextField(blank=True, default="")
    dokument_hash_sha256 = models.CharField(max_length=64, blank=True, default="")
    export_snapshot = models.JSONField(default=dict, blank=True)
    gesichert_am = models.DateTimeField(null=True, blank=True)
    nachtraeglich_gesichert = models.BooleanField(default=False)
    mieter_unterschrift_fehlt_grund = models.CharField(max_length=1000, blank=True, default="")
    abgeschlossen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abgeschlossene_protokolle",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "protokoll"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(zaehlerstand_wasser_kalt__gte=0),
                name="protokoll_wasser_kalt_nicht_negativ",
            ),
            models.CheckConstraint(
                condition=models.Q(zaehlerstand_wasser_warm__gte=0),
                name="protokoll_wasser_warm_nicht_negativ",
            ),
            models.CheckConstraint(
                condition=models.Q(zaehlerstand_heizung__gte=0),
                name="protokoll_heizung_nicht_negativ",
            ),
            models.CheckConstraint(
                condition=models.Q(zaehlerstand_strom__gte=0),
                name="protokoll_strom_nicht_negativ",
            ),
        ]


class ProtokollUnterschrift(models.Model):
    protokoll = models.ForeignKey(
        Protokoll, on_delete=models.CASCADE, related_name="unterschriften"
    )
    rolle = models.CharField(
        max_length=20, choices=[("mitarbeiter", "Mitarbeiter"), ("mieter", "Mieter")]
    )
    name = models.CharField(max_length=511)
    # Storage-relative private name; no public ImageField URL is exposed.
    datei = models.TextField()
    hash_sha256 = models.CharField(max_length=64)
    erfasst_am = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("protokoll", "rolle"), name="unterschrift_pro_rolle"),
            models.CheckConstraint(
                condition=models.Q(rolle__in=["mitarbeiter", "mieter"]),
                name="unterschrift_gueltige_rolle",
            ),
        ]


class ProtokollEntwurf(models.Model):
    protokoll_entwurf_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sitzungsschluessel = models.CharField(max_length=64)
    entwurfsbereich = models.CharField(max_length=255)
    daten = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "protokoll_entwurf"
        constraints = [
            models.UniqueConstraint(
                fields=("sitzungsschluessel", "entwurfsbereich"),
                name="protokoll_entwurf_eindeutig_pro_sitzung_und_bereich",
            )
        ]


class Raum(models.Model):
    raum_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wohnung = models.ForeignKey(Wohnung, on_delete=models.CASCADE, related_name="raeume")
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "raum"
        constraints = [
            models.UniqueConstraint(
                fields=("wohnung", "name"), name="raum_name_pro_wohnung_eindeutig"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Raumprotokoll(models.Model):
    raumprotokoll_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protokoll = models.ForeignKey(Protokoll, on_delete=models.CASCADE, related_name="raeume")
    raum = models.ForeignKey(Raum, on_delete=models.PROTECT, related_name="raumprotokolle")
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "raumprotokoll"
        constraints = [
            models.UniqueConstraint(
                fields=("protokoll", "raum"), name="raumprotokoll_eindeutig_pro_protokoll"
            )
        ]


class Merkmal(models.Model):
    merkmal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bereich = models.CharField(max_length=255)
    bezeichnung = models.CharField(max_length=255)
    datentyp = PostgreSQLEnumField(
        enum_type="merkmal_datentyp_enum",
        choices=MerkmalDatentyp.choices,
        max_length=255,
    )
    optionen = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merkmal"

    def __str__(self) -> str:
        return f"{self.bereich}: {self.bezeichnung}"


class RaumMerkmal(models.Model):
    raum_merkmal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raumprotokoll = models.ForeignKey(
        Raumprotokoll, on_delete=models.CASCADE, related_name="raum_merkmale"
    )
    merkmal = models.ForeignKey(Merkmal, on_delete=models.PROTECT, related_name="raum_merkmale")
    wert = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "raum_merkmal"
        constraints = [
            models.UniqueConstraint(
                fields=("raumprotokoll", "merkmal"),
                name="raum_merkmal_eindeutig_pro_raumprotokoll",
            )
        ]


class RaumMerkmalFoto(models.Model):
    raum_merkmal_foto_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raum_merkmal = models.ForeignKey(
        RaumMerkmal,
        on_delete=models.CASCADE,
        related_name="fotos",
    )
    datei = models.ImageField(upload_to=handover_photo_upload_path)
    content_type = models.CharField(max_length=50)
    dateigroesse = models.PositiveIntegerField()
    inhalt_hash_sha256 = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "raum_merkmal_foto"
        constraints = [
            models.UniqueConstraint(
                fields=("raum_merkmal", "inhalt_hash_sha256"),
                condition=~models.Q(inhalt_hash_sha256=""),
                name="raum_merkmal_foto_hash_eindeutig",
            )
        ]


class HandoverPhotoCleanup(models.Model):
    cleanup_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    storage_name = models.CharField(max_length=512, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "handover_photo_cleanup"
        ordering = ("created_at", "cleanup_id")


class HandoverArchiveCleanup(models.Model):
    cleanup_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    storage_name = models.CharField(max_length=512, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "handover_archive_cleanup"
        ordering = ("created_at", "cleanup_id")


class ProtokollSchluessel(models.Model):
    protokoll_schluessel_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    protokoll = models.ForeignKey(
        Protokoll, on_delete=models.CASCADE, related_name="protokoll_schluessel"
    )
    anzahl = models.PositiveSmallIntegerField()
    raum_bezeichnung = models.CharField(max_length=255)
    aufschrift = models.CharField(max_length=255, blank=True, default="")
    schluesselnummer = models.CharField(max_length=255, blank=True, default="")
    fehlt = models.BooleanField(default=False)
    fehlgrund = models.TextField(blank=True, default="")
    nachlieferung_am = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "protokoll_schluessel"
