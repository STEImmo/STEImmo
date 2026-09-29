from django.db import migrations, models


def uebernehme_miete_aus_zuordnung(apps, schema_editor):
    Stellplatz = apps.get_model("immobilien", "Stellplatz")
    StellplatzZuordnung = apps.get_model("immobilien", "StellplatzZuordnung")

    for zuordnung in StellplatzZuordnung.objects.all().iterator():
        Stellplatz.objects.filter(stellplatz_id=zuordnung.stellplatz_id).update(
            miete=zuordnung.miete
        )


def uebernehme_miete_in_zuordnung(apps, schema_editor):
    Stellplatz = apps.get_model("immobilien", "Stellplatz")
    StellplatzZuordnung = apps.get_model("immobilien", "StellplatzZuordnung")

    for stellplatz in Stellplatz.objects.all().iterator():
        StellplatzZuordnung.objects.filter(stellplatz_id=stellplatz.stellplatz_id).update(
            miete=stellplatz.miete
        )


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0002_stellplatz_zuordnung"),
    ]

    operations = [
        migrations.AddField(
            model_name="stellplatz",
            name="miete",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RunPython(
            uebernehme_miete_aus_zuordnung,
            reverse_code=uebernehme_miete_in_zuordnung,
        ),
        migrations.RemoveConstraint(
            model_name="stellplatzzuordnung",
            name="stellplatz_zuordnung_miete_nicht_negativ",
        ),
        migrations.RemoveField(
            model_name="stellplatzzuordnung",
            name="miete",
        ),
        migrations.AddConstraint(
            model_name="stellplatz",
            constraint=models.CheckConstraint(
                condition=models.Q(("miete__gte", 0)),
                name="stellplatz_miete_nicht_negativ",
            ),
        ),
    ]
