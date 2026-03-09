"""
Middleware: Setzt den Session-Schluessels fuer den aktuellen Request-Thread.

Liest den abgeleiteten Schluessel aus der Django-Session und schreibt ihn
in den Thread-Local Speicher (signatur.crypto). Nach dem Request wird
der Thread-Local automatisch geleert.

Reihenfolge in settings.MIDDLEWARE:
    Nach SessionMiddleware und AuthenticationMiddleware einfuegen.
"""
import logging

from .crypto import SESSION_KEY, clear_session_schluessel, set_session_schluessel

logger = logging.getLogger(__name__)


class SignaturKeyMiddleware:
    """Stellt den Signatur-Entschluesselungsschluessel fuer die Dauer eines Requests bereit."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Session-Schluessel in Thread-Local schreiben (nur wenn vorhanden)
        dk_hex = None
        try:
            if hasattr(request, "session"):
                dk_hex = request.session.get(SESSION_KEY)
        except Exception:
            pass

        if dk_hex:
            set_session_schluessel(dk_hex)

        try:
            response = self.get_response(request)
        finally:
            # Immer loeschen – auch bei Exceptions
            clear_session_schluessel()

        return response
