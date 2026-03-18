"""
Management-Command: matrix_scheduler

Endlosschleife fuer den Docker-Scheduler-Container.

Aufgaben:
  - Jede Minute:       Sitzungs-Erinnerungen pruefen (Matrix-Nachrichten)
  - Taeglich 02:00:    Matrix-Accounts anlegen + Passwort setzen

Aufruf (docker-compose):
    command: python manage.py matrix_scheduler
"""
import logging
import subprocess
import sys
import time
from datetime import date, datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scheduler-Loop: Sitzungs-Erinnerungen (minuetlich) + Matrix-Sync (02:00 Uhr)."

    def handle(self, *args, **options):
        self.stdout.write("PRIMA Scheduler gestartet.\n")
        self.stdout.flush()

        letzter_sync_tag = None
        iteration = 0  # zaehlt 10s-Zyklen

        while True:
            # --- Alle 10 Sekunden: EH-Rueckmeldungen pollen ---
            try:
                call_command("eh_rueckmeldung_poller", verbosity=0)
            except Exception as exc:
                logger.warning("eh_rueckmeldung_poller fehlgeschlagen: %s", exc)

            # --- Alle 10 Sekunden: Branderkunder-DM-Rueckmeldungen pollen ---
            try:
                call_command("brand_rueckmeldung_poller", verbosity=0)
            except Exception as exc:
                logger.warning("brand_rueckmeldung_poller fehlgeschlagen: %s", exc)

            # --- Alle 10 Sekunden: Branderkunder-Timeout pruefen (Eskalation nach 90s) ---
            try:
                call_command("brand_eskalation_pruefen", verbosity=0)
            except Exception as exc:
                logger.warning("brand_eskalation_pruefen fehlgeschlagen: %s", exc)

            # --- Jede Minute (jede 6. Iteration): Sitzungs-Erinnerungen ---
            if iteration % 6 == 0:
                try:
                    call_command("matrix_sitzung_erinnerungen", verbosity=0)
                except Exception as exc:
                    logger.warning("matrix_sitzung_erinnerungen fehlgeschlagen: %s", exc)

            # --- Taeglich um 02:00 Uhr: Matrix-Accounts synchronisieren ---
            jetzt = datetime.now()
            heute = date.today()
            if jetzt.hour == 2 and letzter_sync_tag != heute:
                self.stdout.write(
                    f"[{jetzt.strftime('%Y-%m-%d %H:%M')}] Naechtlicher Matrix-Sync...\n"
                )
                self.stdout.flush()
                try:
                    call_command("matrix_accounts_sync", verbosity=1)
                except Exception as exc:
                    logger.warning("matrix_accounts_sync fehlgeschlagen: %s", exc)
                try:
                    call_command("ersthelfer_schein_warnung", verbosity=0)
                except Exception as exc:
                    logger.warning("ersthelfer_schein_warnung fehlgeschlagen: %s", exc)
                letzter_sync_tag = heute
                self.stdout.write("Naechtlicher Matrix-Sync abgeschlossen.\n")
                self.stdout.flush()

            iteration += 1
            time.sleep(10)
