"""Management Command: reorganisiere_auf_2_gfs

Reorganisiert die Struktur auf 2 GFs:
- GF Technik (IT & Entwicklung)
- GF Verwaltung (alle anderen Bereiche)

Aufruf:
    python manage.py reorganisiere_auf_2_gfs
    python manage.py reorganisiere_auf_2_gfs --dry-run
"""

from django.core.management.base import BaseCommand

from hr.models import Stelle, HRMitarbeiter


class Command(BaseCommand):
    help = "Reorganisiert auf 2 GF-Stellen"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt nur was gemacht wuerde, ohne zu speichern.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Hole die GF-Stellen
        gf_technik = Stelle.objects.filter(kuerzel="gf_technik").first()
        gf_verwaltung = Stelle.objects.filter(kuerzel="gf_verwaltung").first()
        gf_produktion = Stelle.objects.filter(kuerzel="gf_produktion").first()
        gf_finanzen = Stelle.objects.filter(kuerzel="gf_finanzen").first()

        if not gf_technik:
            self.stdout.write(self.style.ERROR("gf_technik nicht gefunden!"))
            return

        if not gf_finanzen:
            self.stdout.write(self.style.WARNING("gf_finanzen nicht gefunden - wurde bereits geloescht?"))
            if not gf_verwaltung:
                self.stdout.write(self.style.ERROR("Auch gf_verwaltung nicht gefunden!"))
                return

        # Phase 1: Umbenennen nur wenn nötig
        if gf_produktion and not gf_verwaltung:
            self.stdout.write("\n=== Phase 1: GF Produktion zu GF Verwaltung umbenennen ===\n")
            self.stdout.write(f"  {gf_produktion.kuerzel} -> gf_verwaltung: Geschaeftsfuehrung Verwaltung")
            if not dry_run:
                gf_produktion.kuerzel = "gf_verwaltung"
                gf_produktion.bezeichnung = "Geschaeftsfuehrung Verwaltung"
                gf_produktion.save(update_fields=["kuerzel", "bezeichnung"])
                gf_verwaltung = gf_produktion
            else:
                gf_verwaltung = gf_produktion
        elif gf_verwaltung:
            self.stdout.write("\n=== Phase 1: ÜBERSPRUNGEN (gf_verwaltung existiert bereits) ===\n")
        else:
            self.stdout.write(self.style.ERROR("Weder gf_produktion noch gf_verwaltung gefunden!"))
            return

        self.stdout.write("\n=== Phase 2: GF Finanzen auflösen ===\n")

        # Alle untergeordneten Stellen von gf_finanzen zu gf_verwaltung verschieben
        untergeordnete = Stelle.objects.filter(uebergeordnete_stelle=gf_finanzen)
        self.stdout.write(f"  {untergeordnete.count()} Stellen von gf_finanzen zu gf_verwaltung verschieben")

        if not dry_run:
            untergeordnete.update(uebergeordnete_stelle=gf_verwaltung)

        # Mitarbeiter von gf_finanzen Stelle entfernen (OneToOneField Konflikt)
        if gf_finanzen.ist_besetzt:
            ma = gf_finanzen.aktueller_inhaber
            self.stdout.write(f"  Mitarbeiter {ma.vollname}: Stelle entfernen (gf_finanzen wird geloescht)")
            if not dry_run:
                ma.stelle = None
                ma.save(update_fields=["stelle"])

        # gf_finanzen löschen
        self.stdout.write(f"  gf_finanzen löschen")
        if not dry_run:
            gf_finanzen.delete()

        self.stdout.write("\n=== Phase 3: Bereichsleiter neu zuordnen ===\n")

        # Mapping: OrgEinheit -> GF
        bereich_zuordnung = {
            "IT": gf_technik,
            "BV": gf_verwaltung,
            "VW": gf_verwaltung,
            "HR": gf_verwaltung,
            "FM": gf_verwaltung,
        }

        # Alle Bereichsleiter
        bereichsleiter = Stelle.objects.filter(kuerzel__startswith="bl_")

        zugeordnet = 0
        for bl in bereichsleiter:
            org_kuerzel = bl.org_einheit.kuerzel
            zustaendige_gf = bereich_zuordnung.get(org_kuerzel)

            if zustaendige_gf:
                # Prüfe ob bereits korrekt zugeordnet
                if bl.uebergeordnete_stelle != zustaendige_gf:
                    self.stdout.write(f"  {bl.kuerzel} ({org_kuerzel}) -> {zustaendige_gf.kuerzel}")
                    if not dry_run:
                        bl.uebergeordnete_stelle = zustaendige_gf
                        bl.save(update_fields=["uebergeordnete_stelle"])
                    zugeordnet += 1
                else:
                    self.stdout.write(f"  {bl.kuerzel} ({org_kuerzel}) -> bereits korrekt")
            else:
                self.stdout.write(
                    self.style.WARNING(f"  {bl.kuerzel} ({org_kuerzel}) -> Kein GF gefunden!")
                )

        # Zusammenfassung
        self.stdout.write(
            f"\n{'[DRY-RUN] ' if dry_run else ''}Fertig: "
            f"2 GF-Stellen, {untergeordnete.count()} Stellen verschoben, "
            f"{zugeordnet} neu zugeordnet."
        )
