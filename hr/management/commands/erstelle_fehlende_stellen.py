"""Management Command zum Erstellen fehlender Stellen fuer Mitarbeiter."""

from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import HRMitarbeiter, OrgEinheit, Stelle


class Command(BaseCommand):
    help = "Erstellt automatisch Stellen fuer Mitarbeiter ohne Stelle"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Erstellt die Stellen wirklich (sonst nur Vorschau)",
        )

    def handle(self, *args, **options):
        execute = options["execute"]

        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    "\nVORSCHAU-MODUS (nutze --execute um wirklich zu erstellen)\n"
                )
            )

        # Hole alle Mitarbeiter ohne Stelle
        mitarbeiter_ohne_stelle = HRMitarbeiter.objects.filter(
            stelle__isnull=True
        )

        if not mitarbeiter_ohne_stelle.exists():
            self.stdout.write(
                self.style.SUCCESS(
                    "\nAlle Mitarbeiter haben bereits eine Stelle!\n"
                )
            )
            return

        self.stdout.write(
            f"\nGefunden: {mitarbeiter_ohne_stelle.count()} "
            f"Mitarbeiter ohne Stelle\n"
        )

        # Standard-OrgEinheit fuer Mitarbeiter ohne Zuordnung
        default_org, _ = OrgEinheit.objects.get_or_create(
            kuerzel="HR",
            defaults={
                "bezeichnung": "Human Resources",
                "ist_reserviert": True,
            },
        )

        neue_stellen = []

        for mitarbeiter in mitarbeiter_ohne_stelle:
            # Bestimme OrgEinheit
            org_einheit = default_org
            if mitarbeiter.bereich:
                # Suche OrgEinheit mit passendem Kuerzel
                org_match = OrgEinheit.objects.filter(
                    kuerzel__iexact=mitarbeiter.bereich.kuerzel
                ).first()
                if org_match:
                    org_einheit = org_match

            # Erstelle Kuerzel aus Personalnummer
            # Entferne Bindestriche und wandle in Kleinbuchstaben um
            pn_clean = mitarbeiter.personalnummer.replace("-", "_").lower()

            # Wenn Kuerzel zu lang, kuerze es
            if len(pn_clean) > 20:
                pn_clean = pn_clean[:20]

            # Pruefe ob Kuerzel bereits existiert
            counter = 1
            kuerzel = pn_clean
            while Stelle.objects.filter(kuerzel=kuerzel).exists():
                kuerzel = f"{pn_clean}_{counter}"
                counter += 1

            # Erstelle Bezeichnung
            rolle_text = mitarbeiter.get_rolle_display()
            bezeichnung = f"{rolle_text} – {mitarbeiter.vollname}"

            neue_stellen.append({
                "mitarbeiter": mitarbeiter,
                "kuerzel": kuerzel,
                "bezeichnung": bezeichnung,
                "org_einheit": org_einheit,
            })

            self.stdout.write(
                f"  {mitarbeiter.vollname:30} -> {kuerzel:20} "
                f"({org_einheit.kuerzel})"
            )

        self.stdout.write(
            f"\n{len(neue_stellen)} neue Stelle(n) vorbereitet.\n"
        )

        if execute:
            self.stdout.write("Erstelle Stellen...\n")

            with transaction.atomic():
                for stelle_data in neue_stellen:
                    # Erstelle Stelle
                    stelle = Stelle.objects.create(
                        kuerzel=stelle_data["kuerzel"],
                        bezeichnung=stelle_data["bezeichnung"],
                        org_einheit=stelle_data["org_einheit"],
                    )

                    # Verknuepfe mit Mitarbeiter
                    mitarbeiter = stelle_data["mitarbeiter"]
                    mitarbeiter.stelle = stelle
                    mitarbeiter.save(update_fields=["stelle"])

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  OK: {stelle.kuerzel} erstellt und "
                            f"{mitarbeiter.vollname} zugeordnet"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nERFOLG: {len(neue_stellen)} Stelle(n) erstellt "
                    f"und zugeordnet!\n"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nNutze --execute um die Stellen zu erstellen.\n"
                )
            )
