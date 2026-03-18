"""
Synapse Admin API Service.

Stellt Funktionen bereit um per HTTP-API mit dem lokalen Matrix/Synapse-Server
zu kommunizieren. Alle Fehler werden still geloggt – kein Absturz des aufrufenden
Vorgangs bei API-Problemen.
"""
import logging
import urllib.parse

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_config():
    """Gibt (homeserver_url, bot_token) zurueck oder (None, None) wenn nicht konfiguriert.

    Bevorzugt MATRIX_HOMESERVER_INTERNAL_URL fuer server-seitige API-Calls
    (z.B. http://host.docker.internal:8009) damit der Django-Container Synapse
    direkt erreicht ohne Cloudflare-Umweg.
    """
    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    if not homeserver or not token:
        return None, None
    return homeserver, token


def _matrix_user_id(username):
    """Baut die Matrix-User-ID aus dem Django-Username.

    Verwendet immer die oeffentliche MATRIX_HOMESERVER_URL fuer die Domain,
    nie die interne URL – Matrix-User-IDs sind immer mit dem oeffentlichen
    Servernamen aufgebaut.

    Beispiel: 'max.mustermann' -> '@max.mustermann:georg-klein.com'
    """
    # MATRIX_SERVER_NAME hat Vorrang (z.B. "georg-klein.com"),
    # sonst Domain aus MATRIX_HOMESERVER_URL extrahieren
    domain = getattr(settings, "MATRIX_SERVER_NAME", "").strip()
    if not domain:
        public_url = getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
        if not public_url:
            return None
        domain = public_url.replace("https://", "").replace("http://", "").split("/")[0]
    return f"@{username}:{domain}"


def lade_matrix_user_id(mitarbeiter):
    """Gibt die Matrix-User-ID fuer einen HRMitarbeiter zurueck.

    Benutzt den Django-Username des verknuepften Users.
    Gibt None zurueck wenn kein User verknuepft oder nicht konfiguriert.
    """
    if not mitarbeiter.user:
        return None
    return _matrix_user_id(mitarbeiter.user.username)


