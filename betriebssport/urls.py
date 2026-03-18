from django.urls import path

from . import views

app_name = "betriebssport"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("anlegen/", views.gruppe_anlegen, name="gruppe_anlegen"),
    path("<int:pk>/", views.gruppe_detail, name="gruppe_detail"),
    path("<int:pk>/bearbeiten/", views.gruppe_bearbeiten, name="gruppe_bearbeiten"),
    path("<int:pk>/beitreten/", views.beitreten_toggle, name="beitreten_toggle"),
    path(
        "<int:pk>/einheit/anlegen/",
        views.einheit_anlegen,
        name="einheit_anlegen",
    ),
    path(
        "<int:pk>/einheit/<int:einheit_pk>/ausgefallen/",
        views.einheit_ausgefallen,
        name="einheit_ausgefallen",
    ),
    path(
        "<int:pk>/einheit/<int:einheit_pk>/teilnahme/",
        views.teilnahme_toggle,
        name="teilnahme_toggle",
    ),
    path(
        "<int:pk>/gutschrift/<str:monat_str>/",
        views.gutschrift_monat,
        name="gutschrift_monat",
    ),
    path(
        "<int:pk>/gutschrift/<str:monat_str>/download/",
        views.gutschrift_download,
        name="gutschrift_download",
    ),
    path(
        "<int:pk>/gutschrift/<str:monat_str>/laufzettel/starten/",
        views.gutschrift_laufzettel_starten,
        name="gutschrift_laufzettel_starten",
    ),
]
