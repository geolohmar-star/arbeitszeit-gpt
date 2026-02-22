import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Bereich(models.Model):
    """Oberste Organisationsebene (z.B. IT & Entwicklung)."""
    name = models.CharField(max_length=100)
    kuerzel = models.CharField(max_length=10, unique=True)
    beschreibung = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Bereich"
        verbose_name_plural = "Bereiche"

    def __str__(self):
        return self.name


class Abteilung(models.Model):
    """Zweite Ebene (z.B. Softwareentwicklung)."""
    name = models.CharField(max_length=100)
    kuerzel = models.CharField(max_length=10)
    bereich = models.ForeignKey(
        Bereich,
        on_delete=models.CASCADE,
        related_name="abteilungen",
    )

    class Meta:
        ordering = ["bereich", "name"]
        unique_together = ["bereich", "kuerzel"]
        verbose_name = "Abteilung"
        verbose_name_plural = "Abteilungen"

    def __str__(self):
        return f"{self.bereich.kuerzel} / {self.name}"


class Team(models.Model):
    """Operative Einheit innerhalb einer Abteilung."""
    name = models.CharField(max_length=100)
    abteilung = models.ForeignKey(
        Abteilung,
        on_delete=models.CASCADE,
        related_name="teams",
    )

    class Meta:
        ordering = ["abteilung", "name"]
        verbose_name = "Team"
        verbose_name_plural = "Teams"

    def __str__(self):
        return f"{self.abteilung.kuerzel} / {self.name}"


class OrgEinheit(models.Model):
    """Organisationseinheit (flach mit optionaler Hierarchie).

    Repraesentiert Bereiche wie FM, IT, GF. Reservierte Einheiten
    werden per Data-Migration angelegt und koennen nicht versehentlich
    geloescht werden.
    """
    bezeichnung = models.CharField(max_length=100)
    ist_reserviert = models.BooleanField(
        default=False,
        help_text="Reservierte Einheiten werden per Migration angelegt "
                  "und sollten nicht geloescht werden.",
    )
    kuerzel = models.CharField(max_length=10, unique=True)
    leitende_stelle = models.ForeignKey(
        "Stelle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="geleitete_orgeinheiten",
        verbose_name="Leitende Stelle",
        help_text="Die Stelle, die diese OrgEinheit leitet (z.B. Bereichsleiter)",
    )
    uebergeordnet = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="untereinheiten",
        verbose_name="Uebergeordnete Einheit",
    )

    class Meta:
        ordering = ["kuerzel"]
        verbose_name = "Organisationseinheit"
        verbose_name_plural = "Organisationseinheiten"

    def __str__(self):
        return f"{self.kuerzel} – {self.bezeichnung}"


class Stelle(models.Model):
    """Repraesentiert eine Position (z.B. fm1, gf1).

    Die Email-Adresse gehoert der Stelle, nicht der Person.
    Mitarbeiterwechsel erfordert keine Permission-Updates mehr.
    """

    KATEGORIE_LEITUNG = 'leitung'
    KATEGORIE_STAB = 'stab'
    KATEGORIE_FACHKRAFT = 'fachkraft'

    KATEGORIE_CHOICES = [
        (KATEGORIE_LEITUNG, 'Leitung'),
        (KATEGORIE_STAB, 'Stab'),
        (KATEGORIE_FACHKRAFT, 'Fachkraft'),
    ]
    bezeichnung = models.CharField(max_length=200)
    delegiert_an = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erhaelt_delegation",
        verbose_name="Delegiert an",
        help_text="Massengeschaeft dauerhaft an diese Stelle delegiert.",
    )
    eskalation_nach_tagen = models.PositiveIntegerField(
        default=3,
        verbose_name="Eskalation nach (Tagen)",
    )
    kategorie = models.CharField(
        max_length=20,
        choices=KATEGORIE_CHOICES,
        default=KATEGORIE_FACHKRAFT,
        verbose_name="Kategorie",
        help_text="Leitungsstellen werden im Organigramm besonders hervorgehoben.",
    )
    kuerzel = models.CharField(max_length=20, unique=True)
    max_urlaubstage_genehmigung = models.PositiveIntegerField(
        default=0,
        verbose_name="Max. Urlaubstage Genehmigung",
        help_text="0 = unbegrenzt; darueber hinaus automatische Eskalation.",
    )
    org_einheit = models.ForeignKey(
        OrgEinheit,
        on_delete=models.PROTECT,
        related_name="stellen",
        verbose_name="Organisationseinheit",
    )
    uebergeordnete_stelle = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="untergeordnete_stellen",
        verbose_name="Uebergeordnete Stelle",
    )
    vertreten_durch = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vertritt_stellen",
        verbose_name="Vertreten durch",
    )
    vertretung_bis = models.DateField(
        null=True,
        blank=True,
        verbose_name="Vertretung bis",
    )
    vertretung_von = models.DateField(
        null=True,
        blank=True,
        verbose_name="Vertretung von",
    )

    class Meta:
        ordering = ["kuerzel"]
        verbose_name = "Stelle"
        verbose_name_plural = "Stellen"

    def __str__(self):
        return f"{self.kuerzel} – {self.bezeichnung}"

    @property
    def email(self):
        """Berechnet die Email-Adresse der Stelle."""
        domain = getattr(settings, "STELLEN_EMAIL_DOMAIN", "firma.de")
        return f"{self.kuerzel.lower()}@{domain}"

    @property
    def ist_besetzt(self):
        """Prueft ob die Stelle aktuell besetzt ist."""
        return hasattr(self, "hrmitarbeiter") and self.hrmitarbeiter is not None

    @property
    def aktueller_inhaber(self):
        """Gibt den aktuellen HRMitarbeiter zurueck oder None."""
        return getattr(self, "hrmitarbeiter", None)

    def verantwortliche_stelle(self, datum=None):
        """Gibt die tatsaechlich verantwortliche Stelle zurueck.

        Prueft in dieser Reihenfolge:
        1. Temporaere Vertretung aktiv (von <= datum <= bis)? -> vertreten_durch
        2. Delegation gesetzt? -> delegiert_an
        3. Sonst: self
        """
        if datum is None:
            datum = timezone.localdate()

        # Temporaere Vertretung pruefen
        if (
            self.vertreten_durch is not None
            and self.vertretung_von is not None
            and self.vertretung_bis is not None
            and self.vertretung_von <= datum <= self.vertretung_bis
        ):
            return self.vertreten_durch

        # Dauerhafte Delegation pruefen
        if self.delegiert_an is not None:
            return self.delegiert_an

        return self


