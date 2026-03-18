import json
import logging
import threading
import time
import urllib.error
import urllib.request

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Brandalarm, BranderkunderToken, SicherheitsAlarm

logger = logging.getLogger(__name__)

# Kuerzel aller sicherheitsrelevanten Stellen
_SECURITY_KUERZEL = frozenset([
    "al_sec", "sv_sec",
    "ma_sec1", "ma_sec2", "ma_sec3", "ma_sec4",
    "pf_sec", "al_as", "ba_as", "gf1", "gf_tech", "gf_verw",
])


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _ist_security(user):
    """Prueft ob ein User Security-Zugriff hat.

    Gibt True zurueck wenn der User Staff ist oder eine Security-Stelle besetzt.
    """
    if user.is_staff:
        return True
    try:
        kuerzel = user.hr_mitarbeiter.stelle.kuerzel
        return kuerzel in _SECURITY_KUERZEL
    except Exception:
        return False


def _benachrichtige_security(alarm):
    """Sendet Matrix-Ping und ntfy-Push an Security-Raum.

    Bei AMOK: dringende Benachrichtigung mit @room-Mention.
    Bei Stillem Alarm: diskrete Benachrichtigung ohne @room.
    Faellt bei Fehlern graceful ab – kein Exception-Bubble.
    """
    from django.conf import settings

    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    bot_token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    security_room = getattr(settings, "MATRIX_SECURITY_PING_ROOM_ID", "")
    ntfy_url = getattr(settings, "NTFY_URL", "").rstrip("/")

    jetzt = timezone.localtime(alarm.erstellt_am)
    zeit_str = jetzt.strftime("%H:%M")
    ort_str = alarm.ort or "unbekannt"

    # Matrix-Ping
    if homeserver and bot_token and security_room:
        _matrix_security_ping(
            homeserver, bot_token, security_room, alarm, ort_str, zeit_str
        )

    # ntfy-Push
    if ntfy_url:
        _ntfy_security_senden(alarm, ort_str, zeit_str, ntfy_url, settings)


