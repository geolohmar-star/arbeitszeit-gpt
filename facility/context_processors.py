from hr.models import HRMitarbeiter

from .models import FacilityTeam, Stoermeldung


def facility_context(request):
    """Stellt facility-bezogene Variablen fuer alle Templates bereit."""
    if not request.user.is_authenticated:
        return {}

    # Einmal auswerten – danach nur noch Python-Listenoperationen (kein zweites DB-Hit)
    if request.user.is_staff:
        ist_facility_mitglied = True
        kategorien = []  # Staff-Pfad braucht keinen Kategorie-Filter
    else:
        kategorien = list(
            FacilityTeam.objects.filter(mitglieder=request.user)
            .values_list("kategorie", flat=True)
        )
        ist_facility_mitglied = bool(kategorien)

    # Vorgesetzten-Zugang: Hat der User direkte Berichte?
    ist_vorgesetzter = False
    try:
        ist_vorgesetzter = request.user.hr_mitarbeiter.direkte_berichte.exists()
    except Exception:
        pass

    # Badge: Anzahl offener (unbearbeiteter) Stoermeldungen in den eigenen Teams
    facility_queue_anzahl = 0
    if ist_facility_mitglied:
        if request.user.is_staff:
            facility_queue_anzahl = Stoermeldung.objects.filter(
                status="offen"
            ).count()
        else:
            facility_queue_anzahl = Stoermeldung.objects.filter(
                status="offen", kategorie__in=kategorien
            ).count()

    # Badge: Anzahl weitergeleiteter Stoermeldungen fuer den AL
    if request.user.is_staff:
        al_queue_anzahl = Stoermeldung.objects.filter(status="weitergeleitet").count()
    else:
        al_queue_anzahl = Stoermeldung.objects.filter(
            status="weitergeleitet", eskaliert_an=request.user
        ).count()

    return {
        "ist_facility_mitglied": ist_facility_mitglied,
        "facility_queue_anzahl": facility_queue_anzahl,
        "ist_vorgesetzter": ist_vorgesetzter,
        "al_queue_anzahl": al_queue_anzahl,
    }
