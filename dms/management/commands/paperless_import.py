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
import re
import urllib.request
import urllib.error

from django.conf import settings
from django.core.management.base import BaseCommand

from dms.models import Dokument, DokumentKategorie, DokumentTag, PaperlessImportLog, PaperlessWorkflowRegel
from dms.services import speichere_dokument, suchvektor_befuellen

# Muster fuer Vorgangsnummern: KUERZEL-LFDNR-DATUM-UHRZEIT, z.B. HUN-00042-20260323-1423
VORGANGSNUMMER_RE = re.compile(r"\b([A-Z]{2,6})-(\d{5})-(\d{8})-(\d{4})\b")

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

        # Aktive Workflow-Regeln laden (nach Prioritaet sortiert)
        regeln = list(PaperlessWorkflowRegel.objects.filter(aktiv=True).select_related("workflow_template"))

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

        # Paperless Dokumenttypen + Tags als {id: name}-Dict laden (fuer Regel-Matching)
        doc_types = {}
        tag_names_map = {}
        if regeln and dokumente:
            try:
                req = urllib.request.Request(
                    f"{base_url}/api/document_types/?page_size=200", headers=headers
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    dt_daten = json.loads(resp.read().decode("utf-8"))
                doc_types = {item["id"]: item["name"] for item in dt_daten.get("results", [])}

                req = urllib.request.Request(
                    f"{base_url}/api/tags/?page_size=500", headers=headers
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    tag_daten = json.loads(resp.read().decode("utf-8"))
                tag_names_map = {item["id"]: item["name"] for item in tag_daten.get("results", [])}
            except Exception as exc:
                logger.warning("Konnte Paperless-Metadaten (Tags/Typen) nicht laden: %s", exc)
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
            # OCR-Text: Paperless liefert ihn direkt im Dokument-JSON (Feld 'content')
            ocr_text = (doc.get("content") or "").strip()

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

            # Workflow-Vorschlag ermitteln (erste passende aktive Regel)
            workflow_vorschlag = None
            if regeln:
                dt_id = doc.get("document_type")
                dt_name = (doc_types.get(dt_id) or "").strip().lower() if dt_id else ""
                tag_ids = doc.get("tags") or []
                tag_names_lower = {
                    (tag_names_map.get(tid) or "").strip().lower()
                    for tid in tag_ids
                    if tag_names_map.get(tid)
                }

                for regel in regeln:
                    vergleich = (regel.paperless_name or "").strip().lower()
                    if regel.treffer_typ == PaperlessWorkflowRegel.TREFFER_DOKUMENTTYP:
                        if vergleich and dt_name == vergleich:
                            workflow_vorschlag = regel.workflow_template
                            break
                    elif regel.treffer_typ == PaperlessWorkflowRegel.TREFFER_TAG:
                        if vergleich and vergleich in tag_names_lower:
                            workflow_vorschlag = regel.workflow_template
                            break
                    elif regel.treffer_typ == PaperlessWorkflowRegel.TREFFER_MUSTER:
                        muster = (regel.muster_regex or "").strip()
                        if muster and ocr_text:
                            try:
                                treffer = re.search(muster, ocr_text)
                            except re.error as exc:
                                logger.warning(
                                    "Ungueltige Regex in Regel '%s': %s", regel.bezeichnung, exc
                                )
                                continue
                            if treffer:
                                workflow_vorschlag = regel.workflow_template
                                logger.info(
                                    "Muster-Treffer '%s' fuer Regel '%s' in Paperless #%s",
                                    treffer.group(0),
                                    regel.bezeichnung,
                                    pl_id,
                                )
                                break

            if workflow_vorschlag:
                self.stdout.write(
                    f"    Workflow-Vorschlag: '{workflow_vorschlag.name}' fuer #{pl_id} '{titel}'"
                )

            # Dokument anlegen (Klasse 1 – offen, da Paperless-Dokumente im Regelfall offen sind)
            dok = Dokument(
                titel=titel,
                dateiname=dateiname,
                dateityp=content_type,
                groesse_bytes=len(inhalt_bytes),
                klasse="offen",
                paperless_id=pl_id,
                workflow_vorschlag=workflow_vorschlag,
                ocr_text=ocr_text,
            )

            try:
                speichere_dokument(dok, inhalt_bytes)
                dok.save()

                # Paperless-Tags als PRIMA-DMS-Tags uebernehmen (get_or_create)
                for tid in (doc.get("tags") or []):
                    tag_name = (tag_names_map.get(tid) or "").strip()
                    if tag_name:
                        prima_tag, _ = DokumentTag.objects.get_or_create(
                            name=tag_name,
                            defaults={"farbe": "#6b7280"},
                        )
                        dok.tags.add(prima_tag)

                # Suchvektor nach dem Speichern befuellen (pk benoetigt)
                suchvektor_befuellen(dok, ocr_text)

                # Vorgangsnummer im OCR-Text suchen und FormularEintrag verknuepfen
                if ocr_text:
                    self._verknuepfe_vorgangsnummer(ocr_text, dok, pl_id)

                PaperlessImportLog.objects.create(
                    paperless_id=pl_id,
                    dokument=dok,
                    status="ok",
                )
                importiert += 1
                ocr_info = f" ({len(ocr_text)} Zeichen OCR)" if ocr_text else " (kein OCR-Text)"
                self.stdout.write(f"  Importiert: #{pl_id} '{titel}'{ocr_info}")
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

    def _verknuepfe_vorgangsnummer(self, ocr_text, dok, pl_id):
        """Sucht Vorgangsnummern im OCR-Text, verknuepft FormularEintrag und startet ggf. Workflow."""
        from prozesse.models import FormularEintrag
        from workflow.services import WorkflowEngine

        treffer = VORGANGSNUMMER_RE.findall(ocr_text)
        if not treffer:
            return

        engine = WorkflowEngine()

        for kuerzel, lfdnr, datum, uhrzeit in treffer:
            vorgangsnummer = f"{kuerzel}-{lfdnr}-{datum}-{uhrzeit}"
            try:
                eintrag = FormularEintrag.objects.select_related(
                    "schema__workflow_template", "workflow_instance"
                ).get(vorgangsnummer=vorgangsnummer)

                if eintrag.paperless_dokument_id:
                    if eintrag.paperless_dokument_id != pl_id:
                        logger.warning(
                            "Vorgangsnummer %s bereits mit Paperless #%s verknuepft,"
                            " neuer Treffer: #%s",
                            vorgangsnummer,
                            eintrag.paperless_dokument_id,
                            pl_id,
                        )
                    continue

                # Paperless-Dokument verknuepfen
                eintrag.paperless_dokument_id = pl_id
                update_fields = ["paperless_dokument_id"]

                # Automatischen Workflow starten wenn Schema ein Template hat
                if eintrag.schema.workflow_template and not eintrag.workflow_instance:
                    try:
                        instance = engine.start_workflow(
                            template=eintrag.schema.workflow_template,
                            content_object=eintrag,
                            user=None,  # systemausgeloest, kein menschlicher User
                        )
                        eintrag.workflow_instance = instance
                        update_fields.append("workflow_instance")
                        self.stdout.write(
                            f"    Workflow '{eintrag.schema.workflow_template.name}'"
                            f" gestartet fuer Eintrag #{eintrag.pk} (Instanz #{instance.pk})."
                        )
                    except Exception as exc:
                        logger.error(
                            "Workflow-Start fehlgeschlagen fuer Eintrag #%s: %s",
                            eintrag.pk,
                            exc,
                        )

                eintrag.save(update_fields=update_fields)
                self.stdout.write(
                    f"    Vorgangsnummer {vorgangsnummer} mit FormularEintrag #{eintrag.pk}"
                    f" und Paperless #{pl_id} verknuepft."
                )

            except FormularEintrag.DoesNotExist:
                logger.info(
                    "Vorgangsnummer %s im OCR-Text von Paperless #%s gefunden,"
                    " aber kein passender FormularEintrag vorhanden.",
                    vorgangsnummer,
                    pl_id,
                )
