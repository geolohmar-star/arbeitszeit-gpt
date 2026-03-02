"""Views fuer Team-Queue-System.

Team-Bearbeitungsstapel fuer genehmigte Antraege.
"""
from datetime import date as date_type, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import logging

from arbeitszeit.models import Zeiterfassung
from formulare.models import AenderungZeiterfassung, TeamQueue, ZAGAntrag, ZAGStorno
from formulare.views import _erstelle_zag_eintraege
from workflow.models import WorkflowTask
from workflow.services import WorkflowEngine

logger = logging.getLogger(__name__)


def _naechsten_task_claimen_und_url(erledigter_task, user):
    """Sucht den naechsten freien Task im selben Team, claimed ihn und gibt die Detail-URL zurueck.

    Gibt None zurueck wenn kein weiterer Task vorhanden.
    """
    from django.urls import reverse

    team = erledigter_task.zugewiesen_an_team
    if not team:
        return None

    naechster = (
        WorkflowTask.objects.filter(
            zugewiesen_an_team=team,
            status="offen",
            claimed_von__isnull=True,
        )
        .order_by("erstellt_am")
        .first()
    )
    if not naechster:
        return None

    # Auto-claimen
    naechster.claimed_von = user
    naechster.claimed_am = timezone.now()
    naechster.status = "in_bearbeitung"
    naechster.save(update_fields=["claimed_von", "claimed_am", "status"])

    # Detail-URL je nach Content-Type
    co = naechster.instance.content_object
    ct = naechster.instance.content_type.model
    if co is None:
        return None

    url_map = {
        "zeitgutschrift": "formulare:zeitgutschrift_detail",
        "zagantrag": "formulare:zag_erfolg",
        "aenderungzeiterfassung": "formulare:aenderung_erfolg",
        "zagstorno": "formulare:zag_storno_erfolg",
        "dienstreiseantrag": "formulare:dienstreise_detail",
    }
    url_name = url_map.get(ct)
    if not url_name:
        return None

    return reverse(url_name, args=[co.pk]) + f"?queue_task={naechster.pk}"


@login_required
def team_queue_uebersicht(request):
    """Zeigt die Team-Queue fuer den eingeloggten User.

    Anzeige:
    - Offene Antraege (genehmigt, ungeclaimed)
    - In Bearbeitung (geclaimed von Teammitgliedern)
    - Meine Antraege (geclaimed vom User selbst)
    """
    # Finde alle Teams in denen der User Mitglied ist
    user_teams = TeamQueue.objects.filter(mitglieder=request.user)

    if not user_teams.exists():
        return render(
            request,
            "formulare/team_queue_uebersicht.html",
            {"kein_team": True},
        )

    # Erstes Team als Standard (spaeter: Team-Auswahl)
    team = user_teams.first()

    # Offene Antraege in Queue
    queue_antraege = team.antraege_in_queue()

    # In Bearbeitung (vom ganzen Team)
    in_bearbeitung = team.antraege_in_bearbeitung()

    # Meine geclaimten Antraege
    meine_antraege = []
    for model in [AenderungZeiterfassung, ZAGAntrag, ZAGStorno]:
        meine_antraege.extend(
            model.objects.filter(
                claimed_von=request.user,
                status="in_bearbeitung",
            ).select_related("antragsteller")
        )
    meine_antraege = sorted(meine_antraege, key=lambda x: x.claimed_am)

    # Mitglieder-IDs des Teams fuer Team-Bearbeitung-Filter
    mitglieder_ids = list(team.mitglieder.values_list("id", flat=True))

    # Offene/claimbare Workflow-Tasks des Teams (noch nicht geclaimed)
    offene_wf_tasks = WorkflowTask.objects.filter(
        zugewiesen_an_team=team,
        status="offen",
        claimed_von__isnull=True,
    ).select_related(
        "instance",
        "instance__template",
        "step",
    ).order_by("frist", "erstellt_am")

    # Meine geclaimten Workflow-Tasks
    meine_wf_tasks = WorkflowTask.objects.filter(
        zugewiesen_an_team=team,
        claimed_von=request.user,
        status="in_bearbeitung",
    ).select_related(
        "instance",
        "instance__template",
        "step",
    ).order_by("claimed_am")

    # Alle Team-Mitglieder in Bearbeitung (nicht eigene)
    team_wf_tasks = WorkflowTask.objects.filter(
        zugewiesen_an_team=team,
        status="in_bearbeitung",
        claimed_von__in=mitglieder_ids,
    ).exclude(
        claimed_von=request.user,
    ).select_related(
        "instance",
        "instance__template",
        "step",
        "claimed_von",
    ).order_by("claimed_am")

    return render(
        request,
        "formulare/team_queue_uebersicht.html",
        {
            "team": team,
            "queue_antraege": queue_antraege,
            "in_bearbeitung": in_bearbeitung,
            "meine_antraege": meine_antraege,
            "user_teams": user_teams,
            # Neue Workflow-Task-Abschnitte
            "offene_wf_tasks": offene_wf_tasks,
            "meine_wf_tasks": meine_wf_tasks,
            "team_wf_tasks": team_wf_tasks,
        },
    )


