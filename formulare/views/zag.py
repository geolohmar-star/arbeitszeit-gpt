# -*- coding: utf-8 -*-
"""Views fuer Z-AG-Antraege und Z-AG-Stornierungen."""

import logging
import uuid
from datetime import date as date_type, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from arbeitszeit.models import Tagesarbeitszeit, Zeiterfassung, get_feiertagskalender
from formulare.models import ZAGAntrag, ZAGStorno

from ._utils import (
    WOCHENTAG_MAP,
    _auto_signiere_zag,
    _get_queue_task_aus_request,
    _get_team_bearbeiter_task,
    _hole_antrag_signatur,
    _ist_team_mitglied_fuer_antrag,
    _offene_antraege_fuer_user,
    _sammle_workflow_unterzeichner,
    _signiere_pdf_alle_unterzeichner,
    _starte_workflow_fuer_antrag,
    _vereinbarung_fuer_mitarbeiter,
)

logger = logging.getLogger(__name__)


def _soll_minuten_fuer_datum(mitarbeiter, datum):
    """Berechnet Soll-Minuten aus Vereinbarung fuer ein Datum.

    Gibt None zurueck wenn keine Vereinbarung vorhanden.
    """
    if datum.weekday() >= 5:
        # Wochenenden haben keine Soll-Zeit
        return 0

    vereinbarung = _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum)
    if not vereinbarung:
        return None

    wochentag_name = WOCHENTAG_MAP[datum.weekday()]

    if vereinbarung.arbeitszeit_typ == "individuell":
        tage = Tagesarbeitszeit.objects.filter(
            vereinbarung=vereinbarung,
            wochentag=wochentag_name,
        )
        if tage.exists():
            gesamt = sum(t.zeit_in_minuten for t in tage)
            return int(round(gesamt / tage.count()))
        return 0

    if vereinbarung.wochenstunden:
        return int(round(float(vereinbarung.wochenstunden) / 5 * 60))
    return None


def _erstelle_zag_eintraege(mitarbeiter, datum_von, datum_bis, bemerkung):
    """Erstellt Zeiterfassungs-Eintraege fuer einen Z-AG-Zeitraum.

    Wochenenden und Feiertage (standortabhaengig) werden uebersprungen.
    Gibt die Anzahl erstellter Eintraege zurueck.
    """
    cal = get_feiertagskalender(mitarbeiter.standort)
    aktuell = datum_von
    anzahl = 0
    while aktuell <= datum_bis:
        # Nur Werktage (Mo-Fr) und keine Feiertage
        if aktuell.weekday() < 5 and not cal.is_holiday(aktuell):
            soll_minuten = _soll_minuten_fuer_datum(mitarbeiter, aktuell)
            Zeiterfassung.objects.update_or_create(
                mitarbeiter=mitarbeiter,
                datum=aktuell,
                defaults={
                    "art": "z_ag",
                    "arbeitsbeginn": None,
                    "arbeitsende": None,
                    "pause_minuten": 0,
                    "arbeitszeit_minuten": 0,
                    "soll_minuten": soll_minuten,
                    "bemerkung": bemerkung,
                },
            )
            anzahl += 1
        aktuell += timedelta(days=1)
    return anzahl


def _zag_jahres_kontext(mitarbeiter):
    """Berechnet Z-AG-Tage des laufenden Jahres fuer den Kontext."""
    jahr = date_type.today().year
    z_ag_tage_jahr = Zeiterfassung.objects.filter(
        mitarbeiter=mitarbeiter,
        datum__year=jahr,
        art="z_ag",
    ).count()
    return {"z_ag_tage_jahr": z_ag_tage_jahr, "z_ag_jahr": jahr}


def _zaehle_zag_tage(mitarbeiter, datum_von, datum_bis):
    """Zaehlt Arbeitstage im Zeitraum exklusive Wochenenden, Feiertage
    und (bei individueller Vereinbarung) vertragsfreier Wochentage.
    """
    cal = get_feiertagskalender(mitarbeiter.standort)

    # Vereinbarung zum Startdatum (wird fuer gesamten Zeitraum genutzt)
    vereinbarung = _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum_von)

    # Freie Wochentage aus individueller Vereinbarung ermitteln
    freie_wochentage = set()
    if vereinbarung and vereinbarung.arbeitszeit_typ == "individuell":
        for wt_num in range(5):  # Mo-Fr
            wt_name = WOCHENTAG_MAP[wt_num]
            tage_vb = Tagesarbeitszeit.objects.filter(
                vereinbarung=vereinbarung,
                wochentag=wt_name,
            )
            if not tage_vb.exists() or all(t.zeitwert == 0 for t in tage_vb):
                freie_wochentage.add(wt_num)

    aktuell = datum_von
    anzahl = 0
    while aktuell <= datum_bis:
        if (
            aktuell.weekday() < 5
            and not cal.is_holiday(aktuell)
            and aktuell.weekday() not in freie_wochentage
        ):
            anzahl += 1
        aktuell += timedelta(days=1)
    return anzahl


