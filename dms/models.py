"""
DMS – Dokumentenmanagementsystem (PRIMA)

Zwei Dokumentenklassen:
  Klasse 1 – OFFEN:    Betriebsanweisungen, Formulare, Protokolle
                        PostgreSQL GIN-Volltext-Index (FTS)
  Klasse 2 – SENSIBEL: Personalakten, Lohnunterlagen, Zeugnisse
                        AES-256-GCM verschluesselt (DMS_VERSCHLUESSEL_KEY)

Alle Inhalte als BinaryField – kein Dateisystem, kein Railway-Ephemeral-FS-Problem.
"""
import logging

from django.contrib.auth.models import User
from django.db import models

logger = logging.getLogger(__name__)


class DokumentKategorie(models.Model):
    """Hierarchische Kategorie fuer DMS-Dokumente.

    Beispiele: Betriebsanweisungen > Sicherheit, Personalakten > Zeugnisse
    """

    beschreibung = models.CharField(
        max_length=500, blank=True, verbose_name="Beschreibung"
    )
    elternkategorie = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unterkategorien",
        verbose_name="Elternkategorie",
    )
    klasse = models.CharField(
        max_length=10,
        choices=[("offen", "Offen (Volltext)"), ("sensibel", "Sensibel (verschluesselt)")],
        default="offen",
        verbose_name="Dokumentenklasse",
    )
    name = models.CharField(max_length=100, verbose_name="Name")
    sortierung = models.PositiveIntegerField(default=0, verbose_name="Sortierung")

    class Meta:
        ordering = ["sortierung", "name"]
        verbose_name = "Dokumentkategorie"
        verbose_name_plural = "Dokumentkategorien"

    def __str__(self):
        if self.elternkategorie:
            return f"{self.elternkategorie.name} > {self.name}"
        return self.name


class DokumentTag(models.Model):
    """Freies Tag-Label fuer Dokumente."""

    farbe = models.CharField(
        max_length=7, default="#6c757d", verbose_name="Farbe (Hex)"
    )
    name = models.CharField(max_length=50, unique=True, verbose_name="Name")

    class Meta:
        ordering = ["name"]
        verbose_name = "Dokument-Tag"
        verbose_name_plural = "Dokument-Tags"

    def __str__(self):
        return self.name


