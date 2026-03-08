from django.contrib import admin

from .models import (
    BetriebssportGutschrift,
    Sporteinheit,
    Sportgruppe,
    SportgruppeMitglied,
    Sportteilnahme,
)


class SportgruppeMitgliedInline(admin.TabularInline):
    model = SportgruppeMitglied
    extra = 0
    autocomplete_fields = ["mitarbeiter"]


@admin.register(Sportgruppe)
class SportgruppeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "sportart",
        "standort",
        "get_wochentag_display",
        "verantwortlicher",
        "status",
    ]
    list_filter = ["sportart", "status", "standort"]
    search_fields = ["name", "verantwortlicher__nachname"]
    inlines = [SportgruppeMitgliedInline]

    def get_wochentag_display(self, obj):
        return obj.get_wochentag_display()
    get_wochentag_display.short_description = "Wochentag"


@admin.register(Sporteinheit)
class SporteinheitAdmin(admin.ModelAdmin):
    list_display = ["gruppe", "datum", "status", "kw"]
    list_filter = ["status", "gruppe"]
    date_hierarchy = "datum"

    def kw(self, obj):
        return obj.kw
    kw.short_description = "KW"


@admin.register(Sportteilnahme)
class SportteilnahmeAdmin(admin.ModelAdmin):
    list_display = ["mitarbeiter", "einheit", "markiert_am"]
    list_filter = ["einheit__gruppe"]
    search_fields = ["mitarbeiter__nachname"]


@admin.register(BetriebssportGutschrift)
class BetriebssportGutschriftAdmin(admin.ModelAdmin):
    list_display = ["gruppe", "monat", "status", "erstellt_von", "eingereicht_am"]
    list_filter = ["status", "gruppe"]
    date_hierarchy = "monat"
