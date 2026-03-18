"""Migration 0011: Felderaenderungen (bereits in DB angewendet).

Diese Migration wurde automatisch im Container erzeugt und enthielt
AlterField-Operationen fuer bemerkungen (ProzessAntrag) und
aktion_typ (WorkflowStep). Die Aenderungen sind bereits in der
Datenbank vorhanden.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0010_prozessantrag_workflow_template"),
    ]

    operations = [
        # Felderaenderungen wurden bereits durch den Container angewendet
    ]
