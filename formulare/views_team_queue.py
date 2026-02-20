"""Views fuer Team-Queue-System.

Team-Bearbeitungsstapel fuer genehmigte Antraege.
"""
from datetime import date as date_type, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from arbeitszeit.models import Zeiterfassung
from formulare.models import AenderungZeiterfassung, TeamQueue, ZAGAntrag, ZAGStorno
from formulare.views import _erstelle_zag_eintraege


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

    return render(
        request,
        "formulare/team_queue_uebersicht.html",
        {
            "team": team,
            "queue_antraege": queue_antraege,
            "in_bearbeitung": in_bearbeitung,
            "meine_antraege": meine_antraege,
            "user_teams": user_teams,
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
