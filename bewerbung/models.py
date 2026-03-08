import random
import string

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class EinladungsCode(models.Model):
    """5-stelliger Einladungscode fuer Bewerber.

    HR gibt den Code vor Ort an den Bewerber weiter (spaeter per SMS).
    Ohne gueltigen Code kann kein Bewerbungsbogen ausgefuellt werden.
    """

    STATUS_VERFUEGBAR = "verfuegbar"
    STATUS_AUSGEGEBEN = "ausgegeben"
    STATUS_VERWENDET = "verwendet"

    STATUS_CHOICES = [
        (STATUS_VERFUEGBAR, "Verfuegbar"),
        (STATUS_AUSGEGEBEN, "Ausgegeben (noch nicht benutzt)"),
        (STATUS_VERWENDET, "Verwendet"),
    ]

    code = models.CharField(max_length=5, unique=True, verbose_name="Code")
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_VERFUEGBAR, verbose_name="Status"
    )
    ausgegeben_an_name = models.CharField(
        max_length=100, blank=True, verbose_name="Ausgegeben an (Name)"
    )
    ausgegeben_an_telefon = models.CharField(
        max_length=30, blank=True, verbose_name="Ausgegeben an (Telefon)"
    )
    ausgegeben_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ausgegebene_codes",
        verbose_name="Ausgegeben von (HR)",
    )
    ausgegeben_am = models.DateTimeField(null=True, blank=True, verbose_name="Ausgegeben am")
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "code"]
        verbose_name = "Einladungscode"
        verbose_name_plural = "Einladungscodes"

    def __str__(self):
        return f"{self.code} ({self.get_status_display()})"

    @classmethod
    def generiere_batch(cls, anzahl: int = 100) -> int:
        """Generiert n neue eindeutige 5-stellige Codes (A-Z0-9, ohne O/0/I/1).

        Gibt die Anzahl tatsaechlich erstellter Codes zurueck.
        """
        zeichen = [c for c in string.ascii_uppercase + string.digits if c not in "OI01"]
        erstellt = 0
        versuche = 0
        while erstellt < anzahl and versuche < anzahl * 10:
            versuche += 1
            code = "".join(random.choices(zeichen, k=5))
            if not cls.objects.filter(code=code).exists():
                cls.objects.create(code=code)
                erstellt += 1
        return erstellt


