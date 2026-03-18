import logging
from decimal import Decimal

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Sportgruppe(models.Model):
    """Eine regelmaessig stattfindende Betriebssport-Gruppe."""

    SPORTART_CHOICES = [
        ("fussball", "Fussball"),
        ("volleyball", "Volleyball"),
        ("basketball", "Basketball"),
        ("laufen", "Laufen / Joggen"),
        ("radfahren", "Radfahren"),
        ("schwimmen", "Schwimmen"),
        ("yoga", "Yoga / Meditation"),
        ("fitness", "Fitness / Krafttraining"),
        ("tischtennis", "Tischtennis"),
        ("sonstiges", "Sonstiges"),
    ]

    WOCHENTAG_CHOICES = [
        (0, "Montag"),
        (1, "Dienstag"),
        (2, "Mittwoch"),
        (3, "Donnerstag"),
        (4, "Freitag"),
        (5, "Samstag"),
        (6, "Sonntag"),
    ]

    STATUS_CHOICES = [
        ("aktiv", "Aktiv"),
        ("pausiert", "Pausiert"),
        ("aufgeloest", "Aufgeloest"),
    ]

    beschreibung = models.TextField(blank=True, verbose_name="Beschreibung")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gutschrift_stunden = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal("1.0"),
        verbose_name="Gutschrift-Stunden pro Einheit",
        help_text="Max. 1 Stunde pro Woche anrechenbar.",
    )
    mitglieder = models.ManyToManyField(
        "hr.HRMitarbeiter",
        through="SportgruppeMitglied",
        related_name="sportgruppen",
        blank=True,
        verbose_name="Mitglieder",
    )
    name = models.CharField(max_length=200, verbose_name="Name")
    ort_beschreibung = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Ort",
        help_text="z.B. Turnhalle Hauptgebaeude, Sportplatz Nord",
    )
    sportart = models.CharField(
        max_length=30,
        choices=SPORTART_CHOICES,
        verbose_name="Sportart",
    )
    standort = models.ForeignKey(
        "raumbuch.Standort",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sportgruppen",
        verbose_name="Standort",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="aktiv",
        verbose_name="Status",
    )
    uhrzeit_bis = models.TimeField(null=True, blank=True, verbose_name="Uhrzeit bis")
    uhrzeit_von = models.TimeField(null=True, blank=True, verbose_name="Uhrzeit von")
    verantwortlicher = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.PROTECT,
        related_name="geleitete_sportgruppen",
        verbose_name="Verantwortlicher",
    )
    wochentag = models.IntegerField(
        choices=WOCHENTAG_CHOICES,
        verbose_name="Wochentag",
    )

    class Meta:
        ordering = ["sportart", "name"]
        verbose_name = "Sportgruppe"
        verbose_name_plural = "Sportgruppen"

    def __str__(self):
        return f"{self.get_sportart_display()} – {self.name}"

    @property
    def wochentag_kurz(self):
        tage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        return tage[self.wochentag]


class SportgruppeMitglied(models.Model):
    """Through-Model fuer Sportgruppen-Mitgliedschaft (mit Beitrittsdatum)."""

    beigetreten_am = models.DateTimeField(auto_now_add=True)
    gruppe = models.ForeignKey(
        Sportgruppe,
        on_delete=models.CASCADE,
        related_name="mitgliedschaften",
    )
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.CASCADE,
        related_name="sport_mitgliedschaften",
    )

    class Meta:
        unique_together = [["gruppe", "mitarbeiter"]]
        verbose_name = "Sportgruppen-Mitglied"
        verbose_name_plural = "Sportgruppen-Mitglieder"

    def __str__(self):
        return f"{self.mitarbeiter} in {self.gruppe}"


