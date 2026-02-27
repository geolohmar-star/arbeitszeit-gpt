from django.urls import path

from . import views

app_name = "veranstaltungen"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("anlegen/", views.anlegen, name="anlegen"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/anmelden/", views.anmelden, name="anmelden"),
    path(
        "<int:pk>/bestaetigung/",
        views.bestaetigung_liste,
        name="bestaetigung_liste",
    ),
    path(
        "<int:pk>/gutschrift/",
        views.gutschrift_erstellen,
        name="gutschrift_erstellen",
    ),
    path(
        "<int:pk>/gutschrift/pdf/",
        views.gutschrift_pdf,
        name="gutschrift_pdf",
    ),
    path(
        "<int:pk>/status/",
        views.status_aendern,
        name="status_aendern",
    ),
]
