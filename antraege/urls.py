from django.urls import path

from . import views

app_name = "antraege"

urlpatterns = [
    path("", views.pfad_liste, name="pfad_liste"),
    path("meine/", views.meine_antraege, name="meine_antraege"),
    path("editor/neu/", views.pfad_editor, name="pfad_editor_neu"),
    path("editor/<int:pk>/", views.pfad_editor, name="pfad_editor"),
    path("editor/laden/<int:pk>/", views.pfad_editor_laden, name="pfad_editor_laden"),
    path("editor/speichern/", views.pfad_editor_speichern, name="pfad_editor_speichern"),
    path("starten/<int:pk>/", views.pfad_starten, name="pfad_starten"),
    path("sitzung/<int:sitzung_pk>/", views.pfad_schritt, name="pfad_schritt"),
    path("sitzung/<int:sitzung_pk>/abgeschlossen/", views.pfad_abgeschlossen, name="pfad_abgeschlossen"),
]
