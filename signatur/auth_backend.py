"""
Signatur-Auth-Backend: Erbt von ModelBackend und ergaenzt die Schluesselverwaltung.

Beim erfolgreichen Login:
  1. PBKDF2-Schluessel aus Klartext-Passwort ableiten
  2. Abgeleiteten Schluessel in Session speichern
  3. Falls privater Schluessel noch Plaintext: automatisch verschluesseln (Migration)

Wird in settings.AUTHENTICATION_BACKENDS STATT ModelBackend eingetragen.
"""
import logging

from django.contrib.auth.backends import ModelBackend

from .crypto import (
    SESSION_KEY,
    leite_schluessel_ab,
    verschluessele_privaten_schluessel,
)

logger = logging.getLogger(__name__)


class SignaturAuthBackend(ModelBackend):
    """ModelBackend + automatische Signatur-Schluesselverwaltung beim Login."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(
            request, username=username, password=password, **kwargs
        )

        if not user or not request or not password:
            return user

        try:
            # Passwort-Hash fuer Signal-Erkennung cachen
            from signatur.signals import _passwort_hash_cache
            _passwort_hash_cache[user.pk] = user.password

            self._verarbeite_login(request, user, password)
        except Exception as exc:
            # Fehler hier duerfen den Login NICHT blockieren
            logger.warning(
                "Signatur-Schluesselverwaltung beim Login fehlgeschlagen (User %s): %s",
                getattr(user, "username", "?"),
                exc,
            )

        return user

    # ------------------------------------------------------------------

    def _verarbeite_login(self, request, user, password: str) -> None:
        """Leitet Schluessel ab, speichert ihn in Session, migriert Plaintext-Keys."""
        from .models import MitarbeiterZertifikat

        zert = MitarbeiterZertifikat.objects.filter(user=user, status="aktiv").first()
        if not zert:
            return

        if zert.schluessel_salt:
            # Schluessel bereits verschluesselt – nur Session-Schluessel setzen
            salt = bytes.fromhex(zert.schluessel_salt)
            dk = leite_schluessel_ab(password, salt)
            request.session[SESSION_KEY] = dk.hex()
            logger.debug("Session-Schluessel fuer %s gesetzt.", user.username)
        else:
            # Noch Plaintext – automatisch verschluesseln (Migration)
            self._migriere_plaintext_key(request, user, zert, password)

    def _migriere_plaintext_key(self, request, user, zert, password: str) -> None:
        """Verschluesselt einen noch im Plaintext gespeicherten privaten Schluessel."""
        if not zert.privater_schluessel_pem:
            logger.warning(
                "Migration uebersprungen: kein privater_schluessel_pem bei User %s.",
                user.username,
            )
            return

        verschluesselt, salt, nonce = verschluessele_privaten_schluessel(
            zert.privater_schluessel_pem, password
        )

        zert.privater_schluessel_verschluesselt = verschluesselt
        zert.schluessel_salt = salt.hex()
        zert.schluessel_nonce = nonce.hex()
        # Plaintext-Feld leeren NACHDEM verschluesseltes Feld gesetzt ist
        zert.privater_schluessel_pem = ""
        zert.save(update_fields=[
            "privater_schluessel_verschluesselt",
            "schluessel_salt",
            "schluessel_nonce",
            "privater_schluessel_pem",
        ])

        # Session-Schluessel setzen
        dk = leite_schluessel_ab(password, salt)
        request.session[SESSION_KEY] = dk.hex()

        logger.info(
            "Privater Schluessel von %s automatisch verschluesselt (PBKDF2+AES-256-GCM).",
            user.username,
        )
