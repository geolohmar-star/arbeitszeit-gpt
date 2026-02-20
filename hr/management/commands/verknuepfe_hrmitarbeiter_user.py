"""Management Command: verknuepfe_hrmitarbeiter_user

Verknuepft HRMitarbeiter automatisch mit passenden Django-Usern.

Matching-Strategien (in dieser Reihenfolge):
1. Username enthaelt Personalnummer (z.B. "gerhard.vogt.AP-1000")
2. Username = vorname.nachname (case-insensitive)
3. Username = ErsterBuchstabeVorname + Nachname (z.B. "GKlein")
4. Username = vorname + nachname (ohne Punkt, case-insensitive)

Aufruf:
    python manage.py verknuepfe_hrmitarbeiter_user
    python manage.py verknuepfe_hrmitarbeiter_user --dry-run
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from hr.models import HRMitarbeiter


class Command(BaseCommand):
    help = "Verknuepft HRMitarbeiter automatisch mit Django-Usern"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt nur was gemacht wuerde, ohne zu speichern.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Alle User in ein Dict laden fuer schnelleren Lookup
        alle_user = {u.username.lower(): u for u in User.objects.all()}

        # Alle HRMitarbeiter ohne User-Verknuepfung
        ohne_user = HRMitarbeiter.objects.filter(user__isnull=True)
        gesamt = ohne_user.count()

        if gesamt == 0:
            self.stdout.write("Alle HRMitarbeiter haben bereits einen User.")
            return

        self.stdout.write(f"\n{gesamt} HRMitarbeiter ohne User-Verknuepfung.\n")

        verknuepft = 0
        nicht_gefunden = []

        for hrm in ohne_user:
            user = self._finde_user(hrm, alle_user)

            if user:
                if not dry_run:
                    hrm.user = user
                    hrm.save(update_fields=["user"])
                self.stdout.write(
                    f"  [OK] {hrm.personalnummer} ({hrm.vorname} {hrm.nachname}) "
                    f"-> User: {user.username}"
                )
                verknuepft += 1
            else:
                nicht_gefunden.append(hrm)

        # Zusammenfassung
        self.stdout.write(
            f"\n{'[DRY-RUN] ' if dry_run else ''}Ergebnis: "
            f"{verknuepft} verknuepft, {len(nicht_gefunden)} nicht gefunden."
        )

        if nicht_gefunden:
            self.stdout.write(
                "\nFolgende HRMitarbeiter konnten nicht zugeordnet werden:"
            )
            for hrm in nicht_gefunden[:10]:  # Nur erste 10 anzeigen
                self.stdout.write(
                    f"  {hrm.personalnummer}: {hrm.vorname} {hrm.nachname}"
                )
            if len(nicht_gefunden) > 10:
                self.stdout.write(f"  ... und {len(nicht_gefunden) - 10} weitere")

    def _finde_user(self, hrm, alle_user_dict):
        """Versucht einen passenden User fuer den HRMitarbeiter zu finden."""
        vorname = hrm.vorname.strip()
        nachname = hrm.nachname.strip()
        pnr = hrm.personalnummer.strip()

        # Strategie 1: Username enthaelt Personalnummer
        for username, user in alle_user_dict.items():
            if pnr.lower() in username:
                return user

        # Strategie 2: vorname.nachname
        kandidat = f"{vorname}.{nachname}".lower()
        if kandidat in alle_user_dict:
            return alle_user_dict[kandidat]

        # Strategie 3: ErsterBuchstabeVorname + Nachname
        if vorname and nachname:
            kandidat = f"{vorname[0]}{nachname}".lower()
            if kandidat in alle_user_dict:
                return alle_user_dict[kandidat]

        # Strategie 4: vornamenachname (ohne Punkt)
        kandidat = f"{vorname}{nachname}".lower()
        if kandidat in alle_user_dict:
            return alle_user_dict[kandidat]

        # Nichts gefunden
        return None