class Sporteinheit(models.Model):
    """Eine konkrete Trainingseinheit (ein Termin)."""

    STATUS_CHOICES = [
        ("geplant", "Geplant"),
        ("stattgefunden", "Stattgefunden"),
        ("ausgefallen", "Ausgefallen"),
    ]

    datum = models.DateField(verbose_name="Datum")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_sporteinheiten",
        verbose_name="Erstellt von",
    )
    gruppe = models.ForeignKey(
        Sportgruppe,
        on_delete=models.CASCADE,
        related_name="einheiten",
        verbose_name="Gruppe",
    )
    notiz = models.TextField(blank=True, verbose_name="Notiz")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="geplant",
        verbose_name="Status",
    )

    class Meta:
        ordering = ["datum"]
        unique_together = [["gruppe", "datum"]]
        verbose_name = "Sporteinheit"
        verbose_name_plural = "Sporteinheiten"

    def __str__(self):
        return f"{self.gruppe} – {self.datum}"

    @property
    def kw(self):
        """Kalenderwoche der Einheit."""
        return self.datum.isocalendar()[1]


class Sportteilnahme(models.Model):
    """Selbst-Eintrag eines Mitarbeiters fuer eine Sporteinheit."""

    einheit = models.ForeignKey(
        Sporteinheit,
        on_delete=models.CASCADE,
        related_name="teilnahmen",
        verbose_name="Einheit",
    )
    markiert_am = models.DateTimeField(auto_now_add=True)
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.CASCADE,
        related_name="sport_teilnahmen",
        verbose_name="Mitarbeiter",
    )

    class Meta:
        unique_together = [["einheit", "mitarbeiter"]]
        verbose_name = "Sportteilnahme"
        verbose_name_plural = "Sportteilnahmen"

    def __str__(self):
        return f"{self.mitarbeiter} @ {self.einheit}"


