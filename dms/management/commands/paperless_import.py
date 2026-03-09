"""
Management-Command: Paperless-ngx Dokumente importieren.

Pollt die Paperless-ngx REST API und importiert neue Dokumente in PRIMA DMS.
Bereits importierte Dokumente werden via PaperlessImportLog uebersprungen.

Verwendung:
    python manage.py paperless_import
    python manage.py paperless_import --limit 50
    python manage.py paperless_import --dry-run

Konfiguration in settings.py / .env:
    PAPERLESS_URL    Basis-URL, z.B. http://192.168.1.100:8000
    PAPERLESS_TOKEN  API-Token aus Paperless-Admin > API-Token
"""
import json
import logging
import urllib.request
import urllib.error

from django.conf import settings
from django.core.management.base import BaseCommand

from dms.models import Dokument, DokumentKategorie, PaperlessImportLog
from dms.services import speichere_dokument

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Importiert neue Dokumente aus Paperless-ngx in PRIMA DMS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximale Anzahl Dokumente pro Lauf (Standard: 25)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen was importiert wuerde, nichts speichern",
        )

    def handle(self, *args, **options):
        base_url = getattr(settings, "PAPERLESS_URL", "").rstrip("/")
        token = getattr(settings, "PAPERLESS_TOKEN", "")
        limit = options["limit"]
        dry_run = options["dry_run"]

        if not base_url or not token:
            self.stderr.write(
                "PAPERLESS_URL und PAPERLESS_TOKEN muessen in settings.py / .env konfiguriert sein."
            )
            return

        if dry_run:
            self.stdout.write("[DRY-RUN] Keine Aenderungen werden gespeichert.")

        # Bereits importierte IDs laden (Set fuer schnelles Lookup)
        bereits_importiert = set(
            PaperlessImportLog.objects.values_list("paperless_id", flat=True)
        )

        # Paperless-API abfragen
        url = f"{base_url}/api/documents/?page_size={limit}&ordering=-created"
        headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                daten = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            self.stderr.write(f"Verbindung zu Paperless-ngx fehlgeschlagen: {exc}")
            return

        dokumente = daten.get("results", [])
        self.stdout.write(f"Paperless liefert {len(dokumente)} Dokumente (letzte {limit}).")

        importiert = 0
        uebersprungen = 0

        for doc in dokumente:
            pl_id = doc.get("id")
            if pl_id in bereits_importiert:
                uebersprungen += 1
                continue

            titel = doc.get("title") or doc.get("original_file_name") or f"Paperless #{pl_id}"
            dateiname = doc.get("original_file_name") or f"paperless_{pl_id}.pdf"
            content_type = "application/pdf"  # Paperless erzeugt immer PDFs

            # Inhalt herunterladen
            download_url = f"{base_url}/api/documents/{pl_id}/download/"
            try:
                req = urllib.request.Request(download_url, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    inhalt_bytes = resp.read()
                    ctype = resp.headers.get("Content-Type", content_type)
                    content_type = ctype.split(";")[0].strip()
            except urllib.error.URLError as exc:
                logger.warning("Download fehlgeschlagen fuer Paperless #%s: %s", pl_id, exc)
                if not dry_run:
                    PaperlessImportLog.objects.create(
                        paperless_id=pl_id,
                        status="fehler",
                        fehler=str(exc),
                    )
                continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] Wuerde importieren: #{pl_id} '{titel}' ({len(inhalt_bytes)} Bytes)"
                )
                importiert += 1
                continue

            # Dokument anlegen (Klasse 1 – offen, da Paperless-Dokumente im Regelfall offen sind)
            dok = Dokument(
                titel=titel,
                dateiname=dateiname,
                dateityp=content_type,
                groesse_bytes=len(inhalt_bytes),
                klasse="offen",
                paperless_id=pl_id,
            )

            try:
                speichere_dokument(dok, inhalt_bytes)
                dok.save()
                PaperlessImportLog.objects.create(
                    paperless_id=pl_id,
                    dokument=dok,
                    status="ok",
                )
                importiert += 1
                self.stdout.write(f"  Importiert: #{pl_id} '{titel}'")
            except Exception as exc:
                logger.error("Import fehlgeschlagen fuer Paperless #%s: %s", pl_id, exc)
                PaperlessImportLog.objects.create(
                    paperless_id=pl_id,
                    status="fehler",
                    fehler=str(exc),
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Fertig: {importiert} importiert, {uebersprungen} uebersprungen."
            )
        )
