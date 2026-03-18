from django.urls import path

from . import api_views, views

app_name = "dms"

urlpatterns = [
    path("", views.dokument_liste, name="liste"),
    path("upload/", views.dokument_upload, name="upload"),
    path("tags/anlegen/", views.tag_anlegen, name="tag_anlegen"),
    path("<int:pk>/loeschen/planen/", views.dokument_loeschen_planen, name="loeschen_planen"),
    path("neu/", views.dokument_neu, name="neu"),
    path("<int:pk>/", views.dokument_detail, name="detail"),
    path("<int:pk>/download/", views.dokument_download, name="download"),
    path("<int:pk>/vorschau/", views.dokument_vorschau, name="vorschau"),
    # Zugriffsschluessel
    path("<int:pk>/zugriff/beantragen/", views.zugriff_beantragen, name="zugriff_beantragen"),
    path("zugriffsantraege/", views.zugriffsantraege_liste, name="zugriffsantraege"),
    path("zugriffsantraege/<int:schluessel_pk>/genehmigen/", views.zugriff_genehmigen, name="zugriff_genehmigen"),
    path("zugriffsantraege/<int:schluessel_pk>/ablehnen/", views.zugriff_ablehnen, name="zugriff_ablehnen"),
    path("zugriffsantraege/<int:schluessel_pk>/widerrufen/", views.zugriff_widerrufen, name="zugriff_widerrufen"),
    # OnlyOffice-Integration
    path("<int:pk>/onlyoffice/", views.onlyoffice_editor, name="onlyoffice_editor"),
    path("<int:pk>/onlyoffice/laden/", views.onlyoffice_dokument_laden, name="onlyoffice_laden"),
    path("<int:pk>/onlyoffice/callback/", views.onlyoffice_callback, name="onlyoffice_callback"),
    path("<int:pk>/onlyoffice/forcesave/", views.onlyoffice_forcesave, name="onlyoffice_forcesave"),
    path("<int:pk>/onlyoffice/version/", views.onlyoffice_version_check, name="onlyoffice_version_check"),
    # DMS → Workflow + Laufzettel
    path("<int:pk>/workflow/starten/", views.dms_workflow_starten, name="workflow_starten"),
    path("<int:pk>/workflow/vorschlag-verwerfen/", views.workflow_vorschlag_verwerfen, name="workflow_vorschlag_verwerfen"),
    path("<int:pk>/laufzettel/starten/", views.dms_laufzettel_starten, name="laufzettel_starten"),
    path("api/stellen/", views.stelle_autocomplete, name="stelle_autocomplete"),
    path("api/laufzettel-vorlagen/", views.laufzettel_vorlagen, name="laufzettel_vorlagen"),
    # Ablage-Kategorien verwalten (DMS-Admin)
    path("einstellungen/ablagen/", views.ablage_liste, name="ablage_liste"),
    path("einstellungen/ablagen/<int:pk>/bearbeiten/", views.ablage_bearbeiten, name="ablage_bearbeiten"),
    path("einstellungen/ablagen/<int:pk>/loeschen/", views.ablage_loeschen, name="ablage_loeschen"),
    # Workflow-Trigger-Regeln (Staff)
    path("einstellungen/workflow-regeln/", views.workflow_regeln_liste, name="workflow_regeln"),
    path("einstellungen/workflow-regeln/neu/", views.workflow_regel_erstellen, name="workflow_regel_erstellen"),
    path("einstellungen/workflow-regeln/<int:regel_pk>/bearbeiten/", views.workflow_regel_bearbeiten, name="workflow_regel_bearbeiten"),
    path("einstellungen/workflow-regeln/<int:regel_pk>/loeschen/", views.workflow_regel_loeschen, name="workflow_regel_loeschen"),
    # Versionsverlauf
    path("<int:pk>/versionen/<int:version_nr>/restore/",          views.version_restore,         name="version_restore"),
    path("<int:pk>/versionen/<int:version_nr>/download/",         views.version_download,        name="version_download"),
    path("<int:pk>/versionen/<int:version_nr>/vorschau/",         views.version_vorschau,        name="version_vorschau"),
    path("<int:pk>/versionen/<int:version_nr>/onlyoffice/",       views.version_onlyoffice,      name="version_onlyoffice"),
    path("<int:pk>/versionen/<int:version_nr>/onlyoffice/laden/", views.onlyoffice_version_laden, name="version_onlyoffice_laden"),
    # Persoenliche Ablage
    path("meine-ablage/",                                               views.meine_ablage,                    name="meine_ablage"),
    path("meine-ablage/upload/",                                        views.meine_ablage_upload,             name="meine_ablage_upload"),
    path("meine-ablage/<int:pk>/freigabe/",                             views.meine_ablage_freigabe,           name="meine_ablage_freigabe"),
    path("meine-ablage/<int:pk>/freigabe/<int:user_pk>/entfernen/",     views.meine_ablage_freigabe_entfernen, name="meine_ablage_freigabe_entfernen"),
    path("meine-ablage/<int:pk>/loeschen/",                             views.meine_ablage_loeschen,           name="meine_ablage_loeschen"),
    # API v1 – externe Systeme (SAP, Paperless-ngx, etc.)
    path("api/v1/health/",                             api_views.api_health,                name="api_health"),
    path("api/v1/dokumente/",                          api_views.api_dokumente,             name="api_dokumente"),
    path("api/v1/dokumente/<int:pk>/",                 api_views.api_dokument_detail,       name="api_dokument_detail"),
    path("api/v1/dokumente/<int:pk>/inhalt/",          api_views.api_dokument_inhalt,       name="api_dokument_inhalt"),
    path("api/v1/dokumente/<int:pk>/version/",         api_views.api_dokument_neue_version, name="api_dokument_neue_version"),
    path("api/v1/kategorien/",                         api_views.api_kategorien,            name="api_kategorien"),
    path("api/v1/dokumentation/",                      views.api_dokumentation,             name="api_dokumentation"),
]
