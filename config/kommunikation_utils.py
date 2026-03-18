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


def _matrix_rate_limit_warten(exc, kontext=""):
    """Liest retry_after_ms aus einem 429-Response-Body und wartet entsprechend."""
    try:
        body = json.loads(exc.read().decode("utf-8"))
        warte_ms = int(body.get("retry_after_ms", 5000))
    except Exception:
        warte_ms = 5000
    warte_sek = max(warte_ms / 1000, 1.0)
    logger.info("Matrix Rate Limit (%s) – warte %.1f Sekunden.", kontext, warte_sek)
    time.sleep(warte_sek + 0.2)


def matrix_nachricht_senden(room_id, text):
    """Sendet eine Textnachricht per Matrix Client-Server-API in einen Raum.

    Benoetigt MATRIX_HOMESERVER_URL und MATRIX_BOT_TOKEN in settings/Umgebung.
    Schlaegt still fehl wenn nicht konfiguriert – kein Blocking des Hauptprozesses.
    Verwendet PUT /rooms/{room_id}/send/m.room.message/{txn_id}
    Bei HTTP 429 wird einmal nach retry_after_ms wiederholt.
    """
    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not room_id:
        logger.debug(
            "Matrix-Benachrichtigung uebersprungen (MATRIX_HOMESERVER_URL oder "
            "MATRIX_BOT_TOKEN nicht konfiguriert)."
        )
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    def _sende(txn_id):
        url = (
            f"{homeserver}/_matrix/client/v3/rooms/{room_id}"
            f"/send/m.room.message/{txn_id}"
        )
        payload = json.dumps({"msgtype": "m.text", "body": text}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info(
                "Matrix-Nachricht gesendet in Raum %s (HTTP %s)", room_id, resp.status
            )

    for versuch in range(5):
        try:
            _sende(str(int(time.time() * 1000) + versuch))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _matrix_rate_limit_warten(exc, room_id)
                continue
            logger.warning("Matrix-Nachricht konnte nicht gesendet werden: %s", exc)
            break
        except urllib.error.URLError as exc:
            logger.warning("Matrix-Nachricht konnte nicht gesendet werden: %s", exc)
            break


def matrix_dm_senden(empfaenger_matrix_id, text):
    """Sendet eine Direktnachricht an einen Matrix-Nutzer.

    Legt automatisch einen privaten Raum an (is_direct=true) und sendet
    die Nachricht dort. Gibt die room_id zurueck (oder None bei Fehler).
    """
    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not empfaenger_matrix_id:
        logger.debug(
            "Matrix-DM uebersprungen (nicht konfiguriert oder kein Empfaenger)."
        )
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Privaten DM-Raum erstellen (bei 429: einmal wiederholen)
    create_url = f"{homeserver}/_matrix/client/v3/createRoom"
    create_payload = json.dumps({
        "invite": [empfaenger_matrix_id],
        "is_direct": True,
        "preset": "private_chat",
        "initial_state": [
            {
                "type": "m.room.history_visibility",
                "content": {"history_visibility": "invited"},
            }
        ],
    }).encode("utf-8")

    def _erstelle_raum():
        req = urllib.request.Request(
            create_url, data=create_payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("room_id")

    # Raum erstellen – bis zu 5 Versuche bei 429
    dm_room_id = None
    for versuch in range(5):
        try:
            dm_room_id = _erstelle_raum()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _matrix_rate_limit_warten(exc, f"createRoom fuer {empfaenger_matrix_id}")
                continue
            logger.warning("Matrix-DM Raum konnte nicht erstellt werden: %s", exc)
            return None
        except urllib.error.URLError as exc:
            logger.warning("Matrix-DM Raum konnte nicht erstellt werden: %s", exc)
            return None
    if not dm_room_id:
        logger.warning(
            "Matrix-DM createRoom fuer %s nach 5 Versuchen fehlgeschlagen.",
            empfaenger_matrix_id,
        )
        return None

    if not dm_room_id:
        logger.warning("Matrix-DM: Kein room_id nach createRoom erhalten.")
        return None

    # Nachricht senden
    matrix_nachricht_senden(dm_room_id, text)
    return dm_room_id


def matrix_messages_seit_token(room_id, since_token=None):
    """Laedt neue Nachrichten aus einem Matrix-Raum seit dem letzten Poll.

    Gibt (nachrichten_liste, neuer_since_token) zurueck.
    nachrichten_liste: Liste von dicts mit 'sender', 'body', 'event_id'
    """
    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not room_id:
        return [], since_token

    headers = {"Authorization": f"Bearer {token}"}

    # Ohne since_token: aktuellen End-Token holen (rueckwaerts, limit=1)
    if not since_token:
        url = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/messages?dir=b&limit=1"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                since_token = data.get("end", "")
        except urllib.error.URLError as exc:
            logger.warning("matrix_messages_seit_token (init) Fehler: %s", exc)
            return [], since_token
        return [], since_token

    # Mit since_token: vorwaerts pollen
    url = (
        f"{homeserver}/_matrix/client/v3/rooms/{room_id}/messages"
        f"?dir=f&from={since_token}&limit=30"
    )
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        logger.warning("matrix_messages_seit_token Fehler: %s", exc)
        return [], since_token

    nachrichten = []
    for event in data.get("chunk", []):
        if event.get("type") != "m.room.message":
            continue
        content = event.get("content", {})
        if content.get("msgtype") != "m.text":
            continue
        nachrichten.append({
            "sender": event.get("sender", ""),
            "body": content.get("body", "").strip(),
            "event_id": event.get("event_id", ""),
        })

    neuer_token = data.get("end", since_token)
    return nachrichten, neuer_token


def matrix_nutzer_in_raum_einladen(room_id, matrix_user_id):
    """Laedt einen Matrix-Nutzer per Bot-Einladung in einen Raum ein.

    Verwendet die normale Client-API (/invite). Der Nutzer sieht die Einladung
    beim naechsten Element-Login und muss sie einmal annehmen.
    Schlaegt still fehl wenn der Nutzer bereits Mitglied ist.
    Gibt True zurueck bei Erfolg oder bereits Mitglied, False bei Fehler.
    """
    import json
    import urllib.error
    import urllib.request

    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not room_id or not matrix_user_id:
        return False

    payload = json.dumps({"user_id": matrix_user_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{homeserver}/_matrix/client/v3/rooms/{room_id}/invite",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        logger.info("Matrix-Einladung gesendet: %s -> %s", matrix_user_id, room_id)
        return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        if exc.code == 403 and ("already" in body.lower() or "in the room" in body.lower()):
            return True  # bereits Mitglied – kein Problem
        logger.warning(
            "Matrix-Einladung fehlgeschlagen fuer %s in %s (HTTP %s): %s",
            matrix_user_id, room_id, exc.code, body[:200],
        )
        return False
    except urllib.error.URLError as exc:
        logger.warning("Matrix-Einladung Netzwerkfehler: %s", exc)
        return False


def matrix_power_level_setzen(room_id, matrix_user_id, level=50):
    """Setzt den Power Level eines Nutzers in einem Matrix-Raum.

    Liest zuerst die aktuellen Power-Levels, ergaenzt den Nutzer und schreibt
    den State-Event zurueck. Wird verwendet um al_as Schreibrechte zu geben.
    Gibt True bei Erfolg, False bei Fehler zurueck.
    """
    import json
    import urllib.error
    import urllib.request

    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not room_id or not matrix_user_id:
        return False

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Aktuelle Power-Levels lesen
    url_get = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/state/m.room.power_levels"
    req_get = urllib.request.Request(url_get, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req_get, timeout=5) as resp:
            power_levels = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Power-Levels lesen fehlgeschlagen fuer %s: %s", room_id, exc)
        return False

    # Nutzer-Level setzen
    if "users" not in power_levels:
        power_levels["users"] = {}
    power_levels["users"][matrix_user_id] = level

    # Zurueckschreiben
    url_put = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/state/m.room.power_levels"
    payload = json.dumps(power_levels).encode("utf-8")
    req_put = urllib.request.Request(url_put, data=payload, headers=headers, method="PUT")
    try:
        urllib.request.urlopen(req_put, timeout=5)
        logger.info("Power Level %s gesetzt fuer %s in %s", level, matrix_user_id, room_id)
        return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        logger.warning(
            "Power Level setzen fehlgeschlagen: %s in %s (HTTP %s): %s",
            matrix_user_id, room_id, exc.code, body[:200],
        )
        return False
    except urllib.error.URLError as exc:
        logger.warning("Power Level setzen Netzwerkfehler: %s", exc)
        return False


def matrix_reaktionen_holen(room_id, event_id):
    """Laedt alle Emoji-Reaktionen auf eine bestimmte Nachricht.

    Gibt eine Liste von dicts zurueck: {'sender', 'emoji'}
    """
    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token or not room_id or not event_id:
        return []

    url = (
        f"{homeserver}/_matrix/client/v3/rooms/{room_id}"
        f"/relations/{event_id}/m.reaction?limit=50"
    )
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        logger.warning("matrix_reaktionen_holen Fehler: %s", exc)
        return []

    reaktionen = []
    for event in data.get("chunk", []):
        emoji = (
            event.get("content", {})
            .get("m.relates_to", {})
            .get("key", "")
        )
        reaktionen.append({
            "sender": event.get("sender", ""),
            "emoji": emoji,
        })
    return reaktionen
