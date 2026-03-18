from django.urls import path

from . import views

app_name = "korrespondenz"

urlpatterns = [
    # Briefvorgaenge
    path("",                        views.brief_liste,     name="brief_liste"),
    path("neu/",                    views.brief_erstellen, name="brief_erstellen"),
    path("<int:pk>/",               views.brief_detail,    name="brief_detail"),
    path("<int:pk>/download/",      views.brief_download,  name="brief_download"),
    path("<int:pk>/status/",        views.brief_status_aendern, name="brief_status_aendern"),
    path("<int:pk>/loeschen/",      views.brief_loeschen,  name="brief_loeschen"),
    path("<int:pk>/in-ablage/",     views.brief_in_ablage_speichern, name="brief_in_ablage"),
    path("<int:pk>/pdf/",           views.brief_pdf_exportieren, name="brief_pdf_exportieren"),
    # OnlyOffice-Integration
    path("<int:pk>/onlyoffice/",          views.brief_editor,                  name="brief_editor"),
    path("<int:pk>/onlyoffice/laden/",    views.brief_onlyoffice_laden,        name="onlyoffice_laden"),
    path("<int:pk>/onlyoffice/callback/", views.brief_onlyoffice_callback,     name="onlyoffice_callback"),
    path("<int:pk>/onlyoffice/forcesave/",views.brief_onlyoffice_forcesave,    name="onlyoffice_forcesave"),
    path("<int:pk>/onlyoffice/version/",  views.brief_onlyoffice_version_check,name="onlyoffice_version_check"),
    # Briefvorlagen
    path("vorlagen/",                      views.vorlage_liste,    name="vorlage_liste"),
    path("vorlagen/<int:pk>/defaults/",    views.vorlage_defaults, name="vorlage_defaults"),
]
