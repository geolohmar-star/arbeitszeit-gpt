from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta






# ============================================
# 1. SCHICHTTYP (braucht nichts)
# ============================================

# ============================================
# 1. SCHICHTTYP
# ============================================
class Schichttyp(models.Model):
    name = models.CharField(max_length=100)
    kuerzel = models.CharField(max_length=10)
    start_zeit = models.TimeField()
    ende_zeit = models.TimeField()
    farbe = models.CharField(max_length=7, default='#6c757d')
    pausenzeit_minuten = models.IntegerField(default=0)
    aktiv = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Schichttyp"
        verbose_name_plural = "Schichttypen"
        ordering = ['start_zeit']
    
    def __str__(self):
        return f"{self.name} ({self.kuerzel})"
    
    @property
    def arbeitszeit_stunden(self):
        start = datetime.combine(datetime.today(), self.start_zeit)
        ende = datetime.combine(datetime.today(), self.ende_zeit)
        if ende < start:
            ende += timedelta(days=1)
        dauer = (ende - start).total_seconds() / 3600
        dauer -= self.pausenzeit_minuten / 60
        return round(dauer, 2)


# ============================================
# 2. SCHICHTPLAN
# ============================================
class Schichtplan(models.Model):
    STATUS_CHOICES = [
        ('entwurf', 'Entwurf'),
        ('zur_genehmigung', 'Zur Genehmigung'),
        ('veroeffentlicht', 'Veröffentlicht'),
        ('archiviert', 'Archiviert'),
    ]

    name = models.CharField(max_length=200)
    start_datum = models.DateField()
    ende_datum = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='entwurf')
    
    wunschperiode = models.ForeignKey(
        'SchichtwunschPeriode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schichtplaene',
        help_text="Wähle die Wunschperiode aus, die als Basis für diesen Plan dient."
    )

    konfiguration = models.ForeignKey(
        'SchichtplanKonfiguration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='schichtplaene',
        help_text="Konfiguration, mit der dieser Plan erstellt wurde (Auto-gesetzt)"
    )

    erstellt_von = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)
    bemerkungen = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Schichtplan"
        verbose_name_plural = "Schichtpläne"
        ordering = ['-start_datum']
    
    def __str__(self):
        return f"{self.name} ({self.start_datum} - {self.ende_datum})"
    
    def clean(self):
        super().clean()
        # 1. Check: Grundlogik Datum
        if self.ende_datum and self.start_datum and self.ende_datum < self.start_datum:
            raise ValidationError("Ende-Datum muss nach Start-Datum liegen.")
        
        # 2. Check: Zusammenhang mit Wunschperiode
        if self.wunschperiode and self.start_datum:
            if self.start_datum.month != self.wunschperiode.fuer_monat.month or \
               self.start_datum.year != self.wunschperiode.fuer_monat.year:
                raise ValidationError(
                    f"Das Startdatum ({self.start_datum.strftime('%m/%Y')}) passt nicht "
                    f"zur gewählten Wunschperiode ({self.wunschperiode.fuer_monat.strftime('%m/%Y')})."
                )

    @property
    def anzahl_tage(self):
        return (self.ende_datum - self.start_datum).days + 1


