import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0024_handover_photo_cleanup_queue"),
    ]

    operations = [
        migrations.CreateModel(
            name="HandoverArchiveCleanup",
            fields=[
                (
                    "cleanup_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("storage_name", models.CharField(max_length=512, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "handover_archive_cleanup",
                "ordering": ("created_at", "cleanup_id"),
            },
        ),
    ]