def _matrix_security_ping(homeserver, bot_token, security_room, alarm, ort_str, zeit_str):
    """Sendet Nachricht in den SECURITY_PING Matrix-Raum."""
    if alarm.typ == SicherheitsAlarm.TYP_AMOK:
        body_text = (
            f"@room AMOK-ALARM - Ort: {ort_str} - {zeit_str} Uhr - SOFORT HANDELN"
        )
        formatted = (
            f'<strong><a href="https://matrix.to/#/{security_room}">@room</a>'
            f" AMOK-ALARM</strong> \u2013 Ort: <strong>{ort_str}</strong>"
            f" \u2013 {zeit_str} Uhr \u2013 SOFORT HANDELN"
        )
    else:
        body_text = (
            f"STILLER ALARM - Ort: {ort_str} - {zeit_str} Uhr - Diskret reagieren"
        )
        formatted = (
            f"STILLER ALARM \u2013 Ort: <strong>{ort_str}</strong>"
            f" \u2013 {zeit_str} Uhr \u2013 Diskret reagieren"
        )

    txn_id = str(int(time.time() * 1000))
    url = (
        f"{homeserver}/_matrix/client/v3/rooms/{security_room}"
        f"/send/m.room.message/{txn_id}"
    )
    payload = json.dumps({
        "msgtype": "m.text",
        "body": body_text,
        "format": "org.matrix.custom.html",
        "formatted_body": formatted,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
        logger.info(
            "Security Matrix-Ping gesendet fuer Alarm %s (%s).",
            alarm.pk, alarm.typ,
        )
    except Exception as exc:
        logger.warning(
            "Security Matrix-Ping fehlgeschlagen (nicht kritisch): %s", exc
        )


def _ntfy_push(ntfy_url, topic, title, body, priority="urgent", click_url=""):
    """Generischer ntfy-Push. Faellt graceful ab.

    click_url wird als Click-Header gesetzt – Tippen auf die Notification
    oeffnet die URL direkt im Browser.
    """
    if not ntfy_url or not topic:
        return
    headers = {
        "Title": title,
        "Priority": priority,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if click_url:
        headers["Click"] = click_url
    try:
        req = urllib.request.Request(
            f"{ntfy_url}/{topic}",
            data=body.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("ntfy Push an Topic %s gesendet.", topic)
    except Exception as exc:
        logger.warning("ntfy Push an %s fehlgeschlagen (nicht kritisch): %s", topic, exc)


def _ntfy_security_senden(alarm, ort_str, zeit_str, ntfy_url, settings):
    """Sendet Push-Benachrichtigung via ntfy an Security-Topic."""
    if alarm.typ == SicherheitsAlarm.TYP_AMOK:
        topic = getattr(settings, "NTFY_AMOK_TOPIC", "amok-alarm-prima")
        priority = "urgent"
        title = "AMOK-ALARM"
        nachricht = f"Ort: {ort_str} | {zeit_str} Uhr | Alarm #{alarm.pk}"
    else:
        topic = getattr(settings, "NTFY_STILL_TOPIC", "security-intern")
        priority = "high"
        title = "Stiller Alarm"
        nachricht = f"Ort: {ort_str} | {zeit_str} Uhr | Alarm #{alarm.pk}"

    url = f"{ntfy_url}/{topic}"
    req = urllib.request.Request(
        url,
        data=nachricht.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": priority,
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
        logger.info(
            "ntfy Security-Push gesendet fuer Alarm %s (%s).",
            alarm.pk, alarm.typ,
        )
    except Exception as exc:
        logger.warning(
            "ntfy Security-Push fehlgeschlagen (nicht kritisch): %s", exc
        )


# ---------------------------------------------------------------------------
# Oeffentliche Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def alarm_ausloesen(request):
    """Loest einen Sicherheitsalarm aus (AMOK oder Stiller Alarm).

    AMOK erfordert eine explizite Bestaetigungseingabe ("AMOK").
    Stiller Alarm liefert JSON zurueck damit die Seite nicht neu laedt.
    """
    typ = request.POST.get("typ", "").strip()
    ort = request.POST.get("ort", "").strip()

    if typ not in (SicherheitsAlarm.TYP_AMOK, SicherheitsAlarm.TYP_STILL):
        return JsonResponse({"ok": False, "fehler": "Ungueltiger Alarm-Typ."}, status=400)

    if typ == SicherheitsAlarm.TYP_AMOK:
        # AMOK erfordert explizite Textbestaetigung
        bestaetigung = request.POST.get("bestaetigung", "").strip()
        if bestaetigung != "AMOK":
            return render(request, "sicherheit/amok_bestaetigung_fehler.html", {
                "fehler": "Bitte genau das Wort AMOK eingeben um den Alarm auszuloesen.",
            }, status=400)

    # Kein Ort angegeben: Buero-Ort des Meldenden aus HR-Stammdaten verwenden
    if not ort:
        ort = _ermittle_ort_aus_hr(request.user)

    alarm = SicherheitsAlarm.objects.create(
        typ=typ,
        ort=ort,
        ausgeloest_von=request.user,
    )

    try:
        _benachrichtige_security(alarm)
    except Exception:
        logger.exception(
            "Fehler beim Benachrichtigen Security (Alarm %s)", alarm.pk
        )

    if typ == SicherheitsAlarm.TYP_AMOK:
        return redirect("sicherheit:amok_bestaetigung", pk=alarm.pk)

    # Stiller Alarm: kein sichtbares Feedback – JSON-Antwort
    return JsonResponse({"ok": True, "pk": alarm.pk})


@login_required
def amok_bestaetigung_view(request, pk):
    """Zeigt Verhaltensregeln nach AMOK-Ausloesung."""
    alarm = get_object_or_404(SicherheitsAlarm, pk=pk, typ=SicherheitsAlarm.TYP_AMOK)
    return render(request, "sicherheit/amok_bestaetigung.html", {"alarm": alarm})


@login_required
@require_POST
def alarm_schliessen(request, pk):
    """Schliesst einen aktiven Alarm ab – nur fuer Security-Personal und Staff."""
    if not _ist_security(request.user):
        raise PermissionDenied

    alarm = get_object_or_404(
        SicherheitsAlarm, pk=pk, status=SicherheitsAlarm.STATUS_AKTIV
    )
    alarm.status = SicherheitsAlarm.STATUS_GESCHLOSSEN
    alarm.geschlossen_am = timezone.now()
    alarm.geschlossen_von = request.user
    notiz = request.POST.get("notiz", "").strip()
    if notiz:
        alarm.notiz = notiz
    ort = request.POST.get("ort", "").strip()
    if ort:
        alarm.ort = ort
    alarm.save(update_fields=[
        "status", "geschlossen_am", "geschlossen_von", "notiz", "ort"
    ])

    logger.info(
        "Alarm %s von %s geschlossen.", alarm.pk, request.user.username
    )
    return redirect("sicherheit:alarm_liste")


@login_required
def sicherheit_dashboard(request):
    """Startseite fuer Security (al_sec) und Arbeitsschutz (al_as).

    Zeigt aktive Brandalarme, aktive Sicherheitsalarme und Schnellzugriff.
    """
    if not _ist_security(request.user):
        raise PermissionDenied

    aktive_brandalarme = (
        Brandalarm.objects
        .exclude(status=Brandalarm.STATUS_GESCHLOSSEN)
        .select_related("gemeldet_von")
        .prefetch_related("erkunder_tokens__erkunder")
        .order_by("-erstellt_am")
    )
    aktive_sicherheitsalarme = (
        SicherheitsAlarm.objects
        .filter(status=SicherheitsAlarm.STATUS_AKTIV)
        .select_related("ausgeloest_von")
        .order_by("-erstellt_am")
    )
    return render(request, "sicherheit/sicherheit_dashboard.html", {
        "aktive_brandalarme": aktive_brandalarme,
        "aktive_sicherheitsalarme": aktive_sicherheitsalarme,
        "ist_arbeitsschutz": _ist_arbeitsschutz(request.user),
    })


@login_required
def alarm_liste(request):
    """Liste aller Sicherheitsalarme – nur fuer Security-Personal und Staff."""
    if not _ist_security(request.user):
        raise PermissionDenied

    alarme = (
        SicherheitsAlarm.objects
        .select_related("ausgeloest_von", "geschlossen_von")
        .order_by("-erstellt_am")
    )
    return render(request, "sicherheit/alarm_liste.html", {"alarme": alarme})


@login_required
def alarm_detail(request, pk):
    """Detailansicht eines Sicherheitsalarms – nur fuer Security-Personal und Staff."""
    if not _ist_security(request.user):
        raise PermissionDenied

    alarm = get_object_or_404(
        SicherheitsAlarm.objects.select_related("ausgeloest_von", "geschlossen_von"),
        pk=pk,
    )

    # Aktuellen Raum des Meldenden aus Raumbuch-Belegung nachschlagen
    aktueller_raum = None
    if alarm.ausgeloest_von:
        try:
            from datetime import date

            from raumbuch.models import Belegung

            heute = date.today()
            belegung = (
                Belegung.objects
                .filter(
                    mitarbeiter=alarm.ausgeloest_von.hr_mitarbeiter,
                    von__lte=heute,
                )
                .filter(Q(bis__isnull=True) | Q(bis__gte=heute))
                .select_related("raum")
                .order_by("-von")
                .first()
            )
            if belegung:
                raum = belegung.raum
                aktueller_raum = (
                    f"Raum {raum.raumnummer} – {raum.raumname}"
                    if raum.raumname
                    else f"Raum {raum.raumnummer}"
                )
        except Exception:
            pass

    return render(request, "sicherheit/alarm_detail.html", {
        "alarm": alarm,
        "aktueller_raum": aktueller_raum,
    })


@login_required
def security_alarm_status_json(request):
    """JSON-Endpunkt fuer Security-Personal: alle aktiven Alarme mit Detail-URLs.

    Gibt Brandalarme (alle aktiven Status) und Sicherheitsalarme zurueck.
    Nur fuer Security-Stellen zugaenglich.
    """
    if not _ist_security(request.user):
        return JsonResponse({"alarme": []})

    alarme = []

    # Brandalarme (alle nicht-geschlossenen)
    for alarm in Brandalarm.objects.exclude(
        status=Brandalarm.STATUS_GESCHLOSSEN
    ).order_by("-erstellt_am"):
        if alarm.status == Brandalarm.STATUS_BESTAETIGUNG:
            detail_url = f"/sicherheit/brand/{alarm.pk}/einsatz/"
            status_label = "Security-Review erforderlich"
        elif alarm.status == Brandalarm.STATUS_EVAKUIERUNG:
            detail_url = f"/sicherheit/brand/{alarm.pk}/einsatz/"
            status_label = "EVAKUIERUNG AKTIV"
        else:
            detail_url = f"/sicherheit/brand/{alarm.pk}/einsatz/"
            status_label = "Erkunder unterwegs"

        alarme.append({
            "id": f"brand-{alarm.pk}",
            "typ": "brand",
            "status": alarm.status,
            "status_label": status_label,
            "ort": alarm.ort_aktuell,
            "detail_url": detail_url,
        })

    # Sicherheitsalarme (AMOK + Still)
    for alarm in SicherheitsAlarm.objects.filter(
        status=SicherheitsAlarm.STATUS_AKTIV
    ).order_by("-erstellt_am"):
        typ_label = "AMOK-ALARM" if alarm.typ == SicherheitsAlarm.TYP_AMOK else "Stiller Alarm"
        alarme.append({
            "id": f"amok-{alarm.pk}",
            "typ": alarm.typ,
            "status": alarm.status,
            "status_label": typ_label,
            "ort": alarm.ort or "unbekannt",
            "detail_url": f"/sicherheit/{alarm.pk}/",
        })

    return JsonResponse({"alarme": alarme})


@login_required
def sicherheit_status_json(request):
    """JSON-Endpunkt fuer den client-seitigen AMOK-Status-Poller.

    Wird alle 5 Sekunden vom Browser aller eingeloggten Nutzer abgefragt.
    Gibt nur AMOK-Alarme zurueck – stille Alarme bleiben verborgen.
    """
    from .context_processors import sicherheit_banner

    data = sicherheit_banner(request)
    return JsonResponse({
        "amok_aktiv": data.get("amok_banner_aktiv", False),
        "ort": data.get("amok_banner_ort", ""),
        "zeit": data.get("amok_banner_zeit", ""),
        "pk": data.get("amok_alarm_pk"),
    })


# ---------------------------------------------------------------------------
# Brand-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _ermittle_ort_aus_hr(user):
    """Gibt den aktuellen Raum des Nutzers zurueck.

    Sucht zuerst eine aktive Belegung im Raumbuch (raumnummer + raumname).
    Fallback: Stelle + Name aus HR-Stammdaten.
    """
    from datetime import date

    try:
        ma = user.hr_mitarbeiter
    except Exception:
        return "Buero unbekannt"

    # Aktive Raumbuch-Belegung suchen
    try:
        from raumbuch.models import Belegung

        heute = date.today()
        belegung = (
            Belegung.objects
            .filter(
                mitarbeiter=ma,
                von__lte=heute,
            )
            .filter(Q(bis__isnull=True) | Q(bis__gte=heute))
            .select_related("raum")
            .order_by("-von")
            .first()
        )
        if belegung:
            raum = belegung.raum
            if raum.raumname:
                return f"Raum {raum.raumnummer} – {raum.raumname}"
            return f"Raum {raum.raumnummer}"
    except Exception:
        pass

    # Fallback: Stelle + Name aus HR
    teile = []
    if ma.stelle:
        teile.append(ma.stelle.bezeichnung)
    if ma.nachname:
        teile.append(f"(Buero {ma.vorname} {ma.nachname})")
    return ", ".join(teile) if teile else "Buero unbekannt"


def _benachrichtige_branderkunder(brandalarm):
    """Benachrichtigt alle Branderkunder via Matrix-Raum, Matrix-DM und ntfy.

    Kanaele parallel:
    - Matrix Security-Raum: Hinweis fuer Security zur Bereitschaft
    - Matrix Branderkunder-Raum: @room-Ping, alle Erkunder sehen die Meldung
    - Matrix DM: individueller Token-Link an jeden Erkunder (kein Login noetig)
    - ntfy: individueller Push pro Erkunder mit Token-Link als Click-URL
    """
    from django.conf import settings
    from hr.models import HRMitarbeiter

    security_room      = getattr(settings, "MATRIX_SECURITY_PING_ROOM_ID", "")
    erkunder_room      = getattr(settings, "MATRIX_BRANDERKUNDER_ROOM_ID", "")
    ntfy_url           = getattr(settings, "NTFY_URL", "").rstrip("/")
    ntfy_topic         = getattr(settings, "NTFY_BRANDERKUNDER_TOPIC", "branderkunder-prima")
    zeit               = timezone.localtime(brandalarm.erstellt_am).strftime("%H:%M")
    ort                = brandalarm.ort

    # Matrix Security-Raum
    if security_room:
        try:
            from config.kommunikation_utils import matrix_nachricht_senden
            matrix_nachricht_senden(
                security_room,
                f"BRANDMELDUNG – Ort: {ort} – {zeit} Uhr"
                " – Branderkunder informiert – Security bitte bereithalten",
            )
        except Exception as exc:
            logger.warning("Security-Ping bei Brandmeldung fehlgeschlagen: %s", exc)

    # Matrix Branderkunder-Raum
    if erkunder_room:
        try:
            from config.kommunikation_utils import matrix_nachricht_senden
            matrix_nachricht_senden(
                erkunder_room,
                f"@room BRANDMELDUNG – {zeit} Uhr\n"
                f"Gemeldet: {ort}\n"
                f"\n"
                f"Bitte Brandort aufsuchen und Rueckmeldung geben.\n"
                f"Jeder Erkunder hat einen persoenlichen Link per DM und ntfy erhalten.",
            )
        except Exception as exc:
            logger.warning("Branderkunder-Raum-Ping fehlgeschlagen: %s", exc)

    # Tokens erstellen – Branderkunder + al_as (Arbeitsschutzbeauftragter)
    from django.db.models import Q
    erkunder_qs = list(
        HRMitarbeiter.objects.filter(
            Q(ist_branderkunder=True) | Q(stelle__kuerzel="al_as")
        ).distinct().select_related("stelle")
    )
    token_map = {}
    for ma in erkunder_qs:
        token_obj = BranderkunderToken.objects.create(brandalarm=brandalarm, erkunder=ma)
        token_map[ma.pk] = token_obj

    # ntfy: ein einziger Broadcast an alle Abonnenten von branderkunder-prima
    _ntfy_push(
        ntfy_url, ntfy_topic,
        title="BRANDMELDUNG",
        body=f"Ort: {ort} – bitte Brandort aufsuchen und Rueckmeldung geben",
        priority="urgent",
    )

    # Brandort-Etage aus Belegung des Melders ermitteln
    brand_raum_info = None
    try:
        brand_raum_info = _belegung_raum_info(brandalarm.gemeldet_von.hr_mitarbeiter)
    except Exception:
        pass

    if brand_raum_info is None:
        # Kein Raumvektor bekannt – alle mit 1s-Pause senden
        logger.info(
            "Brandmeldung %s: kein Raumvektor fuer Melder – sende alle Erkunder sequenziell.",
            brandalarm.pk,
        )
        for ma in erkunder_qs:
            token_obj = token_map.get(ma.pk)
            if token_obj:
                _sende_brand_dm(ma, brandalarm, token_obj)
                time.sleep(0.3)
        return

    brand_gebaeude_pk, brand_reihenfolge = brand_raum_info

    # Erkunder nach Etagenabstand gruppieren
    # Anderes Gebaeude: Basisabstand 100 + Etagenabstand (immer nach allen anderen)
    wellen = {}   # abstand (int) -> [HRMitarbeiter]
    kein_raum = []
    for ma in erkunder_qs:
        info = _belegung_raum_info(ma)
        if info is None:
            kein_raum.append(ma)
        else:
            erkunder_gebaeude_pk, erkunder_reihenfolge = info
            if erkunder_gebaeude_pk != brand_gebaeude_pk:
                abstand = 100 + abs(erkunder_reihenfolge - brand_reihenfolge)
            else:
                abstand = abs(erkunder_reihenfolge - brand_reihenfolge)
            wellen.setdefault(abstand, []).append(ma)

    # Erkunder ohne Raumzuweisung in eigene letzte Welle
    if kein_raum:
        wellen[999] = kein_raum

    # Pausen zwischen den Wellen – nur zur Entlastung des Synapse Rate-Limits
    # Innerhalb jeder Welle: 1s pro DM
    # Zwischen Wellen: kurze Atempause damit Synapse nicht drosselt
    PAUSEN = {1: 5, 2: 5}
    STANDARD_PAUSE = 5

    for i, abstand in enumerate(sorted(wellen.keys())):
        if i > 0:
            pause = PAUSEN.get(i, STANDARD_PAUSE)
            logger.info(
                "Brandmeldung %s Welle %d (Abstand %d) – warte %d Sek.",
                brandalarm.pk, i + 1, abstand, pause,
            )
            time.sleep(pause)

        gruppe = wellen[abstand]
        logger.info(
            "Brandmeldung %s Welle %d: %d Erkunder (Abstand %d Etagen).",
            brandalarm.pk, i + 1, len(gruppe), abstand,
        )
        for ma in gruppe:
            token_obj = token_map.get(ma.pk)
            if token_obj:
                _sende_brand_dm(ma, brandalarm, token_obj)
                time.sleep(0.3)


def _belegung_raum_info(ma):
    """Gibt (gebaeude_pk, geschoss_reihenfolge) des aktuellen Raums zurueck.

    Sucht zuerst nach dauerhafter Belegung (bis=None), dann nach aktiver befristeter.
    Gibt None zurueck wenn keine Belegung vorhanden.
    """
    from raumbuch.models import Belegung
    from datetime import date as _date
    b = (
        Belegung.objects
        .filter(mitarbeiter=ma, bis__isnull=True)
        .select_related("raum__geschoss__gebaeude")
        .first()
    )
    if not b:
        b = (
            Belegung.objects
            .filter(mitarbeiter=ma, bis__gte=_date.today())
            .select_related("raum__geschoss__gebaeude")
            .order_by("-bis")
            .first()
        )
    if b:
        return (b.raum.geschoss.gebaeude_id, b.raum.geschoss.reihenfolge)
    return None


def _sende_brand_dm(erkunder, brandalarm, token_obj):
    """Sendet Matrix-DM mit Token-Link an einen Branderkunder.

    Matrix-ID wird aus dem Stellen-Kuerzel gebildet (z.B. @ma_fm2:server).
    Mitarbeiter ohne Stelle werden uebersprungen.
    """
    stelle = getattr(erkunder, "stelle", None)
    if not stelle:
        return
    from django.conf import settings
    server_name = getattr(settings, "MATRIX_SERVER_NAME", "")
    if not server_name:
        return
    matrix_id = f"@{stelle.kuerzel}:{server_name}"
    base = getattr(settings, "PRIMA_BASE_URL", "https://prima.georg-klein.com")
    token_url = f"{base}/sicherheit/brand/erkunden/{token_obj.token}/"
    nachricht = (
        f"BRANDERKUNDEN – Auftrag fuer {erkunder.vollname}\n"
        f"Gemeldet: {brandalarm.ort}\n"
        f"\n"
        f"Bitte Brandort aufsuchen und mit einer Zahl antworten:\n"
        f"  1 – Ich bin zur Branderkundung unterwegs\n"
        f"  2 – Feueralarm (Brand bestaetigt)\n"
        f"  3 – Freitext (schreibe deine Meldung direkt)\n"
        f"  9 – Fehlalarm\n"
        f"\n"
        f"Rueckmeldeseite (kein Login noetig):\n{token_url}"
    )
    try:
        from config.kommunikation_utils import matrix_dm_senden, matrix_nachricht_senden, matrix_messages_seit_token

        # Bestehenden DM-Raum wiederverwenden (kein erneutes Einladen noetig)
        bestehender_raum = erkunder.matrix_bot_dm_room_id
        if bestehender_raum:
            matrix_nachricht_senden(bestehender_raum, nachricht)
            room_id = bestehender_raum
            logger.info("Brand-DM wiederverwendet Raum %s fuer %s", room_id, erkunder)
        else:
            room_id = matrix_dm_senden(matrix_id, nachricht)
            if room_id:
                erkunder.matrix_bot_dm_room_id = room_id
                erkunder.save(update_fields=["matrix_bot_dm_room_id"])
                logger.info("Brand-DM neuer Raum %s fuer %s", room_id, erkunder)

        if room_id:
            _, seit = matrix_messages_seit_token(room_id, since_token=None)
            felder = ["matrix_dm_room_id"]
            token_obj.matrix_dm_room_id = room_id
            if seit:
                token_obj.matrix_dm_since_token = seit
                felder.append("matrix_dm_since_token")
            token_obj.save(update_fields=felder)
    except Exception as exc:
        logger.warning("Brand-DM an %s fehlgeschlagen: %s", erkunder, exc)


def _vollalarm_brand(brandalarm):
    """Sendet Vollalarm nach Security-Bestaetigung.

    Kanaele parallel:
    - Matrix: EH-Raum, Security-Raum, Raeumungshelfer-Raum (@room)
    - ntfy: alle Mitarbeiter (brand-alarm-prima), Raeumungshelfer, Brandbekaempfer
    - Matrix-DM: individuell an jeden Raeumungshelfer
    """
    from django.conf import settings
    eh_room              = getattr(settings, "MATRIX_EH_PING_ROOM_ID", "")
    security_room        = getattr(settings, "MATRIX_SECURITY_PING_ROOM_ID", "")
    raeumungshelfer_room = getattr(settings, "MATRIX_RAEUMUNGSHELFER_ROOM_ID", "")
    ntfy_url             = getattr(settings, "NTFY_URL", "").rstrip("/")
    ort  = brandalarm.ort_aktuell
    zeit = timezone.localtime(brandalarm.erstellt_am).strftime("%H:%M")

    # Matrix-Raeume
    matrix_text = (
        f"@room BRAND-ALARM – Ort: {ort} – {zeit} Uhr"
        " – GEBAEUDE VERLASSEN – Security verstaendigt Feuerwehr"
    )
    raeumungs_text = (
        f"@room VOLLALARM – Ort: {ort} – {zeit} Uhr"
        " – Bitte sofort Raeumung des eigenen Bereichs starten!"
        " Sammelplatz aufsuchen. Alle Personen erfassen."
    )
    try:
        from config.kommunikation_utils import matrix_nachricht_senden
        for room_id in [r for r in [eh_room, security_room] if r]:
            matrix_nachricht_senden(room_id, matrix_text)
        if raeumungshelfer_room:
            matrix_nachricht_senden(raeumungshelfer_room, raeumungs_text)
    except Exception as exc:
        logger.warning("Vollalarm Matrix fehlgeschlagen: %s", exc)

    # ntfy: alle Mitarbeiter
    _ntfy_push(
        ntfy_url,
        getattr(settings, "NTFY_BRAND_TOPIC", "brand-alarm-prima"),
        title="BRAND-ALARM",
        body=f"Ort: {ort} – Gebaeude verlassen! Security verstaendigt Feuerwehr.",
        priority="urgent",
    )
    # ntfy: Raeumungshelfer
    _ntfy_push(
        ntfy_url,
        getattr(settings, "NTFY_RAEUMUNGSHELFER_TOPIC", "raeumungshelfer-prima"),
        title="VOLLALARM – RAEUMUNG",
        body=f"Ort: {ort} – Sofort Bereich raeumen! Sammelplatz aufsuchen und absichern.",
        priority="urgent",
    )
    # ntfy: Brandbekaempfer
    _ntfy_push(
        ntfy_url,
        getattr(settings, "NTFY_BRANDBEKAEMPFER_TOPIC", "brandbekaempfer-prima"),
        title="VOLLALARM – BRANDBEKAEMPFUNG",
        body=f"Ort: {ort} – Kleiner Brand? Loescher einsetzen wenn sicher. Bei Ausbreitung: sofort evakuieren!",
        priority="urgent",
    )

    # Matrix-DM an jeden Raeumungshelfer individuell
    _benachrichtige_raeumungshelfer(brandalarm)


def _benachrichtige_raeumungshelfer(brandalarm):
    """Sendet Matrix-DM an alle Raeumungshelfer."""
    from hr.models import HRMitarbeiter
    ort = brandalarm.ort_aktuell
    nachricht = (
        f"BRAND BESTAETIGT – Ort: {ort}\n"
        "Bitte sofort Raeumung Ihres Bereichs starten.\n"
        "Sammelplatz aufsuchen. Alle Personen erfassen."
    )
    from django.conf import settings as _settings
    server_name = getattr(_settings, "MATRIX_SERVER_NAME", "")
    for ma in HRMitarbeiter.objects.filter(ist_raeumungshelfer=True).select_related("stelle"):
        stelle = getattr(ma, "stelle", None)
        if not stelle or not server_name:
            continue
        matrix_id = f"@{stelle.kuerzel}:{server_name}"
        try:
            from config.kommunikation_utils import matrix_dm_senden
            matrix_dm_senden(matrix_id, nachricht)
        except Exception as exc:
            logger.warning("Raeumungshelfer-DM an %s fehlgeschlagen: %s", ma, exc)


# ---------------------------------------------------------------------------
# Brand-Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def brand_melden(request):
    """Loest eine Brandmeldung aus (Eingabe FEUER erforderlich).

    Ermittelt Ort aus POST oder HR-Buero als Fallback.
    Zweiter unabhaengiger Melder eskaliert direkt zu Security-Review.
    """
    bestaetigung = request.POST.get("bestaetigung", "").strip().upper()
    if bestaetigung != "FEUER":
        return render(request, "sicherheit/brand_fehler.html", {
            "fehler": "Bitte genau das Wort FEUER eingeben.",
        }, status=400)

    ort = request.POST.get("ort", "").strip() or _ermittle_ort_aus_hr(request.user)

    aktiver = (
        Brandalarm.objects
        .filter(status=Brandalarm.STATUS_GEMELDET)
        .order_by("-erstellt_am")
        .first()
    )
    if aktiver and aktiver.gemeldet_von != request.user:
        aktiver.melder_anzahl += 1
        aktiver.status = Brandalarm.STATUS_BESTAETIGUNG
        aktiver.save(update_fields=["melder_anzahl", "status"])
        logger.info("Zweiter Melder – Brandalarm %s eskaliert.", aktiver.pk)
        return redirect("sicherheit:brand_gemeldet", pk=aktiver.pk)

    brandalarm = Brandalarm.objects.create(ort=ort, gemeldet_von=request.user)

    # Benachrichtigungen im Hintergrund – Browser wartet nicht
    t = threading.Thread(
        target=_benachrichtige_branderkunder,
        args=(brandalarm,),
        daemon=True,
    )
    t.start()

    return redirect("sicherheit:brand_gemeldet", pk=brandalarm.pk)


@login_required
def brand_gemeldet_view(request, pk):
    """Bestaetigungsseite fuer den Melder – zeigt aktuellen Erkunder-Status."""
    brandalarm = get_object_or_404(
        Brandalarm.objects.prefetch_related("erkunder_tokens__erkunder"),
        pk=pk,
    )
    return render(request, "sicherheit/brand_gemeldet.html", {"brandalarm": brandalarm})


def brand_erkunden_token(request, token):
    """Tokenbasierte Rueckmeldeseite fuer Branderkunder (kein Login noetig).

    Aktionen:
      unterwegs  - Bin auf dem Weg
      am_ort     - Bin am Brandort angekommen
      lage       - Lagemeldung (data-notiz als lage_notiz)
      nachricht  - Freie Textnachricht an Security
      bestaetigt - Brand bestaetigt + Wo-genau, Security wird gepingt
      fehlalarm  - Kein Brand, bei allen Erkundern schliesst Alarm
    """
    token_obj = get_object_or_404(BranderkunderToken, token=token)
    brandalarm = token_obj.brandalarm
    erkunder = token_obj.erkunder

    if request.method == "POST":
        aktion      = request.POST.get("aktion", "")
        ort_praezise = request.POST.get("ort_praezise", "").strip()
        notiz       = request.POST.get("notiz", "").strip()
        lage_notiz  = request.POST.get("lage_notiz", "").strip()

        # --- Hilfsfunktion: Security-Ping ---
        def _security_ping(text):
            try:
                from django.conf import settings as _s
                from config.kommunikation_utils import matrix_nachricht_senden
                room = getattr(_s, "MATRIX_SECURITY_PING_ROOM_ID", "")
                if room:
                    matrix_nachricht_senden(room, text)
            except Exception as exc:
                logger.warning("Security-Ping fehlgeschlagen: %s", exc)

        if aktion == "unterwegs":
            token_obj.status = BranderkunderToken.STATUS_UNTERWEGS
            token_obj.save(update_fields=["status"])
            _security_ping(
                f"Branderkunder {erkunder.vollname} ist UNTERWEGS"
                f" – Brandort: {brandalarm.ort}"
            )
            return render(request, "sicherheit/brand_erkunden_bestaetigung.html", {
                "token_obj": token_obj, "brandalarm": brandalarm,
                "erkunder": erkunder, "meldung": "unterwegs",
            })

        if aktion == "am_ort":
            token_obj.status = BranderkunderToken.STATUS_AM_ORT
            token_obj.save(update_fields=["status"])
            _security_ping(
                f"Branderkunder {erkunder.vollname} ist AM ORT"
                f" – Brandort: {brandalarm.ort}"
            )
            return render(request, "sicherheit/brand_erkunden_bestaetigung.html", {
                "token_obj": token_obj, "brandalarm": brandalarm,
                "erkunder": erkunder, "meldung": "am_ort",
            })

        if aktion == "lage":
            meldung_text = lage_notiz or "Lagemeldung"
            token_obj.notiz = meldung_text
            token_obj.save(update_fields=["notiz"])
            _security_ping(
                f"Branderkunder {erkunder.vollname} meldet: {meldung_text}"
                f" – Ort: {brandalarm.ort}"
            )
            return render(request, "sicherheit/brand_erkunden_bestaetigung.html", {
                "token_obj": token_obj, "brandalarm": brandalarm,
                "erkunder": erkunder, "meldung": "lage", "lage_text": meldung_text,
            })

        if aktion == "nachricht":
            if notiz:
                token_obj.notiz = notiz
                token_obj.save(update_fields=["notiz"])
                _security_ping(
                    f"Branderkunder {erkunder.vollname}: {notiz}"
                    f" – Ort: {brandalarm.ort}"
                )
            return render(request, "sicherheit/brand_erkunden_bestaetigung.html", {
                "token_obj": token_obj, "brandalarm": brandalarm,
                "erkunder": erkunder, "meldung": "nachricht", "lage_text": notiz,
            })

        if aktion == "bestaetigt":
            token_obj.status = BranderkunderToken.STATUS_BESTAETIGT
            token_obj.ort_praezise = ort_praezise
            token_obj.save(update_fields=["status", "ort_praezise"])
            if brandalarm.status == Brandalarm.STATUS_GEMELDET:
                brandalarm.status = Brandalarm.STATUS_BESTAETIGUNG
                if ort_praezise:
                    brandalarm.ort_praezise = ort_praezise
                brandalarm.save(update_fields=["status", "ort_praezise"])
            _security_ping(
                f"Branderkunder {erkunder.vollname} BESTAETIGT Brand"
                f" – Ort: {ort_praezise or brandalarm.ort}"
                f" – Bitte Security-Bestaetigung: /sicherheit/brand/{brandalarm.pk}/security/"
            )
            return render(request, "sicherheit/brand_erkunden_bestaetigung.html", {
                "token_obj": token_obj, "brandalarm": brandalarm,
                "erkunder": erkunder, "meldung": "bestaetigt",
            })

        if aktion == "fehlalarm":
            token_obj.status = BranderkunderToken.STATUS_FEHLALARM
            token_obj.save(update_fields=["status"])
            _security_ping(
                f"Branderkunder {erkunder.vollname} meldet FEHLALARM"
                f" – Ort: {brandalarm.ort}"
            )
            alle_fehlalarm = not brandalarm.erkunder_tokens.exclude(
                status=BranderkunderToken.STATUS_FEHLALARM
            ).exists()
            if alle_fehlalarm and brandalarm.status == Brandalarm.STATUS_GEMELDET:
                brandalarm.status = Brandalarm.STATUS_GESCHLOSSEN
                brandalarm.geschlossen_am = timezone.now()
                brandalarm.save(update_fields=["status", "geschlossen_am"])
            return render(request, "sicherheit/brand_erkunden_bestaetigung.html", {
                "token_obj": token_obj, "brandalarm": brandalarm,
                "erkunder": erkunder, "meldung": "fehlalarm",
            })

    return render(request, "sicherheit/brand_erkunden_token.html", {
        "token_obj": token_obj,
        "brandalarm": brandalarm,
        "erkunder": erkunder,
        "letzte_notiz": token_obj.notiz,
    })


@login_required
def brand_security_bestaetigen(request, pk):
    """Security-Review: Brand bestaetigen oder als Fehlalarm schliessen."""
    if not _ist_security(request.user):
        raise PermissionDenied
    brandalarm = get_object_or_404(
        Brandalarm, pk=pk, status=Brandalarm.STATUS_BESTAETIGUNG
    )
    if request.method == "POST":
        entscheidung = request.POST.get("entscheidung", "")
        if entscheidung == "bestaetigt":
            brandalarm.status = Brandalarm.STATUS_EVAKUIERUNG
            brandalarm.security_bestaetigt_von = request.user
            brandalarm.security_bestaetigt_am = timezone.now()
            brandalarm.save(update_fields=[
                "status", "security_bestaetigt_von", "security_bestaetigt_am",
            ])
            threading.Thread(
                target=_vollalarm_brand,
                args=(brandalarm,),
                daemon=True,
            ).start()
            return redirect("sicherheit:brand_detail", pk=brandalarm.pk)

        if entscheidung == "fehlalarm":
            brandalarm.status = Brandalarm.STATUS_GESCHLOSSEN
            brandalarm.geschlossen_am = timezone.now()
            brandalarm.geschlossen_von = request.user
            brandalarm.notiz = request.POST.get("notiz", "").strip()
            brandalarm.save(update_fields=[
                "status", "geschlossen_am", "geschlossen_von", "notiz",
            ])
            return redirect("sicherheit:brand_liste")

    return render(request, "sicherheit/brand_security.html", {"brandalarm": brandalarm})


@login_required
@require_POST
def brand_schliessen(request, pk):
    """Entwarnung – schliesst aktiven Brandalarm."""
    if not _ist_security(request.user):
        raise PermissionDenied
    brandalarm = get_object_or_404(
        Brandalarm,
        pk=pk,
        status__in=[
            Brandalarm.STATUS_GEMELDET,
            Brandalarm.STATUS_EVAKUIERUNG,
            Brandalarm.STATUS_BESTAETIGUNG,
        ],
    )
    brandalarm.status = Brandalarm.STATUS_GESCHLOSSEN
    brandalarm.geschlossen_am = timezone.now()
    brandalarm.geschlossen_von = request.user
    brandalarm.notiz = request.POST.get("notiz", "").strip()
    brandalarm.save(update_fields=["status", "geschlossen_am", "geschlossen_von", "notiz"])
    return redirect("sicherheit:brand_liste")


@login_required
def brand_erkunder_status_json(request):
    """Gibt aktiven Brandalarm-Token fuer den eingeloggten Branderkunder zurueck.

    Wird vom Poller alle 5 Sekunden abgefragt. Gibt token_url zurueck
    damit der Browser ein Erkunder-spezifisches Overlay anzeigen kann.
    """
    leer = {"erkunder_alarm": False}
    try:
        from django.conf import settings
        base = getattr(settings, "PRIMA_BASE_URL", "")

        # Security/AS: zur Einsatzleitstelle des neuesten aktiven Brandes leiten
        # (kein Token-Status noetig – immer verfuegbar solange Alarm aktiv)
        if _ist_security(request.user):
            aktiver_brand = (
                Brandalarm.objects
                .exclude(status=Brandalarm.STATUS_GESCHLOSSEN)
                .order_by("-erstellt_am")
                .first()
            )
            if not aktiver_brand:
                return JsonResponse(leer)
            return JsonResponse({
                "erkunder_alarm": True,
                "ort": aktiver_brand.ort,
                "token_url": f"{base}/sicherheit/brand/{aktiver_brand.pk}/einsatz/",
                "ist_security": True,
            })

        # Normaler Branderkunder: nur wenn eigener Token ausstehend
        ma = request.user.hr_mitarbeiter
        if not ma.ist_branderkunder:
            return JsonResponse(leer)
        token = (
            BranderkunderToken.objects
            .filter(
                erkunder=ma,
                brandalarm__status=Brandalarm.STATUS_GEMELDET,
                status=BranderkunderToken.STATUS_AUSSTEHEND,
            )
            .select_related("brandalarm")
            .order_by("-erstellt_am")
            .first()
        )
        if not token:
            return JsonResponse(leer)
        return JsonResponse({
            "erkunder_alarm": True,
            "ort": token.brandalarm.ort,
            "token_url": f"{base}/sicherheit/brand/erkunden/{token.token}/",
            "ist_security": False,
        })
    except Exception:
        return JsonResponse(leer)


@login_required
def brand_liste(request):
    """Liste aller Brandalarme – nur Security/Staff."""
    if not _ist_security(request.user):
        raise PermissionDenied
    alarme = (
        Brandalarm.objects
        .select_related("gemeldet_von", "geschlossen_von")
        .prefetch_related("erkunder_tokens")
        .order_by("-erstellt_am")
    )
    hat_aktive = alarme.filter(
        status__in=[
            Brandalarm.STATUS_GEMELDET,
            Brandalarm.STATUS_BESTAETIGUNG,
            Brandalarm.STATUS_EVAKUIERUNG,
        ]
    ).exists()
    return render(request, "sicherheit/brand_liste.html", {
        "alarme": alarme,
        "hat_aktive": hat_aktive,
    })


@login_required
def brand_detail(request, pk):
    """Detailansicht eines Brandalarms."""
    if not _ist_security(request.user):
        raise PermissionDenied
    brandalarm = get_object_or_404(
        Brandalarm.objects
        .select_related("gemeldet_von", "security_bestaetigt_von", "geschlossen_von")
        .prefetch_related("erkunder_tokens__erkunder"),
        pk=pk,
    )
    return render(request, "sicherheit/brand_detail.html", {
        "brandalarm": brandalarm,
        "ist_arbeitsschutz": _ist_arbeitsschutz(request.user),
    })


@login_required
def brand_nachbewertung(request, pk):
    """Nachbewertung eines geschlossenen Brandalarms durch Arbeitsschutz (al_as) oder Staff.

    GET: Formular mit vorausgefuelltem Bewertungstext
    POST: Bewertung + Text speichern, weiterleiten zur Detailansicht
    """
    if not _ist_arbeitsschutz(request.user):
        raise PermissionDenied

    brandalarm = get_object_or_404(
        Brandalarm.objects
        .select_related("gemeldet_von", "geschlossen_von")
        .prefetch_related("erkunder_tokens__erkunder"),
        pk=pk,
        status=Brandalarm.STATUS_GESCHLOSSEN,
    )

    if request.method == "POST":
        bewertung = request.POST.get("bewertung", "").strip()
        text = request.POST.get("text", "").strip()
        if bewertung in dict(Brandalarm.BEWERTUNG_CHOICES):
            brandalarm.nachbewertung = bewertung
            brandalarm.nachbewertung_text = text
            brandalarm.nachbewertung_erstellt_am = timezone.now()
            brandalarm.nachbewertung_erstellt_von = request.user
            brandalarm.save(update_fields=[
                "nachbewertung",
                "nachbewertung_text",
                "nachbewertung_erstellt_am",
                "nachbewertung_erstellt_von",
            ])
            logger.info(
                "Brandalarm %s nachbewertet von %s: %s",
                brandalarm.pk, request.user.username, bewertung,
            )
        return redirect("sicherheit:brand_detail", pk=brandalarm.pk)

    # Vorbelegungstext aus Alarmdaten generieren
    erkunder_status = []
    for tok in brandalarm.erkunder_tokens.filter(status=BranderkunderToken.STATUS_BESTAETIGT):
        eintrag = tok.erkunder.vollname
        if tok.ort_praezise:
            eintrag += f" (Ort: {tok.ort_praezise})"
        if tok.notiz:
            eintrag += f" – {tok.notiz}"
        erkunder_status.append(eintrag)

    vortext = (
        f"Brandalarm #{brandalarm.pk} vom "
        f"{brandalarm.erstellt_am.strftime('%d.%m.%Y %H:%M')} Uhr.\n"
        f"Ort: {brandalarm.ort}"
    )
    if brandalarm.ort_praezise:
        vortext += f" ({brandalarm.ort_praezise})"
    vortext += ".\n"
    if erkunder_status:
        vortext += "Brand bestaetigt durch: " + ", ".join(erkunder_status) + ".\n"
    else:
        vortext += "Kein Erkunder hat den Brand bestaetigt (Fehlalarm / automatisch geschlossen).\n"
    if brandalarm.notiz:
        vortext += f"Notiz: {brandalarm.notiz}\n"

    return render(request, "sicherheit/brand_nachbewertung.html", {
        "brandalarm": brandalarm,
        "vortext": vortext,
        "bewertung_choices": Brandalarm.BEWERTUNG_CHOICES,
    })


@login_required
def brand_einsatz(request, pk):
    """Einsatzleitstelle fuer Security/AS – live Uebersicht aller Erkunder-Rueckmeldungen.

    Kombiniert Statusanzeige, Erkunder-Meldungen und Aktionsbuttons auf einer Seite.
    Auto-Refresh alle 8 Sekunden per JS.
    """
    if not _ist_security(request.user):
        raise PermissionDenied
    brandalarm = get_object_or_404(
        Brandalarm.objects
        .select_related("gemeldet_von", "security_bestaetigt_von", "geschlossen_von")
        .prefetch_related("erkunder_tokens__erkunder"),
        pk=pk,
    )
    if request.method == "POST":
        aktion = request.POST.get("aktion", "")
        if aktion == "abbrechen" and brandalarm.status != Brandalarm.STATUS_GESCHLOSSEN:
            brandalarm.status = Brandalarm.STATUS_GESCHLOSSEN
            brandalarm.geschlossen_am = timezone.now()
            brandalarm.geschlossen_von = request.user
            brandalarm.notiz = request.POST.get("notiz", "Einsatz abgebrochen").strip()
            brandalarm.save(update_fields=[
                "status", "geschlossen_am", "geschlossen_von", "notiz"
            ])
            return redirect("sicherheit:brand_liste")

    # Erkunder nach Status gruppieren fuer Zaehler
    tokens = list(brandalarm.erkunder_tokens.all())
    zaehler = {
        "bestaetigt": sum(1 for t in tokens if t.status == BranderkunderToken.STATUS_BESTAETIGT),
        "fehlalarm":  sum(1 for t in tokens if t.status == BranderkunderToken.STATUS_FEHLALARM),
        "unterwegs":  sum(1 for t in tokens if t.status == BranderkunderToken.STATUS_UNTERWEGS),
        "am_ort":     sum(1 for t in tokens if t.status == BranderkunderToken.STATUS_AM_ORT),
        "ausstehend": sum(1 for t in tokens if t.status == BranderkunderToken.STATUS_AUSSTEHEND),
    }
    # Freitexte (Notizen) der Erkunder – nur gefuellte
    meldungen = [t for t in tokens if t.notiz]
    meldungen.sort(key=lambda t: t.status)

    return render(request, "sicherheit/brand_einsatz.html", {
        "brandalarm": brandalarm,
        "tokens": tokens,
        "zaehler": zaehler,
        "meldungen": meldungen,
        "ist_arbeitsschutz": _ist_arbeitsschutz(request.user),
    })


@login_required
def brand_einsatz_json(request, pk):
    """JSON-Endpunkt fuer den Einsatz-Live-Poller (Erkunder-Klötzchen aktualisieren)."""
    if not _ist_security(request.user):
        return JsonResponse({"fehler": "Kein Zugriff"}, status=403)
    brandalarm = get_object_or_404(Brandalarm, pk=pk)
    tokens = list(
        brandalarm.erkunder_tokens
        .select_related("erkunder")
        .values("pk", "status", "notiz", "ort_praezise",
                "erkunder__vorname", "erkunder__nachname")
    )
    return JsonResponse({
        "status": brandalarm.status,
        "tokens": [
            {
                "pk": t["pk"],
                "status": t["status"],
                "name": f"{t['erkunder__vorname']} {t['erkunder__nachname']}".strip(),
                "notiz": t["notiz"] or "",
                "ort_praezise": t["ort_praezise"] or "",
            }
            for t in tokens
        ],
    })


@login_required
def brand_status_json(request):
    """JSON-Endpunkt fuer den Brand-Evakuierungs-Poller."""
    from .context_processors import sicherheit_banner
    data = sicherheit_banner(request)
    return JsonResponse({
        "brand_aktiv": data.get("brand_banner_aktiv", False),
        "ort": data.get("brand_banner_ort", ""),
        "zeit": data.get("brand_banner_zeit", ""),
        "pk": data.get("brand_alarm_pk"),
    })


# ---------------------------------------------------------------------------
# Arbeitsschutz-Verwaltung
# ---------------------------------------------------------------------------

# Felder die verwaltet werden koennen – Reihenfolge bestimmt Spaltenfolge
_ARBEITSSCHUTZ_ROLLEN = [
    ("ist_ersthelfer",      "Ersthelfer"),
    ("ist_branderkunder",   "Branderkunder"),
    ("ist_raeumungshelfer", "Raeumungshelfer"),
    ("ist_brandbekaempfer", "Brandbekaempfer"),
]


def _ist_arbeitsschutz(user):
    """Prueft ob ein User Arbeitsschutz-Zugriff hat (al_as oder Staff)."""
    if user.is_staff:
        return True
    try:
        return user.hr_mitarbeiter.stelle.kuerzel == "al_as"
    except Exception:
        return False


@login_required
def arbeitsschutz_dashboard(request):
    """Uebersichtsseite fuer die Verwaltung von Arbeitsschutz-Rollen.

    Zeigt alle Mitarbeiter mit ihren Brandschutz-Kennzeichnungen
    und ermoeglicht direkte Aenderungen per HTMX-Checkbox.
    Nur fuer Arbeitsschutz-Beauftragte und Staff.
    """
    if not _ist_arbeitsschutz(request.user):
        raise PermissionDenied

    from hr.models import HRMitarbeiter

    mitarbeiter_qs = (
        HRMitarbeiter.objects
        .select_related("stelle", "stelle__org_einheit", "user")
        .order_by("stelle__org_einheit__bezeichnung", "stelle__bezeichnung")
    )

    # Zaehler pro Rolle + Daten mit vorberechneten Rollenwerten aufbauen
    zaehler = {feld: 0 for feld, _ in _ARBEITSSCHUTZ_ROLLEN}
    mitarbeiter_daten = []
    for ma in mitarbeiter_qs:
        rollen_werte = []
        for feld, bezeichnung in _ARBEITSSCHUTZ_ROLLEN:
            wert = getattr(ma, feld, False)
            if wert:
                zaehler[feld] += 1
            rollen_werte.append((feld, bezeichnung, wert))
        mitarbeiter_daten.append((ma, rollen_werte))

    return render(request, "sicherheit/arbeitsschutz_dashboard.html", {
        "mitarbeiter_daten": mitarbeiter_daten,
        "rollen": _ARBEITSSCHUTZ_ROLLEN,
        "zaehler": zaehler,
        "gesamt": len(mitarbeiter_daten),
    })


@login_required
@require_POST
def arbeitsschutz_rolle_toggle(request, pk):
    """Schaltet eine Arbeitsschutz-Rolle fuer einen Mitarbeiter um.

    HTMX-View: gibt nur die aktualisierte Checkbox-Zelle zurueck.
    """
    if not _ist_arbeitsschutz(request.user):
        raise PermissionDenied

    from hr.models import HRMitarbeiter

    ma = get_object_or_404(HRMitarbeiter.objects.select_related("stelle"), pk=pk)
    feld = request.POST.get("feld", "")

    erlaubte_felder = {f for f, _ in _ARBEITSSCHUTZ_ROLLEN}
    if feld not in erlaubte_felder:
        return JsonResponse({"fehler": "Ungueltiges Feld"}, status=400)

    aktuell = getattr(ma, feld, False)
    setattr(ma, feld, not aktuell)
    ma.save(update_fields=[feld])

    logger.info(
        "Arbeitsschutz: %s.%s = %s (geaendert von %s)",
        ma, feld, not aktuell, request.user.username,
    )

    return render(request, "sicherheit/partials/_arbeitsschutz_checkbox.html", {
        "ma": ma,
        "feld": feld,
        "wert": not aktuell,
    })


@login_required
@require_POST
def arbeitsschutz_matrix_einladen(request):
    """Sendet Matrix-Einladungen an alle Mitarbeiter mit gesetzten Rollen.

    Laeuft im Vordergrund und gibt eine Statusmeldung zurueck (HTMX).
    """
    if not _ist_arbeitsschutz(request.user):
        raise PermissionDenied

    from django.conf import settings as _settings
    from hr.models import HRMitarbeiter
    from hr.signals import _ping_raeume_fuer_mitarbeiter
    from config.kommunikation_utils import (
        matrix_nutzer_in_raum_einladen,
        matrix_power_level_setzen,
    )

    server_name = getattr(_settings, "MATRIX_SERVER_NAME", "")
    gesendet = 0
    fehler = 0

    if server_name:
        mitarbeiter = (
            HRMitarbeiter.objects
            .select_related("stelle")
            .filter(
                ist_ersthelfer=True
            ) | HRMitarbeiter.objects.select_related("stelle").filter(
                ist_branderkunder=True
            ) | HRMitarbeiter.objects.select_related("stelle").filter(
                ist_raeumungshelfer=True
            ) | HRMitarbeiter.objects.select_related("stelle").filter(
                ist_brandbekaempfer=True
            )
        )
        mitarbeiter = mitarbeiter.distinct()

        # Raeume in denen al_as Schreibrechte (Moderator) bekommt
        al_as_moderator_raeume = [
            r for r in [
                getattr(_settings, "MATRIX_SECURITY_PING_ROOM_ID", ""),
                getattr(_settings, "MATRIX_BRANDERKUNDER_ROOM_ID", ""),
                getattr(_settings, "MATRIX_EH_PING_ROOM_ID", ""),
            ] if r
        ]

        for ma in mitarbeiter:
            stelle = getattr(ma, "stelle", None)
            if not stelle:
                continue
            matrix_id = f"@{stelle.kuerzel}:{server_name}"
            raeume = _ping_raeume_fuer_mitarbeiter(ma)
            for room_id, _ in raeume:
                if matrix_nutzer_in_raum_einladen(room_id, matrix_id):
                    gesendet += 1
                else:
                    fehler += 1

            # al_as erhaelt Moderator-Status (Power Level 50) in allen Ping-Raeumen
            if stelle.kuerzel == "al_as":
                for room_id in al_as_moderator_raeume:
                    matrix_power_level_setzen(room_id, matrix_id, level=50)

    return render(request, "sicherheit/partials/_matrix_einladen_ergebnis.html", {
        "gesendet": gesendet,
        "fehler": fehler,
        "server_konfiguriert": bool(server_name),
    })
