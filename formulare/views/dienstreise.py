# -*- coding: utf-8 -*-
"""Views fuer Dienstreise-Antraege und -Tagebuch."""

import datetime as _dt
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from formulare.forms import DienstreiseantragForm
from formulare.models import Dienstreiseantrag, ReisezeitTagebuchEintrag, Zeitgutschrift

from ._utils import (
    _auto_signiere_dienstreise,
    _hole_antrag_signatur,
    _sammle_workflow_unterzeichner,
    _signiere_pdf_alle_unterzeichner,
    _starte_workflow_fuer_antrag,
)
from .zeitgutschrift import (
    _berechne_tagebuch_gesamt,
    _gutschrift_minuten_fuer_eintrag,
    _minuten_zu_hmin,
    _regelarbeitszeit_fuer_tag,
)

logger = logging.getLogger(__name__)

# Wochentags-Liste fuer Tagebuch-Anzeige
WOCHENTAGE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
]


@login_required
def dienstreise_erstellen(request):
    """Erstelle einen neuen Dienstreiseantrag.

    HTMX-Pattern: Inline-Validierung + Partial-Rendering.
    """
    mitarbeiter = get_object_or_404(
        request.user.mitarbeiter.__class__,
        user=request.user
    )

    if request.method == "POST":
        form = DienstreiseantragForm(request.POST)
        if form.is_valid():
            antrag = form.save(commit=False)
            antrag.antragsteller = mitarbeiter
            antrag.save()

            _auto_signiere_dienstreise(antrag, request)

            # Workflow automatisch starten (via Signal - siehe signals.py)

            # HTMX: Erfolgs-Partial
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "formulare/partials/_dienstreise_erfolg.html",
                    {"antrag": antrag},
                )

            return redirect("formulare:dienstreise_uebersicht")

        # HTMX: Formular mit Fehlern zurueckgeben
        if request.headers.get("HX-Request"):
            return render(
                request,
                "formulare/partials/_dienstreise_formular.html",
                {"form": form},
            )

    else:
        form = DienstreiseantragForm()

    context = {"form": form}

    # HTMX: Nur Formular-Partial
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dienstreise_formular.html",
            context,
        )

    return render(request, "formulare/dienstreise_erstellen.html", context)


@login_required
def dienstreise_bearbeiten(request, pk):
    """Bearbeite einen bestehenden Dienstreiseantrag.

    Nur der Antragsteller kann seinen eigenen Antrag bearbeiten.
    Wird verwendet wenn Antrag zur Ueberarbeitung zurueckgesendet wurde.
    """
    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    # Pruefe Berechtigung: Nur Antragsteller darf bearbeiten
    if request.user != antrag.antragsteller.user:
        messages.error(request, "Sie koennen nur Ihre eigenen Antraege bearbeiten.")
        return redirect("formulare:meine_dienstreisen")

    if request.method == "POST":
        form = DienstreiseantragForm(request.POST, instance=antrag)
        if form.is_valid():
            antrag = form.save()

            messages.success(
                request,
                "Ihre Aenderungen wurden gespeichert. "
                "Bitte kehren Sie zum Workflow-Task zurueck um die Bearbeitung abzuschliessen."
            )

            # Zurueck zur Workflow-Task-Ansicht falls task_id uebergeben
            task_id = request.GET.get("task_id")
            if task_id:
                return redirect("workflow:task_detail", pk=task_id)

            return redirect("formulare:meine_dienstreisen")

        # HTMX: Formular mit Fehlern
        if request.headers.get("HX-Request"):
            return render(
                request,
                "formulare/partials/_dienstreise_formular.html",
                {"form": form, "bearbeiten": True},
            )

    else:
        form = DienstreiseantragForm(instance=antrag)

    context = {
        "form": form,
        "antrag": antrag,
        "bearbeiten": True,
    }

    # HTMX: Nur Formular-Partial
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dienstreise_formular.html",
            context,
        )

    return render(request, "formulare/dienstreise_bearbeiten.html", context)


@login_required
def dienstreise_uebersicht(request):
    """Zeigt alle Dienstreiseantraege des Users."""
    mitarbeiter = get_object_or_404(
        request.user.mitarbeiter.__class__,
        user=request.user
    )

    antraege = Dienstreiseantrag.objects.filter(
        antragsteller=mitarbeiter
    ).select_related("workflow_instance").order_by("-erstellt_am")

    context = {"antraege": antraege}

    # HTMX: Partial
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dienstreise_liste.html",
            context,
        )

    return render(request, "formulare/dienstreise_uebersicht.html", context)


