# Datamigration: Gruppe "Prima-Vollzugriff" anlegen
# Mitglieder dieser Gruppe haben Web-Vollzugriff wie is_staff,
# koennen sich aber NICHT in Django-Admin einloggen.

from django.db import migrations


def erstelle_gruppe(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Prima-Vollzugriff")


def entferne_gruppe(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Prima-Vollzugriff").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("berechtigungen", "0001_init"),
    ]

    operations = [
        migrations.RunPython(erstelle_gruppe, entferne_gruppe),
    ]
