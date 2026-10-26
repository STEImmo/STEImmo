import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def preserve_send_times(apps, schema_editor):
    pending_model = apps.get_model("immobilien", "PendingEmailChange")
    throttle_model = apps.get_model("immobilien", "AccountEmailChangeThrottle")
    database = schema_editor.connection.alias
    throttle_model.objects.using(database).bulk_create(
        [
            throttle_model(user_id=pending.user_id, last_sent_at=pending.last_sent_at)
            for pending in pending_model.objects.using(database).iterator()
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0029_account_profile_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountEmailChangeThrottle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("last_sent_at", models.DateTimeField()),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
        ),
        migrations.RunPython(preserve_send_times, migrations.RunPython.noop),
    ]
