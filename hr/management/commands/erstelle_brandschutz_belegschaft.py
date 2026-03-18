"""
Management-Command: erstelle_brandschutz_belegschaft

Weist einem Drittel der Belegschaft die Rolle Branderkunder zu,
einem weiteren Drittel die Rolle Raeumungshelfer.
Erstellt je einen Matrix-Raum nach Stellenbezeichnung und laedt alle ein.

Ausfuehren:
    python manage.py erstelle_brandschutz_belegschaft
    python manage.py erstelle_brandschutz_belegschaft --trocken
    python manage.py erstelle_brandschutz_belegschaft --zuruecksetzen
"""
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

from hr.models import HRMitarbeiter

logger = logging.getLogger(__name__)

# Security-Kuerzel bleiben aussen vor (haben eigene Rollen)
_AUSSCHLUSS_KUERZEL = frozenset([
    "al_sec", "sv_sec", "ma_sec1", "ma_sec2", "ma_sec3", "ma_sec4",
    "pf_sec", "al_as", "ba_as", "gf1", "gf_tech", "gf_verw",
])


def _matrix_raum_erstellen(name, alias, homeserver, bot_token):
    """Erstellt einen Matrix-Raum via normaler Client-API (als Bot-User).

    Gibt die room_id zurueck oder None bei Fehler.
    """
    url = f"{homeserver}/_matrix/client/v3/createRoom"
    payload = json.dumps({
        "name": name,
        "room_alias_name": alias,
        "preset": "private_chat",
        "topic": f"PRIMA Brandschutz – {name}",
        "initial_state": [],
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("room_id")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        if exc.code == 400 and ("alias" in body.lower() or "m_room_in_use" in body.lower()):
            logger.info("Raum-Alias '%s' bereits vergeben – suche vorhandenen Raum.", alias)
        else:
            logger.warning("Raum '%s' konnte nicht erstellt werden (HTTP %s): %s", name, exc.code, body[:200])
        return None
    except urllib.error.URLError as exc:
        logger.warning("Raum erstellen – Netzwerkfehler: %s", exc)
        return None


def _synapse_raum_id_aus_alias(alias, server_name, homeserver, bot_token):
    """Laedt die room_id eines Raums anhand seines Alias."""
    url = f"{homeserver}/_matrix/client/v3/directory/room/%23{alias}%3A{server_name}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {bot_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("room_id")
    except Exception:
        return None


class Command(BaseCommand):
    help = (
        "Weist 1/3 der Belegschaft als Branderkunder und 1/3 als "
        "Raeumungshelfer zu, erstellt Matrix-Raeume und laedt alle ein."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--trocken",
            action="store_true",
            dest="trocken",
            help="Nur anzeigen – keine Datenbankzuweisungen, keine Matrix-Aktion",
        )
        parser.add_argument(
            "--zuruecksetzen",
            action="store_true",
            dest="zuruecksetzen",
            help="Alle Branderkunder- und Raeumungshelfer-Flags entfernen",
        )

    def handle(self, *args, **options):
        trocken      = options["trocken"]
        zuruecksetzen = options["zuruecksetzen"]

        if zuruecksetzen:
            self._zuruecksetzen(trocken)
            return

        # ---------------------------------------------------------------------------
        # Mitarbeiterliste aufbauen (ohne Ausschluss-Stellen, mit user-Account)
        # ---------------------------------------------------------------------------
        kandidaten = list(
            HRMitarbeiter.objects
            .select_related("stelle", "user")
            .filter(user__isnull=False)
            .exclude(stelle__kuerzel__in=_AUSSCHLUSS_KUERZEL)
            .order_by("stelle__bezeichnung", "pk")
        )
        # Bereits zugewiesene herausfiltern (Idempotenz)
        kandidaten = [
            ma for ma in kandidaten
            if not ma.ist_branderkunder and not ma.ist_raeumungshelfer
            and not ma.ist_ersthelfer  # Ersthelfer bleiben aussen vor
        ]

        gesamt  = len(kandidaten)
        drittel = gesamt // 3

        erkunder_gruppe   = kandidaten[0::3][:drittel]    # jeden 1. von 3
        raeumungs_gruppe  = kandidaten[1::3][:drittel]    # jeden 2. von 3

        self.stdout.write(
            f"Kandidaten (ohne Ersthelfer/Security/Ausschluss): {gesamt}\n"
            f"  -> Branderkunder:   {len(erkunder_gruppe)}\n"
            f"  -> Raeumungshelfer: {len(raeumungs_gruppe)}\n"
        )

        # ---------------------------------------------------------------------------
        # Raumnamen aus Stellenbezeichnungen zusammenstellen
        # ---------------------------------------------------------------------------
        def stellenbezeichnungen(gruppe):
            bezeichnungen = sorted(set(
                (ma.stelle.bezeichnung if ma.stelle else "Unbekannt")
                for ma in gruppe
            ))
            return ", ".join(bezeichnungen)

        erkunder_raumname  = f"Branderkunder – {stellenbezeichnungen(erkunder_gruppe)}"
        raeumungs_raumname = f"Raeumungshelfer – {stellenbezeichnungen(raeumungs_gruppe)}"

        # Alias: Kurzform (max 64 Zeichen, lowercase, nur erlaubte Zeichen)
        erkunder_alias  = "prima-branderkunder"
        raeumungs_alias = "prima-raeumungshelfer"

        self.stdout.write(f"\nRaumname Branderkunder:\n  {erkunder_raumname}\n")
        self.stdout.write(f"\nRaumname Raeumungshelfer:\n  {raeumungs_raumname}\n")

        # ---------------------------------------------------------------------------
        # Ausgabe nach Stellenbezeichnung
        # ---------------------------------------------------------------------------
        self.stdout.write("\n--- BRANDERKUNDER ---")
        for ma in sorted(erkunder_gruppe, key=lambda m: m.stelle.bezeichnung if m.stelle else ""):
            stelle = ma.stelle.bezeichnung if ma.stelle else "?"
            self.stdout.write(f"  {stelle}")

        self.stdout.write("\n--- RAEUMUNGSHELFER ---")
        for ma in sorted(raeumungs_gruppe, key=lambda m: m.stelle.bezeichnung if m.stelle else ""):
            stelle = ma.stelle.bezeichnung if ma.stelle else "?"
            self.stdout.write(f"  {stelle}")

        if trocken:
            self.stdout.write(self.style.WARNING("\nTrockenlauf – keine Aenderungen gespeichert."))
            return

        # ---------------------------------------------------------------------------
        # Flags in der Datenbank setzen
        # ---------------------------------------------------------------------------
        erkunder_ids  = [ma.pk for ma in erkunder_gruppe]
        raeumungs_ids = [ma.pk for ma in raeumungs_gruppe]

        HRMitarbeiter.objects.filter(pk__in=erkunder_ids).update(ist_branderkunder=True)
        HRMitarbeiter.objects.filter(pk__in=raeumungs_ids).update(ist_raeumungshelfer=True)

        self.stdout.write(self.style.SUCCESS(
            f"\n[OK] {len(erkunder_ids)} Branderkunder gesetzt."
        ))
        self.stdout.write(self.style.SUCCESS(
            f"[OK] {len(raeumungs_ids)} Raeumungshelfer gesetzt."
        ))

        # ---------------------------------------------------------------------------
        # Matrix-Raeume erstellen und Mitglieder einladen
        # ---------------------------------------------------------------------------
        homeserver  = (
            getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
            or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
        )
        admin_token  = getattr(settings, "MATRIX_ADMIN_TOKEN", "")
        bot_token    = getattr(settings, "MATRIX_BOT_TOKEN", "")
        server_name  = getattr(settings, "MATRIX_SERVER_NAME", "")

        if not homeserver or not server_name:
            self.stderr.write("Matrix nicht konfiguriert – Einladungen uebersprungen.")
            return

        from config.kommunikation_utils import matrix_nutzer_in_raum_einladen

        for (gruppe, alias, raumname, setting_name) in [
            (erkunder_gruppe,  erkunder_alias,  erkunder_raumname,  "MATRIX_BRANDERKUNDER_ROOM_ID"),
            (raeumungs_gruppe, raeumungs_alias, raeumungs_raumname, "MATRIX_RAEUMUNGSHELFER_ROOM_ID"),
        ]:
            room_id = None

            # Raum erstellen via Client-API (als Bot-User)
            if bot_token:
                room_id = _matrix_raum_erstellen(raumname, alias, homeserver, bot_token)
                if room_id:
                    self.stdout.write(self.style.SUCCESS(
                        f"[OK] Matrix-Raum '{alias}' erstellt: {room_id}"
                    ))

            # Fallback: vorhandenen Raum per Alias suchen
            if not room_id and bot_token:
                room_id = _synapse_raum_id_aus_alias(alias, server_name, homeserver, bot_token)
                if room_id:
                    self.stdout.write(f"[INFO] Vorhandener Raum '{alias}': {room_id}")

            if not room_id:
                self.stderr.write(
                    f"[SKIP] Kein Raum fuer '{alias}' – bitte {setting_name} manuell setzen."
                )
                continue

            # Alle Mitglieder einladen
            ok_count = 0
            for ma in gruppe:
                stelle = getattr(ma, "stelle", None)
                if not stelle:
                    continue  # kein Stellen-Kuerzel – kein Matrix-Login
                kuerzel = stelle.kuerzel
                matrix_id = f"@{kuerzel}:{server_name}"
                if matrix_nutzer_in_raum_einladen(room_id, matrix_id):
                    ok_count += 1
                time.sleep(0.5)  # Synapse-Rate-Limit respektieren (~2 Einladungen/s)

            self.stdout.write(self.style.SUCCESS(
                f"[OK] {ok_count}/{len(gruppe)} Einladungen gesendet fuer '{alias}'"
            ))

    def _zuruecksetzen(self, trocken):
        """Entfernt alle Branderkunder- und Raeumungshelfer-Flags."""
        erkunder_count  = HRMitarbeiter.objects.filter(ist_branderkunder=True).count()
        raeumungs_count = HRMitarbeiter.objects.filter(ist_raeumungshelfer=True).count()
        self.stdout.write(
            f"Zuruecksetzen: {erkunder_count} Branderkunder, {raeumungs_count} Raeumungshelfer"
        )
        if not trocken:
            HRMitarbeiter.objects.filter(ist_branderkunder=True).update(ist_branderkunder=False)
            HRMitarbeiter.objects.filter(ist_raeumungshelfer=True).update(ist_raeumungshelfer=False)
            self.stdout.write(self.style.SUCCESS("Alle Flags zurueckgesetzt."))
        else:
            self.stdout.write(self.style.WARNING("Trockenlauf – keine Aenderungen."))
