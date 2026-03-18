"""Migration: WorkflowTrigger-Modell anlegen."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("workflow", "0011_workflow_trigger_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowTrigger",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Lesbarer Name z.B. 'Dienstreiseantrag eingereicht'",
                        max_length=200,
                        verbose_name="Name",
                    ),
                ),
                (
                    "beschreibung",
                    models.TextField(
                        blank=True,
                        verbose_name="Beschreibung",
                    ),
                ),
                (
                    "trigger_event",
                    models.CharField(
                        help_text=(
                            "Eindeutiger Schluessel (muss mit WorkflowTemplate.trigger_event "
                            "uebereinstimmen)"
                        ),
                        max_length=100,
                        unique=True,
                        verbose_name="Trigger-Event-Key",
                    ),
                ),
                (
                    "trigger_auf",
                    models.CharField(
                        choices=[
                            ("erstellt", "Neu erstellt"),
                            ("aktualisiert", "Aktualisiert"),
                        ],
                        default="erstellt",
                        max_length=20,
                        verbose_name="Ausloesen bei",
                    ),
                ),
                (
                    "antragsteller_pfad",
                    models.CharField(
                        default="antragsteller.user",
                        help_text=(
                            "Punkt-getrennter Attributpfad zum User-Objekt "
                            "(z.B. 'antragsteller.user' oder 'erstellt_von')"
                        ),
                        max_length=200,
                        verbose_name="Antragsteller-Pfad",
                    ),
                ),
                (
                    "workflow_instance_feld",
                    models.CharField(
                        default="workflow_instance",
                        help_text=(
                            "Feldname am Model zum Speichern der Workflow-Instanz"
                        ),
                        max_length=100,
                        verbose_name="Workflow-Instance-Feld",
                    ),
                ),
                (
                    "ist_aktiv",
                    models.BooleanField(
                        default=True,
                        verbose_name="Aktiv",
                    ),
                ),
                (
                    "erstellt_am",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Erstellt am",
                    ),
                ),
                (
                    "content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                        verbose_name="Django-Model",
                    ),
                ),
            ],
            options={
                "verbose_name": "Workflow-Trigger",
                "verbose_name_plural": "Workflow-Trigger",
                "ordering": ["name"],
            },
        ),
    ]
