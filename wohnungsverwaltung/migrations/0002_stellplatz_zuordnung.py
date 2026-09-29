import uuid

import django.db.models.deletion
from django.db import migrations, models


def migrate_stellplaetze_to_zuordnungen(apps, schema_editor):
    Stellplatz = apps.get_model("immobilien", "Stellplatz")
    StellplatzZuordnung = apps.get_model("immobilien", "StellplatzZuordnung")

    StellplatzZuordnung.objects.bulk_create(
        [
            StellplatzZuordnung(
                stellplatz_id=stellplatz.stellplatz_id,
                wohnung_id=stellplatz.wohnung_id,
                miete=stellplatz.miete,
            )
            for stellplatz in Stellplatz.objects.all().iterator()
        ]
    )


def restore_stellplatz_fields(apps, schema_editor):
    Stellplatz = apps.get_model("immobilien", "Stellplatz")
    StellplatzZuordnung = apps.get_model("immobilien", "StellplatzZuordnung")

    for zuordnung in StellplatzZuordnung.objects.all().iterator():
        Stellplatz.objects.filter(stellplatz_id=zuordnung.stellplatz_id).update(
            wohnung_id=zuordnung.wohnung_id,
            miete=zuordnung.miete,
        )


DROP_LEGACY_STELLPLATZ_COLUMNS = """
ALTER TABLE stellplatz DROP CONSTRAINT stellplatz_miete_nicht_negativ;
ALTER TABLE stellplatz DROP COLUMN wohnung_id;
ALTER TABLE stellplatz DROP COLUMN miete;
"""

RESTORE_LEGACY_STELLPLATZ_COLUMNS = """
ALTER TABLE stellplatz
    ADD COLUMN wohnung_id uuid NULL REFERENCES wohnung (wohnung_id) ON DELETE CASCADE;
ALTER TABLE stellplatz ADD COLUMN miete numeric(12, 2) NULL;
ALTER TABLE stellplatz
    ADD CONSTRAINT stellplatz_miete_nicht_negativ CHECK (miete >= 0);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StellplatzZuordnung",
            fields=[
                (
                    "stellplatz_zuordnung_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("miete", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "stellplatz",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="zuordnungen",
                        to="immobilien.stellplatz",
                    ),
                ),
                (
                    "wohnung",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stellplatz_zuordnungen",
                        to="immobilien.wohnung",
                    ),
                ),
            ],
            options={
                "db_table": "stellplatz_zuordnung",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("stellplatz",), name="stellplatz_nur_einer_wohnung"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("miete__gte", 0)),
                        name="stellplatz_zuordnung_miete_nicht_negativ",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            migrate_stellplaetze_to_zuordnungen,
            reverse_code=restore_stellplatz_fields,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=DROP_LEGACY_STELLPLATZ_COLUMNS,
                    reverse_sql=RESTORE_LEGACY_STELLPLATZ_COLUMNS,
                )
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="stellplatz",
                    name="stellplatz_miete_nicht_negativ",
                ),
                migrations.RemoveField(
                    model_name="stellplatz",
                    name="wohnung",
                ),
                migrations.RemoveField(
                    model_name="stellplatz",
                    name="miete",
                ),
            ],
        ),
    ]
