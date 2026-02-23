import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import WorkflowInstance, WorkflowTask, WorkflowTemplate, WorkflowStep
from .services import WorkflowEngine


@login_required
def arbeitsstapel(request):
    """Arbeitsstapel: Zeigt alle offenen Tasks fuer den aktuellen User.

    Tasks werden angezeigt wenn:
    - direkt an den User zugewiesen (zugewiesen_an_user)
    - an die Stelle des Users zugewiesen und User hat diese Stelle
    """
    user = request.user

    # Tasks die dem User direkt zugewiesen sind
    tasks_direkt = Q(zugewiesen_an_user=user)

    # Tasks die der Stelle des Users zugewiesen sind
    tasks_stelle = Q(zugewiesen_an_user__isnull=True)
    if hasattr(user, "hr_mitarbeiter") and user.hr_mitarbeiter.stelle:
        tasks_stelle &= Q(zugewiesen_an_stelle=user.hr_mitarbeiter.stelle)
    else:
        # User hat keine Stelle → keine Stellen-Tasks
        tasks_stelle = Q(pk__isnull=True)

    # Kombiniere beide Bedingungen
    tasks = (
        WorkflowTask.objects.filter(tasks_direkt | tasks_stelle)
        .filter(status__in=["offen", "in_bearbeitung"])
        .select_related(
            "instance",
            "instance__template",
            "step",
            "zugewiesen_an_stelle",
            "zugewiesen_an_user",
        )
        .order_by("frist", "erstellt_am")
    )

    # Kategorisierung
    ueberfaellig = [t for t in tasks if t.ist_ueberfaellig]
    heute_faellig = [t for t in tasks if t.ist_heute_faellig and not t.ist_ueberfaellig]
    demnaechst = [t for t in tasks if not t.ist_ueberfaellig and not t.ist_heute_faellig]

    context = {
        "tasks": tasks,
        "ueberfaellig": ueberfaellig,
        "heute_faellig": heute_faellig,
        "demnaechst": demnaechst,
        "anzahl_gesamt": tasks.count(),
        "anzahl_ueberfaellig": len(ueberfaellig),
        "anzahl_heute": len(heute_faellig),
    }

    return render(request, "workflow/arbeitsstapel.html", context)


@login_required
def task_detail(request, pk):
    """Detailansicht eines einzelnen Tasks."""
    task = get_object_or_404(
        WorkflowTask.objects.select_related(
            "instance",
            "instance__template",
            "instance__content_type",
            "step",
            "zugewiesen_an_stelle",
            "zugewiesen_an_user",
            "erledigt_von",
        ),
        pk=pk,
    )

    # Pruefe ob User berechtigt ist diesen Task zu sehen
    if not task.kann_bearbeiten(request.user):
        messages.error(request, "Sie sind nicht berechtigt, diesen Task zu bearbeiten.")
        return redirect("workflow:arbeitsstapel")

    # Hole alle Tasks dieser Workflow-Instanz
    workflow_tasks = (
        task.instance.tasks.all()
        .select_related("step", "zugewiesen_an_stelle", "erledigt_von")
        .order_by("step__reihenfolge", "erstellt_am")
    )

    context = {
        "task": task,
        "workflow_tasks": workflow_tasks,
    }

    return render(request, "workflow/task_detail.html", context)


