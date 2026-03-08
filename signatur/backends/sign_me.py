"""
sign-me Backend – Bundesdruckerei Qualifizierte Signatur (QES).

Dieses Modul implementiert die sign-me REST-API der Bundesdruckerei.
Im Intranet-Betrieb wird es ueber einen Gateway-Server angebunden:

  Django (Intranet)  →  Gateway-Server (DMZ)  →  api.sign-me.de (Internet)

Konfiguration in settings.py:
  SIGNATUR_BACKEND     = "sign_me"
  SIGNATUR_SIGN_ME_URL = "https://api.sign-me.de"          # Produktion
                       = "http://gateway.intern:8080"        # ueber Gateway
  SIGNATUR_SIGN_ME_KEY = "<API-Key vom Bundesdruckerei-Vertrag>"

Fuer den echten Produktionsbetrieb:
  1. Vertrag mit Bundesdruckerei / sign-me abschliessen
  2. API-Key erhalten
  3. Mitarbeiter einmalig per Video-Ident verifizieren lassen
  4. SIGNATUR_SIGN_ME_URL und SIGNATUR_SIGN_ME_KEY in .env setzen
  5. SIGNATUR_BACKEND = "sign_me" in settings.py
  → Kein weiterer Code-Aenderung noetig.

sign-me API-Dokumentation:
  https://www.bundesdruckerei.de/de/sign-me
"""
import logging
import uuid

logger = logging.getLogger(__name__)