def _storniere_zag_eintraege(mitarbeiter, datum_von, datum_bis):
    """Loescht Z-AG-Zeiterfassungs-Eintraege im Zeitraum.

    Gibt die Anzahl tatsaechlich geloeschter Eintraege zurueck.
    """
    deleted, _ = Zeiterfassung.objects.filter(
        mitarbeiter=mitarbeiter,
        art="z_ag",
        datum__gte=datum_von,
        datum__lte=datum_bis,
    ).delete()
    return deleted


# ---------------------------------------------------------------------------
# Z-AG Antrag Views
# ---------------------------------------------------------------------------

@login_required
def zag_antrag(request):
    """Formular fuer Z-AG Antrag mit mehreren Datumsbereichen."""
    if request.method == "POST":
        # Zeilen aus POST sammeln
        von_datums = request.POST.getlist("zag_von_datum")
        bis_datums = request.POST.getlist("zag_bis_datum")

        zag_daten = []
        fehler = []

        for i in range(len(von_datums)):
            von_str = von_datums[i] if i < len(von_datums) else ""
            bis_str = bis_datums[i] if i < len(bis_datums) else ""

            if not von_str and not bis_str:
                # Leere Zeile ueberspringen
                continue

            if not von_str or not bis_str:
                fehler.append(
                    f"Zeile {i + 1}: Bitte beide Datumsfelder ausfullen."
                )
                continue

            try:
                von = date_type.fromisoformat(von_str)
                bis = date_type.fromisoformat(bis_str)
            except ValueError:
                fehler.append(f"Zeile {i + 1}: Ungultiges Datum.")
                continue

            if bis < von:
                fehler.append(
                    f"Zeile {i + 1}: Bis-Datum darf nicht vor Von-Datum liegen."
                )
                continue

            zag_daten.append({"von_datum": von_str, "bis_datum": bis_str})

        if not zag_daten and not fehler:
            fehler.append("Bitte mindestens eine Zeile ausfullen.")

        # Pflichtfelder Vertretung
        vertretung_name = request.POST.get("vertretung_name", "").strip()
        vertretung_telefon = request.POST.get("vertretung_telefon", "").strip()
        if not vertretung_name:
            fehler.append("Bitte die Vertretung (Name) angeben.")
        if not vertretung_telefon:
            fehler.append("Bitte die Telefonnummer der Vertretung angeben.")

        if fehler:
            # Zeilen mit row_id fuer Tage-Zaehler wiederherstellen
            zag_raws = [
                {
                    "von": von_datums[i] if i < len(von_datums) else "",
                    "bis": bis_datums[i] if i < len(bis_datums) else "",
                    "row_id": uuid.uuid4().hex[:8],
                }
                for i in range(max(len(von_datums), len(bis_datums)))
            ]
            fehler_kontext = {
                "fehler": fehler,
                "zag_raws": zag_raws,
                "vertretung_name": vertretung_name,
                "vertretung_telefon": vertretung_telefon,
            }
            if hasattr(request.user, "mitarbeiter"):
                fehler_kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
            return render(request, "formulare/zag_antrag.html", fehler_kontext)

        # Antrag speichern
        mitarbeiter = request.user.mitarbeiter
        antrag = ZAGAntrag.objects.create(
            antragsteller=mitarbeiter,
            zag_daten=zag_daten,
            vertretung_name=request.POST.get("vertretung_name", "").strip(),
            vertretung_telefon=request.POST.get("vertretung_telefon", "").strip(),
        )

        # KEINE Zeiterfassungs-Eintraege beim Antragstellen mehr!
        # Werden erst bei Genehmigung erstellt (siehe genehmigung_entscheiden)

        _auto_signiere_zag(antrag, request)

        # Workflow starten (falls aktives Template vorhanden)
        _starte_workflow_fuer_antrag("zag_antrag_erstellt", antrag, request.user)

        return redirect("formulare:zag_erfolg", pk=antrag.pk)

    # Optionales Vorbefuellen des Von-Datums aus Query-Parameter
    first_von = request.GET.get("von", "")

    kontext = {
        "first_row_id": uuid.uuid4().hex[:8],
        "first_von": first_von,
    }
    if hasattr(request.user, "mitarbeiter"):
        kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
    return render(request, "formulare/zag_antrag.html", kontext)


