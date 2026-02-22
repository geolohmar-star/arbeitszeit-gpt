"""Management Command: Bereinigt doppelte HRMitarbeiter-Eintraege"""
from django.core.management.base import BaseCommand
from django.db import transaction
from collections import defaultdict
from hr.models import HRMitarbeiter


class Command(BaseCommand):
    help = 'Bereinigt doppelte HRMitarbeiter-Eintraege (behaelt jeweils den aeltesten)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an was geloescht wuerde, ohne zu loeschen',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Gruppiere nach Vorname + Nachname
        duplikate_gruppen = defaultdict(list)
        for m in HRMitarbeiter.objects.all().order_by('id'):
            key = f'{m.vorname} {m.nachname}'
            duplikate_gruppen[key].append(m)

        # Finde Duplikate
        zu_loeschen = []
        for name, mitarbeiter_liste in duplikate_gruppen.items():
            if len(mitarbeiter_liste) > 1:
                # Behalte den ersten (niedrigste ID = aeltesten)
                behalten = mitarbeiter_liste[0]
                loeschen = mitarbeiter_liste[1:]

                self.stdout.write(f'\n{name}:')
                self.stdout.write(f'  BEHALTEN: ID {behalten.id}, Stelle: {behalten.stelle.kuerzel if behalten.stelle else "Keine"}')

                for m in loeschen:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  LOESCHEN: ID {m.id}, Stelle: {m.stelle.kuerzel if m.stelle else "Keine"}'
                        )
                    )
                    zu_loeschen.append(m)

        # Zusammenfassung
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'Gesamt: {HRMitarbeiter.objects.count()} HRMitarbeiter')
        self.stdout.write(f'Einzigartige Namen: {len(duplikate_gruppen)}')
        self.stdout.write(f'Zu loeschen: {len(zu_loeschen)}')

        if not zu_loeschen:
            self.stdout.write(self.style.SUCCESS('\nKeine Duplikate gefunden!'))
            return

        # Loeschen
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Nichts wurde geloescht.'))
            self.stdout.write('Fuehre ohne --dry-run aus um tatsaechlich zu loeschen.')
        else:
            self.stdout.write(self.style.WARNING(f'\nLoeschen von {len(zu_loeschen)} Duplikaten...'))

            with transaction.atomic():
                for m in zu_loeschen:
                    name = f'{m.vorname} {m.nachname}'
                    stelle_name = m.stelle.kuerzel if m.stelle else 'Keine'
                    m.delete()
                    self.stdout.write(f'  [OK] {name} (ID {m.id}, Stelle: {stelle_name})')

            self.stdout.write(self.style.SUCCESS(f'\n{len(zu_loeschen)} Duplikate erfolgreich geloescht!'))
            self.stdout.write(f'Verbleibend: {HRMitarbeiter.objects.count()} HRMitarbeiter')
