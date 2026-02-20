"""Management Command: erstelle_stellen_aus_ma

Erstellt automatisch Stellen basierend auf vorhandenen HRMitarbeitern
und weist die Mitarbeiter den Stellen zu.

Logik:
1. Fuer jeden HRMitarbeiter ohne Stelle wird eine Stelle erstellt
2. Kuerzel: rolle_kuerzel + laufende Nummer (z.B. gf1, tl_fm1, ma_pf1)
3. OrgEinheit wird aus Bereich gemappt (FM -> FM, Pflege -> PF, etc.)
4. Hierarchie: uebergeordnete_stelle basierend auf hrm.vorgesetzter
5. Stelle wird dem HRMitarbeiter zugewiesen

Aufruf:
    python manage.py erstelle_stellen_aus_ma
    python manage.py erstelle_stellen_aus_ma --dry-run
"""

from django.core.management.base import BaseCommand

from hr.models import HRMitarbeiter, OrgEinheit, Stelle


class Command(BaseCommand):
    help = "Erstellt Stellen aus vorhandener HRMitarbeiter-Struktur"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt nur was gemacht wuerde, ohne zu speichern.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Mapping: Bereich -> OrgEinheit-Kuerzel
        bereich_mapping = {
            "Geschaeftsfuehrung": "GF",
            "Betrieb": "BV",
            "Verwaltung": "VW",
            "Human Resources": "HR",
            "IT": "IT",
            "Facility Management": "FM",
            "Pflege": "PF",
            "Kueche": "KU",
            "Technik": "TL",
            "Logistik": "TL",
        }

        # Rolle -> Kuerzel-Prefix
        rolle_prefix = {
            "gf": "gf",
            "bereichsleiter": "bl",
            "abteilungsleiter": "al",
            "teamleiter": "tl",
            "assistent": "sv",
            "mitarbeiter": "ma",
        }

        # Alle HRMitarbeiter ohne Stelle
        ohne_stelle = HRMitarbeiter.objects.filter(stelle__isnull=True).select_related(
            "bereich", "abteilung", "vorgesetzter"
        )
        gesamt = ohne_stelle.count()

        if gesamt == 0:
            self.stdout.write("Alle HRMitarbeiter haben bereits eine Stelle.")
            return

        self.stdout.write(f"\n{gesamt} HRMitarbeiter ohne Stelle gefunden.\n")

        erstellt = 0
        fehler = []
        stellen_cache = {}  # hrm.pk -> Stelle
        kuerzel_zaehler = {}  # (prefix, org_kuerzel) -> count

        # Phase 1: Stellen erstellen (ohne Hierarchie)
        for hrm in ohne_stelle:
            try:
                # OrgEinheit ermitteln
                bereich_name = hrm.bereich.name if hrm.bereich else None
                org_kuerzel = None

                # Exact Match
                if bereich_name in bereich_mapping:
                    org_kuerzel = bereich_mapping[bereich_name]
                else:
                    # Fuzzy Match fuer Teilstrings
                    for key, value in bereich_mapping.items():
                        if bereich_name and key.lower() in bereich_name.lower():
                            org_kuerzel = value
                            break

                if not org_kuerzel:
                    org_kuerzel = "BV"  # Fallback

                org_einheit = OrgEinheit.objects.get(kuerzel=org_kuerzel)

                # Kuerzel generieren
                prefix = rolle_prefix.get(hrm.rolle, "ma")
                zaehler_key = (prefix, org_kuerzel)

                # Initialisiere Zaehler falls noch nicht vorhanden
                if zaehler_key not in kuerzel_zaehler:
                    # Zaehle vorhandene Stellen mit gleichem Prefix in DB
                    kuerzel_zaehler[zaehler_key] = Stelle.objects.filter(
                        kuerzel__startswith=f"{prefix}_",
                        org_einheit=org_einheit,
                    ).count()

                # Erhoehe Zaehler
                kuerzel_zaehler[zaehler_key] += 1
                count = kuerzel_zaehler[zaehler_key]
                kuerzel = f"{prefix}_{org_kuerzel.lower()}{count}"

                # Bezeichnung
                bezeichnung = f"{hrm.get_rolle_display()}"
                if hrm.abteilung:
                    bezeichnung += f" {hrm.abteilung.name}"
                elif hrm.bereich:
                    bezeichnung += f" {hrm.bereich.name}"

                if not dry_run:
                    stelle = Stelle.objects.create(
                        kuerzel=kuerzel,
                        bezeichnung=bezeichnung,
                        org_einheit=org_einheit,
                        max_urlaubstage_genehmigung=0,  # Default: unbegrenzt
                        eskalation_nach_tagen=3,
                    )
                    stellen_cache[hrm.pk] = stelle
                    self.stdout.write(
                        f"  [OK] {hrm.vollname} ({hrm.rolle}) -> {kuerzel}"
                    )
                else:
                    self.stdout.write(
                        f"  [DRY-RUN] {hrm.vollname} ({hrm.rolle}) -> {kuerzel} ({org_kuerzel})"
                    )

                erstellt += 1

            except Exception as e:
                fehler.append((hrm, str(e)))
                self.stdout.write(
                    self.style.ERROR(f"  [FEHLER] {hrm.vollname}: {e}")
                )

        # Phase 2: Hierarchie setzen und Mitarbeiter zuweisen
        if not dry_run:
            self.stdout.write("\nSetze Hierarchie und weise Mitarbeiter zu...\n")
            for hrm in ohne_stelle:
                if hrm.pk not in stellen_cache:
                    continue

                stelle = stellen_cache[hrm.pk]

                # Hierarchie: uebergeordnete_stelle von Vorgesetztem
                if hrm.vorgesetzter and hrm.vorgesetzter.pk in stellen_cache:
                    stelle.uebergeordnete_stelle = stellen_cache[hrm.vorgesetzter.pk]
                elif hrm.vorgesetzter and hrm.vorgesetzter.stelle:
                    stelle.uebergeordnete_stelle = hrm.vorgesetzter.stelle

                stelle.save()

                # Stelle dem Mitarbeiter zuweisen
                hrm.stelle = stelle
                hrm.save(update_fields=["stelle"])

        # Zusammenfassung
        self.stdout.write(
            f"\n{'[DRY-RUN] ' if dry_run else ''}Ergebnis: "
            f"{erstellt} Stellen erstellt, {len(fehler)} Fehler."
        )

        if fehler:
            self.stdout.write("\nFehler bei folgenden Mitarbeitern:")
            for hrm, err in fehler[:10]:
                self.stdout.write(f"  {hrm.vollname}: {err}")
            if len(fehler) > 10:
                self.stdout.write(f"  ... und {len(fehler) - 10} weitere")
