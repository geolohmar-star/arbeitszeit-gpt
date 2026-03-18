# -*- coding: utf-8 -*-
"""Views fuer Team-Builder und API-Endpunkte."""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from formulare.models import TeamQueue

logger = logging.getLogger(__name__)


@login_required
def api_team_queues(request):
    """API-Endpunkt: Gibt alle Team-Queues als JSON zurueck.

    Wird vom Workflow-Editor verwendet um Team-Dropdown zu befuellen.
    """
    teams = TeamQueue.objects.all().order_by("name")

    data = {
        "teams": [
            {
                "id": team.id,
                "name": team.name,
            }
            for team in teams
        ]
    }

    return JsonResponse(data)


@login_required
def team_builder(request):
    """Team-Builder: Visuelle Verwaltung von Team-Queues."""
    from django.contrib.auth import get_user_model
    from hr.models import OrgEinheit

    User = get_user_model()

    # OrgEinheit aus Query-Parameter
    org_kuerzel = request.GET.get("org")
    org = None
    if org_kuerzel:
        try:
            org = OrgEinheit.objects.get(kuerzel=org_kuerzel)
        except OrgEinheit.DoesNotExist:
            pass

    teams = TeamQueue.objects.all().prefetch_related("mitglieder").order_by("name")

    from facility.models import FacilityTeam
    facility_teams = FacilityTeam.objects.all().prefetch_related("mitglieder").select_related("teamleiter")

    def _mit_stelle(qs):
        """Reichert User-Queryset mit Stellen-Info an."""
        result = []
        for user in qs:
            stelle_info = ""
            try:
                ma = user.hr_mitarbeiter
                if ma.stelle:
                    stelle_info = f"{ma.stelle.kuerzel} – {ma.stelle.bezeichnung}"
            except Exception:
                pass
            result.append({
                "id": user.id,
                "name": user.get_full_name() or user.username,
                "username": user.username,
                "stelle": stelle_info,
            })
        return result

    # User-Liste: Wenn OrgEinheit angegeben, zuerst deren Mitarbeiter
    org_users = None
    other_users = None
    all_users = None

    if org:
        org_qs = User.objects.filter(
            is_active=True,
            hr_mitarbeiter__stelle__org_einheit=org
        ).distinct().order_by("last_name", "first_name", "username")

        other_qs = User.objects.filter(is_active=True).exclude(
            id__in=org_qs.values_list("id", flat=True)
        ).order_by("last_name", "first_name", "username")

        org_users = _mit_stelle(org_qs)
        other_users = _mit_stelle(other_qs)
    else:
        all_qs = User.objects.filter(is_active=True).order_by(
            "last_name", "first_name", "username"
        )
        all_users = _mit_stelle(all_qs)

    # Alle User als Python-Liste fuer json_script im Template
    if org:
        alle_fuer_json = (org_users or []) + (other_users or [])
    else:
        alle_fuer_json = all_users or []

    context = {
        "teams": teams,
        "facility_teams": facility_teams,
        "all_users": all_users,
        "org_users": org_users,
        "other_users": other_users,
        "org": org,
        "org_kuerzel": org_kuerzel,
        "users_json": alle_fuer_json,
    }

    return render(request, "formulare/team_builder.html", context)


@login_required
def team_builder_detail(request, pk):
    """API: Team-Details laden."""
    team = get_object_or_404(TeamQueue, pk=pk)

    data = {
        "id": team.id,
        "name": team.name,
        "beschreibung": team.beschreibung,
        "antragstypen": team.antragstypen or [],
    }

    return JsonResponse(data)


@login_required
def team_builder_create(request):
    """API: Neues Team erstellen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        beschreibung = data.get("beschreibung", "").strip()
        antragstypen = data.get("antragstypen", [])

        if not name:
            return JsonResponse({"error": "Name erforderlich"}, status=400)

        # Kuerzel aus Name ableiten (lowercase, nur Buchstaben/Zahlen)
        import re
        basis = re.sub(r"[^a-z0-9]", "", name.lower())[:18] or "team"
        kuerzel = basis
        zaehler = 2
        while TeamQueue.objects.filter(kuerzel=kuerzel).exists():
            kuerzel = f"{basis}{zaehler}"
            zaehler += 1

        team = TeamQueue.objects.create(
            name=name,
            beschreibung=beschreibung,
            kuerzel=kuerzel,
            antragstypen=antragstypen,
        )

        return JsonResponse({
            "success": True,
            "id": team.id,
            "message": f"Team '{team.name}' erstellt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def team_builder_update(request, pk):
    """API: Team bearbeiten."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    team = get_object_or_404(TeamQueue, pk=pk)

    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        beschreibung = data.get("beschreibung", "").strip()
        antragstypen = data.get("antragstypen", [])

        if not name:
            return JsonResponse({"error": "Name erforderlich"}, status=400)

        team.name = name
        team.beschreibung = beschreibung
        team.antragstypen = antragstypen
        team.save()

        return JsonResponse({
            "success": True,
            "message": f"Team '{team.name}' aktualisiert"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def team_builder_delete(request, pk):
    """API: Team loeschen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    team = get_object_or_404(TeamQueue, pk=pk)

    # Pruefe ob Team in Workflows verwendet wird
    from workflow.models import WorkflowStep, WorkflowTask

    verwendung_steps = WorkflowStep.objects.filter(zustaendig_team=team).count()
    verwendung_tasks = WorkflowTask.objects.filter(zugewiesen_an_team=team).count()

    if verwendung_steps > 0 or verwendung_tasks > 0:
        return JsonResponse({
            "error": f"Team wird in {verwendung_steps} Workflow-Schritten und {verwendung_tasks} Tasks verwendet"
        }, status=400)

    team_name = team.name
    team.delete()

    return JsonResponse({
        "success": True,
        "message": f"Team '{team_name}' geloescht"
    })


@login_required
def team_builder_add_member(request, pk):
    """API: Mitglied zum Team hinzufuegen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from django.contrib.auth import get_user_model

    User = get_user_model()
    team = get_object_or_404(TeamQueue, pk=pk)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "User-ID erforderlich"}, status=400)

        user = get_object_or_404(User, pk=user_id)

        if team.mitglieder.filter(id=user.id).exists():
            return JsonResponse({"error": "User ist bereits Mitglied"}, status=400)

        team.mitglieder.add(user)

        return JsonResponse({
            "success": True,
            "message": f"{user.username} zu '{team.name}' hinzugefuegt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def team_builder_remove_member(request, pk):
    """API: Mitglied aus Team entfernen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from django.contrib.auth import get_user_model

    User = get_user_model()
    team = get_object_or_404(TeamQueue, pk=pk)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "User-ID erforderlich"}, status=400)

        user = get_object_or_404(User, pk=user_id)
        team.mitglieder.remove(user)

        return JsonResponse({
            "success": True,
            "message": f"{user.username} aus '{team.name}' entfernt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
