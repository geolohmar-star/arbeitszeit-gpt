from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ITSystem(models.Model):
    """Ein IT-System das ueberwacht wird (z.B. Mailserver, OnlyOffice)."""

    STATUS_OK        = "ok"
    STATUS_WARNUNG   = "warnung"
    STATUS_GESTOERT  = "gestoert"
    STATUS_WARTUNG   = "wartung"

    STATUS_CHOICES = [
        (STATUS_OK,       "Betrieb normal"),
        (STATUS_WARNUNG,  "Warnung"),
        (STATUS_GESTOERT, "Gestoert"),
        (STATUS_WARTUNG,  "Wartung"),
    ]

    bezeichnung  = models.CharField(max_length=100)
    beschreibung = models.TextField(blank=True)
    ping_url     = models.URLField(
        blank=True,
        verbose_name="URL fuer automatischen Ping",
        help_text="Wird alle 5 Minuten per HTTP-GET geprueft. Leer lassen fuer manuellen Status.",
    )
    reihenfolge  = models.PositiveSmallIntegerField(default=10)
    aktiv        = models.BooleanField(default=True)
    status       = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OK
    )

    class Meta:
        ordering = ["reihenfolge", "bezeichnung"]
        verbose_name = "IT-System"
        verbose_name_plural = "IT-Systeme"

    def __str__(self):
        return self.bezeichnung

    @property
    def status_farbe(self):
        return {
            self.STATUS_OK:       "success",
            self.STATUS_WARNUNG:  "warning",
            self.STATUS_GESTOERT: "danger",
            self.STATUS_WARTUNG:  "secondary",
        }.get(self.status, "secondary")

    @property
    def aktuelle_wartung(self):
        jetzt = timezone.now()
        return self.wartungen.filter(ende__gte=jetzt).order_by("start").first()


class ITStatusMeldung(models.Model):
    """Manuelle Statusmeldung eines Admins fuer ein IT-System."""

    system       = models.ForeignKey(
        ITSystem, on_delete=models.CASCADE, related_name="meldungen"
    )
    status       = models.CharField(max_length=20, choices=ITSystem.STATUS_CHOICES)
    titel        = models.CharField(max_length=200)
    beschreibung = models.TextField(blank=True)
    erstellt_von = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="it_meldungen"
    )
    erstellt_am  = models.DateTimeField(auto_now_add=True)
    geloest_am   = models.DateTimeField(null=True, blank=True)
    workflow_instance = models.ForeignKey(
        "workflow.WorkflowInstance",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="it_meldungen",
        verbose_name="Workflow-Instanz",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Statusmeldung"
        verbose_name_plural = "Statusmeldungen"

    def __str__(self):
        return f"{self.system} – {self.titel}"

    @property
    def ist_aktiv(self):
        return self.geloest_am is None


class ITWartung(models.Model):
    """Geplantes Wartungsfenster fuer ein IT-System."""

    system       = models.ForeignKey(
        ITSystem, on_delete=models.CASCADE, related_name="wartungen"
    )
    titel        = models.CharField(max_length=200)
    beschreibung = models.TextField(blank=True)
    start        = models.DateTimeField()
    ende         = models.DateTimeField()
    erstellt_von = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="it_wartungen"
    )
    erstellt_am  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start"]
        verbose_name = "Wartungsfenster"
        verbose_name_plural = "Wartungsfenster"

    def __str__(self):
        return f"{self.system} – {self.titel}"

    @property
    def ist_aktiv(self):
        jetzt = timezone.now()
        return self.start <= jetzt <= self.ende

    @property
    def liegt_in_zukunft(self):
        return self.start > timezone.now()
