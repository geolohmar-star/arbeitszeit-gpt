from django.urls import path

from formulare import views

app_name = "formulare"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "meine-antraege/",
        views.meine_antraege,
        name="meine_antraege",
    ),
    path(
        "aenderung-zeiterfassung/",
        views.aenderung_zeiterfassung,
        name="aenderung_zeiterfassung",
    ),
    path(
        "aenderung-zeiterfassung/<int:pk>/erfolg/",
        views.aenderung_erfolg,
        name="aenderung_erfolg",
    ),
    path(
        "aenderung-zeiterfassung/<int:pk>/pdf/",
        views.aenderung_pdf,
        name="aenderung_pdf",
    ),
    path(
        "aenderung-zeiterfassung/felder/",
        views.aenderung_felder,
        name="aenderung_felder",
    ),
    path(
        "aenderung-zeiterfassung/neue-zeitzeile/",
        views.neue_zeitzeile,
        name="neue_zeitzeile",
    ),
    path(
        "aenderung-zeiterfassung/samstag-felder/",
        views.samstag_felder,
        name="samstag_felder",
    ),
    path(
        "aenderung-zeiterfassung/soll-fuer-datum/",
        views.soll_fuer_datum,
        name="soll_fuer_datum",
    ),
    path(
        "aenderung-zeiterfassung/neue-tauschzeile/",
        views.neue_tauschzeile,
        name="neue_tauschzeile",
    ),
    path(
        "aenderung-zeiterfassung/tausch-validierung/",
        views.tausch_validierung,
        name="tausch_validierung",
    ),
]
