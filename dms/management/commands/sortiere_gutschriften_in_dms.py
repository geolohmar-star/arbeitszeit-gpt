"""
Management Command: sortiere_gutschriften_in_dms

Archiviert abgeschlossene Betriebssport- und Veranstaltungs-Gutschriften
nachtraeglich in die DMS-Ablagen.

Aufruf:
  python manage.py sortiere_gutschriften_in_dms [--dry-run]
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Archiviert bestehende abgeschlossene Gutschriften in den DMS-Ablagen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen, nicht tatsaechlich archivieren.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN – keine Aenderungen werden gespeichert."))

        from dms.models import DokumentKategorie

        ablage_bs = DokumentKategorie.objects.filter(
            name="Betriebssport-Gutschriften"
        ).first()
        ablage_ve = DokumentKategorie.objects.filter(
            name="Veranstaltungs-Gutschriften"
        ).first()

        if not ablage_bs:
            self.stdout.write(self.style.ERROR(
                "Ablage 'Betriebssport-Gutschriften' nicht gefunden. "
                "Bitte erst 'python manage.py erstelle_zeitgutschrift_ablagen' ausfuehren."
            ))
            return
        if not ablage_ve:
            self.stdout.write(self.style.ERROR(
                "Ablage 'Veranstaltungs-Gutschriften' nicht gefunden."
            ))
            return

        self._archiviere_betriebssport(ablage_bs.pk, dry_run)
        self._archiviere_veranstaltungen(ablage_ve.pk, dry_run)

    def _archiviere_betriebssport(self, kategorie_id, dry_run):
        from betriebssport.models import BetriebssportGutschrift

        qs = BetriebssportGutschrift.objects.filter(
            status__in=["abgeschlossen", "genehmigt"]
        ).select_related("gruppe", "erstellt_von")

        self.stdout.write(f"\nBetriebssport: {qs.count()} abgeschlossene Gutschrift(en)")

        for gutschrift in qs:
            label = f"BS pk={gutschrift.pk} | {gutschrift.gruppe.name} {gutschrift.monat:%m/%Y}"
            if dry_run:
                self.stdout.write(f"  [DRY] {label}")
                continue
            try:
                dok = gutschrift.archiviere_in_dms(kategorie_id)
                if dok:
                    self.stdout.write(
                        self.style.SUCCESS(f"  [OK]  {label} -> DMS pk={dok.pk}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  [SKIP] {label} – keine PDF-Bytes verfuegbar")
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  [ERR] {label}: {exc}")
                )

    def _archiviere_veranstaltungen(self, kategorie_id, dry_run):
        from veranstaltungen.models import FeierteilnahmeGutschrift

        qs = FeierteilnahmeGutschrift.objects.filter(
            status__in=["bearbeitet", "eingereicht"]
        ).select_related("feier", "erstellt_von")

        self.stdout.write(f"\nVeranstaltungen: {qs.count()} Gutschrift(en)")

        for gutschrift in qs:
            label = (
                f"VE pk={gutschrift.pk} | {gutschrift.feier.titel} "
                f"({gutschrift.feier.datum})"
            )
            if dry_run:
                self.stdout.write(f"  [DRY] {label}")
                continue
            try:
                dok = gutschrift.archiviere_in_dms(kategorie_id)
                if dok:
                    self.stdout.write(
                        self.style.SUCCESS(f"  [OK]  {label} -> DMS pk={dok.pk}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  [SKIP] {label} – keine PDF-Bytes verfuegbar")
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  [ERR] {label}: {exc}")
                )
