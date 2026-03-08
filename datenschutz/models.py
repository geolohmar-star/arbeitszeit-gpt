import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Loeschprotokoll(models.Model):
    """Dauerhaftes Protokoll ueber durchgefuehrte Datenlöschungen.

    Enthaelt ausschliesslich Metadaten – KEINE personenbezogenen Inhalte mehr.
    Nur die Personalnummer und ein anonymisierter Namensstump bleiben als
    Nachweis fuer Aufsichtsbehoerden erhalten (Art. 5 Abs. 2 DSGVO).
    """

    # Minimale Identifikation fuer Nachweiszwecke
    user_id_intern = models.IntegerField(
        verbose_name="Interne User-ID (war)",
        help_text="PK des geloeschten Django-Users – kein FK mehr.",
    )
    personalnummer = models.CharField(
        max_length=20,
        verbose_name="Personalnummer",
    )
    nachname_kuerzel = models.CharField(
        max_length=5,
        verbose_name="Nachname-Kuerzel (3 Zeichen)",
        help_text="Nur erste 3 Buchstaben – zur Identifikation bei Rueckfragen.",
    )
    eintritt_datum = models.DateField(null=True, blank=True)
    austritt_datum = models.DateField(null=True, blank=True)

    # Loeschvorgang
    loeschung_ausgefuehrt_am = models.DateTimeField(default=timezone.now)
    loeschung_durch = models.CharField(
        max_length=200,
        verbose_name="Ausgefuehrt durch",
        help_text="'System (pruefe_loeschfristen)' oder Username des Admins.",
    )

    # Metadaten: was wurde geloescht (Kategorien + Mengen, kein Inhalt)
    kategorien = models.JSONField(
        verbose_name="Geloeschte Datenkategorien",
        help_text="Dict: Kategoriename → Anzahl Datensaetze.",
        default=dict,
    )

    # Gespeichertes Loeschprotokoll-PDF (bleibt dauerhaft)
    protokoll_pdf = models.BinaryField(
        null=True,
        blank=True,
        verbose_name="Protokoll-PDF",
    )

    class Meta:
        ordering = ["-loeschung_ausgefuehrt_am"]
        verbose_name = "Loeschprotokoll"
        verbose_name_plural = "Loeschprotokolle"

    def __str__(self):
        return (
            f"Loeschung {self.nachname_kuerzel}*** / PNr {self.personalnummer} "
            f"am {self.loeschung_ausgefuehrt_am.date()}"
        )
