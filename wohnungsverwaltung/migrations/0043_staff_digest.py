from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("immobilien", "0042_merge_open_step_reminders")]

    operations = [
        migrations.AddField(
            model_name="decisionnotification",
            name="task_versions",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
