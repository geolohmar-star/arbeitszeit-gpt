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
    path("<int:pk>/weiterleiten/", views.stoermeldung_weiterleiten, name="weiterleiten"),
    path("al-queue/", views.al_queue, name="al_queue"),
    path("<int:pk>/al-antwort/", views.al_antwort, name="al_antwort"),
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
    # Wartungsplaene
    path("wartung/", views.wartungsplan_liste, name="wartungsplan_liste"),
    path("wartung/neu/", views.wartungsplan_erstellen, name="wartungsplan_erstellen"),
    path("wartung/<int:pk>/bearbeiten/", views.wartungsplan_bearbeiten, name="wartungsplan_bearbeiten"),
    path("wartung/<int:pk>/loeschen/", views.wartungsplan_loeschen, name="wartungsplan_loeschen"),
    path("mein-team/", views.vorgesetzter_stoermeldungen, name="vorgesetzter"),
    path("monatsreport/", views.al_monatsreport, name="monatsreport"),
    path("einstellungen/", views.facility_einstellungen, name="einstellungen"),
    # Team-Builder Member-Management
    path("teams/<int:pk>/mitglied/hinzufuegen/", views.facility_team_mitglied_hinzufuegen, name="team_mitglied_hinzufuegen"),
    path("teams/<int:pk>/mitglied/entfernen/", views.facility_team_mitglied_entfernen, name="team_mitglied_entfernen"),
]
