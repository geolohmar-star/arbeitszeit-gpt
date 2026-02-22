from django.contrib import admin

from .models import (
    Abteilung,
    Bereich,
    HierarchieSnapshot,
    HRMitarbeiter,
    OrgEinheit,
    Projektgruppe,
    Stelle,
    Team,
)


@admin.register(Bereich)
class BereichAdmin(admin.ModelAdmin):
    list_display = ["name", "kuerzel"]
    search_fields = ["name"]


@admin.register(Abteilung)
class AbteilungAdmin(admin.ModelAdmin):
    list_display = ["name", "kuerzel", "bereich"]
    list_filter = ["bereich"]
    search_fields = ["name"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "abteilung"]
    list_filter = ["abteilung__bereich", "abteilung"]
    search_fields = ["name"]


@admin.register(OrgEinheit)
class OrgEinheitAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "bezeichnung", "leitende_stelle", "uebergeordnet", "ist_reserviert", "stellen_anzahl"]
    list_filter = ["ist_reserviert"]
    search_fields = ["kuerzel", "bezeichnung"]
    autocomplete_fields = ["leitende_stelle", "uebergeordnet"]

    def has_delete_permission(self, request, obj=None):
        """Reservierte Einheiten koennen nicht geloescht werden."""
        if obj is not None and obj.ist_reserviert:
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        """Reservierte Einheiten: nur Superuser darf kuerzel und ist_reserviert aendern."""
        return super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        """Kuerzel und ist_reserviert bei reservierten Einheiten sperren."""
        if obj is not None and obj.ist_reserviert and not request.user.is_superuser:
            return ["kuerzel", "ist_reserviert"]
        return []

    @admin.display(description="Stellen")
    def stellen_anzahl(self, obj):
        """Zaehlt die verknuepften Stellen."""
        return obj.stellen.count()


@admin.register(Stelle)
class StelleAdmin(admin.ModelAdmin):
    list_display = [
        "kuerzel",
        "bezeichnung",
        "kategorie",
        "org_einheit",
        "uebergeordnete_stelle",
        "get_ist_besetzt",
        "get_inhaber",
        "get_email",
        "get_geleitete_orgeinheiten",
        "delegiert_an",
    ]
    list_filter = ["org_einheit", "kategorie"]
    search_fields = ["kuerzel", "bezeichnung"]
    readonly_fields = ["get_email", "get_geleitete_orgeinheiten"]
    fieldsets = [
        (
            "Stelle",
            {
                "fields": [
                    "kuerzel",
                    "bezeichnung",
                    "kategorie",
                    "org_einheit",
                    "uebergeordnete_stelle",
                    "get_email",
                ]
            },
        ),
        (
            "Delegation und Kompetenzrahmen",
            {
                "fields": [
                    "delegiert_an",
                    "max_urlaubstage_genehmigung",
                ]
            },
        ),
        (
            "Vertretung (temporaer)",
            {
                "fields": [
                    "vertreten_durch",
                    "vertretung_von",
                    "vertretung_bis",
                ]
            },
        ),
        (
            "Eskalation",
            {
                "fields": ["eskalation_nach_tagen"]
            },
        ),
    ]

    @admin.display(description="Besetzt", boolean=True)
    def get_ist_besetzt(self, obj):
        """Zeigt ob die Stelle besetzt ist."""
        return obj.ist_besetzt

    @admin.display(description="Inhaber/in")
    def get_inhaber(self, obj):
        """Gibt den aktuellen Inhaber als String zurueck."""
        inhaber = obj.aktueller_inhaber
        if inhaber:
            return inhaber.vollname
        return "–"

    @admin.display(description="E-Mail (Stelle)")
    def get_email(self, obj):
        """Zeigt die berechnete Email-Adresse der Stelle."""
        return obj.email

    @admin.display(description="Leitet OrgEinheiten")
    def get_geleitete_orgeinheiten(self, obj):
        """Zeigt welche OrgEinheiten von dieser Stelle geleitet werden."""
        geleitete = obj.geleitete_orgeinheiten.all()
        if geleitete:
            return ", ".join([org.kuerzel for org in geleitete])
        return "–"


