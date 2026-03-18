"""
Management Command: loesche_freigegebene_dokumente

Loescht DMS-Dokumente bei denen:
  - loeschen_am <= heute
  - loeschen_genehmigt = True

Taeglich per Cron aufrufen:
  python manage.py loesche_freigegebene_dokumente

Optionen:
  --dry-run   Nur anzeigen, nicht loeschen
"""
import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Loescht DMS-Dokumente mit abgelaufenem, genehmigtem Loeschkennzeichen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen welche Dokumente geloescht wuerden, nicht wirklich loeschen.",
        )

    def handle(self, *args, **options):
        from dms.models import Dokument, ZugriffsProtokoll

        dry_run = options["dry_run"]
        heute = date.today()

        kandidaten = Dokument.objects.filter(
            loeschen_am__lte=heute,
            loeschen_genehmigt=True,
        ).select_related("loeschen_beantragt_von", "erstellt_von")

        anzahl = kandidaten.count()
        if anzahl == 0:
            self.stdout.write("  [OK]  Keine faelligen Loeschdokumente gefunden.")
            return

        self.stdout.write(
            f"  {'[DRY-RUN] ' if dry_run else ''}Gefunden: {anzahl} Dokument(e) zum Loeschen."
        )

        geloescht = 0
        fehler = 0
        for dok in kandidaten:
            info = (
                f"pk={dok.pk} | '{dok.titel}' | "
                f"Loeschen am: {dok.loeschen_am} | "
                f"Beantragt von: {dok.loeschen_beantragt_von or '-'}"
            )
            if dry_run:
                self.stdout.write(f"  [DRY]  Wuerde loeschen: {info}")
                continue

            try:
                # Protokolleintrag vor dem Loeschen
                ZugriffsProtokoll.objects.create(
                    dokument=dok,
                    user=dok.loeschen_beantragt_von,
                    aktion="loeschen",
                    zeitpunkt=timezone.now(),
                    notiz=(
                        f"Automatische Loeschung nach genehmigtem Loeschantrag. "
                        f"Loeschen-am: {dok.loeschen_am}. "
                        f"Begruendung: {dok.loeschen_begruendung or '-'}"
                    ),
                )
                dok.delete()
                geloescht += 1
                self.stdout.write(f"  [DEL]  Geloescht: {info}")
                logger.info("DMS-Dokument geloescht: %s", info)
            except Exception as exc:
                fehler += 1
                self.stdout.write(
                    self.style.ERROR(f"  [ERR]  Fehler bei {info}: {exc}")
                )
                logger.error("Loeschfehler fuer Dokument pk=%s: %s", dok.pk, exc)

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Ergebnis: {geloescht} geloescht, {fehler} Fehler."
                )
            )
