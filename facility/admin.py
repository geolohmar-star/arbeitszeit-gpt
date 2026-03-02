from django.contrib import admin

from .models import FacilityTeam, Stoermeldung, Textbaustein


@admin.register(Textbaustein)
class TextbausteinAdmin(admin.ModelAdmin):
    list_display = ["kategorie", "text", "reihenfolge", "ist_aktiv"]
    list_filter = ["kategorie", "ist_aktiv"]
    search_fields = ["text"]


@admin.register(FacilityTeam)
class FacilityTeamAdmin(admin.ModelAdmin):
    list_display = ["kategorie", "teamleiter", "eskalation_nach_tagen"]
    filter_horizontal = ["mitglieder"]


@admin.register(Stoermeldung)
class StoermeldungAdmin(admin.ModelAdmin):
    list_display = [
        "get_betreff",
        "kategorie",
        "prioritaet",
        "status",
        "melder",
        "erstellt_am",
    ]
    list_filter = ["kategorie", "status", "prioritaet"]
    search_fields = ["raumnummer", "beschreibung"]
    date_hierarchy = "erstellt_am"
