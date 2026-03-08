"""
Signals fuer die Datenschutz-App.

- post_save Mitarbeiter (neu): Signatur-Zertifikat automatisch ausstellen
- pre_save Mitarbeiter: Austritt erkennen und sofort alles sperren
"""
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


@receiver(pre_save, sender="arbeitszeit.Mitarbeiter")
def mitarbeiter_austritt_sperren(sender, instance, **kwargs):
    """Sperrt alle Zugaenge wenn austritt_datum gesetzt wird."""
    if not instance.pk:
        return  # Neuer Datensatz – nichts zu sperren

    try:
        alt = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Austritt wurde neu gesetzt (war vorher leer)
    if not alt.austritt_datum and instance.austritt_datum:
        heute = timezone.now().date()
        if instance.austritt_datum <= heute:
            _sperre_mitarbeiter(instance)


@receiver(post_save, sender="arbeitszeit.Mitarbeiter")
def mitarbeiter_zertifikat_ausstellen(sender, instance, created, **kwargs):
    """Stellt automatisch ein Signatur-Zertifikat aus wenn ein Mitarbeiter neu angelegt wird."""
    if not created:
        return
    if not instance.user_id:
        return

    try:
        _erstelle_zertifikat(instance.user)
    except Exception as exc:
        logger.error(
            "Automatische Zertifikat-Ausstellung fuer Mitarbeiter %s fehlgeschlagen: %s",
            instance.personalnummer,
            exc,
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _sperre_mitarbeiter(mitarbeiter):
    """Sperrt alle Zugaenge eines Mitarbeiters sofort."""
    user = mitarbeiter.user

    # 1. Django-Login sperren
    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])
        logger.info("User %s deaktiviert (Austritt).", user.username)

    # 2. Signatur-Zertifikat sperren
    try:
        from signatur.models import MitarbeiterZertifikat
        gesperrt = MitarbeiterZertifikat.objects.filter(
            user=user, status="aktiv"
        ).update(status="gesperrt")
        if gesperrt:
            logger.info("%d Signatur-Zertifikat(e) fuer %s gesperrt.", gesperrt, user.username)
    except Exception as exc:
        logger.warning("Signatur-Sperrung fuer %s fehlgeschlagen: %s", user.username, exc)

    # 3. Raumbuch-Zutrittsprofil deaktivieren
    try:
        from raumbuch.models import ZutrittsProfil
        ZutrittsProfil.objects.filter(mitarbeiter=user).update(ist_aktiv=False)
    except Exception as exc:
        logger.warning("Zutrittsprofil-Sperrung fuer %s fehlgeschlagen: %s", user.username, exc)

    # 4. Mitarbeiter als inaktiv markieren
    mitarbeiter.aktiv = False
    # Kein save() hier – pre_save-Signal, wird von Django selbst gespeichert

    logger.info(
        "Alle Zugaenge fuer Mitarbeiter %s (Austritt %s) gesperrt.",
        mitarbeiter.personalnummer,
        mitarbeiter.austritt_datum,
    )


def _erstelle_zertifikat(user):
    """Erstellt ein Signatur-Zertifikat fuer einen neuen User."""
    from signatur.models import MitarbeiterZertifikat, RootCA

    # Zertifikat bereits vorhanden?
    if MitarbeiterZertifikat.objects.filter(user=user).exists():
        return

    # Root-CA vorhanden?
    ca = RootCA.objects.first()
    if not ca:
        logger.warning(
            "Kein Root-CA vorhanden – Zertifikat fuer %s kann nicht ausgestellt werden. "
            "Bitte 'python manage.py erstelle_ca' ausfuehren.",
            user.username,
        )
        return

    # CA-Schluessel laden
    import os
    from django.conf import settings
    ca_key_path = settings.BASE_DIR / "signatur" / "ca_root.key.pem"
    if not ca_key_path.exists():
        logger.warning(
            "CA-Schluessel nicht gefunden (%s) – Zertifikat fuer %s wird nicht ausgestellt.",
            ca_key_path,
            user.username,
        )
        return

    # Management-Command-Logik direkt aufrufen
    from django.core.management import call_command
    try:
        call_command("erstelle_ca", user=user.username, verbosity=0)
        logger.info("Signatur-Zertifikat fuer User %s automatisch ausgestellt.", user.username)
    except Exception as exc:
        logger.error("Zertifikat-Ausstellung via erstelle_ca fuer %s fehlgeschlagen: %s", user.username, exc)
