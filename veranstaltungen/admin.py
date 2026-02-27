from django.contrib import admin

from .models import Feier, FeierteilnahmeAnmeldung, FeierteilnahmeGutschrift


class AnmeldungInline(admin.TabularInline):
    model = FeierteilnahmeAnmeldung
    extra = 0
    fields = [
        "mitarbeiter",
        "ist_vorbereitungsteam",
        "ist_gast",
        "teilnahme_bestaetigt",
        "bemerkung",
    ]
    autocomplete_fields = ["mitarbeiter"]


@admin.register(Feier)
class FeierAdmin(admin.ModelAdmin):
    list_display = [
        "titel",
        "art",
        "datum",
        "status",
        "reichweite",
        "verantwortlicher",
    ]
    list_filter = ["art", "status", "reichweite", "datum"]
    search_fields = ["titel", "ort"]
    date_hierarchy = "datum"
    inlines = [AnmeldungInline]
    fieldsets = [
        (
            "Grunddaten",
            {
                "fields": [
                    "titel",
                    "art",
                    "datum",
                    "uhrzeit_von",
                    "uhrzeit_bis",
                    "ort",
                    "status",
                    "anmeldeschluss",
                ]
            },
        ),
        (
            "Zuordnung",
            {
                "fields": [
                    "reichweite",
                    "abteilung",
                    "bereich",
                    "erstellt_von",
                    "verantwortlicher",
                ]
            },
        ),
        (
            "Zeitgutschrift Teilnehmer",
            {
                "fields": [
                    "gutschrift_stunden",
                    "gutschrift_faktor",
                ]
            },
        ),
        (
            "Zeitgutschrift Vorbereitungsteam",
            {
                "fields": [
                    "vorbereitung_stunden",
                    "vorbereitung_faktor",
                ]
            },
        ),
    ]


@admin.register(FeierteilnahmeAnmeldung)
class FeierteilnahmeAnmeldungAdmin(admin.ModelAdmin):
    list_display = [
        "feier",
        "mitarbeiter",
        "ist_vorbereitungsteam",
        "teilnahme_bestaetigt",
        "angemeldet_am",
    ]
    list_filter = ["feier", "ist_vorbereitungsteam", "teilnahme_bestaetigt"]
    search_fields = [
        "mitarbeiter__vorname",
        "mitarbeiter__nachname",
        "feier__titel",
    ]
    autocomplete_fields = ["mitarbeiter", "feier"]


@admin.register(FeierteilnahmeGutschrift)
class FeierteilnahmeGutschriftAdmin(admin.ModelAdmin):
    list_display = ["feier", "status", "erstellt_von", "erstellt_am"]
    list_filter = ["status"]
    search_fields = ["feier__titel"]
