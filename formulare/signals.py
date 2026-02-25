"""Signals fuer automatischen Workflow-Start

Wenn ein Dienstreiseantrag erstellt wird, wird automatisch
ein passender Workflow gestartet.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from formulare.models import AenderungZeiterfassung, Dienstreiseantrag, Zeitgutschrift
from workflow.models import WorkflowTemplate
from workflow.services import WorkflowEngine


@receiver(post_save, sender=Dienstreiseantrag)
def start_dienstreise_workflow(sender, instance, created, **kwargs):
    """Startet automatisch Workflow bei neuem Dienstreiseantrag.

    Trigger: dienstreise_erstellt
    """
    if not created:
        return

    # Suche passendes Workflow-Template
    try:
        template = WorkflowTemplate.objects.get(
            trigger_event="dienstreise_erstellt",
            ist_aktiv=True
        )
    except WorkflowTemplate.DoesNotExist:
        # Kein Template gefunden → kein Workflow
        return
    except WorkflowTemplate.MultipleObjectsReturned:
        # Mehrere Templates → nimm das neueste
        template = WorkflowTemplate.objects.filter(
            trigger_event="dienstreise_erstellt",
            ist_aktiv=True
        ).order_by("-erstellt_am").first()

    # Starte Workflow
    engine = WorkflowEngine()
    try:
        workflow_instance = engine.start_workflow(
            template=template,
            content_object=instance,
            user=instance.antragsteller.user
        )

        # Verknuepfe Workflow mit Antrag
        instance.workflow_instance = workflow_instance
        instance.save(update_fields=["workflow_instance"])
    except Exception as e:
        # Fehler beim Workflow-Start → Loggen aber nicht abbrechen
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Fehler beim Starten des Dienstreise-Workflows "
            f"fuer Antrag {instance.id}: {e}"
        )


@receiver(post_save, sender=Zeitgutschrift)
def start_zeitgutschrift_workflow(sender, instance, created, **kwargs):
    """Startet automatisch Workflow bei neuer Zeitgutschrift.

    Trigger: zeitgutschrift_erstellt
    """
    if not created:
        return

    # Suche passendes Workflow-Template
    try:
        template = WorkflowTemplate.objects.get(
            trigger_event="zeitgutschrift_erstellt",
            ist_aktiv=True
        )
    except WorkflowTemplate.DoesNotExist:
        # Kein Template gefunden → kein Workflow
        return
    except WorkflowTemplate.MultipleObjectsReturned:
        # Mehrere Templates → nimm das neueste
        template = WorkflowTemplate.objects.filter(
            trigger_event="zeitgutschrift_erstellt",
            ist_aktiv=True
        ).order_by("-erstellt_am").first()

    # Starte Workflow
    engine = WorkflowEngine()
    try:
        workflow_instance = engine.start_workflow(
            template=template,
            content_object=instance,
            user=instance.antragsteller.user
        )

        # Verknuepfe Workflow mit Antrag
        instance.workflow_instance = workflow_instance
        instance.save(update_fields=["workflow_instance"])
    except Exception as e:
        # Fehler beim Workflow-Start → Loggen aber nicht abbrechen
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Fehler beim Starten des Zeitgutschrift-Workflows "
            f"fuer Antrag {instance.id}: {e}"
        )


@receiver(post_save, sender=AenderungZeiterfassung)
def start_aenderung_workflow(sender, instance, created, **kwargs):
    """Startet automatisch Workflow bei neuer Aenderung Zeiterfassung.

    Trigger: aenderung_zeiterfassung_erstellt
    """
    if not created:
        return

    # Suche passendes Workflow-Template
    try:
        template = WorkflowTemplate.objects.get(
            trigger_event="aenderung_zeiterfassung_erstellt",
            ist_aktiv=True
        )
    except WorkflowTemplate.DoesNotExist:
        # Kein Template gefunden → kein Workflow
        return
    except WorkflowTemplate.MultipleObjectsReturned:
        # Mehrere Templates → nimm das neueste
        template = WorkflowTemplate.objects.filter(
            trigger_event="aenderung_zeiterfassung_erstellt",
            ist_aktiv=True
        ).order_by("-erstellt_am").first()

    # Starte Workflow
    engine = WorkflowEngine()
    try:
        workflow_instance = engine.start_workflow(
            template=template,
            content_object=instance,
            user=instance.antragsteller.user
        )

        # Verknuepfe Workflow mit Antrag
        instance.workflow_instance = workflow_instance
        instance.save(update_fields=["workflow_instance"])
    except Exception as e:
        # Fehler beim Workflow-Start → Loggen aber nicht abbrechen
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Fehler beim Starten des Aenderung-Workflows "
            f"fuer Antrag {instance.id}: {e}"
        )
