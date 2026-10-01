from django.db import migrations

ROLE_PERMISSIONS = {
    "Bewerber": ("access_applicant_area",),
    "Mieter": ("access_tenant_area",),
    "Mitarbeiter": ("access_employee_area",),
    "Benutzerverwaltung": ("access_employee_area", "manage_user_accounts"),
}

PERMISSION_NAMES = {
    "access_applicant_area": "Kann auf den Bewerberbereich zugreifen",
    "access_tenant_area": "Kann auf den vorbereiteten Mieterbereich zugreifen",
    "access_employee_area": "Kann auf den Mitarbeiterbereich zugreifen",
    "manage_user_accounts": "Kann Konten und Zugriffsrechte verwalten",
}


def create_access_roles(apps, schema_editor) -> None:
    content_type_model = apps.get_model("contenttypes", "ContentType")
    group_model = apps.get_model("auth", "Group")
    permission_model = apps.get_model("auth", "Permission")
    person_model = apps.get_model("immobilien", "Person")

    content_type, _created = content_type_model.objects.get_or_create(
        app_label="immobilien",
        model="person",
    )
    permissions = {}
    for codename in {codename for values in ROLE_PERMISSIONS.values() for codename in values}:
        permission, _created = permission_model.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": PERMISSION_NAMES[codename]},
        )
        permissions[codename] = permission

    groups = {}
    for group_name, codenames in ROLE_PERMISSIONS.items():
        group, _created = group_model.objects.get_or_create(name=group_name)
        group.permissions.set([permissions[codename] for codename in codenames])
        groups[group_name] = group

    for person in person_model.objects.exclude(user__isnull=True).iterator():
        role_name = "Mitarbeiter" if person.is_employee else "Bewerber"
        groups[role_name].user_set.add(person.user_id)


class Migration(migrations.Migration):
    dependencies = [
        ("immobilien", "0010_merge_20260929_1146"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="person",
            options={
                "db_table": "person",
                "permissions": [
                    ("access_applicant_area", "Kann auf den Bewerberbereich zugreifen"),
                    ("access_tenant_area", "Kann auf den vorbereiteten Mieterbereich zugreifen"),
                    ("access_employee_area", "Kann auf den Mitarbeiterbereich zugreifen"),
                    ("manage_user_accounts", "Kann Konten und Zugriffsrechte verwalten"),
                ],
            },
        ),
        migrations.RunPython(create_access_roles, migrations.RunPython.noop),
    ]
