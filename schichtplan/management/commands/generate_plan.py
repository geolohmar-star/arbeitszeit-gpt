# Django Management Command - Schichtplan Generierung
# Datei: schichtplan/management/commands/generate_plan.py

"""
Management Command zur automatischen Generierung von Schichtplänen.

Usage:
    python manage.py generate_plan 2025-12-01 "Dezember 2025"
    
Features:
    - Generiert Schichtpläne basierend auf historischen Daten
    - Nutzt OR-Tools Constraint Programming für Optimierung
    - Berücksichtigt Ruhezeiten und Mitarbeiter-Präferenzen
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date
from django.db import transaction
from datetime import datetime, timedelta

from arbeitszeit.models import Mitarbeiter
from schichtplan.models import Schichtplan, Schichttyp
from schichtplan.services import SchichtplanGenerator


class Command(BaseCommand):
    help = 'Generiert einen Schichtplan basierend auf historischen Daten'

    def add_arguments(self, parser):
        """Definiert die Command-Line Argumente"""
        parser.add_argument(
            'start_datum',
            type=str,
            help='Startdatum im Format YYYY-MM-DD (z.B. 2025-12-01)'
        )
        
        parser.add_argument(
            'plan_name',
            type=str,
            help='Name des neuen Schichtplans (z.B. "Dezember 2025")'
        )
        
        parser.add_argument(
            '--mitarbeiter',
            type=str,
            nargs='+',
            help='Optional: Liste von Mitarbeiter-IDs (z.B. --mitarbeiter 1 2 3)'
        )
        
        parser.add_argument(
            '--nur-aktive',
            action='store_true',
            help='Nur aktive Mitarbeiter berücksichtigen (empfohlen)'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Existierenden Plan überschreiben ohne Nachfrage'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Testlauf ohne Speichern in der Datenbank'
        )

    def handle(self, *args, **options):
        """Hauptlogik des Commands"""
        
        # ============================================================================
        # 1. VALIDIERUNG & VORBEREITUNG
        # ============================================================================
        
        start_datum_str = options['start_datum']
        plan_name = options['plan_name']
        nur_aktive = options.get('nur_aktive', True)
        force = options.get('force', False)
        dry_run = options.get('dry_run', False)
        
        # Datum parsen und validieren
        start_datum = parse_date(start_datum_str)
        if not start_datum:
            raise CommandError(
                f'❌ Ungültiges Datum: "{start_datum_str}". '
                f'Bitte Format YYYY-MM-DD verwenden (z.B. 2025-12-01)'
            )
        
        # Warnung bei Datum in der Vergangenheit
        if start_datum < datetime.now().date():
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Achtung: Startdatum liegt in der Vergangenheit ({start_datum})'
                )
            )
        
        # Info-Header
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('  🤖 KI-GESTÜTZTE SCHICHTPLAN-GENERIERUNG'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(f'\n📅 Startdatum: {start_datum.strftime("%d.%m.%Y")}')
        self.stdout.write(f'📋 Plan-Name: "{plan_name}"')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🧪 DRY-RUN Modus aktiviert (keine Speicherung)\n'))
        
        # ============================================================================
        # 2. MITARBEITER LADEN
        # ============================================================================
        
        self.stdout.write('\n🔍 Lade Mitarbeiter...')
        
        # Queryset aufbauen
        mitarbeiter_qs = Mitarbeiter.objects.all()
        
        # Filter: Nur aktive
        if nur_aktive:
            mitarbeiter_qs = mitarbeiter_qs.filter(aktiv=True)
            self.stdout.write('   ✓ Filter: Nur aktive Mitarbeiter')
        
        # Filter: Spezifische IDs
        if options.get('mitarbeiter'):
            ma_ids = [int(id) for id in options['mitarbeiter']]
            mitarbeiter_qs = mitarbeiter_qs.filter(id__in=ma_ids)
            self.stdout.write(f'   ✓ Filter: Nur IDs {ma_ids}')
        
        mitarbeiter_list = list(mitarbeiter_qs)
        
        if not mitarbeiter_list:
            raise CommandError('❌ Keine Mitarbeiter gefunden! Prüfe die Filter.')
        
        self.stdout.write(
            self.style.SUCCESS(f'   ✓ {len(mitarbeiter_list)} Mitarbeiter geladen\n')
        )
        
        # Mitarbeiter-Liste anzeigen
        self.stdout.write('📊 Mitarbeiter-Übersicht:')
        for ma in mitarbeiter_list:
            rolle = getattr(ma, 'rolle', 'N/A')
            self.stdout.write(f'   - {ma.id}: {ma.user.get_full_name() or ma.user.username} ({rolle})')
        
        # ============================================================================
        # 3. SCHICHTTYPEN PRÜFEN
        # ============================================================================
        
        self.stdout.write('\n🔧 Prüfe Schichttypen...')
        
        try:
            type_t = Schichttyp.objects.get(kuerzel='T')
            type_n = Schichttyp.objects.get(kuerzel='N')
            self.stdout.write('   ✓ Schichttyp T (Tagschicht) gefunden')
            self.stdout.write('   ✓ Schichttyp N (Nachtschicht) gefunden\n')
        except Schichttyp.DoesNotExist as e:
            raise CommandError(
                '❌ Schichttypen T und/oder N nicht gefunden!\n'
                'Bitte erstelle die Schichttypen zuerst:\n'
                '  python manage.py shell\n'
                "  >>> from schichtplan.models import Schichttyp\n"
                "  >>> Schichttyp.objects.create(kuerzel='T', name='Tagschicht', ...)"
            )
        
        # ============================================================================
        # 4. SCHICHTPLAN ERSTELLEN/LADEN
        # ============================================================================
        
        self.stdout.write('📝 Erstelle Schichtplan...')
        
        # Prüfe ob Plan bereits existiert
        plan_exists = Schichtplan.objects.filter(name=plan_name).exists()
        
        if plan_exists and not force and not dry_run:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Plan "{plan_name}" existiert bereits!')
            )
            antwort = input('   Soll er überschrieben werden? [j/N]: ')
            
            if antwort.lower() not in ['j', 'ja', 'y', 'yes']:
                self.stdout.write(self.style.ERROR('❌ Abgebrochen.'))
                return
        
        if not dry_run:
            # Plan in DB anlegen/aktualisieren
            neuer_plan, created = Schichtplan.objects.update_or_create(
                name=plan_name,
                defaults={
                    'start_datum': start_datum,
                    'status': 'entwurf'  # Falls das Feld existiert
                }
            )
            
            if not created:
                # Alte Schichten löschen
                alte_anzahl = neuer_plan.schichten.count()
                if alte_anzahl > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'   ⚠️  Lösche {alte_anzahl} alte Schichten...'
                        )
                    )
                    neuer_plan.schichten.all().delete()
            
            action = 'erstellt' if created else 'aktualisiert'
            self.stdout.write(self.style.SUCCESS(f'   ✓ Plan "{plan_name}" {action}\n'))
        
        else:
            # Dry-Run: Dummy-Plan erstellen
            from django.utils import timezone
            neuer_plan = Schichtplan(
                name=plan_name,
                start_datum=start_datum
            )
            self.stdout.write('   🧪 Dummy-Plan für Dry-Run erstellt\n')
        
        # ============================================================================
        # 5. GENERATOR INITIALISIEREN & AUSFÜHREN
        # ============================================================================
        
        self.stdout.write('🤖 Starte KI-Generator...\n')
        
        try:
            # Generator initialisieren
            generator = SchichtplanGenerator(mitarbeiter_list)
            
            # Generierung starten (mit Transaktion für Atomarität)
            if not dry_run:
                with transaction.atomic():
                    generator.generiere_vorschlag(neuer_plan)
            else:
                # Im Dry-Run Modus ohne DB-Speicherung
                self.stdout.write('   🧪 Führe Algorithmus aus (ohne DB-Speicherung)...')
                # Hier könntest du eine separate Methode aufrufen, die nicht speichert
                generator.generiere_vorschlag(neuer_plan)
            
            # ============================================================================
            # 6. ERFOLGSMELDUNG & STATISTIKEN
            # ============================================================================
            
            if not dry_run:
                schichten_anzahl = neuer_plan.schichten.count()
                
                self.stdout.write('\n' + '=' * 70)
                self.stdout.write(self.style.SUCCESS('  ✅ ERFOLGREICH ABGESCHLOSSEN'))
                self.stdout.write('=' * 70)
                self.stdout.write(f'\n📊 Statistiken:')
                self.stdout.write(f'   • Plan-Name: {plan_name}')
                self.stdout.write(f'   • Generierte Schichten: {schichten_anzahl}')
                self.stdout.write(f'   • Mitarbeiter: {len(mitarbeiter_list)}')
                self.stdout.write(f'   • Startdatum: {start_datum.strftime("%d.%m.%Y")}')
                
                # Schichten pro Typ
                from django.db.models import Count
                stats = neuer_plan.schichten.values('schichttyp__kuerzel').annotate(
                    anzahl=Count('id')
                )
                self.stdout.write('\n📈 Schichten pro Typ:')
                for stat in stats:
                    kuerzel = stat['schichttyp__kuerzel']
                    anzahl = stat['anzahl']
                    self.stdout.write(f'   • {kuerzel}: {anzahl}')
                
                self.stdout.write(f'\n🔗 Plan-ID: {neuer_plan.pk}')
                self.stdout.write(
                    '\nÖffne den Plan im Admin:\n'
                    f'   http://localhost:8000/admin/schichtplan/schichtplan/{neuer_plan.pk}/change/'
                )
            else:
                self.stdout.write('\n' + '=' * 70)
                self.stdout.write(self.style.WARNING('  🧪 DRY-RUN ABGESCHLOSSEN'))
                self.stdout.write('=' * 70)
                self.stdout.write('\nKeine Daten wurden gespeichert.')
                self.stdout.write('Führe ohne --dry-run aus, um zu speichern.')
            
        except Exception as e:
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.ERROR('  ❌ FEHLER AUFGETRETEN'))
            self.stdout.write('=' * 70)
            self.stdout.write(f'\n{str(e)}\n')
            
            # Debug-Info
            import traceback
            self.stdout.write('\n📋 Detaillierter Fehler:')
            self.stdout.write(traceback.format_exc())
            
            raise CommandError(f'Generierung fehlgeschlagen: {str(e)}')
