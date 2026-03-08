from django.contrib import admin

from .models import DokumentZugriff, SensiblesDokument


@admin.register(SensiblesDokument)
class SensiblesDokumentAdmin(admin.ModelAdmin):
    list_display = ["dateiname", "kategorie", "user", "groesse_bytes", "hochgeladen_am", "hochgeladen_von"]
    list_filter = ["kategorie", "hochgeladen_am"]
    search_fields = ["dateiname", "user__username", "user__last_name", "beschreibung"]
    readonly_fields = [
        "dateiname", "dateityp", "inhalt_verschluesselt", "groesse_bytes",
        "hochgeladen_am", "hochgeladen_von",
    ]
    # Kein Loeschen oder Hinzufuegen ueber Admin – nur lesender Ueberblick
    def has_add_permission(self, request):
        return False


@admin.register(DokumentZugriff)
class DokumentZugriffAdmin(admin.ModelAdmin):
    list_display = ["zeitpunkt", "user", "dokument", "ip_adresse"]
    list_filter = ["zeitpunkt"]
    search_fields = ["user__username", "dokument__dateiname", "ip_adresse"]
    readonly_fields = ["dokument", "user", "zeitpunkt", "ip_adresse"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
