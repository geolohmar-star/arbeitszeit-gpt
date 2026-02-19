from django.contrib import admin
from .models import BerechtigungsProtokoll


@admin.register(BerechtigungsProtokoll)
class BerechtigungsProtokollAdmin(admin.ModelAdmin):
    list_display = [
        "zeitpunkt",
        "aktion",
        "permission_codename",
        "ziel_mitarbeiter",
        "berechtigter_user",
        "durchgefuehrt_von",
    ]
    list_filter = ["aktion", "permission_codename"]
    search_fields = [
        "ziel_mitarbeiter__nachname",
        "berechtigter_user__username",
        "durchgefuehrt_von__username",
    ]
    readonly_fields = [
        "aktion",
        "permission_codename",
        "ziel_mitarbeiter",
        "berechtigter_user",
        "durchgefuehrt_von",
        "zeitpunkt",
    ]