@login_required
def antrag_detail(request, antrag_typ, pk):
    """Zeigt Details eines geclaimten Antrags.

    Hier kann der Bearbeiter alle Details sehen und den Antrag erledigen
    oder freigeben.
    """
    model_map = {
        "aenderung": AenderungZeiterfassung,
        "zag": ZAGAntrag,
        "zag_storno": ZAGStorno,
    }
    Model = model_map.get(antrag_typ)
    if Model is None:
        messages.error(request, "Ungueltiger Antragstyp.")
        return redirect("formulare:team_queue")

    antrag = get_object_or_404(Model, pk=pk)

    # Pruefe ob User berechtigt (nur eigene geclaimte Antraege ansehen)
    user_teams = TeamQueue.objects.filter(mitglieder=request.user)
    if not user_teams.exists():
        messages.error(request, "Sie sind in keinem Team.")
        return redirect("formulare:team_queue")

    # Entweder: User hat geclaimed ODER Antrag ist noch in Queue (genehmigt)
    if antrag.claimed_von and antrag.claimed_von != request.user:
        messages.error(request, "Dieser Antrag ist von jemand anderem geclaimed.")
        return redirect("formulare:team_queue")

    return render(
        request,
        "formulare/antrag_detail.html",
        {
            "antrag": antrag,
            "antrag_typ": antrag_typ,
        },
    )


@login_required
def antrag_claimen(request, antrag_typ, pk):
    """Claimed einen Antrag aus der Queue.

    # HTMX-View - gibt bei HTMX-Request nur das Partial zurueck.

    Der Antrag wird dem User zugewiesen und Status auf 'in_bearbeitung' gesetzt.
    """
    if request.method != "POST":
        return redirect("formulare:team_queue")

    model_map = {
        "aenderung": AenderungZeiterfassung,
        "zag": ZAGAntrag,
        "zag_storno": ZAGStorno,
    }
    Model = model_map.get(antrag_typ)
    if Model is None:
        return redirect("formulare:team_queue")

    antrag = get_object_or_404(Model, pk=pk)

    # Pruefe ob User in einem Team ist
    user_teams = TeamQueue.objects.filter(mitglieder=request.user)
    if not user_teams.exists():
        messages.error(request, "Sie sind in keinem Team.")
        return redirect("formulare:team_queue")

    # Pruefe ob Antrag noch verfuegbar
    if antrag.status != "genehmigt" or antrag.claimed_von is not None:
        messages.error(request, "Antrag wurde bereits geclaimed.")
        return redirect("formulare:team_queue")

    # Claimen
    antrag.claimed_von = request.user
    antrag.claimed_am = timezone.now()
    antrag.status = "in_bearbeitung"
    antrag.save()

    # Zur Detail-Seite weiterleiten
    messages.success(request, f"Antrag {antrag.get_betreff()} geclaimed.")
    return redirect("formulare:antrag_detail", antrag_typ=antrag_typ, pk=pk)


