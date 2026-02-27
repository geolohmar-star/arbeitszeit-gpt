import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Feier(models.Model):
    """Eine Veranstaltung (Sommerfest, Weihnachtsfeier, Teamausflug etc.).

    Zeitgutschrift wird als Sammelliste erstellt (nicht als Einzeleintraege).
    Vorbereitungsteam hat eigene Stunden und eigenen Faktor.
    """

    ART_CHOICES = [
        ("sommerfest", "Sommerfest"),
        ("weihnachtsfeier", "Weihnachtsfeier"),
        ("teamausflug", "Teamausflug"),
        ("jubilaeum", "Jubilaeum"),
        ("sonstiges", "Sonstiges"),
    ]

    REICHWEITE_CHOICES = [
        ("abteilung", "Abteilung"),
        ("bereich", "Bereich"),
        ("unternehmen", "Unternehmen"),
    ]

    STATUS_CHOICES = [
        ("geplant", "Geplant"),
        ("anmeldung_offen", "Anmeldung offen"),
        ("anmeldung_geschlossen", "Anmeldung geschlossen"),
        ("abgeschlossen", "Abgeschlossen"),
        ("storniert", "Storniert"),
    ]

    # Grunddaten
    abteilung = models.ForeignKey(
        "hr.Abteilung",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="veranstaltungen",
        verbose_name="Abteilung",
    )
    anmeldeschluss = models.DateField(
        null=True,
        blank=True,
        verbose_name="Anmeldeschluss",
    )
    art = models.CharField(
        max_length=30,
        choices=ART_CHOICES,
        default="sonstiges",
        verbose_name="Art der Veranstaltung",
    )
    bereich = models.ForeignKey(
        "hr.Bereich",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="veranstaltungen",
        verbose_name="Bereich",
    )
    datum = models.DateField(verbose_name="Datum")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_veranstaltungen",
        verbose_name="Erstellt von",
    )
    ort = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Ort",
    )
    reichweite = models.CharField(
        max_length=20,
        choices=REICHWEITE_CHOICES,
        default="abteilung",
        verbose_name="Reichweite",
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="geplant",
        verbose_name="Status",
    )
    titel = models.CharField(max_length=200, verbose_name="Titel")
    uhrzeit_bis = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Uhrzeit bis",
    )
    uhrzeit_von = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Uhrzeit von",
    )
    verantwortlicher = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verantwortete_veranstaltungen",
        verbose_name="Verantwortlicher",
    )

    # Zeitgutschrift Teilnehmer
    gutschrift_faktor = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        verbose_name="Gutschrift-Faktor (Teilnehmer)",
        help_text="Beispiel: 0.5 = halbe Vergütung der Veranstaltungsdauer",
    )
    gutschrift_stunden = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Gutschrift-Stunden (Teilnehmer)",
        help_text="Stunden die als Zeitgutschrift angerechnet werden.",
    )

    # Zeitgutschrift Vorbereitungsteam (eigene Berechnung)
    vorbereitung_faktor = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        verbose_name="Faktor (Vorbereitungsteam)",
    )
    vorbereitung_stunden = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Stunden (Vorbereitungsteam)",
        help_text="Separate Stunden für das Vorbereitungsteam.",
    )

    class Meta:
        ordering = ["-datum", "titel"]
        verbose_name = "Veranstaltung"
        verbose_name_plural = "Veranstaltungen"

    def __str__(self):
        return f"{self.titel} ({self.datum})"

    @property
    def gutschrift_teilnehmer_gesamt(self):
        """Zeitgutschrift pro Teilnehmer (Stunden × Faktor)."""
        return self.gutschrift_stunden * self.gutschrift_faktor

    @property
    def gutschrift_vorbereitung_gesamt(self):
        """Zeitgutschrift pro Vorbereitungsmitglied (Stunden × Faktor)."""
        return self.vorbereitung_stunden * self.vorbereitung_faktor

    @property
    def anmeldung_offen(self):
        """True wenn Anmeldung moeglich ist."""
        if self.status != "anmeldung_offen":
            return False
        if self.anmeldeschluss and self.anmeldeschluss < timezone.localdate():
            return False
        return True


