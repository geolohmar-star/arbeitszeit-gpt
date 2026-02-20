from django.urls import path
from . import views

app_name = "hr"

urlpatterns = [
    # Mitarbeiter-Listen und Details
    path("", views.mitarbeiter_liste, name="liste"),
    path("organigramm/", views.organigramm, name="organigramm"),
    path("<int:pk>/", views.mitarbeiter_detail, name="detail"),

    # Stellen-Management
    path("stellen/", views.stellen_uebersicht, name="stellen_uebersicht"),
    path("stellen/neu/", views.stelle_bearbeiten, name="stelle_neu"),
    path("stellen/<int:pk>/bearbeiten/", views.stelle_bearbeiten, name="stelle_bearbeiten"),
    path("stellen/organigramm/", views.stellen_organigramm, name="stellen_organigramm"),
    path("stellen/delegation/", views.delegation_verwalten, name="delegation_verwalten"),

    # Mitarbeiter-Stellen-Zuweisung
    path("mitarbeiter/<int:pk>/stelle-zuweisen/", views.mitarbeiter_stelle_zuweisen, name="mitarbeiter_stelle_zuweisen"),
]
