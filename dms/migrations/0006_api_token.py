"""Migration: ApiToken-Modell + neue ZugriffsProtokoll-Aktionen (api_upload, api_download)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0005_dokument_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("aktiv", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("bezeichnung", models.CharField(max_length=200, verbose_name="Bezeichnung")),
                (
                    "erlaubte_klassen",
                    models.CharField(
                        choices=[
                            ("offen", "Nur offen (Klasse 1)"),
                            ("beide", "Offen + Sensibel (Klasse 1+2)"),
                        ],
                        default="offen",
                        max_length=10,
                        verbose_name="Erlaubte Dokumentenklassen",
                        help_text="Sensibel nur freischalten wenn das Fremdsystem verschluesselt uebertraegt.",
                    ),
                ),
                ("erstellt_am", models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")),
                ("letzte_nutzung", models.DateTimeField(blank=True, null=True, verbose_name="Letzte Nutzung")),
                ("system", models.CharField(blank=True, max_length=100, verbose_name="System (z.B. SAP S/4HANA 2023)")),
                ("token", models.CharField(max_length=64, unique=True, verbose_name="Token (hex)")),
            ],
            options={
                "verbose_name": "API-Token",
                "verbose_name_plural": "API-Tokens",
                "ordering": ["bezeichnung"],
            },
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
                    ("onlyoffice_bearbeitet", "In OnlyOffice bearbeitet"),
                    ("version_wiederhergestellt", "Version wiederhergestellt"),
                    ("api_upload", "API-Upload (externes System)"),
                    ("api_download", "API-Download (externes System)"),
                ],
                default="download",
                max_length=25,
                verbose_name="Aktion",
            ),
        ),
    ]
