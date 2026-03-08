import logging
from datetime import date, timedelta

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Raumtyp-Auswahl (global, wird in Raum verwendet)
# ---------------------------------------------------------------------------
RAUMTYP_CHOICES = [
    ("einzelbuero", "Einzelbuero"),
    ("grossraumbuero", "Grossraumbuero"),
    ("teambuero", "Teambuero"),
    ("homeoffice_pool", "Homeoffice-Pool"),
    ("besprechung", "Besprechungsraum"),
    ("konferenz", "Konferenzraum"),
    ("schulung", "Schulungsraum"),
    ("ideenraum", "Ideenraum"),
    ("telefonbox", "Telefonbox"),
    ("teekueche", "Teekueche"),
    ("kantine", "Kantine"),
    ("pausenraum", "Pausenraum"),
    ("wc_herren", "WC Herren"),
    ("wc_damen", "WC Damen"),
    ("wc_barrierefrei", "WC Barrierefrei"),
    ("dusche", "Dusche"),
    ("serverraum", "Serverraum"),
    ("it_verteiler", "IT-Verteiler"),
    ("elektroverteilung", "Elektroverteilung"),
    ("heizungsraum", "Heizungsraum"),
    ("lueftungsraum", "Lueftungsraum"),
    ("lager", "Lager"),
    ("archiv", "Archiv"),
    ("druckerraum", "Druckerraum"),
    ("putzraum", "Putzraum"),
    ("abstellraum", "Abstellraum"),
    ("flur", "Flur"),
    ("eingang", "Eingang"),
    ("aufzug", "Aufzug"),
    ("windfang", "Windfang"),
    ("sonstiges", "Sonstiges"),
]


# ---------------------------------------------------------------------------
# 2a. Gebaeudestruktur
# ---------------------------------------------------------------------------

class Standort(models.Model):
    """Physischer Standort (Liegenschaft), oberste Ebene der Struktur."""

    adresse = models.TextField(blank=True)
    kuerzel = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        verbose_name = "Standort"
        verbose_name_plural = "Standorte"

    def __str__(self):
        return f"{self.kuerzel} – {self.name}"


class Gebaeude(models.Model):
    """Gebaeude an einem Standort."""

    baujahr = models.IntegerField(null=True, blank=True)
    bezeichnung = models.CharField(max_length=200)
    kuerzel = models.CharField(max_length=10)
    standort = models.ForeignKey(
        Standort, on_delete=models.CASCADE, related_name="gebaeude"
    )

    class Meta:
        ordering = ["standort", "kuerzel"]
        verbose_name = "Gebaeude"
        verbose_name_plural = "Gebaeude"

    def __str__(self):
        return f"{self.standort.kuerzel}/{self.kuerzel} – {self.bezeichnung}"


class Treppenhaus(models.Model):
    """Treppenhaus als eigenes Arbeitsschutzobjekt am Gebaeude."""

    TYP_CHOICES = [
        ("haupt", "Haupttreppenhaus"),
        ("neben", "Nebentreppenhaus"),
        ("notausgang", "Notausgang"),
    ]
    ZUSTAND_CHOICES = [
        ("gut", "Gut"),
        ("maengel", "Maengel vorhanden"),
        ("kritisch", "Kritisch"),
    ]

    bezeichnung = models.CharField(max_length=100)
    gebaeude = models.ForeignKey(
        Gebaeude, on_delete=models.CASCADE, related_name="treppenhaeuser"
    )
    kapazitaet_personen = models.IntegerField(null=True, blank=True)
    letzter_begehungstermin = models.DateField(null=True, blank=True)
    lichte_breite_cm = models.IntegerField(null=True, blank=True)
    maengel = models.TextField(blank=True)
    naechste_pruefung = models.DateField(null=True, blank=True)
    typ = models.CharField(max_length=20, choices=TYP_CHOICES, default="haupt")
    verbindet_geschosse = models.CharField(
        max_length=100, blank=True, help_text="z.B. UG-4.OG"
    )
    zustand = models.CharField(
        max_length=20, choices=ZUSTAND_CHOICES, default="gut"
    )

    class Meta:
        ordering = ["gebaeude", "bezeichnung"]
        verbose_name = "Treppenhaus"
        verbose_name_plural = "Treppenhaeuser"

    def __str__(self):
        return f"{self.gebaeude.kuerzel} – {self.bezeichnung}"