class Dokument(models.Model):
    """Zentrales DMS-Dokument – eine Klasse fuer beide Dokumentenklassen.

    Klasse 1 (offen):
      - inhalt_roh befuellt, inhalt_verschluesselt leer
      - suchvektor wird befuellt (GIN-FTS)

    Klasse 2 (sensibel):
      - inhalt_verschluesselt befuellt (AES-256-GCM), inhalt_roh leer
      - suchvektor leer (kein FTS-Index auf sensible Daten)
    """

    # ------------------------------------------------------------------
    # Identifikation
    # ------------------------------------------------------------------
    dateiname = models.CharField(max_length=255, verbose_name="Dateiname")
    dateityp = models.CharField(max_length=100, verbose_name="MIME-Typ")
    groesse_bytes = models.IntegerField(verbose_name="Dateigroesse (Bytes)")
    titel = models.CharField(max_length=300, verbose_name="Titel")

    # ------------------------------------------------------------------
    # Klassifikation
    # ------------------------------------------------------------------
    kategorie = models.ForeignKey(
        DokumentKategorie,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dokumente",
        verbose_name="Kategorie",
    )
    klasse = models.CharField(
        max_length=10,
        choices=[("offen", "Offen"), ("sensibel", "Sensibel")],
        default="offen",
        verbose_name="Dokumentenklasse",
    )
    tags = models.ManyToManyField(
        DokumentTag, blank=True, related_name="dokumente", verbose_name="Tags"
    )

    # ------------------------------------------------------------------
    # Inhalt – gegenseitig exklusiv je nach Klasse
    # ------------------------------------------------------------------
    inhalt_roh = models.BinaryField(
        null=True, blank=True, verbose_name="Inhalt (unkryptiert, Klasse 1)"
    )
    inhalt_verschluesselt = models.BinaryField(
        null=True, blank=True, verbose_name="Inhalt (AES-256-GCM, Klasse 2)"
    )
    verschluessel_nonce = models.CharField(
        max_length=24,
        blank=True,
        verbose_name="AES-GCM Nonce (Hex)",
    )

    # ------------------------------------------------------------------
    # Volltext-Suchvektor (nur Klasse 1, befuellt via SQL-Trigger oder Service)
    # ------------------------------------------------------------------
    # Hinweis: SearchVectorField existiert nur bei django.contrib.postgres.
    # Wir speichern als TextField um SQLite-Kompatibilitaet zu wahren;
    # der GIN-Index wird separat als Raw-SQL-Migration angelegt.
    suchvektor = models.TextField(blank=True, editable=False, verbose_name="Suchvektor")

    # ------------------------------------------------------------------
    # Metadaten
    # ------------------------------------------------------------------
    beschreibung = models.TextField(blank=True, verbose_name="Beschreibung")
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    erstellt_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_dokumente",
        verbose_name="Erstellt von",
    )
    gueltig_bis = models.DateField(
        null=True, blank=True, verbose_name="Gueltig bis"
    )
    paperless_id = models.IntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="Paperless-ngx ID",
    )
    version = models.PositiveIntegerField(default=1, verbose_name="Version")

    # Sichtbarkeit: fuer welche User zugaenglich (leer = alle berechtigten)
    sichtbar_fuer = models.ManyToManyField(
        User,
        blank=True,
        related_name="sichtbare_dokumente",
        verbose_name="Sichtbar fuer",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"

    def __str__(self):
        return self.titel

    def groesse_lesbar(self):
        """Gibt die Dateigroesse in lesbarer Form zurueck."""
        if self.groesse_bytes < 1024:
            return f"{self.groesse_bytes} B"
        elif self.groesse_bytes < 1024 * 1024:
            return f"{self.groesse_bytes / 1024:.1f} KB"
        else:
            return f"{self.groesse_bytes / (1024 * 1024):.1f} MB"

    @property
    def ist_offen(self):
        return self.klasse == "offen"

    @property
    def ist_sensibel(self):
        return self.klasse == "sensibel"


DAUER_OPTIONEN = [
    (1, "1 Stunde"),
    (4, "4 Stunden"),
    (24, "1 Tag"),
    (72, "3 Tage"),
]


class DokumentZugriffsschluessel(models.Model):
    """Zeitlich begrenzter Zugriffsschluessel fuer sensible Dokumente (Klasse 2).

    Ablauf:
    1. User beantragt Zugriff (antrag_zeitpunkt, antrag_grund, gewuenschte_dauer_h)
    2. Staff genehmigt → genehmigt_von + genehmigt_am + gueltig_bis werden gesetzt
       Gleichzeitig: guardian assign_perm('dms.view_dokument_sensibel', user, dok)
    3. User kann im Zeitfenster downloaden (jeder Download → ZugriffsProtokoll)
    4. Staff kann Zugriff vorzeitig widerrufen → guardian remove_perm
    5. Nach Ablauf: kein Download mehr moeglich, Protokoll bleibt erhalten
    """

    STATUS_OFFEN = "offen"
    STATUS_GENEHMIGT = "genehmigt"
    STATUS_ABGELEHNT = "abgelehnt"
    STATUS_WIDERRUFEN = "widerrufen"
    STATUS_ABGELAUFEN = "abgelaufen"

    STATUS_CHOICES = [
        (STATUS_OFFEN, "Offen (wartet auf Genehmigung)"),
        (STATUS_GENEHMIGT, "Genehmigt"),
        (STATUS_ABGELEHNT, "Abgelehnt"),
        (STATUS_WIDERRUFEN, "Widerrufen"),
        (STATUS_ABGELAUFEN, "Abgelaufen"),
    ]

    antrag_grund = models.TextField(verbose_name="Begruendung des Antrags")
    antrag_zeitpunkt = models.DateTimeField(
        auto_now_add=True, verbose_name="Antrag gestellt am"
    )
    dokument = models.ForeignKey(
        Dokument,
        on_delete=models.CASCADE,
        related_name="zugriffsschluessel",
        verbose_name="Dokument",
    )
    genehmigt_am = models.DateTimeField(
        null=True, blank=True, verbose_name="Genehmigt am"
    )
    genehmigt_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="genehmigte_zugriffsschluessel",
        verbose_name="Genehmigt von",
    )
    gewuenschte_dauer_h = models.PositiveSmallIntegerField(
        choices=DAUER_OPTIONEN,
        default=4,
        verbose_name="Gewuenschte Zugriffsdauer",
    )
    gueltig_bis = models.DateTimeField(
        null=True, blank=True, verbose_name="Gueltig bis"
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_OFFEN,
        verbose_name="Status",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="dms_zugriffsschluessel",
        verbose_name="Antragsteller",
    )

    class Meta:
        ordering = ["-antrag_zeitpunkt"]
        verbose_name = "Dokument-Zugriffsschluessel"
        verbose_name_plural = "Dokument-Zugriffsschluessel"

    def __str__(self):
        return (
            f"{self.user.get_full_name() or self.user.username} – "
            f"{self.dokument.titel} – {self.get_status_display()}"
        )

    def ist_aktiv(self):
        """Prueft ob der Schluessel aktuell gueltig ist."""
        from django.utils import timezone
        return (
            self.status == self.STATUS_GENEHMIGT
            and self.gueltig_bis is not None
            and self.gueltig_bis > timezone.now()
        )

    ist_aktiv.boolean = True
    ist_aktiv.short_description = "Aktiv?"


