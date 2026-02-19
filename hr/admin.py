from django.contrib import admin

from .models import Abteilung, Bereich, HRMitarbeiter, OrgEinheit, Stelle, Team


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
    list_display = ["kuerzel", "bezeichnung", "uebergeordnet", "ist_reserviert", "stellen_anzahl"]
    list_filter = ["ist_reserviert"]
    search_fields = ["kuerzel", "bezeichnung"]

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
        "org_einheit",
        "uebergeordnete_stelle",
        "get_ist_besetzt",
        "get_inhaber",
        "get_email",
        "delegiert_an",
    ]
    list_filter = ["org_einheit"]
    search_fields = ["kuerzel", "bezeichnung"]
    readonly_fields = ["get_email"]
    fieldsets = [
        (
            "Stelle",
            {
                "fields": [
                    "kuerzel",
                    "bezeichnung",
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
