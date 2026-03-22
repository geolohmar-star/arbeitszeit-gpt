from django.contrib import admin

from .models import FeldGruppe, FormularEintrag, FormularSchema


@admin.register(FeldGruppe)
class FeldGruppeAdmin(admin.ModelAdmin):
    list_display = ["name", "erstellt_von", "erstellt_am", "geaendert_am"]
    search_fields = ["name", "beschreibung"]


@admin.register(FormularSchema)
class FormularSchemaAdmin(admin.ModelAdmin):
    list_display = ["name", "aktiv", "erstellt_von", "erstellt_am", "geaendert_am"]
    list_filter = ["aktiv"]
    search_fields = ["name", "beschreibung"]


@admin.register(FormularEintrag)
class FormularEintragAdmin(admin.ModelAdmin):
    list_display = ["schema", "eingereicht_von", "eingereicht_am", "status"]
    list_filter = ["schema", "status"]
    search_fields = ["eingereicht_von__username"]