# ============================================
# 3. SCHICHTWUNSCHPERIODE
# ============================================
class SchichtwunschPeriode(models.Model):
    STATUS_CHOICES = [
        ('vorbereitung', 'In Vorbereitung'),
        ('offen', 'Offen - Wünsche können eingereicht werden'),
        ('geschlossen', 'Geschlossen - Wird geplant'),
        ('genehmigung', 'Wünsche werden genehmigt'),
        ('planung', 'Plan wird generiert'),
        ('veroeffentlicht', 'Plan ist veröffentlicht'),
    ]

    name = models.CharField(max_length=100)
    fuer_monat = models.DateField(help_text="z.B. 2026-03-01")
    eingabe_start = models.DateTimeField()
    eingabe_ende = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='vorbereitung')
    erstellt_von = models.ForeignKey(User, on_delete=models.CASCADE, related_name='erstellte_wunschperioden')
    erstellt_am = models.DateTimeField(auto_now_add=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Schichtwunsch-Periode"
        verbose_name_plural = "Schichtwunsch-Perioden"
        ordering = ['-fuer_monat']

    def __str__(self):
        return f"{self.name} ({self.fuer_monat.strftime('%B %Y')})"
    
    @property
    def ist_offen(self):
        now = timezone.now()
        return self.status == 'offen' and self.eingabe_start <= now <= self.eingabe_ende


# ============================================
# 4. SCHICHTWUNSCH
# ============================================
class Schichtwunsch(models.Model):
    WUNSCH_KATEGORIEN = [
        ('urlaub', '1 - Urlaub'),
        ('kein_tag_aber_nacht', '2 - Kein Tag, aber Nacht möglich'),
        ('keine_nacht_aber_tag', '3 - Keine Nacht, aber Tag möglich'),
        ('tag_bevorzugt', '4 - Tag bevorzugt'),
        ('nacht_bevorzugt', '5 - Nacht bevorzugt'),
        ('gar_nichts', '6 - Gar nichts möglich'),
        ('zusatzarbeit', '7 - Zusatzarbeit'),
        ('ausgleichstag', 'Z-AG Zeitausgleich'),
        ('krank', 'K Krank'),
    ]
    
    periode = models.ForeignKey(SchichtwunschPeriode, on_delete=models.CASCADE, null=True, blank=True)
    mitarbeiter = models.ForeignKey('arbeitszeit.Mitarbeiter', on_delete=models.CASCADE, related_name='schichtwuensche')
    datum = models.DateField()
    wunsch = models.CharField(max_length=30, choices=WUNSCH_KATEGORIEN)
    begruendung = models.TextField(blank=True)
    benoetigt_genehmigung = models.BooleanField(default=False)
    genehmigt = models.BooleanField(default=False)
    ersatz_schichttyp = models.CharField(
        max_length=1,
        choices=[('T', 'Tagschicht'), ('N', 'Nachtschicht')],
        blank=True,
        default=''
    )
    ersatz_bestaetigt = models.BooleanField(default=False)
    ersatz_mitarbeiter = models.ForeignKey(
        'arbeitszeit.Mitarbeiter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ersatz_fuer_wuensche'
    )
    genehmigt_von = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='genehmigte_wuensche')
    genehmigt_am = models.DateTimeField(null=True, blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Schichtwunsch"
        verbose_name_plural = "Schichtwünsche"
        unique_together = [['mitarbeiter', 'datum']]
        ordering = ['datum', 'mitarbeiter']

    def save(self, *args, **kwargs):
        # Keine automatische Genehmigungspflicht mehr
        super().save(*args, **kwargs)


# ============================================
# 5. SCHICHT
# ============================================
class Schicht(models.Model):
    schichtplan = models.ForeignKey(Schichtplan, on_delete=models.CASCADE, related_name='schichten')
    mitarbeiter = models.ForeignKey('arbeitszeit.Mitarbeiter', on_delete=models.CASCADE, related_name='schichten')
    datum = models.DateField()
    schichttyp = models.ForeignKey(Schichttyp, on_delete=models.PROTECT)
    ersatz_markierung = models.BooleanField(default=False)
    abweichende_start_zeit = models.TimeField(null=True, blank=True)
    abweichende_ende_zeit = models.TimeField(null=True, blank=True)
    bemerkungen = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Schicht"
        verbose_name_plural = "Schichten"
        # Ein Mitarbeiter kann nur eine Schicht pro Tag im selben Plan haben
        unique_together = [['schichtplan', 'mitarbeiter', 'datum']]
        ordering = ['datum', 'schichttyp__start_zeit']

    def clean(self):
        super().clean()
        if self.datum < self.schichtplan.start_datum or self.datum > self.schichtplan.ende_datum:
            raise ValidationError("Datum liegt außerhalb des Schichtplan-Zeitraums.")


# ============================================
# 6. SCHICHTTAUSCH
# ============================================
class Schichttausch(models.Model):
    STATUS_CHOICES = [
        ('offen', 'Offen'),
        ('angenommen', 'Angenommen'),
        ('abgelehnt', 'Abgelehnt'),
        ('genehmigt', 'Genehmigt'),
        ('abgebrochen', 'Abgebrochen'),
    ]
    urspruengliche_schicht = models.ForeignKey(Schicht, on_delete=models.CASCADE, related_name='tausch_anfragen')
    angeboten_von = models.ForeignKey('arbeitszeit.Mitarbeiter', on_delete=models.CASCADE, related_name='angebotene_tausche')
    gewuenschter_partner = models.ForeignKey('arbeitszeit.Mitarbeiter', on_delete=models.CASCADE, related_name='erhaltene_tausch_anfragen', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    nachricht = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Schichttausch"
        verbose_name_plural = "Schichttausche"
        ordering = ['-erstellt_am']


# ============================================
# 7. SCHICHTPLAN-ÄNDERUNGSPROTOKOLL (für Rückgängig)
# ============================================
class SchichtplanAenderung(models.Model):
    AKTION_CHOICES = [
        ('angelegt', 'Schicht/Markierung angelegt'),
        ('geloescht', 'Schicht/Markierung gelöscht'),
        ('getauscht', 'Schichten getauscht'),
        ('bearbeitet', 'Schicht bearbeitet'),
    ]
    schichtplan = models.ForeignKey(Schichtplan, on_delete=models.CASCADE, related_name='aenderungsprotokoll')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    zeit = models.DateTimeField(auto_now_add=True)
    aktion = models.CharField(max_length=20, choices=AKTION_CHOICES)
    beschreibung = models.CharField(max_length=400)
    # JSON mit Daten zum Rückgängig-Machen: z.B. {"schicht_id": 1} oder {"schicht1_id": 1, "schicht2_id": 2} oder {"mitarbeiter_id": 1, "datum": "2026-02-15", "schichttyp_id": 1}
    undo_daten = models.JSONField(default=dict, blank=True)
    zurueckgenommen = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Schichtplan-Änderung"
        verbose_name_plural = "Schichtplan-Änderungen"
        ordering = ['-zeit']


# ============================================
# 8. SCHICHTPLAN-SNAPSHOT (Baseline bei Veröffentlichung)
# ============================================
class SchichtplanSnapshot(models.Model):
    schichtplan = models.ForeignKey(
        Schichtplan,
        on_delete=models.CASCADE,
        related_name='snapshots'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Schichtplan-Snapshot"
        verbose_name_plural = "Schichtplan-Snapshots"
        ordering = ['-erstellt_am']

    def __str__(self):
        return f"Snapshot {self.schichtplan.name} ({self.erstellt_am:%d.%m.%Y %H:%M})"


class SchichtplanSnapshotSchicht(models.Model):
    snapshot = models.ForeignKey(
        SchichtplanSnapshot,
        on_delete=models.CASCADE,
        related_name='schichten'
    )
    mitarbeiter = models.ForeignKey('arbeitszeit.Mitarbeiter', on_delete=models.CASCADE)
    datum = models.DateField()
    schichttyp = models.ForeignKey(Schichttyp, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Snapshot-Schicht"
        verbose_name_plural = "Snapshot-Schichten"
        ordering = ['datum', 'schichttyp__start_zeit']


# ============================================
# 9. SCHICHTPLAN-KONFIGURATION
# ============================================
class SchichtplanKonfiguration(models.Model):
    """
    Zentrale Konfiguration für alle Gewichte und Parameter
    des Schichtplan-Generators mit Versionierung zur Rückverfolgbarkeit.
    """

    # === VERSIONIERUNG ===
    version_nummer = models.IntegerField(unique=True, help_text="Auto-inkrementiert bei jeder neuen Config")
    bemerkung = models.TextField(blank=True, help_text="Was wurde geändert? (optional)")
    erstellt_von = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False, related_name='erstellte_konfigurationen')
    aktiv = models.BooleanField(default=False, help_text="Nur die aktive Konfiguration wird für neue Pläne verwendet")

    # === FAIRNESS GEWICHTE (Jahresausgleich) ===
    fairness_weight_tagschichten = models.IntegerField(default=2500, help_text="Tagsschichten-Ausgleich (höher = wichtiger)")
    fairness_weight_nachtschichten = models.IntegerField(default=1500, help_text="Nachtschichten-Ausgleich")
    fairness_weight_wochenenden = models.IntegerField(default=2000, help_text="Wochenend-Ausgleich")

    # === WUNSCH-ERFÜLLUNGS-BONUSE ===
    wunsch_bonus_keine = models.IntegerField(default=5000, help_text="Bonus für 0 Wünsche (Maximum Kooperation)")
    wunsch_bonus_wenige = models.IntegerField(default=3000, help_text="Bonus für wenige Wünsche (1-4)")
    wunsch_bonus_mittel = models.IntegerField(default=1000, help_text="Bonus für mittlere Wünsche (5-14)")
    wunsch_bonus_threshold_wenige = models.IntegerField(default=4, help_text="Threshold für 'wenig' Wünsche")
    wunsch_bonus_threshold_mittel = models.IntegerField(default=14, help_text="Threshold für 'mittel' Wünsche")

    # === WUNSCH-PREFERENCE SCORES ===
    wunsch_tag_bevorzugt = models.IntegerField(default=25000, help_text="Gewicht für 'Tag bevorzugt' Wunsch")
    wunsch_nacht_bevorzugt = models.IntegerField(default=25000, help_text="Gewicht für 'Nacht bevorzugt' Wunsch")
    wunsch_zusatzarbeit = models.IntegerField(default=5000, help_text="Gewicht für 'Zusatzarbeit' Wunsch")
    wunsch_fixe_tagdienste = models.IntegerField(default=30000, help_text="Gewicht für fixe Tagdienst-Wochentage (MA1 Mi, etc.)")

    # === SPECIAL RULES ===
    wockenend_block_strafe = models.IntegerField(default=5000, help_text="MA7: Strafe wenn Nachtdienste nicht in 2er-Blöcken")
    soll_stunden_abweichung_strafe = models.IntegerField(default=2000, help_text="Strafe für Abweichung vom Soll-Stunden-Ziel")
    typ_b_overage_strafe = models.IntegerField(default=2000, help_text="Strafe für Schichten über Target (z.B. >6 Tagdienste)")

    # === TYP B THRESHOLDS ===
    typ_b_min_erforderliche_tage = models.IntegerField(default=8, help_text="Min. verfügbare Tage für Typ B Constraint")
    typ_b_min_tagschichten = models.IntegerField(default=4, help_text="Min. Tagschichten pro Monat (Typ B)")
    typ_b_min_nachtschichten = models.IntegerField(default=4, help_text="Min. Nachtschichten pro Monat (Typ B)")
    typ_b_target_tagschichten = models.IntegerField(default=6, help_text="Soft Target Tagschichten (üb 6 = Strafe)")
    typ_b_target_nachtschichten = models.IntegerField(default=5, help_text="Soft Target Nachtschichten")
    typ_b_max_schichten_bonus = models.IntegerField(default=6, help_text="Über diesen Wert: Strafe pro Schicht")

    # === PRIORITY MULTIPLIKATOREN ===
    priority_multiplier_hoch = models.DecimalField(default=Decimal('1.5'), max_digits=3, decimal_places=2, help_text="High priority: Wünsche werden mit 1.5x gewichtet")
    priority_multiplier_niedrig = models.DecimalField(default=Decimal('0.8'), max_digits=3, decimal_places=2, help_text="Low priority: Wünsche mit 0.8x gewichtet")

    # === SOLVER PARAMETER ===
    solver_timeout_sekunden = models.IntegerField(default=300, help_text="Solver-Timeout in Sekunden (< 60s = suboptimal!)")
    solver_num_workers = models.IntegerField(default=8, help_text="CPU-Worker für Parallelisierung")
    solver_relative_gap_limit = models.DecimalField(default=Decimal('0.01'), max_digits=4, decimal_places=3, help_text="Gap-Limit (0.01 = 1%)")
    solver_linearization_level = models.IntegerField(default=2, help_text="Linearisierungs-Tiefe (0-2)")

    # === ZUSATZDIENSTE ===
    max_zusatzdienste_pro_tag = models.IntegerField(default=2, help_text="Max. Z-Dienste pro Kalendertag")

    # === TAGSCHICHT-BLOCK-PRÄFERENZ ===
    tag_block_3er_strafe = models.IntegerField(
        default=1500,
        verbose_name="Strafe für 3er Tagschicht-Blöcke",
        help_text="Penalty wenn 3 aufeinanderfolgende T-Schichten (z.B. Mo-Di-Mi). Default 1500."
    )
    tag_block_4er_strafe = models.IntegerField(
        default=3000,
        verbose_name="Strafe für 4er+ Tagschicht-Blöcke",
        help_text="Zusatz-Penalty für 4+ aufeinanderfolgende T-Schichten. Default 3000."
    )

    # === VERWALTUNG ===
    erstellt_am = models.DateTimeField(auto_now_add=True, editable=False)
    geaendert_am = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        verbose_name = "Schichtplan-Konfiguration"
        verbose_name_plural = "Schichtplan-Konfigurationen"
        ordering = ['-version_nummer']
        permissions = [
            ('view_config_history', 'Kann Config-Historia anschauen'),
            ('change_scoring_weights', 'Darf Scoring-Gewichte ändern'),
            ('change_solver_parameters', 'Darf Solver-Parameter ändern'),
        ]

    def __str__(self):
        status = "✓ AKTIV" if self.aktiv else "Inaktiv"
        return f"Config v{self.version_nummer} {status} ({self.geaendert_am.strftime('%d.%m.%y %H:%M')})"

    @classmethod
    def get_aktuelle(cls):
        """Gibt die aktive Konfiguration zurück, oder erstellt Defaults"""
        aktive = cls.objects.filter(aktiv=True).first()
        if aktive:
            return aktive
        # Keine aktive Config? Erstelle mit Defaults
        return cls.objects.create(
            version_nummer=(cls.objects.aggregate(models.Max('version_nummer'))['version_nummer__max'] or 0) + 1,
            bemerkung="Auto-erstellt - Defaults",
            aktiv=True
        )

    def save(self, *args, **kwargs):
        """Nur eine Konfiguration darf aktiv sein"""
        if not self.version_nummer:
            # Neue Config: auto-inkrementierte Version
            max_version = SchichtplanKonfiguration.objects.aggregate(models.Max('version_nummer'))['version_nummer__max']
            self.version_nummer = (max_version or 0) + 1

        if self.aktiv:
            # Deaktiviere alle anderen
            SchichtplanKonfiguration.objects.exclude(pk=self.pk).update(aktiv=False)

        super().save(*args, **kwargs)


# ============================================
# 10. REGIONALER FEIERTAG
# ============================================
class RegionalerFeiertag(models.Model):
    """
    Konfigurierbare regionale Feiertage für die Arbeitszeitberechnung.
    Unterstützt sowohl feste Daten als auch Ostern-relative Feiertage.
    """

    TYP_CHOICES = [
        ('fest', 'Festes Datum (Monat + Tag)'),
        ('ostern_relativ', 'Relativ zu Ostern'),
    ]

    REGION_CHOICES = [
        ('all', 'Alle Bundesländer'),
        ('nrw', 'Nordrhein-Westfalen'),
        ('bayern', 'Bayern'),
        ('bw', 'Baden-Württemberg'),
        ('hessen', 'Hessen'),
        ('niedersachsen', 'Niedersachsen'),
    ]

    name = models.CharField(
        max_length=100,
        verbose_name="Feiertag-Name",
        help_text="z.B. 'Rosenmontag', 'Aschermittwoch'"
    )
    typ = models.CharField(
        max_length=20,
        choices=TYP_CHOICES,
        verbose_name="Datum-Typ"
    )
    region = models.CharField(
        max_length=20,
        choices=REGION_CHOICES,
        default='all',
        verbose_name="Region/Bundesland"
    )

    # Für 'fest' Typ (festes Datum)
    monat = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="Monat (1-12)"
    )
    tag = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name="Tag (1-31)"
    )

    # Für 'ostern_relativ' Typ (relativ zu Ostern)
    ostern_offset = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Tage von Osternsonntag",
        help_text="z.B. -48 für Rosenmontag, +39 für Christi Himmelfahrt"
    )

    aktiv = models.BooleanField(
        default=True,
        verbose_name="Aktiv",
        help_text="Inaktive Feiertage werden nicht berücksichtigt"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        verbose_name = "Regionaler Feiertag"
        verbose_name_plural = "Regionale Feiertage"
        ordering = ['region', 'name']
        unique_together = [['name', 'region', 'typ']]

    def __str__(self):
        status = "✓" if self.aktiv else "✗"
        typ_display = dict(self.TYP_CHOICES).get(self.typ, self.typ)
        return f"{status} {self.name} ({self.region}, {typ_display})"

    def clean(self):
        """Validierung: Je nach Typ muss entweder monat+tag oder ostern_offset gesetzt sein"""
        from django.core.exceptions import ValidationError

        if self.typ == 'fest':
            if not self.monat or not self.tag:
                raise ValidationError(
                    "Für feste Feiertage sind Monat und Tag erforderlich."
                )
            if self.ostern_offset is not None:
                raise ValidationError(
                    "Ostern-Offset sollte leer sein für feste Feiertage."
                )
        elif self.typ == 'ostern_relativ':
            if self.ostern_offset is None:
                raise ValidationError(
                    "Für Ostern-relative Feiertage ist der Ostern-Offset erforderlich."
                )
            if self.monat or self.tag:
                raise ValidationError(
                    "Monat und Tag sollten leer sein für Ostern-relative Feiertage."
                )
