"""
Management-Command: Volltext-Suchvektoren aller Dokumente neu aufbauen.

Benoetigt fuer:
  - Erstbefuellung nach Migration auf SearchVectorField (0008)
  - Neuerstellung nach Aenderungen am Gewichtungsschema
  - Reparatur bei beschaedigten oder leeren Suchvektoren

Verwendung:
    python manage.py fts_reindex
    python manage.py fts_reindex --nur-leer      # nur Dok ohne Vektor
    python manage.py fts_reindex --paperless      # OCR-Text neu aus Paperless holen
    python manage.py fts_reindex --batch 500      # Stapelgroesse (Standard: 200)
"""
import logging

from django.core.management.base import BaseCommand

from dms.models import Dokument
from dms.services import suchvektor_befuellen

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Volltext-Suchvektoren aller offenen Dokumente neu aufbauen"

    def add_arguments(self, parser):
        parser.add_argument(
            "--nur-leer",
            action="store_true",
            help="Nur Dokumente ohne bestehenden Suchvektor verarbeiten",
        )
        parser.add_argument(
            "--paperless",
            action="store_true",
            help="OCR-Text fuer Paperless-Dokumente neu aus der Paperless-API laden",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=200,
            help="Anzahl Dokumente pro Datenbankabfrage (Standard: 200)",
        )

    def handle(self, *args, **options):
        nur_leer = options["nur_leer"]
        paperless_refresh = options["paperless"]
        batch = options["batch"]

        qs = Dokument.objects.filter(klasse="offen")
        if nur_leer:
            qs = qs.filter(suchvektor__isnull=True)

        gesamt = qs.count()
        self.stdout.write(
            f"Reindiziere {gesamt} Dokumente "
            f"({'nur leere' if nur_leer else 'alle offenen'}) "
            f"in Stapeln von {batch} ..."
        )

        # Paperless-Verbindung fuer OCR-Refresh vorbereiten
        paperless_client = None
        if paperless_refresh:
            from django.conf import settings as conf
            import urllib.request
            pl_base = getattr(conf, "PAPERLESS_URL", "").rstrip("/")
            pl_token = getattr(conf, "PAPERLESS_TOKEN", "")
            if pl_base and pl_token:
                paperless_client = (pl_base, pl_token)
                self.stdout.write("  Paperless-API verbunden – OCR-Text wird aktualisiert.")
            else:
                self.stdout.write("  WARNUNG: PAPERLESS_URL/TOKEN fehlen – kein OCR-Refresh.")

        verarbeitet = 0
        fehler = 0
        offset = 0

        while True:
            stapel = list(qs.order_by("pk")[offset:offset + batch])
            if not stapel:
                break

            for dok in stapel:
                ocr_text = dok.ocr_text or ""

                # Optional: OCR-Text frisch aus Paperless laden
                if paperless_refresh and dok.paperless_id and paperless_client:
                    pl_base, pl_token = paperless_client
                    import json
                    import urllib.error
                    try:
                        req = urllib.request.Request(
                            f"{pl_base}/api/documents/{dok.paperless_id}/",
                            headers={
                                "Authorization": f"Token {pl_token}",
                                "Accept": "application/json",
                            },
                        )
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            daten = json.loads(resp.read().decode("utf-8"))
                        ocr_text = (daten.get("content") or "").strip()
                        if ocr_text != dok.ocr_text:
                            Dokument.objects.filter(pk=dok.pk).update(ocr_text=ocr_text)
                    except urllib.error.URLError as exc:
                        logger.warning("OCR-Refresh fehlgeschlagen fuer Dok %s: %s", dok.pk, exc)

                try:
                    suchvektor_befuellen(dok, ocr_text)
                    verarbeitet += 1
                except Exception as exc:
                    logger.error("Reindex fehlgeschlagen fuer Dok %s: %s", dok.pk, exc)
                    fehler += 1

            offset += batch
            self.stdout.write(f"  {min(offset, gesamt)}/{gesamt} verarbeitet ...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Fertig: {verarbeitet} Suchvektoren aufgebaut, {fehler} Fehler."
            )
        )