@login_required
def meine_dienstreisen(request):
    """Uebersicht ueber alle Dienstreisen des aktuellen Users.

    Zeigt Status, Workflow-Fortschritt und ermoeglicht Zugriff
    auf detaillierte Workflow-Status-Ansicht.
    """
    # Hole Mitarbeiter des Users
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        # User hat keinen Mitarbeiter -> keine Dienstreisen
        return render(request, "formulare/meine_dienstreisen.html", {
            "antraege": [],
            "anzahl_beantragt": 0,
            "anzahl_genehmigt": 0,
            "anzahl_abgelehnt": 0,
        })

    # Hole alle Dienstreiseantraege des Mitarbeiters
    antraege = Dienstreiseantrag.objects.filter(
        antragsteller=mitarbeiter
    ).select_related(
        "workflow_instance",
        "workflow_instance__template",
        "workflow_instance__aktueller_schritt",
    ).order_by("-erstellt_am")

    # Statistiken
    anzahl_beantragt = antraege.filter(
        status__in=["beantragt", "in_bearbeitung"]
    ).count()
    anzahl_genehmigt = antraege.filter(status="genehmigt").count()
    anzahl_abgelehnt = antraege.filter(status="abgelehnt").count()

    context = {
        "antraege": antraege,
        "anzahl_beantragt": anzahl_beantragt,
        "anzahl_genehmigt": anzahl_genehmigt,
        "anzahl_abgelehnt": anzahl_abgelehnt,
    }

    return render(request, "formulare/meine_dienstreisen.html", context)


@login_required
def dienstreise_detail(request, pk):
    """Detail-Ansicht fuer einen Dienstreiseantrag.

    Zugaenglich fuer: Antragsteller, Vorgesetzte (Workflow-Task),
    Mitglieder des Reisemanagement-Teams mit aktivem Task.
    Zeigt alle Antragsdaten sowie Tagebuch-Eintraege falls vorhanden.
    Ermoeglicht das Erledigen via Team-Stapel (queue_task-Parameter).
    """
    from formulare.models import TeamQueue

    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    ist_antragsteller = antrag.antragsteller.user == request.user

    # Berechtigung via Workflow-Task
    hat_workflow_task = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask as WfTask
        hat_workflow_task = WfTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung"],
            zugewiesen_an_user=request.user,
        ).exists()

        if not hat_workflow_task and hasattr(request.user, "hr_mitarbeiter"):
            stelle = getattr(request.user.hr_mitarbeiter, "stelle", None)
            if stelle:
                hat_workflow_task = WfTask.objects.filter(
                    instance=antrag.workflow_instance,
                    status__in=["offen", "in_bearbeitung"],
                    zugewiesen_an_stelle=stelle,
                ).exists()

        if not hat_workflow_task:
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_workflow_task = WfTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_team__in=user_teams,
            ).exists()

    # Berechtigung via Claim (alter Weg)
    hat_geclaimed = antrag.claimed_von == request.user

    if not (ist_antragsteller or hat_workflow_task or hat_geclaimed):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Optional: aus Team-Stapel geoeffnet
    queue_task = None
    queue_task_pk = request.GET.get("queue_task")
    if queue_task_pk:
        from workflow.models import WorkflowTask as WfTask
        try:
            queue_task = WfTask.objects.select_related("step").get(
                pk=queue_task_pk,
                claimed_von=request.user,
                status="in_bearbeitung",
            )
        except Exception:
            pass

    # Tagebuch-Eintraege und Gutschrift
    tagebuch_eintraege = antrag.tagebuch_eintraege.all().order_by("datum", "von_zeit")
    reisezeit_gutschrift = antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).first()

    return render(
        request,
        "formulare/dienstreise_detail.html",
        {
            "antrag": antrag,
            "ist_antragsteller": ist_antragsteller,
            "queue_task": queue_task,
            "tagebuch_eintraege": tagebuch_eintraege,
            "reisezeit_gutschrift": reisezeit_gutschrift,
            "antrag_signatur": _hole_antrag_signatur("dienstreiseantrag", antrag.pk),
        },
    )


