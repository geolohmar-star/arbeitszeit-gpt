from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
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
