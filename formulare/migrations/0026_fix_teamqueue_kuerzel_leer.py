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
    leere = list(TeamQueue.objects.filter(kuerzel=""))
    if not leere:
        return

    # Einmalige Pruefung VOR der Schleife – vermeidet Snapshot-Isolation-Problem
    # in PostgreSQL (REPEATABLE READ: wiederholte exists()-Abfragen innerhalb
    # derselben Transaktion sehen noch den alten Snapshot, nicht den frisch
    # gespeicherten Wert).
    pg_vorhanden = TeamQueue.objects.filter(kuerzel="PG").exists()

    for tq in leere:
        if pg_vorhanden:
            # PG existiert bereits (vorher oder gerade erstellt) → loeschen
            tq.delete()
        else:
            tq.kuerzel = "PG"
            tq.save(update_fields=["kuerzel"])
            pg_vorhanden = True  # ab jetzt gilt: PG ist vergeben


def rueckgaengig(apps, schema_editor):
    pass  # Kuerzel-Aenderung muss nicht rueckgaengig gemacht werden


class Migration(migrations.Migration):

    dependencies = [
        ("formulare", "0025_teamqueue_antragstypen"),
    ]

    operations = [
        migrations.RunPython(repariere_kuerzel, rueckgaengig),
    ]
