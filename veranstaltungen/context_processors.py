from django.db.models import Q


def veranstaltungen_context(request):
    """Stellt veranstaltungen_offen_anzahl fuer die Navbar bereit."""
    if not request.user.is_authenticated:
        return {"veranstaltungen_offen_anzahl": 0}

    from .models import Feier

    qs = Feier.objects.filter(status="anmeldung_offen")
    qs = _filter_nach_sichtbarkeit(qs, request.user)
    return {"veranstaltungen_offen_anzahl": qs.count()}


def _filter_nach_sichtbarkeit(qs, user):
    """Filtert Feier-QuerySet nach Sichtbarkeit fuer den User.

    - Staff, GF, Bereichsleiter: sehen alles
    - Abteilungsleiter: Unternehmen + eigener Bereich + eigene Abteilung
    - Alle anderen: nur Unternehmen + passender Bereich + passende Abteilung
    """
    if user.is_staff:
        return qs

    try:
        hrma = user.hr_mitarbeiter
    except Exception:
        return qs.filter(reichweite="unternehmen")

    if hrma.rolle in ("gf", "bereichsleiter"):
        return qs

    q = Q(reichweite="unternehmen")

    if hrma.bereich:
        q |= Q(reichweite="bereich", bereich=hrma.bereich)

    if hrma.abteilung:
        q |= Q(reichweite="abteilung", abteilung=hrma.abteilung)
        # Abteilungsleiter sehen zusaetzlich den gesamten Bereich
        if hrma.rolle == "abteilungsleiter" and hrma.abteilung.bereich:
            q |= Q(reichweite="bereich", bereich=hrma.abteilung.bereich)

    return qs.filter(q)
