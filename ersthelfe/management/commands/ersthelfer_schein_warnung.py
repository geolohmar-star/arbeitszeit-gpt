"""
Management-Command: Ersthelfer-Schein-Ablaufwarnung per Matrix-DM.

Sendet 30, 14 und 7 Tage vor Ablauf des Erste-Hilfe-Scheins eine persoenliche
Warnung an den betroffenen Ersthelfer sowie an den Betriebsarzt.

Ausfuehren:
    python manage.py ersthelfer_schein_warnung
    python manage.py ersthelfer_schein_warnung --dry-run
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

WARN_TAGE = [30, 14, 7]


class Command(BaseCommand):
    help = "Sendet Ersthelfer-Schein-Ablaufwarnungen (30/14/7 Tage vor Ablauf)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Keine Nachrichten senden – nur anzeigen was gesendet wuerden",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        from config.kommunikation_utils import matrix_dm_senden
        from hr.models import HRMitarbeiter

        dry_run = options["dry_run"]
        heute = timezone.localdate()
        matrix_server = getattr(settings, "MATRIX_SERVER_NAME", "")
        basis_url = getattr(settings, "PRIMA_BASE_URL", "http://127.0.0.1:8000")

        gewarnte = 0

        for tage in WARN_TAGE:
            zieldatum = heute + timezone.timedelta(days=tage)
            kandidaten = HRMitarbeiter.objects.filter(
                ist_ersthelfer=True,
                ersthelfer_gueltig_bis=zieldatum,
                user__isnull=False,
                user__is_active=True,
            ).select_related("user", "stelle")

            for ma in kandidaten:
                self.stdout.write(
                    f"Warnung an {ma.vollname}: Schein laeuft in {tage} Tagen ab "
                    f"({zieldatum.strftime('%d.%m.%Y')})"
                )

                if dry_run:
                    continue

                if not matrix_server:
                    logger.debug("MATRIX_SERVER_NAME nicht konfiguriert – kein DM.")
                    continue

                if ma.stelle:
                    matrix_id = f"@{ma.stelle.kuerzel}:{matrix_server}"
                else:
                    matrix_id = f"@{ma.user.username}:{matrix_server}"

                dm_text = (
                    f"[PRIMA] Ersthelfer-Schein laeuft in {tage} Tagen ab!\n"
                    f"Dein Erste-Hilfe-Schein gilt noch bis {zieldatum.strftime('%d.%m.%Y')}.\n"
                    f"Bitte eine Auffrischungsschulung buchen.\n"
                    f"Infos: {basis_url}/ersthelfe/"
                )
                matrix_dm_senden(matrix_id, dm_text)
                gewarnte += 1

                # Auch Betriebsarzt informieren
                try:
                    arzt = HRMitarbeiter.objects.filter(
                        stelle__ist_betriebsarzt=True,
                        user__isnull=False,
                        user__is_active=True,
                    ).select_related("user", "stelle").first()
                    if arzt and arzt != ma:
                        if arzt.stelle:
                            arzt_id = f"@{arzt.stelle.kuerzel}:{matrix_server}"
                        else:
                            arzt_id = f"@{arzt.user.username}:{matrix_server}"
                        matrix_dm_senden(
                            arzt_id,
                            f"[PRIMA] Ersthelfer-Schein von {ma.vollname} "
                            f"laeuft in {tage} Tagen ab ({zieldatum.strftime('%d.%m.%Y')}).",
                        )
                except Exception:
                    logger.exception("Fehler beim Benachrichtigen des Betriebsarzts")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN – keine Nachrichten gesendet."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"{gewarnte} Warnungen gesendet."
            ))
