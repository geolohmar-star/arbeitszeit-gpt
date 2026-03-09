from django.urls import path

from . import api_views, views

app_name = "dms"

urlpatterns = [
    path("", views.dokument_liste, name="liste"),
    path("upload/", views.dokument_upload, name="upload"),
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
    # Versionsverlauf
    path("<int:pk>/versionen/<int:version_nr>/restore/", views.version_restore, name="version_restore"),
    # API v1 – externe Systeme (SAP, Paperless-ngx, etc.)
    path("api/v1/health/",                             api_views.api_health,                name="api_health"),
    path("api/v1/dokumente/",                          api_views.api_dokumente,             name="api_dokumente"),
    path("api/v1/dokumente/<int:pk>/",                 api_views.api_dokument_detail,       name="api_dokument_detail"),
    path("api/v1/dokumente/<int:pk>/inhalt/",          api_views.api_dokument_inhalt,       name="api_dokument_inhalt"),
    path("api/v1/dokumente/<int:pk>/version/",         api_views.api_dokument_neue_version, name="api_dokument_neue_version"),
    path("api/v1/kategorien/",                         api_views.api_kategorien,            name="api_kategorien"),
    path("api/v1/dokumentation/",                      views.api_dokumentation,             name="api_dokumentation"),
]
