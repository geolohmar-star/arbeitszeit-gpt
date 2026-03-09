from django.urls import path

from . import views

app_name = "dms"

urlpatterns = [
    path("", views.dokument_liste, name="liste"),
    path("upload/", views.dokument_upload, name="upload"),
    path("<int:pk>/", views.dokument_detail, name="detail"),
    path("<int:pk>/download/", views.dokument_download, name="download"),
    path("<int:pk>/vorschau/", views.dokument_vorschau, name="vorschau"),
    # Zugriffsschluessel
    path("<int:pk>/zugriff/beantragen/", views.zugriff_beantragen, name="zugriff_beantragen"),
    path("zugriffsantraege/", views.zugriffsantraege_liste, name="zugriffsantraege"),
    path("zugriffsantraege/<int:schluessel_pk>/genehmigen/", views.zugriff_genehmigen, name="zugriff_genehmigen"),
    path("zugriffsantraege/<int:schluessel_pk>/ablehnen/", views.zugriff_ablehnen, name="zugriff_ablehnen"),
    path("zugriffsantraege/<int:schluessel_pk>/widerrufen/", views.zugriff_widerrufen, name="zugriff_widerrufen"),
]