class Geschoss(models.Model):
    """Geschoss in einem Gebaeude."""

    KUERZEL_CHOICES = [
        ("UG2", "2. Untergeschoss"),
        ("UG", "Untergeschoss"),
        ("EG", "Erdgeschoss"),
        ("1", "1. Obergeschoss"),
        ("2", "2. Obergeschoss"),
        ("3", "3. Obergeschoss"),
        ("4", "4. Obergeschoss"),
        ("5", "5. Obergeschoss"),
        ("DG", "Dachgeschoss"),
    ]

    bezeichnung = models.CharField(max_length=100)
    gebaeude = models.ForeignKey(
        Gebaeude, on_delete=models.CASCADE, related_name="geschosse"
    )
    kuerzel = models.CharField(max_length=5, choices=KUERZEL_CHOICES)
    reihenfolge = models.IntegerField(default=0)

    class Meta:
        ordering = ["gebaeude", "reihenfolge"]
        verbose_name = "Geschoss"
        verbose_name_plural = "Geschosse"

    def __str__(self):
        return f"{self.gebaeude.kuerzel} – {self.kuerzel} ({self.bezeichnung})"


class Bereich(models.Model):
    """Optionaler Raumbereich innerhalb eines Geschosses (z.B. Westfluegel)."""

    bezeichnung = models.CharField(max_length=100)
    geschoss = models.ForeignKey(
        Geschoss, on_delete=models.CASCADE, related_name="bereiche"
    )
    kuerzel = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["geschoss", "bezeichnung"]
        verbose_name = "Bereich"
        verbose_name_plural = "Bereiche"

    def __str__(self):
        return f"{self.geschoss} – {self.bezeichnung}"


# ---------------------------------------------------------------------------
# 2b. Raum (Kernobjekt)
# ---------------------------------------------------------------------------

class Raum(models.Model):
    """Raum als zentrales Objekt des Raumbuchs."""

    NUTZUNG_CHOICES = [
        ("statisch", "Statisch (dauerhaft belegt)"),
        ("dynamisch", "Buchbar"),
    ]

    bereich = models.ForeignKey(
        Bereich,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="raeume",
    )
    beschreibung = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    flaeche_m2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    geaendert_am = models.DateTimeField(auto_now=True)
    geschoss = models.ForeignKey(
        Geschoss, on_delete=models.PROTECT, related_name="raeume"
    )
    ist_aktiv = models.BooleanField(default=True)
    ist_leer = models.BooleanField(default=False)
    kapazitaet = models.IntegerField(null=True, blank=True)
    nutzungsmodell = models.CharField(
        max_length=20, choices=NUTZUNG_CHOICES, default="statisch"
    )
    raumname = models.CharField(max_length=200, blank=True)
    raumnummer = models.CharField(max_length=20)
    raumtyp = models.CharField(max_length=30, choices=RAUMTYP_CHOICES)

    class Meta:
        ordering = ["geschoss__reihenfolge", "raumnummer"]
        unique_together = [["geschoss", "raumnummer"]]
        verbose_name = "Raum"
        verbose_name_plural = "Raeume"

    def __str__(self):
        name = f" – {self.raumname}" if self.raumname else ""
        return f"{self.raumnummer}{name} ({self.geschoss.kuerzel})"

    def get_anzeigename(self):
        """Kurzbezeichnung fuer Listen und Dropdowns."""
        return self.raumname or self.raumnummer


# ---------------------------------------------------------------------------
# 2c. Datenschichten (5 OneToOne-Models)
# ---------------------------------------------------------------------------

