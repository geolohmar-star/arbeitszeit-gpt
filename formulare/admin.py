from django.contrib import admin

from formulare.models import AenderungZeiterfassung, TeamQueue, ZAGAntrag, ZAGStorno, Dienstreiseantrag


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


@admin.register(Dienstreiseantrag)
class DienstreiseantragAdmin(admin.ModelAdmin):
    list_display = [
        "get_betreff",
        "antragsteller",
        "ziel",
        "von_datum",
        "bis_datum",
        "geschaetzte_kosten",
        "status",
        "get_workflow_status",
        "erstellt_am",
    ]
    list_filter = ["status", "erstellt_am"]
    search_fields = [
        "antragsteller__vorname",
        "antragsteller__nachname",
        "antragsteller__personalnummer",
        "ziel",
    ]
    readonly_fields = ["workflow_instance", "einladungscode", "erstellt_am"]

    fieldsets = [
        (
            "Antragsteller",
            {
                "fields": ["antragsteller", "status"],
            },
        ),
        (
            "Reisedaten",
            {
                "fields": [
                    "von_datum",
                    "bis_datum",
                    "ziel",
                    "zweck",
                    "geschaetzte_kosten",
                ],
            },
        ),
        (
            "Workflow",
            {
                "fields": ["workflow_instance"],
            },
        ),
        (
            "Einladungscode",
            {
                "fields": ["einladungscode"],
                "classes": ["collapse"],
            },
        ),
        (
            "Zeitstempel",
            {
                "fields": ["erstellt_am"],
            },
        ),
    ]

    def get_workflow_status(self, obj):
        if obj.workflow_instance:
            return f"{obj.workflow_instance.get_status_display()} ({obj.workflow_instance.fortschritt}%)"
        return "-"
    get_workflow_status.short_description = "Workflow-Status"
