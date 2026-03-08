"""
Management Command: generiere_einladungscodes

Erstellt 100 eindeutige 5-stellige Einladungscodes fuer den Bewerbungsprozess.
Idempotent – bestehende Codes werden nicht geloescht.

Aufruf:
    python manage.py generiere_einladungscodes
    python manage.py generiere_einladungscodes --anzahl 200
"""
from django.core.management.base import BaseCommand

from bewerbung.models import EinladungsCode


class Command(BaseCommand):
    help = "Generiert Einladungscodes fuer den Bewerbungsprozess (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--anzahl",
            type=int,
            default=100,
            help="Anzahl der zu generierenden Codes (Standard: 100)",
        )

    def handle(self, *args, **options):
        anzahl = options["anzahl"]
        vorher = EinladungsCode.objects.count()
        erstellt = EinladungsCode.generiere_batch(anzahl)
        nachher = EinladungsCode.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Fertig: {erstellt} neue Codes erstellt. "
                f"Gesamt: {nachher} Codes (vorher: {vorher})."
            )
        )
