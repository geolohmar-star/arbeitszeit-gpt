from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0008_prozessverantwortliche_gruppe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProzessAntrag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text=(
                            "Wie soll der neue Prozess heissen? "
                            "(z.B. 'Rechnungspruefung Elektro')"
                        ),
                        max_length=200,
                        verbose_name="Name des Prozesses",
                    ),
                ),
                (
                    "ziel",
                    models.TextField(
                        help_text="Was soll am Ende des Prozesses erreicht sein?",
                        verbose_name="Ziel des Prozesses",
                    ),
                ),
                (
                    "ausloeser_typ",
                    models.CharField(
                        choices=[
                            ("manuell", "Manuell (Mitarbeiter startet selbst)"),
                            ("dms", "DMS-Import (Paperless-Dokument)"),
                            ("formular", "Formular-Einreichung"),
                            ("zeitgesteuert", "Zeitgesteuert (Datum/Uhrzeit)"),
                            ("sonstiges", "Sonstiges"),
                        ],
                        default="manuell",
                        max_length=20,
                        verbose_name="Wie wird der Prozess ausgeloest?",
                    ),
                ),
                (
                    "ausloeser_detail",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Optional: z.B. 'Dokument mit Tag "
                            "Eingangsrechnung aus Paperless'"
                        ),
                        verbose_name="Genauere Beschreibung des Ausloesers",
                    ),
                ),
                (
                    "schritte",
                    models.JSONField(
                        default=list,
                        help_text="Liste der gewuenschten Schritte als JSON",
                        verbose_name="Prozessschritte",
                    ),
                ),
                (
                    "team_benoetigt",
                    models.BooleanField(
                        default=False,
                        verbose_name="Wird ein Team benoetigt?",
                    ),
                ),
                (
                    "team_vorschlag",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Welche Mitarbeiter sollen ins Team? "
                            "(Namen oder Kuerzel)"
                        ),
                        verbose_name="Team-Vorschlag",
                    ),
                ),
                (
                    "pdf_benoetigt",
                    models.BooleanField(
                        default=False,
                        verbose_name="Soll am Ende ein PDF erzeugt werden?",
                    ),
                ),
                (
                    "bemerkungen",
                    models.TextField(
                        blank=True,
                        verbose_name="Zusaetzliche Bemerkungen",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("eingereicht", "Eingereicht"),
                            ("in_pruefung", "In Pruefung"),
                            ("in_umsetzung", "In Umsetzung"),
                            ("umgesetzt", "Umgesetzt"),
                            ("abgelehnt", "Abgelehnt"),
                        ],
                        default="eingereicht",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                (
                    "erstellt_am",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Eingereicht am",
                    ),
                ),
                (
                    "aktualisiert_am",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Aktualisiert am",
                    ),
                ),
                (
                    "antragsteller",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="prozessantraege",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Antragsteller",
                    ),
                ),
                (
                    "workflow_instance",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prozessantraege",
                        to="workflow.workflowinstance",
                        verbose_name="Workflow-Instanz",
                    ),
                ),
            ],
            options={
                "verbose_name": "Prozessantrag",
                "verbose_name_plural": "Prozessantraege",
                "ordering": ["-erstellt_am"],
            },
        ),
    ]
