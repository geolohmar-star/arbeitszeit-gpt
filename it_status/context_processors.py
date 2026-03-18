from .models import ITSystem


def it_status_ampel(request):
    """Liefert den schlechtesten aktuellen Systemstatus fuer die Navbar-Ampel
    sowie ein Flag ob der eingeloggte User zum IT-Helpdesk gehoert."""
    if not request.user.is_authenticated:
        return {}

    prioritaet = {
        ITSystem.STATUS_GESTOERT: 3,
        ITSystem.STATUS_WARNUNG:  2,
        ITSystem.STATUS_WARTUNG:  1,
        ITSystem.STATUS_OK:       0,
    }

    gesamt = ITSystem.STATUS_OK
    try:
        for s in ITSystem.objects.filter(aktiv=True).only("status"):
            if prioritaet.get(s.status, 0) > prioritaet.get(gesamt, 0):
                gesamt = s.status
    except Exception:
        pass

    farbe = {
        ITSystem.STATUS_OK:       "success",
        ITSystem.STATUS_WARNUNG:  "warning",
        ITSystem.STATUS_GESTOERT: "danger",
        ITSystem.STATUS_WARTUNG:  "secondary",
    }.get(gesamt, "secondary")

    ist_helpdesk = (
        request.user.is_staff
        or request.user.groups.filter(name="it_helpdesk").exists()
    )

    return {
        "it_ampel_status": gesamt,
        "it_ampel_farbe":  farbe,
        "ist_helpdesk":    ist_helpdesk,
    }
