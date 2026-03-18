"""
Management Command: erstelle_gutschrift_workflow

Legt das WorkflowTemplate "Veranstaltungs-Gutschrift" an (idempotent).

Ablauf:
  1. Ersteller prueft Sammelliste (antragsteller)
  2a. Abteilungsleiter genehmigt  (wenn reichweite == 'abteilung')
  2b. Bereichsleiter genehmigt    (wenn reichweite == 'bereich')
  2c. Geschaeftsfuehrung genehmigt (wenn reichweite == 'unternehmen')
  3. ZG-Team Stapel (Zeitgutschriften-Team prueft)
  4. ZA-Team / Zeiterfassung bucht
  5. Antragsteller prueft Abschluss

Aufruf:
  python manage.py erstelle_gutschrift_workflow
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Legt WorkflowTemplate 'Veranstaltungs-Gutschrift' an (idempotent)."

    def handle(self, *args, **options):
        self._erstelle_template()
        self.stdout.write(self.style.SUCCESS("Gutschrift-Workflow eingerichtet."))

    def _erstelle_template(self):
        from formulare.models import TeamQueue
        from workflow.models import WorkflowTemplate, WorkflowStep, WorkflowTransition

        TRIGGER = "veranstaltung_gutschrift_eingereicht"

        existing = WorkflowTemplate.objects.filter(trigger_event=TRIGGER).first()
        if existing:
            hat_archivierung = existing.schritte.filter(aktion_typ="archivieren").exists()
            if hat_archivierung:
                self.stdout.write(
                    f"  [SKIP] Template 'Veranstaltungs-Gutschrift' (pk={existing.pk}) "
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
                    "  [ERR]  TeamQueue 'Zeitgutschriften-Team' (kuerzel=ZG) nicht gefunden. "
                    "Bitte erst im Team-Builder anlegen."
                )
            )
            return
        if not za_team:
            self.stdout.write(
                self.style.ERROR(
                    "  [ERR]  TeamQueue 'ZA-Team / Zeiterfassung' nicht gefunden. "
                    "Bitte erst im Team-Builder anlegen."
                )
            )
            return

        # Template anlegen
        template = WorkflowTemplate.objects.create(
            name="Veranstaltungs-Gutschrift",
            beschreibung=(
                "Bearbeitungsprozess fuer Zeitgutschrift-Sammellisten aus Veranstaltungen. "
                "Startet automatisch wenn eine Gutschrift eingereicht wird. "
                "Genehmigungsstufe richtet sich nach der Reichweite der Veranstaltung."
            ),
            kategorie="genehmigung",
            trigger_event=TRIGGER,
            ist_aktiv=True,
            ist_graph_workflow=True,
        )

        # --- Schritte anlegen ---

        # Schritt 1: Ersteller prueft
        s1 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            schritt_typ="task",
            titel="Ersteller prueft Sammelliste",
            beschreibung=(
                "Bitte die Teilnehmerliste und die berechneten Zeitgutschriften pruefen. "
                "Sicherstellen dass alle Teilnehmer korrekt erfasst und bestaetigt sind."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="antragsteller",
            frist_tage=2,
        )

        # Schritt 2a: Abteilungsleiter (Reichweite: Abteilung)
        s2a = WorkflowStep.objects.create(
            template=template,
            reihenfolge=2,
            schritt_typ="task",
            titel="Abteilungsleiter genehmigt",
            beschreibung=(
                "Zeitgutschrift fuer abteilungsweite Veranstaltung genehmigen. "
                "Teilnehmerliste und Stundenanzahl pruefen."
            ),
            aktion_typ="genehmigen",
            zustaendig_rolle="abteilungsleitung",
            frist_tage=3,
        )

        # Schritt 2b: Bereichsleiter (Reichweite: Bereich)
        s2b = WorkflowStep.objects.create(
            template=template,
            reihenfolge=3,
            schritt_typ="task",
            titel="Bereichsleiter genehmigt",
            beschreibung=(
                "Zeitgutschrift fuer bereichsweite Veranstaltung genehmigen. "
                "Teilnehmerliste und Stundenanzahl pruefen."
            ),
            aktion_typ="genehmigen",
            zustaendig_rolle="bereichsleitung",
            frist_tage=3,
        )

        # Schritt 2c: Geschaeftsfuehrung (Reichweite: Unternehmen)
        s2c = WorkflowStep.objects.create(
            template=template,
            reihenfolge=4,
            schritt_typ="task",
            titel="Geschaeftsfuehrung genehmigt",
            beschreibung=(
                "Zeitgutschrift fuer unternehmensweite Veranstaltung genehmigen. "
                "Teilnehmerliste und Stundenanzahl pruefen."
            ),
            aktion_typ="genehmigen",
            zustaendig_rolle="gf",
            frist_tage=5,
        )

        # Schritt 3: ZG-Team Stapel
        s3 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=5,
            schritt_typ="task",
            titel="ZG-Team: Gutschrift-Liste pruefen",
            beschreibung=(
                "Genehmigte Zeitgutschrift-Sammelliste fachlich pruefen. "
                "Stunden und Faktoren kontrollieren, Freigabe fuer Buchung erteilen."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="team_queue",
            zustaendig_team=zg_team,
            frist_tage=3,
        )

        # Schritt 4: ZA-Team / Zeiterfassung bucht
        s4 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=6,
            schritt_typ="task",
            titel="ZA-Team: Zeitgutschriften buchen",
            beschreibung=(
                "Genehmigte Zeitgutschriften fuer alle Teilnehmer in die Zeiterfassung eintragen. "
                "PDF-Sammelliste als Beleg archivieren."
            ),
            aktion_typ="bearbeiten",
            zustaendig_rolle="team_queue",
            zustaendig_team=za_team,
            frist_tage=5,
        )

        # Schritt 5: Antragsteller Abschluss-Pruefung
        s5 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=7,
            schritt_typ="task",
            titel="Antragsteller: Abschluss bestaetigen",
            beschreibung=(
                "Bitte pruefen ob die Zeitgutschriften korrekt in der Zeiterfassung "
                "aller Teilnehmer erscheinen. Abschliessen wenn alles korrekt."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="antragsteller",
            frist_tage=3,
        )

        # --- Transitions anlegen ---

        # antrag_start → s1 (immer, wird intern durch die Engine beim Start gesetzt)
        # (kein WorkflowTransition noetig fuer den ersten Schritt)

        # s1 → s2a (Abteilung)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s1,
            zu_schritt=s2a,
            bedingung_typ="python",
            bedingung_python_code="content_object.feier.reichweite == 'abteilung'",
            label="Abteilung",
            prioritaet=1,
        )

        # s1 → s2b (Bereich)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s1,
            zu_schritt=s2b,
            bedingung_typ="python",
            bedingung_python_code="content_object.feier.reichweite == 'bereich'",
            label="Bereich",
            prioritaet=2,
        )

        # s1 → s2c (Unternehmen)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s1,
            zu_schritt=s2c,
            bedingung_typ="python",
            bedingung_python_code="content_object.feier.reichweite == 'unternehmen'",
            label="Unternehmen",
            prioritaet=3,
        )

        # s2a, s2b, s2c → s3 (immer, alle drei Genehmigungsstufen muenden im ZG-Team)
        for s2 in (s2a, s2b, s2c):
            WorkflowTransition.objects.create(
                template=template,
                von_schritt=s2,
                zu_schritt=s3,
                bedingung_typ="immer",
                prioritaet=1,
            )

        # s3 → s4 (immer)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s3,
            zu_schritt=s4,
            bedingung_typ="immer",
            prioritaet=1,
        )

        # s4 → s5 (immer)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s4,
            zu_schritt=s5,
            bedingung_typ="immer",
            prioritaet=1,
        )

        # Schritt 6: DMS-Archivierung (auto)
        from dms.models import DokumentKategorie
        ablage = DokumentKategorie.objects.filter(
            name="Veranstaltungs-Gutschriften"
        ).first()
        s6 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=8,
            schritt_typ="auto",
            titel="DMS-Ablage: Veranstaltungs-Gutschrift",
            beschreibung=(
                "Gutschrift automatisch im DMS unter "
                "'Zeitgutschriften > Veranstaltungs-Gutschriften' ablegen."
            ),
            aktion_typ="archivieren",
            zustaendig_rolle="direkter_vorgesetzter",
            frist_tage=0,
            auto_config={"kategorie_id": ablage.pk if ablage else None},
        )

        # s5 → s6 (Archivierung nach Abschlussbestaetigung)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s5,
            zu_schritt=s6,
            bedingung_typ="immer",
            prioritaet=1,
        )

        # s6 → Ende
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s6,
            zu_schritt=None,
            bedingung_typ="immer",
            prioritaet=1,
        )

        self.stdout.write(
            f"  [OK]   WorkflowTemplate 'Veranstaltungs-Gutschrift' (pk={template.pk}) "
            f"mit 8 Schritten und 11 Transitions erstellt."
        )
        self.stdout.write(f"         ZG-Team: {zg_team.name} (pk={zg_team.pk})")
        self.stdout.write(f"         ZA-Team: {za_team.name} (pk={za_team.pk})")
        self.stdout.write(
            "         Routing: Abteilung->AL | Bereich->BL | Unternehmen->GF"
        )

    def _ergaenze_archivierungs_schritt(self, template):
        """Haengt Archivierungs-Schritt an ein bestehendes Template an."""
        from workflow.models import WorkflowStep, WorkflowTransition
        from dms.models import DokumentKategorie

        ablage = DokumentKategorie.objects.filter(name="Veranstaltungs-Gutschriften").first()

        letzter = (
            WorkflowStep.objects.filter(template=template)
            .order_by("-reihenfolge")
            .first()
        )
        naechste_reihenfolge = (letzter.reihenfolge + 1) if letzter else 8

        s_archiv = WorkflowStep.objects.create(
            template=template,
            reihenfolge=naechste_reihenfolge,
            schritt_typ="auto",
            titel="DMS-Ablage: Veranstaltungs-Gutschrift",
            beschreibung=(
                "Gutschrift automatisch im DMS unter "
                "'Zeitgutschriften > Veranstaltungs-Gutschriften' ablegen."
            ),
            aktion_typ="archivieren",
            zustaendig_rolle="direkter_vorgesetzter",
            frist_tage=0,
            auto_config={"kategorie_id": ablage.pk if ablage else None},
        )

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
