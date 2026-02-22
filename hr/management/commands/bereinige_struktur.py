"""Management Command zum Bereinigen der Organisationsstruktur."""

from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import HierarchieSnapshot, OrgEinheit, Stelle


class Command(BaseCommand):
    help = "Bereinigt die Organisationsstruktur und baut korrekte Hierarchie auf"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Fuehrt die Bereinigung wirklich durch (sonst nur Vorschau)",
        )

    def handle(self, *args, **options):
        execute = options["execute"]

        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    "\nVORSCHAU-MODUS (nutze --execute um wirklich zu bereinigen)\n"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nWARNUNG: Dies wird die Struktur umbauen!\n"
                )
            )
            confirm = input("Fortfahren? (ja/nein): ")
            if confirm.lower() != "ja":
                self.stdout.write("Abgebrochen.")
                return

        self.stdout.write("\n=== SCHRITT 1: Snapshot erstellen ===\n")
        if execute:
            self._create_snapshot()
            self.stdout.write(self.style.SUCCESS("Snapshot erstellt!"))
        else:
            self.stdout.write("Wuerde Snapshot erstellen...")

        self.stdout.write("\n=== SCHRITT 2: Ziel-Hierarchie definieren ===\n")

        # Neue Struktur definieren
        struktur = {
            "GF": {
                "bezeichnung": "Geschaeftsfuehrung",
                "kinder": {
                    "IT": {
                        "bezeichnung": "Informationstechnik",
                        "kinder": {
                            "DA": {"bezeichnung": "Daten & Analyse", "kinder": {}},
                            "II": {"bezeichnung": "IT-Infrastruktur", "kinder": {}},
                        },
                    },
                    "BV": {
                        "bezeichnung": "Betrieb & Verwaltung",
                        "kinder": {
                            "FM": {"bezeichnung": "Facility Management", "kinder": {}},
                            "EL": {"bezeichnung": "Einkauf & Logistik", "kinder": {}},
                            "BH": {"bezeichnung": "Buchhaltung", "kinder": {}},
                            "CO": {"bezeichnung": "Controlling", "kinder": {}},
                        },
                    },
                    "HR": {
                        "bezeichnung": "Human Resources",
                        "kinder": {
                            "PE": {"bezeichnung": "Personalentwicklung", "kinder": {}},
                            "PV": {"bezeichnung": "Personalverwaltung", "kinder": {}},
                            "PG": {"bezeichnung": "Personalgewinnung", "kinder": {}},
                            "LG": {"bezeichnung": "Lohn & Gehalt", "kinder": {}},
                        },
                    },
                    "VM": {
                        "bezeichnung": "Vertrieb & Marketing",
                        "kinder": {
                            "AD": {"bezeichnung": "Aussendienst", "kinder": {}},
                            "ID": {"bezeichnung": "Innendienst", "kinder": {}},
                            "MK": {"bezeichnung": "Marketing", "kinder": {}},
                        },
                    },
                    "TE": {
                        "bezeichnung": "Technik",
                        "kinder": {
                            "PR": {"bezeichnung": "Produktentwicklung", "kinder": {}},
                            "SE": {"bezeichnung": "Softwareentwicklung", "kinder": {}},
                            "QS": {"bezeichnung": "Qualitaetssicherung", "kinder": {}},
                        },
                    },
                    "ZA": {
                        "bezeichnung": "Zeit & Abrechnung",
                        "kinder": {},
                    },
                },
            }
        }

        self._print_struktur(struktur)

        self.stdout.write("\n=== SCHRITT 3: OrgEinheiten aufbauen ===\n")

        if execute:
            with transaction.atomic():
                org_map = self._baue_hierarchie(struktur)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n{len(org_map)} OrgEinheiten erstellt/aktualisiert!"
                    )
                )

                self.stdout.write("\n=== SCHRITT 4: Stellen zuordnen ===\n")
                self._ordne_stellen_zu(org_map)

                self.stdout.write("\n=== SCHRITT 5: Leere OrgEinheiten loeschen ===\n")
                self._loesche_leere_orgeinheiten()

            self.stdout.write(
                self.style.SUCCESS("\n\nERFOLG: Struktur bereinigt!\n")
            )
        else:
            self.stdout.write("Wuerde OrgEinheiten aufbauen...")
            self.stdout.write("Wuerde Stellen zuordnen...")
            self.stdout.write("Wuerde leere OrgEinheiten loeschen...")
            self.stdout.write(
                self.style.WARNING(
                    "\nNutze --execute um die Bereinigung durchzufuehren.\n"
                )
            )

    def _create_snapshot(self):
        """Erstellt einen Snapshot vor der Bereinigung."""
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Sammle aktuelle Hierarchie
        snapshot_data = {"orgeinheiten": [], "stellen": []}

        for org in OrgEinheit.objects.all():
            snapshot_data["orgeinheiten"].append(
                {
                    "id": org.id,
                    "kuerzel": org.kuerzel,
                    "bezeichnung": org.bezeichnung,
                    "uebergeordnet_id": org.uebergeordnet_id,
                    "ist_reserviert": org.ist_reserviert,
                }
            )

        for stelle in Stelle.objects.all():
            snapshot_data["stellen"].append(
                {
                    "id": stelle.id,
                    "kuerzel": stelle.kuerzel,
                    "bezeichnung": stelle.bezeichnung,
                    "org_einheit_id": stelle.org_einheit_id,
                    "uebergeordnete_stelle_id": stelle.uebergeordnete_stelle_id,
                }
            )

        # Erstelle Snapshot
        admin_user = User.objects.filter(is_staff=True).first()
        HierarchieSnapshot.objects.create(
            created_by=admin_user, snapshot_data=snapshot_data
        )

    def _print_struktur(self, struktur, level=0):
        """Gibt die Zielstruktur aus."""
        for kuerzel, data in struktur.items():
            indent = "  " * level
            self.stdout.write(
                f"{indent}+ {kuerzel} - {data['bezeichnung']}"
            )
            if data.get("kinder"):
                self._print_struktur(data["kinder"], level + 1)

    def _baue_hierarchie(self, struktur, parent=None, org_map=None):
        """Baut die OrgEinheiten-Hierarchie rekursiv auf."""
        if org_map is None:
            org_map = {}

        for kuerzel, data in struktur.items():
            # Hole oder erstelle OrgEinheit
            org, created = OrgEinheit.objects.get_or_create(
                kuerzel=kuerzel,
                defaults={
                    "bezeichnung": data["bezeichnung"],
                    "uebergeordnet": parent,
                    "ist_reserviert": kuerzel in ["GF", "IT", "BV", "HR", "FM"],
                },
            )

            if not created:
                # Update bestehende
                org.bezeichnung = data["bezeichnung"]
                org.uebergeordnet = parent
                org.save(update_fields=["bezeichnung", "uebergeordnet"])
                self.stdout.write(f"  Aktualisiert: {kuerzel}")
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"  Erstellt: {kuerzel}")
                )

            org_map[kuerzel] = org

            # Rekursiv Kinder aufbauen
            if data.get("kinder"):
                self._baue_hierarchie(data["kinder"], parent=org, org_map=org_map)

        return org_map

    def _ordne_stellen_zu(self, org_map):
        """Ordnet Stellen den richtigen OrgEinheiten zu."""
        # Mapping: Stellen-Prefix -> OrgEinheit-Kuerzel
        prefix_map = {
            "gf_": "GF",
            "bl_it": "IT",
            "al_da": "DA",
            "ma_da": "DA",
            "sv_da": "DA",
            "al_ii": "II",
            "ma_ii": "II",
            "sv_ii": "II",
            "al_fm": "FM",
            "ma_fm": "FM",
            "sv_fm": "FM",
            "al_el": "EL",
            "ma_el": "EL",
            "sv_el": "EL",
            "al_bh": "BH",
            "ma_bh": "BH",
            "sv_bh": "BH",
            "al_co": "CO",
            "ma_co": "CO",
            "sv_co": "CO",
            "hr_": "HR",
            "al_pe": "PE",
            "ma_pe": "PE",
            "sv_pe": "PE",
            "al_pv": "PV",
            "ma_pv": "PV",
            "sv_pv": "PV",
            "al_pg": "PG",
            "ma_pg": "PG",
            "sv_pg": "PG",
            "al_lg": "LG",
            "ma_lg": "LG",
            "sv_lg": "LG",
            "al_ad": "AD",
            "ma_ad": "AD",
            "sv_ad": "AD",
            "al_id": "ID",
            "ma_id": "ID",
            "sv_id": "ID",
            "al_mk": "MK",
            "ma_mk": "MK",
            "sv_mk": "MK",
            "al_pr": "PR",
            "ma_pr": "PR",
            "sv_pr": "PR",
            "al_se": "SE",
            "ma_se": "SE",
            "sv_se": "SE",
            "al_qs": "QS",
            "ma_qs": "QS",
            "sv_qs": "QS",
            "tl_za": "ZA",
            "ma_za": "ZA",
            "sv_za": "ZA",
            "bl_bv": "BV",  # Bereichsleiter BV -> BV
            "ap_": "HR",  # Automatisch erstellte Stellen -> HR
            "ma001": "HR",
            "sv001": "HR",
        }

        count = 0
        for stelle in Stelle.objects.all():
            # Finde passende OrgEinheit
            neue_org = None

            for prefix, org_kuerzel in prefix_map.items():
                if stelle.kuerzel.startswith(prefix):
                    neue_org = org_map.get(org_kuerzel)
                    break

            if neue_org and stelle.org_einheit != neue_org:
                alte_org = stelle.org_einheit.kuerzel if stelle.org_einheit else "None"
                stelle.org_einheit = neue_org
                stelle.save(update_fields=["org_einheit"])
                self.stdout.write(
                    f"  {stelle.kuerzel}: {alte_org} -> {neue_org.kuerzel}"
                )
                count += 1

        self.stdout.write(
            self.style.SUCCESS(f"\n{count} Stellen neu zugeordnet!")
        )

    def _loesche_leere_orgeinheiten(self):
        """Loescht OrgEinheiten ohne Stellen und ohne Untereinheiten."""
        # Finde leere OrgEinheiten (nicht reserviert)
        leere = []
        for org in OrgEinheit.objects.filter(ist_reserviert=False):
            if (
                org.stellen.count() == 0
                and org.untereinheiten.count() == 0
            ):
                leere.append(org)

        if leere:
            self.stdout.write(
                f"Loesche {len(leere)} leere OrgEinheiten:"
            )
            for org in leere:
                self.stdout.write(f"  - {org.kuerzel} ({org.bezeichnung})")
                org.delete()
        else:
            self.stdout.write("Keine leeren OrgEinheiten gefunden.")
