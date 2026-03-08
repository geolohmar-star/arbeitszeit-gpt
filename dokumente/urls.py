from django.urls import path

from . import views

app_name = "dokumente"

urlpatterns = [
    path("", views.dokument_liste, name="liste"),
    path("hochladen/", views.dokument_hochladen, name="hochladen"),
    path("<int:pk>/download/", views.dokument_download, name="download"),
    path("<int:pk>/loeschen/", views.dokument_loeschen, name="loeschen"),
    path("log/", views.zugriffs_log, name="log"),
]
