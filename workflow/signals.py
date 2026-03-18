"""Generischer Signal-Handler fuer per GUI konfigurierte Workflow-Trigger.

Ersetzt die hardcodierten Einzel-Handler in formulare/signals.py.
Alle Trigger werden in der WorkflowTrigger-Tabelle verwaltet.
"""
import logging

logger = logging.getLogger(__name__)


def generischer_trigger_handler(sender, instance, created, **kwargs):
    """Wird bei jedem post_save ausgeloest und prueft ob ein Trigger passt.

    Sucht in WorkflowTrigger nach einer Konfiguration fuer das gespeicherte
    Model und den passenden trigger_auf-Wert (erstellt/aktualisiert).
    Startet bei Treffer automatisch den verknuepften Workflow.
    """
    # Vorzeitiger Ausstieg: verhindert Fehler waehrend Migrationen
    try:
        from django.contrib.contenttypes.models import ContentType
        from workflow.models import WorkflowTemplate, WorkflowTrigger
        from workflow.services import WorkflowEngine
    except Exception:
        return

    trigger_auf = "erstellt" if created else "aktualisiert"

    try:
        ct = ContentType.objects.get_for_model(sender)
        trigger_configs = list(
            WorkflowTrigger.objects.filter(
                content_type=ct,
                trigger_auf=trigger_auf,
                ist_aktiv=True,
            )
        )
    except Exception:
        # Tabelle existiert noch nicht (z.B. beim ersten migrate)
        return

    for trigger_config in trigger_configs:
        # Pruefe ob workflow_instance bereits gesetzt (Doppel-Start verhindern)
        feld = trigger_config.workflow_instance_feld
        if getattr(instance, feld, None) is not None:
            continue

        # Passendes WorkflowTemplate suchen
        try:
            template = WorkflowTemplate.objects.get(
                trigger_event=trigger_config.trigger_event,
                ist_aktiv=True,
            )
        except WorkflowTemplate.DoesNotExist:
            continue
        except WorkflowTemplate.MultipleObjectsReturned:
            template = (
                WorkflowTemplate.objects.filter(
                    trigger_event=trigger_config.trigger_event,
                    ist_aktiv=True,
                )
                .order_by("-erstellt_am")
                .first()
            )

        # User aus konfiguriertem Pfad lesen
        user = trigger_config.get_user_from_instance(instance)
        if user is None:
            logger.warning(
                "WorkflowTrigger '%s': Kein User ueber Pfad '%s' "
                "gefunden fuer %s (id=%s)",
                trigger_config.trigger_event,
                trigger_config.antragsteller_pfad,
                sender.__name__,
                instance.pk,
            )
            continue

        # Workflow starten
        engine = WorkflowEngine()
        try:
            workflow_instance = engine.start_workflow(
                template=template,
                content_object=instance,
                user=user,
            )
            setattr(instance, feld, workflow_instance)
            instance.save(update_fields=[feld])
            logger.info(
                "Workflow '%s' gestartet fuer %s (id=%s)",
                trigger_config.trigger_event,
                sender.__name__,
                instance.pk,
            )
        except Exception as e:
            logger.error(
                "Fehler beim Starten des Workflows '%s' fuer %s (id=%s): %s",
                trigger_config.trigger_event,
                sender.__name__,
                instance.pk,
                e,
            )
