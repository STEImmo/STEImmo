import uuid

import django.db.models.deletion
from django.db import migrations, models

import wohnungsverwaltung.fields

CREATE_ENUM_TYPES = """
CREATE TYPE geschlecht_enum AS ENUM ('male', 'female', 'divers');
CREATE TYPE wohnung_status_enum AS ENUM ('taken', 'free', 'blocked');
CREATE TYPE bewerbung_status_enum AS ENUM ('open', 'declined', 'blocked');
CREATE TYPE stellplatz_typ_enum AS ENUM ('car', 'ev', 'bike', 'ebike');
CREATE TYPE schluessel_status_enum AS ENUM ('lost', 'in_use', 'blocked');
CREATE TYPE protokoll_typ_enum AS ENUM ('move_in', 'move_out');
CREATE TYPE protokoll_status_enum AS ENUM ('open', 'signed', 'blocked');
CREATE TYPE merkmal_datentyp_enum AS ENUM (
    'Reibeputz',
    'gekalkt',
    'ohne Tapete',
    'tapezierfähig',
    'Raufaser',
    'Textiltapete',
    'gemusterte Tapete',
    'Holzverkleidung',
    'gestrichen',
    'Fliesen',
    'Stein',
    'ordentlich',
    'unsauber',
    'neu',
    'neuwertig',
    'Gebrauchsspuren',
    'sehr abgenutzt',
    'glatt zugegipst',
    'unsauber zugegipst',
    'nicht zugegipst',
    'Teppichboden',
    'Laminat',
    'Parkett',
    'PVC',
    'Kork',
    'Estrich / kein Boden',
    'sauber',
    'nicht sauber',
    'OK',
    'nicht OK',
    'nicht testbar',
    'laut Mieter OK',
    'Verfärbungen',
    'besenrein',
    'sauber gereinigt',
    'nicht besenrein'
);
CREATE TYPE uebergabe_status_enum AS ENUM ('renovated', 'unrenovated');
CREATE TYPE abnahme_status_enum AS ENUM (
    'accepted',
    'accepted_with_reservation',
    'not_fully_accepted'
);
"""

