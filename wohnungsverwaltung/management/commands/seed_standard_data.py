from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from wohnungsverwaltung.building_plans import APARTMENTS
from wohnungsverwaltung.models import (
    AbnahmeStatus,
    Geschlecht,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollStatus,
    ProtokollTyp,
    Raum,
    RaumMerkmal,
    Raumprotokoll,
    Schluessel,
    SchluesselStatus,
    UebergabeStatus,
    Wohnung,
    WohnungStatus,
)

STANDARD_PEOPLE = [
    {
        "vorname": "Nora",
        "nachname": "Neumann",
        "email": "nora.neumann@example.test",
        "telefonnummer": "+49 30 555 0101",
        "geschlecht": Geschlecht.FEMALE,
        "is_employee": False,
    },
    {
        "vorname": "Ben",
        "nachname": "Berger",
        "email": "ben.berger@example.test",
        "telefonnummer": "+49 30 555 0102",
        "geschlecht": Geschlecht.MALE,
        "is_employee": False,
    },
    {
        "vorname": "Lara",
        "nachname": "Lorenz",
        "email": "lara.lorenz@example.test",
        "telefonnummer": "+49 30 555 0103",
        "geschlecht": Geschlecht.FEMALE,
        "is_employee": False,
    },
    {
        "vorname": "David",
        "nachname": "Dahl",
        "email": "david.dahl@example.test",
        "telefonnummer": "+49 30 555 0104",
        "geschlecht": Geschlecht.MALE,
        "is_employee": False,
    },
    {
        "vorname": "Emilia",
        "nachname": "Engel",
        "email": "emilia.engel@example.test",
        "telefonnummer": "+49 30 555 0105",
        "geschlecht": Geschlecht.FEMALE,
        "is_employee": False,
    },
    {
        "vorname": "Jonas",
        "nachname": "Jansen",
        "email": "jonas.jansen@example.test",
        "telefonnummer": "+49 30 555 0106",
        "geschlecht": Geschlecht.MALE,
        "is_employee": False,
    },
]

STANDARD_EMPLOYEES = [
    {
        "vorname": "Mira",
        "nachname": "Verwaltung",
        "email": "mira.verwaltung@example.test",
        "telefonnummer": "+49 30 555 0199",
        "geschlecht": Geschlecht.FEMALE,
        "is_employee": True,
    },
    {
        "vorname": "Leon",
        "nachname": "Verwaltung",
        "email": "leon.verwaltung@example.test",
        "telefonnummer": "+49 30 555 0200",
        "geschlecht": Geschlecht.MALE,
        "is_employee": True,
    },
]

WALL_FEATURES = [
    ("Reibeputz", MerkmalDatentyp.REIBEPUTZ, []),
    ("Gekalkt", MerkmalDatentyp.GEKALKT, []),
    ("Ohne Tapete", MerkmalDatentyp.OHNE_TAPETE, []),
    ("Tapezierfähig", MerkmalDatentyp.TAPEZIERFAEHIG, []),
    ("Raufaser", MerkmalDatentyp.RAUFASER, []),
    ("Textiltapete", MerkmalDatentyp.TEXTILTAPETE, []),
    ("Gemusterte Tapete", MerkmalDatentyp.GEMUSTERTE_TAPETE, []),
    ("Holzverkleidung", MerkmalDatentyp.HOLZVERKLEIDUNG, []),
    ("Gestrichen in Farbe", MerkmalDatentyp.GESTRICHEN, ["Farbe"]),
    ("Ordentlich", MerkmalDatentyp.ORDENTLICH, []),
    ("Unsauber", MerkmalDatentyp.UNSAUBER, []),
    ("Fliesen", MerkmalDatentyp.FLIESEN, []),
    ("Stein", MerkmalDatentyp.STEIN, []),
    ("Neu", MerkmalDatentyp.NEU, []),
    ("Neuwertig", MerkmalDatentyp.NEUWERTIG, []),
    ("Gebrauchsspuren", MerkmalDatentyp.GEBRAUCHSSPUREN, []),
    ("Sehr abgenutzt", MerkmalDatentyp.SEHR_ABGENUTZT, []),
    ("Schäden", MerkmalDatentyp.NICHT_OK, ["Beschreibung"]),
    ("Anzahl der Bohr- und Nagellöcher", MerkmalDatentyp.OK, ["Anzahl"]),
    ("Bohrlöcher sind glatt zugegipst", MerkmalDatentyp.GLATT_ZUGEGIPST, []),
    ("Bohrlöcher sind unsauber zugegipst", MerkmalDatentyp.UNSAUBER_ZUGEGIPST, []),
]