class RaumFacilityDaten(models.Model):
    """Facility-Schicht: Bau, Ausstattung, Moebel."""

    baujahr = models.IntegerField(null=True, blank=True)
    bodenbelag = models.CharField(max_length=100, blank=True)
    fenster_anzahl = models.IntegerField(null=True, blank=True)
    fenster_verdunkelbar = models.BooleanField(default=False)
    flaeche_m2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    klima_typ = models.CharField(max_length=100, blank=True)
    letzte_renovierung = models.DateField(null=True, blank=True)
    lueftungsanlage = models.BooleanField(default=False)
    moebelliste = models.TextField(blank=True)
    raum = models.OneToOneField(
        Raum, on_delete=models.CASCADE, related_name="facility_daten"
    )
    volumen_m3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Facility-Daten"
        verbose_name_plural = "Facility-Daten"

    def __str__(self):
        return f"Facility-Daten: {self.raum}"


class RaumElektroDaten(models.Model):
    """Elektro-Schicht: Stromkreise, USV, Sicherungen."""

    drehstrom = models.BooleanField(default=False)
    notbeleuchtung = models.BooleanField(default=False)
    raum = models.OneToOneField(
        Raum, on_delete=models.CASCADE, related_name="elektro_daten"
    )
    sicherungsbezeichnungen = models.TextField(blank=True)
    stromkreise_beschreibung = models.TextField(blank=True)
    usv_gesichert = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Elektro-Daten"
        verbose_name_plural = "Elektro-Daten"

    def __str__(self):
        return f"Elektro-Daten: {self.raum}"


class RaumNetzwerkDaten(models.Model):
    """Netzwerk-Schicht: LAN, WLAN, Telefon."""

    WLAN_CHOICES = [
        ("gut", "Gut"),
        ("mittel", "Mittel"),
        ("schwach", "Schwach"),
        ("keine", "Keine"),
    ]

    ip_adressen = models.TextField(blank=True)
    lan_ports_anzahl = models.IntegerField(null=True, blank=True)
    lan_ports_beschreibung = models.TextField(blank=True)
    raum = models.OneToOneField(
        Raum, on_delete=models.CASCADE, related_name="netzwerk_daten"
    )
    switch_name = models.CharField(max_length=100, blank=True)
    switch_port = models.CharField(max_length=100, blank=True)
    telefondosen = models.IntegerField(null=True, blank=True)
    wlan_abdeckung = models.CharField(
        max_length=10, choices=WLAN_CHOICES, blank=True
    )

    class Meta:
        verbose_name = "Netzwerk-Daten"
        verbose_name_plural = "Netzwerk-Daten"

    def __str__(self):
        return f"Netzwerk-Daten: {self.raum}"


class NetzwerkKomponente(models.Model):
    """19-Zoll Rack-Komponente in einem IT-Raum."""

    TYP_CHOICES = [
        ("core_switch", "Core Switch"),
        ("distribution_switch", "Distribution Switch"),
        ("access_switch", "Access Switch"),
        ("patch_panel", "Patch Panel"),
        ("glasfaser_verteiler", "LWL-Verteiler"),
        ("firewall", "Firewall / UTM"),
        ("router", "Router / WAN"),
        ("server", "Server"),
        ("nas", "NAS / Storage"),
        ("ups", "USV / UPS"),
        ("kvm", "KVM-Switch"),
        ("accesspoint", "Access Point"),
        ("sonstiges", "Sonstiges"),
    ]

    raum = models.ForeignKey(
        "Raum", on_delete=models.CASCADE, related_name="netzwerk_komponenten"
    )
    typ = models.CharField(max_length=30, choices=TYP_CHOICES)
    bezeichnung = models.CharField(max_length=100)
    hersteller = models.CharField(max_length=100, blank=True)
    modell = models.CharField(max_length=100, blank=True)
    rack_einheit_start = models.IntegerField(
        null=True, blank=True, verbose_name="Rack-Position (U)"
    )
    rack_einheiten = models.IntegerField(default=1, verbose_name="Hoehe (U)")
    ports_gesamt = models.IntegerField(null=True, blank=True)
    ports_belegt = models.IntegerField(null=True, blank=True)
    ip_adresse = models.CharField(max_length=50, blank=True)
    vlan = models.CharField(max_length=100, blank=True)
    seriennummer = models.CharField(max_length=100, blank=True)
    bemerkung = models.TextField(blank=True)

    class Meta:
        ordering = ["-rack_einheit_start"]
        verbose_name = "Netzwerk-Komponente"
        verbose_name_plural = "Netzwerk-Komponenten"

    def __str__(self):
        return f"{self.bezeichnung} ({self.raum.raumnummer})"

    @property
    def auslastung_prozent(self):
        """Ports-Auslastung in Prozent."""
        if self.ports_gesamt and self.ports_belegt is not None:
            return round(self.ports_belegt / self.ports_gesamt * 100)
        return None


