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
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
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
    # Volltext-Suchvektor (nur Klasse 1)
    # ------------------------------------------------------------------
    # PostgreSQL tsvector-Spalte mit GIN-Index.
    # Wird befuellt durch suchvektor_befuellen() in services.py:
    #   - Titel (Gewicht A), Beschreibung (Gewicht B), OCR-Text (Gewicht C)
    # Sensible Dokumente (Klasse 2): bleibt leer (kein FTS auf verschluesselte Daten).
    suchvektor = SearchVectorField(null=True, blank=True, editable=False, verbose_name="Suchvektor")

    # OCR-Text aus Paperless-ngx (nur Klasse 1, nur bei Paperless-Import).
    # Wird fuer den Suchvektor verwendet und ermoeglicht spaetere Reindizierung
    # ohne erneuten Paperless-API-Aufruf.
    ocr_text = models.TextField(blank=True, editable=False, verbose_name="OCR-Text")

    # ------------------------------------------------------------------
    # Metadaten
    # ------------------------------------------------------------------
    beschreibung = models.TextField(blank=True, verbose_name="Beschreibung")
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    eigentuemereinheit = models.ForeignKey(
        "hr.OrgEinheit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dms_dokumente",
        verbose_name="Eigentuemer-OrgEinheit",
        help_text="Abteilung die fuer dieses Dokument zustaendig ist.",
    )
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

    # ------------------------------------------------------------------
    # Loeschkennzeichen (gesetzt durch DMS-Admin, freigegeben durch DSB-Team)
    # ------------------------------------------------------------------
    loeschen_am = models.DateField(
        null=True, blank=True, verbose_name="Loeschen am",
        help_text="Geplantes Loeschdatum (nur wirksam nach DSB-Freigabe).",
    )
    loeschen_begruendung = models.TextField(
        blank=True, verbose_name="Loeschbegruendung"
    )
    loeschen_beantragt_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dms_loeschantraege",
        verbose_name="Loeschantrag von",
    )
    loeschen_genehmigt = models.BooleanField(
        default=False, verbose_name="Loeschung genehmigt"
    )

    ist_persoenlich = models.BooleanField(
        default=False,
        verbose_name="Persoenliche Ablage",
        help_text="True = Dokument gehoert zur persoenlichen Ablage des Erstellers.",
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

    # Workflow-Vorschlag: gesetzt beim Paperless-Import wenn eine Regel greift.
    # Null = kein Vorschlag, gesetzt = empfohlenes Template wird im Detail-Banner
    # angezeigt. Nach dem Starten des Workflows bleibt das Feld gesetzt (History).
    workflow_vorschlag = models.ForeignKey(
        "workflow.WorkflowTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vorgeschlagene_dokumente",
        verbose_name="Workflow-Vorschlag",
        help_text="Automatisch vorgeschlagener Workflow (gesetzt beim Paperless-Import).",
    )
    # Ob der Vorschlag bereits bearbeitet wurde (Workflow gestartet oder manuell verworfen)
    workflow_vorschlag_erledigt = models.BooleanField(
        default=False,
        verbose_name="Workflow-Vorschlag erledigt",
    )
    # Laufende Workflow-Instanz fuer dieses Dokument (gesetzt durch WorkflowTrigger)
    workflow_instance = models.ForeignKey(
        "workflow.WorkflowInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dms_dokumente",
        verbose_name="Workflow-Instanz",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"
        indexes = [
            GinIndex(fields=["suchvektor"], name="dms_dokument_suchvektor_gin2"),
        ]

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

    def loeschfreigabe_setzen(self):
        """Setzt loeschen_genehmigt=True.

        Wird durch den Workflow-Auto-Schritt 'loeschung_freigeben' aufgerufen,
        nachdem das DSB-Team den Loeschantrag genehmigt hat.
        """
        self.loeschen_genehmigt = True
        self.save(update_fields=["loeschen_genehmigt"])

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
            ("onlyoffice_bearbeitet", "In OnlyOffice bearbeitet"),
            ("version_wiederhergestellt", "Version wiederhergestellt"),
            ("api_upload", "API-Upload (externes System)"),
            ("api_download", "API-Download (externes System)"),
            ("loeschen", "Loeschantrag gestellt"),
            ("geloescht", "Dokument geloescht"),
        ],
        default="download",
        verbose_name="Aktion",
    )
    dokument = models.ForeignKey(
        Dokument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="zugriffe",
        verbose_name="Dokument",
    )
    # Sicherungskopie des Titels – bleibt erhalten wenn das Dokument geloescht wird
    dokument_titel = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Dokument-Titel (Sicherungskopie)",
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


