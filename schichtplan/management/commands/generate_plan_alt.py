# Datei: schichtplan/management/commands/generate_plan.py
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from arbeitszeit.models import Mitarbeiter
from schichtplan.models import Schichtplan
from schichtplan.services import SchichtplanGenerator # Importiere unseren Service

class Command(BaseCommand):
    help = 'Generiert einen Schichtplan basierend auf historischen Daten'

    def add_arguments(self, parser):
        parser.add_argument('start_datum', type=str, help='Startdatum Format YYYY-MM-DD (z.B. 2025-12-01)')
        parser.add_argument('plan_name', type=str, help='Name des neuen Plans')

    def handle(self, *args, **options):
        start_datum_str = options['start_datum']
        plan_name = options['plan_name']
        
        start_datum = parse_date(start_datum_str)
        if not start_datum:
            self.stdout.write(self.style.ERROR('Ungültiges Datum.'))
            return

        self.stdout.write(f"Starte Generierung für {plan_name} ab {start_datum}...")

        # 1. Neuen Plan in DB anlegen
        # update_or_create verhindert doppelte Pläne beim Testen
        neuer_plan, created = Schichtplan.objects.update_or_create(
            name=plan_name,
            defaults={'start_datum': start_datum}
        )
        
        if not created:
             self.stdout.write(self.style.WARNING(f"Plan '{plan_name}' existierte bereits. Lösche alte Einträge..."))
             neuer_plan.schichten.all().delete() # Alte Vorschläge bereinigen

        # 2. Generator initialisieren
        aktive_mitarbeiter = Mitarbeiter.objects.all() # Ggf. filter(aktiv=True)
        generator = SchichtplanGenerator(aktive_mitarbeiter)

        # 3. Ausführen
        try:
            generator.generiere_vorschlag(neuer_plan)
            self.stdout.write(self.style.SUCCESS(f"Fertig! Plan '{plan_name}' wurde erstellt."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Fehler: {str(e)}"))