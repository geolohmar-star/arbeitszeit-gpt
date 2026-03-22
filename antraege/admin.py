from django.contrib import admin

from .models import AntragsPfad, AntragsPfadSchritt, AntragsPfadSitzung, AntragsPfadTransition


class SchrittInline(admin.TabularInline):
    model = AntragsPfadSchritt
    extra = 0
    fields = ["node_id", "titel", "ist_start", "ist_ende"]


class TransitionInline(admin.TabularInline):
    model = AntragsPfadTransition
    extra = 0
    fields = ["von_schritt", "zu_schritt", "bedingung", "label", "reihenfolge"]


@admin.register(AntragsPfad)
class AntragsPfadAdmin(admin.ModelAdmin):
    list_display = ["name", "aktiv", "erstellt_von", "erstellt_am"]
    list_filter = ["aktiv"]
    inlines = [SchrittInline, TransitionInline]


@admin.register(AntragsPfadSitzung)
class AntragsPfadSitzungAdmin(admin.ModelAdmin):
    list_display = ["pfad", "user", "status", "gestartet_am", "abgeschlossen_am"]
    list_filter = ["status", "pfad"]
    readonly_fields = ["gesammelte_daten", "besuchte_schritte"]
