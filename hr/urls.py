from django.urls import path
from . import views

app_name = "hr"

urlpatterns = [
    # Mitarbeiter-Listen und Details
    path("", views.mitarbeiter_liste, name="liste"),
    path("organigramm/", views.organigramm, name="organigramm"),
    path("organigramm/karten/", views.organigramm_karten, name="organigramm_karten"),
    path("<int:pk>/", views.mitarbeiter_detail, name="detail"),

    # Stellen-Management
    path("stellen/", views.stellen_uebersicht, name="stellen_uebersicht"),
    path("stellen/neu/", views.stelle_bearbeiten, name="stelle_neu"),
    path("stellen/<int:pk>/bearbeiten/", views.stelle_bearbeiten, name="stelle_bearbeiten"),
    path("stellen/organigramm/", views.stellen_organigramm, name="stellen_organigramm"),
    path("stellen/delegation/", views.delegation_verwalten, name="delegation_verwalten"),

    # Mitarbeiter-Stellen-Zuweisung
    path("mitarbeiter/<int:pk>/stelle-zuweisen/", views.mitarbeiter_stelle_zuweisen, name="mitarbeiter_stelle_zuweisen"),

    # Netzwerk-Editor (VISUELLER Graph-Editor mit Schere)
    path("netzwerk-editor/", views.netzwerk_editor, name="netzwerk_editor"),
    path("netzwerk-editor/data/", views.netzwerk_editor_data, name="netzwerk_editor_data"),
    path("netzwerk-editor/save/", views.netzwerk_editor_save, name="netzwerk_editor_save"),

    # Tree-Editor (D3 Collapsible Tree mit Edit)
    path("tree-editor/", views.tree_editor, name="tree_editor"),
    path("tree-editor/data/", views.tree_editor_data, name="tree_editor_data"),
    path("tree-editor/save/", views.tree_editor_save, name="tree_editor_save"),

    # OrgChart Kasten (OrgChart.js mit Kaesten)
    path("orgchart-kasten/", views.orgchart_kasten, name="orgchart_kasten"),
    path("orgchart-kasten/data/", views.orgchart_kasten_data, name="orgchart_kasten_data"),

    # Kasten-Organigramm (HTML/CSS einfach)
    path("kasten-organigramm/", views.kasten_organigramm, name="kasten_organigramm"),
    path("kasten-organigramm/<str:kuerzel>/", views.kasten_detail, name="kasten_detail"),
    path("kasten-organigramm/bereich/form/", views.kasten_bereich_form, name="kasten_bereich_form"),
    path("kasten-organigramm/abteilung/form/", views.kasten_abteilung_form, name="kasten_abteilung_form"),
    path("kasten-organigramm/team/form/", views.kasten_team_form, name="kasten_team_form"),
    path("kasten-organigramm/stelle/form/", views.kasten_stelle_form, name="kasten_stelle_form"),
    path("kasten-organigramm/stelle/<int:pk>/edit/", views.kasten_stelle_edit, name="kasten_stelle_edit"),

    # Struktur-Editor (Tabellen-Editor)
    path("struktur-editor/", views.struktur_editor, name="struktur_editor"),
    path("struktur-editor/org/<int:pk>/parent/", views.struktur_editor_org_parent, name="struktur_editor_org_parent"),
    path("struktur-editor/stelle/<int:pk>/org/", views.struktur_editor_stelle_org, name="struktur_editor_stelle_org"),
    path("struktur-editor/stelle/<int:pk>/parent/", views.struktur_editor_stelle_parent, name="struktur_editor_stelle_parent"),
    path("struktur-editor/org/add/", views.struktur_editor_org_add, name="struktur_editor_org_add"),
    path("struktur-editor/stelle/add/", views.struktur_editor_stelle_add, name="struktur_editor_stelle_add"),
    path("struktur-editor/org/<int:pk>/edit/", views.struktur_editor_org_edit, name="struktur_editor_org_edit"),
    path("struktur-editor/stelle/<int:pk>/edit/", views.struktur_editor_stelle_edit, name="struktur_editor_stelle_edit"),
    path("struktur-editor/org/<int:pk>/delete/", views.struktur_editor_org_delete, name="struktur_editor_org_delete"),
    path("struktur-editor/stelle/<int:pk>/delete/", views.struktur_editor_stelle_delete, name="struktur_editor_stelle_delete"),

    # Org-Chart Editor (grafischer Editor)
    path("orgchart-editor/", views.orgchart_editor, name="orgchart_editor"),
    path("orgchart-editor/data/", views.orgchart_editor_data, name="orgchart_editor_data"),
    path("orgchart-editor/<str:typ>/<int:pk>/edit/", views.orgchart_editor_edit, name="orgchart_editor_edit"),
    path("orgchart-editor/add/", views.orgchart_editor_add, name="orgchart_editor_add"),
    path("orgchart-editor/<str:typ>/<int:pk>/delete/", views.orgchart_editor_delete, name="orgchart_editor_delete"),

    # Company Builder (ALTER Editor - kann entfernt werden)
    path("company-builder/", views.company_builder, name="company_builder"),
    path("company-builder/preview/", views.company_builder_preview, name="company_builder_preview"),
    path("company-builder/orgeinheit/neu/", views.company_builder_neue_orgeinheit, name="company_builder_orgeinheit_neu"),
    path("company-builder/stelle/neu/", views.company_builder_neue_stelle, name="company_builder_stelle_neu"),
    path("company-builder/mitarbeiter/neu/", views.company_builder_neuer_mitarbeiter, name="company_builder_mitarbeiter_neu"),
    path("company-builder/hierarchie/update/", views.company_builder_hierarchie_update, name="company_builder_hierarchie_update"),
    path("company-builder/organigramm/", views.company_builder_organigramm, name="company_builder_organigramm"),
    path("company-builder/snapshot/create/", views.snapshot_create, name="snapshot_create"),
    path("company-builder/snapshot/restore/", views.snapshot_restore, name="snapshot_restore"),
    path("company-builder/orgeinheit/<int:pk>/delete/", views.company_builder_delete_orgeinheit, name="company_builder_delete_orgeinheit"),
    path("company-builder/stelle/<int:pk>/delete/", views.company_builder_delete_stelle, name="company_builder_delete_stelle"),
]