@login_required
def dienstreise_tagebuch_auswahl(request):
    """Auswahl eines genehmigten Dienstreiseantrags fuer das Tagebuch.

    Zeigt Pulldown der genehmigten Dienstreisen des Users.
    Nach Auswahl Weiterleitung zum Tagebuch.
    """
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return redirect("arbeitszeit:dashboard")

    antraege = Dienstreiseantrag.objects.filter(
        antragsteller=mitarbeiter,
        status__in=["genehmigt", "erledigt"],
    ).order_by("-von_datum")

    if request.method == "POST":
        antrag_pk = request.POST.get("dienstreise_pk")
        if antrag_pk:
            return redirect("formulare:dienstreise_tagebuch", pk=antrag_pk)

    return render(
        request,
        "formulare/dienstreise_tagebuch_auswahl.html",
        {"antraege": antraege},
    )


@login_required
def dienstreise_tagebuch(request, pk):
    """Tagebuch-Hauptseite fuer eine Dienstreise.

    Zugaenglich fuer Antragsteller (Lesen + Schreiben) und
    Pruefer mit aktivem Workflow-Task (nur Lesen).
    """
    from formulare.models import TeamQueue

    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    # Berechtigungspruefung
    ist_antragsteller = (
        hasattr(request.user, "mitarbeiter")
        and antrag.antragsteller == request.user.mitarbeiter
    )
    hat_pruefer_zugang = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask as WfTask
        # Offen, in Bearbeitung UND erledigt – damit auch nach Abschluss Zugang besteht
        alle_stati = ["offen", "in_bearbeitung", "erledigt"]
        hat_pruefer_zugang = WfTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=alle_stati,
            zugewiesen_an_user=request.user,
        ).exists()
        if not hat_pruefer_zugang and hasattr(request.user, "hr_mitarbeiter"):
            stelle = getattr(request.user.hr_mitarbeiter, "stelle", None)
            if stelle:
                hat_pruefer_zugang = WfTask.objects.filter(
                    instance=antrag.workflow_instance,
                    status__in=alle_stati,
                    zugewiesen_an_stelle=stelle,
                ).exists()
        if not hat_pruefer_zugang:
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_pruefer_zugang = WfTask.objects.filter(
                instance=antrag.workflow_instance,
                zugewiesen_an_team__in=user_teams,
            ).exists()
    # Auch Claim-Zugang beruecksichtigen
    if not hat_pruefer_zugang:
        hat_pruefer_zugang = antrag.claimed_von == request.user

    # Superuser haben immer Zugang
    if request.user.is_superuser or request.user.is_staff:
        hat_pruefer_zugang = True

    if not (ist_antragsteller or hat_pruefer_zugang):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    mitarbeiter = antrag.antragsteller

    tage = []
    aktuell = antrag.von_datum
    while aktuell <= antrag.bis_datum:
        eintraege = antrag.tagebuch_eintraege.filter(datum=aktuell)
        regel_minuten = _regelarbeitszeit_fuer_tag(mitarbeiter, aktuell)
        eintraege_info = []
        for e in eintraege:
            gutschrift_min = _gutschrift_minuten_fuer_eintrag(e, regel_minuten)
            eintraege_info.append({
                "eintrag": e,
                "gutschrift_min": gutschrift_min,
                "gutschrift_hmin": (
                    _minuten_zu_hmin(gutschrift_min) if e.fall != 1 else "-"
                ),
            })
        tage.append({
            "datum": aktuell,
            "wochentag": WOCHENTAGE[aktuell.weekday()],
            "ist_wochenende": aktuell.weekday() >= 5,
            "regel_minuten": regel_minuten,
            "eintraege": eintraege_info,
        })
        aktuell += _dt.timedelta(days=1)

    gesamt_min = _berechne_tagebuch_gesamt(antrag, mitarbeiter)
    gesamt_hmin = _minuten_zu_hmin(gesamt_min)

    bestehende_gutschrift = antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).first()

    return render(
        request,
        "formulare/dienstreise_tagebuch.html",
        {
            "antrag": antrag,
            "tage": tage,
            "gesamt_min": gesamt_min,
            "gesamt_hmin": gesamt_hmin,
            "bestehende_gutschrift": bestehende_gutschrift,
            "ist_antragsteller": ist_antragsteller,
        },
    )