@login_required
def task_bearbeiten(request, pk):
    """Bearbeitet einen Task (Entscheidung treffen).

    POST-Parameter:
    - entscheidung: genehmigt, abgelehnt, zurueckgestellt, weitergeleitet
    - kommentar: optionaler Kommentar
    """
    task = get_object_or_404(WorkflowTask, pk=pk)

    # Pruefe Berechtigung
    if not task.kann_bearbeiten(request.user):
        messages.error(request, "Sie sind nicht berechtigt, diesen Task zu bearbeiten.")
        return redirect("workflow:arbeitsstapel")

    if request.method == "POST":
        entscheidung = request.POST.get("entscheidung")
        kommentar = request.POST.get("kommentar", "")

        # Validiere Entscheidung
        gueltige_entscheidungen = [choice[0] for choice in WorkflowTask.ENTSCHEIDUNG_CHOICES]
        if entscheidung not in gueltige_entscheidungen:
            messages.error(request, "Ungueltige Entscheidung.")
            return redirect("workflow:task_detail", pk=pk)

        # Nutze Workflow-Engine zum Bearbeiten des Tasks
        engine = WorkflowEngine()
        neue_tasks = engine.complete_task(task, entscheidung, kommentar, request.user)

        # Erfolgsmeldung
        if task.instance.status == "abgeschlossen":
            messages.success(
                request,
                f"Workflow '{task.instance.template.name}' erfolgreich abgeschlossen!"
            )
        elif task.instance.status == "abgebrochen":
            messages.warning(
                request,
                f"Workflow '{task.instance.template.name}' wurde abgebrochen."
            )
        elif neue_tasks:
            messages.success(
                request,
                f"Task '{task.step.titel}' erfolgreich bearbeitet. {len(neue_tasks)} neue Task(s) erstellt."
            )
        else:
            messages.success(
                request,
                f"Task '{task.step.titel}' erfolgreich bearbeitet."
            )

        return redirect("workflow:arbeitsstapel")

    # GET → Leite zu Detail-Seite weiter
    return redirect("workflow:task_detail", pk=pk)


@login_required
def workflow_editor(request):
    """Visueller Workflow-Editor mit vis.js.

    Ermoeglicht das grafische Erstellen von Workflow-Templates.
    """
    return render(request, "workflow/workflow_editor.html")


@login_required
def workflow_editor_templates(request):
    """Gibt alle verfuegbaren Workflow-Templates als JSON zurueck."""
    templates = WorkflowTemplate.objects.all().order_by("-erstellt_am")

    data = [
        {
            "id": t.id,
            "name": t.name,
            "kategorie": t.get_kategorie_display(),
            "schritte_anzahl": t.schritte.count(),
            "ist_aktiv": t.ist_aktiv,
        }
        for t in templates
    ]

    return JsonResponse({"templates": data})


@login_required
def workflow_editor_load(request, template_id):
    """Laedt ein bestehendes Workflow-Template in den Editor.

    Gibt Nodes und Edges zurueck die im Editor visualisiert werden koennen.
    """
    template = get_object_or_404(WorkflowTemplate, pk=template_id)

    # Schritte als Nodes
    nodes = []
    for step in template.schritte.all().order_by("reihenfolge"):
        node_id = f"node_{step.id}"
        nodes.append({
            "id": node_id,
            "step_id": step.id,
            "titel": step.titel,
            "beschreibung": step.beschreibung,
            "aktion": step.aktion_typ,
            "rolle": step.zustaendig_rolle,
            "teamId": step.zustaendig_team.id if step.zustaendig_team else None,
            "frist": step.frist_tage,
            "parallel": step.ist_parallel,
            "eskalation": step.eskalation_nach_tagen,
            "reihenfolge": step.reihenfolge,
        })

    # Verbindungen basierend auf Reihenfolge
    edges = []
    schritte_sorted = list(template.schritte.all().order_by("reihenfolge"))
    for i in range(len(schritte_sorted) - 1):
        current = schritte_sorted[i]
        next_step = schritte_sorted[i + 1]
        edges.append({
            "from": f"node_{current.id}",
            "to": f"node_{next_step.id}",
        })

    return JsonResponse({
        "template": {
            "id": template.id,
            "name": template.name,
            "beschreibung": template.beschreibung,
            "kategorie": template.kategorie,
            "trigger_event": template.trigger_event,
        },
        "nodes": nodes,
        "edges": edges,
    })


