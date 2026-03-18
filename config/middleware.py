import re

_ONLYOFFICE_EDITOR_PFAD = re.compile(
    r"^/(dms|korrespondenz)/\d+/(versionen/\d+/)?onlyoffice/$"
)


class CSPMiddleware:
    """Content Security Policy Header fuer alle Antworten.

    Verhindert XSS-Angriffe durch Einschraenkung erlaubter Quellen.
    BSI IT-Grundschutz APP.3.1 – Webanwendungen.

    Ausnahme: OnlyOffice-Editor-Seite benoetigt erweiterte Quellen
    damit der Document Server JS laden und kommunizieren kann.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if _ONLYOFFICE_EDITOR_PFAD.match(request.path):
            # OnlyOffice-Editor: erlaubt Skripte + Verbindungen vom Document Server
            from django.conf import settings
            oo_url = getattr(settings, "ONLYOFFICE_URL", "").rstrip("/")
            response["Content-Security-Policy"] = (
                f"default-src 'self' {oo_url}; "
                f"script-src 'self' {oo_url} 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                f"img-src 'self' data: {oo_url}; "
                f"font-src 'self' {oo_url}; "
                f"connect-src 'self' {oo_url} ws://localhost:8012 wss://localhost:8012; "
                f"frame-src 'self' {oo_url}; "
                "frame-ancestors 'self';"
            )
        else:
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "  # Bootstrap inline styles
                "img-src 'self' data:; "               # data: fuer SVG/Charts
                "font-src 'self'; "
                "frame-ancestors 'none';"              # kein iFrame-Embedding
            )
        return response
