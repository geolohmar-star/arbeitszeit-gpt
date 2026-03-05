"""Data-Migration: TeamQueue + WorkflowTemplate fuer Arbeitszeitvereinbarungen.

Erstellt idempotent (get_or_create):
- formulare.TeamQueue  kuerzel='azv'
- workflow.WorkflowTemplate  trigger_event='arbeitszeitvereinbarung_beantragt'
- workflow.WorkflowStep  reihenfolge=1, rolle=team_queue → TeamQueue 'azv'

Damit landet jede neu gestellte Arbeitszeitvereinbarung automatisch als Task
im Arbeitsstapel des Teams Arbeitszeitvereinbarungen.
"""
from django.db import migrations


def seed_az_workflow(apps, schema_editor):
    """Legt TeamQueue + Workflow-Template an, falls noch nicht vorhanden."""
    TeamQueue = apps.get_model("formulare", "TeamQueue")
    WorkflowTemplate = apps.get_model("workflow", "WorkflowTemplate")
    WorkflowStep = apps.get_model("workflow", "WorkflowStep")

    # TeamQueue anlegen
    team_queue, _ = TeamQueue.objects.get_or_create(
        kuerzel="azv",
        defaults={
            "name": "Arbeitszeitvereinbarungen",
            "beschreibung": (
                "Bearbeitung von Arbeitszeitvereinbarungsantraegen "
                "(Ersteinrichtung, Verringerung, Erhoehung, Weiterbewilligung, Beendigung)"
            ),
            "antragstypen": ["arbeitszeitvereinbarung"],
        },
    )

    # WorkflowTemplate anlegen
    template, created = WorkflowTemplate.objects.get_or_create(
        trigger_event="arbeitszeitvereinbarung_beantragt",
        defaults={
            "name": "Arbeitszeitvereinbarung Bearbeitung",
            "beschreibung": (
                "Workflow fuer neu beantragte Arbeitszeitvereinbarungen. "
                "Der Antrag landet im Team-Stapel des Teams Arbeitszeitvereinbarungen."
            ),
            "kategorie": "bearbeitung",
            "ist_aktiv": True,
            "ist_graph_workflow": False,
            "version": 1,
        },
    )

    # WorkflowStep nur anlegen wenn Template neu erstellt wurde
    if created:
        WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            schritt_typ="task",
            titel="Arbeitszeitvereinbarung bearbeiten",
            beschreibung=(
                "Antrag pruefen, Rueckfragen klaeren und die "
                "Arbeitszeitvereinbarung genehmigen oder ablehnen."
            ),
            aktion_typ="bearbeiten",
            zustaendig_rolle="team_queue",
            zustaendig_team=team_queue,
            frist_tage=5,
            eskalation_nach_tagen=0,
        )


def undo_seed_az_workflow(apps, schema_editor):
    """Entfernt die angelegten Objekte (nur zum Rollback)."""
    WorkflowTemplate = apps.get_model("workflow", "WorkflowTemplate")
    TeamQueue = apps.get_model("formulare", "TeamQueue")

    WorkflowTemplate.objects.filter(
        trigger_event="arbeitszeitvereinbarung_beantragt"
    ).delete()
    TeamQueue.objects.filter(kuerzel="azv").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("arbeitszeit", "0028_zyklus_startdatum"),
        ("formulare", "0025_teamqueue_antragstypen"),
        ("workflow", "0007_add_claim_fields_to_workflowtask"),
    ]

    operations = [
        migrations.RunPython(seed_az_workflow, undo_seed_az_workflow),
    ]
