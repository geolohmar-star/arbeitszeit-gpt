import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class ErsteHilfeVorfall(models.Model):
    """Protokoll eines Erste-Hilfe-Einsatzes.

    DSGVO Art. 9: Gesundheitsdaten – nur Betriebsarzt und Staff duerfen
    alle Details einsehen. Der Meldende sieht nur seinen eigenen Vorfall.
    """

    STATUS_OFFEN = "offen"
    STATUS_ABGESCHLOSSEN = "abgeschlossen"

    STATUS_CHOICES = [
        (STATUS_OFFEN, "Offen"),
        (STATUS_ABGESCHLOSSEN, "Abgeschlossen"),
    ]

    beschreibung = models.TextField(
        blank=True,
        verbose_name="Beschreibung",
        help_text="Optionale Beschreibung der Situation",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    gemeldet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="eh_vorfaelle",
        verbose_name="Gemeldet von",
    )
    geschlossen_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Geschlossen am",
    )
    matrix_ping_event_id = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Matrix EH_PING Event-ID",
        help_text="Event-ID der Alarmnachricht im EH_PING-Raum (fuer Reaktionen-Polling)",
    )
    matrix_ping_since_token = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Matrix EH_PING Since-Token",
        help_text="Pagination-Token fuer Reaktionen-Polling",
    )
    ort = models.CharField(
        max_length=200,
        verbose_name="Ort",
        help_text="Wo ist der Notfall? (z.B. Buero 2.OG, Kantine, Parkplatz)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OFFEN,
        verbose_name="Status",
    )

    BEWERTUNG_POSITIV = "positiv"
    BEWERTUNG_VERBESSERUNG = "verbesserungsbedarf"
    BEWERTUNG_KRITISCH = "kritisch"

    BEWERTUNG_CHOICES = [
        (BEWERTUNG_POSITIV, "Einsatz verlief problemlos"),
        (BEWERTUNG_VERBESSERUNG, "Verbesserungsbedarf erkennbar"),
        (BEWERTUNG_KRITISCH, "Kritische Schwachstellen festgestellt"),
    ]

    protokoll_bewertung = models.CharField(
        max_length=30,
        blank=True,
        choices=BEWERTUNG_CHOICES,
        verbose_name="Bewertung des Einsatzes",
    )
    protokoll_erstellt_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Protokoll erstellt am",
    )
    protokoll_erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eh_protokolle",
        verbose_name="Protokoll erstellt von",
    )
    protokoll_text = models.TextField(
        blank=True,
        verbose_name="Protokolltext",
        help_text="Ergaenzungstext und Bewertung durch den Betriebsarzt",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Erste-Hilfe-Vorfall"
        verbose_name_plural = "Erste-Hilfe-Vorfaelle"
        permissions = [
            ("view_alle_vorfaelle", "Kann alle Erste-Hilfe-Vorfaelle einsehen"),
            ("schliessen_vorfall", "Kann Erste-Hilfe-Vorfall abschliessen"),
        ]

    def __str__(self):
        return f"EH-Vorfall {self.pk} – {self.ort} ({self.erstellt_am.strftime('%d.%m.%Y %H:%M')})"

    @property
    def ist_offen(self):
        return self.status == self.STATUS_OFFEN


class ErsteHilfeErsthelferToken(models.Model):
    """Einmaliger Token fuer die tokenbasierte Rueckmeldung eines Ersthelfers.

    Jeder aktive Ersthelfer erhaelt pro Vorfall einen eigenen Token-Link.
    Der Link ist ohne Login zugaenglich – der Token ist der Zugriffsschluessel.
    """

    erstellt_am = models.DateTimeField(auto_now_add=True)
    ersthelfer = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.CASCADE,
        related_name="eh_tokens",
        verbose_name="Ersthelfer/in",
    )
    matrix_dm_room_id = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Matrix-DM-Raum-ID",
        help_text="Raum-ID des persoenlichen DM-Chats (fuer Antworten-Polling)",
    )
    matrix_dm_since_token = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Matrix-DM Since-Token",
        help_text="Pagination-Token fuer DM-Antworten-Polling",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Token",
    )
    vorfall = models.ForeignKey(
        ErsteHilfeVorfall,
        on_delete=models.CASCADE,
        related_name="ersthelfer_tokens",
        verbose_name="Vorfall",
    )

    class Meta:
        ordering = ["-erstellt_am"]
        unique_together = [("vorfall", "ersthelfer")]
        verbose_name = "Ersthelfer-Token"
        verbose_name_plural = "Ersthelfer-Tokens"

    def __str__(self):
        return f"Token {self.ersthelfer} – Vorfall {self.vorfall_id}"

    @classmethod
    def generiere(cls, vorfall, ersthelfer):
        """Erstellt einen neuen Token fuer einen Ersthelfer zu einem Vorfall."""
        return cls.objects.create(
            vorfall=vorfall,
            ersthelfer=ersthelfer,
            token=secrets.token_urlsafe(32),
        )


