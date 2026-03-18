"""
Management-Command: Pollt Matrix-DMs und EH_PING-Textnachrichten auf Ersthelfer-Rueckmeldungen.

Laeuft alle 30 Sekunden im Scheduler. Wertet aus:
  - Zahl-Antworten (1/2/3/4) in persoenlichen DM-Raeumen (Option B)
  - Zahl-Antworten (1/2/3/4) direkt im EH_PING-Kanal (Option C)

Beide Quellen schreiben in dieselbe ErsteHilfeRueckmeldung.
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Keyword → Status-Mapping (DM-Antworten und EH_PING-Textnachrichten)
KEYWORD_STATUS = {
    # Basis-Status (1-4)
    "1": "unterwegs",
    "unterwegs": "unterwegs",
    "komme": "unterwegs",
    "2": "am_ort",
    "da": "am_ort",
    "vor ort": "am_ort",
    "bin da": "am_ort",
    "3": "brauche_unterstuetzung",
    "hilfe": "brauche_unterstuetzung",
    "unterstuetzung": "brauche_unterstuetzung",
    "4": "nicht_verfuegbar",
    "nein": "nicht_verfuegbar",
    "kann nicht": "nicht_verfuegbar",
    "nicht verfuegbar": "nicht_verfuegbar",
    # Bedarfsmeldungen vor Ort (5-10)
    "5": "brauche_defi",
    "defi": "brauche_defi",
    "defibrillator": "brauche_defi",
    "6": "brauche_rtw",
    "rtw": "brauche_rtw",
    "rettungswagen": "brauche_rtw",
    "112": "brauche_rtw",
    "7": "brauche_zweiten_eh",
    "zweiter": "brauche_zweiten_eh",
    "zweiter ersthelfer": "brauche_zweiten_eh",
    "8": "brauche_material",
    "material": "brauche_material",
    "verband": "brauche_material",
    "verbandsmaterial": "brauche_material",
    "9": "patient_transportfaehig",
    "transportfaehig": "patient_transportfaehig",
    "transport": "patient_transportfaehig",
    "10": "einsatz_beendet",
    "beendet": "einsatz_beendet",
    "fertig": "einsatz_beendet",
    "erledigt": "einsatz_beendet",
}


def _matrix_id_zu_ersthelfer(matrix_id):
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


def _rueckmeldung_speichern(vorfall, ersthelfer, status, quelle):
    """Legt eine ErsteHilfeRueckmeldung an (falls noch nicht vorhanden fuer diesen Status)."""
    from config.kommunikation_utils import matrix_nachricht_senden
    from django.conf import settings

    from ersthelfe.models import ErsteHilfeRueckmeldung

    # Bereits dieselbe Rueckmeldung vorhanden?
    bereits = ErsteHilfeRueckmeldung.objects.filter(
        vorfall=vorfall,
        ersthelfer=ersthelfer,
        status=status,
    ).exists()
    if bereits:
        return False

    ErsteHilfeRueckmeldung.objects.create(
        vorfall=vorfall,
        ersthelfer=ersthelfer,
        status=status,
        notiz=f"via Matrix ({quelle})",
    )
    logger.info(
        "Rueckmeldung gespeichert: Vorfall %s, %s -> %s (%s)",
        vorfall.pk, ersthelfer.vollname, status, quelle,
    )

    # Bestaetigung im EH_PING posten
    status_labels = {
        "unterwegs": "ist unterwegs",
        "am_ort": "ist vor Ort",
        "brauche_unterstuetzung": "braucht Unterstuetzung!",
        "nicht_verfuegbar": "kann nicht kommen",
        "brauche_defi": "braucht einen Defibrillator!",
        "brauche_rtw": "fordert RTW an – bitte 112 verstaendigen!",
        "brauche_zweiten_eh": "braucht einen zweiten Ersthelfer!",
        "brauche_material": "braucht Verbandsmaterial",
        "patient_transportfaehig": "meldet: Patient transportfaehig",
        "einsatz_beendet": "meldet: Einsatz beendet",
    }
    eh_ping_room = getattr(settings, "MATRIX_EH_PING_ROOM_ID", "")
    if eh_ping_room:
        matrix_nachricht_senden(
            eh_ping_room,
            f"EH-Rueckmeldung: {ersthelfer.vollname} {status_labels.get(status, status)}",
        )
    return True


def _freitext_speichern(vorfall, ersthelfer, absender_matrix_id, text):
    """Speichert eine unstrukturierte Textnachricht als ErsteHilfeNachricht."""
    from ersthelfe.models import ErsteHilfeNachricht

    # Duplikat verhindern: gleicher Text + Ersthelfer in den letzten 60 Sekunden
    from django.utils import timezone
    from datetime import timedelta
    grenze = timezone.now() - timedelta(seconds=60)
    bereits = ErsteHilfeNachricht.objects.filter(
        vorfall=vorfall,
        absender=ersthelfer,
        text=text,
        gesendet_am__gte=grenze,
    ).exists()
    if bereits:
        return

    ErsteHilfeNachricht.objects.create(
        vorfall=vorfall,
        absender=ersthelfer,
        absender_matrix_id=absender_matrix_id,
        text=text,
    )
    logger.info(
        "Freitext-Nachricht gespeichert: Vorfall %s, %s: %s",
        vorfall.pk, ersthelfer.vollname, text[:60],
    )


class Command(BaseCommand):
    help = "Pollt Matrix-Reaktionen und DM-Antworten auf EH-Alarme"

    def handle(self, *args, **options):
        from config.kommunikation_utils import matrix_messages_seit_token
        from django.conf import settings

        from ersthelfe.models import ErsteHilfeVorfall

        eh_ping_room = getattr(settings, "MATRIX_EH_PING_ROOM_ID", "")
        bot_kuerzel = "prima-bot"
        server_name = getattr(settings, "MATRIX_SERVER_NAME", "")
        bot_id = f"@{bot_kuerzel}:{server_name}" if server_name else ""

        offene_vorfaelle = ErsteHilfeVorfall.objects.filter(
            status=ErsteHilfeVorfall.STATUS_OFFEN,
        )

        for vorfall in offene_vorfaelle:

            # --- Option C: Textnachrichten im EH_PING-Kanal ---
            if eh_ping_room and vorfall.matrix_ping_since_token:
                nachrichten, neuer_token = matrix_messages_seit_token(
                    eh_ping_room,
                    since_token=vorfall.matrix_ping_since_token,
                )
                if neuer_token and neuer_token != vorfall.matrix_ping_since_token:
                    vorfall.matrix_ping_since_token = neuer_token
                    vorfall.save(update_fields=["matrix_ping_since_token"])

                for msg in nachrichten:
                    if bot_id and msg["sender"] == bot_id:
                        continue
                    ersthelfer = _matrix_id_zu_ersthelfer(msg["sender"])
                    if not ersthelfer:
                        continue
                    schluessel = msg["body"].lower().strip()
                    status = KEYWORD_STATUS.get(schluessel)
                    if not status:
                        for kw, st in KEYWORD_STATUS.items():
                            if schluessel.startswith(kw):
                                status = st
                                break
                    if status:
                        _rueckmeldung_speichern(vorfall, ersthelfer, status, "EH-PING-Antwort")
                    else:
                        # Unbekannter Text → als Freitextnachricht speichern
                        _freitext_speichern(vorfall, ersthelfer, msg["sender"], msg["body"])
