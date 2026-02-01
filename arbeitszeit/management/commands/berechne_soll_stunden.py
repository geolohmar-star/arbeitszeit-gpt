# arbeitszeit/management/commands/berechne_soll_stunden.py
"""
Management Command: Berechnet Soll-Arbeitsstunden für Mitarbeiter
"""

from django.core.management.base import BaseCommand
from arbeitszeit.models import MonatlicheArbeitszeitSoll, Mitarbeiter
from django.utils import timezone
import calendar


class Command(BaseCommand):
    help = 'Berechnet Soll-Arbeitsstunden für alle aktiven Mitarbeiter'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--jahr',
            type=int,
            help='Jahr (Standard: aktuelles Jahr)'
        )
        parser.add_argument(
            '--monat',
            type=int,
            help='Monat 1-12 (Standard: aktueller Monat)'
        )
        parser.add_argument(
            '--alle-monate',
            action='store_true',
            help='Berechnet alle 12 Monate des Jahres'
        )
        parser.add_argument(
            '--mitarbeiter',
            type=int,
            help='Nur für bestimmten Mitarbeiter (ID)'
        )
    
    def handle(self, *args, **options):
        heute = timezone.now().date()
        
        jahr = options.get('jahr') or heute.year
        monat = options.get('monat') or heute.month
        alle_monate = options.get('alle_monate')
        mitarbeiter_id = options.get('mitarbeiter')
        
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(self.style.SUCCESS('  📊 BERECHNUNG SOLL-ARBEITSSTUNDEN'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        # Mitarbeiter-Filter
        if mitarbeiter_id:
            mitarbeiter_qs = Mitarbeiter.objects.filter(id=mitarbeiter_id, aktiv=True)
            if not mitarbeiter_qs.exists():
                self.stdout.write(self.style.ERROR(f'❌ Mitarbeiter mit ID {mitarbeiter_id} nicht gefunden!'))
                return
        else:
            mitarbeiter_qs = Mitarbeiter.objects.filter(aktiv=True)
        
        self.stdout.write(f'\nAktive Mitarbeiter: {mitarbeiter_qs.count()}')
        
        erfolge = 0
        fehler_liste = []
        
        if alle_monate:
            # Alle 12 Monate berechnen
            self.stdout.write(f'Berechne für Jahr {jahr} (alle Monate)...\n')
            
            for m in range(1, 13):
                monat_name = calendar.month_name[m]
                self.stdout.write(f'\n--- {monat_name} {jahr} ---')
                
                monat_erfolge, monat_fehler = self._berechne_monat(
                    mitarbeiter_qs, 
                    jahr, 
                    m
                )
                
                erfolge += monat_erfolge
                fehler_liste.extend(monat_fehler)
        else:
            # Einzelner Monat
            monat_name = calendar.month_name[monat]
            self.stdout.write(f'\nBerechne für {monat_name} {jahr}...\n')
            
            erfolge, fehler_liste = self._berechne_monat(
                mitarbeiter_qs,
                jahr,
                monat
            )
        
        # Zusammenfassung
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'✅ Erfolgreich: {erfolge}'))
        
        if fehler_liste:
            self.stdout.write(self.style.WARNING(f'⚠️  Fehler: {len(fehler_liste)}'))
            self.stdout.write('\nMitarbeiter ohne Arbeitszeitvereinbarung:')
            
            # Gruppiere Fehler nach Mitarbeiter
            ma_fehler = {}
            for fehler in fehler_liste:
                ma_name = fehler['mitarbeiter'].vollname
                if ma_name not in ma_fehler:
                    ma_fehler[ma_name] = []
                ma_fehler[ma_name].append(fehler['monat'])
            
            for ma_name, monate in ma_fehler.items():
                monate_str = ", ".join(monate)
                self.stdout.write(f"  ❌ {ma_name}: {monate_str}")
        
        self.stdout.write('='*70 + '\n')
    
    def _berechne_monat(self, mitarbeiter_qs, jahr, monat):
        """
        Berechnet Soll-Stunden für einen Monat.
        
        Returns:
            tuple: (erfolge_count, fehler_liste)
        """
        erfolge = 0
        fehler = []
        monat_name = calendar.month_name[monat]
        
        for ma in mitarbeiter_qs:
            try:
                obj = MonatlicheArbeitszeitSoll.berechne_und_speichere(ma, jahr, monat)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {ma.vollname}: "
                        f"{obj.arbeitstage_effektiv} AT, "
                        f"{obj.feiertage_anzahl} FT, "
                        f"{obj.wochenstunden}h/Wo, "
                        f"Soll: {obj.soll_stunden_formatiert}"
                    )
                )
                erfolge += 1
                
            except ValueError as e:
                # Keine Vereinbarung gefunden
                self.stdout.write(
                    self.style.WARNING(f"  ⚠️  {ma.vollname}: {e}")
                )
                fehler.append({
                    'mitarbeiter': ma,
                    'monat': monat_name,
                    'fehler': str(e)
                })
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {ma.vollname}: Fehler - {e}")
                )
                fehler.append({
                    'mitarbeiter': ma,
                    'monat': monat_name,
                    'fehler': str(e)
                })
        
        return erfolge, fehler