@login_required
def antrag_freigeben(request, antrag_typ, pk):
    """Gibt einen geclaimten Antrag zurueck in die Queue.

    # HTMX-View - gibt bei HTMX-Request nur das Partial zurueck.
    """
    if request.method != "POST":
        return redirect("formulare:team_queue")

    model_map = {
        "aenderung": AenderungZeiterfassung,
        "zag": ZAGAntrag,
        "zag_storno": ZAGStorno,
    }
    Model = model_map.get(antrag_typ)
    if Model is None:
        return redirect("formulare:team_queue")

    antrag = get_object_or_404(Model, pk=pk)

    # Pruefe ob User berechtigt (nur eigene Antraege freigeben)
    if antrag.claimed_von != request.user:
        messages.error(request, "Sie koennen nur eigene Antraege freigeben.")
        return redirect("formulare:team_queue")

    # Freigeben
    antrag.claimed_von = None
    antrag.claimed_am = None
    antrag.status = "genehmigt"
    antrag.save()

    messages.success(request, f"Antrag {antrag.get_betreff()} freigegeben.")
    return redirect("formulare:team_queue")


@login_required
def antrag_erledigen(request, antrag_typ, pk):
    """Markiert einen Antrag als erledigt.

    # HTMX-View - gibt bei HTMX-Request nur das Partial zurueck.

    Der Antrag wird auf 'erledigt' gesetzt und verschwindet aus der Queue.
    """
    if request.method != "POST":
        return redirect("formulare:team_queue")

    model_map = {
        "aenderung": AenderungZeiterfassung,
        "zag": ZAGAntrag,
        "zag_storno": ZAGStorno,
    }
    Model = model_map.get(antrag_typ)
    if Model is None:
        return redirect("formulare:team_queue")

    antrag = get_object_or_404(Model, pk=pk)

    # Pruefe ob User berechtigt (nur eigene Antraege erledigen)
    if antrag.claimed_von != request.user:
        messages.error(request, "Sie koennen nur eigene Antraege erledigen.")
        return redirect("formulare:team_queue")

    # Erledigen
    antrag.status = "erledigt"
    antrag.erledigt_am = timezone.now()
    antrag.save()

    # Automatische Buchung/Aktualisierung bei Z-AG
    if antrag_typ == "zag":
        # Z-AG erledigt → Zeiterfassungs-Eintraege erstellen/aktualisieren
        # (Falls schon bei Genehmigung erstellt: update_or_create aktualisiert nur)
        gesamt_tage = 0
        for zeile in antrag.zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            bemerkung = f"Z-AG gebucht durch {request.user.get_full_name() or request.user.username} (Team)"
            gesamt_tage += _erstelle_zag_eintraege(
                antrag.antragsteller, von, bis, bemerkung
            )
        messages.success(
            request,
            f"Antrag erledigt und {gesamt_tage} Zeiterfassungs-Eintraege gebucht."
        )

    elif antrag_typ == "zag_storno":
        # Z-AG Storno erledigt → Zeiterfassungs-Eintraege loeschen
        gesamt_geloescht = 0
        for zeile in antrag.storno_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            aktuell = von
            while aktuell <= bis:
                deleted_count, _ = Zeiterfassung.objects.filter(
                    mitarbeiter=antrag.antragsteller,
                    datum=aktuell,
                    art="z_ag",
                ).delete()
                gesamt_geloescht += deleted_count
                aktuell += timedelta(days=1)
        messages.success(
            request,
            f"Antrag erledigt und {gesamt_geloescht} Zeiterfassungs-Eintraege storniert."
        )

    return redirect("formulare:team_queue")


@login_required
def workflow_task_claimen(request, pk):
    """Claimed einen Workflow-Task aus dem Team-Pool.

    Setzt claimed_von, claimed_am und status=in_bearbeitung.
    Nur aufrufbar wenn Task offen und noch nicht geclaimed.
    """
    if request.method != "POST":
        return redirect("formulare:team_queue")

    task = get_object_or_404(WorkflowTask, pk=pk)

    # Pruefe ob User im zugewiesenen Team ist
    if not task.zugewiesen_an_team:
        messages.error(request, "Dieser Task hat keine Team-Zuweisung.")
        return redirect("formulare:team_queue")

    if not task.zugewiesen_an_team.mitglieder.filter(id=request.user.id).exists():
        messages.error(request, "Sie sind kein Mitglied des zugewiesenen Teams.")
        return redirect("formulare:team_queue")

    # Pruefe ob Task noch claimbar
    if task.status != "offen" or task.claimed_von is not None:
        messages.error(request, "Dieser Task ist bereits geclaimed oder nicht mehr offen.")
        return redirect("formulare:team_queue")

    # Claimen
    task.claimed_von = request.user
    task.claimed_am = timezone.now()
    task.status = "in_bearbeitung"
    task.save(update_fields=["claimed_von", "claimed_am", "status"])

    messages.success(request, f"Task '{task.step.titel}' wurde geclaimed.")
    return redirect("formulare:team_queue")


