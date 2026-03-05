"""
Management Command: seed_initial_data

Laedt Seed-Daten (Raumbuch-Struktur, HR-Orgstruktur, Workflow-Templates,
TeamQueues) in die Datenbank – aber NUR wenn die jeweiligen Tabellen noch leer
sind.  Dadurch ist der Command idempotent und kann bei jedem Railway-Deploy
ausgefuehrt werden, ohne Duplikate zu erzeugen.

Reihenfolge (FK-Abhaengigkeiten):
  1. hr.OrgEinheit + hr.Stelle       (Orgstruktur, kein User-FK)
  2. formulare.TeamQueue             (Queues ohne Mitglieder-M2M)
  3. workflow.*                       (Templates, Steps, Transitions)
  4. facility.FacilityTeam           (5 Kategorien, ohne User-M2M)
  5. raumbuch.*                       (Gebaeudestruktur + Raeume)

Aufruf:
  python manage.py seed_initial_data
  python manage.py seed_initial_data --force   # erzwingt Laden auch wenn Daten existieren
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Laedt Seed-Fixtures falls die Tabellen noch leer sind."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Fixtures laden auch wenn bereits Daten vorhanden sind.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        self._laden(
            label="HR Orgstruktur (Stelle, OrgEinheit)",
            check_app="hr",
            check_model="Stelle",
            fixtures=["hr/fixtures/orgstruktur.json"],
            force=force,
        )

        self._laden(
            label="Team-Queues",
            check_app="formulare",
            check_model="TeamQueue",
            fixtures=["formulare/fixtures/teamqueue.json"],
            force=force,
        )

        self._laden(
            label="Workflow-Templates",
            check_app="workflow",
            check_model="WorkflowTemplate",
            fixtures=["workflow/fixtures/templates.json"],
            force=force,
        )

        self._laden(
            label="Facility-Teams (5 Kategorien)",
            check_app="facility",
            check_model="FacilityTeam",
            fixtures=["facility/fixtures/facilityteams.json"],
            force=force,
        )

        self._laden(
            label="Raumbuch-Struktur (Gebaeude, Raeume)",
            check_app="raumbuch",
            check_model="Standort",
            fixtures=["raumbuch/fixtures/struktur.json"],
            force=force,
        )

        self.stdout.write(self.style.SUCCESS("seed_initial_data abgeschlossen."))

    def _laden(self, label, check_app, check_model, fixtures, force):
        """Laedt Fixtures nur wenn Tabelle leer ist (oder --force gesetzt)."""
        from django.apps import apps

        model = apps.get_model(check_app, check_model)
        if not force and model.objects.exists():
            self.stdout.write(f"  [SKIP] {label} – bereits vorhanden.")
            return

        self.stdout.write(f"  [LOAD] {label} ...")
        for fixture in fixtures:
            call_command("loaddata", fixture, verbosity=0)
        self.stdout.write(f"  [OK]   {label} geladen.")
