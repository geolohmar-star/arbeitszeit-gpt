from django.urls import path
from . import views

app_name = "workflow"

urlpatterns = [
    # Arbeitsstapel (work queue)
    path("", views.arbeitsstapel, name="arbeitsstapel"),
    path("task/<int:pk>/", views.task_detail, name="task_detail"),
    path("task/<int:pk>/bearbeiten/", views.task_bearbeiten, name="task_bearbeiten"),

    # Workflow-Status
    path("status/<int:instance_id>/", views.workflow_status, name="workflow_status"),

    # Workflow-Editor
    path("editor/", views.workflow_editor, name="workflow_editor"),
    path("editor/save/", views.workflow_editor_save, name="workflow_editor_save"),
    path("editor/load/<int:template_id>/", views.workflow_editor_load, name="workflow_editor_load"),
    path("editor/templates/", views.workflow_editor_templates, name="workflow_editor_templates"),

    # Workflow manuell starten (nur fuer Tests)
    path("start/<int:template_id>/", views.workflow_start_manual, name="workflow_start_manual"),

    # Trigger-Uebersicht (readonly)
    path("trigger/", views.trigger_uebersicht, name="trigger_uebersicht"),

    # Trigger-Konfiguration (GUI)
    path("trigger/konfiguration/", views.trigger_konfiguration, name="trigger_konfiguration"),
    path("trigger/neu/", views.trigger_erstellen, name="trigger_erstellen"),
    path("trigger/<int:pk>/bearbeiten/", views.trigger_bearbeiten, name="trigger_bearbeiten"),
    path("trigger/<int:pk>/loeschen/", views.trigger_loeschen, name="trigger_loeschen"),
    path("trigger/<int:pk>/toggle/", views.trigger_toggle, name="trigger_toggle"),

    # Prozesszentrale
    path("prozesse/", views.prozesszentrale, name="prozesszentrale"),

    # Prozessantraege
    path(
        "prozesse/antrag/",
        views.prozessantrag_stellen,
        name="prozessantrag_stellen",
    ),
    path(
        "prozesse/antrag/<int:pk>/",
        views.prozessantrag_detail,
        name="prozessantrag_detail",
    ),
    path(
        "prozesse/antraege/",
        views.prozessantrag_liste,
        name="prozessantrag_liste",
    ),
    path(
        "prozesse/antrag/neue-zeile/",
        views.prozessantrag_neue_zeile,
        name="prozessantrag_neue_zeile",
    ),
]