@login_required
def dienstreise_tagebuch_eintrag_neu(request, pk):
    """Einen oder mehrere Tagebucheintraege fuer einen Tag speichern.

    POST: Alle ausgefuellten Zeilen des Formulars speichern.
    GET:  Weiterleitung zur Tagebuch-Uebersicht.
    """
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return HttpResponse(status=403)

    antrag = get_object_or_404(
        Dienstreiseantrag, pk=pk, antragsteller=mitarbeiter
    )

    datum_str = request.POST.get("datum", "")
    try:
        datum = _dt.date.fromisoformat(datum_str)
    except ValueError:
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    if request.method != "POST":
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    # Alle Zeilen einlesen (mehrere Eintraege pro Submit moeglich)
    falls = request.POST.getlist("fall")
    von_zeiten = request.POST.getlist("von_zeit")
    bis_zeiten = request.POST.getlist("bis_zeit")
    bemerkungen = request.POST.getlist("bemerkung")

    fehler = []
    gespeichert = 0

    for i in range(len(falls)):
        fall_str = falls[i] if i < len(falls) else ""
        von_zeit_str = von_zeiten[i] if i < len(von_zeiten) else ""
        bis_zeit_str = bis_zeiten[i] if i < len(bis_zeiten) else ""
        bemerkung = bemerkungen[i] if i < len(bemerkungen) else ""

        # Leere Zeilen ueberspringen
        if not fall_str and not von_zeit_str and not bis_zeit_str:
            continue

        zeile_nr = i + 1
        if not fall_str or fall_str not in ("1", "2", "3"):
            fehler.append(f"Zeile {zeile_nr}: Bitte einen Fall auswaehlen.")
            continue
        if not von_zeit_str:
            fehler.append(f"Zeile {zeile_nr}: Bitte Von-Zeit angeben.")
            continue
        if not bis_zeit_str:
            fehler.append(f"Zeile {zeile_nr}: Bitte Bis-Zeit angeben.")
            continue

        try:
            von_h, von_m = map(int, von_zeit_str.split(":"))
            bis_h, bis_m = map(int, bis_zeit_str.split(":"))
            von_zeit = _dt.time(von_h, von_m)
            bis_zeit = _dt.time(bis_h, bis_m)
            if bis_zeit <= von_zeit:
                fehler.append(
                    f"Zeile {zeile_nr}: Bis-Zeit muss nach Von-Zeit liegen."
                )
                continue
        except (ValueError, AttributeError):
            fehler.append(f"Zeile {zeile_nr}: Ungueltige Zeitangabe (HH:MM).")
            continue

        ReisezeitTagebuchEintrag.objects.create(
            dienstreise=antrag,
            datum=datum,
            fall=int(fall_str),
            von_zeit=von_zeit,
            bis_zeit=bis_zeit,
            bemerkung=bemerkung,
        )
        gespeichert += 1

    if fehler:
        for f in fehler:
            messages.error(request, f)
    elif gespeichert > 0:
        messages.success(
            request,
            f"{gespeichert} Eintrag{'e' if gespeichert > 1 else ''} gespeichert."
        )

    return redirect(
        reverse("formulare:dienstreise_tagebuch", args=[antrag.pk])
        + f"#tag-{datum.isoformat()}"
    )


@login_required
def dienstreise_tagebuch_eintrag_loeschen(request, eintrag_pk):
    """Tagebucheintrag loeschen."""
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return redirect("arbeitszeit:dashboard")

    eintrag = get_object_or_404(
        ReisezeitTagebuchEintrag,
        pk=eintrag_pk,
        dienstreise__antragsteller=mitarbeiter,
    )
    antrag = eintrag.dienstreise
    datum = eintrag.datum
    if request.method == "POST":
        eintrag.delete()
    return redirect(
        reverse("formulare:dienstreise_tagebuch", args=[antrag.pk])
        + f"#tag-{datum.isoformat()}"
    )


