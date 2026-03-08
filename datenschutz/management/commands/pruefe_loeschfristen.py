"""
Management Command: pruefe_loeschfristen

Prueft taeglich die gesetzlichen Aufbewahrungsfristen und loescht
personenbezogene Daten nach Ablauf der jeweiligen Frist.

Fristen (nach Datenkategorie):
  - Stammdaten, Zeiterfassung, Reisekosten, Vertraege:  10 Jahre (§ 147 AO)
  - Signatur-Protokolle, Zertifikate:                  10 Jahre (eIDAS Art. 40)
  - Krankheits-/Gesundheitsdaten:                       3 Jahre (§ 195 BGB)
  - Allg. Antraege ohne Steuerrelevanz:                 3 Jahre (§ 195 BGB)
  - Zutrittsprotokolle, Raumbuchungen:                  2 Jahre (DSGVO Art. 5)
  - Bewerbungsunterlagen Abgelehnte:                    6 Monate (AGG § 15)

Aufrufruf (manuell oder via Cron):
  python manage.py pruefe_loeschfristen
  python manage.py pruefe_loeschfristen --trocken     # kein echter Delete
"""
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Loescht personenbezogene Daten nach gesetzlichen Aufbewahrungsfristen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trocken",
            action="store_true",
            help="Trockenlauf: zeigt was geloescht wuerde, loescht aber nichts.",
        )

    def handle(self, *args, **options):
        trocken = options["trocken"]
        heute = timezone.now().date()

        if trocken:
            self.stdout.write(self.style.WARNING("TROCKENLAUF – keine Daten werden geloescht."))

        from arbeitszeit.models import Mitarbeiter

        # Alle ausgeschiedenen Mitarbeiter pruefen
        ausgeschiedene = Mitarbeiter.objects.filter(
            austritt_datum__isnull=False,
            aktiv=False,
        ).select_related("user")

        geloescht_gesamt = 0

        for ma in ausgeschiedene:
            austritt = ma.austritt_datum
            kategorien = {}

            # ----------------------------------------------------------------
            # Kategorie 1: Zutrittsprotokolle + Raumbuchungen (2 Jahre)
            # ----------------------------------------------------------------
            grenze_2j = austritt + relativedelta(years=2)
            if heute >= grenze_2j:
                kategorien.update(
                    self._loesche_raum_daten(ma, trocken)
                )

            # ----------------------------------------------------------------
            # Kategorie 2: Allg. Antraege ohne Steuerrelevanz (3 Jahre)
            # ----------------------------------------------------------------
            grenze_3j = austritt + relativedelta(years=3)
            if heute >= grenze_3j:
                kategorien.update(
                    self._loesche_allg_antraege(ma, trocken)
                )

            # ----------------------------------------------------------------
            # Kategorie 3: Steuerrelevante Daten + Signaturen (10 Jahre)
            # ----------------------------------------------------------------
            grenze_10j = austritt + relativedelta(years=10)
            if heute >= grenze_10j:
                kategorien.update(
                    self._loesche_steuerrelevante_daten(ma, trocken)
                )
                kategorien.update(
                    self._loesche_signatur_daten(ma, trocken)
                )

                # Letzter Schritt: User-Account selbst loeschen
                if not trocken:
                    self._erstelle_loeschprotokoll(ma, kategorien)
                    self._loesche_user(ma)
                    geloescht_gesamt += 1
                else:
                    self.stdout.write(
                        f"  [TROCKEN] Wuerde User {ma.personalnummer} vollstaendig loeschen."
                    )

            elif kategorien:
                if not trocken:
                    self._erstelle_loeschprotokoll(ma, kategorien)
                    geloescht_gesamt += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Loeschfristen-Pruefung abgeschlossen. "
                f"{geloescht_gesamt} Loeschprotokolle erstellt."
            )
        )

    # ------------------------------------------------------------------------
    # Loesch-Methoden pro Kategorie
    # ------------------------------------------------------------------------

    def _loesche_raum_daten(self, ma, trocken):
        """Zutrittsprotokolle + Raumbuchungen (2 Jahre nach Austritt)."""
        kategorien = {}
        try:
            from raumbuch.models import Raumbuchung, ZutrittsProfil
            buchungen = Raumbuchung.objects.filter(gebucht_von=ma.user)
            kategorien["raumbuchungen"] = buchungen.count()
            if not trocken:
                buchungen.delete()

            zp = ZutrittsProfil.objects.filter(mitarbeiter=ma.user)
            kategorien["zutrittsprofil"] = zp.count()
            if not trocken:
                zp.delete()
        except Exception as exc:
            logger.warning("Fehler beim Loeschen der Raumdaten fuer %s: %s", ma.personalnummer, exc)
        return kategorien

    def _loesche_allg_antraege(self, ma, trocken):
        """ZAG-Antraege, Aenderungsantraege, Zeitgutschriften (3 Jahre)."""
        kategorien = {}
        try:
            from formulare.models import ZAGAntrag, ZAGStorno, AenderungZeiterfassung, Zeitgutschrift
            zag = ZAGAntrag.objects.filter(mitarbeiter=ma)
            kategorien["zag_antraege"] = zag.count()
            if not trocken:
                zag.delete()

            storno = ZAGStorno.objects.filter(mitarbeiter=ma)
            kategorien["zag_stornos"] = storno.count()
            if not trocken:
                storno.delete()

            aend = AenderungZeiterfassung.objects.filter(mitarbeiter=ma)
            kategorien["aenderungsantraege"] = aend.count()
            if not trocken:
                aend.delete()

            zg = Zeitgutschrift.objects.filter(mitarbeiter=ma)
            kategorien["zeitgutschriften"] = zg.count()
            if not trocken:
                zg.delete()
        except Exception as exc:
            logger.warning("Fehler beim Loeschen der Antraege fuer %s: %s", ma.personalnummer, exc)
        return kategorien

    def _loesche_steuerrelevante_daten(self, ma, trocken):
        """Zeiterfassung, Arbeitszeitvereinbarungen, Dienstreisen (10 Jahre)."""
        kategorien = {}
        try:
            from arbeitszeit.models import Zeiterfassung, Arbeitszeitvereinbarung
            ze = Zeiterfassung.objects.filter(mitarbeiter=ma)
            kategorien["zeiterfassungen"] = ze.count()
            if not trocken:
                ze.delete()

            av = Arbeitszeitvereinbarung.objects.filter(mitarbeiter=ma)
            kategorien["arbeitszeitvereinbarungen"] = av.count()
            if not trocken:
                av.delete()
        except Exception as exc:
            logger.warning("Fehler beim Loeschen der Zeitdaten fuer %s: %s", ma.personalnummer, exc)

        try:
            from formulare.models import Dienstreiseantrag
            dr = Dienstreiseantrag.objects.filter(mitarbeiter=ma)
            kategorien["dienstreisen"] = dr.count()
            if not trocken:
                dr.delete()
        except Exception as exc:
            logger.warning("Fehler beim Loeschen der Dienstreisen fuer %s: %s", ma.personalnummer, exc)
        return kategorien

    def _loesche_signatur_daten(self, ma, trocken):
        """Signatur-Protokolle + Zertifikate (10 Jahre, eIDAS Art. 40)."""
        kategorien = {}
        try:
            from signatur.models import MitarbeiterZertifikat, SignaturProtokoll, SignaturJob
            zert = MitarbeiterZertifikat.objects.filter(user=ma.user)
            kategorien["signatur_zertifikate"] = zert.count()
            if not trocken:
                zert.delete()

            jobs = SignaturJob.objects.filter(erstellt_von=ma.user)
            kategorien["signatur_jobs"] = jobs.count()
            if not trocken:
                # Protokolle haengen via OneToOne an Job – werden per CASCADE geloescht
                jobs.delete()
        except Exception as exc:
            logger.warning("Fehler beim Loeschen der Signaturdaten fuer %s: %s", ma.personalnummer, exc)
        return kategorien

    # ------------------------------------------------------------------------
    # Protokoll + User-Loeschung
    # ------------------------------------------------------------------------

    def _erstelle_loeschprotokoll(self, ma, kategorien):
        """Erstellt einen dauerhaften Loescheintrag (nur Metadaten)."""
        from datenschutz.models import Loeschprotokoll
        from weasyprint import HTML
        from django.template.loader import render_to_string

        eintrag = Loeschprotokoll(
            user_id_intern=ma.user_id,
            personalnummer=ma.personalnummer,
            nachname_kuerzel=ma.nachname[:3] if ma.nachname else "???",
            eintritt_datum=ma.eintrittsdatum,
            austritt_datum=ma.austritt_datum,
            loeschung_durch="System (pruefe_loeschfristen)",
            kategorien=kategorien,
        )

        # PDF generieren und einbetten
        try:
            html_str = render_to_string("datenschutz/loeschprotokoll_pdf.html", {
                "eintrag": eintrag,
                "kategorien": kategorien,
                "heute": timezone.now().date(),
            })
            pdf_bytes = HTML(string=html_str).write_pdf()
            eintrag.protokoll_pdf = pdf_bytes
        except Exception as exc:
            logger.warning("Loeschprotokoll-PDF konnte nicht erstellt werden: %s", exc)

        eintrag.save()
        logger.info(
            "Loeschprotokoll erstellt fuer %s (Austritt %s), Kategorien: %s",
            ma.personalnummer,
            ma.austritt_datum,
            list(kategorien.keys()),
        )

    def _loesche_user(self, ma):
        """Loescht den Django-User-Account als letzten Schritt."""
        try:
            user = ma.user
            username = user.username
            user.delete()  # CASCADE loescht auch Mitarbeiter
            logger.info("User '%s' vollstaendig geloescht.", username)
        except Exception as exc:
            logger.error("Fehler beim Loeschen des Users fuer %s: %s", ma.personalnummer, exc)
