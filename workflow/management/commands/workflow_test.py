"""Management Command zum Testen der Workflow-Engine

Verwendung:
    python manage.py workflow_test
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from workflow.models import WorkflowTemplate
from workflow.services import WorkflowEngine

User = get_user_model()


class Command(BaseCommand):
    help = "Testet die Workflow-Engine"

    def add_arguments(self, parser):
        parser.add_argument(
            "--template",
            type=int,
            help="Template-ID die getestet werden soll",
        )
        parser.add_argument(
            "--user",
            type=str,
            default="admin",
            help="Username des Users der den Workflow startet",
        )

    def handle(self, *args, **options):
        template_id = options.get("template")
        username = options.get("user")

        # User holen
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User '{username}' nicht gefunden!")
            )
            return

        # Template holen oder alle auflisten
        if template_id:
            try:
                template = WorkflowTemplate.objects.get(pk=template_id)
            except WorkflowTemplate.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Template mit ID {template_id} nicht gefunden!")
                )
                return

            self.stdout.write(f"\nTeste Template: {template.name}\n")
            self.test_template(template, user)
        else:
            # Alle Templates auflisten
            templates = WorkflowTemplate.objects.filter(ist_aktiv=True)
            if not templates.exists():
                self.stdout.write(
                    self.style.WARNING("Keine aktiven Templates gefunden!")
                )
                self.stdout.write("\nBitte erstelle zuerst ein Template im Admin oder Editor.")
                return

            self.stdout.write("\nVerfuegbare Templates:\n")
            for t in templates:
                self.stdout.write(
                    f"  [{t.id}] {t.name} - {t.schritte.count()} Schritte"
                )

            self.stdout.write(
                "\nFuehre aus mit: python manage.py workflow_test --template=<ID>"
            )

    def test_template(self, template, user):
        """Testet ein Template durch Simulation."""
        self.stdout.write(f"Template: {template.name}")
        self.stdout.write(f"Kategorie: {template.get_kategorie_display()}")
        self.stdout.write(f"Schritte: {template.schritte.count()}\n")

        # Schritte anzeigen
        self.stdout.write("Workflow-Schritte:")
        for step in template.schritte.all().order_by("reihenfolge"):
            self.stdout.write(
                f"  {step.reihenfolge}. {step.titel} "
                f"({step.get_aktion_typ_display()}) - "
                f"Zustaendig: {step.get_zustaendig_rolle_display()}"
            )

        # Engine-Test
        self.stdout.write("\n" + "="*50)
        self.stdout.write("ENGINE-TEST")
        self.stdout.write("="*50 + "\n")

        engine = WorkflowEngine()

        # Test 1: Rollen-Aufloesung
        self.stdout.write("Test 1: Rollen-Aufloesung\n")

        rollen = [
            "gf",
            "hr",
            "direkte_fuehrungskraft",
            "abteilungsleitung",
            "bereichsleitung",
        ]

        for rolle in rollen:
            stelle = engine.resolve_rolle(rolle)
            if stelle:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {rolle} -> {stelle.kuerzel} ({stelle.bezeichnung})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  {rolle} -> Nicht gefunden")
                )

        # Test 2: Workflow-Start (Mock-Objekt)
        self.stdout.write("\n\nTest 2: Workflow-Start Simulation")
        self.stdout.write("(Hinweis: Benoetigt ein echtes Objekt zum Testen)\n")
        self.stdout.write(
            "Um einen echten Workflow zu starten, verwende:\n"
            "  /workflow/start/<template_id>/?object_type=formulare.zagantrag&object_id=<id>"
        )

        self.stdout.write("\n" + self.style.SUCCESS("Test abgeschlossen!"))
