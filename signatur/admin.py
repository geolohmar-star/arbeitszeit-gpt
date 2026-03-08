from django.contrib import admin

from .models import MitarbeiterZertifikat, RootCA, SignaturJob, SignaturProtokoll


@admin.register(RootCA)
class RootCAAdmin(admin.ModelAdmin):
    list_display = ["common_name", "organisation", "gueltig_bis", "erstellt_am"]
    readonly_fields = ["erstellt_am", "zertifikat_pem"]


@admin.register(MitarbeiterZertifikat)
class MitarbeiterZertifikatAdmin(admin.ModelAdmin):
    list_display = ["user", "seriennummer", "status", "gueltig_von", "gueltig_bis", "ist_gueltig"]
    list_filter = ["status"]
    search_fields = ["user__username", "user__last_name", "seriennummer"]
    readonly_fields = ["ausgestellt_am", "fingerprint_sha256", "zertifikat_pem"]
    exclude = ["privater_schluessel_pem"]  # Niemals im Admin anzeigen


@admin.register(SignaturJob)
class SignaturJobAdmin(admin.ModelAdmin):
    list_display = ["job_id", "backend", "status", "erstellt_von", "dokument_name", "erstellt_am"]
    list_filter = ["backend", "status"]
    search_fields = ["job_id", "dokument_name"]
    readonly_fields = ["job_id", "erstellt_am", "abgeschlossen_am"]


@admin.register(SignaturProtokoll)
class SignaturProtokollAdmin(admin.ModelAdmin):
    list_display = ["job", "unterzeichner", "signatur_typ", "hash_sha256", "signiert_am"]
    list_filter = ["signatur_typ"]
    search_fields = ["unterzeichner__username", "hash_sha256"]
    readonly_fields = ["signiert_am", "hash_sha256", "signiertes_pdf"]
