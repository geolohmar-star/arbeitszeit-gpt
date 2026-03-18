# -*- coding: utf-8 -*-
"""Dashboard- und Genehmigungs-Views fuer die Formulare-App."""

import logging
from itertools import chain
from operator import attrgetter

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from formulare.models import (
    AenderungZeiterfassung,
    TeamQueue,
    ZAGAntrag,
    ZAGStorno,
    Zeitgutschrift,
)

from ._utils import (
    _annotiere_workflow_status,
    _auto_signiere_genehmigung,
    _get_queue_task_aus_request,
    _get_team_bearbeiter_task,
    _ist_team_mitglied_fuer_antrag,
    _loeschgrenze_berechnen,
    _offene_antraege_fuer_user,
)
from .zag import _erstelle_zag_eintraege

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """Dashboard fuer die Formulare-App.

    Zeigt eine Uebersicht aller verfuegbaren Antragsformulare.
    """
    from workflow.models import WorkflowTask

    # Anzahl offener Workflow-Tasks im Team des eingeloggten Users
    team_stapel_anzahl = 0
    user_teams = TeamQueue.objects.filter(mitglieder=request.user)
    if user_teams.exists():
        team_stapel_anzahl = WorkflowTask.objects.filter(
            zugewiesen_an_team__in=user_teams,
            status="offen",
            claimed_von__isnull=True,
        ).count()

    context = {"team_stapel_anzahl": team_stapel_anzahl}

    # HTMX-Request: nur Partial zurueckgeben
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dashboard.html",
            context,
        )

    return render(request, "formulare/dashboard.html", context)


@login_required
def meine_antraege(request):
    """Liste aller eigenen Antraege, neueste zuerst, mit Paginierung.

    Loescht automatisch Eintraege die aelter als 2 Jahre minus 1 Tag sind.
    Zeigt sowohl AenderungZeiterfassung- als auch ZAGAntrag-Eintraege.
    """
    # Automatische Loeschung abgelaufener Eintraege (alle Nutzer, datenschutzkonform)
    loeschgrenze = _loeschgrenze_berechnen()
    AenderungZeiterfassung.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    ZAGAntrag.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    ZAGStorno.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    Zeitgutschrift.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()

    # Alle Antragstypen zusammenfuehren und nach Datum sortieren
    aenderungen = list(
        AenderungZeiterfassung.objects.filter(
            antragsteller__user=request.user
        )
    )
    for a in aenderungen:
        a.antrag_typ = "aenderung"

    zag_antraege = list(
        ZAGAntrag.objects.filter(
            antragsteller__user=request.user
        )
    )
    for z in zag_antraege:
        z.antrag_typ = "zag"

    zag_stornos = list(
        ZAGStorno.objects.filter(
            antragsteller__user=request.user
        )
    )
    for s in zag_stornos:
        s.antrag_typ = "zag_storno"

    zeitgutschriften = list(
        Zeitgutschrift.objects.filter(
            antragsteller__user=request.user
        )
    )
    for z in zeitgutschriften:
        z.antrag_typ = "zeitgutschrift"

    alle_antraege = sorted(
        chain(aenderungen, zag_antraege, zag_stornos, zeitgutschriften),
        key=attrgetter("erstellt_am"),
        reverse=True,
    )

    # WorkflowInstances fuer alle Antraege laden und anheften
    _annotiere_workflow_status(alle_antraege)

    paginator = Paginator(alle_antraege, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "formulare/meine_antraege.html",
        {
            "page_obj": page_obj,
            "loeschgrenze": loeschgrenze,
        },
    )


@login_required
def genehmigung_uebersicht(request):
    """Weitergeleitet an den neuen Workflow-Arbeitsstapel.

    Die alte Genehmigungsansicht ist abgeschaltet. Alle Genehmigungen
    laufen jetzt ueber /workflow/.
    """
    return redirect("workflow:arbeitsstapel")


