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
    path("editor/schema-felder/<int:schema_pk>/", views.schema_felder_laden, name="schema_felder_laden"),
    path("loeschen/<int:pk>/", views.pfad_loeschen, name="pfad_loeschen"),
    path("blockansicht/<int:pk>/", views.pfad_blockansicht, name="pfad_blockansicht"),
    path("starten/<int:pk>/", views.pfad_starten, name="pfad_starten"),
    path("sitzung/<int:pk>/loeschen/", views.sitzung_loeschen, name="sitzung_loeschen"),
    path("sitzung/<int:pk>/pdf/", views.sitzung_pdf, name="sitzung_pdf"),
    path("sitzung/<int:sitzung_pk>/", views.pfad_schritt, name="pfad_schritt"),
    path("sitzung/<int:sitzung_pk>/abgeschlossen/", views.pfad_abgeschlossen, name="pfad_abgeschlossen"),
]