class Glasfaserverbindung(models.Model):
    """Glasfaser-Verbindung zwischen zwei IT-Raeumen (Backbone)."""

    KABEL_CHOICES = [
        ("om4", "OM4 Multimode (bis 100GbE / 400m)"),
        ("os2", "OS2 Singlemode (bis 100GbE / 10km)"),
    ]
    STECKER_CHOICES = [
        ("lc_duplex", "LC Duplex"),
        ("sc_duplex", "SC Duplex"),
        ("mtp_12", "MTP/MPO 12-faser"),
        ("mtp_24", "MTP/MPO 24-faser"),
    ]

    bezeichnung = models.CharField(max_length=100)
    von_raum = models.ForeignKey(
        "Raum", on_delete=models.CASCADE, related_name="glasfaser_von"
    )
    nach_raum = models.ForeignKey(
        "Raum", on_delete=models.CASCADE, related_name="glasfaser_nach"
    )
    kabel_typ = models.CharField(
        max_length=10, choices=KABEL_CHOICES, default="om4"
    )
    stecker_typ = models.CharField(
        max_length=10, choices=STECKER_CHOICES, default="lc_duplex"
    )
    fasern_anzahl = models.IntegerField(default=12)
    bandbreite = models.CharField(max_length=50, blank=True, default="10 GbE")
    laenge_m = models.IntegerField(null=True, blank=True, verbose_name="Laenge (m)")
    bemerkung = models.TextField(blank=True)

    class Meta:
        verbose_name = "Glasfaserverbindung"
        verbose_name_plural = "Glasfaserverbindungen"

    def __str__(self):
        return f"{self.bezeichnung}: {self.von_raum.raumnummer} -> {self.nach_raum.raumnummer}"


class RaumInstallationDaten(models.Model):
    """Installation-Schicht: Wasser, Brandschutz, GLT."""

    absperrhaehne = models.TextField(blank=True)
    brandschutzklappen = models.TextField(blank=True)
    glt_adressen = models.TextField(blank=True)
    raum = models.OneToOneField(
        Raum, on_delete=models.CASCADE, related_name="installation_daten"
    )

    class Meta:
        verbose_name = "Installations-Daten"
        verbose_name_plural = "Installations-Daten"

    def __str__(self):
        return f"Installations-Daten: {self.raum}"


class RaumArbeitsschutzDaten(models.Model):
    """Arbeitsschutz-Schicht: Brand, Flucht, Barriere."""

    aed_standort = models.CharField(max_length=200, blank=True)
    barrierefrei = models.BooleanField(default=False)
    barrierefreiheit_details = models.TextField(blank=True)
    brandabschnitt = models.CharField(max_length=100, blank=True)
    erste_hilfe_kasten = models.BooleanField(default=False)
    erste_hilfe_standort = models.CharField(max_length=200, blank=True)
    feuerloesch_naechste_pruefung = models.DateField(null=True, blank=True)
    feuerloesch_nummer = models.CharField(max_length=50, blank=True)
    feuerloesch_typ = models.CharField(max_length=100, blank=True)
    fluchtweg_beschreibung = models.TextField(blank=True)
    gefahrstoffe_beschreibung = models.TextField(blank=True)
    gefahrstoffe_vorhanden = models.BooleanField(default=False)
    raum = models.OneToOneField(
        Raum, on_delete=models.CASCADE, related_name="arbeitsschutz_daten"
    )
    rauchmelder = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Arbeitsschutz-Daten"
        verbose_name_plural = "Arbeitsschutz-Daten"

    def __str__(self):
        return f"Arbeitsschutz-Daten: {self.raum}"


# ---------------------------------------------------------------------------
# 2d. Schluesselverwaltung
# ---------------------------------------------------------------------------

