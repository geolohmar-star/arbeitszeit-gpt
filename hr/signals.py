# hr/signals.py
"""
Django Signals fuer die HR-App.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="hr.HRMitarbeiter")
def auto_matrix_einladung(sender, instance, created, **kwargs):
    """Laedt einen neuen Mitarbeiter automatisch in die Matrix-Raeume seiner Org-Einheit ein.

    Wird auch ausgeloest wenn eine bestehende Stelle geaendert wird (Versetzung).
    Schlaegt still fehl – unterbricht nie den Speichervorgang.
    """
    if not instance.stelle_id:
        return
    try:
        from matrix_integration.synapse_service import einladen_in_org_einheit_raeume
        einladen_in_org_einheit_raeume(instance)
    except Exception as exc:
        logger.warning(
            "Matrix-Auto-Einladung fuer HRMitarbeiter pk=%s fehlgeschlagen: %s",
            instance.pk,
            exc,
        )


@receiver(post_save, sender="hr.HRMitarbeiter")
def auto_standard_passwort(sender, instance, created, **kwargs):
    """Setzt hrmitarbeiter2026 als Startpasswort wenn ein neuer HRMitarbeiter
    mit einem frisch angelegten User-Account verknuepft wird.

    Nur bei created=True und nur wenn der User noch das unbrauchbare
    Django-Default-Passwort hat (kein gueltiges Passwort gesetzt).
    """
    if not created:
        return
    if not instance.user_id:
        return
    try:
        user = instance.user
        # Nur setzen wenn der User noch kein nutzbares Passwort hat
        if not user.has_usable_password():
            user.set_password("hrmitarbeiter2026")
            user.save(update_fields=["password"])
    except Exception as exc:
        logger.warning(
            "Standard-Passwort fuer HRMitarbeiter pk=%s fehlgeschlagen: %s",
            instance.pk,
            exc,
        )


def _ping_raeume_fuer_mitarbeiter(instance):
    """Gibt eine Liste von (room_id, beschreibung) zurueck die ein Mitarbeiter
    aufgrund seiner HR-Kennzeichnungen betreten soll.

    EH-Ping-Raum:
      - ist_ersthelfer = True
      - Stelle ist_betriebsarzt = True
      - Stelle-Kuerzel ist EH-Verantwortlicher (al_as)

    Security-Ping-Raum:
      - Stelle-Kuerzel in Security-Kuerzelliste
      - ist_branderkunder = True
      - ist_brandbekaempfer = True
      - ist_raeumungshelfer = True
    """
    from django.conf import settings

    _SECURITY_KUERZEL = frozenset([
        "al_sec", "sv_sec",
        "ma_sec1", "ma_sec2", "ma_sec3", "ma_sec4",
        "pf_sec", "al_as", "ba_as", "gf1", "gf_tech", "gf_verw",
    ])
    _EH_VERANTWORTLICH_KUERZEL = frozenset(["al_as"])

    raeume = []

    stelle = getattr(instance, "stelle", None)
    stelle_kuerzel = stelle.kuerzel if stelle else ""
    ist_betriebsarzt = bool(stelle and getattr(stelle, "ist_betriebsarzt", False))

    eh_raum = getattr(settings, "MATRIX_EH_PING_ROOM_ID", "")
    if eh_raum:
        if (
            instance.ist_ersthelfer
            or ist_betriebsarzt
            or stelle_kuerzel in _EH_VERANTWORTLICH_KUERZEL
        ):
            raeume.append((eh_raum, "EH-Ping"))

    sec_raum = getattr(settings, "MATRIX_SECURITY_PING_ROOM_ID", "")
    if sec_raum:
        if (
            stelle_kuerzel in _SECURITY_KUERZEL
            or instance.ist_brandbekaempfer
        ):
            raeume.append((sec_raum, "Security-Ping"))

    erkunder_raum = getattr(settings, "MATRIX_BRANDERKUNDER_ROOM_ID", "")
    if erkunder_raum and instance.ist_branderkunder:
        raeume.append((erkunder_raum, "Branderkunder"))

    raeumungs_raum = getattr(settings, "MATRIX_RAEUMUNGSHELFER_ROOM_ID", "")
    if raeumungs_raum and instance.ist_raeumungshelfer:
        raeume.append((raeumungs_raum, "Raeumungshelfer"))

    return raeume


@receiver(post_save, sender="hr.HRMitarbeiter")
def auto_ping_raum_einladung(sender, instance, created, **kwargs):
    """Laedt einen Mitarbeiter automatisch in alle Ping-Raeume ein die
    seinen HR-Kennzeichnungen entsprechen.

    Abgedeckt: EH-Ping (Ersthelfer, Betriebsarzt, EH-Verantwortlicher)
    und Security-Ping (Security-Stellen, Brandschutz-Flags).
    Schlaegt still fehl – unterbricht nie den Speichervorgang.
    """
    try:
        from django.conf import settings

        from config.kommunikation_utils import matrix_nutzer_in_raum_einladen

        server_name = getattr(settings, "MATRIX_SERVER_NAME", "")
        if not server_name:
            return

        stelle = getattr(instance, "stelle", None)
        if not stelle:
            return  # kein Stellen-Kuerzel – kein Matrix-Login moeglich
        kuerzel = stelle.kuerzel

        matrix_id = f"@{kuerzel}:{server_name}"
        raeume = _ping_raeume_fuer_mitarbeiter(instance)

        for room_id, beschreibung in raeume:
            matrix_nutzer_in_raum_einladen(room_id, matrix_id)
            logger.info(
                "%s-Einladung gesendet an %s (HRMitarbeiter pk=%s)",
                beschreibung, matrix_id, instance.pk,
            )

    except Exception as exc:
        logger.warning(
            "auto_ping_raum_einladung fuer HRMitarbeiter pk=%s fehlgeschlagen: %s",
            instance.pk,
            exc,
        )


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
