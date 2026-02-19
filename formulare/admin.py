from django.contrib import admin

from formulare.models import AenderungZeiterfassung, ZAGAntrag, ZAGStorno


@admin.register(AenderungZeiterfassung)
class AenderungZeiterfassungAdmin(admin.ModelAdmin):
    list_display = ["get_betreff", "antragsteller", "status", "erstellt_am"]
    list_filter = ["status", "art"]
    search_fields = [
        "antragsteller__vorname",
        "antragsteller__nachname",
        "antragsteller__personalnummer",
    ]


@admin.register(ZAGAntrag)
class ZAGAntragAdmin(admin.ModelAdmin):
    list_display = ["get_betreff", "antragsteller", "status", "erstellt_am"]
    list_filter = ["status"]
    search_fields = [
        "antragsteller__vorname",
        "antragsteller__nachname",
        "antragsteller__personalnummer",
    ]


@admin.register(ZAGStorno)
class ZAGStornoAdmin(admin.ModelAdmin):
    list_display = ["get_betreff", "antragsteller", "status", "erstellt_am"]
    list_filter = ["status"]
    search_fields = [
        "antragsteller__vorname",
        "antragsteller__nachname",
        "antragsteller__personalnummer",
    ]