class ErsteHilfeNachricht(models.Model):
    """Freitext-Nachricht aus dem Matrix-EH_PING-Raum zu einem Vorfall."""

    absender = models.ForeignKey(
        "hr.HRMitarbeiter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eh_nachrichten",
        verbose_name="Absender",
    )
    absender_matrix_id = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Matrix-ID (Fallback)",
    )
    gesendet_am = models.DateTimeField(auto_now_add=True)
    text = models.TextField(verbose_name="Nachricht")
    vorfall = models.ForeignKey(
        ErsteHilfeVorfall,
        on_delete=models.CASCADE,
        related_name="nachrichten",
        verbose_name="Vorfall",
    )

    class Meta:
        ordering = ["gesendet_am"]
        verbose_name = "EH-Nachricht"
        verbose_name_plural = "EH-Nachrichten"

    def __str__(self):
        name = self.absender.vollname if self.absender else self.absender_matrix_id
        return f"{name}: {self.text[:40]}"

    @property
    def absender_name(self):
        if self.absender:
            return self.absender.vollname
        return self.absender_matrix_id.split(":")[0].lstrip("@") or "Unbekannt"


class ErsteHilfeRueckmeldung(models.Model):
    """Statusmeldung eines Ersthelfers zu einem Vorfall (tokenbasiert, kein Login)."""

    STATUS_UNTERWEGS = "unterwegs"
    STATUS_AM_ORT = "am_ort"
    STATUS_UNTERSTUETZUNG = "brauche_unterstuetzung"
    STATUS_NICHT_VERFUEGBAR = "nicht_verfuegbar"
    # Konkrete Bedarfsmeldungen vor Ort (Erweiterung der 1-4-Optionen)
    STATUS_BRAUCHE_DEFI = "brauche_defi"
    STATUS_BRAUCHE_RTW = "brauche_rtw"
    STATUS_BRAUCHE_ZWEITEN_EH = "brauche_zweiten_eh"
    STATUS_BRAUCHE_MATERIAL = "brauche_material"
    STATUS_PATIENT_TRANSPORTFAEHIG = "patient_transportfaehig"
    STATUS_EINSATZ_BEENDET = "einsatz_beendet"

    STATUS_CHOICES = [
        (STATUS_UNTERWEGS, "Bin unterwegs"),
        (STATUS_AM_ORT, "Bin vor Ort"),
        (STATUS_UNTERSTUETZUNG, "Brauche Unterstuetzung"),
        (STATUS_NICHT_VERFUEGBAR, "Kann nicht kommen"),
        (STATUS_BRAUCHE_DEFI, "Brauche Defibrillator"),
        (STATUS_BRAUCHE_RTW, "Bitte RTW verstaendigen (112)"),
        (STATUS_BRAUCHE_ZWEITEN_EH, "Brauche zweiten Ersthelfer"),
        (STATUS_BRAUCHE_MATERIAL, "Brauche Verbandsmaterial"),
        (STATUS_PATIENT_TRANSPORTFAEHIG, "Patient transportfaehig"),
        (STATUS_EINSATZ_BEENDET, "Einsatz beendet / kein Arzt noetig"),
    ]

    # Status die als kritisch/dringend gelten (Hervorhebung in der Uebersicht)
    STATUS_KRITISCH = frozenset({
        STATUS_UNTERSTUETZUNG,
        STATUS_BRAUCHE_DEFI,
        STATUS_BRAUCHE_RTW,
        STATUS_BRAUCHE_ZWEITEN_EH,
    })

    STATUS_FARBE = {
        STATUS_UNTERWEGS: "warning",
        STATUS_AM_ORT: "success",
        STATUS_UNTERSTUETZUNG: "danger",
        STATUS_NICHT_VERFUEGBAR: "secondary",
        STATUS_BRAUCHE_DEFI: "danger",
        STATUS_BRAUCHE_RTW: "danger",
        STATUS_BRAUCHE_ZWEITEN_EH: "warning",
        STATUS_BRAUCHE_MATERIAL: "warning",
        STATUS_PATIENT_TRANSPORTFAEHIG: "info",
        STATUS_EINSATZ_BEENDET: "success",
    }

    ersthelfer = models.ForeignKey(
        "hr.HRMitarbeiter",
        on_delete=models.PROTECT,
        related_name="eh_rueckmeldungen",
        verbose_name="Ersthelfer/in",
    )
    gemeldet_am = models.DateTimeField(auto_now_add=True)
    notiz = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Notiz",
        help_text="Optionaler Freitext",
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        verbose_name="Status",
    )
    vorfall = models.ForeignKey(
        ErsteHilfeVorfall,
        on_delete=models.CASCADE,
        related_name="rueckmeldungen",
        verbose_name="Vorfall",
    )

    class Meta:
        ordering = ["-gemeldet_am"]
        verbose_name = "EH-Rueckmeldung"
        verbose_name_plural = "EH-Rueckmeldungen"

    def __str__(self):
        return f"{self.ersthelfer.vollname}: {self.get_status_display()}"

    @property
    def farbe(self):
        return self.STATUS_FARBE.get(self.status, "secondary")
