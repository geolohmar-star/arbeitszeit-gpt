"""
Management-Command: matrix_sitzung_erinnerungen

Prueft alle aktiven Sitzungen und sendet Matrix-Erinnerungsnachrichten
wenn der konfigurierte Erinnerungszeitpunkt erreicht ist.

Wird jede Minute vom Scheduler-Container aufgerufen.

Aufruf:
    python manage.py matrix_sitzung_erinnerungen
"""
import datetime
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sendet Matrix-Erinnerungen fuer anstehende Sitzungen."

    def handle(self, *args, **options):
        from matrix_integration.models import SitzungsKalender
        from matrix_integration.synapse_service import sende_nachricht

        jetzt = timezone.localtime(timezone.now())

        # Alle aktiven Sitzungen mit gesetztem naechste_ausfuehrung laden
        sitzungen = SitzungsKalender.objects.filter(
            ist_aktiv=True,
            naechste_ausfuehrung__isnull=False,
            matrix_raum__ist_aktiv=True,
        ).exclude(
            matrix_raum__room_id=""
        ).select_related("matrix_raum")

        gesendet = 0
        for sitzung in sitzungen:
            naechste = timezone.localtime(sitzung.naechste_ausfuehrung)
            erinnerung_zeitpunkt = naechste - datetime.timedelta(minutes=sitzung.erinnerung_minuten)

            # Bereits fuer diese Ausfuehrung gesendet?
            if sitzung.erinnerung_gesendet_am and sitzung.erinnerung_gesendet_am >= erinnerung_zeitpunkt:
                continue

            # Ist es Zeit fuer die Erinnerung? (Fenster: erinnerung_zeitpunkt bis Sitzungsbeginn)
            if not (erinnerung_zeitpunkt <= jetzt <= naechste):
                continue

            # Nachricht zusammenbauen
            uhrzeit = naechste.strftime("%H:%M")
            datum = naechste.strftime("%d.%m.%Y")
            wochentag = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                         "Freitag", "Samstag", "Sonntag"][naechste.weekday()]

            nachricht = (
                f"Erinnerung: {sitzung.name}\n"
                f"Heute {wochentag}, {datum} um {uhrzeit} Uhr"
            )
            if sitzung.beschreibung:
                nachricht += f"\n{sitzung.beschreibung}"

            room_id = sitzung.matrix_raum.room_id
            erfolg = sende_nachricht(room_id, nachricht)

            if erfolg:
                # Erinnerung als gesendet markieren
                sitzung.erinnerung_gesendet_am = jetzt
                # naechste_ausfuehrung fuer wiederkehrende Sitzungen nach dem Termin zuruecksetzen
                # (wird vom naechsten Durchlauf nach Sitzungsende neu berechnet)
                sitzung.save(update_fields=["erinnerung_gesendet_am"])
                gesendet += 1
                logger.info("Erinnerung gesendet: %s um %s", sitzung.name, uhrzeit)
            else:
                logger.warning("Erinnerung fehlgeschlagen: %s", sitzung.name)

        # Abgelaufene Sitzungen: naechste_ausfuehrung neu berechnen
        _naechste_ausfuehrung_aktualisieren(jetzt)

        if gesendet:
            self.stdout.write(f"{gesendet} Erinnerung(en) gesendet.\n")


def _naechste_ausfuehrung_aktualisieren(jetzt):
    """Aktualisiert naechste_ausfuehrung fuer Sitzungen deren Termin abgelaufen ist."""
    from matrix_integration.models import SitzungsKalender

    abgelaufen = SitzungsKalender.objects.filter(
        ist_aktiv=True,
        naechste_ausfuehrung__lt=jetzt,
    )

    for sitzung in abgelaufen:
        neue_ausfuehrung = sitzung.berechne_naechste_ausfuehrung()
        if neue_ausfuehrung:
            sitzung.naechste_ausfuehrung = neue_ausfuehrung
        else:
            # Keine weiteren Ausfuehrungen (einmalig oder Enddatum ueberschritten)
            sitzung.ist_aktiv = False
            sitzung.naechste_ausfuehrung = None
        sitzung.save(update_fields=["naechste_ausfuehrung", "ist_aktiv"])
