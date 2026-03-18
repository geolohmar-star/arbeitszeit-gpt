"""
Management Command: erstelle_betriebssport_workflow

Legt das WorkflowTemplate "Betriebssport" an (idempotent).

Ablauf:
  1. Verantwortlicher prueft Monatsliste        (antragsteller)
  2. ZG-Team: Sammelliste fachlich pruefen      (team_queue=ZG)
  3. ZA-Team: Zeitgutschriften buchen           (team_queue=ZA)
  4. Verantwortlicher: Abschluss bestaetigen    (antragsteller)

Aufruf:
  python manage.py erstelle_betriebssport_workflow
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Legt WorkflowTemplate 'Betriebssport' an (idempotent)."

    def handle(self, *args, **options):
        self._erstelle_template()
        self.stdout.write(self.style.SUCCESS("Betriebssport-Workflow eingerichtet."))

    def _erstelle_template(self):
        from formulare.models import TeamQueue
        from workflow.models import WorkflowTemplate, WorkflowStep, WorkflowTransition

        TRIGGER = "betriebssport_gutschrift_eingereicht"

        existing = WorkflowTemplate.objects.filter(trigger_event=TRIGGER).first()
        if existing:
            # Nur Archivierungs-Schritt ergaenzen falls noch nicht vorhanden
            hat_archivierung = existing.schritte.filter(aktion_typ="archivieren").exists()
            if hat_archivierung:
                self.stdout.write(
                    f"  [SKIP] Template 'Betriebssport' (pk={existing.pk}) "
                    f"hat bereits Archivierungs-Schritt."
                )
                return
            self.stdout.write(
                f"  [INFO] Ergaenze Archivierungs-Schritt zu Template pk={existing.pk}."
            )
            self._ergaenze_archivierungs_schritt(existing)
            return

        # Team-Queues suchen
        zg_team = (
            TeamQueue.objects.filter(kuerzel="ZG").first()
            or TeamQueue.objects.filter(name__icontains="Zeitgutschrift").first()
        )
        za_team = (
            TeamQueue.objects.filter(kuerzel="ZA").first()
            or TeamQueue.objects.filter(name__icontains="Zeitausgleich").first()
            or TeamQueue.objects.filter(name__icontains="Zeiterfassung").first()
        )

        if not zg_team:
            self.stdout.write(
                self.style.ERROR(
                    "  [ERR]  TeamQueue 'ZG' nicht gefunden. "
                    "Bitte erst im Team-Builder anlegen."
                )
            )
            return
        if not za_team:
            self.stdout.write(
                self.style.ERROR(
                    "  [ERR]  TeamQueue 'ZA' nicht gefunden. "
                    "Bitte erst im Team-Builder anlegen."
                )
            )
            return

        template = WorkflowTemplate.objects.create(
            name="Betriebssport",
            beschreibung=(
                "Bearbeitungsprozess fuer monatliche Betriebssport-Zeitgutschriften. "
                "Startet automatisch wenn der Verantwortliche die Monatsliste einreicht."
            ),
            kategorie="genehmigung",
            trigger_event=TRIGGER,
            ist_aktiv=True,
            ist_graph_workflow=True,
        )

        # Schritt 1: Verantwortlicher prueft
        s1 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            schritt_typ="task",
            titel="Verantwortlicher prueft Monatsliste",
            beschreibung=(
                "Bitte die Monatsliste pruefen: Einheiten, Teilnahmen und "
                "berechnete Stunden auf Richtigkeit kontrollieren."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="antragsteller",
            frist_tage=2,
        )

        # Schritt 2: ZG-Team
        s2 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=2,
            schritt_typ="task",
            titel="ZG-Team: Betriebssport-Liste pruefen",
            beschreibung=(
                "Betriebssport-Sammelliste fachlich pruefen. "
                "Stunden und Teilnehmerliste kontrollieren, Freigabe fuer Buchung erteilen."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="team_queue",
            zustaendig_team=zg_team,
            frist_tage=3,
        )

        # Schritt 3: ZA-Team bucht
        s3 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=3,
            schritt_typ="task",
            titel="ZA-Team: Zeitgutschriften buchen",
            beschreibung=(
                "Betriebssport-Zeitgutschriften fuer alle Teilnehmer in die "
                "Zeiterfassung eintragen. PDF-Sammelliste als Beleg archivieren."
            ),
            aktion_typ="bearbeiten",
            zustaendig_rolle="team_queue",
            zustaendig_team=za_team,
            frist_tage=5,
        )

        # Schritt 4: Abschluss-Bestaetigung
        s4 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=4,
            schritt_typ="task",
            titel="Verantwortlicher: Abschluss bestaetigen",
            beschreibung=(
                "Bitte pruefen ob die Zeitgutschriften korrekt in der Zeiterfassung "
                "aller Teilnehmer erscheinen. Abschliessen wenn alles stimmt."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="antragsteller",
            frist_tage=3,
        )

        # Transitionen (alle: immer)
        for von, zu in [(s1, s2), (s2, s3), (s3, s4)]:
            WorkflowTransition.objects.create(
                template=template,
                von_schritt=von,
                zu_schritt=zu,
                bedingung_typ="immer",
                prioritaet=1,
            )

        # Schritt 5: DMS-Archivierung (auto)
        from dms.models import DokumentKategorie
        ablage = DokumentKategorie.objects.filter(
            name="Betriebssport-Gutschriften"
        ).first()
        s5 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=5,
            schritt_typ="auto",
            titel="DMS-Ablage: Betriebssport-Gutschrift",
            beschreibung="Gutschrift automatisch im DMS unter 'Zeitgutschriften > Betriebssport-Gutschriften' ablegen.",
            aktion_typ="archivieren",
            zustaendig_rolle="direkter_vorgesetzter",
            frist_tage=0,
            auto_config={"kategorie_id": ablage.pk if ablage else None},
        )

        # Transition: Schritt 4 -> Schritt 5 (Archivierung)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s4,
            zu_schritt=s5,
            bedingung_typ="immer",
            prioritaet=1,
        )

        # Ende
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s5,
            zu_schritt=None,
            bedingung_typ="immer",
            prioritaet=1,
        )

        self.stdout.write(
            f"  [OK]   WorkflowTemplate 'Betriebssport' (pk={template.pk}) "
            f"mit 5 Schritten und 5 Transitionen erstellt."
        )
        self.stdout.write(f"         ZG-Team: {zg_team.name} (pk={zg_team.pk})")
        self.stdout.write(f"         ZA-Team: {za_team.name} (pk={za_team.pk})")

    def _ergaenze_archivierungs_schritt(self, template):
        """Haengt Archivierungs-Schritt an ein bestehendes Template an."""
        from workflow.models import WorkflowStep, WorkflowTransition
        from dms.models import DokumentKategorie

        ablage = DokumentKategorie.objects.filter(name="Betriebssport-Gutschriften").first()

        # Letzten Schritt (vor Ende) suchen
        letzter = (
            WorkflowStep.objects.filter(template=template)
            .order_by("-reihenfolge")
            .first()
        )
        naechste_reihenfolge = (letzter.reihenfolge + 1) if letzter else 5

        s_archiv = WorkflowStep.objects.create(
            template=template,
            reihenfolge=naechste_reihenfolge,
            schritt_typ="auto",
            titel="DMS-Ablage: Betriebssport-Gutschrift",
            beschreibung=(
                "Gutschrift automatisch im DMS unter "
                "'Zeitgutschriften > Betriebssport-Gutschriften' ablegen."
            ),
            aktion_typ="archivieren",
            zustaendig_rolle="direkter_vorgesetzter",
            frist_tage=0,
            auto_config={"kategorie_id": ablage.pk if ablage else None},
        )

        # Bisherige Abschluss-Transition (zu_schritt=None) umlenken
        alte_ende_transition = WorkflowTransition.objects.filter(
            template=template, zu_schritt=None
        ).order_by("-prioritaet").first()

        if alte_ende_transition and letzter:
            alte_ende_transition.zu_schritt = s_archiv
            alte_ende_transition.save()
            WorkflowTransition.objects.create(
                template=template,
                von_schritt=s_archiv,
                zu_schritt=None,
                bedingung_typ="immer",
                prioritaet=1,
            )

        self.stdout.write(
            f"  [OK]  Archivierungs-Schritt pk={s_archiv.pk} zu Template pk={template.pk} ergaenzt."
        )
