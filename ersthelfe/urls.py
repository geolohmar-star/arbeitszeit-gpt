from django.urls import path

from . import views

app_name = "ersthelfe"

urlpatterns = [
    path("", views.vorfall_liste, name="vorfall_liste"),
    path("arbeitsschutz/", views.arbeitsschutz_uebersicht, name="arbeitsschutz_uebersicht"),
    path("ausloesen/", views.vorfall_ausloesen, name="vorfall_ausloesen"),
    path("<int:pk>/", views.vorfall_detail, name="vorfall_detail"),
    path("<int:pk>/schliessen/", views.vorfall_schliessen, name="vorfall_schliessen"),
    path("<int:pk>/protokoll/", views.protokoll_bearbeiten, name="protokoll_bearbeiten"),
    path("<int:pk>/protokoll/pdf/", views.protokoll_pdf, name="protokoll_pdf"),
    path("rueckmeldung/<str:token>/", views.rueckmeldung, name="rueckmeldung"),
    path("status.json", views.eh_status_json, name="status_json"),
    path("tetra/", views.tetra_info, name="tetra_info"),
]
