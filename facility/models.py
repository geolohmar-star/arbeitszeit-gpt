from django.conf import settings
from django.db import models
from django.urls import reverse

KATEGORIE_CHOICES = [
    ("elektro", "Elektro"),
    ("sanitaer_heizung", "Sanitaer / Heizung"),
    ("schlosser", "Schlosser"),
    ("schreiner", "Schreiner"),
    ("maler", "Maler"),
]


class Textbaustein(models.Model):
    """Vordefinierter Meldungstext fuer eine Stoermeldungs-Kategorie."""

    kategorie = models.CharField(max_length=30, choices=KATEGORIE_CHOICES)
    text = models.CharField(max_length=300)
    reihenfolge = models.PositiveIntegerField(default=0)
    ist_aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["kategorie", "reihenfolge", "text"]
        verbose_name = "Textbaustein"
        verbose_name_plural = "Textbausteine"

    def __str__(self):
        return f"{self.get_kategorie_display()}: {self.text}"


class FacilityTeam(models.Model):
    """Einem Facility-Team zugeordnete Mitglieder fuer eine Kategorie."""

    kategorie = models.CharField(
        max_length=30, choices=KATEGORIE_CHOICES, unique=True
    )
    mitglieder = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="facility_teams",
    )
    teamleiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="geleitete_facility_teams",
    )
    eskalation_nach_tagen = models.PositiveIntegerField(default=3)

    class Meta:
        ordering = ["kategorie"]
        verbose_name = "Facility-Team"
        verbose_name_plural = "Facility-Teams"

    def __str__(self):
        return self.get_kategorie_display()


class Stoermeldung(models.Model):
    """Stoermeldung eines Mitarbeiters an das Facility-Management."""

    PRIORITAET_CHOICES = [
        ("normal", "Normal"),
        ("dringend", "Dringend"),
        ("sofort", "Sofort / Notfall"),
    ]
    STATUS_CHOICES = [
        ("offen", "Offen"),
        ("in_bearbeitung", "In Bearbeitung"),
        ("erledigt", "Erledigt"),
        ("unloesbar", "Unloesbar / Eskaliert"),
    ]

    # Melder
    melder = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.PROTECT,
        related_name="stoermeldungen",
    )
    melder_telefon = models.CharField(max_length=50)

    # Ort
    raumnummer = models.CharField(max_length=50)
    raum_freitext = models.TextField(blank=True)
    raumbuch_id = models.PositiveIntegerField(
        null=True, blank=True
    )  # Platzhalter fuer kuenftige Raumbuch-App

    # Stoerung
    kategorie = models.CharField(max_length=30, choices=KATEGORIE_CHOICES)
    textbaustein = models.ForeignKey(
        Textbaustein,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    beschreibung = models.TextField(blank=True)
    prioritaet = models.CharField(
        max_length=20, choices=PRIORITAET_CHOICES, default="normal"
    )

    # Status & Zeitstempel
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="offen"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    # Bearbeitung
    claimed_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="geclaimte_stoermeldungen",
    )
    claimed_am = models.DateTimeField(null=True, blank=True)
    bearbeitet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bearbeitete_stoermeldungen",
    )
    bearbeitet_am = models.DateTimeField(null=True, blank=True)
    erledigungs_kommentar = models.TextField(blank=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Stoermeldung"
        verbose_name_plural = "Stoermeldungen"

    def __str__(self):
        return f"#{self.pk:05d} {self.get_kategorie_display()} - {self.raumnummer}"

    def get_betreff(self):
        return f"STR-{self.pk:05d}"

    def get_absolute_url(self):
        return reverse("facility:detail", args=[self.pk])
