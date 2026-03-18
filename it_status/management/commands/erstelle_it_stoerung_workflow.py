"""
Management-Command: Erstellt das Workflow-Template "IT-Stoerungsmeldung"
mit einem Verteilen-(Postbote)-Schritt fuer E-Mail und Matrix.

Ausfuehren:
    python manage.py erstelle_it_stoerung_workflow
    python manage.py erstelle_it_stoerung_workflow --ueberschreiben
"""
from django.core.management.base import BaseCommand

TRIGGER = "it_stoerung_gemeldet"


class Command(BaseCommand):
    help = "Erstellt das Workflow-Template fuer IT-Stoerungsmeldungen (Postbote E-Mail + Matrix)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ueberschreiben",
            action="store_true",
            help="Vorhandenes Template aktualisieren",
        )

    def handle(self, *args, **options):
        from workflow.models import WorkflowStep, WorkflowTemplate

        vorhandenes = WorkflowTemplate.objects.filter(trigger_event=TRIGGER).first()
        if vorhandenes and not options["ueberschreiben"]:
            self.stdout.write(
                f"Template '{vorhandenes.name}' bereits vorhanden "
                f"(trigger_event={TRIGGER}). "
                "Nutze --ueberschreiben zum Aktualisieren."
            )
            return

        if vorhandenes:
            vorhandenes.schritte.all().delete()
            template = vorhandenes
            self.stdout.write("Vorhandenes Template wird aktualisiert ...")
        else:
            template = WorkflowTemplate(trigger_event=TRIGGER)

        template.name = "IT-Stoerungsmeldung"
        template.beschreibung = (
            "Wird automatisch gestartet wenn eine neue IT-Stoerung gemeldet wird. "
            "Benachrichtigt das IT-Helpdesk-Team per E-Mail und Matrix."
        )
        template.kategorie = "information"
        template.ist_aktiv = True
        template.save()

        # E-Mail-Empfaenger: alle aktiven Mitglieder der Gruppe 'it_helpdesk'
        from django.contrib.auth.models import Group
        empfaenger = ""
        try:
            gruppe = Group.objects.get(name="it_helpdesk")
            emails = list(
                gruppe.user_set
                .filter(is_active=True, email__gt="")
                .values_list("email", flat=True)
            )
            empfaenger = ", ".join(emails)
        except Group.DoesNotExist:
            pass

        # Schritt 1: Verteilen (Postbote) – E-Mail + Matrix
        WorkflowStep.objects.create(
            template=template,
            titel="Benachrichtigung IT-Helpdesk",
            beschreibung="Informiert das Helpdesk-Team per E-Mail und Matrix-Nachricht.",
            schritt_typ="auto",
            aktion_typ="verteilen",
            reihenfolge=1,
            auto_config={
                "kanaele": [
                    {
                        "typ": "email",
                        "empfaenger": empfaenger,
                        "betreff": "[PRIMA IT] {{status}}: {{system}} – {{titel}}",
                        "text": (
                            "IT-Stoerungsmeldung vom {{datum}} um {{uhrzeit}} Uhr\n"
                            "=========================================\n\n"
                            "System:      {{system}}\n"
                            "Status:      {{status}}\n"
                            "Meldung:     {{titel}}\n"
                            "Beschreibung:{{beschreibung}}\n\n"
                            "Gemeldet von: {{antragsteller_name}}\n\n"
                            "Details: http://127.0.0.1:8000/it-status/"
                        ),
                    },
                    {
                        "typ": "matrix",
                        "raum_id": "!NfxKjqxMDsKXSmixhZ:georg-klein.com",
                        "nachricht": (
                            "IT-Stoerung [{{status}}] – {{system}}\n"
                            "Meldung: {{titel}}\n"
                            "Beschreibung: {{beschreibung}}\n"
                            "Gemeldet von: {{antragsteller_name}} am {{datum}} um {{uhrzeit}} Uhr\n"
                            "Details: http://127.0.0.1:8000/it-status/"
                        ),
                    },
                ]
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"Template '{template.name}' gespeichert (pk={template.pk})."
        ))
        self.stdout.write(f"  Trigger-Event:  {TRIGGER}")
        self.stdout.write(f"  E-Mail-Empf.:   {empfaenger or '(keine it_helpdesk-Gruppe gefunden)'}")
        self.stdout.write("")
        self.stdout.write(
            "Naechster Schritt: Trigger aktivieren unter "
            "http://127.0.0.1:8000/workflow/trigger/"
        )
