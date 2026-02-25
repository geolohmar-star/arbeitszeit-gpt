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
        ("eskaliert", "Eskaliert"),
        ("in_bearbeitung", "In Bearbeitung"),
        ("erledigt", "Erledigt"),
    ]

    PRIORITAET_CHOICES = [
        (0, "Normal"),
        (1, "Hoch"),
        (2, "Dringend"),
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

    # Team-Queue Felder
    claimed_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Claimed am",
    )
    claimed_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_claimed",
        verbose_name="Claimed von",
    )
    erledigt_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Erledigt am",
    )

    erstellt_am = models.DateTimeField(auto_now_add=True)
    prioritaet = models.IntegerField(
        choices=PRIORITAET_CHOICES,
        default=0,
        verbose_name="Prioritaet",
    )
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

    # Workflow-Verknuepfung
    workflow_instance = models.ForeignKey(
        "workflow.WorkflowInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aenderungen_zeiterfassung",
        verbose_name="Workflow-Instanz",
    )

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


class ZAGAntrag(Antrag):
    """Antrag auf Zeitausgleich (Z-AG).

    Speichert einen oder mehrere Datumsbereich(e) als JSON.
    Beim Absenden werden sofort Zeiterfassungs-Eintraege erstellt.
    """

    # Mehrere Zeilen: [{"von_datum": "2026-02-10", "bis_datum": "2026-02-12"}, ...]
    zag_daten = models.JSONField(null=True, blank=True)

    # Vertretungsfelder
    vertretung_name = models.CharField(max_length=200, blank=True)
    vertretung_telefon = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Z-AG Antrag"
        verbose_name_plural = "Z-AG Antraege"

    def get_betreff(self):
        """Eindeutige Betreffzeile fuer diesen Antrag.

        Zeitstempel wird in Ortszeit (Europe/Berlin) ausgegeben.
        """
        ma = self.antragsteller
        ortszeit = timezone.localtime(self.erstellt_am)
        zeitstempel = ortszeit.strftime("%Y%m%d-%H%M%S")
        return (
            f"ZAG-{ma.vorname} {ma.nachname}"
            f"-{ma.personalnummer}"
            f"-{zeitstempel}"
        )

    def __str__(self):
        return f"Z-AG Antrag - {self.antragsteller}"


class ZAGStorno(Antrag):
    """Stornierung von Z-AG-Eintraegen in der Zeiterfassung.

    Speichert einen oder mehrere Datumsbereiche als JSON.
    Beim Absenden werden sofort die entsprechenden Zeiterfassungs-
    Eintraege geloescht.
    """

    # Mehrere Zeilen: [{"von_datum": "2026-02-10", "bis_datum": "2026-02-12"}, ...]
    storno_daten = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Z-AG Storno"
        verbose_name_plural = "Z-AG Stornierungen"

    def get_betreff(self):
        """Eindeutige Betreffzeile fuer diesen Storno-Antrag."""
        ma = self.antragsteller
        ortszeit = timezone.localtime(self.erstellt_am)
        zeitstempel = ortszeit.strftime("%Y%m%d-%H%M%S")
        return (
            f"ZAGS-{ma.vorname} {ma.nachname}"
            f"-{ma.personalnummer}"
            f"-{zeitstempel}"
        )

    def __str__(self):
        return f"Z-AG Storno - {self.antragsteller}"


