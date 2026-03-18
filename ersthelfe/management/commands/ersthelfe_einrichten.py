"""
Management-Command: Ersthelfe-Grundkonfiguration

- Legt Stelle 'ba_as' (Betriebsarzt) an und besetzt sie
- Markiert 3 Mitarbeiter als Ersthelfer
- Erstellt Matrix-Raum EH_PING und laedt Bot ein
- Speichert Raum-ID in settings (gibt sie aus fuer .env.prima)

Ausfuehren:
    python manage.py ersthelfe_einrichten
    python manage.py ersthelfe_einrichten --ueberschreiben
"""
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models

logger = logging.getLogger(__name__)


def _matrix_post(homeserver, token, pfad, payload):
    """Hilfsfunktion: POST gegen Matrix API, gibt Response-Dict zurueck."""
    url = f"{homeserver}{pfad}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Command(BaseCommand):
    help = "Richtet Betriebsarzt-Stelle, Ersthelfer und Matrix-EH-Raum ein"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ueberschreiben",
            action="store_true",
            help="Bereits vorhandene Konfiguration aktualisieren",
        )

    def handle(self, *args, **options):
        ueberschreiben = options["ueberschreiben"]

        self._stelle_und_betriebsarzt_anlegen(ueberschreiben)
        self._ersthelfer_markieren(ueberschreiben)
        self._matrix_raum_einrichten()

    # -----------------------------------------------------------------------

    def _stelle_und_betriebsarzt_anlegen(self, ueberschreiben):
        from django.contrib.auth.models import User

        from hr.models import HRMitarbeiter, OrgEinheit, Stelle

        self.stdout.write("\n--- Betriebsarzt-Stelle ---")

        # OrgEinheit ermitteln (HR oder erste verfuegbare)
        try:
            org_einheit = OrgEinheit.objects.get(kuerzel="HR")
        except OrgEinheit.DoesNotExist:
            org_einheit = OrgEinheit.objects.first()

        # Stelle ba_as anlegen oder laden
        stelle, neu = Stelle.objects.get_or_create(
            kuerzel="ba_as",
            defaults={
                "bezeichnung": "Betriebsarzt/Betriebsaerztin",
                "org_einheit": org_einheit,
                "ist_betriebsarzt": True,
            },
        )
        if not neu and not ueberschreiben:
            self.stdout.write(f"  Stelle 'ba_as' bereits vorhanden – uebersprungen (--ueberschreiben zum Aktualisieren)")
        else:
            stelle.ist_betriebsarzt = True
            stelle.bezeichnung = "Betriebsarzt/Betriebsaerztin"
            stelle.save()
            self.stdout.write(self.style.SUCCESS(f"  Stelle 'ba_as' {'angelegt' if neu else 'aktualisiert'}."))

        # Bereits besetzt?
        if stelle.ist_besetzt:
            self.stdout.write(f"  Stelle bereits besetzt durch: {stelle.hrmitarbeiter.vollname}")
            return

        # Mitarbeiter ohne Stelle suchen – bevorzugt jemand aus HR
        kandidat = (
            HRMitarbeiter.objects.filter(stelle__isnull=True, user__isnull=False)
            .order_by("nachname")
            .first()
        )
        if not kandidat:
            self.stdout.write(self.style.WARNING(
                "  Kein freier Mitarbeiter fuer Betriebsarzt-Stelle gefunden. "
                "Stelle bleibt unbesetzt."
            ))
            return

        kandidat.stelle = stelle
        kandidat.save(update_fields=["stelle"])
        self.stdout.write(self.style.SUCCESS(
            f"  {kandidat.vollname} ({kandidat.personalnummer}) als Betriebsarzt/in eingestellt."
        ))

    def _ersthelfer_markieren(self, ueberschreiben):
        from django.utils import timezone

        from hr.models import HRMitarbeiter

        self.stdout.write("\n--- Ersthelfer ---")

        # Bereits vorhandene Ersthelfer zaehlen
        vorhandene = HRMitarbeiter.objects.filter(ist_ersthelfer=True).count()
        if vorhandene >= 3 and not ueberschreiben:
            self.stdout.write(
                f"  Bereits {vorhandene} Ersthelfer konfiguriert – uebersprungen."
            )
            for eh in HRMitarbeiter.objects.filter(ist_ersthelfer=True).select_related("stelle"):
                self.stdout.write(f"    - {eh.vollname} ({eh.stelle.kuerzel if eh.stelle else '-'})")
            return

        # 3 Mitarbeiter auswaehlen: gestreut ueber verschiedene Abteilungen
        # Bevorzugt MA mit Stelle und aktivem User, die noch kein Ersthelfer sind
        kandidaten = list(
            HRMitarbeiter.objects.filter(
                ist_ersthelfer=False,
                stelle__isnull=False,
                user__isnull=False,
                user__is_active=True,
            )
            .select_related("stelle__org_einheit", "user")
            .order_by("stelle__org_einheit__kuerzel", "nachname")
        )

        # Je einen aus unterschiedlichen OrgEinheiten waehlen
        gewaehlt = []
        gesehene_org = set()
        for ma in kandidaten:
            if len(gewaehlt) >= 3:
                break
            org_key = ma.stelle.org_einheit.kuerzel if ma.stelle and ma.stelle.org_einheit else ""
            if org_key not in gesehene_org:
                gewaehlt.append(ma)
                gesehene_org.add(org_key)

        # Falls nicht genug aus verschiedenen OrgEinheiten: auffuellen
        if len(gewaehlt) < 3:
            for ma in kandidaten:
                if ma not in gewaehlt:
                    gewaehlt.append(ma)
                if len(gewaehlt) >= 3:
                    break

        heute = timezone.localdate()
        ablauf = heute.replace(year=heute.year + 2)  # Schein 2 Jahre gueltig

        for ma in gewaehlt:
            ma.ist_ersthelfer = True
            ma.ersthelfer_seit = heute
            ma.ersthelfer_gueltig_bis = ablauf
            ma.save(update_fields=["ist_ersthelfer", "ersthelfer_seit", "ersthelfer_gueltig_bis"])
            self.stdout.write(self.style.SUCCESS(
                f"  {ma.vollname} ({ma.stelle.kuerzel}) als Ersthelfer/in markiert."
                f" Schein gueltig bis {ablauf.strftime('%d.%m.%Y')}."
            ))

        if len(gewaehlt) < 3:
            self.stdout.write(self.style.WARNING(
                f"  Nur {len(gewaehlt)} Ersthelfer konfiguriert – nicht genug freie Mitarbeiter."
            ))

    def _matrix_raum_einrichten(self):
        self.stdout.write("\n--- Matrix-Raum EH_PING ---")

        homeserver = (
            getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
            or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
        )
        bot_token = getattr(settings, "MATRIX_BOT_TOKEN", "")
        admin_token = getattr(settings, "MATRIX_ADMIN_TOKEN", "")
        server_name = getattr(settings, "MATRIX_SERVER_NAME", "")

        if not homeserver or not bot_token:
            self.stdout.write(self.style.WARNING(
                "  MATRIX_HOMESERVER_URL / MATRIX_BOT_TOKEN nicht konfiguriert – uebersprungen."
            ))
            return

        # Raum-Alias pruefen ob bereits vorhanden
        alias = f"#EH_PING:{server_name}"
        alias_encoded = alias.replace("#", "%23").replace(":", "%3A")
        try:
            req = urllib.request.Request(
                f"{homeserver}/_matrix/client/v3/directory/room/{alias_encoded}",
                headers={"Authorization": f"Bearer {bot_token}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raum_id = data.get("room_id")
                self.stdout.write(f"  Raum '{alias}' bereits vorhanden: {raum_id}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raum_id = None
            else:
                self.stdout.write(self.style.ERROR(f"  Fehler beim Pruefen des Raum-Alias: {exc}"))
                return

        if raum_id is None:
            # Raum erstellen (Bot erstellt ihn)
            token_fuer_erstellung = admin_token or bot_token
            try:
                result = _matrix_post(homeserver, token_fuer_erstellung, "/_matrix/client/v3/createRoom", {
                    "room_alias_name": "EH_PING",
                    "name": "Erste Hilfe – Einsatzkoordination",
                    "topic": "PRIMA Erste-Hilfe-Alarm. Nur fuer Ersthelfer und Betriebsarzt.",
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
                })
                raum_id = result.get("room_id")
                self.stdout.write(self.style.SUCCESS(f"  Raum erstellt: {raum_id}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Raum konnte nicht erstellt werden: {exc}"))
                return

        # Bot einladen und joinen (falls noch nicht Mitglied)
        bot_user_id = f"@prima-bot:{server_name}"
        if admin_token and admin_token != bot_token:
            # Admin laedt Bot ein
            try:
                _matrix_post(homeserver, admin_token, f"/_matrix/client/v3/rooms/{raum_id}/invite", {
                    "user_id": bot_user_id,
                })
                self.stdout.write(f"  Bot {bot_user_id} eingeladen.")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
                if "already" in body.lower() or exc.code in (400, 403):
                    self.stdout.write(f"  Bot bereits Mitglied (oder Einladung nicht noetig).")
                else:
                    self.stdout.write(self.style.WARNING(f"  Bot-Einladung: {exc.code} – {body}"))

            # Bot joint dem Raum
            try:
                _matrix_post(homeserver, bot_token, f"/_matrix/client/v3/join/{raum_id}", {})
                self.stdout.write(f"  Bot ist dem Raum beigetreten.")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
                self.stdout.write(f"  Bot-Join: {exc.code} – {body} (evtl. bereits Mitglied)")

        # Betriebsarzt und Ersthelfer einladen
        self._mitglieder_einladen(homeserver, bot_token, server_name, raum_id)

        # Testping senden
        try:
            txn_id = str(int(time.time() * 1000))
            _matrix_put(
                homeserver, bot_token,
                f"/_matrix/client/v3/rooms/{raum_id}/send/m.room.message/{txn_id}",
                {"msgtype": "m.text", "body": "[PRIMA] EH-Raum eingerichtet. Bereit fuer Erste-Hilfe-Alarme."},
            )
            self.stdout.write(self.style.SUCCESS("  Testping erfolgreich gesendet."))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Testping fehlgeschlagen: {exc}"))

    def _mitglieder_einladen(self, homeserver, bot_token, server_name, raum_id):
        """Laedt alle Ersthelfer und den Betriebsarzt in den EH_PING-Raum ein."""
        from hr.models import HRMitarbeiter

        self.stdout.write("\n--- Mitglieder einladen ---")

        mitglieder = list(
            HRMitarbeiter.objects.filter(
                stelle__isnull=False,
                user__isnull=False,
                user__is_active=True,
            ).filter(
                models.Q(ist_ersthelfer=True) | models.Q(stelle__ist_betriebsarzt=True)
            ).select_related("stelle", "user")
        )

        for ma in mitglieder:
            kuerzel = ma.stelle.kuerzel
            matrix_id = f"@{kuerzel}:{server_name}"
            try:
                _matrix_post(
                    homeserver, bot_token,
                    f"/_matrix/client/v3/rooms/{raum_id}/invite",
                    {"user_id": matrix_id},
                )
                rolle = "Betriebsarzt" if ma.stelle.ist_betriebsarzt else "Ersthelfer"
                self.stdout.write(self.style.SUCCESS(
                    f"  {ma.vollname} ({kuerzel}) eingeladen [{rolle}]"
                ))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode() if hasattr(exc, "read") else ""
                if "already" in body.lower() or "in the room" in body.lower():
                    self.stdout.write(f"  {ma.vollname} bereits im Raum.")
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  Einladung fuer {kuerzel} fehlgeschlagen: {body[:80]}"
                    ))

        # Ergebnis ausgeben
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Naechster Schritt ==="))
        self.stdout.write(f"  Folgende Zeile in .env.prima eintragen:")
        self.stdout.write(f"  MATRIX_EH_PING_ROOM_ID={raum_id}")
        self.stdout.write("")
        self.stdout.write("  Danach Container neu starten:")
        self.stdout.write("  docker compose up -d web")