class Schluessel(models.Model):
    """Physischer Schluessel im Schliessanlagen-Bestand."""

    ANLAGE_TYP = [
        ("general", "Generalschluessel"),
        ("gruppe", "Gruppenschluessel"),
        ("einzel", "Einzelschluessel"),
    ]

    anzahl_kopien = models.IntegerField(default=1)
    bezeichnung = models.CharField(max_length=200)
    raeume = models.ManyToManyField(
        Raum, blank=True, related_name="schluessel"
    )
    schliessanlage = models.CharField(max_length=100, blank=True)
    schliessanlage_typ = models.CharField(
        max_length=20, choices=ANLAGE_TYP, default="einzel"
    )
    schluesselnummer = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["schluesselnummer"]
        verbose_name = "Schluessel"
        verbose_name_plural = "Schluessel"

    def __str__(self):
        return f"{self.schluesselnummer} – {self.bezeichnung}"

    def ist_verfuegbar(self):
        """True wenn kein aktiver Ausgabe-Datensatz ohne Rueckgabe existiert."""
        return not self.ausgaben.filter(rueckgabe_datum__isnull=True).exists()


class SchluesselAusgabe(models.Model):
    """Protokoll der Schluessel-Ausgabe an einen Mitarbeiter."""

    ausgabe_datum = models.DateField()
    ausgegeben_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ausgaben_erstellt",
    )
    bemerkung = models.TextField(blank=True)
    empfaenger = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.PROTECT,
        related_name="schluessel_ausgaben",
    )
    rueckgabe_datum = models.DateField(null=True, blank=True)
    schluessel = models.ForeignKey(
        Schluessel, on_delete=models.PROTECT, related_name="ausgaben"
    )

    class Meta:
        ordering = ["-ausgabe_datum"]
        verbose_name = "Schluessel-Ausgabe"
        verbose_name_plural = "Schluessel-Ausgaben"

    def __str__(self):
        return (
            f"{self.schluessel.schluesselnummer} → {self.empfaenger} "
            f"am {self.ausgabe_datum}"
        )


# ---------------------------------------------------------------------------
# 2e. Gebaeudesicherheit / Zutrittskontrolle
# ---------------------------------------------------------------------------

class ZutrittsProfil(models.Model):
    """Zutrittsprofil das mehreren Mitarbeitern zugewiesen werden kann."""

    beschreibung = models.TextField(blank=True)
    bezeichnung = models.CharField(max_length=200)
    raeume = models.ManyToManyField(
        Raum, blank=True, related_name="zutrittsprofile"
    )

    class Meta:
        ordering = ["bezeichnung"]
        verbose_name = "Zutrittsprofil"
        verbose_name_plural = "Zutrittsprofile"

    def __str__(self):
        return self.bezeichnung


class ZutrittsToken(models.Model):
    """Elektronischer Zutrittstoken (Badge, Transponder) eines Mitarbeiters."""

    STATUS_CHOICES = [
        ("beantragt", "Beantragt"),
        ("aktiv", "Aktiv"),
        ("gesperrt", "Gesperrt"),
        ("verloren", "Verloren"),
    ]

    ablauf_warnung_tage = models.IntegerField(default=30)
    ausgestellt_am = models.DateField()
    badge_id = models.CharField(max_length=100)
    bemerkung = models.TextField(blank=True)
    gueltig_bis = models.DateField(null=True, blank=True)
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.PROTECT,
        related_name="zutritts_tokens",
    )
    profile = models.ManyToManyField(ZutrittsProfil, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="aktiv"
    )

    class Meta:
        ordering = ["mitarbeiter", "badge_id"]
        verbose_name = "Zutrittstoken"
        verbose_name_plural = "Zutrittsgutschriften"

    def __str__(self):
        return f"{self.badge_id} – {self.mitarbeiter} ({self.get_status_display()})"

    def laeuft_bald_ab(self):
        """True wenn Token innerhalb der Warnfrist ablaueft."""
        if self.gueltig_bis:
            warnung_ab = self.gueltig_bis - timedelta(days=self.ablauf_warnung_tage)
            return date.today() >= warnung_ab
        return False


# ---------------------------------------------------------------------------
# 2f. Phase 2 – Belegung, Reinigung, Besuch
# ---------------------------------------------------------------------------

