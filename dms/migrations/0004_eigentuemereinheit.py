"""Migration: Eigentuemer-OrgEinheit zu Dokument hinzufuegen.

Erlaubt es, einem Dokument eine zustaendige Abteilung zuzuordnen.
Mitglieder der Eigentuemer-OrgEinheit erhalten automatischen Zugriff
auf sensible Dokumente dieser Abteilung (ohne Zugriffsschluessel).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0003_zugriffsschluessel"),
        ("hr", "0005_stelle_kategorie"),
    ]

    operations = [
        migrations.AddField(
            model_name="dokument",
            name="eigentuemereinheit",
            field=models.ForeignKey(
                blank=True,
                help_text="Abteilung die fuer dieses Dokument zustaendig ist.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dms_dokumente",
                to="hr.orgeinheit",
                verbose_name="Eigentuemer-OrgEinheit",
            ),
        ),
    ]
