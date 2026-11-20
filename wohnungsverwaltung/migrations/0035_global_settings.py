from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("immobilien", "0034_confirmed_attic_areas")]

    operations = [
        migrations.CreateModel(
            name="GlobalSettings",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("optional_user_emails_enabled", models.BooleanField(default=True)),
                ("version", models.PositiveBigIntegerField(default=0)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)), name="global_settings_singleton"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GlobalSettingsChange",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("actor_account_id", models.PositiveBigIntegerField()),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("changed_fields", models.JSONField()),
            ],
        ),
    ]
