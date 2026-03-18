from django.utils import timezone


def sicherheit_banner(request):
    """Gibt AMOK- und Brand-Banner-Status fuer ALLE eingeloggten Nutzer zurueck.

    Stille Alarme erscheinen absichtlich NICHT im Banner.
    Brand-Banner nur bei aktivem Evakuierungsstatus.
    """
    leer = {
        "amok_banner_aktiv": False,
        "amok_banner_ort": "",
        "amok_banner_zeit": "",
        "amok_alarm_pk": None,
        "brand_banner_aktiv": False,
        "brand_banner_ort": "",
        "brand_banner_zeit": "",
        "brand_alarm_pk": None,
    }

    if not request.user.is_authenticated:
        return leer

    from .models import Brandalarm, SicherheitsAlarm

    # AMOK-Status
    amok = (
        SicherheitsAlarm.objects
        .filter(typ=SicherheitsAlarm.TYP_AMOK, status=SicherheitsAlarm.STATUS_AKTIV)
        .order_by("-erstellt_am")
        .first()
    )
    amok_daten = {}
    if amok:
        zeit = timezone.localtime(amok.erstellt_am).strftime("%H:%M")
        amok_daten = {
            "amok_banner_aktiv": True,
            "amok_banner_ort": amok.ort,
            "amok_banner_zeit": zeit,
            "amok_alarm_pk": amok.pk,
        }

    # Brand-Status (nur bei Evakuierung sichtbar fuer alle)
    brand = (
        Brandalarm.objects
        .filter(status=Brandalarm.STATUS_EVAKUIERUNG)
        .order_by("-erstellt_am")
        .first()
    )
    brand_daten = {}
    if brand:
        zeit = timezone.localtime(brand.erstellt_am).strftime("%H:%M")
        brand_daten = {
            "brand_banner_aktiv": True,
            "brand_banner_ort": brand.ort_aktuell,
            "brand_banner_zeit": zeit,
            "brand_alarm_pk": brand.pk,
        }

    return {**leer, **amok_daten, **brand_daten}
