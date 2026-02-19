from django.conf import settings
from django.db import models
from django.utils import timezone


class Antrag(models.Model):
    """Abstraktes Basis-Model fuer alle Antragsformulare.

    Enthaelt gemeinsame Felder wie Status, Antragsteller und
    Bearbeitungsinformationen. Konkrete Formulare erben davon.
    """

    STATUS_CHOICES = [
        ("beantragt", "Beantragt"),
        ("genehmigt", "Genehmigt"),
        ("abgelehnt", "Abgelehnt"),
    ]

    aktualisiert_am = models.DateTimeField(auto_now=True)
    antragsteller = models.ForeignKey(
        "arbeitszeit.Mitarbeiter",
        on_delete=models.CASCADE,
        related_name="%(class)s_antraege",
    )
    bearbeitet_am = models.DateTimeField(
        null=True,
        blank=True,
    )
    bearbeitet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_bearbeitet",
    )
    bemerkung_bearbeiter = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="beantragt",
    )

    class Meta:
        abstract = True
        ordering = ["-erstellt_am"]

    def __str__(self):
        return (
            f"{self.__class__._meta.verbose_name} "
            f"von {self.antragsteller} ({self.status})"
        )


class AenderungZeiterfassung(Antrag):
    """Antrag auf manuelle Aenderung der Zeiterfassung.

    Unterstuetzt verschiedene Arten von Korrekturen (beruflich unterwegs,
    K-Taste, B-Taste). Weitere Arten koennen ergaenzt werden.
    """

    ART_CHOICES = [
        ("beruflich_unterwegs", "Beruflich unterwegs"),
        ("b_taste", "B-Taste"),
        ("k_taste", "K-Taste"),
    ]

    TERMINAL_CHOICES = [
        ("bedient", "Bedient"),
        ("nicht_bedient", "Nicht bedient"),
    ]

    # Eigene Choices fuer K-Taste (andere Bedeutung als Kommen/Gehen)
    KTASTE_TERMINAL_CHOICES = [
        ("nicht_bedient", "Nicht bedient"),
        ("versehentlich_bedient", "Versehentlich bedient"),
    ]

    # Art der Aenderung
    art = models.CharField(max_length=30, choices=ART_CHOICES, blank=True)

    # Gehen-Felder (fuer beruflich_unterwegs und b_taste)
    gehen_datum = models.DateField(null=True, blank=True)
    gehen_terminal = models.CharField(
        max_length=20,
        choices=TERMINAL_CHOICES,
        blank=True,
    )

    # Kommen-Felder (fuer beruflich_unterwegs und b_taste)
    kommen_datum = models.DateField(null=True, blank=True)
    kommen_terminal = models.CharField(
        max_length=20,
        choices=TERMINAL_CHOICES,
        blank=True,
    )

    # K-Taste-Felder (einzelnes Datum ohne Kommen/Gehen)
    ktaste_datum = models.DateField(null=True, blank=True)
    ktaste_terminal = models.CharField(
        max_length=22,
        choices=KTASTE_TERMINAL_CHOICES,
        blank=True,
    )

    # Tageszeiten-Box: vollständiger Tagesablauf mit Pausenzeiten
    tages_datum = models.DateField(null=True, blank=True)
    kommen_zeit = models.TimeField(null=True, blank=True)
    pause_gehen_zeit = models.TimeField(null=True, blank=True)
    pause_kommen_zeit = models.TimeField(null=True, blank=True)
    gehen_zeit = models.TimeField(null=True, blank=True)

    # Samstagsarbeit-Box
    SAMSTAG_ART_CHOICES = [
        ("im_betrieb", "Im Betrieb (automatische Erfassung 06:00 - 18:00)"),
        ("ausserhalb", "Außerhalb des Betriebes"),
        ("dauerfreigabe", "Ich habe eine Dauerfreigabe für Samstagsarbeit"),
    ]

    samstag_art = models.CharField(
        max_length=20,
        choices=SAMSTAG_ART_CHOICES,
        blank=True,
    )
    samstag_beginn = models.TimeField(null=True, blank=True)
    samstag_datum = models.DateField(null=True, blank=True)
    samstag_ende = models.TimeField(null=True, blank=True)
    samstag_freigabe_ab = models.DateField(null=True, blank=True)
    samstag_freigabe_bis = models.DateField(null=True, blank=True)
    samstag_vereinbarungsnummer = models.CharField(
        max_length=50, blank=True
    )

    # Array-Daten aus den dynamischen Zeilen (als JSON gespeichert)
    tausch_daten = models.JSONField(null=True, blank=True)
    zeiten_daten = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Aenderung Zeiterfassung"
        verbose_name_plural = "Aenderungen Zeiterfassung"

    def get_betreff(self):
        """Eindeutige Betreffzeile fuer diesen Antrag.

        Zeitstempel wird in Ortszeit (Europe/Berlin) ausgegeben.
        """
        ma = self.antragsteller
        ortszeit = timezone.localtime(self.erstellt_am)
        zeitstempel = ortszeit.strftime("%Y%m%d-%H%M%S")
        return (
            f"AEM-{ma.vorname} {ma.nachname}"
            f"-{ma.personalnummer}"
            f"-{zeitstempel}"
        )

    def __str__(self):
        return (
            f"Aenderung Zeiterfassung ({self.get_art_display()})"
            f" - {self.antragsteller}"
        )
