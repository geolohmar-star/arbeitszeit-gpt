from django.contrib import admin
from .models import Schichttyp, Schichtplan, Schicht, Schichtwunsch, Schichttausch, SchichtplanKonfiguration, RegionalerFeiertag
from arbeitszeit.models import Mitarbeiter


@admin.register(Schichttyp)
class SchichttypAdmin(admin.ModelAdmin):
    list_display = ['name', 'kuerzel', 'start_zeit', 'ende_zeit', 'aktiv']


@admin.register(Schichtplan)
class SchichtplanAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_datum', 'ende_datum', 'status']


@admin.register(Schicht)
class SchichtAdmin(admin.ModelAdmin):
    list_display = ['mitarbeiter', 'datum', 'schichttyp']


@admin.register(Schichtwunsch)
class SchichtwunschAdmin(admin.ModelAdmin):
    list_display = ['mitarbeiter', 'datum']


@admin.register(Schichttausch)
class SchichttauschAdmin(admin.ModelAdmin):
    list_display = ['urspruengliche_schicht', 'status']


@admin.register(SchichtplanKonfiguration)
class SchichtplanKonfigurationAdmin(admin.ModelAdmin):
    """
    Admin-Interface für Schichtplan-Optimierer-Parameter.
    Alle Werte hier beeinflussen die Schichtplanerstellung!

    ⚠️ WARNUNG: Werte unter 1000 können zu Solver-Fehlschlägen führen.
    """

    readonly_fields = ['erstellt_am', 'geaendert_am', 'version_nummer', 'erstellt_von']
    list_display = ['__str__', 'aktiv', 'geaendert_am']
    list_filter = ['aktiv', 'geaendert_am']

    fieldsets = (
        ('⚙️ FAIRNESS - Jahresausgleich zwischen Mitarbeitern', {
            'description': (
                '<strong>Diese Gewichte bestimmen, wie stark Tag-, Nacht- und Wochenend-Schichten '
                'zwischen dem Team ausgeglichen werden.</strong><br><br>'
                '• Höhere Werte = stärkerer Ausgleich<br>'
                '• Recommendation: Tag > Wochenende > Nacht<br>'
                '• Beispiel: 2500 T + 2000 WE + 1500 N bedeutet: Tagschichten am wichtigsten'
            ),
            'fields': (
                'fairness_weight_tagschichten',
                'fairness_weight_wochenenden',
                'fairness_weight_nachtschichten',
            ),
        }),
        ('🎁 WUNSCH-ERFÜLLUNG - Bonuse für fleißige Planer', {
            'description': (
                '<strong>Mitarbeiter, die wenig Wünsche äußern, bekommen Bonus.</strong><br><br>'
                'Dies incentiviert Ko-Operation und macht Planung kalkulierbar.<br>'
                '• <strong>Nicht unter 0 setzen!</strong><br>'
                '• Beispiel: 0 Wünsche → +5000, 1-4 Wünsche → +3000, 5-14 Wünsche → +1000'
            ),
            'fields': (
                'wunsch_bonus_keine',
                'wunsch_bonus_wenige',
                'wunsch_bonus_mittel',
                'wunsch_bonus_threshold_wenige',
                'wunsch_bonus_threshold_mittel',
            ),
        }),
        ('💰 WUNSCH-PREFERENCES - Gewichtung von Wünschen', {
            'description': (
                '<strong>Wenn ein Mitarbeiter einen Wunsch äußert,</strong> wird dieser mit diesen Werten '
                'ins Optimierungsziel eingerechnet.<br><br>'
                '• Höhere Werte = stärkere Beachtung<br>'
                '• "Tag bevorzugt" & "Nacht bevorzugt" sollten gleich sein (~25000)<br>'
                '• <strong>Range: 25000 empfohlen</strong>'
            ),
            'fields': (
                'wunsch_tag_bevorzugt',
                'wunsch_nacht_bevorzugt',
                'wunsch_zusatzarbeit',
                'wunsch_fixe_tagdienste',
            ),
        }),
        ('🚫 SPEZIELLE REGELN - Strafen für Fälle', {
            'description': (
                '<strong>Optionale Strafen für spezifische Situationen:</strong><br><br>'
                '• MA7: Nachtdienste blockweise (Fr+Sa oder Sa+So)<br>'
                '• Abweichung vom Soll-Stunden-Ziel<br>'
                '• Typ B: Zu viele Schichten über Target<br><br>'
                '<strong>Höhere Werte = stärkere Bestrafung</strong>'
            ),
            'fields': (
                'wockenend_block_strafe',
                'soll_stunden_abweichung_strafe',
                'typ_b_overage_strafe',
            ),
        }),
        ('📋 TYP B - Spezialregel für gemischte Schichten', {
            'description': (
                '<strong>Mitarbeiter Typ B müssen mindestens 4T + 4N pro Monat arbeiten.</strong><br><br>'
                'Diese Werte regeln:<br>'
                '• <strong>min_erforderliche_tage:</strong>Min verfügbare Tage um Constraint zu erzwingen<br>'
                '• <strong>min_tagschichten / min_nachtschichten:</strong> Hard Minimums<br>'
                '• <strong>target_tagschichten / target_nachtschichten:</strong> Soft Targets für Strafe<br><br>'
                '<strong>Empfehlung: Min 4, Target 5-6</strong>'
            ),
            'fields': (
                'typ_b_min_erforderliche_tage',
                'typ_b_min_tagschichten',
                'typ_b_min_nachtschichten',
                'typ_b_target_tagschichten',
                'typ_b_target_nachtschichten',
                'typ_b_max_schichten_bonus',
            ),
        }),
        ('🎯 PLANUNGS-PRIORITÄT - Multiplikatoren', {
            'description': (
                '<strong>Multiplikatoren für High & Low Priority Mitarbeiter:</strong><br><br>'
                '• High-Priority (1.5): Wünsche werden mit 1.5x gewichtet (bis 50% Erhöhung)<br>'
                '• Low-Priority (0.8): Wünsche mit 0.8x gewichtet (bis 20% Reduktion)<br><br>'
                '<strong>Range: 0.5 - 2.0 empfohlen</strong>'
            ),
            'fields': (
                'priority_multiplier_hoch',
                'priority_multiplier_niedrig',
            ),
        }),
        ('⚡ SOLVER-ENGINE - Solver-Performance', {
            'description': (
                '<strong>Parameter beeinflussen wie lange und gründlich der Solver sucht.</strong><br><br>'
                '• <strong>timeout_sekunden:</strong> < 60s = suboptimal! 300s (5min) = Goldstandard<br>'
                '• <strong>num_workers:</strong> CPU-Threads (8 = gut ausgelastet)<br>'
                '• <strong>relative_gap_limit:</strong> 0.01 = 1% Optimalitätslücke (gut)<br>'
                '• <strong>linearization_level:</strong> 0-2 (2 = beste Qualität)<br><br>'
                '<strong>⚠️ Zu kurze Timeouts führen zu suboptimalen Lösungen!</strong>'
            ),
            'fields': (
                'solver_timeout_sekunden',
                'solver_num_workers',
                'solver_relative_gap_limit',
                'solver_linearization_level',
            ),
        }),
        ('🔧 ZUSATZDIENSTE (Z)', {
            'description': (
                '<strong>Wie viele Zusatzdienste an einem Tag maximal?</strong><br><br>'
                '• Zu hoch = chaotische Tagesplanung<br>'
                '• Zu niedrig = Soll-Stunden möglicherweise nicht erreichbar<br><br>'
                '<strong>Empfehlung: 2</strong>'
            ),
            'fields': (
                'max_zusatzdienste_pro_tag',
            ),
        }),
        ('🏗️ TAGSCHICHT-BLOCK-PRÄFERENZ', {
            'description': (
                '<strong>Bevorzugt Tagschichten zu 2er-Blöcken statt 3er+</strong><br><br>'
                '• Penalty für 3 aufeinanderfolgende T-Schichten (z.B. Mo-Di-Mi)<br>'
                '• Höhere Penalty für 4er+ Blöcke (z.B. Mo-Di-Mi-Do)<br>'
                '• <strong>Nicht hart erzwungen:</strong> 3er+ OK wenn Solver sonst keine Lösung findet<br><br>'
                '<strong>Beispiel:</strong> 1500 für 3er, 3000 für 4er bedeutet: '
                'Solver bevorzugt viele 2er vor wenigen längeren Blöcken'
            ),
            'fields': (
                'tag_block_3er_strafe',
                'tag_block_4er_strafe',
            ),
        }),
        ('📊 META - Versionierung & Status', {
            'fields': ('version_nummer', 'bemerkung', 'aktiv', 'erstellt_von', 'erstellt_am', 'geaendert_am'),
            'classes': ('collapse',),
            'description': (
                '<strong>Versionskontrolle für diese Konfiguration:</strong><br>'
                '• <strong>version_nummer:</strong> Auto-inkrementiert (unveränderbar)<br>'
                '• <strong>bemerkung:</strong> Was wurde geändert? (Optional)<br>'
                '• <strong>aktiv:</strong> Nur die aktive Config wird für neue Pläne verwendet<br>'
                '• <strong>erstellt_von / erstellt_am:</strong> Audit-Trail'
            ),
        }),
    )

    def has_change_permission(self, request, obj=None):
        """Schichtplaner dürfen Configs ändern (wenn sie Permission haben)"""
        if request.user.is_superuser:
            return True
        return request.user.has_perm('schichtplan.change_schichtplankonfiguration')

    def has_delete_permission(self, request, obj=None):
        """Keine Configs löschen erlaubt - nur deaktivieren!"""
        return False

    def has_add_permission(self, request):
        """Nur Superuser darf neue Configs erstellen (Versionierung!)"""
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        """Speichern + Version + User-Info"""
        if not change:  # Neue Config
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(RegionalerFeiertag)
class RegionalerFeiertagAdmin(admin.ModelAdmin):
    """
    Admin-Interface für konfigurierbare regionale Feiertage.
    Unterstützt sowohl feste Daten als auch Ostern-relative Feiertage.
    """

    list_display = ['name', 'typ', 'region', 'aktiv', 'erstellt_am']
    list_filter = ['region', 'aktiv', 'typ']
    search_fields = ['name']
    readonly_fields = ['erstellt_am']
    ordering = ['region', 'name']

    fieldsets = (
        ('Grunddaten', {
            'fields': ('name', 'region', 'typ', 'aktiv'),
            'description': 'Geben Sie hier den Feiertag und die Region ein.'
        }),
        ('Festes Datum (Für Typ "Festes Datum")', {
            'fields': ('monat', 'tag'),
            'description': 'Nur für Typ "Festes Datum": Monat (1-12) und Tag (1-31). Beispiel: Monat=12, Tag=25 für Weihnachten.',
            'classes': ('collapse',),
        }),
        ('Ostern-Relativ (Für Typ "Relativ zu Ostern")', {
            'fields': ('ostern_offset',),
            'description': 'Nur für Typ "Ostern-relativ": Tage vom Osternsonntag. Beispiele:<br>'
                          '• -48 = Rosenmontag<br>'
                          '• -46 = Aschermittwoch<br>'
                          '• -2 = Karfreitag<br>'
                          '• +1 = Ostermontag<br>'
                          '• +39 = Christi Himmelfahrt<br>'
                          '• +50 = Pfingstmontag<br>'
                          '• +60 = Fronleichnam',
            'classes': ('collapse',),
        }),
        ('Metadaten', {
            'fields': ('erstellt_am',),
            'classes': ('collapse',),
        }),
    )

    def has_delete_permission(self, request, obj=None):
        """Feiertage können gelöscht werden"""
        return True