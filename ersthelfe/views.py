import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    ErsteHilfeErsthelferToken,
    ErsteHilfeNachricht,
    ErsteHilfeRueckmeldung,
    ErsteHilfeVorfall,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _ist_eh_verantwortlicher(user):
    """Prueft ob ein User alle Vorfaelle sehen darf (Betriebsarzt, al_as oder Staff)."""
    if user.is_staff:
        return True
    if user.has_perm("ersthelfe.view_alle_vorfaelle"):
        return True
    try:
        stelle = user.hr_mitarbeiter.stelle
        if stelle and (stelle.ist_betriebsarzt or stelle.kuerzel == "al_as"):
            return True
    except Exception:
        pass
    return False


def _ntfy_alarm_senden(vorfall, ort, zeit):
    """Sendet Push-Benachrichtigung via ntfy (selbst gehostet, Priority urgent).

    Priority 'urgent' durchdringt den Nicht-Stoeren-Modus auf Android.
    Erfordert: ntfy-App auf Android, Topic eh-alarm-prima abonniert.
    """
    import urllib.request
    from django.conf import settings

    ntfy_url = getattr(settings, "NTFY_URL", "").rstrip("/")
    ntfy_topic = getattr(settings, "NTFY_EH_TOPIC", "")
    if not ntfy_url or not ntfy_topic:
        return

    nachricht = f"Einsatzort: {ort} | Alarmzeit: {zeit} Uhr | Vorfall #{vorfall.pk}"
    url = f"{ntfy_url}/{ntfy_topic}"
    req = urllib.request.Request(
        url,
        data=nachricht.encode("utf-8"),
        headers={
            "Title": "!!! ERSTE HILFE ALARM !!!",
            "Priority": "urgent",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
        logger.info("ntfy EH-Alarm fuer Vorfall %s gesendet.", vorfall.pk)
    except Exception as exc:
        logger.warning("ntfy EH-Alarm fehlgeschlagen (nicht kritisch): %s", exc)


def _setze_bot_als_moderator(homeserver, bot_token, room_id):
    """Setzt den Bot auf Power Level 50 (Moderator) im EH_PING-Raum.

    Noetig damit @room-Mentions den Benachrichtigungston in Element ausloesen –
    Synapse erlaubt @room nur fuer Nutzer mit Power Level >= notifications.room (default 50).
    Wird bei jedem Alarm einmalig aufgerufen; schlaegt graceful fehl wenn bereits Moderator.
    """
    import json
    import urllib.error
    import urllib.request

    try:
        # Aktuelle Power-Levels lesen
        url_get = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/state/m.room.power_levels"
        req_get = urllib.request.Request(
            url_get,
            headers={"Authorization": f"Bearer {bot_token}"},
        )
        with urllib.request.urlopen(req_get, timeout=5) as resp:
            power_levels = json.loads(resp.read().decode("utf-8"))

        # Bot-User-ID ermitteln
        url_whoami = f"{homeserver}/_matrix/client/v3/account/whoami"
        req_who = urllib.request.Request(
            url_whoami,
            headers={"Authorization": f"Bearer {bot_token}"},
        )
        with urllib.request.urlopen(req_who, timeout=5) as resp:
            bot_user_id = json.loads(resp.read().decode("utf-8")).get("user_id", "")

        if not bot_user_id:
            return

        users = power_levels.setdefault("users", {})
        if users.get(bot_user_id, 0) >= 50:
            return  # Bereits Moderator – nichts zu tun

        users[bot_user_id] = 50
        import time
        txn_id = str(int(time.time() * 1000))
        url_put = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/state/m.room.power_levels"
        payload = json.dumps(power_levels).encode("utf-8")
        req_put = urllib.request.Request(
            url_put,
            data=payload,
            headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req_put, timeout=5):
            pass
        logger.info("Bot auf Power Level 50 im EH_PING-Raum gesetzt.")
    except Exception as exc:
        logger.warning("Bot-Moderator-Setzung fehlgeschlagen (nicht kritisch): %s", exc)


def _benachrichtige_ersthelfer(vorfall):
    """Sendet Alarm-Nachricht in den EH_PING Matrix-Raum.

    Ersthelfer und Betriebsarzt sind im Raum und antworten mit 1/2/3/4.
    Speichert since_token fuer spaeteres Polling.
    Funktioniert auch ohne Matrix (graceful degradation).
    """
    import json
    import time
    import urllib.error
    import urllib.request

    from config.kommunikation_utils import matrix_messages_seit_token
    from django.conf import settings

    homeserver = (
        getattr(settings, "MATRIX_HOMESERVER_INTERNAL_URL", "").rstrip("/")
        or getattr(settings, "MATRIX_HOMESERVER_URL", "").rstrip("/")
    )
    bot_token = getattr(settings, "MATRIX_BOT_TOKEN", "")
    eh_ping_room = getattr(settings, "MATRIX_EH_PING_ROOM_ID", "")

    if not homeserver or not bot_token or not eh_ping_room:
        logger.info("MATRIX_EH_PING_ROOM_ID nicht konfiguriert – EH-Ping uebersprungen.")
        return

    # Sicherstellen dass der Bot Moderator-Rechte hat (noetig fuer @room-Mention mit Ton)
    _setze_bot_als_moderator(homeserver, bot_token, eh_ping_room)

    jetzt = timezone.localtime(vorfall.erstellt_am)
    try:
        meldender_name = vorfall.gemeldet_von.hr_mitarbeiter.vollname
    except Exception:
        meldender_name = vorfall.gemeldet_von.get_full_name() or vorfall.gemeldet_von.username

    ping_text = (
        f"@room EH-ALARM [ERSTE HILFE] Notfall – {vorfall.ort}\n"
        f"Gemeldet von {meldender_name} um {jetzt.strftime('%H:%M')} Uhr\n\n"
        f"Ersthelfer – antwortet mit einer Zahl oder Freitext:\n"
        f"  1 = Bin unterwegs\n"
        f"  2 = Bin vor Ort\n"
        f"  3 = Brauche Unterstuetzung\n"
        f"  4 = Kann nicht kommen\n"
        f"--- Bedarfsmeldungen vor Ort ---\n"
        f"  5 = Brauche Defibrillator\n"
        f"  6 = Bitte RTW verstaendigen (112)\n"
        f"  7 = Brauche zweiten Ersthelfer\n"
        f"  8 = Brauche Verbandsmaterial\n"
        f"  9 = Patient transportfaehig\n"
        f" 10 = Einsatz beendet / kein Arzt noetig\n"
        f"Oder einfach eine Freitextnachricht schreiben."
    )
    txn_id = str(int(time.time() * 1000))
    url = (
        f"{homeserver}/_matrix/client/v3/rooms/{eh_ping_room}"
        f"/send/m.room.message/{txn_id}"
    )
    # formatted_body mit HTML fuer korrekten @room-Mention (Ton-Benachrichtigung in Element)
    payload = json.dumps({
        "msgtype": "m.text",
        "body": ping_text,
        "format": "org.matrix.custom.html",
        "formatted_body": (
            f'<strong><a href="https://matrix.to/#/!room:{eh_ping_room}">@room</a>'
            f" EH-ALARM [ERSTE HILFE] Notfall \u2013 {vorfall.ort}</strong><br>"
            f"Gemeldet von {meldender_name} um {jetzt.strftime('%H:%M')} Uhr<br><br>"
            f"Ersthelfer \u2013 antwortet mit einer Zahl oder Freitext:<br>"
            f"&nbsp;&nbsp;1 = Bin unterwegs<br>"
            f"&nbsp;&nbsp;2 = Bin vor Ort<br>"
            f"&nbsp;&nbsp;3 = Brauche Unterstuetzung<br>"
            f"&nbsp;&nbsp;4 = Kann nicht kommen<br>"
            f"<em>Bedarfsmeldungen vor Ort:</em><br>"
            f"&nbsp;&nbsp;5 = Brauche Defibrillator<br>"
            f"&nbsp;&nbsp;6 = Bitte RTW verstaendigen (112)<br>"
            f"&nbsp;&nbsp;7 = Brauche zweiten Ersthelfer<br>"
            f"&nbsp;&nbsp;8 = Brauche Verbandsmaterial<br>"
            f"&nbsp;&nbsp;9 = Patient transportfaehig<br>"
            f"&nbsp;10 = Einsatz beendet / kein Arzt noetig<br>"
            f"Oder einfach eine Freitextnachricht schreiben."
        ),
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            json.loads(resp.read().decode("utf-8"))
            _, seit = matrix_messages_seit_token(eh_ping_room, since_token=None)
            vorfall.matrix_ping_since_token = seit or ""
            vorfall.save(update_fields=["matrix_ping_since_token"])
            logger.info("EH_PING-Alarm gesendet, Vorfall %s", vorfall.pk)
    except urllib.error.URLError as exc:
        logger.warning("EH_PING-Alarm fehlgeschlagen: %s", exc)

    # ntfy: Push-Benachrichtigung mit Alarm-Ton fuer Android
    jetzt_lokal = timezone.localtime(vorfall.erstellt_am)
    _ntfy_alarm_senden(vorfall, vorfall.ort, jetzt_lokal.strftime("%H:%M"))


# ---------------------------------------------------------------------------
# Oeffentliche Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def vorfall_ausloesen(request):
    """Erstellt einen neuen EH-Vorfall und loest die Meldekette aus.

    Wird per POST aus dem Navbar-Modal aufgerufen (2-Klick-Bestaetigung).
    """
    ort = request.POST.get("ort", "").strip()
    beschreibung = request.POST.get("beschreibung", "").strip()

    if not ort:
        messages.error(request, "Bitte einen Ort angeben.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    vorfall = ErsteHilfeVorfall.objects.create(
        gemeldet_von=request.user,
        ort=ort,
        beschreibung=beschreibung,
    )

    try:
        _benachrichtige_ersthelfer(vorfall)
    except Exception:
        logger.exception("Fehler beim Benachrichtigen der Ersthelfer (Vorfall %s)", vorfall.pk)

    messages.success(
        request,
        "Erste-Hilfe-Alarm ausgeloest! Alle Ersthelfer wurden benachrichtigt.",
    )
    return redirect("ersthelfe:vorfall_detail", pk=vorfall.pk)


def rueckmeldung(request, token):
    """Tokenbasierte Rueckmeldeseite fuer Ersthelfer (kein Login erforderlich).

    Zeigt 4 grosse Aktions-Buttons. POST speichert die Rueckmeldung.
    """
    token_obj = get_object_or_404(ErsteHilfeErsthelferToken, token=token)
    vorfall = token_obj.vorfall
    ersthelfer = token_obj.ersthelfer

    # Letzte Rueckmeldung dieses Ersthelfers zu diesem Vorfall
    letzte = (
        ErsteHilfeRueckmeldung.objects
        .filter(vorfall=vorfall, ersthelfer=ersthelfer)
        .order_by("-gemeldet_am")
        .first()
    )

    if request.method == "POST":
        neuer_status = request.POST.get("status")
        gueltige_stati = dict(ErsteHilfeRueckmeldung.STATUS_CHOICES).keys()
        if neuer_status not in gueltige_stati:
            return render(request, "ersthelfe/rueckmeldung.html", {
                "vorfall": vorfall,
                "ersthelfer": ersthelfer,
                "letzte": letzte,
                "fehler": "Ungueltiger Status.",
                "STATUS_CHOICES": ErsteHilfeRueckmeldung.STATUS_CHOICES,
            })

        meldung = ErsteHilfeRueckmeldung.objects.create(
            vorfall=vorfall,
            ersthelfer=ersthelfer,
            status=neuer_status,
            notiz=request.POST.get("notiz", "").strip()[:200],
        )

        # Rueckmeldung auch in EH_PING posten
        try:
            from config.kommunikation_utils import matrix_nachricht_senden
            from django.conf import settings
            eh_ping_room = getattr(settings, "MATRIX_EH_PING_ROOM_ID", "")
            if eh_ping_room:
                matrix_nachricht_senden(
                    eh_ping_room,
                    f"EH-Rueckmeldung: {ersthelfer.vollname} – {meldung.get_status_display()}"
                    + (f" ({meldung.notiz})" if meldung.notiz else ""),
                )
        except Exception:
            logger.exception("Fehler beim Senden der EH-Rueckmeldung in Matrix")

        return render(request, "ersthelfe/rueckmeldung_bestaetigung.html", {
            "vorfall": vorfall,
            "ersthelfer": ersthelfer,
            "meldung": meldung,
        })

    return render(request, "ersthelfe/rueckmeldung.html", {
        "vorfall": vorfall,
        "ersthelfer": ersthelfer,
        "letzte": letzte,
        "STATUS_CHOICES": ErsteHilfeRueckmeldung.STATUS_CHOICES,
    })


# ---------------------------------------------------------------------------
# Geschuetzte Views (Betriebsarzt / Staff)
# ---------------------------------------------------------------------------

@login_required
def vorfall_liste(request):
    """Liste aller Vorfaelle – nur fuer EH-Verantwortliche."""
    if not _ist_eh_verantwortlicher(request.user):
        raise PermissionDenied

    vorfaelle = (
        ErsteHilfeVorfall.objects
        .select_related("gemeldet_von")
        .prefetch_related("rueckmeldungen__ersthelfer")
    )
    return render(request, "ersthelfe/vorfall_liste.html", {
        "vorfaelle": vorfaelle,
    })


@login_required
def vorfall_detail(request, pk):
    """Detail eines Vorfalls.

    Eigene Vorfaelle darf jeder sehen, fremde nur EH-Verantwortliche.
    """
    vorfall = get_object_or_404(ErsteHilfeVorfall, pk=pk)

    ist_verantwortlicher = _ist_eh_verantwortlicher(request.user)

    # Ersthelfer duerfen laufende Vorfaelle beobachten (nur lesen)
    ist_ersthelfer = False
    try:
        ist_ersthelfer = request.user.hr_mitarbeiter.ist_ersthelfer
    except Exception:
        pass

    if not ist_verantwortlicher and not ist_ersthelfer and vorfall.gemeldet_von != request.user:
        raise PermissionDenied

    rueckmeldungen = vorfall.rueckmeldungen.select_related("ersthelfer").order_by("-gemeldet_am")
    tokens = vorfall.ersthelfer_tokens.select_related("ersthelfer").all()
    nachrichten = vorfall.nachrichten.select_related("absender").order_by("gesendet_am")
    ist_melder = (vorfall.gemeldet_von == request.user)

    # Status-Zusammenfassung fuer den Melder
    status_zusammenfassung = {}
    if ist_melder and not ist_verantwortlicher:
        for r in rueckmeldungen:
            status_zusammenfassung[r.ersthelfer_id] = r  # neueste pro Ersthelfer
        status_zusammenfassung = list(status_zusammenfassung.values())

    return render(request, "ersthelfe/vorfall_detail.html", {
        "vorfall": vorfall,
        "rueckmeldungen": rueckmeldungen,
        "nachrichten": nachrichten,
        "tokens": tokens,
        "ist_verantwortlicher": ist_verantwortlicher,
        "ist_ersthelfer": ist_ersthelfer,
        "ist_melder": ist_melder,
        "status_zusammenfassung": status_zusammenfassung,
    })


@login_required
@require_POST
def vorfall_schliessen(request, pk):
    """Schliesst einen Vorfall ab (nur EH-Verantwortliche)."""
    if not _ist_eh_verantwortlicher(request.user):
        raise PermissionDenied

    vorfall = get_object_or_404(ErsteHilfeVorfall, pk=pk, status=ErsteHilfeVorfall.STATUS_OFFEN)
    vorfall.status = ErsteHilfeVorfall.STATUS_ABGESCHLOSSEN
    vorfall.geschlossen_am = timezone.now()
    vorfall.save(update_fields=["status", "geschlossen_am"])

    messages.success(request, f"Vorfall {vorfall.pk} wurde abgeschlossen.")
    return redirect("ersthelfe:vorfall_detail", pk=vorfall.pk)


def _vorschlagstext_generieren(vorfall, rueckmeldungen):
    """Erstellt einen strukturierten Vorschlagstext aus dem Systemprotokoll."""
    jetzt_vorfall = timezone.localtime(vorfall.erstellt_am)
    try:
        meldender = vorfall.gemeldet_von.hr_mitarbeiter.vollname
    except Exception:
        meldender = vorfall.gemeldet_von.get_full_name() or vorfall.gemeldet_von.username

    zeilen = [
        f"Erste-Hilfe-Einsatz vom {jetzt_vorfall.strftime('%d.%m.%Y')}",
        f"",
        f"Ort: {vorfall.ort}",
        f"Alarmzeit: {jetzt_vorfall.strftime('%H:%M')} Uhr",
        f"Alarmiert von: {meldender}",
    ]

    if vorfall.beschreibung:
        zeilen += ["", f"Ausgangslage: {vorfall.beschreibung}"]

    zeilen += ["", "Einsatzverlauf (Systemprotokoll):", f"  {jetzt_vorfall.strftime('%H:%M')} Uhr – Alarm ausgeloest"]

    # Rueckmeldungen chronologisch (aelteste zuerst)
    for r in sorted(rueckmeldungen, key=lambda x: x.gemeldet_am):
        t = timezone.localtime(r.gemeldet_am).strftime("%H:%M")
        zeilen.append(f"  {t} Uhr – {r.ersthelfer.vollname}: {r.get_status_display()}"
                      + (f" ({r.notiz})" if r.notiz else ""))

    if vorfall.geschlossen_am:
        t = timezone.localtime(vorfall.geschlossen_am).strftime("%H:%M")
        zeilen.append(f"  {t} Uhr – Vorfall abgeschlossen")

    # Beteiligte Ersthelfer zusammenfassen
    am_ort = [r.ersthelfer.vollname for r in rueckmeldungen if r.status == "am_ort"]
    if am_ort:
        zeilen += ["", f"Vor Ort eingesetzt: {', '.join(dict.fromkeys(am_ort))}"]

    zeilen += [
        "",
        "Ergaenzungen und Bewertung:",
        "[Hier eigene Erganezungen eintragen]",
    ]

    return "\n".join(zeilen)


@login_required
def protokoll_bearbeiten(request, pk):
    """Erstellt oder bearbeitet das Abschlussprotokolll eines Vorfalls."""
    if not _ist_eh_verantwortlicher(request.user):
        raise PermissionDenied

    vorfall = get_object_or_404(ErsteHilfeVorfall, pk=pk)
    rueckmeldungen = list(vorfall.rueckmeldungen.select_related("ersthelfer").order_by("gemeldet_am"))

    if request.method == "POST":
        vorfall.protokoll_text = request.POST.get("protokoll_text", "").strip()
        vorfall.protokoll_bewertung = request.POST.get("protokoll_bewertung", "")
        vorfall.protokoll_erstellt_am = timezone.now()
        vorfall.protokoll_erstellt_von = request.user
        vorfall.save(update_fields=[
            "protokoll_text", "protokoll_bewertung",
            "protokoll_erstellt_am", "protokoll_erstellt_von",
        ])
        messages.success(request, "Protokoll gespeichert.")
        return redirect("ersthelfe:vorfall_detail", pk=vorfall.pk)

    # Vorschlagstext nur wenn noch kein Protokoll vorhanden
    vorschlag = vorfall.protokoll_text or _vorschlagstext_generieren(vorfall, rueckmeldungen)

    return render(request, "ersthelfe/protokoll_bearbeiten.html", {
        "vorfall": vorfall,
        "vorschlag": vorschlag,
        "BEWERTUNG_CHOICES": ErsteHilfeVorfall.BEWERTUNG_CHOICES,
    })


@login_required
def arbeitsschutz_uebersicht(request):
    """Uebersicht aller EH-Vorfaelle fuer den Arbeitsschutz (Betriebsarzt/Staff).

    Zeigt Statistiken, kritische Rueckmeldungen und Freitextnachrichten der letzten
    Vorfaelle auf einen Blick.
    """
    if not _ist_eh_verantwortlicher(request.user):
        raise PermissionDenied

    from datetime import datetime, timedelta

    from django.db.models import Count, Prefetch

    # Zeitraum: letztes Jahr, per GET-Parameter eingrenzbar
    heute = timezone.localdate()
    try:
        von_str = request.GET.get("von", "")
        von_datum = datetime.strptime(von_str, "%Y-%m-%d").date() if von_str else heute - timedelta(days=365)
    except ValueError:
        von_datum = heute - timedelta(days=365)
    try:
        bis_str = request.GET.get("bis", "")
        bis_datum = datetime.strptime(bis_str, "%Y-%m-%d").date() if bis_str else heute
    except ValueError:
        bis_datum = heute

    vorfaelle = (
        ErsteHilfeVorfall.objects
        .filter(erstellt_am__date__gte=von_datum, erstellt_am__date__lte=bis_datum)
        .select_related("gemeldet_von")
        .prefetch_related(
            Prefetch(
                "rueckmeldungen",
                queryset=ErsteHilfeRueckmeldung.objects.select_related("ersthelfer").order_by("gemeldet_am"),
            ),
            Prefetch(
                "nachrichten",
                queryset=ErsteHilfeNachricht.objects.select_related("absender").order_by("gesendet_am"),
            ),
        )
        .order_by("-erstellt_am")
    )

    # Statistiken
    gesamt = vorfaelle.count()
    offen = sum(1 for v in vorfaelle if v.ist_offen)
    abgeschlossen = gesamt - offen

    # Kritische Rueckmeldungen (alle Vorfaelle im Zeitraum)
    kritische_rueckmeldungen = (
        ErsteHilfeRueckmeldung.objects
        .filter(
            vorfall__erstellt_am__date__gte=von_datum,
            vorfall__erstellt_am__date__lte=bis_datum,
            status__in=list(ErsteHilfeRueckmeldung.STATUS_KRITISCH),
        )
        .select_related("ersthelfer", "vorfall")
        .order_by("-gemeldet_am")
    )

    # Haeufigkeit der Status-Typen
    status_statistik = (
        ErsteHilfeRueckmeldung.objects
        .filter(
            vorfall__erstellt_am__date__gte=von_datum,
            vorfall__erstellt_am__date__lte=bis_datum,
        )
        .values("status")
        .annotate(anzahl=Count("id"))
        .order_by("-anzahl")
    )
    # Status-Label nachschlagen
    status_label_map = dict(ErsteHilfeRueckmeldung.STATUS_CHOICES)
    status_farbe_map = ErsteHilfeRueckmeldung.STATUS_FARBE
    for eintrag in status_statistik:
        eintrag["label"] = status_label_map.get(eintrag["status"], eintrag["status"])
        eintrag["farbe"] = status_farbe_map.get(eintrag["status"], "secondary")

    # Freitextnachrichten (fuer Aufmerksamkeit des Arbeitsschutzes)
    freitextnachrichten = (
        ErsteHilfeNachricht.objects
        .filter(
            vorfall__erstellt_am__date__gte=von_datum,
            vorfall__erstellt_am__date__lte=bis_datum,
        )
        .select_related("absender", "vorfall")
        .order_by("-gesendet_am")
    )

    return render(request, "ersthelfe/arbeitsschutz_uebersicht.html", {
        "vorfaelle": vorfaelle,
        "gesamt": gesamt,
        "offen": offen,
        "abgeschlossen": abgeschlossen,
        "kritische_rueckmeldungen": kritische_rueckmeldungen,
        "status_statistik": status_statistik,
        "freitextnachrichten": freitextnachrichten,
        "von_datum": von_datum,
        "bis_datum": bis_datum,
    })


@login_required
def protokoll_pdf(request, pk):
    """Erzeugt das Einsatzprotokoll als PDF."""
    if not _ist_eh_verantwortlicher(request.user):
        raise PermissionDenied

    vorfall = get_object_or_404(ErsteHilfeVorfall, pk=pk)
    rueckmeldungen = vorfall.rueckmeldungen.select_related("ersthelfer").order_by("gemeldet_am")

    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from weasyprint import HTML

    html_string = render_to_string("ersthelfe/protokoll_pdf.html", {
        "vorfall": vorfall,
        "rueckmeldungen": rueckmeldungen,
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    dateiname = f"EH-Protokoll-{vorfall.pk}-{timezone.localdate().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response


@login_required
def tetra_info(request):
    """Informationsseite: TETRA-BOS-Anbindung an PRIMA (Konzept & Machbarkeit)."""
    return render(request, "ersthelfe/tetra_info.html")


@login_required
def eh_status_json(request):
    """Leichtgewichtiger JSON-Endpunkt fuer den Client-seitigen EH-Status-Poller.

    Gibt zurueck ob gerade ein offener Vorfall vorliegt (und der Banner aktiv waere).
    Wird alle 10 Sekunden vom Browser abgefragt – nur eingeloggte Nutzer.
    """
    from django.http import JsonResponse
    from .context_processors import eh_badge

    data = eh_badge(request)
    return JsonResponse({
        "aktiv": data.get("eh_banner_aktiv", False),
        "ort": data.get("eh_banner_ort", ""),
        "zeit": data.get("eh_banner_zeit", ""),
        "pk": data.get("eh_banner_pk"),
    })

