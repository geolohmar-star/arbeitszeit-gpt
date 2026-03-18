from django.urls import path

from . import views

app_name = "matrix_integration"

urlpatterns = [
    # Matrix-Raeume
    path("", views.raum_liste, name="raum_liste"),
    path("raum/anlegen/", views.raum_anlegen, name="raum_anlegen"),
    path("raum/<int:pk>/", views.raum_detail, name="raum_detail"),
    path("raum/<int:pk>/bearbeiten/", views.raum_bearbeiten, name="raum_bearbeiten"),
    path("raum/<int:pk>/loeschen/", views.raum_loeschen, name="raum_loeschen"),

    # Teilnehmer-Templates
    path("templates/", views.template_liste, name="template_liste"),
    path("templates/anlegen/", views.template_anlegen, name="template_anlegen"),
    path("templates/<int:pk>/bearbeiten/", views.template_bearbeiten, name="template_bearbeiten"),
    path("templates/<int:pk>/loeschen/", views.template_loeschen, name="template_loeschen"),

    # Sitzungs-Kalender
    path("sitzungen/", views.sitzung_liste, name="sitzung_liste"),
    path("sitzungen/anlegen/", views.sitzung_anlegen, name="sitzung_anlegen"),
    path("sitzungen/<int:pk>/bearbeiten/", views.sitzung_bearbeiten, name="sitzung_bearbeiten"),

    # Synapse API
    path("api/raum-erstellen/", views.synapse_raum_erstellen, name="synapse_raum_erstellen"),

    # Self-Service Passwort-Reset
    path("passwort-reset/", views.matrix_passwort_reset_self, name="passwort_reset_self"),

    # Jitsi-Raeume
    path("jitsi/", views.jitsi_liste, name="jitsi_liste"),
    path("jitsi/anlegen/", views.jitsi_anlegen, name="jitsi_anlegen"),
    path("jitsi/<int:pk>/bearbeiten/", views.jitsi_bearbeiten, name="jitsi_bearbeiten"),
    path("jitsi/<int:pk>/loeschen/", views.jitsi_loeschen, name="jitsi_loeschen"),
]
