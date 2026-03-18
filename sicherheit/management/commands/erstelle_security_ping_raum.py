"""
Management-Command: SECURITY_PING Matrix-Raum erstellen

Erstellt einen Matrix-Raum fuer Security-Alarme und laedt alle
sicherheitsrelevanten Mitarbeiter ein (Stellen-Kuerzel-Liste).

Ausfuehren:
    python manage.py erstelle_security_ping_raum
"""
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Sicherheitsrelevante Stellen-Kuerzel
_SECURITY_KUERZEL = [
    "al_sec", "sv_sec",
    "ma_sec1", "ma_sec2", "ma_sec3", "ma_sec4",
    "pf_sec", "al_as", "ba_as", "gf1", "gf_tech", "gf_verw",
]


def _matrix_post(homeserver, token, pfad, payload):
    """Hilfsfunktion: POST gegen Matrix API, gibt Response-Dict zurueck."""
    url = f"{homeserver}{pfad}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _matrix_put(homeserver, token, pfad, payload):
    """Hilfsfunktion: PUT gegen Matrix API."""
    url = f"{homeserver}{pfad}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Command(BaseCommand):
    help = "Erstellt Matrix-Raum SECURITY_PING und laedt Security-Personal ein"

    def handle(self, *args, **options):
        homeserver = (
            getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
            or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
        )
        bot_token = getattr(settings, "MATRIX_BOT_TOKEN", "")
        admin_token = getattr(settings, "MATRIX_ADMIN_TOKEN", "")
        server_name = getattr(settings, "MATRIX_SERVER_NAME", "")

        if not homeserver or not bot_token:
            self.stdout.write(self.style.WARNING(
                "MATRIX_HOMESERVER_URL / MATRIX_BOT_TOKEN nicht konfiguriert – abgebrochen."
            ))
            return

        raum_id = self._raum_einrichten(homeserver, bot_token, admin_token, server_name)
        if raum_id:
            self._mitglieder_einladen(homeserver, bot_token, server_name, raum_id)
            self._testping_senden(homeserver, bot_token, raum_id)
            self._abschluss_ausgeben(raum_id)

    def _raum_einrichten(self, homeserver, bot_token, admin_token, server_name):
        """Erstellt oder gibt bestehenden SECURITY_PING-Raum zurueck."""
        self.stdout.write("\n--- Matrix-Raum SECURITY_PING ---")

        alias = f"#SECURITY_PING:{server_name}"
        alias_encoded = alias.replace("#", "%23").replace(":", "%3A")

        # Pruefen ob Raum bereits vorhanden
        try:
            req = urllib.request.Request(
                f"{homeserver}/_matrix/client/v3/directory/room/{alias_encoded}",
                headers={"Authorization": f"Bearer {bot_token}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raum_id = data.get("room_id")
                self.stdout.write(
                    f"  Raum '{alias}' bereits vorhanden: {raum_id}"
                )
                return raum_id
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                self.stdout.write(self.style.ERROR(
                    f"  Fehler beim Pruefen des Raum-Alias: {exc}"
                ))
                return None

        # Raum erstellen
        token_fuer_erstellung = admin_token or bot_token
        try:
            result = _matrix_post(
                homeserver,
                token_fuer_erstellung,
                "/_matrix/client/v3/createRoom",
                {
                    "room_alias_name": "SECURITY_PING",
                    "name": "Security – Alarmierung",
                    "topic": "PRIMA Sicherheitsalarme. Nur fuer Security-Personal.",
                    "preset": "private_chat",
                    "visibility": "private",
                    "power_level_content_override": {
                        "users_default": 0,
                        "events_default": 50,
                        "state_default": 50,
                        "ban": 50,
                        "kick": 50,
                        "redact": 50,
                        "invite": 50,
                    },
                },
            )
            raum_id = result.get("room_id")
            self.stdout.write(self.style.SUCCESS(f"  Raum erstellt: {raum_id}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                f"  Raum konnte nicht erstellt werden: {exc}"
            ))
            return None

        # Bot einladen und joinen (falls Admin-Token vorhanden)
        bot_user_id = f"@prima-bot:{server_name}"
        if admin_token and admin_token != bot_token:
            try:
                _matrix_post(
                    homeserver, admin_token,
                    f"/_matrix/client/v3/rooms/{raum_id}/invite",
                    {"user_id": bot_user_id},
                )
                self.stdout.write(f"  Bot {bot_user_id} eingeladen.")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
                if "already" in body.lower() or exc.code in (400, 403):
                    self.stdout.write("  Bot bereits Mitglied.")
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  Bot-Einladung: {exc.code} – {body}"
                    ))

            try:
                _matrix_post(
                    homeserver, bot_token,
                    f"/_matrix/client/v3/join/{raum_id}",
                    {},
                )
                self.stdout.write("  Bot ist dem Raum beigetreten.")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
                self.stdout.write(
                    f"  Bot-Join: {exc.code} – {body} (evtl. bereits Mitglied)"
                )

        return raum_id

    def _mitglieder_einladen(self, homeserver, bot_token, server_name, raum_id):
        """Laedt alle Security-Mitarbeiter in den SECURITY_PING-Raum ein."""
        from hr.models import HRMitarbeiter

        self.stdout.write("\n--- Security-Mitarbeiter einladen ---")

        mitglieder = list(
            HRMitarbeiter.objects
            .filter(
                stelle__kuerzel__in=_SECURITY_KUERZEL,
                user__isnull=False,
                user__is_active=True,
            )
            .select_related("stelle", "user")
        )

        if not mitglieder:
            self.stdout.write(self.style.WARNING(
                "  Keine Security-Mitarbeiter gefunden (Stellen-Kuerzel pruefen)."
            ))
            return

        for ma in mitglieder:
            kuerzel = ma.stelle.kuerzel
            matrix_id = f"@{kuerzel}:{server_name}"
            try:
                _matrix_post(
                    homeserver, bot_token,
                    f"/_matrix/client/v3/rooms/{raum_id}/invite",
                    {"user_id": matrix_id},
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  {ma.vollname} ({kuerzel}) eingeladen."
                ))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
                if "already" in body.lower() or "in the room" in body.lower():
                    self.stdout.write(f"  {ma.vollname} bereits im Raum.")
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  Einladung fuer {kuerzel} fehlgeschlagen: {body[:80]}"
                    ))

    def _testping_senden(self, homeserver, bot_token, raum_id):
        """Sendet eine Test-Nachricht in den SECURITY_PING-Raum."""
        try:
            txn_id = str(int(time.time() * 1000))
            _matrix_put(
                homeserver, bot_token,
                f"/_matrix/client/v3/rooms/{raum_id}/send/m.room.message/{txn_id}",
                {
                    "msgtype": "m.text",
                    "body": "[PRIMA] SECURITY_PING-Raum eingerichtet. Bereit fuer Sicherheitsalarme.",
                },
            )
            self.stdout.write(self.style.SUCCESS("\n  Testping erfolgreich gesendet."))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"\n  Testping fehlgeschlagen: {exc}"))

    def _abschluss_ausgeben(self, raum_id):
        """Gibt Instruktionen fuer den naechsten Schritt aus."""
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Naechster Schritt ==="))
        self.stdout.write("  Folgende Zeile in .env.prima eintragen:")
        self.stdout.write(f"  MATRIX_SECURITY_PING_ROOM_ID={raum_id}")
        self.stdout.write("")
        self.stdout.write("  Danach Container neu starten:")
        self.stdout.write("  docker compose up -d web")
