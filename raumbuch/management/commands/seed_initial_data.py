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

        self._laden_immer(
            label="Facility Textbausteine",
            fixtures=["facility/fixtures/textbausteine.json"],
        )

        self._laden(
            label="Raumbuch-Struktur (Gebaeude, Raeume)",
            check_app="raumbuch",
            check_model="Standort",
            fixtures=["raumbuch/fixtures/struktur.json"],
            force=force,
        )

        self._erstelle_abteilung_wenn_noetig(
            label="Security-Abteilung (User + HRMitarbeiter)",
            check_app="hr",
            check_kuerzel="SEC",
            command="erstelle_security_abteilung",
            force=force,
        )

        self._vergebe_durchwahlnummern()

        self.stdout.write("  [LOAD] Raumbelegungen (Stelle -> Raum) ...")
        call_command("seed_belegungen", verbosity=1)
        self.stdout.write("  [OK]   Raumbelegungen abgeschlossen.")

        self.stdout.write(self.style.SUCCESS("seed_initial_data abgeschlossen."))

    def _erstelle_abteilung_wenn_noetig(self, label, check_app, check_kuerzel, command, force):
        """Ruft ein Management-Command auf, wenn die OrgEinheit noch nicht existiert."""
        from django.apps import apps
        model = apps.get_model(check_app, "OrgEinheit")
        if not force and model.objects.filter(kuerzel=check_kuerzel).exists():
            self.stdout.write(f"  [SKIP] {label} – bereits vorhanden.")
            return
        self.stdout.write(f"  [LOAD] {label} ...")
        call_command(command, verbosity=1)
        self.stdout.write(f"  [OK]   {label} abgeschlossen.")

    def _vergebe_durchwahlnummern(self):
        """Vergibt 4-stellige Durchwahlen an alle HRMitarbeiter ohne Durchwahl.

        Laeuft immer – idempotent, da nur leere Felder befuellt werden.
        """
        from django.apps import apps
        from django.db.models import Max

        HRMitarbeiter = apps.get_model("hr", "HRMitarbeiter")
        ohne = HRMitarbeiter.objects.filter(durchwahl="")
        count = ohne.count()
        if count == 0:
            self.stdout.write("  [SKIP] Durchwahlnummern – alle bereits vergeben.")
            return

        self.stdout.write(f"  [LOAD] Durchwahlnummern ({count} fehlend) ...")
        hoechste = HRMitarbeiter.objects.exclude(durchwahl="").aggregate(
            Max("durchwahl")
        )["durchwahl__max"]
        naechste = int(hoechste) + 1 if hoechste and hoechste.isdigit() else 4001
        for ma in ohne.order_by("personalnummer"):
            ma.durchwahl = str(naechste)
            ma.save(update_fields=["durchwahl"])
            naechste += 1
        self.stdout.write(f"  [OK]   Durchwahlnummern – {count} vergeben ab 4001.")

    def _laden_immer(self, label, fixtures):
        """Laedt Fixtures immer – loaddata ist idempotent bei expliziten PKs."""
        self.stdout.write(f"  [LOAD] {label} (immer) ...")
        for fixture in fixtures:
            call_command("loaddata", fixture, verbosity=0)
        self.stdout.write(f"  [OK]   {label} geladen.")

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
