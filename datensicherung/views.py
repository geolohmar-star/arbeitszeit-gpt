"""
Views fuer die Datensicherungs-Uebersicht (BSI CON.3).

Backup: pg_dump als SQL-Dump in /backups/
Restore-Test: temporaere Datenbank anlegen, Dump einspielen,
              Tabellen/Zeilen zaehlen, Ergebnis protokollieren,
              temporaere Datenbank wieder loeschen.
"""
import logging
import os
import subprocess
import threading
from datetime import timedelta
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import BackupProtokoll

logger = logging.getLogger(__name__)

# BSI CON.3: Restore-Test soll spaetestens alle 90 Tage stattfinden.
RESTORE_TEST_WARNUNG_TAGE = 60   # Gelb ab 60 Tagen
RESTORE_TEST_KRITISCH_TAGE = 90  # Rot ab 90 Tagen


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Datenbankverbindung parsen
# ---------------------------------------------------------------------------

def _db_params() -> dict:
    """Liest DATABASE_URL und gibt Verbindungsparameter als dict zurueck."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        from django.conf import settings
        db = settings.DATABASES["default"]
        return {
            "host": db.get("HOST", "localhost"),
            "port": str(db.get("PORT", "5432")),
            "name": db["NAME"],
            "user": db.get("USER", ""),
            "password": db.get("PASSWORD", ""),
        }
    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "name": parsed.path.lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def _backup_verzeichnis() -> str:
    """Pfad zum Backup-Verzeichnis (wird angelegt falls nicht vorhanden)."""
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backups")
    os.makedirs(base, exist_ok=True)
    return base


# ---------------------------------------------------------------------------
# Ampel-Berechnung
# ---------------------------------------------------------------------------

def _ampel_status():
    """
    Gibt (farbe, text) zurueck basierend auf dem Alter des letzten
    erfolgreichen Restore-Tests (BSI CON.3).
    """
    letzter = (
        BackupProtokoll.objects.filter(typ="restore_test", status="ok")
        .order_by("-abgeschlossen_am")
        .first()
    )
    if not letzter:
        return "rot", "Noch kein erfolgreicher Restore-Test durchgefuehrt"

    alter = (timezone.now() - letzter.abgeschlossen_am).days
    if alter >= RESTORE_TEST_KRITISCH_TAGE:
        return "rot", f"Letzter Restore-Test vor {alter} Tagen – BSI-Frist ueberschritten!"
    if alter >= RESTORE_TEST_WARNUNG_TAGE:
        return "gelb", f"Letzter Restore-Test vor {alter} Tagen – Bald faellig (max. 90 Tage)"
    return "gruen", f"Letzter Restore-Test vor {alter} Tagen – OK"


# ---------------------------------------------------------------------------
# Backup-Logik (laeuft im Hintergrund-Thread)
# ---------------------------------------------------------------------------

def _fuehre_backup_durch(protokoll_id: int) -> None:
    """Erstellt einen pg_dump-Dump und aktualisiert das Protokoll."""
    from .models import BackupProtokoll

    protokoll = BackupProtokoll.objects.get(pk=protokoll_id)
    db = _db_params()
    verz = _backup_verzeichnis()
    zeitstempel = timezone.now().strftime("%Y%m%d_%H%M%S")
    dateiname = f"prima_backup_{zeitstempel}.sql"
    dateipfad = os.path.join(verz, dateiname)

    env = os.environ.copy()
    if db["password"]:
        env["PGPASSWORD"] = db["password"]

    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["name"],
        "-f", dateipfad,
        "--no-password",
        "--format=plain",
    ]

    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "pg_dump fehlgeschlagen")

        dateig = os.path.getsize(dateipfad)

        # Tabellen zaehlen (Zeilen mit CREATE TABLE im Dump)
        with open(dateipfad, encoding="utf-8", errors="replace") as f:
            tabellen = sum(1 for line in f if line.startswith("CREATE TABLE"))

        protokoll.status = "ok"
        protokoll.dateiname = dateiname
        protokoll.dateigroesse_bytes = dateig
        protokoll.tabellen_anzahl = tabellen
        protokoll.abgeschlossen_am = timezone.now()
        protokoll.save()
        logger.info("Backup erfolgreich: %s (%d Bytes)", dateiname, dateig)

    except Exception as exc:
        protokoll.status = "fehler"
        protokoll.fehler_meldung = str(exc)
        protokoll.abgeschlossen_am = timezone.now()
        protokoll.save()
        logger.error("Backup fehlgeschlagen: %s", exc)


# ---------------------------------------------------------------------------
# Restore-Test-Logik (laeuft im Hintergrund-Thread)
# ---------------------------------------------------------------------------

def _fuehre_restore_test_durch(protokoll_id: int) -> None:
    """
    Restore-Test nach BSI CON.3:
    1. Letztes erfolgreiches Backup-SQL-Dump laden
    2. Temporaere Datenbank anlegen
    3. Dump einspielen
    4. Tabellen und Zeilen zaehlen
    5. Ergebnis protokollieren
    6. Temporaere Datenbank loeschen
    """
    import psycopg2
    from .models import BackupProtokoll

    protokoll = BackupProtokoll.objects.get(pk=protokoll_id)
    db = _db_params()
    verz = _backup_verzeichnis()

    # Letztes erfolgreiches Backup suchen
    letztes_backup = (
        BackupProtokoll.objects.filter(typ="backup", status="ok", dateiname__endswith=".sql")
        .order_by("-abgeschlossen_am")
        .first()
    )
    if not letztes_backup:
        protokoll.status = "fehler"
        protokoll.fehler_meldung = "Kein erfolgreiches Backup vorhanden – bitte zuerst Backup erstellen."
        protokoll.abgeschlossen_am = timezone.now()
        protokoll.save()
        return

    dump_pfad = os.path.join(verz, letztes_backup.dateiname)
    if not os.path.exists(dump_pfad):
        protokoll.status = "fehler"
        protokoll.fehler_meldung = f"Dump-Datei nicht gefunden: {letztes_backup.dateiname}"
        protokoll.abgeschlossen_am = timezone.now()
        protokoll.save()
        return

    temp_db = f"prima_restore_test_{protokoll_id}"
    env = os.environ.copy()
    if db["password"]:
        env["PGPASSWORD"] = db["password"]

    base_args = ["-h", db["host"], "-p", db["port"], "-U", db["user"], "--no-password"]

    def _psql(args, input_text=None):
        return subprocess.run(
            ["psql"] + base_args + args,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=300,
        )

    try:
        # Temporaere DB anlegen
        r = _psql(["-d", "postgres", "-c", f"CREATE DATABASE {temp_db};"])
        if r.returncode != 0:
            raise RuntimeError(f"CREATE DATABASE: {r.stderr}")

        try:
            # Dump einspielen
            r = _psql(["-d", temp_db, "-f", dump_pfad])
            # psql gibt returncode 0 auch bei Warnungen – Fehler erkennen
            if r.returncode != 0 and "ERROR" in r.stderr:
                raise RuntimeError(f"psql restore: {r.stderr[:500]}")

            # Tabellen zaehlen
            r = _psql([
                "-d", temp_db,
                "-t", "-c",
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
            ])
            tabellen_anzahl = int(r.stdout.strip()) if r.returncode == 0 else 0

            # Zeilen gesamt schaetzen (pg_class)
            r = _psql([
                "-d", temp_db,
                "-t", "-c",
                "SELECT coalesce(sum(reltuples::bigint), 0) FROM pg_class "
                "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace;"
            ])
            zeilen_gesamt = int(float(r.stdout.strip())) if r.returncode == 0 else 0

            protokoll.status = "ok"
            protokoll.dateiname = letztes_backup.dateiname
            protokoll.tabellen_anzahl = tabellen_anzahl
            protokoll.zeilen_gesamt = zeilen_gesamt
            protokoll.abgeschlossen_am = timezone.now()
            protokoll.save()
            logger.info(
                "Restore-Test erfolgreich: %d Tabellen, ~%d Zeilen",
                tabellen_anzahl, zeilen_gesamt,
            )

        finally:
            # Temporaere DB in jedem Fall loeschen
            _psql(["-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {temp_db};"])

    except Exception as exc:
        protokoll.status = "fehler"
        protokoll.fehler_meldung = str(exc)
        protokoll.abgeschlossen_am = timezone.now()
        protokoll.save()
        logger.error("Restore-Test fehlgeschlagen: %s", exc)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
def uebersicht(request):
    """BSI CON.3 Datensicherungs-Dashboard."""
    if not request.user.is_staff:
        return HttpResponse("Kein Zugriff – nur fuer Administratoren.", status=403)

    ampel_farbe, ampel_text = _ampel_status()

    letztes_backup = (
        BackupProtokoll.objects.filter(typ="backup", status="ok")
        .order_by("-abgeschlossen_am")
        .first()
    )
    letzter_restore = (
        BackupProtokoll.objects.filter(typ="restore_test", status="ok")
        .order_by("-abgeschlossen_am")
        .first()
    )
    laufende = BackupProtokoll.objects.filter(status="laufend")
    protokolle = BackupProtokoll.objects.all()[:50]

    return render(request, "datensicherung/uebersicht.html", {
        "ampel_farbe": ampel_farbe,
        "ampel_text": ampel_text,
        "letztes_backup": letztes_backup,
        "letzter_restore": letzter_restore,
        "laufende": laufende,
        "protokolle": protokolle,
        "warnung_tage": RESTORE_TEST_WARNUNG_TAGE,
        "kritisch_tage": RESTORE_TEST_KRITISCH_TAGE,
    })


@login_required
@require_POST
def backup_ausloesen(request):
    """Startet einen neuen Datenbank-Backup-Vorgang im Hintergrund."""
    if not request.user.is_staff:
        return HttpResponse("Kein Zugriff.", status=403)

    protokoll = BackupProtokoll.objects.create(
        typ="backup",
        status="laufend",
        erstellt_von=request.user,
    )

    t = threading.Thread(
        target=_fuehre_backup_durch,
        args=(protokoll.pk,),
        daemon=True,
    )
    t.start()

    return redirect("datensicherung:uebersicht")


@login_required
@require_POST
def restore_test_ausloesen(request):
    """Startet einen Restore-Test im Hintergrund."""
    if not request.user.is_staff:
        return HttpResponse("Kein Zugriff.", status=403)

    protokoll = BackupProtokoll.objects.create(
        typ="restore_test",
        status="laufend",
        erstellt_von=request.user,
    )

    t = threading.Thread(
        target=_fuehre_restore_test_durch,
        args=(protokoll.pk,),
        daemon=True,
    )
    t.start()

    return redirect("datensicherung:uebersicht")


@login_required
def status_partial(request):
    """
    HTMX-Partial: Gibt nur die Protokolltabelle und Ampel zurueck.
    Wird alle 5 Sekunden abgefragt solange ein Vorgang laeuft.
    """
    if not request.user.is_staff:
        return HttpResponse("", status=403)

    ampel_farbe, ampel_text = _ampel_status()
    laufende = BackupProtokoll.objects.filter(status="laufend")
    protokolle = BackupProtokoll.objects.all()[:50]

    return render(request, "datensicherung/_status_partial.html", {
        "ampel_farbe": ampel_farbe,
        "ampel_text": ampel_text,
        "laufende": laufende,
        "protokolle": protokolle,
    })
