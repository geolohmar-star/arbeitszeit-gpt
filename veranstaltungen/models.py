import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Feier(models.Model):
    """Eine Veranstaltung (Sommerfest, Weihnachtsfeier, Teamausflug etc.).

    Zeitgutschrift wird als Sammelliste erstellt (nicht als Einzeleintraege).
    Vorbereitungsteam hat eigene Stunden und eigenen Faktor.
    """

    ART_CHOICES = [
        ("sommerfest", "Sommerfest"),
        ("weihnachtsfeier", "Weihnachtsfeier"),
        ("teamausflug", "Teamausflug"),
        ("jubilaeum", "Jubilaeum"),
        ("sonstiges", "Sonstiges"),
    ]

    REICHWEITE_CHOICES = [
        ("abteilung", "Abteilung"),
        ("bereich", "Bereich"),
        ("unternehmen", "Unternehmen"),
    ]

    STATUS_CHOICES = [
        ("geplant", "Geplant"),
        ("anmeldung_offen", "Anmeldung offen"),
        ("anmeldung_geschlossen", "Anmeldung geschlossen"),
        ("abgeschlossen", "Abgeschlossen"),
        ("storniert", "Storniert"),
    ]

    # Grunddaten
    abteilung = models.ForeignKey(
        "hr.Abteilung",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="veranstaltungen",
        verbose_name="Abteilung",
    )
    anmeldeschluss = models.DateField(
        null=True,
        blank=True,
        verbose_name="Anmeldeschluss",
    )
    art = models.CharField(
        max_length=30,
        choices=ART_CHOICES,
        default="sonstiges",
        verbose_name="Art der Veranstaltung",
    )
    bereich = models.ForeignKey(
        "hr.Bereich",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="veranstaltungen",
        verbose_name="Bereich",
    )
    datum = models.DateField(verbose_name="Datum")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_veranstaltungen",
        verbose_name="Erstellt von",
    )
    ort = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Ort",
    )
    reichweite = models.CharField(
        max_length=20,
        choices=REICHWEITE_CHOICES,
        default="abteilung",
        verbose_name="Reichweite",
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="geplant",
        verbose_name="Status",
    )
    titel = models.CharField(max_length=200, verbose_name="Titel")
    uhrzeit_bis = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Uhrzeit bis",
    )
    uhrzeit_von = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Uhrzeit von",
    )
    verantwortlicher = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verantwortete_veranstaltungen",
        verbose_name="Verantwortlicher",
    )

    # Zeitgutschrift Teilnehmer
    gutschrift_faktor = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        verbose_name="Gutschrift-Faktor (Teilnehmer)",
        help_text="Beispiel: 0.5 = halbe Vergütung der Veranstaltungsdauer",
    )
    gutschrift_stunden = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Gutschrift-Stunden (Teilnehmer)",
        help_text="Stunden die als Zeitgutschrift angerechnet werden.",
    )

    # Zeitgutschrift Vorbereitungsteam (eigene Berechnung)
    vorbereitung_faktor = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        verbose_name="Faktor (Vorbereitungsteam)",
    )
    vorbereitung_stunden = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Stunden (Vorbereitungsteam)",
        help_text="Separate Stunden für das Vorbereitungsteam.",
    )

    class Meta:
        ordering = ["-datum", "titel"]
        verbose_name = "Veranstaltung"
        verbose_name_plural = "Veranstaltungen"

    def __str__(self):
        return f"{self.titel} ({self.datum})"

    @property
    def gutschrift_teilnehmer_gesamt(self):
        """Zeitgutschrift pro Teilnehmer (Stunden × Faktor)."""
        return self.gutschrift_stunden * self.gutschrift_faktor

    @property
    def gutschrift_vorbereitung_gesamt(self):
        """Zeitgutschrift pro Vorbereitungsmitglied (Stunden × Faktor)."""
        return self.vorbereitung_stunden * self.vorbereitung_faktor

    @property
    def anmeldung_offen(self):
        """True wenn Anmeldung moeglich ist."""
        if self.status != "anmeldung_offen":
            return False
        if self.anmeldeschluss and self.anmeldeschluss < timezone.localdate():
            return False
        return True


class FeierteilnahmeAnmeldung(models.Model):
    """Anmeldung eines Mitarbeiters zu einer Veranstaltung."""

    feier = models.ForeignKey(
        Feier,
        on_delete=models.CASCADE,
        related_name="anmeldungen",
        verbose_name="Veranstaltung",
    )
    ist_gast = models.BooleanField(
        default=False,
        verbose_name="Gast",
        help_text="Externer Gast (kein Mitarbeiter).",
    )
    ist_vorbereitungsteam = models.BooleanField(
        default=False,
        verbose_name="Vorbereitungsteam",
    )
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.CASCADE,
        related_name="veranstaltungsanmeldungen",
        verbose_name="Mitarbeiter",
    )
    angemeldet_am = models.DateTimeField(auto_now_add=True)
    teilnahme_bestaetigt = models.BooleanField(
        default=False,
        verbose_name="Teilnahme bestaetigt",
    )
    bestaetigt_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bestaetigt am",
    )
    bestaetigt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bestaetigte_anmeldungen",
        verbose_name="Bestaetigt von",
    )
    bemerkung = models.TextField(
        blank=True,
        verbose_name="Bemerkung",
    )

    class Meta:
        ordering = ["feier", "mitarbeiter"]
        unique_together = ["feier", "mitarbeiter"]
        verbose_name = "Teilnahmeanmeldung"
        verbose_name_plural = "Teilnahmeanmeldungen"

    def __str__(self):
        return f"{self.mitarbeiter} @ {self.feier}"

    @property
    def gutschrift_stunden(self):
        """Berechnet die Zeitgutschrift fuer diese Anmeldung."""
        if self.ist_vorbereitungsteam:
            return self.feier.gutschrift_vorbereitung_gesamt
        return self.feier.gutschrift_teilnehmer_gesamt


