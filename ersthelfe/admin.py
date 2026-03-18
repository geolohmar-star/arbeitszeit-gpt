from django.contrib import admin

from .models import ErsteHilfeErsthelferToken, ErsteHilfeRueckmeldung, ErsteHilfeVorfall


@admin.register(ErsteHilfeVorfall)
class ErsteHilfeVorfallAdmin(admin.ModelAdmin):
    list_display = ["pk", "ort", "status", "gemeldet_von", "erstellt_am"]
    list_filter = ["status"]
    readonly_fields = ["erstellt_am", "geschlossen_am"]
    search_fields = ["ort", "beschreibung"]


@admin.register(ErsteHilfeRueckmeldung)
class ErsteHilfeRueckmeldungAdmin(admin.ModelAdmin):
    list_display = ["vorfall", "ersthelfer", "status", "gemeldet_am"]
    list_filter = ["status"]
    readonly_fields = ["gemeldet_am"]


@admin.register(ErsteHilfeErsthelferToken)
class ErsteHilfeErsthelferTokenAdmin(admin.ModelAdmin):
    list_display = ["vorfall", "ersthelfer", "erstellt_am"]
    readonly_fields = ["token", "erstellt_am"]
