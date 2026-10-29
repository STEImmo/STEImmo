from decimal import Decimal

from django.db import migrations


def correct_attic_areas(apps, schema_editor):
    """Confirmed amendment to #165: the older letter's 111 m² is incorrect."""
    Wohnung = apps.get_model("immobilien", "Wohnung")
    units = Wohnung.objects.using(schema_editor.connection.alias).filter(
        gebaeudenummer="1", etage=4
    )
    updates = []
    for number, area in (("401", "92.90"), ("402", "64.90")):
        matching = list(units.filter(wohnungsnummer=number))
        if len(matching) > 1:
            raise RuntimeError(f"Mehrdeutige Wohnungszuordnung für Dachgeschosswohnung {number}.")
        if matching:
            updates.append((matching[0].pk, Decimal(area)))
    for unit_id, area in updates:
        units.filter(pk=unit_id).update(groesse_qm=area)


class Migration(migrations.Migration):
    dependencies = [("immobilien", "0033_correct_confirmed_room_counts")]

    operations = [
        migrations.RunPython(correct_attic_areas, migrations.RunPython.noop),
    ]
