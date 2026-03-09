from django.urls import path

from . import views

app_name = "dms"

urlpatterns = [
    path("", views.dokument_liste, name="liste"),
    path("upload/", views.dokument_upload, name="upload"),
    path("<int:pk>/", views.dokument_detail, name="detail"),
    path("<int:pk>/download/", views.dokument_download, name="download"),
    path("<int:pk>/vorschau/", views.dokument_vorschau, name="vorschau"),
]
