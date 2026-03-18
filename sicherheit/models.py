import secrets

from django.contrib.auth.models import User
from django.db import models


class SicherheitsAlarm(models.Model):
    """Sicherheitsalarm – AMOK oder Stiller Alarm."""

    TYP_AMOK = "amok"
    TYP_STILL = "still"
    TYP_CHOICES = [
        (TYP_AMOK, "AMOK-Alarm"),
        (TYP_STILL, "Stiller Alarm"),
    ]

    STATUS_AKTIV = "aktiv"
    STATUS_GESCHLOSSEN = "geschlossen"
    STATUS_CHOICES = [
        (STATUS_AKTIV, "Aktiv"),
        (STATUS_GESCHLOSSEN, "Geschlossen"),
    ]

    ausgeloest_von = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="ausgeloeste_alarme",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geschlossen_am = models.DateTimeField(null=True, blank=True)
    geschlossen_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="geschlossene_alarme",
    )
    notiz = models.TextField(blank=True)
    ort = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_AKTIV
    )
    typ = models.CharField(max_length=20, choices=TYP_CHOICES)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Sicherheitsalarm"
        verbose_name_plural = "Sicherheitsalarme"

    def __str__(self):
        typ_label = "AMOK-Alarm" if self.typ == self.TYP_AMOK else "Stiller Alarm"
        return f"{typ_label} #{self.pk} ({self.status})"


class Brandalarm(models.Model):
    """Brandalarm mit mehrstufiger Verifikationskette.

    Statusmaschine:
      gemeldet      -> 1 Melder, Branderkunder gepingt
      bestaetigung  -> 2. Melder ODER Branderkunder bestaetigt -> Security-Review
      evakuierung   -> Security bestaetigt -> Vollalarm fuer alle
      geschlossen   -> Entwarnung
    """

    STATUS_GEMELDET = "gemeldet"
    STATUS_BESTAETIGUNG = "bestaetigung"
    STATUS_EVAKUIERUNG = "evakuierung"
    STATUS_GESCHLOSSEN = "geschlossen"
    STATUS_CHOICES = [
        (STATUS_GEMELDET, "Gemeldet – Branderkunder unterwegs"),
        (STATUS_BESTAETIGUNG, "Bestaetigung ausstehend – Security-Review"),
        (STATUS_EVAKUIERUNG, "Evakuierung aktiv"),
        (STATUS_GESCHLOSSEN, "Geschlossen / Entwarnung"),
    ]

    BEWERTUNG_POSITIV = "positiv"
    BEWERTUNG_VERBESSERUNG = "verbesserungsbedarf"
    BEWERTUNG_KRITISCH = "kritisch"
    BEWERTUNG_CHOICES = [
        (BEWERTUNG_POSITIV, "Positiv – alles lief korrekt"),
        (BEWERTUNG_VERBESSERUNG, "Verbesserungsbedarf"),
        (BEWERTUNG_KRITISCH, "Kritisch – Massnahmen erforderlich"),
    ]

    erstellt_am = models.DateTimeField(auto_now_add=True)
    gemeldet_von = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="gemeldete_brandalarme",
        verbose_name="Gemeldet von",
    )
    geschlossen_am = models.DateTimeField(null=True, blank=True)
    geschlossen_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="geschlossene_brandalarme",
        verbose_name="Geschlossen von",
    )
    melder_anzahl = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Anzahl Meldungen",
        help_text="Erhoeht sich wenn ein zweiter Nutzer meldet",
    )
    notiz = models.TextField(blank=True, verbose_name="Notiz")
    ort = models.CharField(
        max_length=200,
        verbose_name="Gemeldeter Ort",
        help_text="Vom Melder angegebener oder aus Buero ermittelter Ort",
    )
    ort_praezise = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Praeziser Ort",
        help_text="Vom Branderkunder praezisierter Brandort",
    )
    nachbewertung = models.CharField(
        max_length=30,
        blank=True,
        choices=BEWERTUNG_CHOICES,
        verbose_name="Nachbewertung",
    )
    nachbewertung_erstellt_am = models.DateTimeField(null=True, blank=True)
    nachbewertung_erstellt_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bewertete_brandalarme",
        verbose_name="Nachbewertung erstellt von",
    )
    nachbewertung_text = models.TextField(blank=True, verbose_name="Nachbewertungstext")
    security_bestaetigt_am = models.DateTimeField(null=True, blank=True)
    security_bestaetigt_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bestaetigte_brandalarme",
        verbose_name="Security-Bestaetigung von",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_GEMELDET,
        verbose_name="Status",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Brandalarm"
        verbose_name_plural = "Brandalarme"

    def __str__(self):
        return f"Brandalarm #{self.pk} – {self.ort} ({self.get_status_display()})"

    @property
    def ort_aktuell(self):
        """Gibt den praezisierten Ort zurueck, falls vorhanden, sonst den gemeldeten."""
        return self.ort_praezise or self.ort


class BranderkunderToken(models.Model):
    """Einmaliger Token fuer die tokenbasierte Rueckmeldung eines Branderkunder.

    Jeder Branderkunder erhaelt pro Brandalarm einen eigenen Token-Link.
    Der Link ist ohne Login zugaenglich.
    """

    STATUS_AUSSTEHEND = "ausstehend"
    STATUS_UNTERWEGS = "unterwegs"
    STATUS_AM_ORT = "am_ort"
    STATUS_BESTAETIGT = "bestaetigt"
    STATUS_FEHLALARM = "fehlalarm"
    STATUS_CHOICES = [
        (STATUS_AUSSTEHEND, "Ausstehend"),
        (STATUS_UNTERWEGS, "Bin auf dem Weg"),
        (STATUS_AM_ORT, "Bin am Brandort"),
        (STATUS_BESTAETIGT, "Brand bestaetigt"),
        (STATUS_FEHLALARM, "Kein Brand / Fehlalarm"),
    ]

    brandalarm = models.ForeignKey(
        Brandalarm,
        on_delete=models.CASCADE,
        related_name="erkunder_tokens",
        verbose_name="Brandalarm",
    )
    erkunder = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.CASCADE,
        related_name="brand_tokens",
        verbose_name="Branderkunder/in",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    matrix_dm_room_id = models.CharField(max_length=200, blank=True)
    matrix_dm_since_token = models.CharField(max_length=500, blank=True)
    notiz = models.TextField(
        blank=True,
        verbose_name="Freitext-Meldung",
        help_text="Lagemeldung oder freie Nachricht des Branderkunder",
    )
    ort_praezise = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Wo genau?",
        help_text="Vom Branderkunder gemeldeter praeziser Brandort",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AUSSTEHEND,
    )
    token = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Branderkunder-Token"
        verbose_name_plural = "Branderkunder-Tokens"

    def __str__(self):
        return f"Token {self.erkunder} – {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)