DROP_ENUM_TYPES = """
DROP TYPE IF EXISTS abnahme_status_enum;
DROP TYPE IF EXISTS uebergabe_status_enum;
DROP TYPE IF EXISTS merkmal_datentyp_enum;
DROP TYPE IF EXISTS protokoll_status_enum;
DROP TYPE IF EXISTS protokoll_typ_enum;
DROP TYPE IF EXISTS schluessel_status_enum;
DROP TYPE IF EXISTS stellplatz_typ_enum;
DROP TYPE IF EXISTS bewerbung_status_enum;
DROP TYPE IF EXISTS wohnung_status_enum;
DROP TYPE IF EXISTS geschlecht_enum;
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(CREATE_ENUM_TYPES, reverse_sql=DROP_ENUM_TYPES),
        migrations.CreateModel(
            name="Person",
            fields=[
                (
                    "person_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("vorname", models.CharField(max_length=255)),
                ("nachname", models.CharField(max_length=255)),
                ("titel", models.CharField(blank=True, default="", max_length=255)),
                (
                    "geschlecht",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        blank=True,
                        choices=[
                            ("male", "male"),
                            ("female", "female"),
                            ("divers", "divers"),
                        ],
                        enum_type="geschlecht_enum",
                        max_length=255,
                        null=True,
                    ),
                ),
                ("email", models.EmailField(max_length=255, unique=True)),
                ("telefonnummer", models.CharField(blank=True, default="", max_length=255)),
                ("geburtsdatum", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "person"},
        ),
        migrations.CreateModel(
            name="Wohnung",
            fields=[
                (
                    "wohnung_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("etage", models.SmallIntegerField(default=0)),
                ("wohnungsnummer", models.CharField(max_length=255)),
                ("gebaeudenummer", models.CharField(max_length=255)),
                ("groesse_qm", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("zimmeranzahl", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("kaltmiete", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("warmmiete", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("kaution", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("barrierefrei", models.BooleanField(default=False)),
                (
                    "status",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("taken", "taken"),
                            ("free", "free"),
                            ("blocked", "blocked"),
                        ],
                        default="free",
                        enum_type="wohnung_status_enum",
                        max_length=255,
                    ),
                ),
                (
                    "zaehlernummer_wasser_kalt",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "zaehlernummer_wasser_warm",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "zaehlernummer_heizung",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "zaehlernummer_strom",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "wohnung",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("groesse_qm__gte", 0)),
                        name="wohnung_groesse_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("zimmeranzahl__gte", 0)),
                        name="wohnung_zimmer_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("kaltmiete__gte", 0)),
                        name="wohnung_kaltmiete_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("warmmiete__gte", 0)),
                        name="wohnung_warmmiete_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("kaution__gte", 0)),
                        name="wohnung_kaution_nicht_negativ",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Bewerbung",
            fields=[
                (
                    "bewerbung_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("score", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("personenanzahl", models.PositiveSmallIntegerField(default=0)),
                ("ueber_mich", models.TextField(blank=True, default="")),
                ("haustiere", models.BooleanField(default=False)),
                ("barrierefreiheit_benoetigt", models.BooleanField(default=False)),
                ("alternative_wohnung_akzeptiert", models.BooleanField(default=False)),
                (
                    "status",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("open", "open"),
                            ("declined", "declined"),
                            ("blocked", "blocked"),
                        ],
                        default="open",
                        enum_type="bewerbung_status_enum",
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bewerbungen",
                        to="immobilien.person",
                    ),
                ),
                (
                    "wohnung",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bewerbungen",
                        to="immobilien.wohnung",
                    ),
                ),
            ],
            options={
                "db_table": "bewerbung",
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "open")),
                        fields=("person",),
                        name="bewerbung_eine_offene_pro_person",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("score__gte", 0)),
                        name="bewerbung_score_nicht_negativ",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Stellplatz",
            fields=[
                (
                    "stellplatz_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "stellplatz_typ",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("car", "car"),
                            ("ev", "ev"),
                            ("bike", "bike"),
                            ("ebike", "ebike"),
                        ],
                        enum_type="stellplatz_typ_enum",
                        max_length=255,
                    ),
                ),
                ("miete", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "wohnung",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stellplaetze",
                        to="immobilien.wohnung",
                    ),
                ),
            ],
            options={
                "db_table": "stellplatz",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("miete__gte", 0)),
                        name="stellplatz_miete_nicht_negativ",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Schluessel",
            fields=[
                (
                    "schluessel_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("bezeichnung", models.CharField(max_length=255)),
                ("anzahl", models.PositiveSmallIntegerField(default=0)),
                ("aufschrift", models.CharField(blank=True, default="", max_length=255)),
                (
                    "status",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("lost", "lost"),
                            ("in_use", "in_use"),
                            ("blocked", "blocked"),
                        ],
                        enum_type="schluessel_status_enum",
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "wohnung",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schluessel",
                        to="immobilien.wohnung",
                    ),
                ),
            ],
            options={"db_table": "schluessel"},
        ),
        migrations.CreateModel(
            name="Protokoll",
            fields=[
                (
                    "protokoll_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "protokoll_typ",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[("move_in", "move_in"), ("move_out", "move_out")],
                        enum_type="protokoll_typ_enum",
                        max_length=255,
                    ),
                ),
                (
                    "status",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("open", "open"),
                            ("signed", "signed"),
                            ("blocked", "blocked"),
                        ],
                        default="open",
                        enum_type="protokoll_status_enum",
                        max_length=255,
                    ),
                ),
                (
                    "uebergabe_status",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[("renovated", "renovated"), ("unrenovated", "unrenovated")],
                        enum_type="uebergabe_status_enum",
                        max_length=255,
                    ),
                ),
                (
                    "abnahme_status",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("accepted", "accepted"),
                            ("accepted_with_reservation", "accepted_with_reservation"),
                            ("not_fully_accepted", "not_fully_accepted"),
                        ],
                        enum_type="abnahme_status_enum",
                        max_length=255,
                    ),
                ),
                (
                    "zaehlerstand_wasser_kalt",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "zaehlerstand_wasser_warm",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "zaehlerstand_heizung",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "zaehlerstand_strom",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                ("dokument_pfad", models.TextField(blank=True, default="")),
                ("dokument_hash_sha256", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protokolle",
                        to="immobilien.person",
                    ),
                ),
                (
                    "wohnung",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protokolle",
                        to="immobilien.wohnung",
                    ),
                ),
            ],
            options={
                "db_table": "protokoll",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("zaehlerstand_wasser_kalt__gte", 0)),
                        name="protokoll_wasser_kalt_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("zaehlerstand_wasser_warm__gte", 0)),
                        name="protokoll_wasser_warm_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("zaehlerstand_heizung__gte", 0)),
                        name="protokoll_heizung_nicht_negativ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("zaehlerstand_strom__gte", 0)),
                        name="protokoll_strom_nicht_negativ",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Raumprotokoll",
            fields=[
                (
                    "raumprotokoll_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "protokoll",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="raeume",
                        to="immobilien.protokoll",
                    ),
                ),
            ],
            options={"db_table": "raumprotokoll"},
        ),
        migrations.CreateModel(
            name="Merkmal",
            fields=[
                (
                    "merkmal_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("bereich", models.CharField(max_length=255)),
                ("bezeichnung", models.CharField(max_length=255)),
                (
                    "datentyp",
                    wohnungsverwaltung.fields.PostgreSQLEnumField(
                        choices=[
                            ("Reibeputz", "Reibeputz"),
                            ("gekalkt", "gekalkt"),
                            ("ohne Tapete", "ohne Tapete"),
                            ("tapezierfähig", "tapezierfähig"),
                            ("Raufaser", "Raufaser"),
                            ("Textiltapete", "Textiltapete"),
                            ("gemusterte Tapete", "gemusterte Tapete"),
                            ("Holzverkleidung", "Holzverkleidung"),
                            ("gestrichen", "gestrichen"),
                            ("Fliesen", "Fliesen"),
                            ("Stein", "Stein"),
                            ("ordentlich", "ordentlich"),
                            ("unsauber", "unsauber"),
                            ("neu", "neu"),
                            ("neuwertig", "neuwertig"),
                            ("Gebrauchsspuren", "Gebrauchsspuren"),
                            ("sehr abgenutzt", "sehr abgenutzt"),
                            ("glatt zugegipst", "glatt zugegipst"),
                            ("unsauber zugegipst", "unsauber zugegipst"),
                            ("nicht zugegipst", "nicht zugegipst"),
                            ("Teppichboden", "Teppichboden"),
                            ("Laminat", "Laminat"),
                            ("Parkett", "Parkett"),
                            ("PVC", "PVC"),
                            ("Kork", "Kork"),
                            ("Estrich / kein Boden", "Estrich / kein Boden"),
                            ("sauber", "sauber"),
                            ("nicht sauber", "nicht sauber"),
                            ("OK", "OK"),
                            ("nicht OK", "nicht OK"),
                            ("nicht testbar", "nicht testbar"),
                            ("laut Mieter OK", "laut Mieter OK"),
                            ("Verfärbungen", "Verfärbungen"),
                            ("besenrein", "besenrein"),
                            ("sauber gereinigt", "sauber gereinigt"),
                            ("nicht besenrein", "nicht besenrein"),
                        ],
                        enum_type="merkmal_datentyp_enum",
                        max_length=255,
                    ),
                ),
                ("optionen", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "merkmal"},
        ),
        migrations.CreateModel(
            name="RaumMerkmal",
            fields=[
                (
                    "raum_merkmal_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("wert", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "merkmal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="raum_merkmale",
                        to="immobilien.merkmal",
                    ),
                ),
                (
                    "raumprotokoll",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="raum_merkmale",
                        to="immobilien.raumprotokoll",
                    ),
                ),
            ],
            options={"db_table": "raum_merkmal"},
        ),
        migrations.CreateModel(
            name="BewerbungStellplatz",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "bewerbung_id",
                        "stellplatz_id",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "bewerbung",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bewerbung_stellplaetze",
                        to="immobilien.bewerbung",
                    ),
                ),
                (
                    "stellplatz",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bewerbung_stellplaetze",
                        to="immobilien.stellplatz",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "bewerbung_stellplatz"},
        ),
    ]
