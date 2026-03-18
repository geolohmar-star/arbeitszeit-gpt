"""
Management-Command: matrix_einladungen_senden

Laedt alle aktiven Mitarbeiter in die Matrix-Raeume ihrer Org-Einheit ein.
Nützlich fuer den initialen Rollout oder nach einer Neukonfiguration.

Aufruf:
    python manage.py matrix_einladungen_senden
    python manage.py matrix_einladungen_senden --trocken   # nur anzeigen, nicht senden
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Laedt alle aktiven Mitarbeiter in ihre Matrix-Raeume (Org-Einheit) ein."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trocken",
            action="store_true",
            help="Trockenlauffuer Anzeige ohne echte API-Aufrufe.",
        )

    def handle(self, *args, **options):
        from hr.models import HRMitarbeiter
        from matrix_integration.synapse_service import einladen_in_org_einheit_raeume, lade_matrix_user_id
        from matrix_integration.models import MatrixRaum

        trocken = options["trocken"]
        if trocken:
            self.stdout.write("TROCKENLAUF – keine echten Einladungen werden gesendet.\n")

        mitarbeiter_qs = HRMitarbeiter.objects.filter(
            user__isnull=False,
            stelle__isnull=False,
            stelle__org_einheit__isnull=False,
        ).select_related("user", "stelle__org_einheit")

        gesamt = mitarbeiter_qs.count()
        self.stdout.write(f"Verarbeite {gesamt} Mitarbeiter...\n")

        for ma in mitarbeiter_qs:
            matrix_id = lade_matrix_user_id(ma)
            org = ma.stelle.org_einheit.bezeichnung if ma.stelle and ma.stelle.org_einheit else "–"
            raeume = MatrixRaum.objects.filter(
                ist_aktiv=True,
                org_einheit_id=ma.stelle.org_einheit_id,
            ).exclude(room_id="")

            if not raeume.exists():
                self.stdout.write(
                    f"  {ma} ({org}): keine aktiven Matrix-Raeume fuer diese Einheit.\n"
                )
                continue

            for raum in raeume:
                self.stdout.write(
                    f"  {ma} ({org}) -> {raum.name} [{raum.room_id}] "
                    f"als {matrix_id}\n"
                )
                if not trocken:
                    from matrix_integration.synapse_service import einladen_in_raum
                    einladen_in_raum(raum.room_id, matrix_id)

        self._al_fm_in_facility_raeume(trocken)
        self.stdout.write(self.style.SUCCESS("Fertig.\n"))

    def _al_fm_in_facility_raeume(self, trocken):
        """Laedt al_fm explizit in alle Facility-Ping-Raeume ein.

        al_fm (Abteilungsleiter Facility Management) soll alle Stoermeldungen
        mitbekommen, unabhaengig von der org_einheit-basierten Einladungslogik.
        """
        from hr.models import Stelle
        from matrix_integration.models import MatrixRaum
        from matrix_integration.synapse_service import einladen_in_raum, lade_matrix_user_id

        self.stdout.write("\n--- al_fm in Facility-Ping-Raeume einladen ---")

        # al_fm-Stelle und Inhaber ermitteln
        try:
            stelle = Stelle.objects.get(kuerzel="al_fm")
        except Stelle.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                "  Stelle 'al_fm' nicht gefunden – uebersprungen."
            ))
            return

        try:
            ma = stelle.hrmitarbeiter
        except Exception:
            self.stdout.write(self.style.WARNING(
                "  Stelle 'al_fm' ist nicht besetzt – uebersprungen."
            ))
            return

        matrix_id = lade_matrix_user_id(ma)
        if not matrix_id:
            self.stdout.write(self.style.WARNING(
                f"  {ma.vollname}: keine Matrix-ID ermittelbar – uebersprungen."
            ))
            return

        # Alle Facility-Ping-Raeume (allgemein + FM-Teams)
        facility_ping_typen = {"facility", "fm_elektro", "fm_maler", "fm_sanitaer", "fm_schlosser", "fm_schreiner"}
        raeume = MatrixRaum.objects.filter(
            ping_typ__in=facility_ping_typen,
            ist_aktiv=True,
        ).exclude(room_id="")

        if not raeume.exists():
            self.stdout.write("  Keine aktiven Facility-Ping-Raeume gefunden.")
            return

        for raum in raeume:
            self.stdout.write(
                f"  {ma.vollname} ({matrix_id}) -> {raum.name} [{raum.ping_typ}]"
            )
            if not trocken:
                einladen_in_raum(raum.room_id, matrix_id)
