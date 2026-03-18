from formulare.models import TeamQueue
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

    # Fuehrungskraft: AL, BL oder GF (duerfen Token beantragen)
    ist_fuehrungskraft = request.user.is_staff
    if not ist_fuehrungskraft:
        try:
            rolle = request.user.hr_mitarbeiter.rolle
            ist_fuehrungskraft = rolle in ("gf", "bereichsleiter", "abteilungsleiter")
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

    # Security-Team: Mitglieder der sec-token Queue
    ist_security_mitglied = request.user.is_staff
    if not ist_security_mitglied:
        try:
            ist_security_mitglied = TeamQueue.objects.filter(
                kuerzel="sec-token", mitglieder=request.user
            ).exists()
        except Exception:
            pass

    # Badge: offene Token-Antraege (nur fuer Security-Team / Staff)
    token_anfragen_anzahl = 0
    if ist_security_mitglied:
        try:
            from raumbuch.models import ZutrittsToken
            token_anfragen_anzahl = ZutrittsToken.objects.filter(
                status="beantragt"
            ).count()
        except Exception:
            pass

    # Arbeitsschutz-Beauftragter: Kuerzel al_as oder Staff
    ist_arbeitsschutz = request.user.is_staff
    if not ist_arbeitsschutz:
        try:
            ist_arbeitsschutz = (
                request.user.hr_mitarbeiter.stelle.kuerzel == "al_as"
            )
        except Exception:
            pass

    # Sicherheits-Zugang: Security-Stellen oder Staff
    _SECURITY_KUERZEL = frozenset([
        "al_sec", "sv_sec",
        "ma_sec1", "ma_sec2", "ma_sec3", "ma_sec4",
        "pf_sec", "al_as", "ba_as", "gf1", "gf_tech", "gf_verw",
    ])
    ist_security_zugang = request.user.is_staff or ist_arbeitsschutz
    if not ist_security_zugang:
        try:
            ist_security_zugang = (
                request.user.hr_mitarbeiter.stelle.kuerzel in _SECURITY_KUERZEL
            )
        except Exception:
            pass

    return {
        "ist_facility_mitglied": ist_facility_mitglied,
        "facility_queue_anzahl": facility_queue_anzahl,
        "ist_vorgesetzter": ist_vorgesetzter,
        "ist_fuehrungskraft": ist_fuehrungskraft,
        "al_queue_anzahl": al_queue_anzahl,
        "ist_security_mitglied": ist_security_mitglied,
        "token_anfragen_anzahl": token_anfragen_anzahl,
        "ist_arbeitsschutz": ist_arbeitsschutz,
        "ist_security_zugang": ist_security_zugang,
    }
