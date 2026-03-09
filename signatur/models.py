import logging

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class RootCA(models.Model):
    """Interne Root-CA – einmaliges Singleton."""

    zertifikat_pem = models.TextField(verbose_name="Root-Zertifikat (PEM)")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_bis = models.DateField()
    organisation = models.CharField(max_length=200, default="Intern")
    common_name = models.CharField(max_length=200, default="Interne Root CA")

    class Meta:
        verbose_name = "Root-CA"
        verbose_name_plural = "Root-CA"

    def __str__(self):
        return f"Root-CA: {self.common_name} (bis {self.gueltig_bis})"


class MitarbeiterZertifikat(models.Model):
    """X.509-Zertifikat fuer einen Mitarbeiter (fuer FES-Signatur)."""

    STATUS_CHOICES = [
        ("aktiv", "Aktiv"),
        ("gesperrt", "Gesperrt"),
        ("abgelaufen", "Abgelaufen"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signatur_zertifikat",
    )
    zertifikat_pem = models.TextField(verbose_name="Zertifikat (PEM)")

    # Privater Schluessel – Plaintext (wird bei erstem Login automatisch geleert)
    # Dient als Migrations-Feld: leer = Schluessel wurde bereits verschluesselt
    privater_schluessel_pem = models.TextField(
        verbose_name="Privater Schluessel (PEM, Plaintext – wird migriert)",
        blank=True,
    )

    # Verschluesselter privater Schluessel (AES-256-GCM + PBKDF2)
    privater_schluessel_verschluesselt = models.BinaryField(
        null=True,
        blank=True,
        verbose_name="Privater Schluessel (AES-256-GCM verschluesselt)",
    )
    # PBKDF2-Salt (hex, 32 Bytes = 64 Zeichen)
    schluessel_salt = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Schluessel-Salt (PBKDF2, hex)",
    )
    # AES-GCM Nonce (hex, 12 Bytes = 24 Zeichen)
    schluessel_nonce = models.CharField(
        max_length=24,
        blank=True,
        verbose_name="Schluessel-Nonce (AES-GCM, hex)",
    )

    seriennummer = models.CharField(max_length=100, unique=True)
    ausgestellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_von = models.DateField()
    gueltig_bis = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aktiv")
    fingerprint_sha256 = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Mitarbeiter-Zertifikat"
        verbose_name_plural = "Mitarbeiter-Zertifikate"
        ordering = ["-ausgestellt_am"]

    def __str__(self):
        return f"Zertifikat {self.user.get_full_name()} (SN: {self.seriennummer})"

    @property
    def ist_gueltig(self):
        from datetime import date
        return self.status == "aktiv" and self.gueltig_von <= date.today() <= self.gueltig_bis

    @property
    def key_ist_verschluesselt(self) -> bool:
        """True wenn der private Schluessel mit PBKDF2+AES-256-GCM geschuetzt ist."""
        return bool(self.schluessel_salt and self.privater_schluessel_verschluesselt)


class SignaturJob(models.Model):
    """Auftrag fuer eine Signatur – entspricht sign-me Job-Konzept."""

    STATUS_CHOICES = [
        ("pending", "Ausstehend"),
        ("completed", "Abgeschlossen"),
        ("failed", "Fehlgeschlagen"),
    ]

    BACKEND_CHOICES = [
        ("intern", "Intern (pyhanko)"),
        ("sign_me", "sign-me (Bundesdruckerei)"),
        ("gateway", "Gateway (intern → sign-me)"),
    ]

    job_id = models.CharField(max_length=100, unique=True)
    backend = models.CharField(max_length=20, choices=BACKEND_CHOICES, default="intern")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="signatur_jobs",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    abgeschlossen_am = models.DateTimeField(null=True, blank=True)
    dokument_name = models.CharField(max_length=255)
    # Optionale Verknuepfung mit Antraegen etc.
    content_type = models.CharField(max_length=100, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    fehler_meldung = models.TextField(blank=True)

    class Meta:
        verbose_name = "Signatur-Job"
        verbose_name_plural = "Signatur-Jobs"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"Job {self.job_id} – {self.dokument_name} ({self.status})"


class SignaturProtokoll(models.Model):
    """Unveraenderliches Protokoll jeder erfolgreich erstellten Signatur."""

    job = models.OneToOneField(
        SignaturJob, on_delete=models.CASCADE, related_name="protokoll"
    )
    unterzeichner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="signaturen",
    )
    zertifikat = models.ForeignKey(
        MitarbeiterZertifikat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    signiert_am = models.DateTimeField(auto_now_add=True)
    hash_sha256 = models.CharField(
        max_length=64, verbose_name="SHA-256 Dokumenten-Hash"
    )
    signatur_typ = models.CharField(
        max_length=20,
        default="FES",
        choices=[("FES", "Fortgeschrittene Signatur"), ("QES", "Qualifizierte Signatur")],
    )
    # Gespeichertes signiertes PDF
    signiertes_pdf = models.BinaryField(null=True, blank=True)

    class Meta:
        verbose_name = "Signatur-Protokoll"
        verbose_name_plural = "Signatur-Protokolle"
        ordering = ["-signiert_am"]

    def __str__(self):
        return f"Signatur {self.job.dokument_name} von {self.unterzeichner} am {self.signiert_am:%d.%m.%Y}"
