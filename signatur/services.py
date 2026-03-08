"""
Zentraler Einstiegspunkt fuer alle Signatur-Operationen.

Einzige Import-Stelle fuer Views und andere Apps:

    from signatur.services import get_backend, signiere_pdf

Der konkrete Backend wird per settings.SIGNATUR_BACKEND bestimmt:
  "intern"   → pyhanko + interne CA (Standard, offline)
  "sign_me"  → Bundesdruckerei sign-me (QES, benoetigt Gateway)
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_BACKEND_CACHE = None


def get_backend():
    """
    Gibt den konfigurierten Signatur-Backend zurueck.
    Wird gecacht nach erstem Aufruf.
    """
    global _BACKEND_CACHE
    if _BACKEND_CACHE is not None:
        return _BACKEND_CACHE

    backend_name = getattr(settings, "SIGNATUR_BACKEND", "intern")

    if backend_name == "intern":
        from signatur.backends.intern import InternBackend
        _BACKEND_CACHE = InternBackend()
    elif backend_name == "sign_me":
        from signatur.backends.sign_me import SignMeBackend
        _BACKEND_CACHE = SignMeBackend()
    else:
        raise ValueError(
            f"Unbekannter SIGNATUR_BACKEND: '{backend_name}'. "
            "Erlaubt: 'intern', 'sign_me'"
        )

    logger.info("Signatur-Backend: %s (%s)", backend_name, _BACKEND_CACHE.SIGNATUR_TYP)
    return _BACKEND_CACHE


def signiere_pdf(pdf_bytes: bytes, user, dokument_name: str = "Dokument",
                 sichtbar: bool = True, **kwargs) -> bytes:
    """
    Komfort-Funktion: PDF signieren in einer Zeile.

    Verwendung in Views:
        from signatur.services import signiere_pdf
        signiertes = signiere_pdf(pdf_bytes, request.user, "Zeitgutschrift")

    Args:
        pdf_bytes:      Unsigniertes PDF
        user:           Django-User (Unterzeichner)
        dokument_name:  Name des Dokuments (fuer Protokoll)
        sichtbar:       Sichtbaren Stempel einbetten (Standard: True)
        **kwargs:       Weitere Metadaten (content_type, object_id, seite)

    Returns:
        Signiertes PDF als bytes
    """
    backend = get_backend()
    meta = {
        "dokument_name": dokument_name,
        "sichtbar": sichtbar,
        **kwargs,
    }
    return backend.signiere_direkt(pdf_bytes, user, meta)
