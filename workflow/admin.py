from django.contrib import admin
from django.utils.html import format_html
from .models import WorkflowTemplate, WorkflowStep, WorkflowInstance, WorkflowTask, WorkflowTransition


class WorkflowStepInline(admin.TabularInline):
    """Inline fuer Workflow-Schritte innerhalb eines Templates"""
    model = WorkflowStep
    extra = 1
    fields = [
        "reihenfolge",
        "titel",
        "aktion_typ",
        "zustaendig_rolle",
        "zustaendig_stelle",
        "zustaendig_team",
        "frist_tage",
        "ist_parallel",
    ]
    ordering = ["reihenfolge"]


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    """Admin fuer Workflow-Templates"""

    list_display = [
        "name",
        "kategorie",
        "ist_aktiv",
        "ist_graph_workflow",
        "get_anzahl_schritte",
        "get_anzahl_instanzen",
        "version",
        "erstellt_am",
        "erstellt_von",
    ]
    list_filter = ["ist_aktiv", "kategorie", "erstellt_am"]
    search_fields = ["name", "beschreibung"]
    readonly_fields = ["erstellt_am", "aktualisiert_am", "get_anzahl_schritte"]
    inlines = [WorkflowStepInline]

    fieldsets = [
        (
            "Grunddaten",
            {
                "fields": [
                    "name",
                    "beschreibung",
                    "kategorie",
                    "trigger_event",
                    "ist_aktiv",
                    "ist_graph_workflow",
                ]
            },
        ),
        (
            "Versionierung",
            {
                "fields": [
                    "version",
                    "erstellt_von",
                    "erstellt_am",
                    "aktualisiert_am",
                ]
            },
        ),
        (
            "Statistik",
            {
                "fields": ["get_anzahl_schritte"],
            },
        ),
    ]

    def get_anzahl_schritte(self, obj):
        """Anzahl der Schritte im Template"""
        return obj.anzahl_schritte

    get_anzahl_schritte.short_description = "Anzahl Schritte"

    def get_anzahl_instanzen(self, obj):
        """Anzahl der laufenden Instanzen"""
        return obj.instanzen.count()

    get_anzahl_instanzen.short_description = "Instanzen"


