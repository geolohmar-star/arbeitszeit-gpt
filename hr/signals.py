# hr/signals.py
"""
Django Signals fuer die HR-App.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="hr.HRMitarbeiter")
def auto_erstelle_zertifikat(sender, instance, created, **kwargs):
    """Stellt automatisch ein Signatur-Zertifikat aus wenn ein neuer
    HRMitarbeiter angelegt wird und dieser einen Django-User hat.

    Schlaegt still fehl – unterbricht nie den Speichervorgang.
    """
    if not created:
        return
    if not instance.user_id:
        return
    try:
        from signatur.services import erstelle_mitarbeiter_zertifikat
        erstelle_mitarbeiter_zertifikat(instance.user)
    except Exception as exc:
        logger.warning(
            "Auto-Zertifikat fuer HRMitarbeiter pk=%s fehlgeschlagen: %s",
            instance.pk,
            exc,
        )
