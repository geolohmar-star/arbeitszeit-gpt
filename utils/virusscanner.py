"""Virusscanner-Integration fuer Datei-Uploads.

Verbindet sich mit einem ClamAV-Daemon im Netzwerk (clamd).
Laeuft die Verbindung fehl oder ist kein Server konfiguriert,
wird der Upload NICHT blockiert – nur geloggt (Fallback-Modus).

Konfiguration via Umgebungsvariablen (siehe .env):
    CLAMAV_HOST  – IP oder Hostname des Scanner-Servers (leer = deaktiviert)
    CLAMAV_PORT  – Port des clamd-Dienstes (Standard: 3310)
    CLAMAV_TIMEOUT – Verbindungs-Timeout in Sekunden (Standard: 15)
    CLAMAV_BLOCKIERE_BEI_FEHLER – "True" = Upload ablehnen wenn Scanner
                                   nicht erreichbar (Standard: False)
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class ScanErgebnis:
    """Ergebnis eines Virenscans."""

    def __init__(self, sauber: bool, bedrohung: str = "", fehler: str = ""):
        self.sauber = sauber          # True = keine Bedrohung gefunden
        self.bedrohung = bedrohung    # Name der Bedrohung falls gefunden
        self.fehler = fehler          # Fehlermeldung falls Scanner nicht erreichbar
        self.scanner_aktiv = True     # False = Scanner nicht konfiguriert/erreichbar

    def __str__(self):
        if not self.scanner_aktiv:
            return "Scanner nicht aktiv (Fallback)"
        if self.sauber:
            return "Sauber"
        return f"Bedrohung gefunden: {self.bedrohung}"


def _get_clamav_config():
    """Liest ClamAV-Konfiguration aus settings/Umgebungsvariablen."""
    host = getattr(settings, "CLAMAV_HOST", "")
    port = int(getattr(settings, "CLAMAV_PORT", 3310))
    timeout = int(getattr(settings, "CLAMAV_TIMEOUT", 15))
    blockiere_bei_fehler = getattr(settings, "CLAMAV_BLOCKIERE_BEI_FEHLER", False)
    return host, port, timeout, blockiere_bei_fehler


def scan_datei(datei) -> ScanErgebnis:
    """Scannt eine hochgeladene Datei auf Viren.

    Args:
        datei: Django InMemoryUploadedFile oder aehnliches File-Objekt

    Returns:
        ScanErgebnis mit Attributen:
            .sauber          – True wenn unbedenklich
            .bedrohung       – Name der Bedrohung (leer wenn sauber)
            .fehler          – Fehlermeldung (leer wenn OK)
            .scanner_aktiv   – False wenn Scanner nicht konfiguriert/erreichbar

    Beispiel:
        ergebnis = scan_datei(request.FILES["beleg"])
        if not ergebnis.sauber:
            # Ablehnen
    """
    host, port, timeout, blockiere_bei_fehler = _get_clamav_config()

    # Scanner nicht konfiguriert → Fallback
    if not host:
        logger.debug(
            "Virusscanner nicht konfiguriert (CLAMAV_HOST leer). "
            "Upload wird ohne Scan zugelassen."
        )
        ergebnis = ScanErgebnis(sauber=True)
        ergebnis.scanner_aktiv = False
        return ergebnis

    # pyclamd nur importieren wenn Scanner konfiguriert ist
    try:
        import pyclamd
    except ImportError:
        logger.warning(
            "pyclamd nicht installiert. Bitte 'pip install pyclamd' ausfuehren. "
            "Upload wird ohne Scan zugelassen."
        )
        ergebnis = ScanErgebnis(sauber=True, fehler="pyclamd nicht installiert")
        ergebnis.scanner_aktiv = False
        return ergebnis

    # Verbindung zum ClamAV-Server herstellen
    try:
        cd = pyclamd.ClamdNetworkSocket(host=host, port=port, timeout=timeout)
        cd.ping()
    except Exception as e:
        logger.error(
            "ClamAV-Server nicht erreichbar (%s:%s): %s. "
            "Upload wird %s.",
            host,
            port,
            e,
            "abgelehnt" if blockiere_bei_fehler else "ohne Scan zugelassen",
        )
        ergebnis = ScanErgebnis(
            sauber=not blockiere_bei_fehler,
            fehler=f"Scanner nicht erreichbar: {e}",
        )
        ergebnis.scanner_aktiv = False
        return ergebnis

    # Datei scannen
    try:
        datei.seek(0)
        inhalt = datei.read()
        datei.seek(0)  # Zeiger zuruecksetzen fuer spaeteres Speichern

        result = cd.scan_stream(inhalt)

        if result is None:
            # Sauber
            logger.info("Virusscanner: '%s' – sauber.", datei.name)
            return ScanErgebnis(sauber=True)
        else:
            # Bedrohung gefunden: result = {'stream': ('FOUND', 'Virus.Name')}
            bedrohung = list(result.values())[0][1] if result else "Unbekannt"
            logger.warning(
                "Virusscanner: BEDROHUNG in '%s' gefunden: %s",
                datei.name,
                bedrohung,
            )
            return ScanErgebnis(sauber=False, bedrohung=bedrohung)

    except Exception as e:
        logger.error("Fehler beim Scannen von '%s': %s", datei.name, e)
        ergebnis = ScanErgebnis(
            sauber=not blockiere_bei_fehler,
            fehler=f"Scan-Fehler: {e}",
        )
        ergebnis.scanner_aktiv = False
        return ergebnis


def scan_mehrere_dateien(dateien) -> tuple[bool, list[ScanErgebnis]]:
    """Scannt mehrere Dateien. Gibt (alle_sauber, ergebnisse) zurueck."""
    ergebnisse = [scan_datei(d) for d in dateien]
    alle_sauber = all(e.sauber for e in ergebnisse)
    return alle_sauber, ergebnisse