class DokumentVersion(models.Model):
    """Versionsverlauf eines DMS-Dokuments.

    Jede Bearbeitung (OnlyOffice-Callback, manueller Upload) erzeugt einen
    neuen Eintrag. Die aktuelle Version ist immer die mit der hoechsten version_nr.
    Aeltere Versionen bleiben unveraendert erhalten (Revisionssicherheit).
    """

    dateiname = models.CharField(max_length=255, verbose_name="Dateiname")
    dokument = models.ForeignKey(
        Dokument,
        on_delete=models.CASCADE,
        related_name="versionen",
        verbose_name="Dokument",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    erstellt_von = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erstellte_versionen",
        verbose_name="Erstellt von",
    )
    groesse_bytes = models.IntegerField(verbose_name="Dateigroesse (Bytes)")
    inhalt_roh = models.BinaryField(
        null=True, blank=True, verbose_name="Inhalt (unkryptiert)"
    )
    inhalt_verschluesselt = models.BinaryField(
        null=True, blank=True, verbose_name="Inhalt (AES-256-GCM)"
    )
    kommentar = models.CharField(
        max_length=300, blank=True, verbose_name="Kommentar"
    )
    verschluessel_nonce = models.CharField(
        max_length=24, blank=True, verbose_name="AES-GCM Nonce (Hex)"
    )
    version_nr = models.PositiveIntegerField(verbose_name="Versionsnummer")

    class Meta:
        ordering = ["-version_nr"]
        unique_together = [("dokument", "version_nr")]
        verbose_name = "Dokument-Version"
        verbose_name_plural = "Dokument-Versionen"

    def __str__(self):
        return f"{self.dokument.titel} v{self.version_nr} ({self.erstellt_am:%d.%m.%Y})"

    def groesse_lesbar(self):
        """Gibt die Dateigroesse in lesbarer Form zurueck."""
        if self.groesse_bytes < 1024:
            return f"{self.groesse_bytes} B"
        elif self.groesse_bytes < 1024 * 1024:
            return f"{self.groesse_bytes / 1024:.1f} KB"
        return f"{self.groesse_bytes / (1024 * 1024):.1f} MB"


class ApiToken(models.Model):
    """API-Token fuer externe Systeme die auf das DMS zugreifen (SAP, Paperless, etc.).

    Externe Systeme senden den Token im Authorization-Header:
        Authorization: Bearer <token>

    Jedes System erhaelt einen eigenen Token – so kann der Zugriff einzeln
    gesperrt, auditiert und erneuert werden ohne andere Systeme zu beeinflussen.
    """

    aktiv = models.BooleanField(default=True, verbose_name="Aktiv")
    bezeichnung = models.CharField(max_length=200, verbose_name="Bezeichnung")
    erlaubte_klassen = models.CharField(
        max_length=10,
        choices=[
            ("offen", "Nur offen (Klasse 1)"),
            ("beide", "Offen + Sensibel (Klasse 1+2)"),
        ],
        default="offen",
        verbose_name="Erlaubte Dokumentenklassen",
        help_text="Sensibel nur freischalten wenn das Fremdsystem verschluesselt uebertraegt.",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    letzte_nutzung = models.DateTimeField(
        null=True, blank=True, verbose_name="Letzte Nutzung"
    )
    system = models.CharField(
        max_length=100, blank=True, verbose_name="System (z.B. SAP S/4HANA 2023)"
    )
    token = models.CharField(max_length=64, unique=True, verbose_name="Token (hex)")

    class Meta:
        ordering = ["bezeichnung"]
        verbose_name = "API-Token"
        verbose_name_plural = "API-Tokens"

    def __str__(self):
        return f"{self.bezeichnung} ({self.system or 'kein System'})"

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)


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


class PaperlessWorkflowRegel(models.Model):
    """Konfigurierbare Mapping-Regel: Paperless-Dokumenttyp oder Tag → Workflow-Template.

    Beim Paperless-Import wird jede Regel geprueft. Die erste Regel mit einem
    Treffer (Dokumenttyp-Name ODER Tag-Name) setzt das Feld
    Dokument.workflow_vorschlag auf das zugeordnete Template.

    Mehrere Regeln werden nach 'prioritaet' (aufsteigend) sortiert – niedrige
    Zahl = hoehere Prioritaet.

    Beispiel:
        Dokumenttyp = "Rechnung", Template = "Rechnungspruefung"
        Tag         = "elektro",  Template = "Rechnungspruefung Elektro"
    """

    TREFFER_DOKUMENTTYP = "dokumenttyp"
    TREFFER_TAG = "tag"

    TREFFER_CHOICES = [
        (TREFFER_DOKUMENTTYP, "Paperless Dokumenttyp (Name)"),
        (TREFFER_TAG, "Paperless Tag (Name)"),
    ]

    bezeichnung = models.CharField(
        max_length=200,
        verbose_name="Bezeichnung",
        help_text="Interne Beschreibung der Regel, z.B. 'Eingangsrechnungen Elektro'.",
    )
    treffer_typ = models.CharField(
        max_length=20,
        choices=TREFFER_CHOICES,
        default=TREFFER_DOKUMENTTYP,
        verbose_name="Treffer-Typ",
        help_text="Ob der Name als Paperless-Dokumenttyp oder als Tag verglichen wird.",
    )
    paperless_name = models.CharField(
        max_length=200,
        verbose_name="Paperless-Name",
        help_text=(
            "Name des Dokumenttyps oder Tags in Paperless-ngx (Gross/Kleinschreibung egal). "
            "Beispiel: 'Rechnung' oder 'elektro'."
        ),
    )
    workflow_template = models.ForeignKey(
        "workflow.WorkflowTemplate",
        on_delete=models.CASCADE,
        related_name="paperless_regeln",
        verbose_name="Workflow-Template",
        help_text="Dieses Template wird als Vorschlag gesetzt wenn die Regel greift.",
    )
    prioritaet = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="Prioritaet (niedrig = zuerst geprueft)",
    )
    aktiv = models.BooleanField(default=True, verbose_name="Aktiv")

    class Meta:
        ordering = ["prioritaet", "bezeichnung"]
        verbose_name = "Paperless-Workflow-Regel"
        verbose_name_plural = "Paperless-Workflow-Regeln"

    def __str__(self):
        return f"{self.bezeichnung} [{self.get_treffer_typ_display()}: {self.paperless_name}]"