@login_required
def workflow_task_freigeben(request, pk):
    """Gibt einen geclaimten Workflow-Task zurueck in den Pool.

    Setzt claimed_von und claimed_am zurueck, status wieder auf offen.
    """
    if request.method != "POST":
        return redirect("formulare:team_queue")

    task = get_object_or_404(WorkflowTask, pk=pk)

    # Pruefe ob User diesen Task geclaimed hat
    if task.claimed_von != request.user:
        messages.error(request, "Sie koennen nur eigene Tasks freigeben.")
        return redirect("formulare:team_queue")

    # Freigeben
    task.claimed_von = None
    task.claimed_am = None
    task.status = "offen"
    task.save(update_fields=["claimed_von", "claimed_am", "status"])

    messages.success(request, f"Task '{task.step.titel}' wurde freigegeben.")
    return redirect("formulare:team_queue")


@login_required
def workflow_task_erledigen(request, pk):
    """Erledigt einen geclaimten Workflow-Task.

    Fuehrt antragstyp-spezifische Business-Logik aus (ZAG buchen, Storno loeschen)
    und schliesst den Task via WorkflowEngine ab.
    """
    if request.method != "POST":
        return redirect("formulare:team_queue")

    task = get_object_or_404(WorkflowTask, pk=pk)

    # Pruefe ob User diesen Task geclaimed hat
    if task.claimed_von != request.user:
        messages.error(request, "Sie koennen nur eigene Tasks erledigen.")
        return redirect("formulare:team_queue")

    # Business-Logik je nach Antragstyp
    content_object = task.instance.content_object

    if isinstance(content_object, ZAGAntrag) and content_object.zag_daten:
        # Z-AG: Zeiterfassungs-Eintraege erstellen
        gesamt_tage = 0
        benutzer_name = request.user.get_full_name() or request.user.username
        for zeile in content_object.zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            bemerkung = f"Z-AG gebucht durch {benutzer_name} (Workflow)"
            gesamt_tage += _erstelle_zag_eintraege(
                content_object.antragsteller, von, bis, bemerkung
            )
        messages.success(
            request,
            f"Task erledigt – {gesamt_tage} Zeiterfassungs-Eintraege gebucht."
        )

    elif isinstance(content_object, ZAGStorno) and content_object.storno_daten:
        # Z-AG Storno: Zeiterfassungs-Eintraege loeschen
        gesamt_geloescht = 0
        for zeile in content_object.storno_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            aktuell = von
            while aktuell <= bis:
                deleted_count, _ = Zeiterfassung.objects.filter(
                    mitarbeiter=content_object.antragsteller,
                    datum=aktuell,
                    art="z_ag",
                ).delete()
                gesamt_geloescht += deleted_count
                aktuell += timedelta(days=1)
        messages.success(
            request,
            f"Task erledigt – {gesamt_geloescht} Zeiterfassungs-Eintraege storniert."
        )

    else:
        # Kein spezieller Business-Code noetig
        messages.success(request, f"Task '{task.step.titel}' erledigt.")

    # Workflow-Engine: Task abschliessen und naechsten Schritt aktivieren
    try:
        WorkflowEngine().complete_task(
            task=task,
            entscheidung="genehmigt",
            kommentar="",
            user=request.user,
        )
    except Exception as exc:
        logger.error("Fehler beim Abschliessen des WorkflowTasks %s: %s", task.pk, exc)
        messages.error(request, "Workflow-Fehler beim Abschliessen des Tasks.")

    # Naechsten Task im selben Team auto-claimen und dorthin weiterleiten
    next_url = _naechsten_task_claimen_und_url(task, request.user)
    if next_url:
        return redirect(next_url)
    return redirect("formulare:team_queue")
