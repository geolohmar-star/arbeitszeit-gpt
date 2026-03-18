"""Context Processor fuer die Matrix-Integration."""

from django.conf import settings


def matrix_kontext(request):
    """Stellt Matrix-Konfiguration fuer alle Templates bereit.

    Liefert matrix_konfiguriert=True und den oeffentlichen Homeserver-URL
    wenn MATRIX_HOMESERVER_URL in den Settings gesetzt ist.
    """
    homeserver = getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    server_name = getattr(settings, "MATRIX_SERVER_NAME", "")

    if not homeserver or not request.user.is_authenticated:
        return {
            "matrix_konfiguriert": False,
            "matrix_homeserver_url": "",
            "matrix_server_name": "",
            "matrix_element_web_url": "",
        }

    # Element-Web laeuft standardmaessig auf dem Client-Rechner oder
    # alternativ app.element.io – hier nutzen wir den konfigurierten Wert
    element_url = getattr(settings, "ELEMENT_WEB_URL", "https://app.element.io")

    return {
        "matrix_konfiguriert": True,
        "matrix_homeserver_url": homeserver,
        "matrix_server_name": server_name,
        "matrix_element_web_url": element_url,
    }
