# -*- coding: utf-8 -*-
"""Views fuer Zeitgutschrift-Antraege."""

import datetime as _dt
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from arbeitszeit.models import get_feiertagskalender
from formulare.forms import ZeitgutschriftForm
from formulare.models import Zeitgutschrift, ZeitgutschriftBeleg

from ._utils import (
    _auto_signiere_zeitgutschrift,
    _hole_antrag_signatur,
    _offene_antraege_fuer_user,
    _starte_workflow_fuer_antrag,
)

logger = logging.getLogger(__name__)


def _dezimal_zu_hmin(stunden):
    """Konvertiert Dezimalstunden in 'Xh YYmin' Format. Z.B. 7.8 -> '7h 48min'."""
    h = int(stunden)
    m = round((stunden - h) * 60)
    if m == 60:
        h += 1
        m = 0
    return f"{h}h {m:02d}min"


def _minuten_zu_hmin(minuten):
    """Formatiert Minuten (auch negativ) als '+Xh MMmin' oder '-Xh MMmin'."""
    vorzeichen = "-" if minuten < 0 else "+"
    abs_min = abs(minuten)
    h = abs_min // 60
    m = abs_min % 60
    return f"{vorzeichen}{h}h {m:02d}min"


def _regelarbeitszeit_fuer_tag(mitarbeiter, datum):
    """Regelarbeitszeit in Minuten fuer einen bestimmten Tag.

    Beruecksichtigt Arbeitszeitvereinbarung und Mehrwochenmodelle.
    Gibt 0 zurueck fuer Wochenenden oder wenn keine Vereinbarung vorhanden.
    """
    if datum.weekday() >= 5:
        return 0

    vereinbarung = mitarbeiter.get_aktuelle_vereinbarung(stichtag=datum)
    if not vereinbarung:
        return 0

    if vereinbarung.arbeitszeit_typ == "regelmaessig" and vereinbarung.wochenstunden:
        return round(float(vereinbarung.wochenstunden) * 60 / 5)

    if vereinbarung.arbeitszeit_typ == "individuell":
        wt_map = {
            0: "montag", 1: "dienstag", 2: "mittwoch",
            3: "donnerstag", 4: "freitag",
        }
        wochentag = wt_map.get(datum.weekday())
        woche = vereinbarung.zyklus_woche_fuer_datum(datum) or 1
        ta = vereinbarung.tagesarbeitszeiten.filter(
            wochentag=wochentag, woche=woche
        ).first()
        if ta and ta.zeitwert:
            return (ta.zeitwert // 100) * 60 + (ta.zeitwert % 100)

    return 0


def _gutschrift_minuten_fuer_eintrag(eintrag, regel_minuten):
    """Gutschrift in Minuten fuer einen einzelnen Tagebucheintrag.

    Fall 1: 0 (Terminalerfassung genuegt)
    Fall 2: tatsaechliche Zeit - Regelarbeitszeit (kann negativ sein)
    Fall 3: tatsaechliche Zeit / 3
    """
    if eintrag.fall == 1:
        return 0
    if eintrag.fall == 2:
        return eintrag.dauer_minuten - regel_minuten
    if eintrag.fall == 3:
        return round(eintrag.dauer_minuten / 3)
    return 0


def _berechne_tagebuch_gesamt(antrag, mitarbeiter):
    """Gesamtgutschrift aller Tagebucheintraege in Minuten (kann negativ sein)."""
    total = 0
    for eintrag in antrag.tagebuch_eintraege.all():
        regel = _regelarbeitszeit_fuer_tag(mitarbeiter, eintrag.datum)
        total += _gutschrift_minuten_fuer_eintrag(eintrag, regel)
    return total


def _berechne_fortbildung(mitarbeiter, von_datum, bis_datum, wochenstunden_regulaer):
    """Berechnet Zeitgutschrift fuer ganztaegige Fortbildung.

    Iteriert ueber Arbeitstage (Mo-Fr ohne Feiertage) und vergleicht:
    - Fortbildungs-Soll (eingegebene taegliche Sollzeit)
    - Vereinbarungs-Soll (aus get_aktuelle_vereinbarung)

    Gibt JSON-Struktur mit Zeilen, Summen und Differenz zurueck.
    """
    from datetime import timedelta
    try:
        # Feiertagskalender
        feiertage = get_feiertagskalender(mitarbeiter.standort)

        # Taegliche Sollzeit aus eingegebenen Wochenstunden
        taegliche_sollzeit = wochenstunden_regulaer / 5

        zeilen = []
        summe_fortbildung = 0
        summe_vereinbarung = 0

        # Iteriere ueber Datumsbereich
        aktuell = von_datum
        while aktuell <= bis_datum:
            # Nur Arbeitstage (Mo-Fr ohne Feiertage) - workalendar-API verwenden
            if feiertage.is_working_day(aktuell):
                # Vereinbarungs-Soll holen (taegliche Sollzeit aus Wochenstunden)
                vereinbarung = mitarbeiter.get_aktuelle_vereinbarung(aktuell)
                if vereinbarung and vereinbarung.wochenstunden:
                    vereinbarung_soll = float(vereinbarung.wochenstunden) / 5
                else:
                    vereinbarung_soll = 0

                # Wochentag als Text
                wochentag_text = [
                    "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                    "Samstag", "Sonntag"
                ][aktuell.weekday()]

                zeilen.append({
                    "datum": aktuell.strftime("%d.%m.%Y"),
                    "wochentag": wochentag_text,
                    "fortbildung_soll": _dezimal_zu_hmin(float(taegliche_sollzeit)),
                    "vereinbarung_soll": _dezimal_zu_hmin(float(vereinbarung_soll)),
                })

                summe_fortbildung += float(taegliche_sollzeit)
                summe_vereinbarung += float(vereinbarung_soll)

            aktuell += timedelta(days=1)

        # Differenz berechnen
        differenz = abs(summe_fortbildung - summe_vereinbarung)
        differenz_hoeherer = (
            "fortbildung" if summe_fortbildung > summe_vereinbarung
            else "vereinbarung"
        )

        return {
            "zeilen": zeilen,
            "summe_fortbildung": _dezimal_zu_hmin(summe_fortbildung),
            "summe_vereinbarung": _dezimal_zu_hmin(summe_vereinbarung),
            "differenz": _dezimal_zu_hmin(differenz),
            "differenz_hoeherer": differenz_hoeherer,
        }
    except Exception as e:
        logger.error("Fehler in _berechne_fortbildung: %s", e)
        return None


@login_required
def zeitgutschrift_antrag(request):
    """Haupt-View fuer Zeitgutschrift-Antraege.

    Unterstuetzt drei Arten:
    - Haertefallregelung
    - Ehrenamt
    - Fortbildung (mit Berechnung)
    """
    form = ZeitgutschriftForm(request.POST or None, request.FILES or None)

    if request.method == "POST":
        if form.is_valid():
            antrag = form.save(commit=False)
            antrag.antragsteller = request.user.mitarbeiter

            # Art-spezifische Verarbeitung
            art = antrag.art

            if art in ("haertefall", "ehrenamt"):
                # Zeilen aus POST sammeln
                zeile_datums = request.POST.getlist("zeile_datum")
                zeile_von_zeits = request.POST.getlist("zeile_von_zeit")
                zeile_bis_zeits = request.POST.getlist("zeile_bis_zeit")

                zeilen_daten = []
                for i in range(len(zeile_datums)):
                    zeile = {
                        "datum": zeile_datums[i] if i < len(zeile_datums) else "",
                        "von_zeit": zeile_von_zeits[i] if i < len(zeile_von_zeits) else "",
                        "bis_zeit": zeile_bis_zeits[i] if i < len(zeile_bis_zeits) else "",
                    }
                    if any(zeile.values()):
                        zeilen_daten.append(zeile)

                if not zeilen_daten:
                    form.add_error(None, "Mindestens eine Zeile ist erforderlich.")
                    context = {"form": form}
                    return render(
                        request,
                        "formulare/zeitgutschrift_antrag.html",
                        context,
                    )

                antrag.zeilen_daten = zeilen_daten

            elif art in ("erkrankung_angehoerige", "erkrankung_kind", "erkrankung_betreuung"):
                from decimal import Decimal, InvalidOperation
                erkrankung_typ = request.POST.get("erkrankung_typ", "")
                datum_str = request.POST.get("erkrankung_datum", "")
                antrag.erkrankung_typ = erkrankung_typ

                if datum_str:
                    from datetime import datetime as dt
                    try:
                        erkrankung_datum = dt.strptime(datum_str, "%Y-%m-%d").date()
                        # Wochenende pruefen
                        if erkrankung_datum.weekday() >= 5:
                            wochentag = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                                         "Freitag", "Samstag", "Sonntag"][erkrankung_datum.weekday()]
                            form.add_error(None, f"Das Datum ist ein {wochentag} – kein Arbeitstag.")
                            return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                        # Feiertag pruefen
                        cal = get_feiertagskalender(request.user.mitarbeiter.standort)
                        if cal.is_holiday(erkrankung_datum):
                            from arbeitszeit.models import feiertag_name_deutsch
                            name = feiertag_name_deutsch(cal, erkrankung_datum)
                            form.add_error(None, f"Das Datum ist ein Feiertag ({name}).")
                            return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                        antrag.erkrankung_datum = erkrankung_datum
                    except ValueError:
                        form.add_error(None, "Ungaeltiges Datum.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

                if erkrankung_typ == "regulaer":
                    try:
                        wochenstunden = Decimal(request.POST.get("erkrankung_wochenstunden", ""))
                        antrag.erkrankung_wochenstunden = wochenstunden
                        antrag.erkrankung_gutschrift_stunden = (wochenstunden / 5) / 2
                    except InvalidOperation:
                        form.add_error(None, "Bitte gueltige Wochenstunden eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

                elif erkrankung_typ == "individuell":
                    try:
                        tagesstunden = Decimal(request.POST.get("erkrankung_tagesstunden", ""))
                        antrag.erkrankung_tagesstunden = tagesstunden
                        antrag.erkrankung_gutschrift_stunden = tagesstunden / 2
                    except InvalidOperation:
                        form.add_error(None, "Bitte gueltige Tagesstunden eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                else:
                    form.add_error(None, "Bitte Art der Arbeitszeit auswaehlen.")
                    return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

            elif art == "sonstige":
                try:
                    antrag.mehrarbeit_buchungsmonat = int(request.POST.get("mehrarbeit_buchungsmonat", 0))
                    antrag.mehrarbeit_buchungsjahr = int(request.POST.get("mehrarbeit_buchungsjahr", 0))
                    antrag.mehrarbeit_stunden = int(request.POST.get("mehrarbeit_stunden", 0))
                    antrag.mehrarbeit_minuten = int(request.POST.get("mehrarbeit_minuten", 0))
                    antrag.mehrarbeit_begruendung = request.POST.get("mehrarbeit_begruendung", "")
                    vorzeichen = request.POST.get("sonstige_vorzeichen", "")
                    if vorzeichen not in ("+", "-"):
                        form.add_error(None, "Bitte Plus oder Minus auswaehlen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    antrag.sonstige_vorzeichen = vorzeichen
                    if not (1 <= antrag.mehrarbeit_buchungsmonat <= 12):
                        form.add_error(None, "Bitte einen gueltigen Monat auswaehlen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if antrag.mehrarbeit_stunden == 0 and antrag.mehrarbeit_minuten == 0:
                        form.add_error(None, "Bitte Stunden oder Minuten eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if not (0 <= antrag.mehrarbeit_minuten <= 59):
                        form.add_error(None, "Minuten muessen zwischen 0 und 59 liegen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                except (ValueError, TypeError):
                    form.add_error(None, "Ungueltige Eingabe.")
                    return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

            elif art in ("mehrarbeit", "mehrarbeit_buchung", "ueberstunden_buchung", "rufbereitschaft_buchung"):
                try:
                    antrag.mehrarbeit_buchungsmonat = int(request.POST.get("mehrarbeit_buchungsmonat", 0))
                    antrag.mehrarbeit_buchungsjahr = int(request.POST.get("mehrarbeit_buchungsjahr", 0))
                    antrag.mehrarbeit_stunden = int(request.POST.get("mehrarbeit_stunden", 0))
                    antrag.mehrarbeit_minuten = int(request.POST.get("mehrarbeit_minuten", 0))
                    antrag.mehrarbeit_begruendung = request.POST.get("mehrarbeit_begruendung", "")
                    if not (1 <= antrag.mehrarbeit_buchungsmonat <= 12):
                        form.add_error(None, "Bitte einen gueltigen Monat auswaehlen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if antrag.mehrarbeit_stunden == 0 and antrag.mehrarbeit_minuten == 0:
                        form.add_error(None, "Bitte Stunden oder Minuten eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if not (0 <= antrag.mehrarbeit_minuten <= 59):
                        form.add_error(None, "Minuten muessen zwischen 0 und 59 liegen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                except (ValueError, TypeError):
                    form.add_error(None, "Ungueltige Eingabe.")
                    return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

            elif art == "fortbildung" and antrag.fortbildung_aktiv:
                # Berechnung durchfuehren
                berechnung = _berechne_fortbildung(
                    request.user.mitarbeiter,
                    antrag.fortbildung_von_datum,
                    antrag.fortbildung_bis_datum,
                    antrag.fortbildung_wochenstunden_regulaer,
                )
                antrag.fortbildung_berechnung = berechnung

            # Antrag speichern
            antrag.save()

            # Belege hochladen (mit optionalem Virenscan)
            from utils.virusscanner import scan_mehrere_dateien
            belege = request.FILES.getlist("belege")
            if belege:
                alle_sauber, ergebnisse = scan_mehrere_dateien(belege)
                if not alle_sauber:
                    infizierte = [
                        e.bedrohung for e in ergebnisse if not e.sauber
                    ]
                    from django.contrib import messages
                    messages.error(
                        request,
                        f"Upload abgelehnt: Bedrohung gefunden – {', '.join(infizierte)}",
                    )
                    antrag.delete()
                    return redirect("formulare:zeitgutschrift_antrag")
            for beleg in belege:
                ZeitgutschriftBeleg.objects.create(
                    zeitgutschrift=antrag,
                    datei=beleg,
                    dateiname_original=beleg.name,
                )

            _auto_signiere_zeitgutschrift(antrag, request)

            # Workflow starten (falls aktives Template vorhanden)
            _starte_workflow_fuer_antrag("zeitgutschrift_erstellt", antrag, request.user)

            # Erfolgs-Seite
            return redirect("formulare:zeitgutschrift_erfolg", pk=antrag.pk)

        # Fehler: HTMX-Support
        if request.headers.get("HX-Request"):
            return render(
                request,
                "formulare/partials/_zeitgutschrift_felder.html",
                {"form": form},
            )

    context = {"form": form}
    return render(request, "formulare/zeitgutschrift_antrag.html", context)


@login_required
def zeitgutschrift_felder(request):
    """HTMX-View: Gibt Art-abhaengige Felder zurueck."""
    from django.utils import timezone

    art = request.GET.get("art", "")
    individ = request.GET.get("individ_bestaetigung", "")
    erkrankung_typ = request.GET.get("erkrankung_typ", "")
    form = ZeitgutschriftForm(initial={"art": art})

    heute = timezone.localdate()
    monate = [
        (1, "Januar"), (2, "Februar"), (3, "Maerz"), (4, "April"),
        (5, "Mai"), (6, "Juni"), (7, "Juli"), (8, "August"),
        (9, "September"), (10, "Oktober"), (11, "November"), (12, "Dezember"),
    ]
    jahre = list(range(heute.year - 1, heute.year + 2))

    context = {
        "form": form,
        "art": art,
        "individ": individ,
        "erkrankung_typ": erkrankung_typ,
        "monate": monate,
        "jahre": jahre,
        "aktuelles_monat": heute.month,
        "aktuelles_jahr": heute.year,
    }
    response = render(
        request,
        "formulare/partials/_zeitgutschrift_felder.html",
        context,
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
def neue_zeitgutschrift_zeile(request):
    """HTMX-View: Gibt neue leere Zeile zurueck."""
    return render(request, "formulare/partials/_zeitgutschrift_zeile.html")


@login_required
def zeitgutschrift_fortbildung_berechnen(request):
    """HTMX-View: Live-Berechnung fuer Fortbildung."""
    # Daten aus POST holen
    von_datum_str = request.POST.get("fortbildung_von_datum")
    bis_datum_str = request.POST.get("fortbildung_bis_datum")
    wochenstunden_str = request.POST.get("fortbildung_wochenstunden_regulaer")

    berechnung = None

    try:
        if von_datum_str and bis_datum_str and wochenstunden_str:
            from datetime import datetime
            von_datum = datetime.strptime(von_datum_str, "%Y-%m-%d").date()
            bis_datum = datetime.strptime(bis_datum_str, "%Y-%m-%d").date()
            wochenstunden = float(wochenstunden_str)

            berechnung = _berechne_fortbildung(
                request.user.mitarbeiter,
                von_datum,
                bis_datum,
                wochenstunden,
            )
    except (ValueError, AttributeError):
        pass

    context = {"berechnung": berechnung}
    return render(
        request,
        "formulare/partials/_fortbildung_berechnung.html",
        context,
    )


@login_required
def zeitgutschrift_datum_pruefen(request):
    """HTMX-View: Prueft ob ein Datum ein gueltiger Arbeitstag ist (kein Wochenende/Feiertag)."""
    from datetime import datetime as dt

    datum_str = request.POST.get("erkrankung_datum", "")
    fehler = None

    if datum_str:
        try:
            datum = dt.strptime(datum_str, "%Y-%m-%d").date()
            mitarbeiter = request.user.mitarbeiter

            if datum.weekday() >= 5:
                wochentag = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                             "Freitag", "Samstag", "Sonntag"][datum.weekday()]
                fehler = f"{datum.strftime('%d.%m.%Y')} ist ein {wochentag} – kein Arbeitstag."
            else:
                cal = get_feiertagskalender(mitarbeiter.standort)
                if cal.is_holiday(datum):
                    from arbeitszeit.models import feiertag_name_deutsch
                    name = feiertag_name_deutsch(cal, datum)
                    fehler = f"{datum.strftime('%d.%m.%Y')} ist ein Feiertag ({name})."
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_erkrankung_datum_pruefung.html",
        {"fehler": fehler},
    )


@login_required
def zeitgutschrift_erkrankung_berechnen(request):
    """HTMX-View: Live-Berechnung der Zeitgutschrift fuer Erkrankung eines Angehoerigen."""
    from decimal import Decimal, InvalidOperation

    erkrankung_typ = request.POST.get("erkrankung_typ", "")
    gutschrift = None
    fehler = None

    try:
        if erkrankung_typ == "regulaer":
            wochenstunden = Decimal(request.POST.get("erkrankung_wochenstunden", ""))
            tageszeit = wochenstunden / 5
            gutschrift = tageszeit / 2
        elif erkrankung_typ == "individuell":
            tagesstunden = Decimal(request.POST.get("erkrankung_tagesstunden", ""))
            gutschrift = tagesstunden / 2
    except InvalidOperation:
        fehler = "Bitte gueltige Stunden eingeben."

    gutschrift_hmin = _dezimal_zu_hmin(float(gutschrift)) if gutschrift is not None else None
    context = {"gutschrift": gutschrift, "gutschrift_hmin": gutschrift_hmin, "fehler": fehler}
    return render(
        request,
        "formulare/partials/_erkrankung_berechnung.html",
        context,
    )


@login_required
def zeitgutschrift_detail(request, pk):
    """Detail-Ansicht fuer Genehmiger, Antragsteller und Workflow-Bearbeiter."""
    antrag = get_object_or_404(Zeitgutschrift, pk=pk)

    # Berechtigungspruefung: Antragsteller oder Genehmiger
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_genehmiger = antrag.antragsteller in berechtigte_ma

    # Workflow-Berechtigung: Hat User einen Task fuer diesen Antrag?
    hat_workflow_task = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        # Direkt zugewiesene Tasks
        hat_workflow_task = WorkflowTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung"],
            zugewiesen_an_user=request.user
        ).exists()

        # Oder Tasks an die Stelle des Users
        if not hat_workflow_task and hasattr(request.user, "hr_mitarbeiter"):
            stelle = request.user.hr_mitarbeiter.stelle
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_stelle=stelle
            ).exists()

        # Oder Tasks an ein Team, in dem der User Mitglied ist
        if not hat_workflow_task:
            from formulare.models import TeamQueue
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_team__in=user_teams
            ).exists()

    # Team-Queue-Berechtigung: Hat User den Antrag geclaimed?
    hat_antrag_geclaimed = antrag.claimed_von == request.user

    # Staff und Superuser haben immer Lesezugriff
    ist_admin = request.user.is_superuser or request.user.is_staff

    if not (ist_antragsteller or ist_genehmiger or hat_workflow_task
            or hat_antrag_geclaimed or ist_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Optional: aus Team-Queue geoeffnet -> queue_task fuer Erledigen-Button
    queue_task = None
    queue_task_pk = request.GET.get("queue_task")
    if queue_task_pk:
        from workflow.models import WorkflowTask
        try:
            queue_task = WorkflowTask.objects.select_related("step").get(
                pk=queue_task_pk,
                claimed_von=request.user,
                status="in_bearbeitung",
            )
        except WorkflowTask.DoesNotExist:
            pass

    context = {
        "antrag": antrag,
        "ist_genehmiger": ist_genehmiger,
        "ist_antragsteller": ist_antragsteller,
        "queue_task": queue_task,
    }
    return render(request, "formulare/zeitgutschrift_detail.html", context)


@login_required
def zeitgutschrift_erfolg(request, pk):
    """Erfolgs-Seite nach Antragstellung."""
    antrag = get_object_or_404(Zeitgutschrift, pk=pk)

    # Berechtigungspruefung: Antragsteller oder Genehmiger
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    if (
        antrag.antragsteller.user != request.user
        and antrag.antragsteller not in berechtigte_ma
    ):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    context = {
        "antrag": antrag,
        "antrag_signatur": _hole_antrag_signatur("zeitgutschrift", antrag.pk),
    }
    return render(request, "formulare/zeitgutschrift_erfolg.html", context)


@login_required
def zeitgutschrift_pdf(request, pk):
    """PDF-Download fuer Zeitgutschrift-Antrag."""
    antrag = get_object_or_404(Zeitgutschrift, pk=pk)

    # Berechtigungspruefung: Antragsteller, Genehmiger oder Workflow-Bearbeiter
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_genehmiger = antrag.antragsteller in berechtigte_ma

    # Workflow-Berechtigung: Hat User einen Task fuer diesen Antrag?
    hat_workflow_task = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        # Direkt zugewiesene Tasks
        hat_workflow_task = WorkflowTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung"],
            zugewiesen_an_user=request.user
        ).exists()

        # Oder Tasks an die Stelle des Users
        if not hat_workflow_task and hasattr(request.user, "hr_mitarbeiter"):
            stelle = request.user.hr_mitarbeiter.stelle
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_stelle=stelle
            ).exists()

        # Oder Tasks an ein Team, in dem der User Mitglied ist
        if not hat_workflow_task:
            from formulare.models import TeamQueue
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_team__in=user_teams
            ).exists()

    # Team-Queue-Berechtigung: Hat User den Antrag geclaimed?
    hat_antrag_geclaimed = antrag.claimed_von == request.user

    ist_admin = request.user.is_superuser or request.user.is_staff

    if not (ist_antragsteller or ist_genehmiger or hat_workflow_task
            or hat_antrag_geclaimed or ist_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Bei Reisezeit-Tagebuch: Tagebuch-Daten fuer PDF aufbereiten
    tagebuch_tage = []
    tagebuch_gesamt_min = 0
    tagebuch_gesamt_hmin = ""
    dienstreise = None

    if antrag.art == "reisezeit_tagebuch":
        try:
            dienstreise = antrag.reisezeit_dienstreise
        except Exception:
            dienstreise = None

        if dienstreise:
            WOCHENTAGE = [
                "Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag",
            ]
            mitarbeiter = dienstreise.antragsteller
            aktuell = dienstreise.von_datum
            while aktuell <= dienstreise.bis_datum:
                eintraege = dienstreise.tagebuch_eintraege.filter(datum=aktuell)
                regel_minuten = _regelarbeitszeit_fuer_tag(mitarbeiter, aktuell)
                eintraege_info = []
                for e in eintraege:
                    gutschrift_min = _gutschrift_minuten_fuer_eintrag(
                        e, regel_minuten
                    )
                    eintraege_info.append({
                        "eintrag": e,
                        "gutschrift_min": gutschrift_min,
                        "gutschrift_hmin": (
                            _minuten_zu_hmin(gutschrift_min)
                            if e.fall != 1 else "-"
                        ),
                    })
                tagebuch_tage.append({
                    "datum": aktuell,
                    "wochentag": WOCHENTAGE[aktuell.weekday()],
                    "ist_wochenende": aktuell.weekday() >= 5,
                    "regel_minuten": regel_minuten,
                    "eintraege": eintraege_info,
                })
                aktuell += _dt.timedelta(days=1)

            tagebuch_gesamt_min = _berechne_tagebuch_gesamt(
                dienstreise, mitarbeiter
            )
            tagebuch_gesamt_hmin = _minuten_zu_hmin(tagebuch_gesamt_min)

    # PDF mit WeasyPrint generieren
    try:
        from weasyprint import HTML
        import datetime as dt

        zg_workflow_tasks = []
        if antrag.workflow_instance:
            from workflow.models import WorkflowTask
            zg_workflow_tasks = list(
                WorkflowTask.objects
                .filter(instance=antrag.workflow_instance)
                .select_related("step", "erledigt_von")
                .order_by("step__reihenfolge")
            )

        html_string = render_to_string(
            "formulare/pdf/zeitgutschrift_pdf.html",
            {
                "antrag": antrag,
                "dienstreise": dienstreise,
                "tagebuch_tage": tagebuch_tage,
                "tagebuch_gesamt_min": tagebuch_gesamt_min,
                "tagebuch_gesamt_hmin": tagebuch_gesamt_hmin,
                "workflow_tasks": zg_workflow_tasks,
                "now": dt.datetime.now(),
            },
        )

        dateiname_zg = f"zeitgutschrift_{antrag.id}.pdf"

        # Option B: Gespeichertes signiertes PDF zurueckgeben wenn vorhanden.
        # (Signaturen akkumulieren sich bei jeder Aktion des jeweiligen Users.)
        from formulare.views._utils import _lade_signatur_pdf
        gespeichertes = _lade_signatur_pdf(antrag)
        if gespeichertes:
            pdf = gespeichertes
        else:
            # Fallback: Frisch generieren + mit aktuellem User signieren
            from formulare.views._utils import _signiere_und_speichere
            html = HTML(string=html_string, base_url=request.build_absolute_uri())
            pdf_roh = html.write_pdf()
            pdf = _signiere_und_speichere(antrag, request.user, pdf_roh, dateiname_zg)

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="{dateiname_zg}"'
        )
        return response
    except ImportError:
        return HttpResponse(
            "WeasyPrint nicht installiert. Bitte 'weasyprint' installieren.",
            status=500,
        )
