from django.urls import path

from . import views

app_name = "sicherheit"

urlpatterns = [
    # AMOK + Stiller Alarm
    path("ausloesen/", views.alarm_ausloesen, name="alarm_ausloesen"),
    path("status.json", views.sicherheit_status_json, name="status_json"),
    path("security-alarm-status.json", views.security_alarm_status_json, name="security_alarm_status_json"),
    path("", views.sicherheit_dashboard, name="sicherheit_dashboard"),
    path("alarme/", views.alarm_liste, name="alarm_liste"),
    path("<int:pk>/", views.alarm_detail, name="alarm_detail"),
    path("<int:pk>/bestaetigung/", views.amok_bestaetigung_view, name="amok_bestaetigung"),
    path("<int:pk>/schliessen/", views.alarm_schliessen, name="alarm_schliessen"),

    # Arbeitsschutz-Verwaltung
    path("arbeitsschutz/", views.arbeitsschutz_dashboard, name="arbeitsschutz_dashboard"),
    path("arbeitsschutz/<int:pk>/rolle/", views.arbeitsschutz_rolle_toggle, name="arbeitsschutz_rolle_toggle"),
    path("arbeitsschutz/matrix-einladen/", views.arbeitsschutz_matrix_einladen, name="arbeitsschutz_matrix_einladen"),

    # Brandalarm
    path("brand/melden/", views.brand_melden, name="brand_melden"),
    path("brand/status.json", views.brand_status_json, name="brand_status_json"),
    path("brand/erkunder-status.json", views.brand_erkunder_status_json, name="brand_erkunder_status_json"),
    path("brand/erkunden/<str:token>/", views.brand_erkunden_token, name="brand_erkunden_token"),
    path("brand/", views.brand_liste, name="brand_liste"),
    path("brand/<int:pk>/", views.brand_detail, name="brand_detail"),
    path("brand/<int:pk>/gemeldet/", views.brand_gemeldet_view, name="brand_gemeldet"),
    path("brand/<int:pk>/security/", views.brand_security_bestaetigen, name="brand_security"),
    path("brand/<int:pk>/schliessen/", views.brand_schliessen, name="brand_schliessen"),
    path("brand/<int:pk>/nachbewertung/", views.brand_nachbewertung, name="brand_nachbewertung"),
    path("brand/<int:pk>/einsatz/", views.brand_einsatz, name="brand_einsatz"),
    path("brand/<int:pk>/einsatz.json", views.brand_einsatz_json, name="brand_einsatz_json"),
]
