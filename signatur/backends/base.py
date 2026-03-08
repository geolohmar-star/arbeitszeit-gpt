"""
Abstrakte Basisklasse fuer alle Signatur-Backends.

Jedes Backend (intern/pyhanko, sign-me, Gateway) implementiert
exakt diese Schnittstelle. Django-Code spricht nur mit dieser Klasse –
der konkrete Backend wird per settings.SIGNATUR_BACKEND gewechselt.

API angelehnt an die Bundesdruckerei sign-me REST-API:
  POST /auth          → authentifiziere()
  POST /sign          → starte_signatur_job()
  GET  /sign/{id}     → hole_status()
  GET  /sign/{id}/dl  → hole_signiertes_pdf()
  POST /verify        → verifiziere()
"""


class SignaturBackend:
    """Abstrakte Basisklasse – alle Backends erben hiervon."""

    BACKEND_NAME = "abstract"
    SIGNATUR_TYP = "FES"

    def authentifiziere(self, user) -> dict:
        """
        Prueft ob der User ein gueltiges Zertifikat hat und gibt
        einen Auth-Kontext zurueck.

        sign-me aequivalent: OAuth2 Token-Request

        Returns:
            {
                "token": str,
                "user_id": str,
                "zertifikat_sn": str,
                "gueltig_bis": str,
            }
        """
        raise NotImplementedError

    def starte_signatur_job(
        self, pdf_bytes: bytes, user, meta: dict
    ) -> str:
        """
        Startet einen Signaturauftrag und gibt die Job-ID zurueck.

        sign-me aequivalent: POST /api/v1/sign

        Args:
            pdf_bytes:  Unsigniertes PDF als Bytes
            user:       Django-User (Unterzeichner)
            meta:       Zusaetzliche Infos {
                            "dokument_name": str,
                            "content_type": str,   (optional)
                            "object_id": int,       (optional)
                            "sichtbar": bool,       (Stempel einbetten)
                            "seite": int,           (Seite fuer Stempel, 0=letzte)
                        }

        Returns:
            job_id (str)
        """
        raise NotImplementedError

    def hole_status(self, job_id: str) -> dict:
        """
        Fragt den Status eines laufenden Signaturauftrags ab.

        sign-me aequivalent: GET /api/v1/sign/{job_id}

        Returns:
            {
                "status": "pending" | "completed" | "failed",
                "fortschritt": int (0-100),
                "fehler": str | None,
            }
        """
        raise NotImplementedError

    def hole_signiertes_pdf(self, job_id: str) -> bytes:
        """
        Liefert das fertig signierte PDF.

        sign-me aequivalent: GET /api/v1/sign/{job_id}/download

        Returns:
            Signiertes PDF als Bytes
        """
        raise NotImplementedError

    def verifiziere(self, pdf_bytes: bytes) -> dict:
        """
        Prueft alle Signaturen in einem PDF.

        sign-me aequivalent: POST /api/v1/verify

        Returns:
            {
                "gueltig": bool,
                "signaturen": [
                    {
                        "unterzeichner": str,
                        "zeitstempel": str,
                        "zertifikat_aussteller": str,
                        "signatur_typ": "FES" | "QES",
                        "unveraendert": bool,
                    }
                ]
            }
        """
        raise NotImplementedError

    def signiere_direkt(self, pdf_bytes: bytes, user, meta: dict) -> bytes:
        """
        Komfort-Methode: Job starten + sofort Ergebnis holen.
        Fuer synchrone Verwendung in Views.

        Intern immer verfuegbar. Bei sign-me nur wenn Job sofort
        abgeschlossen ist (normalerweise nach wenigen Sekunden).
        """
        job_id = self.starte_signatur_job(pdf_bytes, user, meta)
        status = self.hole_status(job_id)
        if status["status"] != "completed":
            raise RuntimeError(
                f"Signatur-Job {job_id} nicht sofort abgeschlossen: {status}"
            )
        return self.hole_signiertes_pdf(job_id)
