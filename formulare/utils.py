"""Hilfsfunktionen fuer die formulare-App.

Hier liegen Funktionen die sowohl von Views als auch von
Management Commands genutzt werden.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def genehmigende_stelle(antragsteller_ma, dauer_tage=0):
    """Ermittelt die verantwortliche Stelle fuer einen Antrag.

    Logik:
    1. HRMitarbeiter des Antragstellers suchen (via arbeitszeit.Mitarbeiter.user)
    2. Uebergeordnete Stelle des Antragstellers ermitteln
    3. Fallback-Schleife (max. 5 Ebenen): hoch gehen solange Stelle unbesetzt
    4. Kompetenzrahmen: eskalieren wenn dauer_tage > max_urlaubstage_genehmigung (>0)
    5. verantwortliche_stelle() aufrufen (Vertretung/Delegation)

    Gibt None zurueck wenn keine Stelle ermittelt werden kann.
    """
    # HRMitarbeiter via User ermitteln
    user = getattr(antragsteller_ma, "user", None)
    if user is None:
        return None

    try:
        hr_ma = user.hr_mitarbeiter
    except Exception:
        return None

    if hr_ma.stelle is None:
        return None

    # Uebergeordnete Stelle des Antragstellers holen
    kandidat = hr_ma.stelle.uebergeordnete_stelle
    if kandidat is None:
        return None

    # Fallback-Schleife: bis zu 5 Ebenen hochgehen wenn Stelle unbesetzt
    MAX_EBENEN = 5
    for _ in range(MAX_EBENEN):
        if kandidat is None:
            return None
        if kandidat.ist_besetzt:
            break
        kandidat = kandidat.uebergeordnete_stelle
    else:
        # Alle Ebenen durchlaufen, letzten Kandidaten nehmen
        if kandidat is None:
            return None

    # Kompetenzrahmen pruefen: bei Ueberschreitung eskalieren
    if dauer_tage > 0 and kandidat.max_urlaubstage_genehmigung > 0:
        if dauer_tage > kandidat.max_urlaubstage_genehmigung:
            eskalations_stelle = kandidat.uebergeordnete_stelle
            if eskalations_stelle is not None:
                kandidat = eskalations_stelle

    # Delegation und Vertretung aufloesen
    return kandidat.verantwortliche_stelle()
