"""Management Command: erstelle_test_workflow

Erstellt komplette Test-Daten fuer den Genehmigungs-Workflow:
- Test-Mitarbeiter mit Stelle
- Vorgesetzter mit uebergeordneter Stelle
- Optional: Delegation an Stellvertreter
- Z-AG Test-Antrag

Aufruf:
    python manage.py erstelle_test_workflow
    python manage.py erstelle_test_workflow --mit-delegation
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from arbeitszeit.models import Mitarbeiter
from formulare.models import ZAGAntrag
from hr.models import HRMitarbeiter, OrgEinheit, Stelle


class Command(BaseCommand):
    help = "Erstellt Test-Daten fuer Genehmigungs-Workflow"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mit-delegation",
            action="store_true",
            help="Erstellt zusaetzlich Delegation an Stellvertreter",
        )

    def handle(self, *args, **options):
        mit_delegation = options["mit_delegation"]

        self.stdout.write("\n=== Test-Workflow Setup ===\n")

        # 1. OrgEinheit pruefen/erstellen
        org, _ = OrgEinheit.objects.get_or_create(
            kuerzel="TEST",
            defaults={"bezeichnung": "Test-Bereich"},
        )
        self.stdout.write(f"OrgEinheit: {org}")

        # 2. Vorgesetzten-Stelle erstellen
        vorgesetzter_stelle, created = Stelle.objects.get_or_create(
            kuerzel="test_vg",
            defaults={
                "bezeichnung": "Test Vorgesetzter",
                "org_einheit": org,
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Vorgesetzten-Stelle erstellt: {vorgesetzter_stelle}")
            )
        else:
            self.stdout.write(f"Vorgesetzten-Stelle: {vorgesetzter_stelle} (existiert)")

        # 3. Mitarbeiter-Stelle (untergeordnet) erstellen
        mitarbeiter_stelle, created = Stelle.objects.get_or_create(
            kuerzel="test_ma",
            defaults={
                "bezeichnung": "Test Mitarbeiter",
                "org_einheit": org,
                "uebergeordnete_stelle": vorgesetzter_stelle,
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Mitarbeiter-Stelle erstellt: {mitarbeiter_stelle}")
            )
        else:
            self.stdout.write(f"Mitarbeiter-Stelle: {mitarbeiter_stelle} (existiert)")

        # 4. Vorgesetzten-User + HRMitarbeiter erstellen
        vg_user, created = User.objects.get_or_create(
            username="test_vorgesetzter",
            defaults={
                "first_name": "Max",
                "last_name": "Vorgesetzter",
                "email": "max.vg@test.de",
                "is_staff": True,
            },
        )
        if created:
            vg_user.set_password("test123")
            vg_user.save()
            self.stdout.write(self.style.SUCCESS(f"User erstellt: {vg_user.username}"))
        else:
            self.stdout.write(f"User: {vg_user.username} (existiert)")

        vg_hr, _ = HRMitarbeiter.objects.get_or_create(
            personalnummer="VG001",
            defaults={
                "user": vg_user,
                "vorname": "Max",
                "nachname": "Vorgesetzter",
                "stelle": vorgesetzter_stelle,
                "rolle": "abteilungsleiter",
            },
        )
        self.stdout.write(f"HRMitarbeiter Vorgesetzter: {vg_hr}")

        # 5. Mitarbeiter-User + arbeitszeit.Mitarbeiter erstellen
        ma_user, created = User.objects.get_or_create(
            username="test_mitarbeiter",
            defaults={
                "first_name": "Anna",
                "last_name": "Mitarbeiter",
                "email": "anna.ma@test.de",
            },
        )
        if created:
            ma_user.set_password("test123")
            ma_user.save()
            self.stdout.write(self.style.SUCCESS(f"User erstellt: {ma_user.username}"))
        else:
            self.stdout.write(f"User: {ma_user.username} (existiert)")

        ma_hr, _ = HRMitarbeiter.objects.get_or_create(
            personalnummer="MA001",
            defaults={
                "user": ma_user,
                "vorname": "Anna",
                "nachname": "Mitarbeiter",
                "stelle": mitarbeiter_stelle,
                "rolle": "mitarbeiter",
            },
        )

        # arbeitszeit.Mitarbeiter erstellen
        ma_az, _ = Mitarbeiter.objects.get_or_create(
            user=ma_user,
            defaults={
                "personalnummer": "MA001",
                "vorname": "Anna",
                "nachname": "Mitarbeiter",
            },
        )
        self.stdout.write(f"Mitarbeiter (arbeitszeit): {ma_az}")

        # 6. Optional: Stellvertreter mit Delegation
        if mit_delegation:
            sv_stelle, created = Stelle.objects.get_or_create(
                kuerzel="test_sv",
                defaults={
                    "bezeichnung": "Test Stellvertreter",
                    "org_einheit": org,
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Stellvertreter-Stelle erstellt: {sv_stelle}")
                )

            # Delegation setzen
            vorgesetzter_stelle.delegiert_an = sv_stelle
            vorgesetzter_stelle.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Delegation: {vorgesetzter_stelle.kuerzel} -> {sv_stelle.kuerzel}"
                )
            )

            # Stellvertreter-User erstellen
            sv_user, created = User.objects.get_or_create(
                username="test_stellvertreter",
                defaults={
                    "first_name": "Lisa",
                    "last_name": "Stellvertreter",
                    "email": "lisa.sv@test.de",
                    "is_staff": True,
                },
            )
            if created:
                sv_user.set_password("test123")
                sv_user.save()
                self.stdout.write(
                    self.style.SUCCESS(f"User erstellt: {sv_user.username}")
                )

            sv_hr, _ = HRMitarbeiter.objects.get_or_create(
                personalnummer="SV001",
                defaults={
                    "user": sv_user,
                    "vorname": "Lisa",
                    "nachname": "Stellvertreter",
                    "stelle": sv_stelle,
                    "rolle": "assistent",
                },
            )
            self.stdout.write(f"Stellvertreter: {sv_hr}")

        # 7. Test Z-AG Antrag erstellen
        heute = date.today()
        morgen = heute + timedelta(days=1)

        antrag, created = ZAGAntrag.objects.get_or_create(
            antragsteller=ma_az,
            status="beantragt",
            defaults={
                "zag_daten": [
                    {
                        "von_datum": heute.isoformat(),
                        "bis_datum": morgen.isoformat(),
                    }
                ],
                "vertretung_name": "Keine",
                "vertretung_telefon": "",
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Z-AG Antrag erstellt: ID {antrag.pk}")
            )
        else:
            self.stdout.write(f"Z-AG Antrag: ID {antrag.pk} (existiert)")

        # Zusammenfassung
        self.stdout.write("\n=== Test-Workflow bereit! ===\n")
        self.stdout.write(f"Mitarbeiter: test_mitarbeiter / test123")
        self.stdout.write(f"Vorgesetzter: test_vorgesetzter / test123")
        if mit_delegation:
            self.stdout.write(f"Stellvertreter: test_stellvertreter / test123")
        self.stdout.write(f"\nZ-AG Antrag ID: {antrag.pk}")
        self.stdout.write(f"Status: {antrag.status}")
        self.stdout.write(f"\n{self.style.SUCCESS('Workflow-Test starten:')}")
        self.stdout.write(
            f"1. Login als Vorgesetzter: http://127.0.0.1:8000/login/"
        )
        self.stdout.write(
            f"2. Genehmigung: http://127.0.0.1:8000/formulare/genehmigung/"
        )
        self.stdout.write(
            f"3. Team-Queue: http://127.0.0.1:8000/formulare/team-queue/"
        )
