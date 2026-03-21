"""
Migration: ZugriffsProtokoll fuer dauerhafte Loeschprotokollierung vorbereiten.

- dokument FK: CASCADE -> SET_NULL (Protokoll bleibt nach Dokumentloeschung erhalten)
- dokument_titel CharField hinzufuegen (Titel bleibt nach Loeschung lesbar)
- 'geloescht' als Aktion-Choice
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0011_persoenliche_ablage"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        # Neues Feld: Titel des Dokuments (bleibt erhalten wenn Dokument geloescht wird)
        migrations.AddField(
            model_name="zugriffsprotokoll",
            name="dokument_titel",
            field=models.CharField(
                blank=True,
                max_length=300,
                verbose_name="Dokument-Titel (Sicherungskopie)",
                help_text="Automatisch gesetzt – bleibt erhalten wenn das Dokument geloescht wird.",
            ),
        ),
        # FK: CASCADE -> SET_NULL damit Protokoll das Dokument ueberdauert
        migrations.AlterField(
            model_name="zugriffsprotokoll",
            name="dokument",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="zugriffe",
                to="dms.dokument",
                verbose_name="Dokument",
            ),
        ),
    ]
