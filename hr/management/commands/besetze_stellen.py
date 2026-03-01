"""Management Command zum automatischen Besetzen von Stellen mit HRMitarbeitern.

Zuordnung nach Rolle + Bereich/Abteilung:
  gf             -> gf*  (OrgEinheit: GF)
  bereichsleiter -> bl_* (Bereich BV/FC/PO -> VW, IT -> IT, VM -> VM)
  abteilungsleiter -> al_* (Abteilung -> OrgEinheit, z.B. BU->BH, INF->II)
  assistent      -> sv_* (gleiche OrgEinheit wie Abteilung)
  teamleiter     -> tl_* (gleiche OrgEinheit wie Abteilung)
  mitarbeiter    -> ma_* (gleiche OrgEinheit wie Abteilung)
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import HRMitarbeiter, Stelle

# Abteilungs-Kuerzel -> OrgEinheit-Kuerzel (wo sie abweichen)
ABT_ZU_ORG = {
    "BU": "BH",   # Buchhaltung -> BH
    "INF": "II",  # IT-Infrastruktur -> II
    "PD": "PR",   # Produktentwicklung -> PR
}

# Bereichs-Kuerzel -> OrgEinheit-Kuerzel fuer Bereichsleiter
BEREICH_ZU_ORG_BL = {
    "BV": "VW",   # Betrieb & Verwaltung -> VW
    "FC": "VW",   # Finanzen & Controlling -> VW
    "PO": "VW",   # Personal & Organisation -> VW
    "IT": "IT",
    "VM": "VM",
    "GF": "GF",
}

# Rolle -> Stellen-Prefix
ROLLE_ZU_PREFIX = {
    "gf": "gf",
    "bereichsleiter": "bl_",
    "abteilungsleiter": "al_",
    "assistent": "sv_",
    "teamleiter": "tl_",
    "mitarbeiter": "ma_",
}


def _org_fuer_mitarbeiter(mitarbeiter):
    """Ermittelt den OrgEinheit-Kuerzel passend zu Rolle und Bereich/Abteilung."""
    rolle = mitarbeiter.rolle

    if rolle == "gf":
        return "GF"

    if rolle == "bereichsleiter":
        bereich_kuerzel = mitarbeiter.bereich.kuerzel if mitarbeiter.bereich else None
        return BEREICH_ZU_ORG_BL.get(bereich_kuerzel) if bereich_kuerzel else None

    # Alle anderen Rollen: Abteilung -> OrgEinheit
    if mitarbeiter.abteilung:
        abt = mitarbeiter.abteilung.kuerzel
        return ABT_ZU_ORG.get(abt, abt)

    return None


def _finde_stelle(mitarbeiter, freie_stellen_qs):
    """Sucht die passende freie Stelle fuer einen Mitarbeiter."""
    prefix = ROLLE_ZU_PREFIX.get(mitarbeiter.rolle)
    if not prefix:
        return None, "Rolle nicht gemappt"

    org_kuerzel = _org_fuer_mitarbeiter(mitarbeiter)

    # Erst: passender Prefix + passende OrgEinheit
    if org_kuerzel:
        stelle = (
            freie_stellen_qs
            .filter(kuerzel__istartswith=prefix, org_einheit__kuerzel=org_kuerzel)
            .order_by("kuerzel")
            .first()
        )
        if stelle:
            return stelle, None

    # Fallback: nur passender Prefix (ohne OrgEinheit-Match)
    stelle = (
        freie_stellen_qs
        .filter(kuerzel__istartswith=prefix)
        .order_by("kuerzel")
        .first()
    )
    if stelle:
        return stelle, f"Kein OrgEinheit-Match fuer '{org_kuerzel}', Fallback verwendet"

    return None, f"Keine freie Stelle mit Prefix '{prefix}' und OrgEinheit '{org_kuerzel}'"


class Command(BaseCommand):
    help = "Besetzt Stellen nach Rolle und Bereich/Abteilung automatisch"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Fuehrt die Zuordnung wirklich durch (sonst nur Vorschau)",
        )

    def handle(self, *args, **options):
        execute = options["execute"]

        if not execute:
            self.stdout.write(self.style.WARNING(
                "\nVORSCHAU-MODUS (--execute um wirklich zuzuordnen)\n"
            ))

        # Nur Mitarbeiter ohne Stelle und freie Stellen
        mitarbeiter_qs = (
            HRMitarbeiter.objects
            .filter(stelle__isnull=True)
            .select_related("bereich", "abteilung", "team")
            .order_by("rolle", "nachname")
        )
        freie_stellen_qs = Stelle.objects.filter(hrmitarbeiter__isnull=True)

        self.stdout.write(
            f"Mitarbeiter ohne Stelle: {mitarbeiter_qs.count()}\n"
            f"Freie Stellen:           {freie_stellen_qs.count()}\n"
        )

        zuordnungen = []
        nicht_zugeordnet = []

        # Bereits zugewiesene Stellen in dieser Runde verfolgen
        # (damit nicht 2 Mitarbeiter die gleiche Stelle bekommen)
        bereits_vergeben = set()

        for ma in mitarbeiter_qs:
            # freie_stellen_qs exkludiert die in dieser Runde bereits vergebenen
            verfuegbar = freie_stellen_qs.exclude(pk__in=bereits_vergeben)
            stelle, hinweis = _finde_stelle(ma, verfuegbar)

            if stelle:
                bereits_vergeben.add(stelle.pk)
                zuordnungen.append((ma, stelle, hinweis))
            else:
                nicht_zugeordnet.append((ma, hinweis))

        # Vorschau ausgeben
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"ZUORDNUNGEN ({len(zuordnungen)} Stueck):")
        self.stdout.write(f"{'='*60}")
        for ma, stelle, hinweis in zuordnungen:
            zeile = (
                f"  {ma.nachname}, {ma.vorname:15} ({ma.rolle:18}) "
                f"-> {stelle.kuerzel:12} | {stelle.bezeichnung[:40]}"
            )
            if hinweis:
                zeile += f"\n    [HINWEIS: {hinweis}]"
            self.stdout.write(zeile)

        if nicht_zugeordnet:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(
                self.style.WARNING(f"NICHT ZUGEORDNET ({len(nicht_zugeordnet)} Stueck):")
            )
            self.stdout.write(f"{'='*60}")
            for ma, grund in nicht_zugeordnet:
                abt = ma.abteilung.kuerzel if ma.abteilung else "-"
                self.stdout.write(
                    f"  {ma.nachname}, {ma.vorname} ({ma.rolle}, Abt:{abt}) "
                    f"-> {grund}"
                )

        self.stdout.write(f"\nErgebnis: {len(zuordnungen)} zugeordnet, "
                          f"{len(nicht_zugeordnet)} ohne Stelle\n")

        if not execute:
            self.stdout.write(self.style.WARNING(
                "Nutze --execute um die Zuordnungen durchzufuehren.\n"
            ))
            return

        # Durchfuehren
        with transaction.atomic():
            for ma, stelle, _ in zuordnungen:
                ma.stelle = stelle
                ma.save(update_fields=["stelle"])

        self.stdout.write(self.style.SUCCESS(
            f"\nERFOLG: {len(zuordnungen)} Stelle(n) besetzt!\n"
        ))
