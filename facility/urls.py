from django.urls import path

from . import views

app_name = "facility"

urlpatterns = [
    # Melder-Seite
    path("", views.stoermeldung_erstellen, name="erstellen"),
    path("<int:pk>/", views.stoermeldung_detail, name="detail"),
    path("<int:pk>/erfolg/", views.stoermeldung_erfolg, name="erfolg"),
    path("meine/", views.meine_stoermeldungen, name="meine"),
    # Team-Queue
    path("queue/", views.facility_queue, name="queue"),
    path("<int:pk>/claimen/", views.stoermeldung_claimen, name="claimen"),
    path("<int:pk>/freigeben/", views.stoermeldung_freigeben, name="freigeben"),
    path("<int:pk>/erledigen/", views.stoermeldung_erledigen, name="erledigen"),
    path("<int:pk>/unloesbar/", views.stoermeldung_unloesbar, name="unloesbar"),
    # HTMX-Partial
    path("textbausteine/laden/", views.textbausteine_laden, name="textbausteine_laden"),
    # Textbaustein-Verwaltung
    path("textbausteine/", views.textbaustein_liste, name="textbaustein_liste"),
    path("textbausteine/neu/", views.textbaustein_erstellen, name="textbaustein_erstellen"),
    path(
        "textbausteine/<int:pk>/bearbeiten/",
        views.textbaustein_bearbeiten,
        name="textbaustein_bearbeiten",
    ),
    path(
        "textbausteine/<int:pk>/loeschen/",
        views.textbaustein_loeschen,
        name="textbaustein_loeschen",
    ),
    path("workflow-einrichten/", views.facility_workflow_anleitung, name="workflow_anleitung"),
]
