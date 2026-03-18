from django.contrib import admin

from .models import Brandalarm, BranderkunderToken, SicherheitsAlarm


@admin.register(SicherheitsAlarm)
class SicherheitsAlarmAdmin(admin.ModelAdmin):
    list_display = ["typ", "ort", "status", "ausgeloest_von", "erstellt_am"]
    list_filter = ["typ", "status"]
    readonly_fields = [
        "ausgeloest_von",
        "erstellt_am",
        "geschlossen_am",
        "geschlossen_von",
    ]


class BranderkunderTokenInline(admin.TabularInline):
    model = BranderkunderToken
    extra = 0
    readonly_fields = ["token", "erkunder", "status", "ort_praezise", "matrix_dm_room_id"]
    can_delete = False


@admin.register(Brandalarm)
class BrandalarmAdmin(admin.ModelAdmin):
    list_display = [
        "pk", "ort", "melder_anzahl", "status", "gemeldet_von",
        "security_bestaetigt_von", "erstellt_am",
    ]
    list_filter = ["status"]
    readonly_fields = [
        "gemeldet_von", "erstellt_am",
        "security_bestaetigt_von", "security_bestaetigt_am",
        "geschlossen_von", "geschlossen_am",
    ]
    inlines = [BranderkunderTokenInline]


@admin.register(BranderkunderToken)
class BranderkunderTokenAdmin(admin.ModelAdmin):
    list_display = ["pk", "brandalarm", "erkunder", "status", "ort_praezise"]
    list_filter = ["status"]
    readonly_fields = ["token", "erkunder", "brandalarm", "matrix_dm_room_id"]
