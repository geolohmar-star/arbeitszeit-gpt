"""
Interner Signatur-Backend auf Basis von pyhanko + eigener Root-CA.

Laeuft vollstaendig offline im Intranet.
Erzeugt Fortgeschrittene Elektronische Signaturen (FES) nach eIDAS.

Austauschbar gegen sign-me Backend durch Aenderung von
settings.SIGNATUR_BACKEND = "sign_me"
"""
import hashlib
import io
import logging
import uuid
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)


class InternBackend:
    """
    FES-Backend: pyhanko + interne Root-CA.

    Implementiert dieselbe Schnittstelle wie SignaturBackend (base.py),
    sodass ein spaeterer Wechsel auf sign-me nur settings.py betrifft.
    """

    BACKEND_NAME = "intern"
    SIGNATUR_TYP = "FES"

    # ------------------------------------------------------------------
    # authentifiziere
    # ------------------------------------------------------------------
    def authentifiziere(self, user) -> dict:
        """Prueft ob User ein gueltiges Mitarbeiter-Zertifikat besitzt."""
        from signatur.models import MitarbeiterZertifikat
        try:
            zert = MitarbeiterZertifikat.objects.get(user=user, status="aktiv")
        except MitarbeiterZertifikat.DoesNotExist:
            raise ValueError(
                f"Kein aktives Zertifikat fuer {user.get_full_name()}. "
                "Bitte Administrator kontaktieren."
            )
        if not zert.ist_gueltig:
            raise ValueError(
                f"Zertifikat von {user.get_full_name()} ist abgelaufen oder gesperrt."
            )
        return {
            "token": str(uuid.uuid4()),
            "user_id": str(user.pk),
            "zertifikat_sn": zert.seriennummer,
            "gueltig_bis": str(zert.gueltig_bis),
        }

    # ------------------------------------------------------------------
    # starte_signatur_job
    # ------------------------------------------------------------------
    def starte_signatur_job(self, pdf_bytes: bytes, user, meta: dict) -> str:
        """Signiert das PDF synchron und legt einen Job-Eintrag an."""
        from django.utils import timezone as tz
        from signatur.models import MitarbeiterZertifikat, SignaturJob, SignaturProtokoll

        job_id = f"INT-{uuid.uuid4().hex[:12].upper()}"
        dokument_name = meta.get("dokument_name", "Dokument")

        job = SignaturJob.objects.create(
            job_id=job_id,
            backend="intern",
            status="pending",
            erstellt_von=user,
            dokument_name=dokument_name,
            content_type=meta.get("content_type", ""),
            object_id=meta.get("object_id"),
        )

        try:
            zert = MitarbeiterZertifikat.objects.get(user=user, status="aktiv")
            sichtbar = meta.get("sichtbar", True)
            seite = meta.get("seite", -1)

            signiertes_pdf = self._signiere_mit_pyhanko(
                pdf_bytes, zert, user, sichtbar, seite
            )

            doc_hash = hashlib.sha256(pdf_bytes).hexdigest()

            SignaturProtokoll.objects.create(
                job=job,
                unterzeichner=user,
                zertifikat=zert,
                hash_sha256=doc_hash,
                signatur_typ="FES",
                signiertes_pdf=signiertes_pdf,
            )

            job.status = "completed"
            job.abgeschlossen_am = tz.now()
            job.save()

        except Exception as exc:
            job.status = "failed"
            job.fehler_meldung = str(exc)
            job.save()
            logger.error("Signatur-Job %s fehlgeschlagen: %s", job_id, exc)
            raise

        return job_id

    # ------------------------------------------------------------------
    # hole_status
    # ------------------------------------------------------------------
    def hole_status(self, job_id: str) -> dict:
        from signatur.models import SignaturJob
        try:
            job = SignaturJob.objects.get(job_id=job_id)
        except SignaturJob.DoesNotExist:
            return {"status": "failed", "fortschritt": 0, "fehler": "Job nicht gefunden"}

        fortschritt = {"pending": 10, "completed": 100, "failed": 0}
        return {
            "status": job.status,
            "fortschritt": fortschritt.get(job.status, 0),
            "fehler": job.fehler_meldung or None,
        }

    # ------------------------------------------------------------------
    # hole_signiertes_pdf
    # ------------------------------------------------------------------
    def hole_signiertes_pdf(self, job_id: str) -> bytes:
        from signatur.models import SignaturJob
        try:
            job = SignaturJob.objects.get(job_id=job_id, status="completed")
            return bytes(job.protokoll.signiertes_pdf)
        except SignaturJob.DoesNotExist:
            raise ValueError(f"Job {job_id} nicht gefunden oder nicht abgeschlossen.")

    # ------------------------------------------------------------------
    # verifiziere
    # ------------------------------------------------------------------
    def verifiziere(self, pdf_bytes: bytes) -> dict:
        """Prueft Signaturen im PDF mit pyhanko."""
        try:
            from pyhanko.sign import validation
            from pyhanko.pdf_utils.reader import PdfFileReader

            r = PdfFileReader(io.BytesIO(pdf_bytes))
            signaturen = []
            for sig in r.embedded_signatures:
                status = validation.validate_pdf_signature(sig)
                signaturen.append({
                    "unterzeichner": sig.signer_reported_dt or "Unbekannt",
                    "zeitstempel": str(sig.self_reported_timestamp),
                    "zertifikat_aussteller": str(
                        sig.signer_cert.issuer if sig.signer_cert else "?"
                    ),
                    "signatur_typ": "FES",
                    "unveraendert": status.coverage.covers_whole_document,
                })
            return {"gueltig": len(signaturen) > 0, "signaturen": signaturen}
        except Exception as exc:
            logger.warning("Verifikation fehlgeschlagen: %s", exc)
            return {"gueltig": False, "signaturen": [], "fehler": str(exc)}

    # ------------------------------------------------------------------
    # signiere_direkt (Komfort)
    # ------------------------------------------------------------------
    def signiere_direkt(self, pdf_bytes: bytes, user, meta: dict) -> bytes:
        job_id = self.starte_signatur_job(pdf_bytes, user, meta)
        return self.hole_signiertes_pdf(job_id)

    # ------------------------------------------------------------------
    # Interne pyhanko-Signatur
    # ------------------------------------------------------------------
    def _signiere_mit_pyhanko(
        self, pdf_bytes: bytes, zert, user, sichtbar: bool, seite: int
    ) -> bytes:
        """Kern-Signatur via pyhanko."""
        import pyhanko.sign.fields as fields
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign import signers
        from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
        from asn1crypto import pem as asn1pem, x509 as asn1x509, keys as asn1keys
        from pyhanko_certvalidator.registry import SimpleCertificateStore

        def _lade_asn1_cert(pem_str):
            """Laedt ein PEM-Zertifikat als asn1crypto.x509.Certificate."""
            pem_bytes = pem_str.encode() if isinstance(pem_str, str) else pem_str
            _, _, der = asn1pem.unarmor(pem_bytes)
            return asn1x509.Certificate.load(der)

        def _lade_asn1_privkey(pem_str):
            """Laedt einen privaten Schluessel als asn1crypto.keys.PrivateKeyInfo.
            pyhanko 0.34 ruft intern signing_key.dump() auf → asn1crypto-Typ benoetigt."""
            pem_bytes = pem_str.encode() if isinstance(pem_str, str) else pem_str
            _, _, der = asn1pem.unarmor(pem_bytes)
            return asn1keys.PrivateKeyInfo.load(der)

        # Privaten Schluessel entschluesseln (PBKDF2+AES-256-GCM via Session-Schluessel)
        from signatur.crypto import privaten_schluessel_aus_session
        privater_schluessel_pem = privaten_schluessel_aus_session(zert)

        if privater_schluessel_pem is None:
            # Fallback: Plaintext-Feld (Migration noch nicht abgeschlossen)
            privater_schluessel_pem = zert.privater_schluessel_pem
            if not privater_schluessel_pem:
                raise ValueError(
                    f"Kein entschluesselter privater Schluessel verfuegbar fuer {user.get_full_name()}. "
                    "Bitte neu einloggen damit der Schluessel entschluesselt werden kann."
                )
            logger.warning(
                "Signatur mit Plaintext-Schluessel fuer %s – Migration ausstehend.",
                user.username,
            )

        # Zertifikat + Schluessel als asn1crypto laden (pyhanko 0.34 Anforderung)
        cert = _lade_asn1_cert(zert.zertifikat_pem)
        privkey = _lade_asn1_privkey(privater_schluessel_pem)

        # Root-CA-Kette laden
        from signatur.models import RootCA
        root = RootCA.objects.first()
        root_cert = _lade_asn1_cert(root.zertifikat_pem)

        # Signer aufbauen
        signer = signers.SimpleSigner(
            signing_cert=cert,
            signing_key=privkey,
            cert_registry=SimpleCertificateStore.from_certs([root_cert]),
        )

        # PDF einlesen
        reader = PdfFileReader(io.BytesIO(pdf_bytes))
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))

        # Anzahl vorhandener Signaturen ermitteln → eindeutigen Feldnamen vergeben
        vorhandene = len(list(reader.embedded_signatures))
        feld_nr = vorhandene + 1
        feld_name = f"Signatur_{feld_nr}"

        # Metadaten
        rolle = ""
        try:
            hr = user.hr_mitarbeiter
            if hr.stelle:
                rolle = hr.stelle.bezeichnung
        except Exception:
            pass

        location = "Intranet – Interne Signatur"
        contact = user.email or ""
        reason = f"Elektronisch signiert von {user.get_full_name()}"
        if rolle:
            reason += f" ({rolle})"

        meta = PdfSignatureMetadata(
            field_name=feld_name,
            reason=reason,
            location=location,
            contact_info=contact,
        )

        # Signaturfeldposition (sichtbarer Stempel)
        # Standard-Modus (mehrere Unterzeichner): Stempel nebeneinander je 170pt breit.
        # Auf der PRIMA-Signaturseite (A4, 595x842pt) liegt der Stempelrahmen bei:
        #   box = (20, 539, 502, 667)
        # Fuer einzelne Signaturen auf der Signaturseite wird der volle Rahmen genutzt.
        sig_field_spec = None
        if sichtbar:
            total_pages = reader.root["/Pages"]["/Count"]
            zielseite = int(total_pages) - 1 if seite < 0 else min(seite, int(total_pages) - 1)

            if feld_nr == 1:
                # Erste Signatur: voller Stempelbereich der PRIMA-Signaturseite
                box = (20, 539, 502, 667)
            else:
                # Weitere Signaturen: nebeneinander im unteren Bereich
                x_start = 20 + (feld_nr - 1) * 162
                x_end   = x_start + 155
                box = (x_start, 539, x_end, 667)

            sig_field_spec = fields.SigFieldSpec(
                sig_field_name=feld_name,
                on_page=zielseite,
                box=box,
            )
            fields.append_signature_field(writer, sig_field_spec)

        # Signieren
        out = io.BytesIO()
        signers.sign_pdf(
            writer,
            meta,
            signer=signer,
            output=out,
        )
        return out.getvalue()