@login_required
def zag_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen eines Z-AG-Antrags.

    Zeigt Betreffzeile mit Kopierfunktion, Datumsbereich(e) und PDF-Download.
    Zugriff: Antragsteller, Staff, Genehmiger oder Team-Bearbeiter.
    """
    from django.http import HttpResponseForbidden

    antrag = get_object_or_404(ZAGAntrag, pk=pk)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    queue_task = _get_queue_task_aus_request(request, antrag)
    kontext = {
        "antrag": antrag,
        "betreff": antrag.get_betreff(),
        "team_bearbeiter_task": _get_team_bearbeiter_task(antrag),
        "queue_task": queue_task,
        "antrag_signatur": _hole_antrag_signatur("zagantrag", antrag.pk),
    }
    kontext.update(_zag_jahres_kontext(antrag.antragsteller))
    return render(request, "formulare/zag_erfolg.html", kontext)


@login_required
def zag_pdf(request, pk):
    """Gibt den Z-AG-Antrag als PDF-Download zurueck.

    Zugriff: Antragsteller selbst ODER Staff ODER Team-Mitglied mit Claim.
    """
    from weasyprint import HTML

    antrag = get_object_or_404(ZAGAntrag, pk=pk)

    # Berechtigungspruefung
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()

    if not (ist_antragsteller or ist_staff or ist_team or ist_genehmiger):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")

    # Arbeitstage pro Zeitraum berechnen
    mitarbeiter = antrag.antragsteller
    zag_daten_mit_tagen = []
    gesamt_tage = 0
    for zeile in (antrag.zag_daten or []):
        try:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            tage = _zaehle_zag_tage(mitarbeiter, von, bis)
        except (KeyError, ValueError, TypeError):
            von = None
            bis = None
            tage = None
        zag_daten_mit_tagen.append({
            "von_datum": von,
            "bis_datum": bis,
            "tage": tage,
        })
        if tage:
            gesamt_tage += tage

    workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    html_string = render_to_string(
        "formulare/pdf/zag_pdf.html",
        {
            "antrag": antrag,
            "betreff": antrag.get_betreff(),
            "zag_daten_mit_tagen": zag_daten_mit_tagen,
            "gesamt_tage": gesamt_tage,
            "workflow_tasks": workflow_tasks,
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()
    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
    pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner, dateiname)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response


@login_required
def zag_tage_zaehlen(request):
    """HTMX-View - berechnet Arbeitstage fuer einen Z-AG-Zeitraum.

    Beruecksichtigt Wochenenden, standortabhaengige Feiertage und
    freie Wochentage aus individueller Arbeitszeitvereinbarung.
    """
    # HTMX-View - gibt nur Partial zurueck
    von_str = request.GET.get("zag_von_datum", "")
    bis_str = request.GET.get("zag_bis_datum", "")
    tage_anzahl = None

    if von_str and bis_str and hasattr(request.user, "mitarbeiter"):
        try:
            von = date_type.fromisoformat(von_str)
            bis = date_type.fromisoformat(bis_str)
            if bis >= von:
                tage_anzahl = _zaehle_zag_tage(
                    request.user.mitarbeiter, von, bis
                )
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_zag_tage.html",
        {"tage_anzahl": tage_anzahl},
    )


@login_required
def neue_zag_zeile(request):
    """HTMX-View - gibt eine neue leere Z-AG-Zeile als Partial zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer auf '+' klickt.
    """
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_zag_zeile.html",
        {"row_id": row_id},
    )


# ---------------------------------------------------------------------------
# Z-AG Storno Views
# ---------------------------------------------------------------------------

@login_required
def zag_storno_tage_zaehlen(request):
    """HTMX-View - zeigt vorhandene Z-AG-Tage im gewaehlten Zeitraum.

    Berechnet wie viele Zeiterfassungs-Eintraege mit art='z_ag'
    tatsaechlich vorhanden sind und storniert wuerden.
    """
    # HTMX-View - gibt nur Partial zurueck
    von_str = request.GET.get("storno_von_datum", "")
    bis_str = request.GET.get("storno_bis_datum", "")
    tage_anzahl = None

    if von_str and bis_str and hasattr(request.user, "mitarbeiter"):
        try:
            von = date_type.fromisoformat(von_str)
            bis = date_type.fromisoformat(bis_str)
            if bis >= von:
                tage_anzahl = Zeiterfassung.objects.filter(
                    mitarbeiter=request.user.mitarbeiter,
                    art="z_ag",
                    datum__gte=von,
                    datum__lte=bis,
                ).count()
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_zag_storno_tage.html",
        {"tage_anzahl": tage_anzahl},
    )


@login_required
def neue_zag_storno_zeile(request):
    """HTMX-View - gibt eine neue leere Storno-Zeile als Partial zurueck."""
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_zag_storno_zeile.html",
        {"row_id": row_id},
    )


@login_required
def zag_storno(request):
    """Formular fuer Z-AG Stornierung mit mehreren Datumsbereichen."""
    if request.method == "POST":
        von_datums = request.POST.getlist("storno_von_datum")
        bis_datums = request.POST.getlist("storno_bis_datum")

        storno_daten = []
        fehler = []

        for i in range(len(von_datums)):
            von_str = von_datums[i] if i < len(von_datums) else ""
            bis_str = bis_datums[i] if i < len(bis_datums) else ""

            if not von_str and not bis_str:
                continue

            if not von_str or not bis_str:
                fehler.append(
                    f"Zeile {i + 1}: Bitte beide Datumsfelder ausfullen."
                )
                continue

            try:
                von = date_type.fromisoformat(von_str)
                bis = date_type.fromisoformat(bis_str)
            except ValueError:
                fehler.append(f"Zeile {i + 1}: Ungultiges Datum.")
                continue

            if bis < von:
                fehler.append(
                    f"Zeile {i + 1}: Bis-Datum darf nicht vor Von-Datum liegen."
                )
                continue

            storno_daten.append({"von_datum": von_str, "bis_datum": bis_str})

        if not storno_daten and not fehler:
            fehler.append("Bitte mindestens eine Zeile ausfullen.")

        if fehler:
            storno_raws = [
                {
                    "von": von_datums[i] if i < len(von_datums) else "",
                    "bis": bis_datums[i] if i < len(bis_datums) else "",
                    "row_id": uuid.uuid4().hex[:8],
                }
                for i in range(max(len(von_datums), len(bis_datums)))
            ]
            fehler_kontext = {
                "fehler": fehler,
                "storno_raws": storno_raws,
            }
            if hasattr(request.user, "mitarbeiter"):
                fehler_kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
            return render(request, "formulare/zag_storno.html", fehler_kontext)

        # Storno-Antrag speichern
        mitarbeiter = request.user.mitarbeiter
        antrag = ZAGStorno.objects.create(
            antragsteller=mitarbeiter,
            storno_daten=storno_daten,
        )

        # Workflow starten (falls aktives Template vorhanden)
        _starte_workflow_fuer_antrag("zag_storno_erstellt", antrag, request.user)

        return redirect("formulare:zag_storno_erfolg", pk=antrag.pk)

    kontext = {"first_row_id": uuid.uuid4().hex[:8]}
    if hasattr(request.user, "mitarbeiter"):
        mitarbeiter = request.user.mitarbeiter
        kontext.update(_zag_jahres_kontext(mitarbeiter))
        # Zukuenftige Z-AG-Eintraege des laufenden Jahres zur Orientierung
        heute = date_type.today()
        kontext["zag_zukunft"] = (
            Zeiterfassung.objects
            .filter(
                mitarbeiter=mitarbeiter,
                art="z_ag",
                datum__gte=heute,
                datum__year=heute.year,
            )
            .order_by("datum")
        )
    return render(request, "formulare/zag_storno.html", kontext)


@login_required
def zag_storno_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen einer Z-AG Stornierung.

    Zugriff: Antragsteller, Staff, Genehmiger oder Team-Bearbeiter.
    """
    from django.http import HttpResponseForbidden

    antrag = get_object_or_404(ZAGStorno, pk=pk)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    kontext = {
        "antrag": antrag,
        "betreff": antrag.get_betreff(),
        "team_bearbeiter_task": _get_team_bearbeiter_task(antrag),
        "queue_task": _get_queue_task_aus_request(request, antrag),
    }
    kontext.update(_zag_jahres_kontext(antrag.antragsteller))
    return render(request, "formulare/zag_storno_erfolg.html", kontext)


@login_required
def zag_storno_pdf(request, pk):
    """Gibt die Z-AG Stornierung als PDF-Download zurueck."""
    from weasyprint import HTML

    antrag = get_object_or_404(ZAGStorno, pk=pk)

    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    html_string = render_to_string(
        "formulare/pdf/zag_storno_pdf.html",
        {
            "antrag": antrag,
            "betreff": antrag.get_betreff(),
            "workflow_tasks": workflow_tasks,
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()
    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
    pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner, dateiname)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response
