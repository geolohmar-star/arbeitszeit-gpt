"""
Datensicherungs-Protokoll fuer BSI CON.3.

Jeder Backup- und Restore-Test-Vorgang wird hier protokolliert.
Die Ampel-Logik (gruen/gelb/rot) basiert auf dem Alter des letzten
erfolgreichen Restore-Tests (BSI-Vorgabe: max. 90 Tage).
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

TYP_CHOICES = [
    ("backup", "Datensicherung"),
    ("restore_test", "Restore-Test"),
]

STATUS_CHOICES = [
    ("laufend", "Laufend"),
    ("ok", "Erfolgreich"),
    ("fehler", "Fehlgeschlagen"),
]


class BackupProtokoll(models.Model):
    typ = models.CharField(max_length=20, choices=TYP_CHOICES, verbose_name="Typ")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="laufend", verbose_name="Status"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Gestartet am")
    abgeschlossen_am = models.DateTimeField(
        null=True, blank=True, verbose_name="Abgeschlossen am"
    )
    dateiname = models.CharField(
        max_length=300, blank=True, verbose_name="Dateiname"
    )
    dateigroesse_bytes = models.BigIntegerField(
        null=True, blank=True, verbose_name="Dateigroesse (Bytes)"
    )
    tabellen_anzahl = models.IntegerField(
        null=True, blank=True, verbose_name="Tabellen im Backup"
    )
    zeilen_gesamt = models.BigIntegerField(
        null=True, blank=True, verbose_name="Zeilen gesamt (Restore-Test)"
    )
    fehler_meldung = models.TextField(blank=True, verbose_name="Fehlermeldung")
    erstellt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Ausgeloest von",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Backup-Protokoll"
        verbose_name_plural = "Backup-Protokolle"

    def __str__(self):
        return f"{self.get_typ_display()} – {self.erstellt_am:%d.%m.%Y %H:%M} – {self.get_status_display()}"

    @property
    def dateigroesse_mb(self):
        """Dateigroesse in Megabyte (gerundet auf 2 Stellen)."""
        if self.dateigroesse_bytes:
            return round(self.dateigroesse_bytes / 1024 / 1024, 2)
        return None
