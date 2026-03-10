"""
Data-Migration: Erstellt die Gruppe 'Prozessverantwortliche'
und fuegt Anna Schmidt hinzu.
"""
from django.db import migrations


def erstelle_gruppe_und_mitglieder(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    gruppe, _ = Group.objects.get_or_create(name="Prozessverantwortliche")

    try:
        anna = User.objects.get(username="anna.schmidt")
        anna.groups.add(gruppe)
    except User.DoesNotExist:
        pass


def entferne_gruppe(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Prozessverantwortliche").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0007_add_claim_fields_to_workflowtask"),
    ]

    operations = [
        migrations.RunPython(erstelle_gruppe_und_mitglieder, entferne_gruppe),
    ]