class HRMitarbeiter(models.Model):
    """HR-Mitarbeiter mit Organisationszuordnung und Rolle."""

    ROLLE_CHOICES = [
        ("gf", "Geschaeftsfuehrung"),
        ("bereichsleiter", "Bereichsleiter/in"),
        ("abteilungsleiter", "Abteilungsleiter/in"),
        ("assistent", "Assistent/in (Stellvertretung)"),
        ("teamleiter", "Teamleiter/in"),
        ("mitarbeiter", "Mitarbeiter/in"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="hr_mitarbeiter",
        null=True,
        blank=True,
    )
    vorname = models.CharField(max_length=100)
    nachname = models.CharField(max_length=100)
    personalnummer = models.CharField(max_length=20, unique=True)
    rolle = models.CharField(max_length=20, choices=ROLLE_CHOICES, default="mitarbeiter")
    bereich = models.ForeignKey(
        Bereich,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mitarbeiter",
    )
    abteilung = models.ForeignKey(
        Abteilung,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mitarbeiter",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mitarbeiter",
    )
    vorgesetzter = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direkte_berichte",
        verbose_name="Vorgesetzter/Vorgesetzte",
    )
    # Nur fuer Assistenten: fuer wen sie Stellvertreter sind
    stellvertretung_fuer = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stellvertreter",
        verbose_name="Stellvertretung fuer",
    )
    stelle = models.OneToOneField(
        Stelle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hrmitarbeiter",
        verbose_name="Stelle",
    )
    eintrittsdatum = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["nachname", "vorname"]
        verbose_name = "HR-Mitarbeiter"
        verbose_name_plural = "HR-Mitarbeiter"
        permissions = [
            ("genehmigen_antraege", "Kann Antraege genehmigen/ablehnen"),
            ("view_zeiterfassung", "Kann Zeiterfassung einsehen"),
            ("view_stammdaten", "Kann Stammdaten einsehen"),
        ]

    def __str__(self):
        return f"{self.nachname}, {self.vorname} ({self.personalnummer})"

    @property
    def vollname(self):
        return f"{self.vorname} {self.nachname}"

    @property
    def ist_fuehrungskraft(self):
        return self.rolle in ("gf", "bereichsleiter", "abteilungsleiter", "teamleiter")

    @property
    def org_kuerzel(self):
        """Gibt das Kuerzel der Stelle zurueck, falls vorhanden."""
        if self.stelle:
            return self.stelle.kuerzel
        return None

    @property
    def stellen_email(self):
        """Gibt die Email-Adresse der Stelle zurueck, falls vorhanden."""
        if self.stelle:
            return self.stelle.email
        return None


