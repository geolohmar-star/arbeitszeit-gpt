"""Antrags-Pfad-System: Intelligente, verzweigte Antragsformulare.

Jeder AntragsPfad ist ein gerichteter Graph:
- AntragsPfadSchritt  = Knoten  (eine Formularseite mit Feldern)
- AntragsPfadTransition = Kante (bedingte Verbindung zwischen Schritten)

Laufende Nutzersitzungen werden in AntragsPfadSitzung verfolgt.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class AntragsPfad(models.Model):
    """Definition eines verzweigten Antragsformulars."""

    name = models.CharField(max_length=200, verbose_name="Name")
    beschreibung = models.TextField(blank=True, verbose_name="Beschreibung")
    aktiv = models.BooleanField(default=True, verbose_name="Aktiv")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erstellte_antragspfade",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Antrags-Pfad"
        verbose_name_plural = "Antrags-Pfade"

    def __str__(self):
        return self.name

    def start_schritt(self):
        """Gibt den Start-Schritt zurueck."""
        return self.schritte.filter(ist_start=True).first()


class AntragsPfadSchritt(models.Model):
    """Ein Schritt (Knoten) im Antrags-Pfad – entspricht einer Formularseite."""

    pfad = models.ForeignKey(
        AntragsPfad, on_delete=models.CASCADE, related_name="schritte"
    )
    # Kurzbezeichner fuer Referenzierung im Editor (z.B. "s1", "start")
    node_id = models.CharField(max_length=50, verbose_name="Node-ID")
    titel = models.CharField(max_length=200, verbose_name="Titel")
    # Felder als JSON-Liste (gleiches Format wie FormularSchema.schema_json["felder"])
    felder_json = models.JSONField(
        default=list,
        verbose_name="Felder",
        help_text="Eingabefelder dieses Schritts im Schema-Format",
    )
    ist_start = models.BooleanField(default=False, verbose_name="Start-Knoten")
    ist_ende = models.BooleanField(default=False, verbose_name="End-Knoten")
    # Visuelle Position im Editor
    pos_x = models.FloatField(default=200, verbose_name="Position X")
    pos_y = models.FloatField(default=200, verbose_name="Position Y")

    class Meta:
        ordering = ["pk"]
        verbose_name = "Antrags-Schritt"
        verbose_name_plural = "Antrags-Schritte"
        unique_together = [("pfad", "node_id")]

    def __str__(self):
        return f"{self.pfad.name} \u2192 {self.titel}"

    def felder(self):
        return self.felder_json if isinstance(self.felder_json, list) else []


class AntragsPfadTransition(models.Model):
    """Gerichtete Kante zwischen zwei Schritten, optional mit Bedingung."""

    pfad = models.ForeignKey(
        AntragsPfad, on_delete=models.CASCADE, related_name="transitionen"
    )
    von_schritt = models.ForeignKey(
        AntragsPfadSchritt,
        on_delete=models.CASCADE,
        related_name="ausgaende",
        verbose_name="Von",
    )
    zu_schritt = models.ForeignKey(
        AntragsPfadSchritt,
        on_delete=models.CASCADE,
        related_name="eingaenge",
        verbose_name="Zu",
    )
    # Leer = immer wahr; sonst Formel wie "{{tierart}} == \"Kampfhund\""
    bedingung = models.TextField(
        blank=True,
        verbose_name="Bedingung",
        help_text="Formel-Bedingung (leer = immer wahr). Referenziert Feld-IDs aller bisherigen Schritte.",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Beschriftung",
        help_text="Optionaler Text auf der Kante, z.B. 'Ja' oder 'Kampfhund'",
    )
    reihenfolge = models.IntegerField(
        default=0,
        verbose_name="Reihenfolge",
        help_text="Auswertungsreihenfolge bei mehreren Ausgaengen (niedrig = zuerst)",
    )

    class Meta:
        ordering = ["reihenfolge", "pk"]
        verbose_name = "Transition"
        verbose_name_plural = "Transitionen"

    def __str__(self):
        bed = f" [{self.bedingung[:30]}]" if self.bedingung else ""
        return f"{self.von_schritt.titel} \u2192 {self.zu_schritt.titel}{bed}"


class AntragsPfadSitzung(models.Model):
    """Laufende oder abgeschlossene Nutzersitzung durch einen Antrags-Pfad."""

    STATUS_LAUFEND = "laufend"
    STATUS_ABGESCHLOSSEN = "abgeschlossen"
    STATUS_ABGEBROCHEN = "abgebrochen"

    STATUS_CHOICES = [
        (STATUS_LAUFEND, "Laufend"),
        (STATUS_ABGESCHLOSSEN, "Abgeschlossen"),
        (STATUS_ABGEBROCHEN, "Abgebrochen"),
    ]

    pfad = models.ForeignKey(
        AntragsPfad, on_delete=models.PROTECT, related_name="sitzungen"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="antrags_sitzungen",
    )
    aktueller_schritt = models.ForeignKey(
        AntragsPfadSchritt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aktive_sitzungen",
    )
    # Alle bisher gesammelten Formulardaten: {feld_id: wert}
    gesammelte_daten = models.JSONField(default=dict, verbose_name="Gesammelte Daten")
    # Besuchte Schritte in Reihenfolge: [node_id, ...]
    besuchte_schritte = models.JSONField(
        default=list, verbose_name="Besuchte Schritte"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_LAUFEND
    )
    gestartet_am = models.DateTimeField(auto_now_add=True)
    abgeschlossen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-gestartet_am"]
        verbose_name = "Antrags-Sitzung"
        verbose_name_plural = "Antrags-Sitzungen"

    def __str__(self):
        return f"{self.user} \u2013 {self.pfad.name} ({self.get_status_display()})"

    def abschliessen(self):
        """Markiert die Sitzung als abgeschlossen."""
        self.status = self.STATUS_ABGESCHLOSSEN
        self.abgeschlossen_am = timezone.now()
        self.save(update_fields=["status", "abgeschlossen_am"])
