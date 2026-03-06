"""Management Command: Erstellt Raumbelegungen anhand von Stelle-Kuerzel-Mapping.

Liest belegungen_mapping.json (stelle -> raumnummer) und erstellt Belegungen
fuer alle HRMitarbeiter deren Stelle im Mapping vorkommt.

Idempotent: bestehende Belegungen werden nicht dupliziert.
"""
import datetime
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Erstellt Raumbelegungen aus belegungen_mapping.json"

    def handle(self, *args, **options):
        from hr.models import HRMitarbeiter
        from raumbuch.models import Belegung, Raum

        mapping_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "fixtures", "belegungen_mapping.json",
        )
        mapping_path = os.path.normpath(mapping_path)

        with open(mapping_path, encoding="utf-8") as f:
            mapping = json.load(f)

        heute = datetime.date.today()
        erstellt = 0
        uebersprungen = 0
        nicht_gefunden = 0

        # Vorhandene Stellen und HRMitarbeiter auf diesem System ermitteln
        vorhandene_stellen = set(
            HRMitarbeiter.objects.exclude(stelle=None)
            .values_list("stelle__kuerzel", flat=True)
        )
        self.stdout.write(
            f"  HRMitarbeiter mit Stelle: {len(vorhandene_stellen)} "
            f"| Mapping-Eintraege: {len(mapping)}"
        )

        with transaction.atomic():
            for eintrag in mapping:
                stelle_kuerzel = eintrag["stelle"]
                raumnummer = eintrag["raum"]

                if stelle_kuerzel not in vorhandene_stellen:
                    nicht_gefunden += 1
                    continue

                try:
                    ma = HRMitarbeiter.objects.get(stelle__kuerzel=stelle_kuerzel)
                except (HRMitarbeiter.DoesNotExist, HRMitarbeiter.MultipleObjectsReturned):
                    nicht_gefunden += 1
                    continue

                try:
                    raum = Raum.objects.get(raumnummer=raumnummer)
                except Raum.DoesNotExist:
                    nicht_gefunden += 1
                    continue

                _, created = Belegung.objects.get_or_create(
                    mitarbeiter=ma,
                    raum=raum,
                    defaults={"von": heute},
                )
                if created:
                    erstellt += 1
                else:
                    uebersprungen += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Belegungen: {erstellt} erstellt, "
                f"{uebersprungen} bereits vorhanden, "
                f"{nicht_gefunden} Stelle nicht verknuepft/Raum fehlt."
            )
        )
