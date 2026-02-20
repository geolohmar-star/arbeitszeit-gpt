"""Management Command: Erstellt Personal-Abteilung mit Team Zeit/Abrechnung.

Struktur:
- OrgEinheit: Human Resources (HR) unter BV
- Teamleiter: hr_tl1
- Stellvertreter: hr_stv1 (delegiert_an von hr_tl1)
- 10 Mitarbeiter: ma_hr1 bis ma_hr10
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from hr.models import HRMitarbeiter, OrgEinheit, Stelle
from arbeitszeit.models import Mitarbeiter


class Command(BaseCommand):
    help = "Erstellt Personal-Abteilung mit Team Zeit/Abrechnung"

    def handle(self, *args, **options):
        with transaction.atomic():
            self.stdout.write("Erstelle Personal-Abteilung...")

            # OrgEinheit HR unter BV
            bv = OrgEinheit.objects.get(kuerzel="BV")
            hr_einheit, created = OrgEinheit.objects.get_or_create(
                kuerzel="HR",
                defaults={
                    "bezeichnung": "Human Resources",
                    "uebergeordnet": bv,
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  OrgEinheit {hr_einheit.kuerzel} erstellt")
                )
            else:
                self.stdout.write(f"  OrgEinheit {hr_einheit.kuerzel} existiert bereits")

            # Teamleiter Stelle
            tl_stelle, created = Stelle.objects.get_or_create(
                kuerzel="hr_tl1",
                defaults={
                    "bezeichnung": "Teamleiter Zeit/Abrechnung",
                    "org_einheit": hr_einheit,
                    "uebergeordnete_stelle": Stelle.objects.get(kuerzel="bl_bv3"),
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  Stelle {tl_stelle.kuerzel} erstellt")
                )

            # Stellvertreter Stelle
            stv_stelle, created = Stelle.objects.get_or_create(
                kuerzel="hr_stv1",
                defaults={
                    "bezeichnung": "Stellv. Teamleiter Zeit/Abrechnung",
                    "org_einheit": hr_einheit,
                    "uebergeordnete_stelle": tl_stelle,
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  Stelle {stv_stelle.kuerzel} erstellt")
                )

            # Delegation: Teamleiter delegiert an Stellvertreter
            if not tl_stelle.delegiert_an:
                tl_stelle.delegiert_an = stv_stelle
                tl_stelle.save()
                self.stdout.write("  Delegation TL -> STV eingerichtet")

            # 10 Mitarbeiter-Stellen
            mitarbeiter_stellen = []
            for i in range(1, 11):
                kuerzel = f"ma_hr{i}"
                stelle, created = Stelle.objects.get_or_create(
                    kuerzel=kuerzel,
                    defaults={
                        "bezeichnung": f"Mitarbeiter HR Zeit/Abrechnung {i}",
                        "org_einheit": hr_einheit,
                        "uebergeordnete_stelle": tl_stelle,
                    },
                )
                mitarbeiter_stellen.append(stelle)
                if created:
                    self.stdout.write(f"  Stelle {stelle.kuerzel} erstellt")

            self.stdout.write("\nErstelle User, HRMitarbeiter und Mitarbeiter...")

            # Teamleiter
            self._erstelle_person(
                "hr_tl1",
                "Max",
                "Mustermann",
                "Teamleiter",
                tl_stelle,
                "HR-TL-001",
            )

            # Stellvertreter
            self._erstelle_person(
                "hr_stv1",
                "Anna",
                "Schmidt",
                "Stellvertreterin",
                stv_stelle,
                "HR-STV-001",
            )

            # 10 Mitarbeiter
            vornamen = [
                "Lisa",
                "Tom",
                "Julia",
                "Markus",
                "Sarah",
                "Tim",
                "Laura",
                "Felix",
                "Nina",
                "Leon",
            ]
            nachnamen = [
                "Mueller",
                "Weber",
                "Wagner",
                "Becker",
                "Schulz",
                "Hoffmann",
                "Koch",
                "Bauer",
                "Richter",
                "Klein",
            ]

            for i, stelle in enumerate(mitarbeiter_stellen, start=1):
                self._erstelle_person(
                    stelle.kuerzel,
                    vornamen[i - 1],
                    nachnamen[i - 1],
                    f"Sachbearbeiter/in {i}",
                    stelle,
                    f"HR-MA-{i:03d}",
                )

            self.stdout.write(
                self.style.SUCCESS(
                    "\nHR-Abteilung erfolgreich erstellt!"
                    "\n- Teamleiter: hr_tl1 (hr_tl1@firma.de)"
                    "\n- Stellvertreter: hr_stv1 (hr_stv1@firma.de)"
                    "\n- 10 Mitarbeiter: ma_hr1 bis ma_hr10"
                    "\n\nAlle User haben Passwort: testpass123"
                )
            )

    def _erstelle_person(
        self, username, vorname, nachname, funktion, stelle, personalnummer
    ):
        """Erstellt User, HRMitarbeiter und Mitarbeiter fuer eine Person."""
        # User
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": vorname,
                "last_name": nachname,
                "email": f"{username}@firma.de",
            },
        )
        if created:
            user.set_password("testpass123")
            user.save()
            self.stdout.write(f"    User {username} erstellt")

        # HRMitarbeiter
        hr_ma, created = HRMitarbeiter.objects.get_or_create(
            personalnummer=personalnummer,
            defaults={
                "user": user,
                "vorname": vorname,
                "nachname": nachname,
                "stelle": stelle,
            },
        )
        if created:
            self.stdout.write(f"    HRMitarbeiter fuer {username} erstellt")
        else:
            # Update falls schon vorhanden
            hr_ma.user = user
            hr_ma.stelle = stelle
            hr_ma.save()
            self.stdout.write(f"    HRMitarbeiter {username} aktualisiert")

        # arbeitszeit.Mitarbeiter
        ma, created = Mitarbeiter.objects.get_or_create(
            user=user,
            defaults={
                "vorname": vorname,
                "nachname": nachname,
                "personalnummer": personalnummer,
                "abteilung": f"Personal - {funktion}",
            },
        )
        if created:
            self.stdout.write(f"    Mitarbeiter {personalnummer} erstellt")