class Dienstreiseantrag(Antrag):
    """Antrag auf Dienstreise.

    Speichert Reisedaten und wird mit Workflow-System verknuepft.
    Nach Genehmigung kann Einladungscode generiert werden fuer
    Reisezeit-Antrag (1/3 ausserhalb Arbeitszeit).
    """

    # Reisedaten
    von_datum = models.DateField(verbose_name="Reisebeginn")
    bis_datum = models.DateField(verbose_name="Reiseende")
    ziel = models.CharField(
        max_length=200,
        verbose_name="Reiseziel",
        help_text="Stadt, Land oder Veranstaltungsort",
    )
    zweck = models.TextField(
        verbose_name="Zweck der Dienstreise",
        help_text="Grund und Ziel der Reise (z.B. Kundentermin, Schulung, Messe)",
    )

    # Kosten
    geschaetzte_kosten = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Geschaetzte Kosten (EUR)",
        help_text="Geschaetzte Gesamtkosten inkl. Fahrt, Unterkunft, Verpflegung",
    )

    # Workflow-Verknuepfung
    workflow_instance = models.ForeignKey(
        "workflow.WorkflowInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dienstreiseantraege",
        verbose_name="Workflow-Instanz",
    )

    # Einladungscode fuer Reisezeit-Antrag (wird nach Genehmigung generiert)
    einladungscode = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Einladungscode",
        help_text="Code fuer Mitarbeiter um Reisezeit-Antrag zu stellen",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Dienstreiseantrag"
        verbose_name_plural = "Dienstreiseantraege"

    def get_betreff(self):
        """Eindeutige Betreffzeile fuer diesen Antrag."""
        ma = self.antragsteller
        ortszeit = timezone.localtime(self.erstellt_am)
        zeitstempel = ortszeit.strftime("%Y%m%d-%H%M%S")
        return (
            f"DR-{ma.vorname} {ma.nachname}"
            f"-{ma.personalnummer}"
            f"-{zeitstempel}"
        )

    def __str__(self):
        return f"Dienstreise {self.ziel} ({self.von_datum} - {self.bis_datum}) - {self.antragsteller}"

    @property
    def dauer_tage(self):
        """Berechnet die Dauer der Dienstreise in Tagen."""
        if self.von_datum and self.bis_datum:
            return (self.bis_datum - self.von_datum).days + 1
        return 0


