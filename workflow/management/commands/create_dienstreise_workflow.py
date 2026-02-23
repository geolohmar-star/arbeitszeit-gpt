"""Management Command zum Erstellen eines Muster-Dienstreise-Workflows

Verwendung:
    python manage.py create_dienstreise_workflow
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from workflow.models import WorkflowTemplate, WorkflowStep

User = get_user_model()


class Command(BaseCommand):
    help = "Erstellt einen Muster-Workflow fuer Dienstreise-Genehmigung"

    def handle(self, *args, **options):
        # Admin-User holen (oder ersten User)
        try:
            user = User.objects.filter(is_staff=True).first()
            if not user:
                user = User.objects.first()
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("Kein User gefunden! Bitte zuerst User erstellen.")
            )
            return

        # Prüfe ob Template bereits existiert
        existing = WorkflowTemplate.objects.filter(
            trigger_event="dienstreise_erstellt"
        ).first()

        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"\nWorkflow-Template '{existing.name}' existiert bereits!"
                )
            )
            self.stdout.write(
                f"ID: {existing.id}, Schritte: {existing.schritte.count()}\n"
            )

            antwort = input("Loeschen und neu erstellen? (ja/nein): ")
            if antwort.lower() in ["ja", "j", "yes", "y"]:
                existing.delete()
                self.stdout.write(self.style.SUCCESS("Geloescht!\n"))
            else:
                self.stdout.write("Abgebrochen.\n")
                return

        # Template erstellen
        template = WorkflowTemplate.objects.create(
            name="Dienstreise-Genehmigung",
            beschreibung=(
                "Automatischer Genehmigungsworkflow fuer Dienstreiseantraege.\n\n"
                "Der Workflow durchlaeuft folgende Stationen:\n"
                "1. Pruefung durch direkte Fuehrungskraft\n"
                "2. Genehmigung durch Abteilungsleitung\n"
                "3. Bei hohen Kosten: zusaetzliche GF-Genehmigung\n"
                "4. Abschliessende Information an HR"
            ),
            kategorie="genehmigung",
            trigger_event="dienstreise_erstellt",
            ist_aktiv=True,
            erstellt_von=user,
            version=1,
        )

        # Schritt 1: Pruefung durch Fuehrungskraft
        schritt1 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=1,
            titel="Antrag pruefen",
            beschreibung=(
                "Bitte pruefen Sie den Dienstreiseantrag auf:\n"
                "- Notwendigkeit der Reise\n"
                "- Terminliche Machbarkeit\n"
                "- Vertretung waehrend Abwesenheit\n\n"
                "Bei Genehmigung wird der Antrag an die Abteilungsleitung "
                "zur finalen Freigabe weitergeleitet."
            ),
            aktion_typ="pruefen",
            zustaendig_rolle="direkte_fuehrungskraft",
            frist_tage=3,
            ist_parallel=False,
            eskalation_nach_tagen=5,
        )

        # Schritt 2: Genehmigung durch Abteilungsleitung
        schritt2 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=2,
            titel="Antrag genehmigen",
            beschreibung=(
                "Bitte genehmigen Sie den Dienstreiseantrag.\n\n"
                "Bereits geprueft von: Direkte Fuehrungskraft\n\n"
                "Zu pruefen:\n"
                "- Budgetrahmen\n"
                "- Geschaeftlicher Nutzen\n"
                "- Alternativen (z.B. Videokonferenz)"
            ),
            aktion_typ="genehmigen",
            zustaendig_rolle="abteilungsleitung",
            frist_tage=2,
            ist_parallel=False,
            eskalation_nach_tagen=4,
        )

        # Schritt 3: Bei hohen Kosten - GF-Freigabe
        # (In Phase 2 wuerde hier eine Bedingung greifen: kosten > 1000 EUR)
        schritt3 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=3,
            titel="GF-Freigabe (bei hohen Kosten)",
            beschreibung=(
                "Dieser Dienstreiseantrag ueberschreitet die normale Kostengrenze "
                "und benoetigt eine zusaetzliche Freigabe durch die Geschaeftsfuehrung.\n\n"
                "Hinweis: In Phase 2 wird dieser Schritt nur bei Kosten > 1000 EUR "
                "automatisch aktiviert."
            ),
            aktion_typ="freigeben",
            zustaendig_rolle="gf",
            frist_tage=2,
            ist_parallel=False,
            eskalation_nach_tagen=3,
            # Phase 2: bedingung_feld="geschaetzte_kosten"
            # Phase 2: bedingung_operator=">"
            # Phase 2: bedingung_wert="1000"
        )

        # Schritt 4: HR informieren
        schritt4 = WorkflowStep.objects.create(
            template=template,
            reihenfolge=4,
            titel="HR informieren",
            beschreibung=(
                "Der Dienstreiseantrag wurde vollstaendig genehmigt.\n\n"
                "Bitte nehmen Sie den Antrag zur Kenntnis und:\n"
                "- Reisekostenabrechnung vorbereiten\n"
                "- Ggf. Reisebuchungen unterstuetzen\n"
                "- Abwesenheit im System vermerken"
            ),
            aktion_typ="informieren",
            zustaendig_rolle="hr",
            frist_tage=1,
            ist_parallel=False,
            eskalation_nach_tagen=0,
        )

        # Erfolgsmeldung
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("WORKFLOW ERFOLGREICH ERSTELLT!"))
        self.stdout.write("="*60 + "\n")

        self.stdout.write(f"Template-ID: {template.id}")
        self.stdout.write(f"Name: {template.name}")
        self.stdout.write(f"Trigger-Event: {template.trigger_event}")
        self.stdout.write(f"Anzahl Schritte: {template.schritte.count()}\n")

        self.stdout.write("Workflow-Schritte:\n")
        for step in template.schritte.all().order_by("reihenfolge"):
            self.stdout.write(
                f"  {step.reihenfolge}. {step.titel} "
                f"({step.get_aktion_typ_display()}) - "
                f"{step.get_zustaendig_rolle_display()} - "
                f"Frist: {step.frist_tage} Tage"
            )

        self.stdout.write("\n" + self.style.SUCCESS("BEREIT ZUM TESTEN!") + "\n")
        self.stdout.write("Naechste Schritte:")
        self.stdout.write("1. Dienstreiseantrag erstellen: /formulare/dienstreise/erstellen/")
        self.stdout.write("2. Workflow wird automatisch gestartet")
        self.stdout.write("3. Tasks im Arbeitsstapel bearbeiten: /workflow/\n")
