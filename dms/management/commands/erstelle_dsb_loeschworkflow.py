"""
Management Command: erstelle_dsb_loeschworkflow

Legt das WorkflowTemplate "DMS-Loeschantrag" an (idempotent).

Ablauf:
  1. DSB-Team prueft Loeschantrag und genehmigt
  2. Auto: Loeschfreigabe-Flag am Dokument setzen

Aufruf:
  python manage.py erstelle_dsb_loeschworkflow
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

TRIGGER = "dms_loeschantrag_eingereicht"


class Command(BaseCommand):
    help = "Legt WorkflowTemplate 'DMS-Loeschantrag' an (idempotent)."

    def handle(self, *args, **options):
        self._erstelle_template()
        self.stdout.write(self.style.SUCCESS("DSB-Loeschworkflow eingerichtet."))

    def _erstelle_template(self):
        from formulare.models import TeamQueue
        from workflow.models import WorkflowTemplate, WorkflowStep, WorkflowTransition

        existing = WorkflowTemplate.objects.filter(trigger_event=TRIGGER).first()
        if existing:
            self.stdout.write(
                f"  [SKIP] Template 'DMS-Loeschantrag' (pk={existing.pk}) bereits vorhanden."
            )
            return

        dsb_team = (
            TeamQueue.objects.filter(kuerzel="DSB").first()
            or TeamQueue.objects.filter(name__icontains="DSB").first()
            or TeamQueue.objects.filter(name__icontains="Datenschutz").first()
        )
        if not dsb_team:
            self.stdout.write(
                self.style.ERROR(
                    "  [ERR]  TeamQueue 'DSB' nicht gefunden. "
                    "Bitte erst fixture laden: python manage.py loaddata formulare/fixtures/teamqueue.json"
                )
            )
            return

        template = WorkflowTemplate.objects.create(
            name="DMS-Loeschantrag",
            beschreibung=(
                "Pruefung und Freigabe von DMS-Loeschantraegen durch den Datenschutzbeauftragten. "
                "Startet automatisch wenn ein DMS-Admin eine Loeschung plant. "
                "Erst nach DSB-Freigabe wird das Dokument am geplanten Datum geloescht."
            ),
            kategorie="genehmigung",
            trigger_event=TRIGGER,
            ist_aktiv=True,
            ist_graph_workflow=True,
        )

        # Schritt 1: DSB-Team prueft und genehmigt
        s1 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            schritt_typ="task",
            titel="DSB: Loeschantrag pruefen",
            beschreibung=(
                "Loeschantrag datenschutzrechtlich pruefen. "
                "Aufbewahrungsfristen beachten (GoBD: Lohnunterlagen 10 J., "
                "Geschaeftsbriefe 6 J., Bewerbungsunterlagen 6 Monate nach Ablehnung). "
                "Nur freigeben wenn keine gesetzliche Aufbewahrungspflicht besteht."
            ),
            aktion_typ="genehmigen",
            zustaendig_rolle="team_queue",
            zustaendig_team=dsb_team,
            frist_tage=5,
        )

        # Schritt 2: Auto – Loeschfreigabe setzen
        s2 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=2,
            schritt_typ="auto",
            titel="Loeschfreigabe setzen",
            beschreibung="Loeschung-genehmigt-Flag am Dokument automatisch setzen.",
            aktion_typ="loeschung_freigeben",
            zustaendig_rolle="direkter_vorgesetzter",
            frist_tage=0,
        )

        # Transitionen
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s1,
            zu_schritt=s2,
            bedingung_typ="immer",
            prioritaet=1,
        )
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s2,
            zu_schritt=None,
            bedingung_typ="immer",
            prioritaet=1,
        )

        self.stdout.write(
            f"  [OK]   WorkflowTemplate 'DMS-Loeschantrag' (pk={template.pk}) "
            f"mit 2 Schritten erstellt."
        )
        self.stdout.write(f"         DSB-Team: {dsb_team.name} (pk={dsb_team.pk})")
