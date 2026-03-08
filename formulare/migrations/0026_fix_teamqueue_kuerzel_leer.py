"""
Data-Migration: Repariert TeamQueue-Eintraege mit leerem Kuerzel.

Hintergrund: Ein frueherer Deploy legte eine TeamQueue "Personalgewinnung"
mit kuerzel='' an. Das verletzt den Unique-Constraint bei erneuten
Erstellungsversuchen. Diese Migration setzt kuerzel='PG' bevor
seed_initial_data laeuft.
"""
from django.db import migrations


def repariere_kuerzel(apps, schema_editor):
    TeamQueue = apps.get_model("formulare", "TeamQueue")
    for tq in TeamQueue.objects.filter(kuerzel=""):
        # Falls bereits eine Queue mit dem Ziel-Kuerzel existiert,
        # die verwaiste leere Queue loeschen statt umbenennen.
        ziel = "PG"
        if TeamQueue.objects.filter(kuerzel=ziel).exists():
            tq.delete()
        else:
            tq.kuerzel = ziel
            tq.save(update_fields=["kuerzel"])


def rueckgaengig(apps, schema_editor):
    pass  # Kuerzel-Aenderung muss nicht rueckgaengig gemacht werden


class Migration(migrations.Migration):

    dependencies = [
        ("formulare", "0025_teamqueue_antragstypen"),
    ]

    operations = [
        migrations.RunPython(repariere_kuerzel, rueckgaengig),
    ]
