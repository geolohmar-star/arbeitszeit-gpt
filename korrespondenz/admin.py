from django.contrib import admin

from .models import Briefvorlage, Briefvorgang


@admin.register(Briefvorlage)
class BriefvorlageAdmin(admin.ModelAdmin):
    list_display  = ["titel", "ist_aktiv", "ist_standard", "erstellt_am", "erstellt_von"]
    list_filter   = ["ist_aktiv", "ist_standard"]
    search_fields = ["titel", "beschreibung"]
    readonly_fields = ["erstellt_am", "erstellt_von"]
    fieldsets = [
        (None, {"fields": ["titel", "beschreibung", "ist_aktiv", "ist_standard"]}),
        ("Standard-Absender (wird beim Erstellen eines Briefs vorbelegt)", {
            "fields": [
                "default_absender_name",
                "default_absender_strasse",
                "default_absender_ort",
                "default_absender_telefon",
                "default_absender_email",
                "default_ort",
                "default_grussformel",
            ],
            "description": (
                "Diese Werte werden automatisch in das Formular eingetragen, "
                "wenn der Nutzer diese Vorlage auswaehlt. "
                "Der Nutzer kann sie jederzeit ueberschreiben."
            ),
        }),
        ("Fusszeile (erscheint auf jeder Seite unten im Brief)", {
            "fields": [
                "fusszeile_firmenname",
                "fusszeile_telefon",
                "fusszeile_telefax",
                "fusszeile_email",
                "fusszeile_internet",
            ],
            "description": (
                "Diese Werte erscheinen in der Fusszeile jeder Seite des Briefs. "
                "Nach dem Aendern hier muss die Vorlage neu generiert werden: "
                "python manage.py erstelle_briefvorlage_din5008 --ueberschreiben"
            ),
        }),
        ("Metadaten", {"fields": ["erstellt_am", "erstellt_von"]}),
    ]


@admin.register(Briefvorgang)
class BriefvorgangAdmin(admin.ModelAdmin):
    list_display  = ["datum", "betreff", "empfaenger_name", "status", "erstellt_von", "erstellt_am"]
    list_filter   = ["status"]
    search_fields = ["betreff", "empfaenger_name", "absender_name"]
    readonly_fields = ["erstellt_am", "geaendert_am", "erstellt_von", "version"]