class Command(BaseCommand):
    help = "Creates idempotent fictitious standard data for local STEImmo development."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        units = self._create_units()
        people = self._create_people(units)
        self._create_wall_features()
        self._create_unit_keys(units)
        self._create_handover_protocols(units, people)
        self.stdout.write(
            self.style.SUCCESS(
                "Standarddaten bereit: "
                f"{Wohnung.objects.count()} Wohnungen, "
                f"{Person.objects.count()} Personen und "
                f"{Protokoll.objects.count()} Übergabeprotokolle."
            )
        )

    def _create_people(self, units: dict[str, Wohnung]) -> dict[str, Person]:
        people = {}
        for person_data, unit in zip(STANDARD_PEOPLE, units.values()):
            person, _ = Person.objects.update_or_create(
                email=person_data["email"],
                defaults={
                    **person_data,
                    "wohnung": unit,
                },
            )
            people[person.email] = person
        for employee_data in STANDARD_EMPLOYEES:
            employee, _ = Person.objects.update_or_create(
                email=employee_data["email"],
                defaults={
                    **employee_data,
                    "wohnung": None,
                },
            )
            people[employee.email] = employee
        return people

    def _create_units(self) -> dict[str, Wohnung]:
        if Wohnung.objects.filter(wohnungsnummer__in=[row[0] for row in APARTMENTS]).exists():
            raise CommandError(
                "Alte Beispielnummern vorhanden. Zuerst sync_building_inventory --apply ausführen."
            )
        units = {}
        for number, (legacy_number, unit_number, floor, area) in enumerate(APARTMENTS, start=1):
            size = Decimal(area)
            rooms = Decimal("1.50") + Decimal((number - 1) % 4) * Decimal("0.50")
            rent = Decimal("720.00") + Decimal(number * 18)
            status = (
                WohnungStatus.BLOCKED
                if number == 25
                else WohnungStatus.TAKEN
                if number % 3 == 0
                else WohnungStatus.FREE
            )
            unit, _ = Wohnung.objects.update_or_create(
                gebaeudenummer="1",
                wohnungsnummer=unit_number,
                defaults={
                    "etage": floor,
                    "groesse_qm": size,
                    "zimmeranzahl": rooms,
                    "kaltmiete": rent,
                    "warmmiete": rent + Decimal("170.00"),
                    "kaution": rent * 3,
                    "barrierefrei": number in {1, 6, 11, 16, 21},
                    "status": status,
                    "zaehlernummer_wasser_kalt": f"KW-1-{number:02d}",
                    "zaehlernummer_wasser_warm": f"WW-1-{number:02d}",
                    "zaehlernummer_heizung": f"HZ-1-{number:02d}",
                    "zaehlernummer_strom": f"ST-1-{number:02d}",
                },
            )
            units[legacy_number] = unit
        return units

    def _create_unit_keys(self, units: dict[str, Wohnung]) -> None:
        for unit in units.values():
            Schluessel.objects.update_or_create(
                wohnung=unit,
                bezeichnung="Wohnungsschlüssel",
                defaults={
                    "anzahl": 2,
                    "aufschrift": f"Haus 1 / {unit.wohnungsnummer}",
                    "status": SchluesselStatus.IN_USE,
                },
            )

    def _create_wall_features(self) -> None:
        for name, data_type, options in WALL_FEATURES:
            Merkmal.objects.update_or_create(
                bereich="Wände",
                bezeichnung=name,
                defaults={"datentyp": data_type, "optionen": options},
            )

    def _create_handover_protocols(
        self, units: dict[str, Wohnung], people: dict[str, Person]
    ) -> None:
        landlord_name = str(people["mira.verwaltung@example.test"])
        signed_protocol = self._get_or_create_protocol(
            unit=units["1.01"],
            person=people["nora.neumann@example.test"],
            landlord_name=landlord_name,
            protocol_type=ProtokollTyp.MOVE_IN,
            status=ProtokollStatus.SIGNED,
            timestamp=timezone.make_aware(datetime(2026, 9, 1, 10, 0)),
        )
        self._create_protocol_details(signed_protocol, confirmed=True)

        open_protocol = self._get_or_create_protocol(
            unit=units["1.02"],
            person=people["ben.berger@example.test"],
            landlord_name=landlord_name,
            protocol_type=ProtokollTyp.MOVE_OUT,
            status=ProtokollStatus.OPEN,
            timestamp=timezone.make_aware(datetime(2026, 9, 25, 14, 30)),
        )
        self._create_protocol_details(open_protocol, confirmed=False)

    def _get_or_create_protocol(
        self,
        *,
        unit: Wohnung,
        person: Person,
        landlord_name: str,
        protocol_type: str,
        status: str,
        timestamp: datetime,
    ) -> Protokoll:
        protocol, _ = Protokoll.objects.get_or_create(
            wohnung=unit,
            person=person,
            protokoll_typ=protocol_type,
            defaults={
                "status": status,
                "uebergabe_zeitpunkt": timestamp,
                "vermieter_name": landlord_name,
                "mieter_zukuenftige_anschrift": "Beispielallee 12\n12345 Musterstadt",
                "uebergabe_status": UebergabeStatus.RENOVATED,
                "abnahme_status": AbnahmeStatus.ACCEPTED_WITH_RESERVATION,
                "zaehlernummer_wasser_kalt": unit.zaehlernummer_wasser_kalt,
                "zaehlernummer_wasser_warm": unit.zaehlernummer_wasser_warm,
                "zaehlernummer_heizung": unit.zaehlernummer_heizung,
                "zaehlernummer_strom": unit.zaehlernummer_strom,
                "zaehlerstand_wasser_kalt": Decimal("124.50"),
                "zaehlerstand_wasser_warm": Decimal("83.25"),
                "zaehlerstand_heizung": Decimal("523.70"),
                "zaehlerstand_strom": Decimal("1987.40"),
                "heizungsablesungen": "IE: 173, IA: 96, Ib: 254",
                "anlagenblaetter_anzahl": 2,
                "kaution_nachweis_vorhanden": protocol_type == ProtokollTyp.MOVE_IN,
                "erste_miete_nachweis_vorhanden": protocol_type == ProtokollTyp.MOVE_IN,
                "nachbesserung_bis": None,
                "nachbesserung_beschreibung": "",
                "schluessel_ueberprueft": status == ProtokollStatus.SIGNED,
                "bestaetigung_erklaert": status == ProtokollStatus.SIGNED,
                "bestaetigt_am": timestamp if status == ProtokollStatus.SIGNED else None,
            },
        )
        return protocol

    def _create_protocol_details(self, protocol: Protokoll, *, confirmed: bool) -> None:
        key, _ = ProtokollSchluessel.objects.get_or_create(
            protokoll=protocol,
            raum_bezeichnung="Wohnungstür",
            schluesselnummer=f"H1-{protocol.wohnung.wohnungsnummer}",
            defaults={
                "anzahl": 2,
                "aufschrift": "Wohnung",
                "fehlt": False,
            },
        )
        if confirmed and key.anzahl != 2:
            key.anzahl = 2
            key.save(update_fields=["anzahl"])

        master_room, _ = Raum.objects.get_or_create(
            wohnung=protocol.wohnung,
            name="Wohnzimmer",
        )
        room, _ = Raumprotokoll.objects.get_or_create(
            protokoll=protocol,
            raum=master_room,
            defaults={"name": master_room.name},
        )
        metric, _ = Merkmal.objects.get_or_create(
            bereich="Wohnzimmer",
            bezeichnung="Fenster",
            datentyp=MerkmalDatentyp.OK,
        )
        RaumMerkmal.objects.get_or_create(
            raumprotokoll=room,
            merkmal=metric,
            defaults={"wert": {"text": "Keine sichtbaren Schäden, Funktion geprüft."}},
        )
