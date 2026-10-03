from django.db import migrations, models
from django.db.models import Count


def ensure_unique_room_features(apps, schema_editor):
    RaumMerkmal = apps.get_model("immobilien", "RaumMerkmal")
    duplicate = (
        RaumMerkmal.objects.values("raumprotokoll_id", "merkmal_id")
        .annotate(entry_count=Count("pk"))
        .filter(entry_count__gt=1)
        .order_by("raumprotokoll_id", "merkmal_id")
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Doppelte Prüfpunkte müssen vor der Migration bereinigt werden "
            f"(Raumprotokoll {duplicate['raumprotokoll_id']}, "
            f"Merkmal {duplicate['merkmal_id']})."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0016_merge_20261001_2020"),
    ]

    operations = [
        migrations.RunPython(ensure_unique_room_features, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="raummerkmal",
            constraint=models.UniqueConstraint(
                fields=("raumprotokoll", "merkmal"),
                name="raum_merkmal_eindeutig_pro_raumprotokoll",
            ),
        ),
    ]
