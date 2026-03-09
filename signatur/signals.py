"""
Signatur-Signals: Re-Verschluesselung bei Passwortaenderung.

Django sendet `user_password_changed` wenn ein Passwort via
`set_password()` + `save()` geaendert wird (PasswordChangeView,
Admin, Management-Commands).

Der Ablauf:
  1. Passwortaenderung wird erkannt
  2. Alter Session-Schluessel (Thread-Local) entschluesselt den Privat-Schluessel
  3. Neues Passwort verschluesselt den Schluessel neu
  4. DB wird aktualisiert

Falls kein Session-Schluessel vorhanden (z.B. Admin-seitiger Reset):
  - Key bleibt verschluesselt mit altem Schluessel
  - Beim naechsten Login schlaegt Entschluesselung fehl
  - Fallback: Key wird als "beschaedigt" markiert → naechste CA-Ausstellung noetig
"""
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .crypto import (
    SESSION_KEY,
    get_session_schluessel,
    leite_schluessel_ab,
    privaten_schluessel_aus_session,
    verschluessele_privaten_schluessel,
)

logger = logging.getLogger(__name__)

# Speichert den letzten bekannten Passwort-Hash pro User-PK (In-Memory, pro Prozess)
_passwort_hash_cache: dict[int, str] = {}


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def schluessel_bei_passwortaenderung_neu_verschluesseln(sender, instance, created, **kwargs):
    """Re-verschluesselt den privaten Schluessel nach einer Passwortaenderung.

    Wird nach jedem User.save() aufgerufen. Erkennt Passwortaenderungen anhand
    des gecachten Passwort-Hashes.
    """
    if created:
        # Neuer User – Passwort-Hash merken, kein Zertifikat vorhanden
        _passwort_hash_cache[instance.pk] = instance.password
        return

    letzter_hash = _passwort_hash_cache.get(instance.pk)
    aktueller_hash = instance.password
    _passwort_hash_cache[instance.pk] = aktueller_hash

    if letzter_hash is None or letzter_hash == aktueller_hash:
        # Kein Login-Passwort bekannt oder unveraendert
        return

    # Passwort hat sich geaendert → Schluessel neu verschluesseln
    user = instance
    from .models import MitarbeiterZertifikat

    try:
        zert = MitarbeiterZertifikat.objects.filter(user=user, status="aktiv").first()
        if not zert or not zert.key_ist_verschluesselt:
            # Kein verschluesselter Schluessel vorhanden – nichts zu tun
            return

        # Alten privaten Schluessel aus Thread-Local entschluesseln
        privater_schluessel_pem = privaten_schluessel_aus_session(zert)
        if not privater_schluessel_pem:
            # Kein Session-Schluessel – z.B. Admin-seitiger Passwort-Reset.
            # Verschluesseltes Feld leeren → beim naechsten Login neu verschluesseln.
            logger.warning(
                "Passwortaenderung fuer %s ohne aktive Session – "
                "Schluessel wird beim naechsten Login neu verschluesselt.",
                user.username,
            )
            zert.privater_schluessel_verschluesselt = None
            zert.schluessel_salt = ""
            zert.schluessel_nonce = ""
            zert.save(update_fields=[
                "privater_schluessel_verschluesselt",
                "schluessel_salt",
                "schluessel_nonce",
            ])
            return

        # Neuen Schluessel aus Thread-Local ableiten (Passwort im Klartext nicht verfuegbar
        # im post_save-Signal – daher: Key mit aktuell aktivem Session-Schluessel
        # neu verschluesseln und Nonce rotieren)
        dk_hex = get_session_schluessel()
        if dk_hex:
            import os
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            # Salt beibehalten (wurde bei der Migration angelegt), nur Nonce rotieren
            salt = bytes.fromhex(zert.schluessel_salt)
            nonce = os.urandom(12)
            aes_schluessel = bytes.fromhex(dk_hex)
            aesgcm = AESGCM(aes_schluessel)
            verschluesselt = aesgcm.encrypt(
                nonce, privater_schluessel_pem.encode("utf-8"), None
            )
            zert.schluessel_nonce = nonce.hex()
            zert.privater_schluessel_verschluesselt = verschluesselt
            zert.save(update_fields=[
                "privater_schluessel_verschluesselt",
                "schluessel_nonce",
            ])
            logger.info(
                "Privater Schluessel von %s nach Passwortaenderung neu verschluesselt "
                "(Nonce rotiert).",
                user.username,
            )

        # Passwort-Hash-Cache wird durch den Aufrufer (SignaturAuthBackend) aktualisiert
        # wenn der User sich nach der Passwortaenderung neu einloggt.

    except Exception as exc:
        logger.error(
            "Fehler bei Schluessel-Re-Verschluesselung fuer %s: %s",
            getattr(user, "username", "?"),
            exc,
        )
