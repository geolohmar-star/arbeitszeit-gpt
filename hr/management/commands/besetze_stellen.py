"""Management Command zum automatischen Besetzen von Stellen mit HRMitarbeitern."""

from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import HRMitarbeiter, Stelle


class Command(BaseCommand):
    help = "Besetzt Stellen automatisch mit passenden HRMitarbeitern"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Fuehrt die Zuordnung wirklich durch (sonst nur Vorschau)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ueberschreibt bestehende Zuordnungen",
        )

    def handle(self, *args, **options):
        execute = options["execute"]
        force = options["force"]

        # Rolle zu Stellen-Prefix Mapping
        rolle_prefix_map = {
            "gf": ["gf"],
            "bereichsleiter": ["bl_"],
            "abteilungsleiter": ["al_"],
            "teamleiter": ["tl_"],
            "assistent": ["ass_"],
            "mitarbeiter": ["ma_"],
        }

        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    "\nVORSCHAU-MODUS (nutze --execute um wirklich zuzuordnen)\n"
                )
            )

        # Hole alle HRMitarbeiter
        if force:
            mitarbeiter_qs = HRMitarbeiter.objects.all()
        else:
            mitarbeiter_qs = HRMitarbeiter.objects.filter(stelle__isnull=True)

        # Hole alle Stellen
        if force:
            stellen_qs = Stelle.objects.all()
        else:
            stellen_qs = Stelle.objects.filter(hrmitarbeiter__isnull=True)

        self.stdout.write(f"\nGefunden:")
        self.stdout.write(f"  - {mitarbeiter_qs.count()} Mitarbeiter ohne Stelle")
        self.stdout.write(f"  - {stellen_qs.count()} freie Stellen\n")

        zuordnungen = []

        # Versuche intelligente Zuordnung
        for mitarbeiter in mitarbeiter_qs:
            # Hole passende Prefixe fuer die Rolle
            prefixes = rolle_prefix_map.get(mitarbeiter.rolle, [])

            # Suche passende Stelle
            passende_stelle = None

            for prefix in prefixes:
                # Zuerst: Suche in gleicher OrgEinheit wenn moeglich
                if mitarbeiter.stelle and mitarbeiter.stelle.org_einheit:
                    passende_stelle = (
                        stellen_qs.filter(
                            kuerzel__istartswith=prefix,
                            org_einheit=mitarbeiter.stelle.org_einheit,
                        )
                        .exclude(hrmitarbeiter__isnull=False)
                        .first()
                    )

                # Wenn nicht gefunden, suche generell
                if not passende_stelle:
                    passende_stelle = (
                        stellen_qs.filter(kuerzel__istartswith=prefix)
                        .exclude(hrmitarbeiter__isnull=False)
                        .first()
                    )

                if passende_stelle:
                    break

            # Wenn keine passende Stelle gefunden, nimm die naechste freie
            if not passende_stelle:
                passende_stelle = (
                    stellen_qs.exclude(hrmitarbeiter__isnull=False).first()
                )

            if passende_stelle:
                zuordnungen.append((mitarbeiter, passende_stelle))
                self.stdout.write(
                    f"  {mitarbeiter.vollname} ({mitarbeiter.rolle}) "
                    f"-> {passende_stelle.kuerzel} ({passende_stelle.bezeichnung})"
                )

        if not zuordnungen:
            self.stdout.write(
                self.style.WARNING("\nKeine Zuordnungen moeglich!\n")
            )
            return

        self.stdout.write(
            f"\n{len(zuordnungen)} Zuordnung(en) vorbereitet.\n"
        )

        if execute:
            self.stdout.write("Fuehre Zuordnungen durch...\n")

            with transaction.atomic():
                for mitarbeiter, stelle in zuordnungen:
                    # Loesche alte Zuordnung falls force
                    if force and hasattr(stelle, "hrmitarbeiter"):
                        alter_mitarbeiter = stelle.hrmitarbeiter
                        alter_mitarbeiter.stelle = None
                        alter_mitarbeiter.save(update_fields=["stelle"])

                    # Setze neue Zuordnung
                    mitarbeiter.stelle = stelle
                    mitarbeiter.save(update_fields=["stelle"])

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  OK: {mitarbeiter.vollname} -> {stelle.kuerzel}"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nERFOLG: {len(zuordnungen)} Stelle(n) besetzt!\n"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nNutze --execute um die Zuordnungen durchzufuehren.\n"
                )
            )
