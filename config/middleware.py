class CSPMiddleware:
    """Content Security Policy Header fuer alle Antworten.

    Verhindert XSS-Angriffe durch Einschraenkung erlaubter Quellen.
    BSI IT-Grundschutz APP.3.1 – Webanwendungen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "  # Bootstrap inline styles
            "img-src 'self' data:; "               # data: fuer SVG/Charts
            "font-src 'self'; "
            "frame-ancestors 'none';"              # kein iFrame-Embedding
        )
        return response
