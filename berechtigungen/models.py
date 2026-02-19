from django.contrib.auth.models import User
from django.db import models


class BerechtigungsProtokoll(models.Model):
    """Protokolliert jede Berechtigungsaenderung fuer den Audit-Trail."""

    AKTION_CHOICES = [
        ("vergeben", "Vergeben"),
        ("entzogen", "Entzogen"),
    ]

    aktion = models.CharField(
        max_length=10,
        choices=AKTION_CHOICES,
        verbose_name="Aktion",
    )
    permission_codename = models.CharField(
        max_length=100,
        verbose_name="Berechtigung",
    )
    ziel_mitarbeiter = models.ForeignKey(
        "arbeitszeit.Mitarbeiter",
        on_delete=models.CASCADE,
        related_name="berechtigungs_protokolle",
        verbose_name="Betroffener Mitarbeiter",
    )
    berechtigter_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erhaltene_berechtigungen",
        verbose_name="Berechtigter Nutzer",
    )
    durchgefuehrt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="berechtigungs_aktionen",
        verbose_name="Durchgefuehrt von",
    )
    zeitpunkt = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Zeitpunkt",
    )
    bemerkung = models.TextField(
        blank=True,
        verbose_name="Bemerkung",
    )

    class Meta:
        ordering = ["-zeitpunkt"]
        verbose_name = "Berechtigungsprotokoll"
        verbose_name_plural = "Berechtigungsprotokolle"

    def __str__(self):
        return (
            f"{self.get_aktion_display()}: {self.permission_codename} "
            f"fuer {self.ziel_mitarbeiter} "
            f"an {self.berechtigter_user} "
            f"({self.zeitpunkt:%d.%m.%Y %H:%M})"
        )
