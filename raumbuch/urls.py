from django.urls import path
from . import views

app_name = "raumbuch"

urlpatterns = [
    # Raumstruktur
    path("", views.raum_uebersicht, name="uebersicht"),
    path("struktur/", views.gebaeude_struktur, name="struktur"),
    path("raum/neu/", views.raum_erstellen, name="raum_erstellen"),
    path("raum/<int:pk>/", views.raum_detail, name="raum_detail"),
    path("raum/<int:pk>/bearbeiten/", views.raum_bearbeiten, name="raum_bearbeiten"),
    path("raum/<int:pk>/loeschen/", views.raum_loeschen, name="raum_loeschen"),
    # Datenschichten
    path("raum/<int:pk>/facility/", views.raum_facility_daten, name="raum_facility"),
    path("raum/<int:pk>/elektro/", views.raum_elektro_daten, name="raum_elektro"),
    path("raum/<int:pk>/netzwerk/", views.raum_netzwerk_daten, name="raum_netzwerk"),
    path("raum/<int:pk>/installation/", views.raum_installation_daten, name="raum_installation"),
    path("raum/<int:pk>/arbeitsschutz/", views.raum_arbeitsschutz_daten, name="raum_arbeitsschutz"),
    path("raum/<int:pk>/log/", views.raum_log, name="raum_log"),
    # Treppenhaus
    path("treppenhaus/", views.treppenhaus_liste, name="treppenhaus_liste"),
    path("treppenhaus/neu/", views.treppenhaus_form, name="treppenhaus_erstellen"),
    path("treppenhaus/<int:pk>/bearbeiten/", views.treppenhaus_form, name="treppenhaus_bearbeiten"),
    path("treppenhaus/<int:pk>/loeschen/", views.treppenhaus_loeschen, name="treppenhaus_loeschen"),
    # Schluessel
    path("schluessel/", views.schluessel_liste, name="schluessel_liste"),
    path("schluessel/neu/", views.schluessel_form, name="schluessel_erstellen"),
    path("schluessel/<int:pk>/", views.schluessel_detail, name="schluessel_detail"),
    path("schluessel/<int:pk>/bearbeiten/", views.schluessel_form, name="schluessel_bearbeiten"),
    path("schluessel/<int:pk>/ausgabe/", views.schluessel_ausgabe, name="schluessel_ausgabe"),
    path(
        "schluessel/ausgabe/<int:ausgabe_pk>/rueckgabe/",
        views.schluessel_rueckgabe,
        name="schluessel_rueckgabe",
    ),
    # Zutrittskontrolle
    path("token/", views.token_liste, name="token_liste"),
    path("token/beantragen/", views.token_anfrage, name="token_anfrage"),
    path("token/neu/", views.token_form, name="token_erstellen"),
    path("token/<int:pk>/bearbeiten/", views.token_form, name="token_bearbeiten"),
    path("token/<int:pk>/sperren/", views.token_sperren, name="token_sperren"),
    path("profil/", views.zutrittsprofil_liste, name="profil_liste"),
    path("profil/neu/", views.zutrittsprofil_form, name="profil_erstellen"),
    path("profil/<int:pk>/bearbeiten/", views.zutrittsprofil_form, name="profil_bearbeiten"),
    # Belegung
    path("belegung/", views.belegungsplan, name="belegungsplan"),
    path("belegung/neu/", views.belegung_form, name="belegung_erstellen"),
    path("belegung/<int:pk>/bearbeiten/", views.belegung_form, name="belegung_bearbeiten"),
    path("belegung/<int:pk>/loeschen/", views.belegung_loeschen, name="belegung_loeschen"),
    # Reinigung
    path("reinigung/", views.reinigung_uebersicht, name="reinigung"),
    path("reinigung/<int:raum_pk>/plan/", views.reinigungsplan_form, name="reinigungsplan"),
    path("reinigung/<int:raum_pk>/quittieren/", views.reinigung_quittieren, name="reinigung_quittieren"),
    # Besuch
    path("besuch/", views.besuch_liste, name="besuch_liste"),
    path("besuch/neu/", views.besuch_anmelden, name="besuch_anmelden"),
    path("besuch/<int:pk>/bearbeiten/", views.besuch_bearbeiten, name="besuch_bearbeiten"),
    # Buchung
    path("buchung/", views.buchung_kalender, name="buchung_kalender"),
    path("buchung/neu/", views.buchung_erstellen, name="buchung_erstellen"),
    path("buchung/raum/<int:raum_pk>/neu/", views.buchung_erstellen, name="buchung_fuer_raum"),
    path("buchung/<int:pk>/", views.buchung_detail, name="buchung_detail"),
    path("buchung/<int:pk>/stornieren/", views.buchung_stornieren, name="buchung_stornieren"),
    # Umzug
    path("umzug/", views.umzug_liste, name="umzug_liste"),
    path("umzug/neu/", views.umzug_form, name="umzug_erstellen"),
    path("umzug/<int:pk>/bearbeiten/", views.umzug_form, name="umzug_bearbeiten"),
    path("umzug/<int:pk>/erledigen/", views.umzug_erledigen, name="umzug_erledigen"),
    # Log
    path("log/", views.gesamtlog, name="gesamtlog"),
]
