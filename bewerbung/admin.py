from django.contrib import admin

from .models import Bewerbung, BewerbungDokument


@admin.register(Bewerbung)
class BewerbungAdmin(admin.ModelAdmin):
    list_display = ["vollname", "status", "erstellt_am", "bearbeitet_von"]
    list_filter = ["status"]
    search_fields = ["vorname", "nachname"]
    readonly_fields = ["erstellt_am"]

    def has_add_permission(self, request):
        return False


@admin.register(BewerbungDokument)
class BewerbungDokumentAdmin(admin.ModelAdmin):
    list_display = ["bewerbung", "typ", "dateiname", "groesse_bytes"]
    readonly_fields = ["bewerbung", "typ", "dateiname", "dateityp", "inhalt_verschluesselt", "groesse_bytes"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
