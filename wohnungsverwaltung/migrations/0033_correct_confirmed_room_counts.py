from decimal import Decimal

from django.db import migrations


def correct_room_counts(apps, schema_editor):
    """Apply the two confirmed corrections from issue #165 once."""
    Wohnung = apps.get_model("immobilien", "Wohnung")
    units = Wohnung.objects.using(schema_editor.connection.alias).filter(gebaeudenummer="1")
    updates = []
    for floor, numbers, count in ((0, ("2", "002"), "2"), (4, ("401",), "3")):
        matching = list(units.filter(etage=floor, wohnungsnummer__in=numbers))
        if len(matching) > 1:
            raise RuntimeError(
                f"Mehrdeutige Wohnungszuordnung für Gebäude 1, Etage {floor}, "
                f"Wohnung {numbers[-1]}. Doppelte Nummern vor dem Migrieren bereinigen."
            )
        if matching:
            updates.append((matching[0].pk, Decimal(count)))
    for unit_id, count in updates:
        units.filter(pk=unit_id).update(zimmeranzahl=count)


class Migration(migrations.Migration):
    dependencies = [("immobilien", "0032_merge_viewing_proposals_and_main")]

    operations = [
        # Do not restore outdated counts or overwrite later edits on rollback.
        migrations.RunPython(correct_room_counts, migrations.RunPython.noop),
    ]