class Zeitgutschrift(Antrag):
    """Antrag auf Zeitgutschrift.

    Unterstuetzt drei Arten:
    - Haertefallregelung
    - Wahrnehmung von Ehrenamtern
    - Ganztaegige Fortbildung bei individueller Arbeitszeit
    """

    ART_CHOICES = [
        ("haertefall", "Haertefallregelung"),
        ("ehrenamt", "Wahrnehmung von Ehrenamtern"),
        (
            "fortbildung",
            "Ganztaegige Fortbildung bei individueller Arbeitszeit",
        ),
    ]

    FORTBILDUNG_TYP_CHOICES = [
        ("typ_a", "Typ A"),
        ("typ_b", "Typ B"),
    ]

    # Art der Zeitgutschrift
    art = models.CharField(max_length=20, choices=ART_CHOICES)

    # Gemeinsame Felder (Haertefall + Ehrenamt)
    # Format: [{"datum": "2026-02-10", "von_zeit": "08:00", "bis_zeit": "16:00"}, ...]
    zeilen_daten = models.JSONField(null=True, blank=True)

    # Fortbildungs-Felder
    fortbildung_aktiv = models.BooleanField(default=False)
    fortbildung_typ = models.CharField(
        max_length=10,
        choices=FORTBILDUNG_TYP_CHOICES,
        blank=True,
    )
    fortbildung_wochenstunden_regulaer = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fortbildung_von_datum = models.DateField(null=True, blank=True)
    fortbildung_bis_datum = models.DateField(null=True, blank=True)
    fortbildung_massnahme_nr = models.CharField(max_length=100, blank=True)

    # Berechnungsergebnis als JSON gespeichert
    # Format: {"zeilen": [...], "summe_fortbildung": "38.0", "summe_vereinbarung": "40.0", "differenz": "2.0"}
    fortbildung_berechnung = models.JSONField(null=True, blank=True)

    # Workflow-Verknuepfung
    workflow_instance = models.ForeignKey(
        "workflow.WorkflowInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="zeitgutschriften",
        verbose_name="Workflow-Instanz",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Zeitgutschrift"
        verbose_name_plural = "Zeitgutschriften"

    def get_betreff(self):
        """Eindeutige Betreffzeile fuer diesen Antrag.

        Zeitstempel wird in Ortszeit (Europe/Berlin) ausgegeben.
        """
        ma = self.antragsteller
        ortszeit = timezone.localtime(self.erstellt_am)
        zeitstempel = ortszeit.strftime("%Y%m%d-%H%M%S")
        return (
            f"ZGH-{ma.vorname} {ma.nachname}"
            f"-{ma.personalnummer}"
            f"-{zeitstempel}"
        )

    def __str__(self):
        return (
            f"Zeitgutschrift ({self.get_art_display()}) "
            f"- {self.antragsteller}"
        )


class ZeitgutschriftBeleg(models.Model):
    """Beleg-Datei fuer Zeitgutschrift-Antrag.

    Unterstuetzt PDF, JPG, PNG-Uploads.
    """

    datei = models.FileField(
        upload_to="zeitgutschriften/belege/%Y/%m/",
    )
    dateiname_original = models.CharField(max_length=255)
    hochgeladen_am = models.DateTimeField(auto_now_add=True)
    zeitgutschrift = models.ForeignKey(
        Zeitgutschrift,
        on_delete=models.CASCADE,
        related_name="belege",
    )

    class Meta:
        ordering = ["hochgeladen_am"]
        verbose_name = "Zeitgutschrift-Beleg"
        verbose_name_plural = "Zeitgutschrift-Belege"

    def __str__(self):
        return f"{self.dateiname_original} ({self.zeitgutschrift.id})"

    def dateityp(self):
        """Gibt Dateityp zurueck (pdf, jpg, png)."""
        erweiterung = self.dateiname_original.lower().split(".")[-1]
        if erweiterung in ["jpg", "jpeg"]:
            return "jpg"
        elif erweiterung == "png":
            return "png"
        elif erweiterung == "pdf":
            return "pdf"
        return "unbekannt"

    def dateigroesse_formatiert(self):
        """Formatierte Dateigroesse (z.B. '2.4 MB')."""
        try:
            groesse_bytes = self.datei.size
            if groesse_bytes < 1024:
                return f"{groesse_bytes} B"
            elif groesse_bytes < 1024 * 1024:
                return f"{groesse_bytes / 1024:.1f} KB"
            else:
                return f"{groesse_bytes / (1024 * 1024):.1f} MB"
        except (OSError, AttributeError):
            return "Unbekannt"


class TeamQueue(models.Model):
    """Team-Bearbeitungsstapel fuer genehmigte Antraege.

    Definiert welche Teams welche Antragstypen bearbeiten.
    Mitglieder koennen Antraege aus der Queue claimen und bearbeiten.
    """

    beschreibung = models.TextField(
        blank=True,
        help_text="Beschreibung des Teams und seiner Zustaendigkeiten.",
    )
    kuerzel = models.CharField(
        max_length=20,
        unique=True,
        help_text="Eindeutiges Kuerzel (z.B. 'zeit', 'hr').",
    )
    mitglieder = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="team_queues",
        verbose_name="Mitglieder",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Team-Name",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Team-Queue"
        verbose_name_plural = "Team-Queues"

    def __str__(self):
        return self.name

    def antraege_in_queue(self):
        """Gibt alle genehmigten, ungeclaimten Antraege zurueck."""
        from itertools import chain

        aenderungen = AenderungZeiterfassung.objects.filter(
            status="genehmigt",
            claimed_von__isnull=True,
        )
        zag_antraege = ZAGAntrag.objects.filter(
            status="genehmigt",
            claimed_von__isnull=True,
        )
        zag_stornos = ZAGStorno.objects.filter(
            status="genehmigt",
            claimed_von__isnull=True,
        )
        zeitgutschriften = Zeitgutschrift.objects.filter(
            status="genehmigt",
            claimed_von__isnull=True,
        )

        # Alle zusammenfuehren und nach Prioritaet/Erstelldatum sortieren
        alle_antraege = sorted(
            chain(aenderungen, zag_antraege, zag_stornos, zeitgutschriften),
            key=lambda x: (-x.prioritaet, x.erstellt_am),
        )
        return alle_antraege

    def antraege_in_bearbeitung(self):
        """Gibt alle geclaimten Antraege des Teams zurueck."""
        from itertools import chain

        mitglieder_ids = self.mitglieder.values_list("id", flat=True)

        aenderungen = AenderungZeiterfassung.objects.filter(
            status="in_bearbeitung",
            claimed_von__in=mitglieder_ids,
        )
        zag_antraege = ZAGAntrag.objects.filter(
            status="in_bearbeitung",
            claimed_von__in=mitglieder_ids,
        )
        zag_stornos = ZAGStorno.objects.filter(
            status="in_bearbeitung",
            claimed_von__in=mitglieder_ids,
        )
        zeitgutschriften = Zeitgutschrift.objects.filter(
            status="in_bearbeitung",
            claimed_von__in=mitglieder_ids,
        )

        alle_antraege = sorted(
            chain(
                aenderungen,
                zag_antraege,
                zag_stornos,
                zeitgutschriften,
            ),
            key=lambda x: x.claimed_am,
        )
        return alle_antraege
