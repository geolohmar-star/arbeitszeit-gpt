"""Management Command: strukturiere_gf_bereiche

Strukturiert die Organisation mit 3 GF-Stellen fuer verschiedene Verantwortungsbereiche:
- GF Technik (IT, Technik/Logistik)
- GF Produktion (Pflege, Kueche)
- GF Finanzen (Verwaltung, HR, Facility Management)

Ordnet die entsprechenden Bereichsleiter den jeweiligen GFs unter.

Aufruf:
    python manage.py strukturiere_gf_bereiche
    python manage.py strukturiere_gf_bereiche --dry-run
"""

from django.core.management.base import BaseCommand

from hr.models import Stelle


class Command(BaseCommand):
    help = "Strukturiert GF-Bereiche neu"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt nur was gemacht wuerde, ohne zu speichern.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Hole die 3 GF-Stellen (sortiert nach PK)
        gf_stellen = list(Stelle.objects.filter(kuerzel__startswith="gf_").order_by("pk"))

        if len(gf_stellen) < 3:
            self.stdout.write(self.style.ERROR(f"Nur {len(gf_stellen)} GF-Stellen gefunden. Benoetigt: 3"))
            return

        gf_technik = gf_stellen[0]
        gf_produktion = gf_stellen[1]
        gf_finanzen = gf_stellen[2]

        # Mapping: Bereichsleiter-Prefix -> GF
        bereich_zuordnung = {
            "IT": gf_technik,
            "TL": gf_technik,  # Technik/Logistik
            "PF": gf_produktion,  # Pflege
            "KU": gf_produktion,  # Kueche
            "VW": gf_finanzen,  # Verwaltung
            "HR": gf_finanzen,  # Human Resources
            "FM": gf_finanzen,  # Facility Management
            "BV": gf_finanzen,  # Betrieb & Verwaltung (Fallback)
        }

        self.stdout.write("\n=== Phase 1: GF-Stellen umbenennen ===\n")

        # GF-Stellen umbenennen
        aenderungen = [
            (gf_technik, "gf_technik", "Geschaeftsfuehrung Technik"),
            (gf_produktion, "gf_produktion", "Geschaeftsfuehrung Produktion"),
            (gf_finanzen, "gf_finanzen", "Geschaeftsfuehrung Finanzen"),
        ]

        for stelle, neues_kuerzel, neue_bezeichnung in aenderungen:
            self.stdout.write(
                f"  {stelle.kuerzel} -> {neues_kuerzel}: {neue_bezeichnung}"
            )
            if not dry_run:
                stelle.kuerzel = neues_kuerzel
                stelle.bezeichnung = neue_bezeichnung
                stelle.save(update_fields=["kuerzel", "bezeichnung"])

        self.stdout.write("\n=== Phase 2: Bereichsleiter den GFs unterordnen ===\n")

        # Hole alle Bereichsleiter (bl_) und Abteilungsleiter (al_)
        bereichsleiter = Stelle.objects.filter(
            kuerzel__startswith="bl_"
        ).select_related("org_einheit")

        abteilungsleiter = Stelle.objects.filter(
            kuerzel__startswith="al_"
        ).select_related("org_einheit")

        zugeordnet = 0

        # Bereichsleiter direkt unter GFs
        for bl in bereichsleiter:
            org_kuerzel = bl.org_einheit.kuerzel
            zustaendige_gf = bereich_zuordnung.get(org_kuerzel)

            if zustaendige_gf:
                self.stdout.write(
                    f"  {bl.kuerzel} ({org_kuerzel}) -> {zustaendige_gf.kuerzel}"
                )
                if not dry_run:
                    bl.uebergeordnete_stelle = zustaendige_gf
                    bl.save(update_fields=["uebergeordnete_stelle"])
                zugeordnet += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {bl.kuerzel} ({org_kuerzel}) -> Kein GF gefunden!"
                    )
                )

        # Abteilungsleiter unter Bereichsleiter (wenn vorhanden)
        # Sonst direkt unter GF
        self.stdout.write("\n=== Phase 3: Abteilungsleiter zuordnen ===\n")

        for al in abteilungsleiter:
            org_kuerzel = al.org_einheit.kuerzel

            # Suche Bereichsleiter in gleicher OrgEinheit
            bl_gleiche_org = Stelle.objects.filter(
                kuerzel__startswith="bl_", org_einheit=al.org_einheit
            ).first()

            if bl_gleiche_org:
                self.stdout.write(
                    f"  {al.kuerzel} -> {bl_gleiche_org.kuerzel} (BL)"
                )
                if not dry_run:
                    al.uebergeordnete_stelle = bl_gleiche_org
                    al.save(update_fields=["uebergeordnete_stelle"])
            else:
                # Direkt unter GF
                zustaendige_gf = bereich_zuordnung.get(org_kuerzel)
                if zustaendige_gf:
                    self.stdout.write(
                        f"  {al.kuerzel} -> {zustaendige_gf.kuerzel} (GF direkt)"
                    )
                    if not dry_run:
                        al.uebergeordnete_stelle = zustaendige_gf
                        al.save(update_fields=["uebergeordnete_stelle"])
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {al.kuerzel} ({org_kuerzel}) -> Kein GF gefunden!"
                        )
                    )

        # Zusammenfassung
        self.stdout.write(
            f"\n{'[DRY-RUN] ' if dry_run else ''}Fertig: "
            f"3 GF-Stellen umbenannt, {zugeordnet} Bereichsleiter zugeordnet."
        )