class SignMeBackend:
    """
    QES-Backend via Bundesdruckerei sign-me API.

    Dieselbe Schnittstelle wie InternBackend – Django-Code unveraendert.
    """

    BACKEND_NAME = "sign_me"
    SIGNATUR_TYP = "QES"

    def __init__(self):
        from django.conf import settings
        self.base_url = getattr(
            settings, "SIGNATUR_SIGN_ME_URL", "https://api.sign-me.de"
        )
        self.api_key = getattr(settings, "SIGNATUR_SIGN_ME_KEY", "")
        self.timeout = getattr(settings, "SIGNATUR_SIGN_ME_TIMEOUT", 30)

    def _headers(self, token=None) -> dict:
        h = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    # ------------------------------------------------------------------
    # authentifiziere
    # ------------------------------------------------------------------
    def authentifiziere(self, user) -> dict:
        """
        OAuth2-Token-Request an sign-me.

        sign-me API: POST /oauth/token
        Payload: { grant_type, client_id, client_secret, scope }

        Im Produktionsbetrieb wird hier die Benutzer-Identitaet
        per vorregistriertem sign-me-Konto bestaetigt.
        """
        import requests

        # Im Produktionsbetrieb: user.email muss ein registriertes
        # sign-me-Konto sein (nach Video-Ident Verifizierung).
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "scope": "sign",
            "subject": user.email,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/oauth/token",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "token": data["access_token"],
                "user_id": user.email,
                "zertifikat_sn": data.get("certificate_serial", "QES"),
                "gueltig_bis": data.get("expires_in", "3600") + "s",
            }
        except Exception as exc:
            logger.error("sign-me Auth fehlgeschlagen: %s", exc)
            raise RuntimeError(f"sign-me nicht erreichbar: {exc}") from exc

    # ------------------------------------------------------------------
    # starte_signatur_job
    # ------------------------------------------------------------------
    def starte_signatur_job(self, pdf_bytes: bytes, user, meta: dict) -> str:
        """
        Startet QES-Signaturauftrag bei sign-me.

        sign-me API: POST /api/v1/sign
        Payload:
          {
            "document": "<base64-PDF>",
            "signatureType": "PAdES_BASELINE_LTA",
            "conformanceLevel": "BASELINE_LTA",
            "signerIdentity": { "email": "...", "name": "..." },
            "visibleSignature": { "page": -1, "x": 30, "y": 30, ... }
          }
        """
        import base64
        import requests
        from signatur.models import SignaturJob

        auth = self.authentifiziere(user)
        token = auth["token"]

        job_id = f"SME-{uuid.uuid4().hex[:12].upper()}"

        SignaturJob.objects.create(
            job_id=job_id,
            backend="sign_me",
            status="pending",
            erstellt_von=user,
            dokument_name=meta.get("dokument_name", "Dokument"),
            content_type=meta.get("content_type", ""),
            object_id=meta.get("object_id"),
        )

        payload = {
            "document": base64.b64encode(pdf_bytes).decode(),
            "signatureType": "PAdES_BASELINE_LTA",
            "conformanceLevel": "BASELINE_LTA",
            "signerIdentity": {
                "email": user.email,
                "name": user.get_full_name(),
            },
            "clientTransactionId": job_id,
        }

        if meta.get("sichtbar", True):
            payload["visibleSignature"] = {
                "page": meta.get("seite", -1),
                "x": 30, "y": 30, "width": 250, "height": 60,
                "text": f"Signiert von {user.get_full_name()}",
            }

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/sign",
                json=payload,
                headers=self._headers(token),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # sign-me gibt eigene Job-ID zurueck – wir speichern sie
            remote_id = data.get("transactionId", job_id)
            SignaturJob.objects.filter(job_id=job_id).update(
                fehler_meldung=f"remote_id:{remote_id}"
            )
        except Exception as exc:
            SignaturJob.objects.filter(job_id=job_id).update(
                status="failed", fehler_meldung=str(exc)
            )
            raise RuntimeError(f"sign-me Signatur fehlgeschlagen: {exc}") from exc

        return job_id

    # ------------------------------------------------------------------
    # hole_status
    # ------------------------------------------------------------------
    def hole_status(self, job_id: str) -> dict:
        """sign-me API: GET /api/v1/sign/{transactionId}"""
        import requests
        from signatur.models import SignaturJob

        try:
            job = SignaturJob.objects.get(job_id=job_id)
            remote_id = job.fehler_meldung.replace("remote_id:", "") if "remote_id:" in job.fehler_meldung else job_id
        except SignaturJob.DoesNotExist:
            return {"status": "failed", "fortschritt": 0, "fehler": "Job nicht gefunden"}

        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/sign/{remote_id}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            sme_status = data.get("status", "PENDING")
            status_map = {"PENDING": "pending", "COMPLETED": "completed", "FAILED": "failed"}
            return {
                "status": status_map.get(sme_status, "pending"),
                "fortschritt": data.get("progress", 50),
                "fehler": data.get("errorMessage"),
            }
        except Exception as exc:
            return {"status": "failed", "fortschritt": 0, "fehler": str(exc)}

    # ------------------------------------------------------------------
    # hole_signiertes_pdf
    # ------------------------------------------------------------------
    def hole_signiertes_pdf(self, job_id: str) -> bytes:
        """sign-me API: GET /api/v1/sign/{transactionId}/download"""
        import base64
        import requests
        from signatur.models import SignaturJob

        job = SignaturJob.objects.get(job_id=job_id)
        remote_id = job.fehler_meldung.replace("remote_id:", "") if "remote_id:" in job.fehler_meldung else job_id

        resp = requests.get(
            f"{self.base_url}/api/v1/sign/{remote_id}/download",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["signedDocument"])

    # ------------------------------------------------------------------
    # verifiziere
    # ------------------------------------------------------------------
    def verifiziere(self, pdf_bytes: bytes) -> dict:
        """sign-me API: POST /api/v1/verify"""
        import base64
        import requests

        payload = {"document": base64.b64encode(pdf_bytes).decode()}
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/verify",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "gueltig": data.get("valid", False),
                "signaturen": [
                    {
                        "unterzeichner": s.get("signerName"),
                        "zeitstempel": s.get("signingTime"),
                        "zertifikat_aussteller": s.get("issuer"),
                        "signatur_typ": "QES",
                        "unveraendert": s.get("integrityOk", False),
                    }
                    for s in data.get("signatures", [])
                ],
            }
        except Exception as exc:
            return {"gueltig": False, "signaturen": [], "fehler": str(exc)}

    # ------------------------------------------------------------------
    # signiere_direkt
    # ------------------------------------------------------------------
    def signiere_direkt(self, pdf_bytes: bytes, user, meta: dict) -> bytes:
        """Komfort: Job starten + auf Abschluss warten + PDF holen."""
        import time
        job_id = self.starte_signatur_job(pdf_bytes, user, meta)
        for _ in range(30):
            status = self.hole_status(job_id)
            if status["status"] == "completed":
                return self.hole_signiertes_pdf(job_id)
            if status["status"] == "failed":
                raise RuntimeError(f"sign-me Job fehlgeschlagen: {status['fehler']}")
            time.sleep(1)
        raise TimeoutError(f"sign-me Job {job_id} Timeout nach 30s")
