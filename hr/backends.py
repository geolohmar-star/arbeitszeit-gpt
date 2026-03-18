"""
Stellen-Auth-Backend: Ermoeglicht Login mit dem Stellen-Kuerzel (z.B. "al_hd")
statt des persoenlichen Django-Usernamens.

Ablauf:
  1. Pruefen ob der eingegebene Username einem Stelle.kuerzel entspricht
  2. Falls ja: den echten Django-Username des aktuellen Stellen-Inhabers ermitteln
  3. Authentifizierung mit dem echten Username fortsetzen (inkl. Signatur-Logik)
  4. Falls kein Stellen-Kuerzel gefunden: normaler Username-Login (Fallback)
"""
import logging

from signatur.auth_backend import SignaturAuthBackend

logger = logging.getLogger(__name__)


class StelleAuthBackend(SignaturAuthBackend):
    """Erweitert SignaturAuthBackend um Stellen-Kuerzel-Login."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        aufgeloester_username = self._stelle_kuerzel_aufloesen(username)
        return super().authenticate(
            request,
            username=aufgeloester_username,
            password=password,
            **kwargs,
        )

    def _stelle_kuerzel_aufloesen(self, username: str | None) -> str | None:
        """Gibt den Django-Username des Stellen-Inhabers zurueck, falls username
        ein Stellen-Kuerzel ist. Sonst unveraendert zurueck."""
        if not username:
            return username
        try:
            from .models import Stelle
            stelle = Stelle.objects.select_related("hrmitarbeiter__user").get(
                kuerzel=username
            )
            inhaber = getattr(stelle, "hrmitarbeiter", None)
            if inhaber and inhaber.user_id:
                logger.debug(
                    "Stellen-Login: Kuerzel '%s' -> User '%s'",
                    username,
                    inhaber.user.username,
                )
                return inhaber.user.username
        except Exception:
            pass
        # Kein Stellen-Kuerzel gefunden → normaler Username
        return username
