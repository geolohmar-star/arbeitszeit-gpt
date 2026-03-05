from datetime import date, timedelta

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


class FacilityEinstellungen(models.Model):
    """Globale Einstellungen fuer die Facility-App (Singleton, immer pk=1).

    Ueber get_or_create(pk=1) wird sichergestellt, dass nur ein Datensatz
    existiert. Die Werte koennen vom Abteilungsleiter ueber die UI angepasst
    werden.
    """

    trend_schwelle = models.PositiveIntegerField(
        default=3,
        verbose_name="Trend-Schwelle (Anzahl Meldungen)",
        help_text=(
            "Ab dieser Wiederholungsanzahl am gleichen Ort und gleicher Kategorie "
            "wird im Monatsbericht eine Tendenz-Warnung ausgegeben."
        ),
    )
    trend_tage = models.PositiveIntegerField(
        default=90,
        verbose_name="Beobachtungszeitraum (Tage)",
        help_text=(
            "Zeitraum in Tagen, ueber den Meldungen auf Tendenzen geprueft werden. "
            "Empfehlung: 30 (Monat), 90 (Quartal) oder 180 (Halbjahr)."
        ),
    )

    class Meta:
        verbose_name = "Facility-Einstellungen"
        verbose_name_plural = "Facility-Einstellungen"

    def __str__(self):
        return "Facility-Einstellungen"

    @classmethod
    def laden(cls):
        """Gibt den einzigen Einstellungs-Datensatz zurueck (legt ihn an falls noetig)."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


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


class Wartungsplan(models.Model):
    """Geplante wiederkehrende Wartungsaufgabe fuer das Facility-Management."""

    EINHEIT_CHOICES = [
        ("tage", "Tage"),
        ("wochen", "Wochen"),
        ("monate", "Monate"),
    ]

    # Beschreibung
    name = models.CharField(max_length=200, verbose_name="Bezeichnung")
    beschreibung = models.TextField(blank=True, verbose_name="Beschreibung")
    kategorie = models.CharField(
        max_length=30, choices=KATEGORIE_CHOICES, verbose_name="Kategorie"
    )

    # Ort
    raumnummer = models.CharField(max_length=50, verbose_name="Raumnummer / Ort")
    raum_freitext = models.TextField(blank=True, verbose_name="Ort-Zusatz")

    # Prioritaet
    prioritaet = models.CharField(
        max_length=20,
        choices=[
            ("normal", "Normal"),
            ("dringend", "Dringend"),
            ("sofort", "Sofort / Notfall"),
        ],
        default="normal",
        verbose_name="Prioritaet",
    )

    # Intervall: z.B. 30 Tage, 2 Wochen, 6 Monate
    intervall_wert = models.PositiveIntegerField(
        verbose_name="Intervall",
        help_text="Zahl fuer das Wartungsintervall (z.B. 30)",
    )
    intervall_einheit = models.CharField(
        max_length=10,
        choices=EINHEIT_CHOICES,
        default="tage",
        verbose_name="Einheit",
    )

    # Faelligkeit
    letzte_ausfuehrung = models.DateField(
        null=True,
        blank=True,
        verbose_name="Letzte Ausfuehrung",
        help_text="Wird automatisch gesetzt wenn eine Wartungsaufgabe erledigt wird.",
    )
    naechste_faelligkeit = models.DateField(
        verbose_name="Naechste Faelligkeit",
        help_text="Wird automatisch berechnet.",
    )

    # Status
    ist_aktiv = models.BooleanField(default=True, verbose_name="Aktiv")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_wartungsplaene",
    )

    class Meta:
        ordering = ["naechste_faelligkeit", "name"]
        verbose_name = "Wartungsplan"
        verbose_name_plural = "Wartungsplaene"

    def __str__(self):
        return f"{self.name} ({self.raumnummer})"

    def berechne_naechste_faelligkeit(self, basis: date = None) -> date:
        """Berechnet das naechste Faelligkeitsdatum ausgehend von basis (Standard: heute)."""
        start = basis or date.today()
        if self.intervall_einheit == "tage":
            return start + timedelta(days=self.intervall_wert)
        elif self.intervall_einheit == "wochen":
            return start + timedelta(weeks=self.intervall_wert)
        elif self.intervall_einheit == "monate":
            # Monatsberechnung ohne dateutil
            monat = start.month - 1 + self.intervall_wert
            jahr = start.year + monat // 12
            monat = monat % 12 + 1
            # Letzter Tag des Monats falls noetig
            import calendar
            tag = min(start.day, calendar.monthrange(jahr, monat)[1])
            return date(jahr, monat, tag)
        return start + timedelta(days=self.intervall_wert)

    def ist_faellig(self) -> bool:
        """True wenn die naechste Faelligkeit heute oder in der Vergangenheit liegt."""
        return self.naechste_faelligkeit <= date.today()

    def hat_offene_aufgabe(self) -> bool:
        """True wenn bereits eine offene/laufende Wartungsaufgabe existiert."""
        return self.ausgeloeste_meldungen.filter(
            status__in=["offen", "in_bearbeitung"]
        ).exists()

    def intervall_anzeige(self) -> str:
        """Lesbare Intervall-Darstellung z.B. 'alle 30 Tage'."""
        return f"alle {self.intervall_wert} {self.get_intervall_einheit_display()}"


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
        ("weitergeleitet", "Weitergeleitet an AL"),
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
    raum = models.ForeignKey(
        "raumbuch.Raum",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stoermeldungen",
        verbose_name="Raum (Raumbuch)",
    )

    # Stoerung
    kategorie = models.CharField(max_length=30, choices=KATEGORIE_CHOICES, db_index=True)
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

    # Wartungsplan-Bezug (gesetzt wenn automatisch ausgeloest)
    ist_wartung = models.BooleanField(
        default=False,
        verbose_name="Wartungsaufgabe",
        help_text="Automatisch ausgeloest durch einen Wartungsplan.",
    )
    wartungsplan = models.ForeignKey(
        Wartungsplan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ausgeloeste_meldungen",
    )

    # Status & Zeitstempel
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="offen", db_index=True
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

    # Eskalation / Weiterleitung an Abteilungsleiter
    eskaliert_an = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eskalierte_stoermeldungen",
    )
    eskaliert_am = models.DateTimeField(null=True, blank=True)
    eskalation_typ = models.CharField(
        max_length=20,
        blank=True,
        choices=[("bestellware", "Bestellware"), ("eskalation", "Eskalation")],
    )
    eskalation_kommentar = models.TextField(blank=True)
    eskalation_antwort = models.TextField(blank=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Stoermeldung"
        verbose_name_plural = "Stoermeldungen"

    def __str__(self):
        prefix = "WAR" if self.ist_wartung else "STR"
        return f"#{self.pk:05d} {self.get_kategorie_display()} - {self.raumnummer}"

    def get_betreff(self):
        prefix = "WAR" if self.ist_wartung else "STR"
        return f"{prefix}-{self.pk:05d}"

    def get_absolute_url(self):
        return reverse("facility:detail", args=[self.pk])
