from django.contrib import admin

from .models import Loeschprotokoll


@admin.register(Loeschprotokoll)
class LoeschprotokollAdmin(admin.ModelAdmin):
    list_display = [
        "personalnummer", "nachname_kuerzel", "austritt_datum",
        "loeschung_ausgefuehrt_am", "loeschung_durch",
    ]
    readonly_fields = [
        "user_id_intern", "personalnummer", "nachname_kuerzel",
        "eintritt_datum", "austritt_datum",
        "loeschung_ausgefuehrt_am", "loeschung_durch",
        "kategorien", "protokoll_pdf",
    ]
    search_fields = ["personalnummer", "nachname_kuerzel"]
    list_filter = ["loeschung_ausgefuehrt_am"]

    def has_add_permission(self, request):
        return False  # Nur durch System erstellt

    def has_delete_permission(self, request, obj=None):
        return False  # Loeschprotokolle duerfen niemals manuell geloescht werden
