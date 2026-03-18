from django.contrib.auth.models import User
from django.db import models


class Briefvorlage(models.Model):
    """DOCX-Vorlage mit {{platzhalter}} fuer DIN-5008-Geschaeftsbriefe.

    Die DOCX-Datei wird als Binaerdaten in der Datenbank gespeichert.
    Platzhalter haben die Form {{schluessel}} und werden beim Erstellen
    eines Briefvorgangs durch echte Werte ersetzt.
    """

    titel        = models.CharField(max_length=200)
    beschreibung = models.TextField(blank=True)
    inhalt       = models.BinaryField()   # DOCX-Bytes mit Platzhaltern
    ist_aktiv    = models.BooleanField(default=True)
    ist_standard = models.BooleanField(
        default=False,
        verbose_name="Standard-Vorlage",
        help_text="Diese Vorlage wird beim Erstellen eines neuen Briefes automatisch vorausgewaehlt.",
    )

    # ---------------------------------------------------------------------------
    # Standard-Absender (wird beim Erstellen eines Briefs vorbelegt)
    # ---------------------------------------------------------------------------
    default_absender_name    = models.CharField(max_length=200, blank=True, verbose_name="Standard-Absender Name/Firma")
    default_absender_strasse = models.CharField(max_length=200, blank=True, verbose_name="Standard-Absender Strasse")
    default_absender_ort     = models.CharField(max_length=200, blank=True, verbose_name="Standard-Absender PLZ/Ort")
    default_absender_telefon = models.CharField(max_length=50, blank=True, verbose_name="Standard-Absender Telefon")
    default_absender_email   = models.CharField(max_length=200, blank=True, verbose_name="Standard-Absender E-Mail")
    default_ort              = models.CharField(max_length=100, blank=True, verbose_name="Standard-Ort (Datum-Zeile)")
    default_grussformel      = models.CharField(max_length=200, blank=True, verbose_name="Standard-Grussformel")

    # ---------------------------------------------------------------------------
    # Fusszeile (erscheint auf jeder Seite unten im Brief)
    # ---------------------------------------------------------------------------
    fusszeile_firmenname = models.CharField(max_length=200, blank=True, verbose_name="Fusszeile Firmenname")
    fusszeile_telefon    = models.CharField(max_length=50,  blank=True, verbose_name="Fusszeile Telefon")
    fusszeile_telefax    = models.CharField(max_length=50,  blank=True, verbose_name="Fusszeile Telefax")
    fusszeile_email      = models.CharField(max_length=200, blank=True, verbose_name="Fusszeile E-Mail")
    fusszeile_internet   = models.CharField(max_length=200, blank=True, verbose_name="Fusszeile Internet")

    erstellt_am  = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="briefvorlagen",
    )

    class Meta:
        ordering = ["titel"]
        verbose_name = "Briefvorlage"
        verbose_name_plural = "Briefvorlagen"

    def __str__(self):
        return self.titel


class Briefvorgang(models.Model):
    """Einzelner Briefvorgang – befuellte Vorlage, editierbar in OnlyOffice.

    Nach dem Erstellen wird die DOCX-Vorlage mit den Formulardaten befuellt
    und als inhalt gespeichert. Anschliessend kann der Brief in OnlyOffice
    weiter bearbeitet und gespeichert werden.
    """

    STATUS_CHOICES = [
        ("entwurf",    "Entwurf"),
        ("fertig",     "Fertig"),
        ("archiviert", "Archiviert"),
    ]

    vorlage = models.ForeignKey(
        Briefvorlage,
        on_delete=models.PROTECT,
        related_name="vorgaenge",
    )

    # ---------------------------------------------------------------------------
    # Absender (wer schreibt den Brief)
    # ---------------------------------------------------------------------------
    absender_name    = models.CharField(max_length=200)
    absender_strasse = models.CharField(max_length=200, blank=True)
    absender_ort     = models.CharField(max_length=200, blank=True)
    absender_telefon = models.CharField(max_length=50, blank=True)
    absender_email   = models.CharField(max_length=200, blank=True)

    # ---------------------------------------------------------------------------
    # Empfaenger
    # ---------------------------------------------------------------------------
    empfaenger_name    = models.CharField(max_length=200)
    empfaenger_zusatz  = models.CharField(max_length=200, blank=True)
    empfaenger_strasse = models.CharField(max_length=200, blank=True)
    empfaenger_plz_ort = models.CharField(max_length=200, blank=True)
    empfaenger_land    = models.CharField(max_length=200, blank=True)

    # ---------------------------------------------------------------------------
    # Briefinhalt
    # ---------------------------------------------------------------------------
    ort              = models.CharField(max_length=100)
    datum            = models.DateField()
    betreff          = models.CharField(max_length=300)
    anrede           = models.CharField(max_length=200)
    brieftext        = models.TextField()
    grussformel      = models.CharField(max_length=200, default="Mit freundlichen Gruessen")
    unterschrift_name  = models.CharField(max_length=200)
    unterschrift_titel = models.CharField(max_length=200, blank=True)

    # ---------------------------------------------------------------------------
    # Gespeicherte DOCX-Datei (nach Befuellung und OnlyOffice-Bearbeitung)
    # ---------------------------------------------------------------------------
    inhalt  = models.BinaryField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    # ---------------------------------------------------------------------------
    # Status und Metadaten
    # ---------------------------------------------------------------------------
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="entwurf")
    erstellt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="briefe",
    )
    erstellt_am  = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Briefvorgang"
        verbose_name_plural = "Briefvorgaenge"

    def __str__(self):
        return f"{self.datum} – {self.betreff}"
