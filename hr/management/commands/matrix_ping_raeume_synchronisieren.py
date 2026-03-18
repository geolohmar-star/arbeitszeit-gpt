"""
Management-Command: matrix_ping_raeume_synchronisieren

Laedt alle HR-Mitarbeiter die eine passende Kennzeichnung tragen in die
entsprechenden Matrix-Ping-Raeume ein.

Ausfuehren:
    python manage.py matrix_ping_raeume_synchronisieren
    python manage.py matrix_ping_raeume_synchronisieren --trocken    # nur anzeigen

Raumzuordnung:
    EH-Ping-Raum:       ist_ersthelfer | Stelle ist_betriebsarzt | Stelle al_as
    Security-Ping-Raum: Security-Stelle | ist_branderkunder | ist_brandbekaempfer | ist_raeumungshelfer
"""
import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from hr.models import HRMitarbeiter
from hr.signals import _ping_raeume_fuer_mitarbeiter
from config.kommunikation_utils import matrix_nutzer_in_raum_einladen

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronisiert Matrix-Ping-Raum-Einladungen fuer alle berechtigten Mitarbeiter"

    def add_arguments(self, parser):
        parser.add_argument(
            "--trocken",
            action="store_true",
            dest="trocken",
            help="Nur anzeigen was getan wuerde – keine Einladungen senden",
        )

    def handle(self, *args, **options):
        trocken = options["trocken"]
        server_name = getattr(settings, "MATRIX_SERVER_NAME", "")

        if not server_name:
            self.stderr.write("MATRIX_SERVER_NAME nicht konfiguriert – Abbruch.")
            return

        if trocken:
            self.stdout.write("Trockenlauf – keine Einladungen werden gesendet.\n")

        mitarbeiter = (
            HRMitarbeiter.objects
            .select_related("stelle", "user")
            .all()
        )

        gesamt    = 0
        eingeladen = 0
        uebersprungen = 0

        for ma in mitarbeiter:
            stelle = getattr(ma, "stelle", None)
            if not stelle:
                continue  # kein Stellen-Kuerzel – kein Matrix-Login
            kuerzel = stelle.kuerzel

            raeume = _ping_raeume_fuer_mitarbeiter(ma)
            if not raeume:
                continue

            matrix_id = f"@{kuerzel}:{server_name}"
            gesamt += 1

            for room_id, beschreibung in raeume:
                if trocken:
                    self.stdout.write(
                        f"  [TROCKEN] {matrix_id} -> {beschreibung} ({room_id})"
                    )
                    eingeladen += 1
                else:
                    ok = matrix_nutzer_in_raum_einladen(room_id, matrix_id)
                    if ok:
                        self.stdout.write(
                            f"  [OK] {matrix_id} -> {beschreibung}"
                        )
                        eingeladen += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  [FEHLER] {matrix_id} -> {beschreibung}"
                            )
                        )
                        uebersprungen += 1
                    # Synapse Rate-Limit respektieren (standard rc_invites: 3/s burst 10)
                    time.sleep(2)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFertig: {gesamt} Mitarbeiter geprueft, "
                f"{eingeladen} Einladungen {'geplant' if trocken else 'gesendet'}, "
                f"{uebersprungen} Fehler."
            )
        )