@admin.register(HRMitarbeiter)
class HRMitarbeiterAdmin(admin.ModelAdmin):
    list_display = [
        "nachname",
        "vorname",
        "personalnummer",
        "rolle",
        "stelle",
        "abteilung",
        "team",
    ]
    list_filter = ["rolle", "bereich", "abteilung"]
    search_fields = ["nachname", "vorname", "personalnummer"]
    raw_id_fields = ["vorgesetzter", "stellvertretung_fuer", "user", "stelle"]
    readonly_fields = ["stellen_email_anzeige"]
    fieldsets = [
        (
            "Basisdaten",
            {
                "fields": [
                    "user",
                    "vorname",
                    "nachname",
                    "personalnummer",
                    "email",
                    "eintrittsdatum",
                    "rolle",
                    "stelle",
                    "stellen_email_anzeige",
                ]
            },
        ),
        (
            "Organisationszuordnung (alt)",
            {
                "fields": [
                    "bereich",
                    "abteilung",
                    "team",
                    "vorgesetzter",
                    "stellvertretung_fuer",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    @admin.display(description="E-Mail (Stelle)")
    def stellen_email_anzeige(self, obj):
        """Zeigt die Email-Adresse der zugewiesenen Stelle."""
        return obj.stellen_email or "–"

    def save_model(self, request, obj, form, change):
        """Automatisches Setzen der Email aus der Stelle."""
        # Wenn eine Stelle zugewiesen ist und Email leer ist, dann Stellen-Email uebernehmen
        if obj.stelle and not obj.email:
            obj.email = obj.stelle.email
        super().save_model(request, obj, form, change)


@admin.register(HierarchieSnapshot)
class HierarchieSnapshotAdmin(admin.ModelAdmin):
    list_display = ["created_at", "created_by", "anzahl_orgeinheiten", "anzahl_stellen"]
    list_filter = ["created_at"]
    readonly_fields = ["created_at", "created_by", "snapshot_data"]

    def has_add_permission(self, request):
        """Snapshots werden nur automatisch erstellt."""
        return False

    def has_change_permission(self, request, obj=None):
        """Snapshots sind read-only."""
        return False

    @admin.display(description="OrgEinheiten")
    def anzahl_orgeinheiten(self, obj):
        """Zaehlt OrgEinheiten im Snapshot."""
        return len(obj.snapshot_data.get('orgeinheiten', []))

    @admin.display(description="Stellen")
    def anzahl_stellen(self, obj):
        """Zaehlt Stellen im Snapshot."""
        return len(obj.snapshot_data.get('stellen', []))


@admin.register(Projektgruppe)
class ProjektgruppeAdmin(admin.ModelAdmin):
    """Admin-Interface fuer Projektgruppen."""

    list_display = [
        "kuerzel",
        "name",
        "status",
        "leiter",
        "start_datum",
        "end_datum",
        "anzahl_mitglieder",
        "prioritaet",
    ]
    list_filter = ["status", "start_datum", "prioritaet"]
    search_fields = ["kuerzel", "name", "beschreibung"]
    date_hierarchy = "start_datum"
    filter_horizontal = ["mitglieder"]

    fieldsets = [
        (
            "Projektinformationen",
            {
                "fields": [
                    "kuerzel",
                    "name",
                    "beschreibung",
                    "status",
                    "prioritaet",
                ]
            },
        ),
        (
            "Zeitraum",
            {
                "fields": [
                    "start_datum",
                    "end_datum",
                    "tatsaechliches_end_datum",
                ]
            },
        ),
        (
            "Team",
            {
                "fields": [
                    "leiter",
                    "stellvertreter",
                    "mitglieder",
                ]
            },
        ),
        (
            "Metadaten",
            {
                "fields": [
                    "erstellt_am",
                    "erstellt_von",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    readonly_fields = ["erstellt_am", "erstellt_von"]

    def save_model(self, request, obj, form, change):
        """Setzt erstellt_von automatisch."""
        if not change:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Mitglieder")
    def anzahl_mitglieder(self, obj):
        """Zeigt Anzahl Mitglieder."""
        return obj.mitglieder_anzahl