class HierarchieSnapshot(models.Model):
    """Snapshot der Organisationshierarchie fuer Undo-Funktionalitaet.

    Speichert den Zustand aller OrgEinheiten und Stellen als JSON
    vor jeder Aenderung. Ermoeglicht Rueckgaengigmachen von Hierarchie-Aenderungen.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Erstellt von",
    )
    snapshot_data = models.JSONField(
        verbose_name="Snapshot-Daten",
        help_text="JSON mit OrgEinheiten und Stellen Hierarchie",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hierarchie-Snapshot"
        verbose_name_plural = "Hierarchie-Snapshots"

    def __str__(self):
        return f"Snapshot vom {self.created_at.strftime('%d.%m.%Y %H:%M')}"


class Projektgruppe(models.Model):
    """Temporaere, abteilungsubergreifende Projektgruppe.

    Projektgruppen sind zeitlich begrenzte Teams die Mitarbeiter
    aus verschiedenen OrgEinheiten zusammenbringen um an einem
    gemeinsamen Projekt zu arbeiten.
    """

    STATUS_AKTIV = "aktiv"
    STATUS_ABGESCHLOSSEN = "abgeschlossen"
    STATUS_PAUSIERT = "pausiert"
    STATUS_ABGEBROCHEN = "abgebrochen"

    STATUS_CHOICES = [
        (STATUS_AKTIV, "Aktiv"),
        (STATUS_ABGESCHLOSSEN, "Abgeschlossen"),
        (STATUS_PAUSIERT, "Pausiert"),
        (STATUS_ABGEBROCHEN, "Abgebrochen"),
    ]

    name = models.CharField(
        max_length=200, verbose_name="Projektname", help_text="Name der Projektgruppe"
    )
    kuerzel = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Kuerzel",
        help_text="Eindeutiges Kuerzel (z.B. PROJ-2025-01)",
    )
    beschreibung = models.TextField(
        blank=True, verbose_name="Beschreibung", help_text="Ziele und Aufgaben"
    )

    # Zeitraum
    start_datum = models.DateField(
        verbose_name="Startdatum", help_text="Projektstart"
    )
    end_datum = models.DateField(
        null=True,
        blank=True,
        verbose_name="Enddatum (geplant)",
        help_text="Geplantes Projektende",
    )
    tatsaechliches_end_datum = models.DateField(
        null=True,
        blank=True,
        verbose_name="Enddatum (tatsaechlich)",
        help_text="Tatsaechliches Projektende",
    )

    # Team
    leiter = models.ForeignKey(
        "HRMitarbeiter",
        on_delete=models.PROTECT,
        related_name="geleitete_projekte",
        verbose_name="Projektleiter/in",
        help_text="Verantwortliche Person fuer dieses Projekt",
    )
    stellvertreter = models.ForeignKey(
        "HRMitarbeiter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stellvertretende_projekte",
        verbose_name="Stellvertreter/in",
        help_text="Vertretung bei Abwesenheit",
    )
    mitglieder = models.ManyToManyField(
        "HRMitarbeiter",
        related_name="projektgruppen",
        blank=True,
        verbose_name="Mitglieder",
        help_text="Alle Projektmitglieder",
    )

    # Status & Metadata
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AKTIV,
        verbose_name="Status",
    )
    prioritaet = models.IntegerField(
        default=5,
        verbose_name="Prioritaet",
        help_text="1 = hoechste Prioritaet, 10 = niedrigste",
    )

    # Audit
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erstellte_projekte",
        verbose_name="Erstellt von",
    )

    class Meta:
        ordering = ["-prioritaet", "start_datum"]
        verbose_name = "Projektgruppe"
        verbose_name_plural = "Projektgruppen"

    def __str__(self):
        return f"{self.kuerzel} - {self.name}"

    @property
    def ist_aktiv(self):
        """Prueft ob das Projekt aktuell aktiv ist."""
        return self.status == self.STATUS_AKTIV

    @property
    def ist_abgeschlossen(self):
        """Prueft ob das Projekt abgeschlossen ist."""
        return self.status == self.STATUS_ABGESCHLOSSEN

    @property
    def laufzeit_tage(self):
        """Berechnet die bisherige Laufzeit in Tagen."""
        if self.tatsaechliches_end_datum:
            return (self.tatsaechliches_end_datum - self.start_datum).days
        return (timezone.now().date() - self.start_datum).days

    @property
    def mitglieder_anzahl(self):
        """Anzahl der Projektmitglieder."""
        return self.mitglieder.count()

    def team_nach_org(self):
        """Gruppiert Mitglieder nach OrgEinheit fuer Uebersicht."""
        result = {}
        for mitglied in self.mitglieder.select_related("stelle__org_einheit").all():
            if mitglied.stelle:
                org_name = mitglied.stelle.org_einheit.bezeichnung
                if org_name not in result:
                    result[org_name] = []
                result[org_name].append(mitglied)
        return result