class Belegung(models.Model):
    """Dauerhafte oder zeitlich begrenzte Raum-Belegung durch einen Mitarbeiter."""

    bis = models.DateField(null=True, blank=True)
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter", on_delete=models.PROTECT, related_name="raum_belegungen"
    )
    notiz = models.TextField(blank=True)
    raum = models.ForeignKey(
        Raum, on_delete=models.PROTECT, related_name="belegungen"
    )
    von = models.DateField()

    class Meta:
        ordering = ["-von"]
        verbose_name = "Belegung"
        verbose_name_plural = "Belegungen"

    def __str__(self):
        return f"{self.raum} ← {self.mitarbeiter} ab {self.von}"

    def ist_aktuell(self):
        """True wenn Belegung heute noch aktiv ist."""
        heute = date.today()
        if self.bis:
            return self.von <= heute <= self.bis
        return self.von <= heute


class Reinigungsplan(models.Model):
    """Reinigungsplan fuer einen Raum."""

    INTERVALL_CHOICES = [
        ("taeglich", "Taeglich"),
        ("woechentlich", "Woechentlich"),
        ("monatlich", "Monatlich"),
        ("nach_bedarf", "Nach Bedarf"),
    ]

    intervall = models.CharField(
        max_length=20, choices=INTERVALL_CHOICES, default="taeglich"
    )
    letzte_reinigung = models.DateField(null=True, blank=True)
    methode = models.CharField(max_length=200, blank=True)
    raum = models.OneToOneField(
        Raum, on_delete=models.CASCADE, related_name="reinigungsplan"
    )
    zustaendig = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Reinigungsplan"
        verbose_name_plural = "Reinigungsplaene"

    def __str__(self):
        return f"Reinigungsplan: {self.raum}"

    def ist_faellig(self):
        """True wenn Reinigung ueberfaellig ist (grobe Schätzung)."""
        if not self.letzte_reinigung:
            return True
        heute = date.today()
        if self.intervall == "taeglich":
            return (heute - self.letzte_reinigung).days >= 1
        elif self.intervall == "woechentlich":
            return (heute - self.letzte_reinigung).days >= 7
        elif self.intervall == "monatlich":
            return (heute - self.letzte_reinigung).days >= 30
        return False


class ReinigungsQuittung(models.Model):
    """Einzelne Reinigungsbestaetigung (Quittung) fuer einen Raum."""

    bemerkung = models.TextField(blank=True)
    quittiert_durch_name = models.CharField(max_length=200)
    raum = models.ForeignKey(
        Raum, on_delete=models.PROTECT, related_name="reinigungen"
    )
    zeitstempel = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-zeitstempel"]
        verbose_name = "Reinigungsquittung"
        verbose_name_plural = "Reinigungsquittungen"

    def __str__(self):
        return f"Reinigung {self.raum} am {self.zeitstempel:%d.%m.%Y}"


class Besuchsanmeldung(models.Model):
    """Vorankuendigung eines externen Besuchs."""

    STATUS_CHOICES = [
        ("angemeldet", "Angemeldet"),
        ("erschienen", "Erschienen"),
        ("abgesagt", "Abgesagt"),
    ]

    besucher_firma = models.CharField(max_length=200, blank=True)
    besucher_nachname = models.CharField(max_length=100)
    besucher_vorname = models.CharField(max_length=100)
    bis = models.TimeField(null=True, blank=True)
    datum = models.DateField()
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="besuchsanmeldungen"
    )
    gastgeber = models.ForeignKey(
        "hr.HRMitarbeiter", on_delete=models.PROTECT, related_name="besuche"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="angemeldet"
    )
    von = models.TimeField(null=True, blank=True)
    zielraum = models.ForeignKey(
        Raum, null=True, blank=True, on_delete=models.SET_NULL, related_name="besuche"
    )
    zweck = models.TextField(blank=True)

    class Meta:
        ordering = ["-datum", "von"]
        verbose_name = "Besuchsanmeldung"
        verbose_name_plural = "Besuchsanmeldungen"

    def __str__(self):
        return (
            f"{self.besucher_vorname} {self.besucher_nachname} "
            f"am {self.datum}"
        )


