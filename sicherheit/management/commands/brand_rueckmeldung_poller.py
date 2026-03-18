"""
Management-Command: Pollt Matrix-DMs auf Branderkunder-Rueckmeldungen.

Laeuft alle 30 Sekunden im Scheduler.
Wertet Zahl-Antworten in persoenlichen DM-Raeumen aus:
  1 – unterwegs
  2 – Brand bestaetigt (Feueralarm)
  3 / Freitext – Lagemeldung / freie Nachricht
  9 – Fehlalarm
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

KEYWORD_STATUS = {
    "1": "unterwegs",
    "unterwegs": "unterwegs",
    "komme": "unterwegs",
    "auf dem weg": "unterwegs",
    "2": "bestaetigt",
    "feuer": "bestaetigt",
    "brand": "bestaetigt",
    "feueralarm": "bestaetigt",
    "bestaetigt": "bestaetigt",
    "9": "fehlalarm",
    "fehlalarm": "fehlalarm",
    "kein brand": "fehlalarm",
    "kein feuer": "fehlalarm",
    "alles ok": "fehlalarm",
}


def _matrix_id_zu_erkunder(matrix_id):
    """Loeest eine Matrix-ID (@kuerzel:server) in einen HRMitarbeiter auf."""
    from django.conf import settings
    from hr.models import HRMitarbeiter

    server_name = getattr(settings, "MATRIX_SERVER_NAME", "")
    if not matrix_id.endswith(f":{server_name}"):
        return None
    kuerzel = matrix_id.split(":")[0].lstrip("@")
    return HRMitarbeiter.objects.filter(
        stelle__kuerzel=kuerzel
    ).select_related("stelle").first()


def _security_ping(text):
    """Sendet kurzen Status-Ping an den Security-Raum."""
    from django.conf import settings
    from config.kommunikation_utils import matrix_nachricht_senden

    room = getattr(settings, "MATRIX_SECURITY_PING_ROOM_ID", "")
    if room:
        matrix_nachricht_senden(room, text)


def _verarbeite_rueckmeldung(token_obj, erkunder, status, notiz=""):
    """Aktualisiert Token-Status und benachrichtigt Security."""
    from django.utils import timezone
    from sicherheit.models import Brandalarm, BranderkunderToken

    brandalarm = token_obj.brandalarm

    if status == "unterwegs":
        if token_obj.status == BranderkunderToken.STATUS_AUSSTEHEND:
            token_obj.status = BranderkunderToken.STATUS_UNTERWEGS
            token_obj.save(update_fields=["status"])
        _security_ping(
            f"Branderkunder {erkunder.vollname} ist UNTERWEGS"
            f" – Brandort: {brandalarm.ort}"
        )
        logger.info("Brand-DM: %s -> unterwegs (Alarm %s)", erkunder.vollname, brandalarm.pk)

    elif status == "bestaetigt":
        token_obj.status = BranderkunderToken.STATUS_BESTAETIGT
        if notiz:
            token_obj.notiz = notiz
        token_obj.save(update_fields=["status", "notiz"])
        if brandalarm.status == Brandalarm.STATUS_GEMELDET:
            brandalarm.status = Brandalarm.STATUS_BESTAETIGUNG
            brandalarm.save(update_fields=["status"])
        _security_ping(
            f"Branderkunder {erkunder.vollname} BESTAETIGT Brand"
            f" – Ort: {brandalarm.ort}"
            f" – Bitte Security-Review: /sicherheit/brand/{brandalarm.pk}/security/"
        )
        logger.info("Brand-DM: %s -> Brand bestaetigt (Alarm %s)", erkunder.vollname, brandalarm.pk)

    elif status == "fehlalarm":
        token_obj.status = BranderkunderToken.STATUS_FEHLALARM
        token_obj.save(update_fields=["status"])
        _security_ping(
            f"Branderkunder {erkunder.vollname} meldet FEHLALARM"
            f" – Ort: {brandalarm.ort}"
        )
        # Alle Fehlalarm? Dann Alarm automatisch schliessen
        alle_fehlalarm = not brandalarm.erkunder_tokens.exclude(
            status=BranderkunderToken.STATUS_FEHLALARM
        ).exists()
        if alle_fehlalarm and brandalarm.status == Brandalarm.STATUS_GEMELDET:
            brandalarm.status = Brandalarm.STATUS_GESCHLOSSEN
            brandalarm.geschlossen_am = timezone.now()
            brandalarm.save(update_fields=["status", "geschlossen_am"])
        logger.info("Brand-DM: %s -> Fehlalarm (Alarm %s)", erkunder.vollname, brandalarm.pk)


def _freitext_verarbeiten(token_obj, erkunder, text):
    """Speichert Freitext-Meldung als Notiz und pingt Security."""
    from sicherheit.models import BranderkunderToken

    brandalarm = token_obj.brandalarm
    token_obj.notiz = text[:500]
    if token_obj.status == BranderkunderToken.STATUS_AUSSTEHEND:
        token_obj.status = BranderkunderToken.STATUS_AM_ORT
    token_obj.save(update_fields=["notiz", "status"])
    _security_ping(
        f"Branderkunder {erkunder.vollname}: {text[:200]}"
        f" – Ort: {brandalarm.ort}"
    )
    logger.info(
        "Brand-DM Freitext: %s – %s (Alarm %s)",
        erkunder.vollname, text[:60], brandalarm.pk,
    )


class Command(BaseCommand):
    help = "Pollt Matrix-DM-Antworten auf Brand-Erkunder-Alarme"

    def handle(self, *args, **options):
        from django.conf import settings
        from config.kommunikation_utils import matrix_messages_seit_token
        from sicherheit.models import Brandalarm, BranderkunderToken

        server_name = getattr(settings, "MATRIX_SERVER_NAME", "")
        bot_id = f"@prima-bot:{server_name}" if server_name else ""

        # Nur Tokens aktiver Alarme mit DM-Raum und since_token pollen
        tokens = (
            BranderkunderToken.objects
            .filter(
                matrix_dm_room_id__gt="",
                matrix_dm_since_token__gt="",
                brandalarm__status__in=[
                    Brandalarm.STATUS_GEMELDET,
                    Brandalarm.STATUS_BESTAETIGUNG,
                    Brandalarm.STATUS_EVAKUIERUNG,
                ],
            )
            .exclude(status__in=[
                BranderkunderToken.STATUS_FEHLALARM,
                BranderkunderToken.STATUS_BESTAETIGT,
            ])
            .select_related("erkunder__stelle", "brandalarm")
        )

        for token_obj in tokens:
            try:
                nachrichten, neuer_token = matrix_messages_seit_token(
                    token_obj.matrix_dm_room_id,
                    since_token=token_obj.matrix_dm_since_token,
                )
            except Exception as exc:
                logger.warning(
                    "Brand-Poller: Fehler beim Polling fuer Token %s: %s",
                    token_obj.pk, exc,
                )
                continue

            if neuer_token and neuer_token != token_obj.matrix_dm_since_token:
                token_obj.matrix_dm_since_token = neuer_token
                token_obj.save(update_fields=["matrix_dm_since_token"])

            erkunder = token_obj.erkunder

            for msg in nachrichten:
                # Eigene Bot-Nachrichten ignorieren
                if bot_id and msg["sender"] == bot_id:
                    continue
                # Nur Nachrichten vom zugewiesenen Erkunder
                absender = _matrix_id_zu_erkunder(msg["sender"])
                if not absender or absender.pk != erkunder.pk:
                    continue

                schluessel = msg["body"].lower().strip()
                status = KEYWORD_STATUS.get(schluessel)
                # Prefix-Match (z.B. "fehlalarm – es war nur der Toaster")
                if not status:
                    for kw, st in KEYWORD_STATUS.items():
                        if schluessel.startswith(kw):
                            status = st
                            break

                if status:
                    _verarbeite_rueckmeldung(token_obj, erkunder, status, notiz=msg["body"])
                else:
                    # Unbekannter Text → Freitext-Meldung
                    _freitext_verarbeiten(token_obj, erkunder, msg["body"])
