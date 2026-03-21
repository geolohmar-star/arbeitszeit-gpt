from django.contrib import admin
from .models import BackupProtokoll


@admin.register(BackupProtokoll)
class BackupProtokollAdmin(admin.ModelAdmin):
    list_display = [
        "erstellt_am",
        "typ",
        "status",
        "dateiname",
        "dateigroesse_mb",
        "tabellen_anzahl",
        "erstellt_von",
    ]
    list_filter = ["typ", "status"]
    readonly_fields = [
        "erstellt_am",
        "abgeschlossen_am",
        "dateiname",
        "dateigroesse_bytes",
        "tabellen_anzahl",
        "zeilen_gesamt",
        "fehler_meldung",
    ]
