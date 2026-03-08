"""Verschluesselungs-Service fuer sensible Dokumente.

Verwendet Fernet (AES-128-CBC + HMAC-SHA256) aus der cryptography-Bibliothek.
Der Schluessel wird aus der Umgebungsvariable DOKUMENT_VERSCHLUESSEL_KEY gelesen.

Schluessel generieren (einmalig, dann in .env eintragen):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Erstellt eine Fernet-Instanz mit dem konfigurierten Schluessel."""
    key = getattr(settings, "DOKUMENT_VERSCHLUESSEL_KEY", "")
    if not key:
        raise ValueError(
            "DOKUMENT_VERSCHLUESSEL_KEY ist nicht in den Einstellungen konfiguriert. "
            "Bitte Schluessel generieren und in .env eintragen."
        )
    raw = key.encode() if isinstance(key, str) else key
    return Fernet(raw)


def verschluessel_dokument(inhalt: bytes) -> bytes:
    """Verschluesselt Dokument-Bytes mit Fernet (AES-128-CBC + HMAC).

    Args:
        inhalt: Rohe Datei-Bytes

    Returns:
        Verschluesselte Bytes (sicher in BinaryField speicherbar)

    Raises:
        ValueError: Wenn DOKUMENT_VERSCHLUESSEL_KEY fehlt
    """
    return _get_fernet().encrypt(inhalt)


def entschluessel_dokument(inhalt_verschluesselt: bytes) -> bytes:
    """Entschluesselt verschluesselte Dokument-Bytes.

    Args:
        inhalt_verschluesselt: Aus der Datenbank gelesene verschluesselte Bytes

    Returns:
        Originale Datei-Bytes

    Raises:
        ValueError: Wenn DOKUMENT_VERSCHLUESSEL_KEY fehlt
        InvalidToken: Wenn Daten manipuliert wurden oder Schluessel falsch ist
    """
    try:
        return _get_fernet().decrypt(bytes(inhalt_verschluesselt))
    except InvalidToken as exc:
        logger.error("Entschluesselung fehlgeschlagen (InvalidToken): %s", exc)
        raise
