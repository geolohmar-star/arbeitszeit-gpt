"""
Debug-Command fuer Railway: Zeigt User und Berechtigungen

Ausfuehren mit: railway run python manage.py debug_railway
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from arbeitszeit.models import Mitarbeiter


class Command(BaseCommand):
    help = 'Zeigt User, Mitarbeiter und Berechtigungen (Debug fuer Railway)'

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write("RAILWAY DEBUG: USER & BERECHTIGUNGEN")
        self.stdout.write("=" * 70)

        # 1. Alle User auflisten
        self.stdout.write("\n### ALLE USER ###\n")
        users = User.objects.all().order_by('username')
        for user in users:
            self.stdout.write(f"\nUser: {user.username}")
            self.stdout.write(f"  - ID: {user.id}")
            self.stdout.write(f"  - Staff: {user.is_staff}")
            self.stdout.write(f"  - Superuser: {user.is_superuser}")
            self.stdout.write(f"  - Active: {user.is_active}")

            # Gruppen
            gruppen = list(user.groups.values_list('name', flat=True))
            self.stdout.write(f"  - Gruppen: {gruppen if gruppen else 'Keine'}")

            # Mitarbeiter-Objekt prüfen
            self.stdout.write(f"  - hasattr('mitarbeiter'): {hasattr(user, 'mitarbeiter')}")

            if hasattr(user, 'mitarbeiter'):
                try:
                    ma = user.mitarbeiter
                    self.stdout.write(f"  - Mitarbeiter-ID: {ma.id}")
                    self.stdout.write(f"  - Name: {ma.vorname} {ma.nachname}")
                    self.stdout.write(f"  - Personalnummer: {ma.personalnummer}")
                    self.stdout.write(f"  - Rolle: '{ma.rolle}'")
                    self.stdout.write(f"  - Abteilung: '{ma.abteilung}'")

                    # Berechtigungsprüfung
                    if ma.rolle:
                        rolle_lower = ma.rolle.strip().lower()
                        ist_schichtplaner = rolle_lower == 'schichtplaner'
                        self.stdout.write(f"  - Rolle normalisiert: '{rolle_lower}'")
                        self.stdout.write(f"  - Match 'schichtplaner': {ist_schichtplaner}")

                    if ma.abteilung:
                        abt_lower = ma.abteilung.strip().lower()
                        ist_kongos = abt_lower == 'kongos'
                        self.stdout.write(f"  - Abteilung normalisiert: '{abt_lower}'")
                        self.stdout.write(f"  - Match 'kongos': {ist_kongos}")

                except Exception as e:
                    self.stdout.write(f"  - FEHLER beim Laden: {e}")
            else:
                self.stdout.write("  - >>> KEIN Mitarbeiter-Objekt verknuepft! <<<")

        # 2. Alle Mitarbeiter ohne User
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("### MITARBEITER OHNE USER ###\n")
        mitarbeiter_ohne_user = Mitarbeiter.objects.filter(user__isnull=True)
        if mitarbeiter_ohne_user.exists():
            for ma in mitarbeiter_ohne_user:
                self.stdout.write(f"- {ma.vorname} {ma.nachname} (PN: {ma.personalnummer})")
        else:
            self.stdout.write("Keine Mitarbeiter ohne User gefunden.")

        # 3. Gruppen
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("### DJANGO GRUPPEN ###\n")
        gruppen = Group.objects.all()
        if gruppen.exists():
            for gruppe in gruppen:
                members = gruppe.user_set.all()
                self.stdout.write(f"\nGruppe: {gruppe.name}")
                self.stdout.write(f"  Mitglieder ({members.count()}): {[u.username for u in members]}")
        else:
            self.stdout.write("Keine Gruppen definiert.")

        # 4. Zusammenfassung
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("### ZUSAMMENFASSUNG ###\n")
        self.stdout.write(f"Total User: {users.count()}")
        self.stdout.write(f"User mit Mitarbeiter-Objekt: {sum(1 for u in users if hasattr(u, 'mitarbeiter'))}")
        self.stdout.write(f"Schichtplaner (Rolle): {Mitarbeiter.objects.filter(rolle__iexact='schichtplaner').count()}")
        self.stdout.write(f"Kongos (Abteilung): {Mitarbeiter.objects.filter(abteilung__iexact='kongos').count()}")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS('Debug-Ausgabe abgeschlossen!'))