@login_required
def dienstreise_gutschrift_beantragen(request, pk):
    """Gutschrift aus Dienstreise-Tagebuch beantragen.

    Erstellt einen Zeitgutschrift-Antrag aus allen Tagebucheintraegen
    (Fall 2 + Fall 3). Nur per POST erlaubt.
    """
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return redirect("arbeitszeit:dashboard")

    antrag = get_object_or_404(
        Dienstreiseantrag, pk=pk, antragsteller=mitarbeiter
    )

    if request.method != "POST":
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    # Keine doppelten Antraege
    if antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).exists():
        messages.warning(request, "Es wurde bereits ein Gutschrift-Antrag gestellt.")
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    gesamt_min = _berechne_tagebuch_gesamt(antrag, mitarbeiter)

    if gesamt_min == 0:
        messages.error(
            request,
            "Keine Gutschrift berechenbar – bitte Eintraege pruefen.",
        )
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    stunden = abs(gesamt_min) // 60
    minuten = abs(gesamt_min) % 60
    vorzeichen = "+" if gesamt_min >= 0 else "-"

    buchungsmonat = antrag.von_datum.month
    buchungsjahr = antrag.von_datum.year

    von_str = antrag.von_datum.strftime("%d.%m.%Y")
    bis_str = antrag.bis_datum.strftime("%d.%m.%Y")

    zg = Zeitgutschrift.objects.create(
        antragsteller=mitarbeiter,
        art="reisezeit_tagebuch",
        status="beantragt",
        reisezeit_dienstreise=antrag,
        mehrarbeit_buchungsmonat=buchungsmonat,
        mehrarbeit_buchungsjahr=buchungsjahr,
        mehrarbeit_stunden=stunden,
        mehrarbeit_minuten=minuten,
        sonstige_vorzeichen=vorzeichen,
        mehrarbeit_begruendung=(
            f"Reisezeit-Tagebuch fuer Dienstreise nach {antrag.ziel} "
            f"({von_str} - {bis_str})"
        ),
    )

    # Workflow starten
    _starte_workflow_fuer_antrag("zeitgutschrift_erstellt", zg, request.user)

    messages.success(
        request,
        f"Gutschrift-Antrag wurde gestellt ({_minuten_zu_hmin(gesamt_min)}).",
    )
    return redirect("formulare:dienstreise_tagebuch", pk=pk)


@login_required
def dienstreise_pdf(request, pk):
    """PDF-Ausdruck eines Dienstreiseantrags inkl. Tagebuch und Gutschrift."""
    from formulare.models import TeamQueue

    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    ist_antragsteller = (
        hasattr(request.user, "mitarbeiter")
        and antrag.antragsteller == request.user.mitarbeiter
    )
    hat_zugang = ist_antragsteller or antrag.claimed_von == request.user
    if not hat_zugang and antrag.workflow_instance:
        from workflow.models import WorkflowTask as WfTask
        user_teams = TeamQueue.objects.filter(mitglieder=request.user)
        hat_zugang = WfTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung", "erledigt"],
        ).filter(
            zugewiesen_an_user=request.user,
        ).exists() or WfTask.objects.filter(
            instance=antrag.workflow_instance,
            zugewiesen_an_team__in=user_teams,
        ).exists()

    if not hat_zugang:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Tagebuch mit Gutschrift-Berechnung aufbereiten
    mitarbeiter = antrag.antragsteller
    tage = []
    aktuell = antrag.von_datum
    while aktuell <= antrag.bis_datum:
        eintraege = antrag.tagebuch_eintraege.filter(datum=aktuell)
        regel_minuten = _regelarbeitszeit_fuer_tag(mitarbeiter, aktuell)
        eintraege_info = []
        for e in eintraege:
            gutschrift_min = _gutschrift_minuten_fuer_eintrag(e, regel_minuten)
            eintraege_info.append({
                "eintrag": e,
                "gutschrift_min": gutschrift_min,
                "gutschrift_hmin": (
                    _minuten_zu_hmin(gutschrift_min) if e.fall != 1 else "-"
                ),
            })
        tage.append({
            "datum": aktuell,
            "wochentag": WOCHENTAGE[aktuell.weekday()],
            "ist_wochenende": aktuell.weekday() >= 5,
            "regel_minuten": regel_minuten,
            "eintraege": eintraege_info,
        })
        aktuell += _dt.timedelta(days=1)

    gesamt_min = _berechne_tagebuch_gesamt(antrag, mitarbeiter)
    gesamt_hmin = _minuten_zu_hmin(gesamt_min)
    reisezeit_gutschrift = antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).first()

    dr_workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        dr_workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    try:
        from weasyprint import HTML
        import datetime as dt

        html_string = render_to_string(
            "formulare/pdf/dienstreise_pdf.html",
            {
                "antrag": antrag,
                "tage": tage,
                "gesamt_min": gesamt_min,
                "gesamt_hmin": gesamt_hmin,
                "reisezeit_gutschrift": reisezeit_gutschrift,
                "workflow_tasks": dr_workflow_tasks,
                "now": dt.datetime.now(),
            },
        )
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()
        dateiname_dr = f"dienstreise_{antrag.pk}_{antrag.ziel}.pdf"
        unterzeichner_dr = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
        pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner_dr, dateiname_dr)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="{dateiname_dr}"'
        )
        return response
    except ImportError:
        return HttpResponse(
            "WeasyPrint nicht installiert.",
            status=500,
        )
