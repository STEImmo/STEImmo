from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("immobilien", "0040_decision_notifications")]

    operations = [
        migrations.AddField(
            model_name="notificationpreference",
            name="reminders_changed_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddConstraint(
            model_name="decisionnotification",
            constraint=models.UniqueConstraint(
                condition=models.Q(kind__in=("main_application_due", "viewing_response_due")),
                fields=("kind", "object_id", "version"),
                name="open_step_reminder_task_version",
            ),
        ),
    ]