def einladen_in_raum(room_id, matrix_user_id):
    """Laedt einen User per Synapse API in einen Raum ein.

    Gibt True bei Erfolg zurueck, False bei Fehler.
    Schlaegt still fehl – kein Exception-Propagation.
    """
    import urllib.error
    import urllib.request
    import json

    homeserver, token = _get_config()
    if not homeserver or not token:
        logger.debug("Matrix nicht konfiguriert – Einladung uebersprungen.")
        return False
    if not room_id or not matrix_user_id:
        return False

    url = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/invite"
    payload = json.dumps({"user_id": matrix_user_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info(
                "Matrix-Einladung gesendet: %s -> Raum %s (Status %s)",
                matrix_user_id, room_id, resp.status,
            )
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        # M_FORBIDDEN = bereits Mitglied oder schon eingeladen -> kein echtes Problem
        if "M_FORBIDDEN" in body or "already" in body.lower():
            logger.debug("Matrix-Einladung uebersprungen (bereits Mitglied): %s", matrix_user_id)
            return True
        logger.warning(
            "Matrix-Einladung fehlgeschlagen fuer %s in %s: HTTP %s – %s",
            matrix_user_id, room_id, exc.code, body,
        )
        return False
    except Exception as exc:
        logger.warning(
            "Matrix-Einladung fehlgeschlagen fuer %s in %s: %s",
            matrix_user_id, room_id, exc,
        )
        return False


def einladen_in_org_einheit_raeume(mitarbeiter):
    """Laedt einen Mitarbeiter in alle aktiven Matrix-Raeume seiner Org-Einheit ein.

    Sucht Raeume ueber MatrixRaum.org_einheit der Stelle des Mitarbeiters.
    Schlaegt still fehl.
    """
    if not mitarbeiter.stelle or not mitarbeiter.stelle.org_einheit_id:
        logger.debug(
            "Mitarbeiter pk=%s hat keine Stelle/Org-Einheit – keine Einladung.",
            mitarbeiter.pk,
        )
        return

    matrix_user_id = lade_matrix_user_id(mitarbeiter)
    if not matrix_user_id:
        logger.debug(
            "Mitarbeiter pk=%s hat keinen Django-User – keine Matrix-Einladung.",
            mitarbeiter.pk,
        )
        return

    from matrix_integration.models import MatrixRaum
    raeume = MatrixRaum.objects.filter(
        ist_aktiv=True,
        org_einheit_id=mitarbeiter.stelle.org_einheit_id,
    ).exclude(room_id="")

    for raum in raeume:
        einladen_in_raum(raum.room_id, matrix_user_id)


def matrix_account_existiert(username):
    """Prueft ob ein Matrix-Account auf Synapse bereits existiert.

    Gibt True zurueck wenn der Account existiert, False wenn nicht oder bei Fehler.
    """
    import urllib.error
    import urllib.request

    homeserver, _ = _get_config()
    admin_token = getattr(settings, "MATRIX_ADMIN_TOKEN", "")
    if not homeserver or not admin_token:
        return False

    matrix_id = _matrix_user_id(username)
    if not matrix_id:
        return False

    url = f"{homeserver}/_synapse/admin/v2/users/{urllib.parse.quote(matrix_id)}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {admin_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        return False
    except Exception:
        return False


def erstelle_matrix_account(username, anzeigename=""):
    """Legt einen Matrix-Account auf Synapse an (via Admin API).

    Gibt True bei Erfolg zurueck, False bei Fehler.

    Passwort-Strategie:
    - Neuer Account: Standardpasswort 'hrmitarbeiter2026' wird gesetzt.
    - Vorhandener Account: Kein Passwort-Reset – das Passwort des Users
      bleibt unveraendert. Django und Matrix haben getrennte Credentials.
    """
    import json
    import urllib.error
    import urllib.request

    from matrix_integration.management.commands.matrix_passwort_setzen import (
        STANDARD_PASSWORT,
    )

    homeserver, _ = _get_config()
    admin_token = getattr(settings, "MATRIX_ADMIN_TOKEN", "")
    if not homeserver or not admin_token:
        logger.warning("MATRIX_ADMIN_TOKEN nicht konfiguriert – Account-Erstellung nicht moeglich.")
        return False

    matrix_id = _matrix_user_id(username)
    if not matrix_id:
        return False

    ist_neu = not matrix_account_existiert(username)

    url = f"{homeserver}/_synapse/admin/v2/users/{urllib.parse.quote(matrix_id)}"
    payload = {"displayname": anzeigename or username}
    if ist_neu:
        # Nur bei neuen Accounts Standardpasswort setzen – vorhandene Passwoerter
        # werden nie ueberschrieben (Django-Passwort != Matrix-Passwort)
        payload["password"] = STANDARD_PASSWORT
        logger.info("Neuer Matrix-Account – Standardpasswort wird gesetzt: %s", matrix_id)
    else:
        logger.debug("Matrix-Account bereits vorhanden – kein Passwort-Reset: %s", matrix_id)

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            aktion = "erstellt" if ist_neu else "aktualisiert"
            logger.info("Matrix-Account %s: %s", aktion, matrix_id)
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("Matrix-Account-Erstellung fehlgeschlagen fuer %s: HTTP %s – %s", matrix_id, exc.code, body)
        return False
    except Exception as exc:
        logger.warning("Matrix-Account-Erstellung fehlgeschlagen fuer %s: %s", matrix_id, exc)
        return False


def setze_matrix_passwort(username, passwort):
    """Setzt das Passwort eines Matrix-Accounts via Synapse Admin API.

    Gibt True bei Erfolg zurueck, False bei Fehler.
    Legt den Account an falls er noch nicht existiert.
    """
    import json
    import urllib.error
    import urllib.request

    homeserver, _ = _get_config()
    admin_token = getattr(settings, "MATRIX_ADMIN_TOKEN", "")
    if not homeserver or not admin_token:
        logger.warning("MATRIX_ADMIN_TOKEN nicht konfiguriert – Passwort-Reset nicht moeglich.")
        return False

    matrix_id = _matrix_user_id(username)
    if not matrix_id:
        return False

    url = f"{homeserver}/_synapse/admin/v2/users/{urllib.parse.quote(matrix_id)}"
    payload = {"password": passwort}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            logger.info("Matrix-Passwort gesetzt fuer: %s", matrix_id)
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning(
            "Passwort-Reset fehlgeschlagen fuer %s: HTTP %s – %s",
            matrix_id, exc.code, body,
        )
        return False
    except Exception as exc:
        logger.warning("Passwort-Reset fehlgeschlagen fuer %s: %s", matrix_id, exc)
        return False


def erstelle_raum(name, alias=None, oeffentlich=False):
    """Erstellt einen neuen Raum auf dem Synapse-Server via API.

    Gibt ein dict {"room_id": "!xxx:domain", "room_alias": "#alias:domain"}
    zurueck oder None bei Fehler.
    """
    import json
    import re
    import urllib.error
    import urllib.request

    homeserver, token = _get_config()
    if not homeserver or not token:
        logger.warning("Matrix nicht konfiguriert – Raum kann nicht erstellt werden.")
        return None

    payload = {
        "name": name,
        "preset": "public_chat" if oeffentlich else "private_chat",
        "visibility": "public" if oeffentlich else "private",
    }
    if alias:
        # Alias nur Kleinbuchstaben, Zahlen, Bindestriche
        sauberer_alias = re.sub(r"[^a-z0-9\-]", "-", alias.lower()).strip("-")
        if sauberer_alias:
            payload["room_alias_name"] = sauberer_alias

    url = f"{homeserver}/_matrix/client/v3/createRoom"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    # Servername fuer Alias (MATRIX_SERVER_NAME hat Vorrang)
    domain = getattr(settings, "MATRIX_SERVER_NAME", "").strip()
    if not domain:
        public_homeserver = getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
        domain = public_homeserver.replace("https://", "").replace("http://", "").split("/")[0]

    def _baue_alias(sauberer_alias):
        return f"#{sauberer_alias}:{domain}" if sauberer_alias else ""

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            room_id = data.get("room_id", "")
            room_alias = _baue_alias(
                re.sub(r"[^a-z0-9\-]", "-", alias.lower()).strip("-") if alias else ""
            )
            logger.info("Matrix-Raum erstellt: %s (%s)", room_id, name)
            return {"room_id": room_id, "room_alias": room_alias}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        # Alias bereits vergeben: Raum ohne Alias erstellen
        if "M_ROOM_IN_USE" in body:
            logger.info("Alias '%s' bereits vergeben – erstelle Raum ohne Alias.", alias)
            payload.pop("room_alias_name", None)
            req2 = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    data2 = json.loads(resp2.read().decode("utf-8"))
                    room_id = data2.get("room_id", "")
                    logger.info("Matrix-Raum ohne Alias erstellt: %s (%s)", room_id, name)
                    return {"room_id": room_id, "room_alias": "", "hinweis": f"Alias '{alias}' war bereits vergeben – Raum ohne Alias erstellt."}
            except Exception as exc2:
                logger.warning("Raum-Erstellung (2. Versuch) fehlgeschlagen: %s", exc2)
                return None
        logger.warning("Raum-Erstellung fehlgeschlagen: HTTP %s – %s", exc.code, body)
        return None
    except Exception as exc:
        logger.warning("Raum-Erstellung fehlgeschlagen: %s", exc)
        return None


def sende_nachricht(room_id, nachricht):
    """Sendet eine Text-Nachricht in einen Matrix-Raum.

    Gibt True bei Erfolg zurueck, False bei Fehler.
    """
    import urllib.error
    import urllib.request
    import json
    import time

    homeserver, token = _get_config()
    if not homeserver or not token:
        logger.debug("Matrix nicht konfiguriert – Nachricht uebersprungen.")
        return False
    if not room_id or not nachricht:
        return False

    # Transaktions-ID fuer Idempotenz
    txn_id = str(int(time.time() * 1000))
    url = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
    payload = json.dumps({
        "msgtype": "m.text",
        "body": nachricht,
    }).encode("utf-8")
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
            logger.info("Matrix-Nachricht gesendet in Raum %s (Status %s)", room_id, resp.status)
            return True
    except Exception as exc:
        logger.warning("Matrix-Nachricht fehlgeschlagen in Raum %s: %s", room_id, exc)
        return False
