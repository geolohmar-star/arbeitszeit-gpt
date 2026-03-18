"""
Management-Command: matrix_passwort_setzen

Setzt das Matrix-Passwort fuer alle aktiven HRMitarbeiter-Accounts
auf ein einheitliches Standardpasswort (z.B. hrmitarbeiter2026).

Aufruf:
    python manage.py matrix_passwort_setzen
    python manage.py matrix_passwort_setzen --passwort meinpasswort123
    python manage.py matrix_passwort_setzen --username ma_fm1
    python manage.py matrix_passwort_setzen --trocken
"""
import logging

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

STANDARD_PASSWORT = "hrmitarbeiter2026"


class Command(BaseCommand):
    help = "Setzt das Matrix-Passwort aller HRMitarbeiter auf ein Standardpasswort."

    def add_arguments(self, parser):
        parser.add_argument(
            "--passwort",
            type=str,
            default=STANDARD_PASSWORT,
            help=f"Passwort das gesetzt werden soll (Standard: {STANDARD_PASSWORT})",
        )
        parser.add_argument(
            "--username",
            type=str,
            help="Nur fuer diesen einen Django-Username ausfuehren.",
        )
        parser.add_argument(
            "--trocken",
            action="store_true",
            help="Nur anzeigen welche User betroffen waeren – kein API-Aufruf.",
        )

    def handle(self, *args, **options):
        from matrix_integration.synapse_service import setze_matrix_passwort

        passwort = options["passwort"]
        nur_username = options.get("username")
        trocken = options["trocken"]

        if trocken:
            self.stdout.write("TROCKENLAUF – kein echter API-Aufruf.\n")

        # Nur User mit verknuepftem HRMitarbeiter beruecksichtigen
        qs = User.objects.filter(
            is_active=True,
            hr_mitarbeiter__isnull=False,
        ).select_related("hr_mitarbeiter")

        if nur_username:
            qs = qs.filter(username=nur_username)

        gesamt = qs.count()
        self.stdout.write(f"Verarbeite {gesamt} User...\n")

        ok_count = 0
        fehler_count = 0

        for user in qs:
            anzeigename = user.get_full_name() or user.username
            self.stdout.write(f"  {user.username} ({anzeigename})")

            if trocken:
                self.stdout.write(" -> wuerde gesetzt werden\n")
                continue

            ok = setze_matrix_passwort(user.username, passwort)
            if ok:
                ok_count += 1
                self.stdout.write(self.style.SUCCESS(" -> OK\n"))
            else:
                fehler_count += 1
                self.stdout.write(self.style.ERROR(" -> FEHLER\n"))

        if not trocken:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nFertig: {ok_count} OK, {fehler_count} Fehler.\n"
                )
            )
            self.stdout.write(
                f"Passwort: {passwort}\n"
                f"Alle betroffenen User koennen sich nun mit diesem Passwort\n"
                f"in Element anmelden.\n"
            )