# ---------------------------------------------------------------------------
# 2g. Phase 4 – Buchungssystem
# ---------------------------------------------------------------------------

class Raumbuchung(models.Model):
    """Zeitliche Buchung eines buchbaren Raums."""

    STATUS_CHOICES = [
        ("offen", "Ausstehend"),
        ("bestaetigt", "Bestaetigt"),
        ("storniert", "Storniert"),
    ]

    betreff = models.CharField(max_length=200)
    bis = models.TimeField()
    buchender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="buchungen",
    )
    buchungs_nr = models.CharField(max_length=20, unique=True)
    datum = models.DateField()
    erstellt_am = models.DateTimeField(auto_now_add=True)
    raum = models.ForeignKey(
        Raum, on_delete=models.PROTECT, related_name="buchungen"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="offen"
    )
    jitsi_link = models.URLField(
        blank=True,
        default="",
        verbose_name="Jitsi-Meeting-Link",
    )
    teilnehmerzahl = models.IntegerField(null=True, blank=True)
    von = models.TimeField()

    class Meta:
        ordering = ["-datum", "von"]
        verbose_name = "Raumbuchung"
        verbose_name_plural = "Raumbuchungen"

    def __str__(self):
        return f"{self.buchungs_nr} – {self.raum} am {self.datum}"

    @classmethod
    def generiere_buchungsnummer(cls):
        """Generiert eine eindeutige Buchungsnummer im Format RB-YYYYMMDD-XXXX."""
        from django.utils import timezone
        heute = timezone.now().strftime("%Y%m%d")
        basis = f"RB-{heute}-"
        # Hoechste laufende Nummer heute ermitteln
        letzte = (
            cls.objects.filter(buchungs_nr__startswith=basis)
            .order_by("-buchungs_nr")
            .first()
        )
        if letzte:
            try:
                nr = int(letzte.buchungs_nr.split("-")[-1]) + 1
            except (ValueError, IndexError):
                nr = 1
        else:
            nr = 1
        return f"{basis}{nr:04d}"


# ---------------------------------------------------------------------------
# 2h. Phase 5 – Umzug + Audit-Trail
# ---------------------------------------------------------------------------

class Umzugsauftrag(models.Model):
    """Geplanter Raumwechsel eines Mitarbeiters oder einer Einheit."""

    STATUS_CHOICES = [
        ("offen", "Offen"),
        ("in_bearbeitung", "In Bearbeitung"),
        ("erledigt", "Erledigt"),
        ("storniert", "Storniert"),
    ]

    beauftragt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="umzuege_beauftragt",
    )
    datum_geplant = models.DateField()
    erstellt_am = models.DateTimeField(auto_now_add=True)
    mitarbeiter = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="umzuege",
    )
    nach_raum = models.ForeignKey(
        Raum,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="einzuege",
    )
    notiz = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="offen"
    )
    von_raum = models.ForeignKey(
        Raum,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="auszuege",
    )

    class Meta:
        ordering = ["datum_geplant"]
        verbose_name = "Umzugsauftrag"
        verbose_name_plural = "Umzugsauftraege"

    def __str__(self):
        ma = str(self.mitarbeiter) if self.mitarbeiter else "unbekannt"
        return f"Umzug {ma}: {self.von_raum} → {self.nach_raum} ({self.datum_geplant})"


class RaumbuchLog(models.Model):
    """Audit-Trail fuer alle Aenderungen im Raumbuch."""

    aktion = models.CharField(max_length=100)
    beschreibung = models.TextField(blank=True)
    geaendert_am = models.DateTimeField(auto_now_add=True)
    geaendert_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    model_name = models.CharField(max_length=100, blank=True)
    objekt_id = models.IntegerField(null=True, blank=True)
    raum = models.ForeignKey(
        Raum,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="log_eintraege",
    )

    class Meta:
        ordering = ["-geaendert_am"]
        verbose_name = "Raumbuch-Log"
        verbose_name_plural = "Raumbuch-Logs"

    def __str__(self):
        return f"{self.aktion} – {self.raum} ({self.geaendert_am:%d.%m.%Y %H:%M})"
