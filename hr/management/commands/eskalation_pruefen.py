"""Management Command: eskalation_pruefen

Prueft alle offenen Antraege auf Eskalations-Timeout.

Aufruf:
    python manage.py eskalation_pruefen
    python manage.py eskalation_pruefen --eskaliere
"""

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from formulare.models import AenderungZeiterfassung, ZAGAntrag, ZAGStorno
from formulare.utils import genehmigende_stelle

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Prueft offene Antraege auf Eskalations-Timeout und meldet Ueberfaellige."

    def add_arguments(self, parser):
        parser.add_argument(
            "--eskaliere",
            action="store_true",
            help="Setzt ueberfaellige Antraege auf Status 'eskaliert'.",
        )

    def handle(self, *args, **options):
        eskaliere = options["eskaliere"]
        heute = date.today()

        # Alle Antragstypen mit Status 'beantragt' zusammenfuehren
        antraege = []
        for Model, label in [
            (AenderungZeiterfassung, "AenderungZeiterfassung"),
            (ZAGAntrag, "ZAGAntrag"),
            (ZAGStorno, "ZAGStorno"),
        ]:
            for antrag in Model.objects.filter(status="beantragt").select_related(
                "antragsteller"
            ):
                antraege.append((antrag, label))

        if not antraege:
            self.stdout.write("Keine offenen Antraege gefunden.")
            return

        ueberfaellig = 0
        eskaliert = 0

        for antrag, label in antraege:
            antragsteller = antrag.antragsteller

            # Verantwortliche Stelle ermitteln
            stelle = genehmigende_stelle(antragsteller)
            if stelle is None:
                # Kein Stellensystem fuer diesen Mitarbeiter konfiguriert
                continue

            eskalation_nach = stelle.eskalation_nach_tagen
            erstellt_datum = antrag.erstellt_am.date()
            faellig_datum = erstellt_datum + timedelta(days=eskalation_nach)

            if heute > faellig_datum:
                ueberfaellig += 1
                wartezeit = (heute - erstellt_datum).days
                self.stdout.write(
                    f"UEBERFAELLIG: {label} #{antrag.pk} "
                    f"von {antragsteller} "
                    f"(erstellt: {erstellt_datum}, "
                    f"Wartezeit: {wartezeit} Tage, "
                    f"Grenze: {eskalation_nach} Tage)"
                )

                if eskaliere:
                    antrag.status = "eskaliert"
                    antrag.save(update_fields=["status", "aktualisiert_am"])
                    eskaliert += 1
                    logger.info(
                        "Antrag %s #%d auf 'eskaliert' gesetzt.",
                        label,
                        antrag.pk,
                    )

        self.stdout.write(
            f"\nErgebnis: {len(antraege)} Antraege geprueft, "
            f"{ueberfaellig} ueberfaellig."
        )

        if eskaliere:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{eskaliert} Antraege auf 'eskaliert' gesetzt."
                )
            )
        elif ueberfaellig > 0:
            self.stdout.write(
                "Hinweis: Nutze --eskaliere um Antraege auf 'eskaliert' zu setzen."
            )