class BetriebssportGutschrift(models.Model):
    """Monatliche Sammelliste fuer Betriebssport-Zeitgutschriften."""

    STATUS_CHOICES = [
        ("entwurf", "Entwurf"),
        ("eingereicht", "Eingereicht"),
        ("abgeschlossen", "Abgeschlossen"),
        ("abgelehnt", "Abgelehnt"),
    ]

    bemerkung = models.TextField(blank=True, verbose_name="Bemerkung")
    eingereicht_am = models.DateTimeField(
        null=True, blank=True, verbose_name="Eingereicht am"
    )
    einheiten = models.ManyToManyField(
        Sporteinheit,
        blank=True,
        related_name="gutschriften",
        verbose_name="Einheiten",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_bssport_gutschriften",
        verbose_name="Erstellt von",
    )
    gruppe = models.ForeignKey(
        Sportgruppe,
        on_delete=models.PROTECT,
        related_name="gutschriften",
        verbose_name="Gruppe",
    )
    monat = models.DateField(
        verbose_name="Monat",
        help_text="Erster Tag des abzurechnenden Monats (z.B. 2026-03-01).",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="entwurf",
        verbose_name="Status",
    )
    workflow_instance = models.ForeignKey(
        "workflow.WorkflowInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bs_gutschriften",
        verbose_name="Workflow-Instanz",
    )

    class Meta:
        ordering = ["-monat"]
        unique_together = [["gruppe", "monat"]]
        verbose_name = "Betriebssport-Gutschrift"
        verbose_name_plural = "Betriebssport-Gutschriften"

    def __str__(self):
        return f"BS-Gutschrift {self.gruppe} {self.monat:%m/%Y}"

    @property
    def antragsteller(self):
        """Fuer WorkflowEngine: Ersteller der Gutschrift."""
        return self.erstellt_von

    def archiviere_in_dms(self, kategorie_id):
        """Legt ein DMS-Dokument fuer diese Gutschrift an (idempotent).

        Bevorzugt vorhandene SignaturJob-PDF-Bytes; faellt auf WeasyPrint zurueck.
        """
        from dms.models import Dokument, DokumentKategorie
        from dms.services import speichere_dokument, suchvektor_befuellen

        kategorie = DokumentKategorie.objects.filter(pk=kategorie_id).first()
        titel = f"BS-Gutschrift {self.gruppe.name} {self.monat:%m/%Y}"
        dateiname = (
            f"BS-{self.pk}_{self.gruppe.name}_{self.monat:%Y-%m}.pdf"
            .replace(" ", "_")
        )

        pdf_bytes = self._pdf_bytes_holen()
        if not pdf_bytes:
            logger.warning(
                "DMS-Archivierung: keine PDF-Bytes fuer BetriebssportGutschrift pk=%s", self.pk
            )
            return None

        # Idempotent: vorhandenes Dokument aktualisieren
        bestehendes = Dokument.objects.filter(dateiname=dateiname).first()
        if bestehendes:
            speichere_dokument(bestehendes, pdf_bytes)
            bestehendes.groesse_bytes = len(pdf_bytes)
            if kategorie:
                bestehendes.kategorie = kategorie
            bestehendes.save()
            suchvektor_befuellen(bestehendes)
            return bestehendes

        dok = Dokument(
            titel=titel,
            dateiname=dateiname,
            dateityp="application/pdf",
            groesse_bytes=len(pdf_bytes),
            kategorie=kategorie,
            klasse="offen",
            beschreibung=(
                f"Betriebssport-Zeitgutschrift – {self.gruppe.name} – "
                f"{self.monat:%B %Y}"
            ),
            erstellt_von=(
                self.erstellt_von.user
                if self.erstellt_von and self.erstellt_von.user_id
                else None
            ),
        )
        speichere_dokument(dok, pdf_bytes)
        dok.save()
        suchvektor_befuellen(dok)
        return dok

    def _pdf_bytes_holen(self):
        """Gibt PDF-Bytes zurueck: bevorzugt signiertes PDF, sonst WeasyPrint."""
        try:
            from signatur.models import SignaturJob
            job = (
                SignaturJob.objects
                .filter(
                    content_type="betriebssportgutschrift",
                    object_id=self.pk,
                    status="completed",
                )
                .order_by("-erstellt_am")
                .first()
            )
            if job and job.signiertes_pdf:
                return bytes(job.signiertes_pdf)
        except Exception:
            pass
        try:
            from weasyprint import HTML
            from django.template.loader import render_to_string
            from django.conf import settings
            from django.utils import timezone as tz
            from .models import Sportteilnahme  # selbe App, kein Zirkularimport

            gruppe = self.gruppe
            einheiten = list(self.einheiten.order_by("datum"))
            mitglieder = list(
                gruppe.mitglieder.select_related("abteilung")
                .order_by("nachname", "vorname")
            )
            alle_teilnahmen = set(
                Sportteilnahme.objects.filter(einheit__in=einheiten)
                .values_list("einheit_id", "mitarbeiter_id")
            )
            teilnehmer_daten = []
            gesamt_stunden = 0
            for ma in mitglieder:
                anzahl = sum(
                    1 for e in einheiten
                    if (e.pk, ma.pk) in alle_teilnahmen and e.status == "stattgefunden"
                )
                stunden = gruppe.gutschrift_stunden * anzahl
                gesamt_stunden += stunden
                if anzahl > 0:
                    teilnehmer_daten.append({
                        "mitarbeiter": ma,
                        "anzahl_einheiten": anzahl,
                        "stunden": stunden,
                    })
            ctx = {
                "gutschrift": self,
                "gruppe": gruppe,
                "einheiten": einheiten,
                "teilnehmer_daten": teilnehmer_daten,
                "gesamt_stunden": gesamt_stunden,
                "workflow_tasks": [],
                "jetzt": tz.now(),
            }
            html_string = render_to_string("betriebssport/pdf/gutschrift_pdf.html", ctx)
            host = getattr(settings, "SITE_URL", None) or (
                f"http://{settings.ALLOWED_HOSTS[0]}"
                if settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS[0] != "*"
                else "http://localhost:8000"
            )
            return HTML(string=html_string, base_url=host).write_pdf()
        except Exception as exc:
            logger.warning("WeasyPrint-Fallback fehlgeschlagen fuer BS pk=%s: %s", self.pk, exc)
            return None

    def get_betreff(self):
        """Betreffzeile fuer Workflow und PDF."""
        return f"Betriebssport – {self.gruppe} – {self.monat:%B %Y}"

    @property
    def monat_str(self):
        """Monat als URL-tauglicher String (YYYY-MM)."""
        return self.monat.strftime("%Y-%m")
