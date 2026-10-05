from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0019_bewerbung_credit_report_proof_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="bewerbung",
            name="income_proof_original_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="bewerbung",
            name="identity_proof_original_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="bewerbung",
            name="credit_report_proof_original_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
