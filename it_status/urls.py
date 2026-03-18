from django.urls import path

from . import views

app_name = "it_status"

urlpatterns = [
    # Oeffentlich (eingeloggt)
    path("", views.uebersicht, name="uebersicht"),
    path("<int:pk>/", views.system_detail, name="system_detail"),

    # Helpdesk-Pflege: Systeme
    path("system/neu/", views.system_neu, name="system_neu"),
    path("<int:pk>/bearbeiten/", views.system_bearbeiten, name="system_bearbeiten"),
    path("<int:pk>/loeschen/", views.system_loeschen, name="system_loeschen"),

    # Helpdesk-Pflege: Meldungen & Wartungen
    path("meldung/neu/", views.meldung_neu, name="meldung_neu"),
    path("meldung/<int:pk>/schliessen/", views.meldung_schliessen, name="meldung_schliessen"),
    path("wartung/neu/", views.wartung_neu, name="wartung_neu"),
    path("wartung/<int:pk>/loeschen/", views.wartung_loeschen, name="wartung_loeschen"),
    path("<int:pk>/status/", views.system_status_aendern, name="system_status_aendern"),
]
