"""Management Command: erstelle_test_team

Erstellt ein Test-Team 'Zeiterfassung-Team' fuer die Team-Queue.
Fuegt alle Staff-User als Mitglieder hinzu.

Aufruf:
    python manage.py erstelle_test_team
    python manage.py erstelle_test_team --alle-user
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from formulare.models import TeamQueue


class Command(BaseCommand):
    help = "Erstellt Test-Team fuer Team-Queue-System"

    def add_arguments(self, parser):
        parser.add_argument(
            "--alle-user",
            action="store_true",
            help="Fuegt alle User hinzu (nicht nur Staff)",
        )

    def handle(self, *args, **options):
        alle_user = options["alle_user"]

        # Pruefen ob Team schon existiert
        team, created = TeamQueue.objects.get_or_create(
            kuerzel="zeit",
            defaults={
                "name": "Zeiterfassung-Team",
                "beschreibung": (
                    "Bearbeitet genehmigte Antraege fuer Zeiterfassung, "
                    "Z-AG und Z-AG-Stornierungen."
                ),
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Team '{team.name}' erstellt.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"Team '{team.name}' existiert bereits.")
            )

        # Mitglieder hinzufuegen
        if alle_user:
            user_qs = User.objects.filter(is_active=True)
            self.stdout.write(f"Fuege alle aktiven User hinzu...")
        else:
            user_qs = User.objects.filter(is_staff=True, is_active=True)
            self.stdout.write(f"Fuege Staff-User hinzu...")

        anzahl_vorher = team.mitglieder.count()
        team.mitglieder.set(user_qs)
        anzahl_nachher = team.mitglieder.count()

        self.stdout.write(
            self.style.SUCCESS(
                f"Mitglieder: {anzahl_nachher} "
                f"(vorher: {anzahl_vorher}, neu: {anzahl_nachher - anzahl_vorher})"
            )
        )

        # Mitglieder auflisten
        self.stdout.write("\n=== Team-Mitglieder ===")
        for user in team.mitglieder.all():
            self.stdout.write(
                f"  - {user.username} "
                f"({user.get_full_name() or 'Kein Name'})"
            )

        self.stdout.write(
            f"\n{self.style.SUCCESS('Fertig!')}"
            f"\nTeam-Queue: http://127.0.0.1:8000/formulare/team-queue/"
        )
