"""Context Processor: Erste-Hilfe-Status fuer die Navbar und Einsatz-Banner."""


def _banner_aus_vorfall(vorfall):
    """Gibt Banner-Felder fuer einen offenen Vorfall zurueck."""
    from django.utils import timezone
    jetzt = timezone.localtime(vorfall.erstellt_am)
    return {
        "eh_banner_aktiv": True,
        "eh_banner_ort": vorfall.ort,
        "eh_banner_zeit": jetzt.strftime("%H:%M"),
        "eh_banner_pk": vorfall.pk,
    }


_BANNER_LEER = {
    "eh_banner_aktiv": False,
    "eh_banner_ort": "",
    "eh_banner_zeit": "",
    "eh_banner_pk": None,
}


def eh_badge(request):
    """Gibt EH-Statusinformationen fuer die Navbar und den Einsatz-Banner zurueck.

    Verantwortliche (Betriebsarzt / al_as / Staff): Anzahl offener Vorfaelle.
      Banner: immer aktiv solange Vorfall offen (bis Vorfall geschlossen).
    Ersthelfer: Link zum aktuellen Vorfall.
      Banner: aktiv bis der Ersthelfer selbst eine Rueckmeldung abgegeben hat.
    Melder: Banner aktiv bis die erste Rueckmeldung eingeht (Hilfe ist unterwegs).
    """
    leer = {
        "eh_offene_vorfaelle": 0,
        "ist_eh_verantwortlicher": False,
        "ist_eh_ersthelfer": False,
        "eh_laufender_vorfall_pk": None,
        **_BANNER_LEER,
    }

    if not request.user.is_authenticated:
        return leer

    from .models import ErsteHilfeVorfall, ErsteHilfeRueckmeldung

    # Verantwortlicher?
    ist_verantwortlicher = False
    if request.user.is_staff:
        ist_verantwortlicher = True
    elif request.user.has_perm("ersthelfe.view_alle_vorfaelle"):
        ist_verantwortlicher = True
    else:
        try:
            stelle = request.user.hr_mitarbeiter.stelle
            if stelle and (stelle.ist_betriebsarzt or stelle.kuerzel == "al_as"):
                ist_verantwortlicher = True
        except Exception:
            pass

    if ist_verantwortlicher:
        offene = list(
            ErsteHilfeVorfall.objects
            .filter(status=ErsteHilfeVorfall.STATUS_OFFEN)
            .order_by("-erstellt_am")
        )
        # Verantwortliche sehen den Banner bis ein Ersthelfer "Bin vor Ort" meldet
        if offene:
            ersthelfer_vor_ort = ErsteHilfeRueckmeldung.objects.filter(
                vorfall=offene[0],
                status="am_ort"
            ).exists()
            banner = _BANNER_LEER if ersthelfer_vor_ort else _banner_aus_vorfall(offene[0])
        else:
            banner = _BANNER_LEER
        return {
            "eh_offene_vorfaelle": len(offene),
            "ist_eh_verantwortlicher": True,
            "ist_eh_ersthelfer": False,
            "eh_laufender_vorfall_pk": None,
            **banner,
        }

    # Ersthelfer?
    ist_ersthelfer = False
    try:
        ist_ersthelfer = request.user.hr_mitarbeiter.ist_ersthelfer
    except Exception:
        pass

    if not ist_ersthelfer:
        # Melder eines offenen Vorfalls: Banner bis erste Rueckmeldung eingeht
        laufender = (
            ErsteHilfeVorfall.objects
            .filter(status=ErsteHilfeVorfall.STATUS_OFFEN, gemeldet_von=request.user)
            .order_by("-erstellt_am")
            .first()
        )
        if laufender:
            hat_rueckmeldung = ErsteHilfeRueckmeldung.objects.filter(
                vorfall=laufender
            ).exists()
            banner = _BANNER_LEER if hat_rueckmeldung else _banner_aus_vorfall(laufender)
            return {**leer, **banner}
        return leer

    # Ersthelfer: Banner nur anzeigen wenn noch keine eigene Rueckmeldung
    laufender = (
        ErsteHilfeVorfall.objects
        .filter(status=ErsteHilfeVorfall.STATUS_OFFEN)
        .order_by("-erstellt_am")
        .first()
    )
    if laufender:
        try:
            hat_selbst_gemeldet = ErsteHilfeRueckmeldung.objects.filter(
                vorfall=laufender,
                ersthelfer=request.user.hr_mitarbeiter
            ).exists()
        except Exception:
            hat_selbst_gemeldet = False
        banner = _BANNER_LEER if hat_selbst_gemeldet else _banner_aus_vorfall(laufender)
    else:
        banner = _BANNER_LEER

    return {
        "eh_offene_vorfaelle": 0,
        "ist_eh_verantwortlicher": False,
        "ist_eh_ersthelfer": True,
        "eh_laufender_vorfall_pk": laufender.pk if laufender else None,
        **banner,
    }
