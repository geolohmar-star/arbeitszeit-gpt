from .models import FacilityTeam


def facility_context(request):
    """Stellt facility-bezogene Variablen fuer alle Templates bereit."""
    if not request.user.is_authenticated:
        return {}
    ist_facility_mitglied = (
        FacilityTeam.objects.filter(mitglieder=request.user).exists()
        or request.user.is_staff
    )
    return {"ist_facility_mitglied": ist_facility_mitglied}
