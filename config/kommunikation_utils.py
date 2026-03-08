"""Hilfsfunktionen fuer externe Kommunikationstools: Jitsi Meet + Matrix."""

import json
import logging
import re
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _slugify(text):
    """Erzeugt einen URL-sicheren Slug ohne externe Abhaengigkeiten."""
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Jitsi Meet
# ---------------------------------------------------------------------------

def jitsi_link_generieren(raumname, datum, buchungs_nr):
    """Erstellt einen Jitsi-Meeting-Link fuer eine Raumbuchung.

    Gibt leeren String zurueck wenn JITSI_BASE_URL nicht konfiguriert ist.
    Der Link ist deterministisch: gleiche Buchung → gleicher Link.
    """
    base_url = getattr(settings, "JITSI_BASE_URL", "").rstrip("/")
    if not base_url:
        return ""
    datum_str = (
        datum.strftime("%Y%m%d")
        if hasattr(datum, "strftime")
        else str(datum).replace("-", "")
    )
    slug = _slugify(f"{raumname}-{datum_str}-{buchungs_nr}")
    return f"{base_url}/{slug}"


# ---------------------------------------------------------------------------
# Matrix / Element
# ---------------------------------------------------------------------------

def matrix_raum_link(raumname):
    """Erstellt einen matrix.to-Link fuer einen persistenten Raum-Chat.

    Gibt leeren String zurueck wenn MATRIX_HOMESERVER_URL nicht konfiguriert ist.
    Der Raumname wird als Matrix-Alias verwendet: #slug:domain
    """
    homeserver = getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    if not homeserver:
        return ""
    slug = _slugify(raumname)
    domain = homeserver.replace("https://", "").replace("http://", "")
    alias = f"#{slug}:{domain}"
    return f"https://matrix.to/#/{alias}"


def matrix_nachricht_senden(room_id, text):
    """Sendet eine Textnachricht per Matrix Client-Server-API in einen Raum.

    Benoetigt MATRIX_HOMESERVER_URL und MATRIX_BOT_TOKEN in settings/Umgebung.
    Schlaegt still fehl wenn nicht konfiguriert – kein Blocking des Hauptprozesses.
    Verwendet PUT /rooms/{room_id}/send/m.room.message/{txn_id}
    """
    homeserver = getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not room_id:
        logger.debug(
            "Matrix-Benachrichtigung uebersprungen (MATRIX_HOMESERVER_URL oder "
            "MATRIX_BOT_TOKEN nicht konfiguriert)."
        )
        return

    txn_id = str(int(time.time() * 1000))
    url = (
        f"{homeserver}/_matrix/client/v3/rooms/{room_id}"
        f"/send/m.room.message/{txn_id}"
    )
    payload = json.dumps({"msgtype": "m.text", "body": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info(
                "Matrix-Nachricht gesendet in Raum %s (HTTP %s)", room_id, resp.status
            )
    except urllib.error.URLError as exc:
        logger.warning("Matrix-Nachricht konnte nicht gesendet werden: %s", exc)
