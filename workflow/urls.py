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

    # Trigger-Uebersicht
    path("trigger/", views.trigger_uebersicht, name="trigger_uebersicht"),
]
