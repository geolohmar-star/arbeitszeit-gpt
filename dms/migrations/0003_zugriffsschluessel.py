"""Migration: DokumentZugriffsschluessel + ZugriffsProtokoll-Erweiterung."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0002_gin_suchvektor_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Neues Model DokumentZugriffsschluessel
        migrations.CreateModel(
            name="DokumentZugriffsschluessel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("antrag_grund", models.TextField(verbose_name="Begruendung des Antrags")),
                ("antrag_zeitpunkt", models.DateTimeField(auto_now_add=True, verbose_name="Antrag gestellt am")),
                ("genehmigt_am", models.DateTimeField(blank=True, null=True, verbose_name="Genehmigt am")),
                ("gewuenschte_dauer_h", models.PositiveSmallIntegerField(
                    choices=[(1, "1 Stunde"), (4, "4 Stunden"), (24, "1 Tag"), (72, "3 Tage")],
                    default=4,
                    verbose_name="Gewuenschte Zugriffsdauer",
                )),
                ("gueltig_bis", models.DateTimeField(blank=True, null=True, verbose_name="Gueltig bis")),
                ("status", models.CharField(
                    choices=[
                        ("offen", "Offen (wartet auf Genehmigung)"),
                        ("genehmigt", "Genehmigt"),
                        ("abgelehnt", "Abgelehnt"),
                        ("widerrufen", "Widerrufen"),
                        ("abgelaufen", "Abgelaufen"),
                    ],
                    default="offen",
                    max_length=15,
                    verbose_name="Status",
                )),
                ("dokument", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="zugriffsschluessel",
                    to="dms.dokument",
                    verbose_name="Dokument",
                )),
                ("genehmigt_von", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="genehmigte_zugriffsschluessel",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Genehmigt von",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dms_zugriffsschluessel",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Antragsteller",
                )),
            ],
            options={
                "verbose_name": "Dokument-Zugriffsschluessel",
                "verbose_name_plural": "Dokument-Zugriffsschluessel",
                "ordering": ["-antrag_zeitpunkt"],
            },
        ),
        # Guardian-Berechtigung fuer sensible Dokumente
        migrations.AlterModelOptions(
            name="dokument",
            options={
                "ordering": ["-erstellt_am"],
                "verbose_name": "Dokument",
                "verbose_name_plural": "Dokumente",
                "permissions": [("view_dokument_sensibel", "Kann sensible Dokumente einsehen")],
            },
        ),
        # ZugriffsProtokoll: neue Aktionen + Notiz-Feld
        migrations.AddField(
            model_name="zugriffsprotokoll",
            name="notiz",
            field=models.TextField(blank=True, verbose_name="Notiz (z.B. Grund, Dauer)"),
        ),
        migrations.AlterField(
            model_name="zugriffsprotokoll",
            name="aktion",
            field=models.CharField(
                choices=[
                    ("download", "Download"),
                    ("vorschau", "Vorschau"),
                    ("erstellt", "Erstellt"),
                    ("geaendert", "Geaendert"),
                    ("zugriff_beantragt", "Zugriff beantragt"),
                    ("zugriff_genehmigt", "Zugriff genehmigt"),
                    ("zugriff_abgelehnt", "Zugriff abgelehnt"),
                    ("zugriff_widerrufen", "Zugriff widerrufen"),
                ],
                default="download",
                max_length=25,
                verbose_name="Aktion",
            ),
        ),
    ]
