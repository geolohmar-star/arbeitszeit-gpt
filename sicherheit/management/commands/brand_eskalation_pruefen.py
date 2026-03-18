"""
Management-Command: brand_eskalation_pruefen

Prueft alle aktiven Brandalarme mit Status 'gemeldet'.
Wenn nach 90 Sekunden kein einziger Erkunder reagiert hat (alle Tokens
noch 'ausstehend'), wird der Alarm automatisch auf 'bestaetigung' eskaliert
und Security per Matrix + ntfy alarmiert.

Wird vom Scheduler alle 10 Sekunden aufgerufen.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from sicherheit.models import Brandalarm, BranderkunderToken

logger = logging.getLogger(__name__)

ESKALATIONS_SCHWELLE_SEKUNDEN = 90


class Command(BaseCommand):
    help = "Branderkunder-Timeout pruefen und ggf. auf Security-Review eskalieren."

    def handle(self, *args, **options):
        jetzt = timezone.now()
        schwelle = jetzt - timezone.timedelta(seconds=ESKALATIONS_SCHWELLE_SEKUNDEN)

        # Alarme die aelter als 90s sind und noch im Status 'gemeldet'
        kandidaten = Brandalarm.objects.filter(
            status=Brandalarm.STATUS_GEMELDET,
            erstellt_am__lte=schwelle,
        ).prefetch_related("erkunder_tokens")

        for alarm in kandidaten:
            tokens = list(alarm.erkunder_tokens.all())

            # Nur eskalieren wenn KEIN Erkunder geantwortet hat
            hat_reaktion = any(
                t.status != BranderkunderToken.STATUS_AUSSTEHEND for t in tokens
            )
            if hat_reaktion:
                continue

            # Eskalation: Kein Erkunder hat reagiert
            alarm.status = Brandalarm.STATUS_BESTAETIGUNG
            alarm.notiz = (
                (alarm.notiz + "\n" if alarm.notiz else "")
                + "Automatisch eskaliert: kein Erkunder hat innerhalb von "
                f"{ESKALATIONS_SCHWELLE_SEKUNDEN}s reagiert."
            )
            alarm.save(update_fields=["status", "notiz"])

            logger.warning(
                "Brandalarm %s eskaliert (kein Erkunder nach %ds).",
                alarm.pk, ESKALATIONS_SCHWELLE_SEKUNDEN,
            )
            self.stdout.write(
                f"Brandalarm #{alarm.pk} eskaliert – kein Erkunder hat reagiert.\n"
            )
            self.stdout.flush()

            self._benachrichtige_security(alarm)

    def _benachrichtige_security(self, alarm):
        """Sendet Security-Ping und ntfy bei automatischer Eskalation."""
        try:
            from django.conf import settings
            from config.kommunikation_utils import matrix_nachricht_senden

            ort = alarm.ort_aktuell
            nachricht = (
                f"BRANDALARM ESKALIERT (kein Erkunder-Rueckmeldung nach "
                f"{ESKALATIONS_SCHWELLE_SEKUNDEN}s)\n"
                f"Ort: {ort}\n"
                f"Security-Review erforderlich – bitte sofort pruefen!"
            )

            # Matrix Security-Ping
            room = getattr(settings, "MATRIX_SECURITY_PING_ROOM_ID", "")
            if room:
                matrix_nachricht_senden(room, nachricht)

            # ntfy
            from sicherheit.views import _ntfy_push
            ntfy_url = getattr(settings, "NTFY_URL", "").rstrip("/")
            brand_topic = getattr(settings, "NTFY_BRAND_TOPIC", "brand-alarm-prima")
            if ntfy_url:
                _ntfy_push(
                    ntfy_url,
                    brand_topic,
                    title="BRAND – KEIN ERKUNDER",
                    body=f"Ort: {ort} – kein Erkunder hat reagiert! Security: Review erforderlich.",
                    priority="urgent",
                )
        except Exception as exc:
            logger.warning("Eskalations-Benachrichtigung fehlgeschlagen: %s", exc)