@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    """Admin fuer Workflow-Schritte"""

    list_display = [
        "titel",
        "template",
        "reihenfolge",
        "schritt_typ",
        "aktion_typ",
        "zustaendig_rolle",
        "zustaendig_stelle",
        "zustaendig_team",
        "frist_tage",
        "ist_parallel",
    ]
    list_filter = ["aktion_typ", "zustaendig_rolle", "ist_parallel", "template"]
    search_fields = ["titel", "beschreibung"]
    autocomplete_fields = [
        "zustaendig_stelle",
        "zustaendig_org",
        "zustaendig_team",
        "eskalation_an_stelle",
    ]

    fieldsets = [
        (
            "Grunddaten",
            {
                "fields": [
                    "template",
                    "reihenfolge",
                    "schritt_typ",
                    "titel",
                    "beschreibung",
                    "aktion_typ",
                ]
            },
        ),
        (
            "Zustaendigkeit",
            {
                "fields": [
                    "zustaendig_rolle",
                    "zustaendig_stelle",
                    "zustaendig_org",
                    "zustaendig_team",
                ]
            },
        ),
        (
            "Fristen & Ausfuehrung",
            {
                "fields": [
                    "frist_tage",
                    "ist_parallel",
                ]
            },
        ),
        (
            "Bedingung (optional)",
            {
                "fields": [
                    "bedingung_feld",
                    "bedingung_operator",
                    "bedingung_wert",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Eskalation",
            {
                "fields": [
                    "eskalation_nach_tagen",
                    "eskalation_an_stelle",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Automatische Aktion (nur fuer schritt_typ='auto')",
            {
                "fields": [
                    "auto_config",
                ],
                "classes": ["collapse"],
            },
        ),
    ]


@admin.register(WorkflowTransition)
class WorkflowTransitionAdmin(admin.ModelAdmin):
    """Admin fuer Workflow-Uebergaenge (Transitions)"""

    list_display = [
        "id",
        "template",
        "von_schritt",
        "zu_schritt",
        "bedingung_typ",
        "label",
        "prioritaet",
    ]
    list_filter = ["template", "bedingung_typ"]
    search_fields = ["von_schritt__titel", "zu_schritt__titel", "label"]
    autocomplete_fields = ["von_schritt", "zu_schritt"]

    fieldsets = [
        (
            "Basis",
            {
                "fields": [
                    "template",
                    "von_schritt",
                    "zu_schritt",
                    "label",
                    "prioritaet",
                ]
            },
        ),
        (
            "Bedingung",
            {
                "fields": [
                    "bedingung_typ",
                    "bedingung_entscheidung",
                    "bedingung_feld",
                    "bedingung_operator",
                    "bedingung_wert",
                    "bedingung_python_code",
                ],
            },
        ),
    ]


class WorkflowTaskInline(admin.TabularInline):
    """Inline fuer Tasks innerhalb einer Workflow-Instanz"""
    model = WorkflowTask
    extra = 0
    fields = [
        "step",
        "zugewiesen_an_stelle",
        "zugewiesen_an_team",
        "zugewiesen_an_user",
        "status",
        "frist",
        "entscheidung",
    ]
    readonly_fields = ["step", "erstellt_am"]
    can_delete = False


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    """Admin fuer Workflow-Instanzen"""

    list_display = [
        "id",
        "template",
        "get_content_object",
        "status",
        "get_fortschritt",
        "aktueller_schritt",
        "gestartet_am",
        "gestartet_von",
    ]
    list_filter = ["status", "template", "gestartet_am"]
    search_fields = ["id", "template__name"]
    readonly_fields = [
        "content_type",
        "object_id",
        "gestartet_am",
        "gestartet_von",
        "get_content_object",
        "get_fortschritt",
    ]
    inlines = [WorkflowTaskInline]

    fieldsets = [
        (
            "Workflow",
            {
                "fields": [
                    "template",
                    "status",
                    "aktueller_schritt",
                    "get_fortschritt",
                ]
            },
        ),
        (
            "Verknuepftes Objekt",
            {
                "fields": [
                    "content_type",
                    "object_id",
                    "get_content_object",
                ]
            },
        ),
        (
            "Zeitstempel",
            {
                "fields": [
                    "gestartet_am",
                    "gestartet_von",
                    "abgeschlossen_am",
                ]
            },
        ),
    ]

    def get_content_object(self, obj):
        """Zeigt das verknuepfte Objekt an"""
        if obj.content_object:
            return format_html(
                '<a href="{}">{}</a>',
                f"/admin/{obj.content_type.app_label}/{obj.content_type.model}/{obj.object_id}/change/",
                str(obj.content_object),
            )
        return "-"

    get_content_object.short_description = "Verknuepftes Objekt"

    def get_fortschritt(self, obj):
        """Zeigt Fortschritt als Prozent"""
        return f"{obj.fortschritt}%"

    get_fortschritt.short_description = "Fortschritt"


@admin.register(WorkflowTask)
class WorkflowTaskAdmin(admin.ModelAdmin):
    """Admin fuer Workflow-Tasks"""

    list_display = [
        "id",
        "get_workflow",
        "step",
        "zugewiesen_an_stelle",
        "zugewiesen_an_team",
        "zugewiesen_an_user",
        "status",
        "get_status_badge",
        "frist",
        "entscheidung",
    ]
    list_filter = [
        "status",
        "entscheidung",
        "step__aktion_typ",
        "erstellt_am",
        "zugewiesen_an_stelle",
        "zugewiesen_an_team",
    ]
    search_fields = [
        "instance__id",
        "step__titel",
        "zugewiesen_an_user__username",
        "kommentar",
    ]
    readonly_fields = [
        "instance",
        "step",
        "erstellt_am",
        "get_workflow",
        "get_status_badge",
    ]
    autocomplete_fields = ["zugewiesen_an_stelle", "zugewiesen_an_team", "zugewiesen_an_user"]

    fieldsets = [
        (
            "Workflow & Schritt",
            {
                "fields": [
                    "instance",
                    "step",
                    "get_workflow",
                ]
            },
        ),
        (
            "Zuweisung",
            {
                "fields": [
                    "zugewiesen_an_stelle",
                    "zugewiesen_an_team",
                    "zugewiesen_an_user",
                ]
            },
        ),
        (
            "Status & Frist",
            {
                "fields": [
                    "status",
                    "get_status_badge",
                    "frist",
                    "erstellt_am",
                ]
            },
        ),
        (
            "Erledigung",
            {
                "fields": [
                    "entscheidung",
                    "kommentar",
                    "erledigt_am",
                    "erledigt_von",
                ]
            },
        ),
    ]

    def get_workflow(self, obj):
        """Zeigt den Namen des Workflows an"""
        return obj.instance.template.name

    get_workflow.short_description = "Workflow"

    def get_status_badge(self, obj):
        """Zeigt Status als farbiges Badge"""
        colors = {
            "offen": "#FFA500",  # Orange
            "in_bearbeitung": "#0066CC",  # Blau
            "erledigt": "#28A745",  # Gruen
            "abgelehnt": "#DC3545",  # Rot
            "eskaliert": "#6C757D",  # Grau
        }
        color = colors.get(obj.status, "#000000")

        badge_text = "UEBERFAELLIG" if obj.ist_ueberfaellig else obj.get_status_display()
        if obj.ist_ueberfaellig:
            color = "#DC3545"

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            badge_text,
        )

    get_status_badge.short_description = "Status-Badge"
