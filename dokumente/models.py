from django.contrib.auth.models import User
from django.db import models


class SensiblesDokument(models.Model):
    KATEGORIE_CHOICES = [
        ("zeugnis", "Zeugnis"),
        ("abschluss", "Abschluss / Qualifikation"),
        ("reise", "Reiseunterlage"),
        ("ausweis", "Ausweis / Identitaetsnachweis"),
        ("sonstige", "Sonstiges"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sensible_dokumente",
        verbose_name="Gehoert zu Mitarbeiter",
    )
    hochgeladen_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="hochgeladene_dokumente",
        verbose_name="Hochgeladen von",
    )
    kategorie = models.CharField(
        max_length=20,
        choices=KATEGORIE_CHOICES,
        verbose_name="Kategorie",
    )
    dateiname = models.CharField(max_length=255, verbose_name="Originaldateiname")
    dateityp = models.CharField(max_length=100, verbose_name="MIME-Typ")
    inhalt_verschluesselt = models.BinaryField(verbose_name="Inhalt (AES-verschluesselt)")
    groesse_bytes = models.IntegerField(verbose_name="Dateigroesse (Bytes)")
    beschreibung = models.CharField(
        max_length=500, blank=True, verbose_name="Beschreibung"
    )
    gueltig_bis = models.DateField(
        null=True, blank=True, verbose_name="Gueltig bis"
    )
    hochgeladen_am = models.DateTimeField(
        auto_now_add=True, verbose_name="Hochgeladen am"
    )

    class Meta:
        ordering = ["-hochgeladen_am"]
        verbose_name = "Sensibles Dokument"
        verbose_name_plural = "Sensible Dokumente"

    def __str__(self):
        return f"{self.get_kategorie_display()} – {self.dateiname} ({self.user.get_full_name() or self.user.username})"

    def groesse_lesbar(self):
        """Gibt die Dateigroesse in lesbarer Form zurueck."""
        if self.groesse_bytes < 1024:
            return f"{self.groesse_bytes} B"
        elif self.groesse_bytes < 1024 * 1024:
            return f"{self.groesse_bytes / 1024:.1f} KB"
        else:
            return f"{self.groesse_bytes / (1024 * 1024):.1f} MB"


class DokumentZugriff(models.Model):
    """Protokolliert jeden Download eines sensiblen Dokuments.

    Unveraenderlich: kein update(), kein delete() ueber normale Wege.
    Dient als DSGVO-konformer Audit-Trail (Art. 5 Abs. 2 – Rechenschaftspflicht).
    """

    dokument = models.ForeignKey(
        SensiblesDokument,
        on_delete=models.CASCADE,
        related_name="zugriffe",
        verbose_name="Dokument",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dokument_zugriffe",
        verbose_name="Zugegriffen von",
    )
    zeitpunkt = models.DateTimeField(auto_now_add=True, verbose_name="Zeitpunkt")
    ip_adresse = models.GenericIPAddressField(
        null=True, blank=True, verbose_name="IP-Adresse"
    )

    class Meta:
        ordering = ["-zeitpunkt"]
        verbose_name = "Dokument-Zugriff"
        verbose_name_plural = "Dokument-Zugriffe"

    def __str__(self):
        username = self.user.username if self.user else "unbekannt"
        return f"{username} – {self.dokument.dateiname} ({self.zeitpunkt:%d.%m.%Y %H:%M})"
