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

    # Company Builder
    path("company-builder/", views.company_builder, name="company_builder"),
    path("company-builder/preview/", views.company_builder_preview, name="company_builder_preview"),
    path("company-builder/orgeinheit/neu/", views.company_builder_neue_orgeinheit, name="company_builder_orgeinheit_neu"),
    path("company-builder/stelle/neu/", views.company_builder_neue_stelle, name="company_builder_stelle_neu"),
    path("company-builder/hierarchie/update/", views.company_builder_hierarchie_update, name="company_builder_hierarchie_update"),
    path("company-builder/organigramm/", views.company_builder_organigramm, name="company_builder_organigramm"),
    path("company-builder/snapshot/create/", views.snapshot_create, name="snapshot_create"),
    path("company-builder/snapshot/restore/", views.snapshot_restore, name="snapshot_restore"),
]