class ZugriffsProtokoll(models.Model):
    """Unveraenderlicher Audit-Trail fuer alle DMS-Aktionen.

    Entspricht DSGVO Art. 5 Abs. 2 – Rechenschaftspflicht.
    Kein update(), kein delete() ueber normale Wege.
    """

    aktion = models.CharField(
        max_length=25,
        choices=[
            ("download", "Download"),
            ("vorschau", "Vorschau"),
            ("erstellt", "Erstellt"),
            ("geaendert", "Geaendert"),
            ("zugriff_beantragt", "Zugriff beantragt"),
            ("zugriff_genehmigt", "Zugriff genehmigt"),
            ("zugriff_abgelehnt", "Zugriff abgelehnt"),
            ("zugriff_widerrufen", "Zugriff widerrufen"),
        ],
        default="download",
        verbose_name="Aktion",
    )
    dokument = models.ForeignKey(
        Dokument,
        on_delete=models.CASCADE,
        related_name="zugriffe",
        verbose_name="Dokument",
    )
    ip_adresse = models.GenericIPAddressField(
        null=True, blank=True, verbose_name="IP-Adresse"
    )
    notiz = models.TextField(blank=True, verbose_name="Notiz (z.B. Grund, Dauer)")
    user = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="dms_zugriffe",
        verbose_name="User",
    )
    zeitpunkt = models.DateTimeField(auto_now_add=True, verbose_name="Zeitpunkt")

    class Meta:
        ordering = ["-zeitpunkt"]
        verbose_name = "Zugriffs-Protokoll"
        verbose_name_plural = "Zugriffs-Protokolle"

    def __str__(self):
        username = self.user.username if self.user else "unbekannt"
        return f"{username} – {self.aktion} – {self.dokument.titel} ({self.zeitpunkt:%d.%m.%Y %H:%M})"


    # DSGVO: kein delete() und kein update() via Manager erzwingen
    class Manager(models.Manager):
        def delete(self):
            raise PermissionError("Audit-Trail darf nicht geloescht werden.")

        def update(self, **kwargs):
            raise PermissionError("Audit-Trail darf nicht veraendert werden.")


class PaperlessImportLog(models.Model):
    """Protokolliert den Paperless-ngx Polling-Import.

    Speichert wann welches Paperless-Dokument importiert wurde
    um Duplikate zu verhindern.
    """

    dokument = models.ForeignKey(
        Dokument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paperless_imports",
        verbose_name="Importiertes Dokument",
    )
    fehler = models.TextField(blank=True, verbose_name="Fehlermeldung")
    importiert_am = models.DateTimeField(
        auto_now_add=True, verbose_name="Importiert am"
    )
    paperless_id = models.IntegerField(
        unique=True, verbose_name="Paperless-ngx Dokument-ID"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("ok", "Erfolgreich"),
            ("fehler", "Fehler"),
            ("uebersprungen", "Uebersprungen"),
        ],
        default="ok",
        verbose_name="Status",
    )

    class Meta:
        ordering = ["-importiert_am"]
        verbose_name = "Paperless-Import-Log"
        verbose_name_plural = "Paperless-Import-Logs"

    def __str__(self):
        return f"Paperless #{self.paperless_id} – {self.status} ({self.importiert_am:%d.%m.%Y})"
