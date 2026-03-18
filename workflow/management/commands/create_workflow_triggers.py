"""Management Command: Erstellt 10 vorkonfigurierte WorkflowTrigger-Eintraege.

Ausfuehren: python manage.py create_workflow_triggers
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Trigger-Definitionen: (name, trigger_event, app_label, model, antragsteller_pfad, beschreibung)
TRIGGER_DEFINITIONEN = [
    (
        "Dienstreiseantrag eingereicht",
        "dienstreise_erstellt",
        "formulare",
        "dienstreiseantrag",
        "antragsteller.user",
        "Startet Genehmigungsworkflow wenn ein neuer Dienstreiseantrag erstellt wird",
    ),
    (
        "Zeitgutschrift eingereicht",
        "zeitgutschrift_erstellt",
        "formulare",
        "zeitgutschrift",
        "antragsteller.user",
        "Startet Genehmigungsworkflow wenn eine neue Zeitgutschrift erstellt wird",
    ),
    (
        "Aenderung Zeiterfassung eingereicht",
        "aenderung_zeiterfassung_erstellt",
        "formulare",
        "aenderungzeiterfassung",
        "antragsteller.user",
        "Startet Pruefungsworkflow wenn eine Aenderung der Zeiterfassung eingereicht wird",
    ),
    (
        "Z-AG Antrag eingereicht",
        "zag_antrag_erstellt",
        "formulare",
        "zagantrag",
        "antragsteller.user",
        "Startet Genehmigungsworkflow wenn ein neuer Z-AG Antrag erstellt wird",
    ),
    (
        "Z-AG Storno eingereicht",
        "zag_storno_erstellt",
        "formulare",
        "zagstorno",
        "antragsteller.user",
        "Startet Pruefungsworkflow wenn ein Z-AG Storno eingereicht wird",
    ),
    (
        "Prozessantrag eingereicht",
        "prozessantrag_erstellt",
        "workflow",
        "prozessantrag",
        "antragsteller",
        "Startet Bearbeitungsworkflow wenn ein neuer Prozessantrag erstellt wird",
    ),
    (
        "Betriebssport Gutschrift eingereicht",
        "betriebssport_gutschrift_eingereicht",
        "betriebssport",
        "betriebssportgutschrift",
        "antragsteller.user",
        "Startet Genehmigungsworkflow fuer Betriebssport-Gutschriften",
    ),
    (
        "Veranstaltungs-Gutschrift eingereicht",
        "veranstaltung_gutschrift_eingereicht",
        "veranstaltungen",
        "veranstaltunggutschrift",
        "antragsteller.user",
        "Startet Genehmigungsworkflow fuer Veranstaltungs-Gutschriften",
    ),
    (
        "Arbeitszeitvereinbarung beantragt",
        "arbeitszeitvereinbarung_beantragt",
        "arbeitszeit",
        "arbeitszeitvereinbarung",
        "antragsteller.user",
        "Startet Genehmigungsworkflow wenn eine Arbeitszeitvereinbarung beantragt wird",
    ),
    (
        "IT-Stoerungsmeldung erstellt",
        "it_stoerung_gemeldet",
        "it_status",
        "itstatusmeldung",
        "erstellt_von",
        "Startet Postboten-Workflow (E-Mail + Matrix) wenn eine neue IT-Stoerung gemeldet wird",
    ),
    (
        "Freier Trigger 1",
        "custom_trigger_1",
        None,
        None,
        "antragsteller.user",
        "Freier Trigger-Slot fuer eigene Erweiterungen",
    ),
]


class Command(BaseCommand):
    help = "Erstellt 10 vorkonfigurierte WorkflowTrigger-Eintraege"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ueberschreiben",
            action="store_true",
            help="Vorhandene Trigger aktualisieren statt ueberspringen",
        )

    def handle(self, *args, **options):
        from workflow.models import WorkflowTrigger

        ueberschreiben = options["ueberschreiben"]
        erstellt = 0
        aktualisiert = 0
        uebersprungen = 0

        for name, trigger_event, app_label, model_name, pfad, beschreibung in TRIGGER_DEFINITIONEN:
            # ContentType ermitteln (falls Model angegeben)
            ct = None
            if app_label and model_name:
                try:
                    ct = ContentType.objects.get(
                        app_label=app_label, model=model_name
                    )
                except ContentType.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [WARN] Model '{app_label}.{model_name}' nicht gefunden "
                            f"fuer Trigger '{trigger_event}' - ohne ContentType angelegt"
                        )
                    )

            vorhandener = WorkflowTrigger.objects.filter(
                trigger_event=trigger_event
            ).first()

            if vorhandener:
                if ueberschreiben:
                    vorhandener.name = name
                    vorhandener.beschreibung = beschreibung
                    vorhandener.content_type = ct
                    vorhandener.antragsteller_pfad = pfad
                    vorhandener.save()
                    self.stdout.write(
                        self.style.SUCCESS(f"  [AKT] {name} ({trigger_event})")
                    )
                    aktualisiert += 1
                else:
                    self.stdout.write(f"  [OK]  {name} ({trigger_event}) - bereits vorhanden")
                    uebersprungen += 1
            else:
                WorkflowTrigger.objects.create(
                    name=name,
                    trigger_event=trigger_event,
                    content_type=ct,
                    antragsteller_pfad=pfad,
                    beschreibung=beschreibung,
                    ist_aktiv=False,  # Standardmaessig inaktiv bis konfiguriert
                )
                self.stdout.write(
                    self.style.SUCCESS(f"  [NEU] {name} ({trigger_event})")
                )
                erstellt += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFertig: {erstellt} neu, {aktualisiert} aktualisiert, "
                f"{uebersprungen} uebersprungen"
            )
        )
        self.stdout.write(
            "Trigger sind standardmaessig INAKTIV. "
            "Aktiviere sie unter: /workflow/trigger/"
        )
