from django.contrib import admin

from .models import (
    Belegung,
    Bereich,
    Besuchsanmeldung,
    Gebaeude,
    Geschoss,
    RaumbuchLog,
    Raumbuchung,
    RaumArbeitsschutzDaten,
    RaumElektroDaten,
    RaumFacilityDaten,
    RaumInstallationDaten,
    RaumNetzwerkDaten,
    Raum,
    Reinigungsplan,
    ReinigungsQuittung,
    Schluessel,
    SchluesselAusgabe,
    Standort,
    Treppenhaus,
    Umzugsauftrag,
    ZutrittsProfil,
    ZutrittsToken,
)


@admin.register(Standort)
class StandortAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "adresse"]
    search_fields = ["name", "kuerzel"]


@admin.register(Gebaeude)
class GebaeudeAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "bezeichnung", "standort", "baujahr"]
    list_filter = ["standort"]
    search_fields = ["bezeichnung", "kuerzel"]


@admin.register(Treppenhaus)
class TreppenhausAdmin(admin.ModelAdmin):
    list_display = ["bezeichnung", "gebaeude", "typ", "zustand", "naechste_pruefung"]
    list_filter = ["typ", "zustand", "gebaeude"]
    search_fields = ["bezeichnung"]


@admin.register(Geschoss)
class GeschossAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "bezeichnung", "gebaeude", "reihenfolge"]
    list_filter = ["gebaeude", "kuerzel"]


@admin.register(Bereich)
class BereichAdmin(admin.ModelAdmin):
    list_display = ["bezeichnung", "kuerzel", "geschoss"]
    list_filter = ["geschoss__gebaeude"]
    search_fields = ["bezeichnung"]


class BelegungInline(admin.TabularInline):
    model = Belegung
    extra = 0
    fields = ["mitarbeiter", "von", "bis", "notiz"]


@admin.register(Raum)
class RaumAdmin(admin.ModelAdmin):
    list_display = ["raumnummer", "raumname", "raumtyp", "geschoss", "ist_aktiv", "ist_leer"]
    list_filter = ["raumtyp", "nutzungsmodell", "ist_aktiv", "ist_leer", "geschoss__gebaeude"]
    search_fields = ["raumnummer", "raumname"]
    inlines = [BelegungInline]


@admin.register(Belegung)
class BelegungAdmin(admin.ModelAdmin):
    list_display = ["raum", "mitarbeiter", "von", "bis"]
    list_filter = ["raum__geschoss__gebaeude"]
    search_fields = ["mitarbeiter__nachname", "mitarbeiter__vorname"]


@admin.register(Reinigungsplan)
class ReinigungsplanAdmin(admin.ModelAdmin):
    list_display = ["raum", "intervall", "letzte_reinigung", "zustaendig"]
    list_filter = ["intervall"]


@admin.register(ReinigungsQuittung)
class ReinigungsQuittungAdmin(admin.ModelAdmin):
    list_display = ["raum", "quittiert_durch_name", "zeitstempel"]
    list_filter = ["raum__geschoss__gebaeude"]


@admin.register(Besuchsanmeldung)
class BesuchsanmeldungAdmin(admin.ModelAdmin):
    list_display = [
        "besucher_nachname", "besucher_vorname", "besucher_firma",
        "datum", "gastgeber", "status",
    ]
    list_filter = ["status", "datum"]
    search_fields = ["besucher_nachname", "besucher_vorname", "besucher_firma"]


class SchluesselAusgabeInline(admin.TabularInline):
    model = SchluesselAusgabe
    extra = 0
    fields = ["empfaenger", "ausgabe_datum", "rueckgabe_datum", "bemerkung"]


@admin.register(Schluessel)
class SchluesselAdmin(admin.ModelAdmin):
    list_display = ["schluesselnummer", "bezeichnung", "schliessanlage", "schliessanlage_typ", "anzahl_kopien"]
    list_filter = ["schliessanlage_typ"]
    search_fields = ["schluesselnummer", "bezeichnung"]
    filter_horizontal = ["raeume"]
    inlines = [SchluesselAusgabeInline]


@admin.register(SchluesselAusgabe)
class SchluesselAusgabeAdmin(admin.ModelAdmin):
    list_display = ["schluessel", "empfaenger", "ausgabe_datum", "rueckgabe_datum"]
    list_filter = ["ausgabe_datum"]
    search_fields = ["empfaenger__nachname", "schluessel__schluesselnummer"]


@admin.register(ZutrittsProfil)
class ZutrittsProfilAdmin(admin.ModelAdmin):
    list_display = ["bezeichnung"]
    filter_horizontal = ["raeume"]
    search_fields = ["bezeichnung"]


@admin.register(ZutrittsToken)
class ZutrittsTokenAdmin(admin.ModelAdmin):
    list_display = ["badge_id", "mitarbeiter", "status", "ausgestellt_am", "gueltig_bis"]
    list_filter = ["status"]
    search_fields = ["badge_id", "mitarbeiter__nachname"]
    filter_horizontal = ["profile"]


@admin.register(Raumbuchung)
class RaumbuchungAdmin(admin.ModelAdmin):
    list_display = ["buchungs_nr", "raum", "datum", "von", "bis", "buchender", "status"]
    list_filter = ["status", "datum"]
    search_fields = ["buchungs_nr", "betreff"]


@admin.register(Umzugsauftrag)
class UmzugsauftragAdmin(admin.ModelAdmin):
    list_display = ["mitarbeiter", "von_raum", "nach_raum", "datum_geplant", "status"]
    list_filter = ["status"]


@admin.register(RaumbuchLog)
class RaumbuchLogAdmin(admin.ModelAdmin):
    list_display = ["aktion", "raum", "geaendert_von", "geaendert_am", "model_name"]
    list_filter = ["aktion", "model_name"]
    readonly_fields = ["geaendert_am"]
