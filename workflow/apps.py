from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    name = "workflow"

    def ready(self):
        """Generischen Trigger-Signal-Handler beim App-Start verbinden."""
        from django.db.models.signals import post_save
        from workflow.signals import generischer_trigger_handler

        # Verbinde mit allen post_save Signals (kein Sender-Filter)
        # Der Handler filtert intern anhand der WorkflowTrigger-Tabelle
        post_save.connect(generischer_trigger_handler)
