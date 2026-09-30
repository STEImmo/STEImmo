import uuid

from django.db import migrations, models


def backfill_raeume(apps, schema_editor):
    Protokoll = apps.get_model("immobilien", "Protokoll")
    Raum = apps.get_model("immobilien", "Raum")
    Raumprotokoll = apps.get_model("immobilien", "Raumprotokoll")

    room_protocols = list(
        Raumprotokoll.objects.order_by("protokoll_id", "name", "raumprotokoll_id").values(
            "raumprotokoll_id", "protokoll_id", "name"
        )
    )
    duplicate_keys = set()
    seen_keys = set()
    for room_protocol in room_protocols:
        key = (room_protocol["protokoll_id"], room_protocol["name"])
        if key in seen_keys:
            duplicate_keys.add(key)
        seen_keys.add(key)
    if duplicate_keys:
        examples = ", ".join(
            f"{protocol_id} / {name!r}"
            for protocol_id, name in sorted(
                duplicate_keys, key=lambda entry: (str(entry[0]), entry[1])
            )
        )
        raise RuntimeError(
            "Raumprotokolle mit demselben Namen im selben Protokoll müssen vor der "
            f"Migration manuell bereinigt werden: {examples}"
        )

    apartment_ids = Protokoll.objects.in_bulk(
        [room_protocol["protokoll_id"] for room_protocol in room_protocols],
        field_name="protokoll_id",
    )
    rooms_by_key = {}
    for room_protocol in room_protocols:
        apartment_id = apartment_ids[room_protocol["protokoll_id"]].wohnung_id
        key = (apartment_id, room_protocol["name"])
        room = rooms_by_key.get(key)
        if room is None:
            room, _ = Raum.objects.get_or_create(
                wohnung_id=apartment_id, name=room_protocol["name"]
            )
            rooms_by_key[key] = room
        Raumprotokoll.objects.filter(pk=room_protocol["raumprotokoll_id"]).update(raum_id=room.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0008_merge_stellplatz_und_protokoll"),
    ]

    operations = [
        migrations.CreateModel(
            name="Raum",
            fields=[
                (
                    "raum_id",
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
                    "wohnung",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="raeume",
                        to="immobilien.wohnung",
                    ),
                ),
            ],
            options={
                "db_table": "raum",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("wohnung", "name"),
                        name="raum_name_pro_wohnung_eindeutig",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="raumprotokoll",
            name="raum",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="raumprotokolle",
                to="immobilien.raum",
            ),
        ),
        migrations.RunPython(backfill_raeume, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="raumprotokoll",
            name="raum",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="raumprotokolle",
                to="immobilien.raum",
            ),
        ),
        migrations.AddConstraint(
            model_name="raumprotokoll",
            constraint=models.UniqueConstraint(
                fields=("protokoll", "raum"),
                name="raumprotokoll_eindeutig_pro_protokoll",
            ),
        ),
    ]
