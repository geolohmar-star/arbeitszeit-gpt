from django.contrib.auth.models import User
from django.db import models


class Ausschreibung(models.Model):
    """Interne Stellenausschreibung – sichtbar fuer alle Mitarbeiter."""

    BESCHAEFTIGUNGSART_CHOICES = [
        ("vollzeit", "Vollzeit"),
        ("teilzeit", "Teilzeit"),
        ("beide", "Vollzeit oder Teilzeit"),
    ]

    STATUS_CHOICES = [
        ("aktiv", "Aktiv"),
        ("pausiert", "Pausiert"),
        ("besetzt", "Besetzt"),
        ("archiviert", "Archiviert"),
    ]

    anforderungen = models.TextField(
        blank=True,
        verbose_name="Anforderungen",
        help_text="Was bringen Bewerber/innen idealerweise mit?",
    )
    aufgaben = models.TextField(
        blank=True,
        verbose_name="Aufgaben & Verantwortlichkeiten",
        help_text="Was erwartet die Person in dieser Stelle?",
    )
    beschaeftigungsart = models.CharField(
        max_length=10,
        choices=BESCHAEFTIGUNGSART_CHOICES,
        default="vollzeit",
        verbose_name="Beschaeftigungsart",
    )
    beschreibung = models.TextField(
        verbose_name="Stellenbeschreibung",
        help_text="Uebersicht zur Stelle und zum Team (Blog-Stil).",
    )
    bewerbungsfrist = models.DateField(
        null=True,
        blank=True,
        verbose_name="Bewerbungsfrist",
        help_text="Leer lassen fuer offenes Ende.",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="erstellte_ausschreibungen",
        verbose_name="Erstellt von",
    )
    geaendert_am = models.DateTimeField(auto_now=True)
    orgeinheit = models.ForeignKey(
        "hr.OrgEinheit",
        on_delete=models.PROTECT,
        related_name="ausschreibungen",
        verbose_name="Organisationseinheit",
    )
    stelle = models.ForeignKey(
        "hr.Stelle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ausschreibungen",
        verbose_name="Stelle",
        help_text="Die konkrete Planstelle, die besetzt werden soll.",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="aktiv",
        verbose_name="Status",
    )
    titel = models.CharField(max_length=200, verbose_name="Stellentitel")
    veroeffentlicht = models.BooleanField(
        default=False,
        verbose_name="Veroeffentlicht",
        help_text="Nur veroeffentlichte Ausschreibungen sind fuer Mitarbeiter sichtbar.",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Ausschreibung"
        verbose_name_plural = "Ausschreibungen"

    def __str__(self):
        return f"{self.titel} ({self.orgeinheit.kuerzel})"

    @property
    def ist_fuehrungsstelle(self):
        """Prueft ob die ausgeschriebene Planstelle eine Leitungsfunktion ist."""
        return (
            self.stelle is not None
            and self.stelle.kategorie == "leitung"
        )

    @property
    def ist_offen(self):
        """Prueft ob Ausschreibung aktiv und veroeffentlicht ist."""
        return self.status == "aktiv" and self.veroeffentlicht

    @property
    def bewerbungen_anzahl(self):
        return self.bewerbungen.count()


class Bewerbung(models.Model):
    """Bewerbung eines Mitarbeiters auf eine interne Ausschreibung."""

    STATUS_CHOICES = [
        ("eingegangen", "Eingegangen"),
        ("sichtung", "In Pruefung"),
        ("gespraech", "Vorstellungsgespraech"),
        ("angeboten", "Angebot unterbreitet"),
        ("abgesagt", "Abgesagt"),
        ("zurueckgezogen", "Zurueckgezogen"),
    ]

    STATUS_FARBE = {
        "eingegangen": "secondary",
        "sichtung": "info",
        "gespraech": "primary",
        "angeboten": "success",
        "abgesagt": "danger",
        "zurueckgezogen": "warning",
    }

    ausschreibung = models.ForeignKey(
        Ausschreibung,
        on_delete=models.CASCADE,
        related_name="bewerbungen",
        verbose_name="Ausschreibung",
    )
    bewerber = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="stellenbewerbungen",
        verbose_name="Bewerber/in",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)
    hr_notiz = models.TextField(
        blank=True,
        verbose_name="HR-Notiz (intern)",
        help_text="Nur fuer HR sichtbar – erscheint nicht beim Bewerber.",
    )
    motivationstext = models.TextField(verbose_name="Motivationstext")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="eingegangen",
        verbose_name="Status",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        unique_together = ("ausschreibung", "bewerber")
        verbose_name = "Bewerbung"
        verbose_name_plural = "Bewerbungen"

    def __str__(self):
        return f"{self.bewerber.get_full_name() or self.bewerber.username} -> {self.ausschreibung.titel}"

    @property
    def status_farbe(self):
        return self.STATUS_FARBE.get(self.status, "secondary")