@require_POST
@login_required
def workflow_editor_save(request):
    """Speichert ein Workflow-Template aus dem Editor.

    POST-Daten (JSON):
    - template: {name, beschreibung, kategorie, trigger_event}
    - schritte: [{titel, beschreibung, aktion, rolle, frist, parallel, eskalation, reihenfolge}, ...]
    """
    try:
        data = json.loads(request.body)
        template_data = data.get("template", {})
        schritte_data = data.get("schritte", [])

        # Validierung
        if not template_data.get("name"):
            return JsonResponse({"error": "Template-Name fehlt"}, status=400)

        if len(schritte_data) == 0:
            return JsonResponse({"error": "Mindestens ein Schritt erforderlich"}, status=400)

        # Template erstellen
        template = WorkflowTemplate.objects.create(
            name=template_data["name"],
            beschreibung=template_data.get("beschreibung", ""),
            kategorie=template_data.get("kategorie", "genehmigung"),
            trigger_event=template_data.get("trigger_event", ""),
            erstellt_von=request.user,
        )

        # Schritte erstellen
        for schritt_data in schritte_data:
            # Team-Queue-Referenz aufloesen
            team_id = schritt_data.get("teamId")
            zustaendig_team = None
            if team_id:
                from formulare.models import TeamQueue
                try:
                    zustaendig_team = TeamQueue.objects.get(id=team_id)
                except TeamQueue.DoesNotExist:
                    return JsonResponse(
                        {"error": f"Team-Queue mit ID {team_id} nicht gefunden"},
                        status=400
                    )

            WorkflowStep.objects.create(
                template=template,
                reihenfolge=schritt_data.get("reihenfolge", 1),
                titel=schritt_data.get("titel", "Unbenannt"),
                beschreibung=schritt_data.get("beschreibung", ""),
                aktion_typ=schritt_data.get("aktion", "genehmigen"),
                zustaendig_rolle=schritt_data.get("rolle", "direkte_fuehrungskraft"),
                zustaendig_team=zustaendig_team,
                frist_tage=schritt_data.get("frist", 3),
                ist_parallel=schritt_data.get("parallel", False),
                eskalation_nach_tagen=schritt_data.get("eskalation", 0),
            )

        return JsonResponse({
            "success": True,
            "template_id": template.id,
            "message": f"Workflow-Template '{template.name}' erfolgreich erstellt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def workflow_status(request, instance_id):
    """Zeigt den Status einer Workflow-Instanz.

    Zeigt eine Timeline mit allen Schritten, aktueller Zustaendigkeit
    und Fortschritt. Kann von Antragstellern und Bearbeitern aufgerufen werden.
    """
    instance = get_object_or_404(
        WorkflowInstance.objects.select_related(
            "template",
            "content_type",
            "gestartet_von",
            "aktueller_schritt",
        ),
        pk=instance_id,
    )

    # Hole alle Tasks dieser Instanz
    workflow_tasks = (
        instance.tasks.all()
        .select_related(
            "step",
            "zugewiesen_an_stelle",
            "zugewiesen_an_stelle__hrmitarbeiter",
            "zugewiesen_an_user",
            "zugewiesen_an_team",
            "erledigt_von",
        )
        .order_by("step__reihenfolge", "erstellt_am")
    )

    # Offene Tasks fuer "Naechste Schritte" Box
    offene_tasks = workflow_tasks.filter(status__in=["offen", "in_bearbeitung"])

    context = {
        "instance": instance,
        "workflow_tasks": workflow_tasks,
        "offene_tasks": offene_tasks,
    }

    return render(request, "workflow/workflow_status.html", context)


@login_required
def workflow_start_manual(request, template_id):
    """Startet einen Workflow manuell (fuer Tests).

    GET-Parameter:
    - object_type: ContentType (z.B. "formulare.zagantrag")
    - object_id: ID des Objekts

    Beispiel:
    /workflow/start/1/?object_type=formulare.zagantrag&object_id=5
    """
    template = get_object_or_404(WorkflowTemplate, pk=template_id)

    # Hole Objekt-Parameter
    object_type_str = request.GET.get("object_type")
    object_id = request.GET.get("object_id")

    if not object_type_str or not object_id:
        messages.error(request, "Parameter object_type und object_id erforderlich!")
        return redirect("workflow:arbeitsstapel")

    # Parse ContentType
    try:
        app_label, model = object_type_str.split(".")
        content_type = ContentType.objects.get(app_label=app_label, model=model)
        model_class = content_type.model_class()
        content_object = model_class.objects.get(pk=object_id)
    except Exception as e:
        messages.error(request, f"Objekt nicht gefunden: {e}")
        return redirect("workflow:arbeitsstapel")

    # Starte Workflow
    engine = WorkflowEngine()
    try:
        instance = engine.start_workflow(template, content_object, request.user)
        messages.success(
            request,
            f"Workflow '{template.name}' erfolgreich gestartet! Instanz-ID: {instance.id}"
        )
    except Exception as e:
        messages.error(request, f"Fehler beim Starten: {e}")

    return redirect("workflow:arbeitsstapel")
