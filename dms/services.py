"""
DMS-Verschluesselungs-Service.

Klasse 2 (sensibel): AES-256-GCM mit serverseitigem Schluessel (DMS_VERSCHLUESSEL_KEY).
Klasse 1 (offen):    Kein Schluessel – Rohdaten werden direkt gespeichert.

Schluessel generieren (einmalig):
    python -c "import os; print(os.urandom(32).hex())"
"""
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

logger = logging.getLogger(__name__)

NONCE_BYTES = 12  # AES-GCM Standard-Nonce


def _get_aes_schluessel() -> bytes:
    """Liest den DMS-Hauptschluessel aus den Einstellungen."""
    key_hex = getattr(settings, "DMS_VERSCHLUESSEL_KEY", "")
    if not key_hex:
        raise ValueError(
            "DMS_VERSCHLUESSEL_KEY ist nicht konfiguriert. "
            "Schluessel generieren: python -c \"import os; print(os.urandom(32).hex())\""
        )
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise ValueError("DMS_VERSCHLUESSEL_KEY muss 32 Bytes (64 Hex-Zeichen) lang sein.")
    return key


def verschluessel_inhalt(inhalt: bytes) -> tuple[bytes, str]:
    """Verschluesselt Dokumentinhalt mit AES-256-GCM.

    Returns:
        (verschluesselte_bytes, nonce_hex)
        Beide Werte in der DB speichern.
    """
    aes_schluessel = _get_aes_schluessel()
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(aes_schluessel)
    verschluesselt = aesgcm.encrypt(nonce, inhalt, None)
    return verschluesselt, nonce.hex()


def entschluessel_inhalt(verschluesselt: bytes, nonce_hex: str) -> bytes:
    """Entschluesselt AES-256-GCM verschluesselten Dokumentinhalt.

    Args:
        verschluesselt: Verschluesselte Bytes aus der DB
        nonce_hex: Hex-Nonce aus der DB

    Returns:
        Originale Datei-Bytes

    Raises:
        ValueError: Schluessel fehlt oder falsche Laenge
        cryptography.exceptions.InvalidTag: Daten manipuliert oder Schluessel falsch
    """
    aes_schluessel = _get_aes_schluessel()
    nonce = bytes.fromhex(nonce_hex)
    aesgcm = AESGCM(aes_schluessel)
    return aesgcm.decrypt(nonce, bytes(verschluesselt), None)


def speichere_dokument(dokument, inhalt_bytes: bytes) -> None:
    """Speichert Dokumentinhalt – verschluesselt (Klasse 2) oder roh (Klasse 1).

    Befuellt die richtigen Felder des Dokument-Objekts (ohne .save() aufzurufen).
    """
    if dokument.klasse == "sensibel":
        verschluesselt, nonce_hex = verschluessel_inhalt(inhalt_bytes)
        dokument.inhalt_verschluesselt = verschluesselt
        dokument.verschluessel_nonce = nonce_hex
        dokument.inhalt_roh = None
    else:
        dokument.inhalt_roh = inhalt_bytes
        dokument.inhalt_verschluesselt = None
        dokument.verschluessel_nonce = ""


def lade_dokument(dokument) -> bytes:
    """Laedt und (falls noetig) entschluesselt den Dokumentinhalt.

    Returns:
        Originale Datei-Bytes

    Raises:
        ValueError: Dokument hat keinen Inhalt
    """
    if dokument.klasse == "sensibel":
        if not dokument.inhalt_verschluesselt or not dokument.verschluessel_nonce:
            raise ValueError(f"Dokument {dokument.pk} hat keinen verschluesselten Inhalt.")
        return entschluessel_inhalt(
            bytes(dokument.inhalt_verschluesselt),
            dokument.verschluessel_nonce,
        )
    else:
        if not dokument.inhalt_roh:
            raise ValueError(f"Dokument {dokument.pk} hat keinen Inhalt.")
        return bytes(dokument.inhalt_roh)