class FeierteilnahmeAnmeldung(models.Model):
    """Anmeldung eines Mitarbeiters zu einer Veranstaltung."""

    feier = models.ForeignKey(
        Feier,
        on_delete=models.CASCADE,
        related_name="anmeldungen",
        verbose_name="Veranstaltung",
    )
    ist_gast = models.BooleanField(
        default=False,
        verbose_name="Gast",
        help_text="Externer Gast (kein Mitarbeiter).",
    )
    ist_vorbereitungsteam = models.BooleanField(
        default=False,
        verbose_name="Vorbereitungsteam",
    )
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.CASCADE,
        related_name="veranstaltungsanmeldungen",
        verbose_name="Mitarbeiter",
    )
    angemeldet_am = models.DateTimeField(auto_now_add=True)
    teilnahme_bestaetigt = models.BooleanField(
        default=False,
        verbose_name="Teilnahme bestaetigt",
    )
    bestaetigt_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bestaetigt am",
    )
    bestaetigt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bestaetigte_anmeldungen",
        verbose_name="Bestaetigt von",
    )
    bemerkung = models.TextField(
        blank=True,
        verbose_name="Bemerkung",
    )

    class Meta:
        ordering = ["feier", "mitarbeiter"]
        unique_together = ["feier", "mitarbeiter"]
        verbose_name = "Teilnahmeanmeldung"
        verbose_name_plural = "Teilnahmeanmeldungen"

    def __str__(self):
        return f"{self.mitarbeiter} @ {self.feier}"

    @property
    def gutschrift_stunden(self):
        """Berechnet die Zeitgutschrift fuer diese Anmeldung."""
        if self.ist_vorbereitungsteam:
            return self.feier.gutschrift_vorbereitung_gesamt
        return self.feier.gutschrift_teilnehmer_gesamt


class FeierteilnahmeGutschrift(models.Model):
    """Sammeldokument fuer die Zeitgutschrift einer Veranstaltung.

    Wird vom Zeiterfassungsteam genehmigt und abgearbeitet.
    Enthaelt alle bestaetigen Teilnehmer als PDF-Sammelliste.
    """

    STATUS_CHOICES = [
        ("entwurf", "Entwurf"),
        ("eingereicht", "Eingereicht"),
        ("bearbeitet", "Bearbeitet"),
        ("abgelehnt", "Abgelehnt"),
    ]

    eingereicht_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Eingereicht am",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_gutschriften",
        verbose_name="Erstellt von",
    )
    feier = models.OneToOneField(
        Feier,
        on_delete=models.CASCADE,
        related_name="gutschrift_dokument",
        verbose_name="Veranstaltung",
    )
    bemerkung = models.TextField(
        blank=True,
        verbose_name="Bemerkung",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="entwurf",
        verbose_name="Status",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Zeitgutschrift-Sammelliste"
        verbose_name_plural = "Zeitgutschrift-Sammellisten"

    def __str__(self):
        return f"Gutschrift: {self.feier}"

    def teilnehmer_bestaetigt(self):
        """Gibt alle bestaetigten Teilnehmer zurueck (kein Vorbereitungsteam)."""
        return self.feier.anmeldungen.filter(
            teilnahme_bestaetigt=True,
            ist_vorbereitungsteam=False,
        ).select_related("mitarbeiter", "mitarbeiter__stelle")

    def vorbereitungsteam_bestaetigt(self):
        """Gibt alle bestaetigten Vorbereitungsmitglieder zurueck."""
        return self.feier.anmeldungen.filter(
            teilnahme_bestaetigt=True,
            ist_vorbereitungsteam=True,
        ).select_related("mitarbeiter", "mitarbeiter__stelle")
