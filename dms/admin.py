from django.contrib import admin

from .models import (
    ApiToken,
    Dokument,
    DokumentKategorie,
    DokumentTag,
    DokumentZugriffsschluessel,
    PaperlessImportLog,
    PaperlessWorkflowRegel,
    ZugriffsProtokoll,
)


@admin.register(DokumentKategorie)
class DokumentKategorieAdmin(admin.ModelAdmin):
    list_display = ["name", "klasse", "elternkategorie", "sortierung"]
    list_filter = ["klasse"]
    search_fields = ["name"]


@admin.register(DokumentTag)
class DokumentTagAdmin(admin.ModelAdmin):
    list_display = ["name", "farbe"]
    search_fields = ["name"]


@admin.register(Dokument)
class DokumentAdmin(admin.ModelAdmin):
    list_display = ["titel", "klasse", "kategorie", "eigentuemereinheit", "dateiname", "groesse_bytes", "erstellt_am"]
    list_filter = ["klasse", "kategorie", "eigentuemereinheit"]
    search_fields = ["titel", "dateiname", "beschreibung"]
    readonly_fields = ["erstellt_am", "paperless_id", "suchvektor"]
    filter_horizontal = ["tags", "sichtbar_fuer"]


@admin.register(ZugriffsProtokoll)
class ZugriffsProtokollAdmin(admin.ModelAdmin):
    list_display = ["zeitpunkt", "user", "aktion", "dokument", "ip_adresse"]
    list_filter = ["aktion"]
    search_fields = ["user__username", "dokument__titel"]
    readonly_fields = ["zeitpunkt", "user", "aktion", "dokument", "ip_adresse"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DokumentZugriffsschluessel)
class DokumentZugriffsschluesselAdmin(admin.ModelAdmin):
    list_display = ["antrag_zeitpunkt", "user", "dokument", "status", "gewuenschte_dauer_h", "ist_aktiv", "gueltig_bis", "genehmigt_von"]
    list_filter = ["status"]
    search_fields = ["user__username", "dokument__titel", "antrag_grund"]
    readonly_fields = ["antrag_zeitpunkt"]

    def ist_aktiv(self, obj):
        return obj.ist_aktiv()
    ist_aktiv.boolean = True
    ist_aktiv.short_description = "Aktiv?"


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ["bezeichnung", "system", "erlaubte_klassen", "aktiv", "erstellt_am", "letzte_nutzung"]
    list_filter = ["aktiv", "erlaubte_klassen"]
    search_fields = ["bezeichnung", "system"]
    readonly_fields = ["erstellt_am", "letzte_nutzung", "token"]

    def save_model(self, request, obj, form, change):
        """Token wird automatisch generiert wenn noch keiner gesetzt ist."""
        super().save_model(request, obj, form, change)


@admin.register(PaperlessImportLog)
class PaperlessImportLogAdmin(admin.ModelAdmin):
    list_display = ["paperless_id", "status", "dokument", "importiert_am"]
    list_filter = ["status"]
    readonly_fields = ["importiert_am", "paperless_id", "status", "dokument", "fehler"]


@admin.register(PaperlessWorkflowRegel)
class PaperlessWorkflowRegelAdmin(admin.ModelAdmin):
    list_display = ["bezeichnung", "treffer_typ", "paperless_name", "workflow_template", "prioritaet", "aktiv"]
    list_filter = ["aktiv", "treffer_typ"]
    search_fields = ["bezeichnung", "paperless_name"]
    list_editable = ["prioritaet", "aktiv"]
