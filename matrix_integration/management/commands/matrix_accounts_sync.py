"""
Management-Command: matrix_accounts_sync

Legt fuer alle aktiven Django-User einen Matrix-Account auf Synapse an
und laedt sie in die Raeume ihrer Org-Einheit ein.

Aufruf:
    python manage.py matrix_accounts_sync
    python manage.py matrix_accounts_sync --trocken
    python manage.py matrix_accounts_sync --username ma_fm1   # nur einen User
"""
import logging

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronisiert alle Django-User als Matrix-Accounts auf Synapse."

    def add_arguments(self, parser):
        parser.add_argument("--trocken", action="store_true", help="Kein echter API-Aufruf.")
        parser.add_argument("--username", type=str, help="Nur diesen einen User synchronisieren.")

    def handle(self, *args, **options):
        from matrix_integration.synapse_service import (
            einladen_in_org_einheit_raeume,
            erstelle_matrix_account,
        )

        trocken = options["trocken"]
        nur_username = options.get("username")

        if trocken:
            self.stdout.write("TROCKENLAUF – keine echten API-Aufrufe.\n")

        qs = User.objects.filter(is_active=True)
        if nur_username:
            qs = qs.filter(username=nur_username)

        gesamt = qs.count()
        self.stdout.write(f"Verarbeite {gesamt} User...\n")

        for user in qs:
            anzeigename = user.get_full_name() or user.username
            self.stdout.write(f"  {user.username} ({anzeigename})")

            if not trocken:
                ok = erstelle_matrix_account(user.username, anzeigename)
                status = "OK" if ok else "FEHLER"
                self.stdout.write(f" -> Account: {status}")

                # Einladung in Org-Einheit-Raeume
                try:
                    ma = user.hr_mitarbeiter
                    if ma.stelle_id:
                        einladen_in_org_einheit_raeume(ma)
                        self.stdout.write(" -> eingeladen")
                except Exception:
                    pass

            self.stdout.write("\n")

        self.stdout.write(self.style.SUCCESS("Fertig.\n"))
