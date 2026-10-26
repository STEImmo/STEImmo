from decimal import Decimal

from django.db import migrations

# Confirmed source: issue #158, screenshot supplied on 24 October 2026.
# Keep this historical migration independent of mutable setup data.
ROOM_COUNTS = (
    (0, "1", "1"),
    (0, "2", "1"),
    (0, "3", "1"),
    (0, "4", "2"),
    (0, "5", "2"),
    (1, "101", "1"),
    (1, "102", "1"),
    (1, "103", "2"),
    (1, "104", "1"),
    (1, "105", "2"),
    (1, "106", "2"),
    (2, "201", "1"),
    (2, "202", "1"),
    (2, "203", "2"),
    (2, "204", "1"),
    (2, "205", "2"),
    (2, "206", "2"),
    (3, "301", "1"),
    (3, "302", "1"),
    (3, "303", "2"),
    (3, "304", "1"),
    (3, "305", "2"),
    (3, "306", "2"),
    (4, "401", "3.5"),
    (4, "402", "3"),
)


def assign_confirmed_room_counts(apps, schema_editor):
    Wohnung = apps.get_model("immobilien", "Wohnung")
    units = Wohnung.objects.using(schema_editor.connection.alias).filter(gebaeudenummer="1")
    updates = []
    for floor, number, count in ROOM_COUNTS:
        numbers = (number, number.zfill(3)) if floor == 0 else (number,)
        matching = list(units.filter(etage=floor, wohnungsnummer__in=numbers))
        if len(matching) > 1:
            raise RuntimeError(
                f"Mehrdeutige Wohnungszuordnung für Gebäude 1, Etage {floor}, Wohnung {number}. "
                "Doppelte Nummern vor dem erneuten Migrieren bereinigen."
            )
        if matching:
            updates.append((matching[0].pk, Decimal(count)))

    # Validate all assignments before updating any data; preserve every other field.
    for unit_id, count in updates:
        units.filter(pk=unit_id).update(zimmeranzahl=count)


class Migration(migrations.Migration):
    dependencies = [("immobilien", "0028_viewing_appointments")]

    operations = [
        # Original values are unknown; rolling back deliberately preserves corrected data.
        migrations.RunPython(assign_confirmed_room_counts, migrations.RunPython.noop),
    ]
