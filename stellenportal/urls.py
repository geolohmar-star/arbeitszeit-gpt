from django.urls import path

from . import views

app_name = "stellenportal"

urlpatterns = [
    # Mitarbeiter
    path("", views.liste, name="liste"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/bewerben/", views.bewerben, name="bewerben"),
    path("meine/", views.meine_bewerbungen, name="meine_bewerbungen"),
    path("bewerbung/<int:pk>/zurueckziehen/", views.bewerbung_zurueckziehen, name="bewerbung_zurueckziehen"),

    # HR
    path("hr/", views.hr_dashboard, name="hr_dashboard"),
    path("hr/neu/", views.ausschreibung_erstellen, name="ausschreibung_erstellen"),
    path("hr/<int:pk>/bearbeiten/", views.ausschreibung_bearbeiten, name="ausschreibung_bearbeiten"),
    path("hr/<int:pk>/bewerbungen/", views.bewerbungen_liste, name="bewerbungen_liste"),
    path("hr/bewerbung/<int:pk>/aktion/", views.bewerbung_aktion, name="bewerbung_aktion"),
    path("hr/bewerbung/<int:pk>/status/", views.bewerbung_status_setzen, name="bewerbung_status_setzen"),
]
