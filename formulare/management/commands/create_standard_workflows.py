"""Management Command: Standard-Workflow-Templates anlegen.

Erstellt idempotent die vier Standard-Workflow-Templates fuer:
- Z-AG Antrag
- Aenderung Zeiterfassung
- Z-AG Storno
- Zeitgutschrift

Jedes Template hat zwei Schritte:
  Schritt 1: Direkter Vorgesetzter genehmigt (frist_tage=3)
  Schritt 2: Team-Queue (frist_tage=5)

Aufruf:
    python manage.py create_standard_workflows
    python manage.py create_standard_workflows --team-name "Zeiterfassung"
"""
from django.core.management.base import BaseCommand

from formulare.models import TeamQueue
from workflow.models import WorkflowStep, WorkflowTemplate


STANDARD_WORKFLOWS = [
    {
        "name": "Z-AG Standard",
        "trigger_event": "zag_antrag_erstellt",
        "team_name_hint": "Zeiterfassung",
    },
    {
        "name": "Aenderung Zeiterfassung",
        "trigger_event": "aenderung_erstellt",
        "team_name_hint": "Zeiterfassung",
    },
    {
        "name": "Z-AG Storno",
        "trigger_event": "zag_storno_erstellt",
        "team_name_hint": "Zeiterfassung",
    },
    {
        "name": "Zeitgutschrift",
        "trigger_event": "zeitgutschrift_erstellt",
        "team_name_hint": "Zeitgutschrift",
    },
]


class Command(BaseCommand):
    """Legt Standard-Workflow-Templates an (idempotent)."""

    help = "Erstellt Standard-Workflow-Templates fuer ZAG, Aenderung, Storno und Zeitgutschrift"

    def add_arguments(self, parser):
        parser.add_argument(
            "--zeiterfassung-team",
            default=None,
            help="Name des Teams fuer Zeiterfassungs-Tasks (Standard: erstes passendes Team)",
        )
        parser.add_argument(
            "--zeitgutschrift-team",
            default=None,
            help="Name des Teams fuer Zeitgutschrift-Tasks (Standard: erstes passendes Team)",
        )

    def handle(self, *args, **options):
        # Teams ermitteln
        zeiterfassung_team = self._finde_team(
            options.get("zeiterfassung_team"), "Zeiterfassung"
        )
        zeitgutschrift_team = self._finde_team(
            options.get("zeitgutschrift_team"), "Zeitgutschrift"
        )

        if not zeiterfassung_team:
            self.stdout.write(
                self.style.WARNING(
                    "Kein Zeiterfassungs-Team gefunden. "
                    "Schritt 2 wird ohne Team-Queue angelegt."
                )
            )
        if not zeitgutschrift_team:
            self.stdout.write(
                self.style.WARNING(
                    "Kein Zeitgutschrift-Team gefunden. "
                    "Schritt 2 wird ohne Team-Queue angelegt."
                )
            )

        for wf_def in STANDARD_WORKFLOWS:
            # Team je nach Workflow-Typ auswaehlen
            if "zeitgutschrift" in wf_def["trigger_event"]:
                team = zeitgutschrift_team
            else:
                team = zeiterfassung_team

            self._erstelle_oder_aktualisiere_workflow(wf_def, team)

        self.stdout.write(self.style.SUCCESS("Standard-Workflows erfolgreich angelegt."))

    def _finde_team(self, team_name_param, hint):
        """Sucht das passende TeamQueue-Objekt.

        Bevorzugt den per Parameter uebergebenen Namen,
        faellt zurueck auf icontains-Suche nach dem Hint.
        """
        if team_name_param:
            try:
                return TeamQueue.objects.get(name=team_name_param)
            except TeamQueue.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Team '{team_name_param}' nicht gefunden.")
                )
                return None

        # Fallback: icontains-Suche
        team = TeamQueue.objects.filter(name__icontains=hint).first()
        if team:
            self.stdout.write(f"  Team fuer '{hint}': {team.name} (pk={team.pk})")
        return team

    def _erstelle_oder_aktualisiere_workflow(self, wf_def, team):
        """Erstellt das Template und seine Schritte, falls noch nicht vorhanden.

        Vorhandene Templates (gleicher trigger_event) werden uebersprungen.
        """
        name = wf_def["name"]
        trigger = wf_def["trigger_event"]

        # Idempotenz: nur erstellen wenn noch nicht vorhanden
        if WorkflowTemplate.objects.filter(trigger_event=trigger).exists():
            self.stdout.write(f"  Uebersprungen (existiert): {name}")
            return

        template = WorkflowTemplate.objects.create(
            name=name,
            trigger_event=trigger,
            kategorie=WorkflowTemplate.KATEGORIE_GENEHMIGUNG,
            ist_aktiv=True,
            beschreibung=f"Standard-Workflow fuer {name}",
        )

        # Schritt 1: Direkter Vorgesetzter
        WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            titel="Vorgesetzter genehmigt",
            beschreibung="Der direkte Vorgesetzte prueft und genehmigt den Antrag.",
            aktion_typ=WorkflowStep.AKTION_GENEHMIGEN,
            zustaendig_rolle=WorkflowStep.ROLLE_DIREKTER_VORGESETZTER,
            frist_tage=3,
        )

        # Schritt 2: Team-Queue
        schritt2 = WorkflowStep(
            template=template,
            reihenfolge=2,
            titel="Zeiterfassungs-Team bearbeitet",
            beschreibung="Das zustaendige Team bucht den Antrag und schliesst ihn ab.",
            aktion_typ=WorkflowStep.AKTION_BEARBEITEN,
            zustaendig_rolle=WorkflowStep.ROLLE_TEAM_QUEUE,
            frist_tage=5,
        )
        if team:
            schritt2.zustaendig_team = team
        schritt2.save()

        self.stdout.write(self.style.SUCCESS(f"  Erstellt: {name} (trigger={trigger})"))
