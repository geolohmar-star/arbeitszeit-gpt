from .views import kann_verwalten


def stellenportal_context(request):
    """Stellt stellenportal_kann_verwalten und neue_bewerbungen_anzahl bereit."""
    if not request.user.is_authenticated:
        return {
            "stellenportal_kann_verwalten": False,
            "stellenportal_neue_bewerbungen": 0,
        }

    verwalten = kann_verwalten(request.user)
    from .models import Ausschreibung, Bewerbung
    offene_stellen = Ausschreibung.objects.filter(status="aktiv", veroeffentlicht=True).count()
    neue = Bewerbung.objects.filter(status="eingegangen").count() if verwalten else 0

    return {
        "stellenportal_kann_verwalten": verwalten,
        "stellenportal_neue_bewerbungen": neue,
        "stellenportal_offene_stellen": offene_stellen,
    }