class FeierteilnahmeGutschrift(models.Model):
    """Sammeldokument fuer die Zeitgutschrift einer Veranstaltung.

    Wird vom Zeiterfassungsteam genehmigt und abgearbeitet.
    Enthaelt alle bestaetigen Teilnehmer als PDF-Sammelliste.
    """

    STATUS_CHOICES = [
        ("entwurf", "Entwurf"),
        ("eingereicht", "Eingereicht"),
        ("bearbeitet", "Bearbeitet"),
        ("abgelehnt", "Abgelehnt"),
    ]

    eingereicht_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Eingereicht am",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_gutschriften",
        verbose_name="Erstellt von",
    )
    feier = models.OneToOneField(
        Feier,
        on_delete=models.CASCADE,
        related_name="gutschrift_dokument",
        verbose_name="Veranstaltung",
    )
    bemerkung = models.TextField(
        blank=True,
        verbose_name="Bemerkung",
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
        related_name="veranstaltungs_gutschriften",
        verbose_name="Workflow-Instanz",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Zeitgutschrift-Sammelliste"
        verbose_name_plural = "Zeitgutschrift-Sammellisten"

    def __str__(self):
        return f"Gutschrift: {self.feier}"

    @property
    def antragsteller(self):
        """Ersteller der Gutschrift – wird vom Workflow-Engine genutzt um Stelle aufzuloesen."""
        return self.erstellt_von

    def get_betreff(self):
        """Betreffzeile fuer Workflow und Signatur."""
        return f"Veranstaltungs-Gutschrift – {self.feier.titel} ({self.feier.datum})"

    def teilnehmer_bestaetigt(self):
        """Gibt alle bestaetigten Teilnehmer zurueck (kein Vorbereitungsteam)."""
        return self.feier.anmeldungen.filter(
            teilnahme_bestaetigt=True,
            ist_vorbereitungsteam=False,
        ).select_related("mitarbeiter", "mitarbeiter__stelle")

    def vorbereitungsteam_bestaetigt(self):
        """Gibt alle bestaetigten Vorbereitungsmitglieder zurueck."""
        return self.feier.anmeldungen.filter(
            teilnahme_bestaetigt=True,
            ist_vorbereitungsteam=True,
        ).select_related("mitarbeiter", "mitarbeiter__stelle")

    def archiviere_in_dms(self, kategorie_id):
        """Legt ein DMS-Dokument fuer diese Gutschrift an (idempotent).

        Bevorzugt vorhandene SignaturJob-PDF-Bytes; faellt auf WeasyPrint zurueck.
        """
        from dms.models import Dokument, DokumentKategorie
        from dms.services import speichere_dokument, suchvektor_befuellen

        feier = self.feier
        kategorie = DokumentKategorie.objects.filter(pk=kategorie_id).first()
        titel = f"VE-Gutschrift {feier.titel} {feier.datum}"
        dateiname = (
            f"VE-{self.pk}_{feier.titel}_{feier.datum}.pdf"
            .replace(" ", "_")
        )

        pdf_bytes = self._pdf_bytes_holen()
        if not pdf_bytes:
            logger.warning(
                "DMS-Archivierung: keine PDF-Bytes fuer FeierteilnahmeGutschrift pk=%s", self.pk
            )
            return None

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
                f"Zeitgutschrift-Sammelliste – {feier.get_art_display()} – "
                f"{feier.titel} ({feier.datum})"
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
                    content_type="feierteilnahmegutschrift",
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

            feier = self.feier
            teilnehmer = self.teilnehmer_bestaetigt()
            vorbereitungsteam = self.vorbereitungsteam_bestaetigt()
            teilnehmer_gesamt = feier.gutschrift_teilnehmer_gesamt * teilnehmer.count()
            vorbereitung_gesamt = feier.gutschrift_vorbereitung_gesamt * vorbereitungsteam.count()
            ctx = {
                "feier": feier,
                "gutschrift": self,
                "teilnehmer": teilnehmer,
                "vorbereitungsteam": vorbereitungsteam,
                "workflow_tasks": [],
                "teilnehmer_gesamt_stunden": teilnehmer_gesamt,
                "vorbereitung_gesamt_stunden": vorbereitung_gesamt,
                "gesamt_stunden": teilnehmer_gesamt + vorbereitung_gesamt,
                "jetzt": tz.now(),
            }
            html_string = render_to_string("veranstaltungen/pdf/gutschrift_pdf.html", ctx)
            host = getattr(settings, "SITE_URL", None) or (
                f"http://{settings.ALLOWED_HOSTS[0]}"
                if settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS[0] != "*"
                else "http://localhost:8000"
            )
            return HTML(string=html_string, base_url=host).write_pdf()
        except Exception as exc:
            logger.warning(
                "WeasyPrint-Fallback fehlgeschlagen fuer VE pk=%s: %s", self.pk, exc
            )
            return None
