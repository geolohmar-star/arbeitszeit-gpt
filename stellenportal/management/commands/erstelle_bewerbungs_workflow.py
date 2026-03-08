"""
Management Command: erstelle_bewerbungs_workflow

Legt die PG-TeamQueue und das WorkflowTemplate "Interne Stellenbewerbung"
an. Idempotent – wird bei wiederholtem Aufruf uebersprungen.

Aufruf:
  python manage.py erstelle_bewerbungs_workflow
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Legt TeamQueue PG und WorkflowTemplate Stellenbewerbung an."

    def handle(self, *args, **options):
        self._erstelle_pg_queue()
        self._erstelle_template()
        self.stdout.write(self.style.SUCCESS("Bewerbungs-Workflow eingerichtet."))

    # ------------------------------------------------------------------
    def _erstelle_pg_queue(self):
        from formulare.models import TeamQueue
        from hr.models import HRMitarbeiter

        queue, created = TeamQueue.objects.get_or_create(
            name="Personalgewinnung",
            defaults={"beschreibung": "Bearbeitungsstapel fuer interne Stellenbewerbungen (OrgEinheit PG)"},
        )
        if created:
            # Alle PG-Mitglieder als Mitglieder eintragen
            pg_user_ids = list(
                HRMitarbeiter.objects
                .filter(stelle__org_einheit__kuerzel="PG")
                .exclude(user__isnull=True)
                .values_list("user_id", flat=True)
            )
            if pg_user_ids:
                queue.mitglieder.set(pg_user_ids)
            self.stdout.write(
                f"  [OK]   TeamQueue 'Personalgewinnung' (pk={queue.pk}) mit {len(pg_user_ids)} Mitgliedern angelegt."
            )
        else:
            self.stdout.write(f"  [SKIP] TeamQueue 'Personalgewinnung' bereits vorhanden (pk={queue.pk}).")
        return queue

    def _erstelle_template(self):
        from formulare.models import TeamQueue
        from workflow.models import WorkflowTemplate, WorkflowStep, WorkflowTransition

        existing = WorkflowTemplate.objects.filter(
            trigger_event="stellenbewerbung_eingegangen"
        ).first()
        if existing:
            if existing.ist_graph_workflow:
                self.stdout.write(
                    f"  [SKIP] WorkflowTemplate 'Interne Stellenbewerbung' bereits vorhanden "
                    f"(Graph-Workflow, pk={existing.pk})."
                )
                return
            # Altes lineares Template durch Graph-Workflow ersetzen
            self.stdout.write(
                f"  [UPD]  Altes lineares Template (pk={existing.pk}) wird durch "
                f"Graph-Workflow mit GF-Abzweig ersetzt ..."
            )
            existing.delete()

        pg_queue = TeamQueue.objects.get(name="Personalgewinnung")

        template = WorkflowTemplate.objects.create(
            name="Interne Stellenbewerbung",
            beschreibung=(
                "Bearbeitungsprozess fuer interne Stellenbewerbungen. "
                "Startet automatisch wenn ein Mitarbeiter eine Bewerbung einreicht. "
                "Bei Fuehrungsstellen ist zusaetzlich eine Genehmigung durch die GF erforderlich."
            ),
            kategorie="pruefung",
            trigger_event="stellenbewerbung_eingegangen",
            ist_aktiv=True,
            ist_graph_workflow=True,
        )

        # Schritt 1: PG prueft Bewerbung
        s1 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            schritt_typ="task",
            titel="Bewerbung pruefen",
            beschreibung=(
                "Eingegangene Bewerbung sichten und entscheiden: "
                "Kandidat/in zum Gespraech einladen oder Bewerbung absagen."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="team_queue",
            zustaendig_team=pg_queue,
            frist_tage=3,
        )

        # Schritt 2: Vorstellungsgespraech
        s2 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=2,
            schritt_typ="task",
            titel="Vorstellungsgespraech fuehren",
            beschreibung=(
                "Vorstellungsgespraech durchfuehren und dokumentieren. "
                "Anschliessend Entscheidung: Kandidat/in weiter empfehlen oder absagen."
            ),
            aktion_typ="entscheiden",
            zustaendig_rolle="team_queue",
            zustaendig_team=pg_queue,
            frist_tage=7,
        )

        # Schritt 3 (Abzweig): GF genehmigt – nur bei Fuehrungsstellen
        s3_gf = WorkflowStep.objects.create(
            template=template,
            reihenfolge=3,
            schritt_typ="task",
            titel="Geschaeftsfuehrung genehmigt",
            beschreibung=(
                "Bei Fuehrungsstellen muss die Geschaeftsfuehrung der Besetzung zustimmen. "
                "Bitte Bewerbungsunterlagen und Empfehlung der Personalgewinnung sichten."
            ),
            aktion_typ="genehmigen",
            zustaendig_rolle="geschaeftsfuehrung",
            frist_tage=5,
        )

        # Schritt 4: Abschlussentscheidung durch PG
        s4 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=4,
            schritt_typ="task",
            titel="Abschlussentscheidung",
            beschreibung=(
                "Angebot unterbreiten oder Bewerbung abschliessen. "
                "Bewerber ueber das Ergebnis informieren."
            ),
            aktion_typ="informieren",
            zustaendig_rolle="team_queue",
            zustaendig_team=pg_queue,
            frist_tage=3,
        )

        # Schritt 5: Bewerber nimmt Kenntnis
        s5 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=5,
            schritt_typ="task",
            titel="Bewerber bestaetigt Ergebnis",
            beschreibung="Der Bewerber nimmt Kenntnis vom Ergebnis des Bewerbungsprozesses.",
            aktion_typ="informieren",
            zustaendig_rolle="antragsteller",
            frist_tage=5,
        )

        # Transitions (Graph-Logik)
        # S1 → S2: immer
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s1,
            zu_schritt=s2,
            bedingung_typ="immer",
            label="weiter",
        )

        # S2 → S3_GF: nur bei Fuehrungsstellen
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s2,
            zu_schritt=s3_gf,
            bedingung_typ="python",
            bedingung_python_code="content_object.ausschreibung.ist_fuehrungsstelle",
            label="Fuehrungsstelle",
            prioritaet=1,
        )

        # S2 → S4: bei normalen Stellen (kein Fuehrungsstellen-Abzweig)
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s2,
            zu_schritt=s4,
            bedingung_typ="python",
            bedingung_python_code="not content_object.ausschreibung.ist_fuehrungsstelle",
            label="normale Stelle",
            prioritaet=2,
        )

        # S3_GF → S4: nach GF-Genehmigung immer weiter
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s3_gf,
            zu_schritt=s4,
            bedingung_typ="immer",
            label="weiter",
        )

        # S4 → S5: immer
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s4,
            zu_schritt=s5,
            bedingung_typ="immer",
            label="weiter",
        )

        # S5 → Ende (NULL): Workflow abgeschlossen
        WorkflowTransition.objects.create(
            template=template,
            von_schritt=s5,
            zu_schritt=None,
            bedingung_typ="immer",
            label="abgeschlossen",
        )

        self.stdout.write(
            f"  [OK]   WorkflowTemplate 'Interne Stellenbewerbung' (pk={template.pk}) "
            f"mit 5 Schritten + GF-Abzweig erstellt (Graph-Workflow)."
        )
