"""
Management Command: erstelle_gutschrift_workflow

Legt das WorkflowTemplate "Veranstaltungs-Gutschrift" an.
Idempotent – wird bei wiederholtem Aufruf uebersprungen (oder aktualisiert).

Ablauf:
  1. Zeitgutschriften-Team: Sammelliste pruefen und genehmigen
  2. Zeiterfassung-Team:    Gutschriften in die Zeiterfassung buchen

Aufruf:
  python manage.py erstelle_gutschrift_workflow
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Legt WorkflowTemplate 'Veranstaltungs-Gutschrift' an (idempotent)."

    def handle(self, *args, **options):
        self._erstelle_template()
        self.stdout.write(self.style.SUCCESS("Gutschrift-Workflow eingerichtet."))

    def _erstelle_template(self):
        from formulare.models import TeamQueue
        from workflow.models import WorkflowTemplate, WorkflowStep

        TRIGGER = "veranstaltung_gutschrift_eingereicht"

        existing = WorkflowTemplate.objects.filter(trigger_event=TRIGGER).first()
        if existing:
            self.stdout.write(
                f"  [SKIP] Template 'Veranstaltungs-Gutschrift' bereits vorhanden "
                f"(pk={existing.pk})."
            )
            return

        zg_team = TeamQueue.objects.filter(name__icontains="Zeitgutschrift").first()
        ze_team = TeamQueue.objects.filter(name__icontains="Zeiterfassung").first()

        if not zg_team:
            self.stdout.write(
                self.style.ERROR("  [ERR]  TeamQueue 'Zeitgutschriften-Team' nicht gefunden.")
            )
            return
        if not ze_team:
            self.stdout.write(
                self.style.ERROR("  [ERR]  TeamQueue 'Zeiterfassung-Team' nicht gefunden.")
            )
            return

        template = WorkflowTemplate.objects.create(
            name="Veranstaltungs-Gutschrift",
            beschreibung=(
                "Bearbeitungsprozess fuer Zeitgutschrift-Sammellisten aus Veranstaltungen. "
                "Startet automatisch wenn eine Gutschrift eingereicht wird. "
                "Schritt 1: Zeitgutschriften-Team prueft und genehmigt die Liste. "
                "Schritt 2: Zeiterfassung-Team bucht die Gutschriften."
            ),
            kategorie="pruefung",
            trigger_event=TRIGGER,
            ist_aktiv=True,
            ist_graph_workflow=False,
        )

        # Schritt 1: Zeitgutschriften-Team prueft
        WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            schritt_typ="task",
            titel="Gutschrift-Liste pruefen",
            beschreibung=(
                "Teilnehmerliste der Veranstaltungs-Gutschrift pruefen und genehmigen. "
                "Sicherstellen dass alle Teilnehmer korrekt erfasst und bestaetigt sind."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="team_queue",
            zustaendig_team=zg_team,
            frist_tage=3,
        )

        # Schritt 2: Zeiterfassung-Team bucht
        WorkflowStep.objects.create(
            template=template,
            reihenfolge=2,
            schritt_typ="task",
            titel="Zeitgutschriften buchen",
            beschreibung=(
                "Genehmigte Zeitgutschriften fuer alle Teilnehmer in die Zeiterfassung eintragen. "
                "PDF-Sammelliste als Beleg archivieren."
            ),
            aktion_typ="buchen",
            zustaendig_rolle="team_queue",
            zustaendig_team=ze_team,
            frist_tage=5,
        )

        self.stdout.write(
            f"  [OK]   WorkflowTemplate 'Veranstaltungs-Gutschrift' (pk={template.pk}) "
            f"mit 2 Schritten erstellt."
        )
        self.stdout.write(
            f"         Schritt 1 -> {zg_team.name} (pk={zg_team.pk})"
        )
        self.stdout.write(
            f"         Schritt 2 -> {ze_team.name} (pk={ze_team.pk})"
        )
