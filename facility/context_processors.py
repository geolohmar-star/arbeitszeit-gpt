from .models import FacilityTeam, Stoermeldung


def facility_context(request):
    """Stellt facility-bezogene Variablen fuer alle Templates bereit."""
    if not request.user.is_authenticated:
        return {}

    user_teams = FacilityTeam.objects.filter(mitglieder=request.user)
    ist_facility_mitglied = user_teams.exists() or request.user.is_staff

    # Badge: Anzahl offener (unbearbeiteter) Stoermeldungen in den eigenen Teams
    facility_queue_anzahl = 0
    if ist_facility_mitglied:
        if request.user.is_staff:
            # Staff sieht alle offenen Meldungen
            facility_queue_anzahl = Stoermeldung.objects.filter(
                status="offen"
            ).count()
        else:
            # Teammitglied sieht nur seine Kategorien
            kategorien = list(user_teams.values_list("kategorie", flat=True))
            facility_queue_anzahl = Stoermeldung.objects.filter(
                status="offen", kategorie__in=kategorien
            ).count()

    return {
        "ist_facility_mitglied": ist_facility_mitglied,
        "facility_queue_anzahl": facility_queue_anzahl,
    }
