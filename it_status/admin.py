from django.contrib import admin

from .models import ITSystem, ITStatusMeldung, ITWartung


class ITStatusMeldungInline(admin.TabularInline):
    model = ITStatusMeldung
    extra = 0
    readonly_fields = ["erstellt_am", "erstellt_von"]
    fields = ["status", "titel", "beschreibung", "geloest_am", "erstellt_am", "erstellt_von"]


class ITWartungInline(admin.TabularInline):
    model = ITWartung
    extra = 0
    readonly_fields = ["erstellt_am", "erstellt_von"]
    fields = ["titel", "start", "ende", "beschreibung", "erstellt_am", "erstellt_von"]


@admin.register(ITSystem)
class ITSystemAdmin(admin.ModelAdmin):
    list_display  = ["bezeichnung", "status", "ping_url", "reihenfolge", "aktiv"]
    list_editable = ["status", "reihenfolge", "aktiv"]
    list_filter   = ["status", "aktiv"]
    search_fields = ["bezeichnung"]
    inlines       = [ITStatusMeldungInline, ITWartungInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk:
                instance.erstellt_von = request.user
            instance.save()
        formset.save_m2m()


@admin.register(ITStatusMeldung)
class ITStatusMeldungAdmin(admin.ModelAdmin):
    list_display    = ["system", "status", "titel", "erstellt_am", "geloest_am"]
    list_filter     = ["status", "system"]
    readonly_fields = ["erstellt_am", "erstellt_von"]
    search_fields   = ["titel", "beschreibung"]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.erstellt_von = request.user
        # Systemstatus beim Speichern einer Meldung automatisch aktualisieren
        obj.system.status = obj.status
        obj.system.save(update_fields=["status"])
        super().save_model(request, obj, form, change)


@admin.register(ITWartung)
class ITWartungAdmin(admin.ModelAdmin):
    list_display    = ["system", "titel", "start", "ende", "erstellt_von"]
    list_filter     = ["system"]
    readonly_fields = ["erstellt_am", "erstellt_von"]
    search_fields   = ["titel"]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)