class Bewerbung(models.Model):
    """Bewerbungsbogen – wird am Intranet-PC vom Bewerber ausgefuellt.

    Kein Login noetig. HR begleitet den Prozess.
    Bei Einstellung: Daten fliessen in HRMitarbeiter + Personalstammdaten.
    Bei Ablehnung: Hard-Delete ALLER Daten (DSGVO-konform).
    """

    STATUS_EINGEGANGEN = "eingegangen"
    STATUS_FAKTENCHECK = "faktencheck"
    STATUS_GESPRAECH = "gespraech_eingeladen"
    STATUS_TAUGLICHKEIT = "tauglichkeitstest"
    STATUS_ZUSAGE = "zusage"
    STATUS_ABGELEHNT = "abgelehnt"

    STATUS_CHOICES = [
        (STATUS_EINGEGANGEN, "Eingegangen"),
        (STATUS_FAKTENCHECK, "Faktencheck"),
        (STATUS_TAUGLICHKEIT, "Tauglichkeitstest"),
        (STATUS_ZUSAGE, "Zusage erteilt"),
        (STATUS_ABGELEHNT, "Abgelehnt"),
    ]

    # Status-Reihenfolge fuer Weiterschalten (nur vorwaerts)
    STATUS_REIHENFOLGE = [
        STATUS_EINGEGANGEN,
        STATUS_FAKTENCHECK,
        STATUS_TAUGLICHKEIT,
        STATUS_ZUSAGE,
    ]

    ANREDE_CHOICES = [
        ("herr", "Herr"),
        ("frau", "Frau"),
        ("divers", "Divers"),
        ("keine", "Keine Angabe"),
    ]
    FAMILIENSTAND_CHOICES = [
        ("ledig", "Ledig"),
        ("verheiratet", "Verheiratet"),
        ("geschieden", "Geschieden"),
        ("verwitwet", "Verwitwet"),
        ("partnerschaft", "Eingetragene Lebenspartnerschaft"),
    ]
    KONFESSION_CHOICES = [
        ("evangelisch", "Evangelisch"),
        ("katholisch", "Katholisch"),
        ("keine", "Keine / Sonstige"),
    ]
    STEUERKLASSE_CHOICES = [
        ("1", "I"), ("2", "II"), ("3", "III"),
        ("4", "IV"), ("5", "V"), ("6", "VI"),
    ]
    KRANKENVERSICHERUNG_CHOICES = [
        ("gesetzlich", "Gesetzlich versichert"),
        ("privat", "Privat versichert"),
    ]
    VERTRAGSART_CHOICES = [
        ("unbefristet", "Unbefristet"),
        ("befristet", "Befristet"),
        ("minijob", "Minijob"),
        ("praktikum", "Praktikum / Ausbildung"),
    ]

    # --- Persoenliche Daten ---
    anrede = models.CharField(max_length=10, choices=ANREDE_CHOICES, default="keine", verbose_name="Anrede")
    vorname = models.CharField(max_length=100, verbose_name="Vorname")
    nachname = models.CharField(max_length=100, verbose_name="Nachname")
    geburtsname = models.CharField(max_length=100, blank=True, verbose_name="Geburtsname")
    geburtsdatum = models.DateField(verbose_name="Geburtsdatum")
    geburtsort = models.CharField(max_length=100, verbose_name="Geburtsort")
    staatsangehoerigkeit = models.CharField(max_length=50, default="deutsch", verbose_name="Staatsangehoerigkeit")
    familienstand = models.CharField(max_length=20, choices=FAMILIENSTAND_CHOICES, blank=True, verbose_name="Familienstand")
    konfession = models.CharField(max_length=20, choices=KONFESSION_CHOICES, blank=True, verbose_name="Konfession")
    anzahl_kinder = models.PositiveSmallIntegerField(default=0, verbose_name="Anzahl Kinder")

    # --- Adresse ---
    strasse = models.CharField(max_length=100, verbose_name="Strasse")
    hausnummer = models.CharField(max_length=10, verbose_name="Hausnummer")
    plz = models.CharField(max_length=10, verbose_name="PLZ")
    ort = models.CharField(max_length=100, verbose_name="Wohnort")
    land = models.CharField(max_length=50, default="Deutschland", verbose_name="Land")

    # --- Kontakt ---
    telefon_privat = models.CharField(max_length=30, blank=True, verbose_name="Telefon privat")
    mobil_privat = models.CharField(max_length=30, verbose_name="Mobil")
    email_privat = models.EmailField(blank=True, verbose_name="E-Mail privat")

    # --- Steuer & Sozialversicherung ---
    steuerklasse = models.CharField(max_length=1, choices=STEUERKLASSE_CHOICES, blank=True, verbose_name="Steuerklasse")
    steuer_id = models.CharField(max_length=11, blank=True, verbose_name="Steuer-ID")
    sozialversicherungsnummer = models.CharField(max_length=12, blank=True, verbose_name="Sozialversicherungsnummer")

    # --- Bankverbindung ---
    iban = models.CharField(max_length=34, blank=True, verbose_name="IBAN")
    bic = models.CharField(max_length=11, blank=True, verbose_name="BIC")
    bank_name = models.CharField(max_length=100, blank=True, verbose_name="Kreditinstitut")

    # --- Krankenversicherung ---
    krankenkasse_name = models.CharField(max_length=100, blank=True, verbose_name="Krankenkasse")
    krankenversicherungsart = models.CharField(max_length=15, choices=KRANKENVERSICHERUNG_CHOICES, blank=True, verbose_name="Versicherungsart")

    # --- Notfallkontakt ---
    notfallkontakt_name = models.CharField(max_length=100, blank=True, verbose_name="Notfallkontakt")
    notfallkontakt_beziehung = models.CharField(max_length=50, blank=True, verbose_name="Beziehung")
    notfallkontakt_telefon = models.CharField(max_length=30, blank=True, verbose_name="Telefon Notfallkontakt")

    # --- Einstellung (von HR ausgefuellt) ---
    angestrebte_stelle = models.ForeignKey(
        "hr.Stelle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bewerbungen",
        verbose_name="Angestrebte Stelle",
    )
    geplantes_eintrittsdatum = models.DateField(null=True, blank=True, verbose_name="Geplantes Eintrittsdatum")
    vertragsart = models.CharField(max_length=15, choices=VERTRAGSART_CHOICES, blank=True, verbose_name="Vertragsart")
    probezeit_bis = models.DateField(null=True, blank=True, verbose_name="Probezeit bis")
    interne_notiz = models.TextField(blank=True, verbose_name="Interne Notiz (HR)", help_text="Nur fuer HR sichtbar, wird bei Ablehnung mitgeloescht.")

    # --- Systemfelder ---
    einladungscode = models.OneToOneField(
        EinladungsCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bewerbung",
        verbose_name="Einladungscode",
    )
    status = models.CharField(
        max_length=22, choices=STATUS_CHOICES, default=STATUS_EINGEGANGEN, verbose_name="Status"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    geaendert_am = models.DateTimeField(auto_now=True, verbose_name="Geaendert am")
    bearbeitet_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bearbeitete_bewerbungen",
        verbose_name="Bearbeitet von (HR)",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Bewerbung"
        verbose_name_plural = "Bewerbungen"

    def __str__(self):
        return f"{self.nachname}, {self.vorname} – {self.get_status_display()}"

    @property
    def vollname(self):
        return f"{self.vorname} {self.nachname}"

    @property
    def naechster_status(self):
        """Gibt den naechsten Status in der Reihenfolge zurueck oder None."""
        try:
            idx = self.STATUS_REIHENFOLGE.index(self.status)
            return self.STATUS_REIHENFOLGE[idx + 1]
        except (ValueError, IndexError):
            return None

    @property
    def naechster_status_label(self):
        labels = dict(self.STATUS_CHOICES)
        ns = self.naechster_status
        return labels.get(ns, "") if ns else ""

    @property
    def ist_abgeschlossen(self):
        return self.status in (self.STATUS_ZUSAGE, self.STATUS_ABGELEHNT)


class BewerbungDokument(models.Model):
    """Hochgeladene Dokumente zu einer Bewerbung (verschluesselt via ClamAV + Fernet)."""

    TYP_CHOICES = [
        ("ausweis", "Personalausweis / Reisepass"),
        ("zeugnis_schule", "Schulzeugnis"),
        ("zeugnis_arbeit", "Arbeitszeugnis"),
        ("abschluss", "Abschlusszeugnis / Zertifikat"),
        ("fuehrerschein", "Fuehrerschein"),
        ("sonstige", "Sonstiges Dokument"),
    ]

    bewerbung = models.ForeignKey(
        Bewerbung,
        on_delete=models.CASCADE,
        related_name="dokumente",
        verbose_name="Bewerbung",
    )
    typ = models.CharField(max_length=20, choices=TYP_CHOICES, verbose_name="Dokumenttyp")
    dateiname = models.CharField(max_length=255, verbose_name="Dateiname")
    dateityp = models.CharField(max_length=100, verbose_name="MIME-Typ")
    inhalt_verschluesselt = models.BinaryField(verbose_name="Inhalt (verschluesselt)")
    groesse_bytes = models.IntegerField(verbose_name="Dateigroesse (Bytes)")
    hochgeladen_am = models.DateTimeField(auto_now_add=True, verbose_name="Hochgeladen am")

    class Meta:
        ordering = ["typ", "dateiname"]
        verbose_name = "Bewerbungsdokument"
        verbose_name_plural = "Bewerbungsdokumente"

    def __str__(self):
        return f"{self.get_typ_display()} – {self.dateiname}"

    def groesse_lesbar(self):
        if self.groesse_bytes < 1024:
            return f"{self.groesse_bytes} B"
        elif self.groesse_bytes < 1024 * 1024:
            return f"{self.groesse_bytes / 1024:.1f} KB"
        return f"{self.groesse_bytes / (1024*1024):.1f} MB"
