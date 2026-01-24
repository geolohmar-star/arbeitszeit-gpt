# arbeitszeit/admin.py - KORRIGIERTE VERSION

from django.contrib import admin
from .models import (
    Mitarbeiter, 
    Arbeitszeitvereinbarung, 
    Tagesarbeitszeit,
    ArbeitszeitHistorie, 
    Urlaubsanspruch, 
    Zeiterfassung
)

@admin.register(Mitarbeiter)
class MitarbeiterAdmin(admin.ModelAdmin):
    list_display = ['personalnummer', 'vollname', 'abteilung', 'standort', 'rolle', 'aktiv']
    list_filter = ['aktiv', 'standort', 'rolle', 'abteilung']
    search_fields = ['personalnummer', 'vorname', 'nachname', 'abteilung']
    
    fieldsets = (
        ('Persönliche Daten', {
            'fields': ('user', 'personalnummer', 'vorname', 'nachname')
        }),
        ('Firmendaten', {
            'fields': ('abteilung', 'standort', 'eintrittsdatum', 'aktiv')
        }),
        ('Berechtigungen', {
            'fields': ('rolle',),
            'description': 'Rolle bestimmt Zugriff auf Verwaltungsfunktionen'
        }),
    )


class TagesarbeitszeitInline(admin.TabularInline):
    model = Tagesarbeitszeit
    extra = 0
    fields = ['wochentag', 'zeitwert', 'formatierte_zeit']
    readonly_fields = ['formatierte_zeit']


@admin.register(Arbeitszeitvereinbarung)
class ArbeitszeitvereinbarungAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'get_mitarbeiter', 
        'antragsart', 
        'arbeitszeit_typ',
        'wochenstunden',
        'status', 
        'gueltig_ab',
        'gueltig_bis'
    ]
    list_filter = ['status', 'antragsart', 'arbeitszeit_typ', 'telearbeit']
    search_fields = [
        'mitarbeiter__vorname', 
        'mitarbeiter__nachname', 
        'mitarbeiter__personalnummer'
    ]
    date_hierarchy = 'gueltig_ab'
    
    fieldsets = (
        ('Mitarbeiter', {
            'fields': ('mitarbeiter',)
        }),
        ('Vereinbarung', {
            'fields': (
                'antragsart',
                'arbeitszeit_typ',
                'wochenstunden',
                'gueltig_ab',
                'gueltig_bis',
                'telearbeit'
            )
        }),
        ('Status', {
            'fields': (
                'status',
                'genehmigt_von',
                'genehmigt_am'
            )
        }),
        ('Beendigung', {
            'fields': (
                'beendigung_beantragt',
                'beendigung_datum'
            ),
            'classes': ('collapse',)
        }),
        ('Notizen', {
            'fields': ('bemerkungen',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['genehmigt_am']
    inlines = [TagesarbeitszeitInline]
    
    def get_mitarbeiter(self, obj):
        """Sichere Anzeige des Mitarbeiters"""
        if obj.mitarbeiter:
            return obj.mitarbeiter.vollname
        return '-'
    get_mitarbeiter.short_description = 'Mitarbeiter'
    get_mitarbeiter.admin_order_field = 'mitarbeiter__nachname'


@admin.register(Tagesarbeitszeit)
class TagesarbeitszeitAdmin(admin.ModelAdmin):
    list_display = ['vereinbarung', 'wochentag', 'formatierte_zeit']
    list_filter = ['wochentag']
    search_fields = ['vereinbarung__mitarbeiter__nachname']


@admin.register(ArbeitszeitHistorie)
class ArbeitszeitHistorieAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'get_mitarbeiter',
        'aenderung_am',
        'alter_status',
        'neuer_status',
        'get_geaendert_von'
    ]
    list_filter = ['alter_status', 'neuer_status', 'aenderung_am']
    search_fields = [
        'vereinbarung__mitarbeiter__vorname',
        'vereinbarung__mitarbeiter__nachname'
    ]
    date_hierarchy = 'aenderung_am'
    readonly_fields = ['aenderung_am']
    
    def get_mitarbeiter(self, obj):
        """Sichere Anzeige des Mitarbeiters"""
        if obj.vereinbarung and obj.vereinbarung.mitarbeiter:
            return obj.vereinbarung.mitarbeiter.vollname
        return '-'
    get_mitarbeiter.short_description = 'Mitarbeiter'
    
    def get_geaendert_von(self, obj):
        """Sichere Anzeige des ändernden Users"""
        if obj.aenderung_durch:
            return obj.aenderung_durch.get_full_name() or obj.aenderung_durch.username
        return '-'
    get_geaendert_von.short_description = 'Geändert von'


@admin.register(Urlaubsanspruch)
class UrlaubsanspruchAdmin(admin.ModelAdmin):
    list_display = [
        'get_mitarbeiter',
        'jahr',
        'jahresurlaubstage_anteilig',
        'genommene_urlaubstage',
        'resturlaubstage'
    ]
    list_filter = ['jahr']
    search_fields = ['mitarbeiter__vorname', 'mitarbeiter__nachname']
    
    def get_mitarbeiter(self, obj):
        """Sichere Anzeige des Mitarbeiters"""
        if obj.mitarbeiter:
            return obj.mitarbeiter.vollname
        return '-'
    get_mitarbeiter.short_description = 'Mitarbeiter'
    get_mitarbeiter.admin_order_field = 'mitarbeiter__nachname'


@admin.register(Zeiterfassung)
class ZeiterfassungAdmin(admin.ModelAdmin):
    list_display = [
        'get_mitarbeiter',
        'datum',
        'arbeitsbeginn',
        'arbeitsende',
        'arbeitszeit_formatiert',
        'art'
    ]
    list_filter = ['art', 'datum']
    search_fields = ['mitarbeiter__vorname', 'mitarbeiter__nachname']
    date_hierarchy = 'datum'
    
    fieldsets = (
        ('Mitarbeiter & Datum', {
            'fields': ('mitarbeiter', 'datum')
        }),
        ('Arbeitszeit', {
            'fields': (
                'arbeitsbeginn',
                'arbeitsende',
                'pause_minuten',
                'arbeitszeit_minuten'
            )
        }),
        ('Art & Bemerkung', {
            'fields': ('art', 'bemerkung')
        }),
    )
    
    readonly_fields = ['arbeitszeit_minuten']
    
    def get_mitarbeiter(self, obj):
        """Sichere Anzeige des Mitarbeiters"""
        if obj.mitarbeiter:
            return obj.mitarbeiter.vollname
        return '-'
    get_mitarbeiter.short_description = 'Mitarbeiter'
    get_mitarbeiter.admin_order_field = 'mitarbeiter__nachname'
