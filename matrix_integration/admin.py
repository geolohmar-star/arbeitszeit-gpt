from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import JitsiRaum, MatrixRaum, SitzungsKalender, TeilnehmerTemplate


def matrix_passwort_zuruecksetzen(modeladmin, request, queryset):
    """Admin-Aktion: Matrix-Passwort auf Standardpasswort zuruecksetzen."""
    from matrix_integration.management.commands.matrix_passwort_setzen import (
        STANDARD_PASSWORT,
    )
    from matrix_integration.synapse_service import setze_matrix_passwort

    ok = 0
    fehler = 0
    for user in queryset:
        if setze_matrix_passwort(user.username, STANDARD_PASSWORT):
            ok += 1
        else:
            fehler += 1
            messages.error(
                request,
                f"Matrix-Passwort fuer '{user.username}' konnte nicht gesetzt werden "
                "(MATRIX_ADMIN_TOKEN konfiguriert?).",
            )

    if ok:
        messages.success(
            request,
            f"Matrix-Passwort fuer {ok} Benutzer auf '{STANDARD_PASSWORT}' zurueckgesetzt.",
        )


matrix_passwort_zuruecksetzen.short_description = (
    "Matrix-Passwort zuruecksetzen (hrmitarbeiter2026)"
)


admin.site.unregister(User)


@admin.register(User)
class UserMitMatrixAdmin(UserAdmin):
    actions = list(UserAdmin.actions or []) + [matrix_passwort_zuruecksetzen]


@admin.register(JitsiRaum)
class JitsiRaumAdmin(admin.ModelAdmin):
    list_display = ["name", "raum_slug", "org_einheit", "ist_aktiv"]
    list_filter = ["ist_aktiv"]
    search_fields = ["name", "raum_slug"]


@admin.register(TeilnehmerTemplate)
class TeilnehmerTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "typ", "org_einheit"]
    list_filter = ["typ"]
    search_fields = ["name"]
    filter_horizontal = ["mitglieder"]


@admin.register(MatrixRaum)
class MatrixRaumAdmin(admin.ModelAdmin):
    list_display = ["name", "typ", "ping_typ", "ist_aktiv", "room_id"]
    list_filter = ["typ", "ping_typ", "ist_aktiv"]
    search_fields = ["name", "room_id", "room_alias"]
    fieldsets = [
        (None, {"fields": ["name", "typ", "beschreibung", "ist_aktiv"]}),
        ("Matrix-Verbindung", {"fields": ["room_id", "room_alias", "element_url"]}),
        ("Teilnehmer", {"fields": ["org_einheit", "teilnehmer_template"]}),
        ("Ping-Kanal", {"fields": ["ping_typ"], "classes": ["collapse"]}),
    ]


@admin.register(SitzungsKalender)
class SitzungsKalenderAdmin(admin.ModelAdmin):
    list_display = ["name", "matrix_raum", "von", "bis", "ist_wiederkehrend", "ist_aktiv", "naechste_ausfuehrung"]
    list_filter = ["ist_wiederkehrend", "ist_aktiv", "wochentag"]
    search_fields = ["name"]
