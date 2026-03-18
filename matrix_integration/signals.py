"""
Signals fuer die matrix_integration-App.

Laedt automatisch alle Mitglieder ein wenn ein MatrixRaum gespeichert wird.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="matrix_integration.MatrixRaum")
def auto_einladungen_bei_raum_speichern(sender, instance, **kwargs):
    """Laedt alle Mitglieder des Raums ein wenn er gespeichert wird.

    Reihenfolge:
    1. Teilnehmer-Template (manuell oder aus Org-Einheit)
    2. Direkt zugeordnete Org-Einheit des Raums
    Schlaegt still fehl – unterbricht nie den Speichervorgang.
    """
    if not instance.ist_aktiv or not instance.room_id:
        return

    try:
        from matrix_integration.synapse_service import _matrix_user_id, einladen_in_raum

        user_ids = set()

        # Mitglieder aus Teilnehmer-Template
        if instance.teilnehmer_template_id:
            mitglieder = instance.teilnehmer_template.get_user_list()
            user_ids.update(mitglieder)

        # Mitglieder aus Org-Einheit des Raums
        if instance.org_einheit_id:
            from hr.models import HRMitarbeiter
            ma_qs = HRMitarbeiter.objects.filter(
                stelle__org_einheit_id=instance.org_einheit_id,
                user__isnull=False,
            ).select_related("user")
            for ma in ma_qs:
                user_ids.add(ma.user_id)

        if not user_ids:
            return

        from django.contrib.auth.models import User
        for user in User.objects.filter(pk__in=user_ids, is_active=True):
            matrix_id = _matrix_user_id(user.username)
            if matrix_id:
                einladen_in_raum(instance.room_id, matrix_id)

        logger.info(
            "Raum %s: %s Einladungen gesendet.", instance.name, len(user_ids)
        )
    except Exception as exc:
        logger.warning(
            "Auto-Einladungen fuer Raum %s fehlgeschlagen: %s", instance.name, exc
        )
