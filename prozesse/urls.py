from django.urls import path

from . import views

app_name = "prozesse"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Bausteine
    path("bausteine/", views.baustein_liste, name="baustein_liste"),
    path("bausteine/neu/", views.baustein_erstellen, name="baustein_erstellen"),
    path("bausteine/<int:pk>/", views.baustein_bearbeiten, name="baustein_bearbeiten"),
    path("bausteine/<int:pk>/loeschen/", views.baustein_loeschen, name="baustein_loeschen"),
    path("bausteine/json/", views.baustein_liste_json, name="baustein_liste_json"),
    # Schema-Editor (Prozessverantwortliche)
    path("schema/neu/", views.schema_erstellen, name="schema_erstellen"),
    path("schema/<int:pk>/", views.schema_bearbeiten, name="schema_bearbeiten"),
    path("schema/<int:pk>/loeschen/", views.schema_loeschen, name="schema_loeschen"),
    path("schema/<int:schema_pk>/eintraege/", views.eintrag_liste, name="eintrag_liste"),
    # HTMX-Vorschau
    path("schema/vorschau/", views.schema_vorschau, name="schema_vorschau"),
    # Formular ausfuellen (interne User, Login erforderlich)
    path("formular/<int:pk>/", views.formular_ausfuellen, name="formular_ausfuellen"),
    path("eintrag/<int:pk>/", views.eintrag_detail, name="eintrag_detail"),
    # Externe Formulare (kein Login, Kiosk)
    path("extern/", views.externe_formulare_liste, name="externe_formulare_liste"),
    path("extern/<int:pk>/", views.formular_extern, name="formular_extern"),
]
