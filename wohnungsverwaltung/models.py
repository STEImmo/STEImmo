import uuid

from django.db import models
from django.utils import timezone

from .fields import PostgreSQLEnumField


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

    def __str__(self) -> str:
        return f"{self.vorname} {self.nachname}"


class Wohnung(models.Model):
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
    personenanzahl = models.PositiveSmallIntegerField(default=0)
    ueber_mich = models.TextField(blank=True, default="")
    haustiere = models.BooleanField(default=False)
    barrierefreiheit_benoetigt = models.BooleanField(default=False)
    alternative_wohnung_akzeptiert = models.BooleanField(default=False)
    status = PostgreSQLEnumField(
        enum_type="bewerbung_status_enum",
        choices=BewerbungStatus.choices,
        default=BewerbungStatus.OPEN,
        max_length=255,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bewerbung"
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(status=BewerbungStatus.OPEN),
                fields=("person",),
                name="bewerbung_eine_offene_pro_person",
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=0), name="bewerbung_score_nicht_negativ"
            ),
        ]


class Stellplatz(models.Model):
    stellplatz_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wohnung = models.ForeignKey(Wohnung, on_delete=models.CASCADE, related_name="stellplaetze")
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
            )
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


class Raumprotokoll(models.Model):
    raumprotokoll_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protokoll = models.ForeignKey(Protokoll, on_delete=models.CASCADE, related_name="raeume")
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "raumprotokoll"


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
