from django.contrib import admin

from formulare.models import AenderungZeiterfassung, TeamQueue, ZAGAntrag, ZAGStorno


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


@admin.register(TeamQueue)
class TeamQueueAdmin(admin.ModelAdmin):
    list_display = ["name", "kuerzel", "get_mitglieder_anzahl", "get_queue_anzahl"]
    search_fields = ["name", "kuerzel"]
    filter_horizontal = ["mitglieder"]
    fieldsets = [
        (
            "Basis-Daten",
            {
                "fields": ["name", "kuerzel", "beschreibung"],
            },
        ),
        (
            "Mitglieder",
            {
                "fields": ["mitglieder"],
            },
        ),
    ]

    def get_mitglieder_anzahl(self, obj):
        return obj.mitglieder.count()
    get_mitglieder_anzahl.short_description = "Mitglieder"

    def get_queue_anzahl(self, obj):
        return len(obj.antraege_in_queue())
    get_queue_anzahl.short_description = "In Queue"
