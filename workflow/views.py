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

from .models import WorkflowInstance, WorkflowTask, WorkflowTemplate, WorkflowStep, WorkflowTransition
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

    # Erledigte Tasks des Users (letzte 30 Tage)
    from datetime import timedelta
    vor_30_tagen = timezone.now() - timedelta(days=30)

    erledigte_tasks = (
        WorkflowTask.objects.filter(erledigt_von=user, status="erledigt")
        .filter(erledigt_am__gte=vor_30_tagen)
        .select_related(
            "instance",
            "instance__template",
            "step",
            "zugewiesen_an_stelle",
            "zugewiesen_an_user",
        )
        .order_by("-erledigt_am")[:20]  # Max 20 neueste
    )

    context = {
        "tasks": tasks,
        "ueberfaellig": ueberfaellig,
        "heute_faellig": heute_faellig,
        "demnaechst": demnaechst,
        "anzahl_gesamt": tasks.count(),
        "anzahl_ueberfaellig": len(ueberfaellig),
        "anzahl_heute": len(heute_faellig),
        "erledigte_tasks": erledigte_tasks,
        "anzahl_erledigt": erledigte_tasks.count(),
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
    # Erlaubt: Tasks die man bearbeiten kann ODER die man selbst erledigt hat
    kann_ansehen = (
        task.kann_bearbeiten(request.user) or
        (task.status == "erledigt" and task.erledigt_von == request.user)
    )

    if not kann_ansehen:
        messages.error(request, "Sie sind nicht berechtigt, diesen Task anzusehen.")
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
        kuerzel_weiterleiten = request.POST.get("kuerzel_weiterleiten", "").strip()

        # Validiere Entscheidung
        gueltige_entscheidungen = [choice[0] for choice in WorkflowTask.ENTSCHEIDUNG_CHOICES]
        if entscheidung not in gueltige_entscheidungen:
            messages.error(request, "Ungueltige Entscheidung.")
            return redirect("workflow:task_detail", pk=pk)

        # Bei Weiterleiten: Finde Ziel-User anhand Kuerzel
        ziel_user = None
        if entscheidung == "weitergeleitet":
            if not kuerzel_weiterleiten:
                messages.error(request, "Bitte geben Sie ein Kuerzel fuer die Weiterleitung ein.")
                return redirect("workflow:task_detail", pk=pk)

            # Suche User anhand Kuerzel (in hr.Stelle oder arbeitszeit.Mitarbeiter)
            from hr.models import Stelle
            from django.contrib.auth import get_user_model
            User = get_user_model()

            try:
                # Versuche zuerst ueber Stelle zu finden
                stelle = Stelle.objects.get(kuerzel__iexact=kuerzel_weiterleiten)
                if stelle.ist_besetzt:
                    ziel_user = stelle.aktueller_inhaber.user
                else:
                    messages.error(request, f"Stelle '{kuerzel_weiterleiten}' ist nicht besetzt.")
                    return redirect("workflow:task_detail", pk=pk)
            except Stelle.DoesNotExist:
                # Falls keine Stelle gefunden, versuche ueber Username
                try:
                    ziel_user = User.objects.get(username__iexact=kuerzel_weiterleiten)
                except User.DoesNotExist:
                    messages.error(request, f"Kein User mit Kuerzel '{kuerzel_weiterleiten}' gefunden.")
                    return redirect("workflow:task_detail", pk=pk)

        # Nutze Workflow-Engine zum Bearbeiten des Tasks
        engine = WorkflowEngine()
        neue_tasks = engine.complete_task(
            task, entscheidung, kommentar, request.user, ziel_user=ziel_user
        )

        # Erfolgsmeldung
        if task.instance.status == "abgeschlossen":
            messages.success(
                request,
                f"✓ Workflow '{task.instance.template.name}' erfolgreich abgeschlossen!"
            )
        elif task.instance.status == "abgebrochen":
            messages.warning(
                request,
                f"Workflow '{task.instance.template.name}' wurde abgebrochen."
            )
        elif neue_tasks:
            messages.success(
                request,
                f"✓ Task '{task.step.titel}' erfolgreich bearbeitet. {len(neue_tasks)} neue Task(s) erstellt."
            )
        else:
            messages.success(
                request,
                f"✓ Task '{task.step.titel}' erfolgreich bearbeitet."
            )

        # Bleibe auf der Task-Detail-Seite statt zum Arbeitsstapel zu springen
        return redirect("workflow:task_detail", pk=pk)

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

    # Verbindungen
    edges = []
    schritte_sorted = list(template.schritte.all().order_by("reihenfolge"))

    if template.ist_graph_workflow:
        # Graph-Workflow: Lade Transitions
        for transition in template.transitions.all():
            von_id = f"node_{transition.von_schritt.id}"
            zu_id = f"node_{transition.zu_schritt.id}" if transition.zu_schritt else "ende"

            edges.append({
                "from": von_id,
                "to": zu_id,
                "config": {
                    "bedingung_typ": transition.bedingung_typ,
                    "bedingung_entscheidung": transition.bedingung_entscheidung,
                    "bedingung_feld": transition.bedingung_feld,
                    "bedingung_operator": transition.bedingung_operator,
                    "bedingung_wert": transition.bedingung_wert,
                    "bedingung_python_code": transition.bedingung_python_code,
                    "label": transition.label,
                    "prioritaet": transition.prioritaet,
                }
            })

        # Fuege Edge von Antrag-Start zum ersten Schritt hinzu
        if schritte_sorted:
            edges.append({
                "from": "antrag_start",
                "to": f"node_{schritte_sorted[0].id}",
                "config": {"bedingung_typ": "immer"}
            })
    else:
        # Legacy: Verbindungen basierend auf Reihenfolge
        # Edge von Antrag-Start zum ersten Schritt (falls Schritte vorhanden)
        if schritte_sorted:
            first_step = schritte_sorted[0]
            edges.append({
                "from": "antrag_start",
                "to": f"node_{first_step.id}",
            })

        # Edges zwischen den Schritten
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
            "ist_aktiv": template.ist_aktiv,
            "ist_graph_workflow": template.ist_graph_workflow,
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
        edges_data = data.get("edges", [])  # Edges aus Request holen
        ist_graph = data.get("ist_graph_workflow", False)  # NEU: Graph-Flag

        # Validierung
        if not template_data.get("name"):
            return JsonResponse({"error": "Template-Name fehlt"}, status=400)

        if len(schritte_data) == 0:
            return JsonResponse({"error": "Mindestens ein Schritt erforderlich"}, status=400)

        # Pruefe ob Update oder Create
        template_id = template_data.get("template_id")

        if template_id:
            # Update bestehendes Template
            try:
                template = WorkflowTemplate.objects.get(id=template_id)
                template.name = template_data["name"]
                template.beschreibung = template_data.get("beschreibung", "")
                template.kategorie = template_data.get("kategorie", "genehmigung")
                template.trigger_event = template_data.get("trigger_event", "")
                template.ist_aktiv = template_data.get("aktiv", True)
                template.edges_data = edges_data  # Legacy: Edges speichern
                template.ist_graph_workflow = ist_graph  # NEU: Graph-Flag
                template.save()

                # Loesche alte Schritte und Transitions
                template.schritte.all().delete()
                template.transitions.all().delete()

                is_update = True
            except WorkflowTemplate.DoesNotExist:
                return JsonResponse({"error": f"Template mit ID {template_id} nicht gefunden"}, status=404)
        else:
            # Template erstellen
            template = WorkflowTemplate.objects.create(
                name=template_data["name"],
                beschreibung=template_data.get("beschreibung", ""),
                kategorie=template_data.get("kategorie", "genehmigung"),
                trigger_event=template_data.get("trigger_event", ""),
                ist_aktiv=template_data.get("aktiv", True),
                erstellt_von=request.user,
                edges_data=edges_data,  # Legacy: Edges speichern
                ist_graph_workflow=ist_graph,  # NEU: Graph-Flag
            )
            is_update = False

        # Schritte erstellen (mit Mapping node_id -> WorkflowStep)
        schritt_mapping = {}  # node_id -> WorkflowStep
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

            step = WorkflowStep.objects.create(
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
            schritt_mapping[schritt_data["id"]] = step

        # NEU: Transitions erstellen (falls Graph-Workflow)
        if ist_graph and edges_data:
            for edge_data in edges_data:
                von_node_id = edge_data["from"]
                zu_node_id = edge_data["to"]
                config = edge_data.get("config", {})

                # Ueberspringe Antrag-Start Node (kein WorkflowStep)
                if von_node_id == "antrag_start":
                    continue

                von_schritt = schritt_mapping.get(von_node_id)
                zu_schritt = schritt_mapping.get(zu_node_id) if zu_node_id != "antrag_start" else None

                if von_schritt:
                    WorkflowTransition.objects.create(
                        template=template,
                        von_schritt=von_schritt,
                        zu_schritt=zu_schritt,
                        bedingung_typ=config.get("bedingung_typ", "immer"),
                        bedingung_entscheidung=config.get("bedingung_entscheidung", ""),
                        bedingung_feld=config.get("bedingung_feld", ""),
                        bedingung_operator=config.get("bedingung_operator", ""),
                        bedingung_wert=config.get("bedingung_wert", ""),
                        bedingung_python_code=config.get("bedingung_python_code", ""),
                        label=config.get("label", ""),
                        prioritaet=config.get("prioritaet", 1),
                    )

        action = "aktualisiert" if is_update else "erstellt"
        return JsonResponse({
            "success": True,
            "template_id": template.id,
            "message": f"Workflow-Template '{template.name}' erfolgreich {action}"
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


@login_required
def trigger_uebersicht(request):
    """Zeigt Uebersicht ueber alle Workflow-Trigger.

    Zeigt welche Trigger-Events registriert sind und welche
    Workflows automatisch ausgeloest werden.
    """
    # Alle Templates mit Trigger-Event
    templates_mit_trigger = (
        WorkflowTemplate.objects
        .exclude(trigger_event="")
        .order_by("trigger_event", "name")
    )

    # Gruppiere nach Trigger-Event
    trigger_map = {}
    for template in templates_mit_trigger:
        if template.trigger_event not in trigger_map:
            trigger_map[template.trigger_event] = []
        trigger_map[template.trigger_event].append(template)

    # Definierte Events (im Code registriert)
    registrierte_events = [
        {
            "name": "dienstreise_erstellt",
            "beschreibung": "Wird ausgeloest wenn ein Dienstreiseantrag erstellt wird",
            "model": "Dienstreiseantrag",
        },
        {
            "name": "zeitgutschrift_erstellt",
            "beschreibung": "Wird ausgeloest wenn eine Zeitgutschrift erstellt wird",
            "model": "Zeitgutschrift",
        },
        {
            "name": "zag_antrag_erstellt",
            "beschreibung": "Noch nicht implementiert",
            "model": "ZAGAntrag",
        },
        {
            "name": "zag_storno_erstellt",
            "beschreibung": "Noch nicht implementiert",
            "model": "ZAGStorno",
        },
        {
            "name": "aenderung_zeiterfassung_erstellt",
            "beschreibung": "Wird ausgeloest wenn eine Aenderung Zeiterfassung erstellt wird",
            "model": "AenderungZeiterfassung",
        },
    ]

    # Markiere welche Events aktive Workflows haben
    for event in registrierte_events:
        event["workflows"] = trigger_map.get(event["name"], [])
        event["aktiv"] = any(
            w.ist_aktiv for w in event["workflows"]
        )

    context = {
        "registrierte_events": registrierte_events,
        "alle_templates": templates_mit_trigger,
    }

    return render(request, "workflow/trigger_uebersicht.html", context)