@login_required
def _genehmigung_uebersicht_alt(request):
    """VERALTET – wird nicht mehr aufgerufen. Nur zur Referenz.

    Ehemals: Uebersicht aller offenen Antraege fuer den eingeloggten Genehmiger.
    """
    berechtigte_ma = _offene_antraege_fuer_user(request.user)

    if not berechtigte_ma.exists():
        return render(
            request,
            "formulare/genehmigung_uebersicht.html",
            {"kein_zugang": True},
        )

    aenderungen = (
        AenderungZeiterfassung.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )
    zag_antraege = (
        ZAGAntrag.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )
    zag_stornos = (
        ZAGStorno.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )
    zeitgutschriften = (
        Zeitgutschrift.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )

    # Zuletzt erledigte Antraege fuer Historie
    aenderungen_erledigt = (
        AenderungZeiterfassung.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )
    zag_erledigt = (
        ZAGAntrag.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )
    zag_storno_erledigt = (
        ZAGStorno.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )
    zeitgutschriften_erledigt = (
        Zeitgutschrift.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )

    gesamt_offen = (
        aenderungen.count() + zag_antraege.count() +
        zag_stornos.count() + zeitgutschriften.count()
    )

    return render(
        request,
        "formulare/genehmigung_uebersicht.html",
        {
            "aenderungen": aenderungen,
            "zag_antraege": zag_antraege,
            "zag_stornos": zag_stornos,
            "zeitgutschriften": zeitgutschriften,
            "aenderungen_erledigt": aenderungen_erledigt,
            "zag_erledigt": zag_erledigt,
            "zag_storno_erledigt": zag_storno_erledigt,
            "zeitgutschriften_erledigt": zeitgutschriften_erledigt,
            "gesamt_offen": gesamt_offen,
            "kein_zugang": False,
        },
    )


@login_required
def genehmigung_entscheiden(request, antrag_typ, pk):
    """Genehmigt oder lehnt einen einzelnen Antrag ab.

    # HTMX-View - gibt bei HTMX-Request nur das erledigte Zeilen-Partial zurueck.

    antrag_typ: 'aenderung' | 'zag' | 'zag_storno' | 'zeitgutschrift'
    """
    from datetime import date as date_type, timedelta
    from django.utils import timezone

    if request.method != "POST":
        return redirect("formulare:genehmigung_uebersicht")

    model_map = {
        "aenderung": AenderungZeiterfassung,
        "zag": ZAGAntrag,
        "zag_storno": ZAGStorno,
        "zeitgutschrift": Zeitgutschrift,
    }
    Model = model_map.get(antrag_typ)
    if Model is None:
        return redirect("formulare:genehmigung_uebersicht")

    antrag = get_object_or_404(Model, pk=pk)

    # Berechtigungspruefung: stellenbasiert mit guardian-Fallback
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    if antrag.antragsteller not in berechtigte_ma:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<span class="badge bg-danger">Keine Berechtigung</span>',
                status=403,
            )
        return redirect("formulare:genehmigung_uebersicht")

    neue_status = request.POST.get("status")
    if neue_status not in ("genehmigt", "abgelehnt"):
        return redirect("formulare:genehmigung_uebersicht")

    antrag.status = neue_status
    antrag.bearbeitet_von = request.user
    antrag.bearbeitet_am = timezone.now()
    antrag.bemerkung_bearbeiter = request.POST.get("bemerkung", "").strip()
    antrag.save()

    # Genehmiger signiert den Antrag digital
    _auto_signiere_genehmigung(antrag, antrag_typ, request)

    # Automatische Buchung bei Z-AG Antraegen
    if antrag_typ == "zag" and neue_status == "genehmigt":
        # Z-AG genehmigt -> Zeiterfassungs-Eintraege erstellen
        from arbeitszeit.models import Zeiterfassung
        gesamt_tage = 0
        for zeile in antrag.zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            bemerkung = f"Z-AG genehmigt von {request.user.get_full_name() or request.user.username}"
            gesamt_tage += _erstelle_zag_eintraege(
                antrag.antragsteller, von, bis, bemerkung
            )

    elif antrag_typ == "zag" and neue_status == "abgelehnt":
        # Z-AG abgelehnt -> Zeiterfassungs-Eintraege loeschen (falls vorhanden)
        from arbeitszeit.models import Zeiterfassung
        for zeile in antrag.zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            aktuell = von
            while aktuell <= bis:
                Zeiterfassung.objects.filter(
                    mitarbeiter=antrag.antragsteller,
                    datum=aktuell,
                    art="z_ag",
                ).delete()
                aktuell += timedelta(days=1)

    elif antrag_typ == "zag_storno" and neue_status == "genehmigt":
        # Z-AG Storno genehmigt -> Zeiterfassungs-Eintraege loeschen
        from arbeitszeit.models import Zeiterfassung
        for zeile in antrag.storno_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            aktuell = von
            while aktuell <= bis:
                Zeiterfassung.objects.filter(
                    mitarbeiter=antrag.antragsteller,
                    datum=aktuell,
                    art="z_ag",
                ).delete()
                aktuell += timedelta(days=1)

    # HTMX: Zeile durch erledigtes Partial ersetzen
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_genehmigung_zeile_erledigt.html",
            {
                "antrag": antrag,
                "antrag_typ": antrag_typ,
            },
        )

    return redirect("formulare:genehmigung_uebersicht")
