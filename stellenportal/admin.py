from django.contrib import admin

from .models import Ausschreibung, Bewerbung


@admin.register(Ausschreibung)
class AusschreibungAdmin(admin.ModelAdmin):
    list_display = ["titel", "orgeinheit", "beschaeftigungsart", "status", "veroeffentlicht", "erstellt_am"]
    list_filter = ["status", "veroeffentlicht", "beschaeftigungsart", "orgeinheit"]
    search_fields = ["titel", "beschreibung"]
    readonly_fields = ["erstellt_am", "geaendert_am", "erstellt_von"]
    fieldsets = [
        ("Grunddaten", {
            "fields": ["titel", "orgeinheit", "stelle", "beschaeftigungsart", "bewerbungsfrist"],
        }),
        ("Inhalt", {
            "fields": ["beschreibung", "aufgaben", "anforderungen"],
        }),
        ("Veroeffentlichung", {
            "fields": ["status", "veroeffentlicht"],
        }),
        ("Audit", {
            "fields": ["erstellt_von", "erstellt_am", "geaendert_am"],
            "classes": ["collapse"],
        }),
    ]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(Bewerbung)
class BewerbungAdmin(admin.ModelAdmin):
    list_display = ["bewerber", "ausschreibung", "status", "erstellt_am"]
    list_filter = ["status", "ausschreibung__orgeinheit"]
    search_fields = ["bewerber__username", "bewerber__first_name", "bewerber__last_name"]
    readonly_fields = ["erstellt_am", "geaendert_am"]
