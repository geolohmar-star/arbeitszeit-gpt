#!/bin/sh
# PRIMA Scheduler
#
# Laeuft als eigener Docker-Container.
# Aufgaben:
#   - Alle 30 Sek:  Brand- und EH-Rueckmeldungen pollen (Matrix-DMs)
#   - Jede Minute:  Sitzungs-Erinnerungen pruefen (Matrix-Nachrichten)
#   - Taeglich 2:00 Uhr: Matrix-Accounts synchronisieren + Passwort setzen

LETZTER_SYNC_TAG=""
LETZTER_POLL=0

while true; do
    # Alle 30 Sekunden: Brand- und EH-Rueckmeldungen pollen
    JETZT=$(date +%s)
    if [ $((JETZT - LETZTER_POLL)) -ge 30 ]; then
        python manage.py brand_rueckmeldung_poller
        python manage.py eh_rueckmeldung_poller
        LETZTER_POLL=$JETZT
    fi

    # Minuetliche Aufgaben
    python manage.py matrix_sitzung_erinnerungen

    # Taeglich um 2:00 Uhr
    AKTUELLE_STUNDE=$(date +"%H")
    AKTUELLER_TAG=$(date +"%Y-%m-%d")

    if [ "$AKTUELLE_STUNDE" = "02" ] && [ "$AKTUELLER_TAG" != "$LETZTER_SYNC_TAG" ]; then
        echo "[$(date)] Naechtlicher Sync startet..."
        python manage.py matrix_accounts_sync
        python manage.py matrix_passwort_setzen
        LETZTER_SYNC_TAG="$AKTUELLER_TAG"
        echo "[$(date)] Naechtlicher Sync abgeschlossen."
    fi

    sleep 30
done
