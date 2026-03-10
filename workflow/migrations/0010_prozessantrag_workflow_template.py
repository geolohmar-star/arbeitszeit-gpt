"""
Data-Migration: Erstellt das Meta-Workflow-Template 'Neuer Prozess beantragen'.
Dieses Template wird automatisch gestartet wenn ein ProzessAntrag eingereicht wird.
"""
from django.db import migrations


def erstelle_prozessantrag_template(apps, schema_editor):
    """Legt das Workflow-Template fuer ProzessAntraege an."""
    WorkflowTemplate = apps.get_model("workflow", "WorkflowTemplate")
    WorkflowStep = apps.get_model("workflow", "WorkflowStep")

    # Pruefen ob Template bereits existiert
    if WorkflowTemplate.objects.filter(
        trigger_event="prozessantrag_erstellt"
    ).exists():
        return

    template = WorkflowTemplate.objects.create(
        name="Neuer Prozess beantragen",
        beschreibung=(
            "Meta-Workflow: Wird automatisch gestartet wenn ein Mitarbeiter "
            "einen neuen Prozess beantragt. Prozessverantwortliche pruefen "
            "den Antrag, bauen das Template und geben es frei."
        ),
        kategorie="bearbeitung",
        trigger_event="prozessantrag_erstellt",
        ist_aktiv=True,
        ist_graph_workflow=False,
        version=1,
    )

    WorkflowStep.objects.create(
        template=template,
        reihenfolge=1,
        titel="Prozessantrag pruefen",
        beschreibung=(
            "Den eingereichten Prozessantrag sichten, Rueckfragen klaeren "
            "und entscheiden ob der Prozess umsetzbar und sinnvoll ist."
        ),
        aktion_typ="pruefen",
        zustaendig_rolle="hr",
        frist_tage=5,
        ist_parallel=False,
        eskalation_nach_tagen=7,
    )

    WorkflowStep.objects.create(
        template=template,
        reihenfolge=2,
        titel="Workflow-Template im Editor bauen",
        beschreibung=(
            "Den genehmigten Prozess im Workflow-Editor umsetzen: "
            "Schritte anlegen, Zustaendigkeiten konfigurieren, "
            "Trigger setzen und Template aktivieren."
        ),
        aktion_typ="bearbeiten",
        zustaendig_rolle="hr",
        frist_tage=10,
        ist_parallel=False,
        eskalation_nach_tagen=14,
    )

    WorkflowStep.objects.create(
        template=template,
        reihenfolge=3,
        titel="Antragsteller informieren",
        beschreibung=(
            "Den Antragsteller ueber die Umsetzung informieren. "
            "Bei Ablehnung: Begruendung mitteilen."
        ),
        aktion_typ="informieren",
        zustaendig_rolle="hr",
        frist_tage=2,
        ist_parallel=False,
        eskalation_nach_tagen=0,
    )


def entferne_template(apps, schema_editor):
    """Loescht das ProzessAntrag-Template (Rueckwaerts-Migration)."""
    WorkflowTemplate = apps.get_model("workflow", "WorkflowTemplate")
    WorkflowTemplate.objects.filter(
        trigger_event="prozessantrag_erstellt"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0009_prozessantrag"),
    ]

    operations = [
        migrations.RunPython(
            erstelle_prozessantrag_template,
            entferne_template,
        ),
    ]
