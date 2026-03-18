"""
Management-Command: Legt die Django-Gruppe 'it_helpdesk' an und weist ihr
alle Berechtigungen fuer die it_status-App zu.

Ausserdem werden alle HRMitarbeiter der IT-Helpdesk-OrgEinheit automatisch
der Gruppe zugewiesen.

Ausfuehren:
    python manage.py erstelle_it_helpdesk_gruppe
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from it_status.models import ITStatusMeldung, ITSystem, ITWartung


class Command(BaseCommand):
    help = "Erstellt die Gruppe 'it_helpdesk' mit IT-Status-Berechtigungen und weist Helpdesk-Mitarbeiter zu."

    def handle(self, *args, **options):
        # Gruppe anlegen oder holen
        gruppe, erstellt = Group.objects.get_or_create(name="it_helpdesk")
        if erstellt:
            self.stdout.write("Gruppe 'it_helpdesk' erstellt.")
        else:
            self.stdout.write("Gruppe 'it_helpdesk' bereits vorhanden.")

        # Alle Berechtigungen fuer it_status-Models zuweisen
        berechtigungen = []
        for model in [ITSystem, ITStatusMeldung, ITWartung]:
            ct = ContentType.objects.get_for_model(model)
            for perm in Permission.objects.filter(content_type=ct):
                berechtigungen.append(perm)

        gruppe.permissions.set(berechtigungen)
        self.stdout.write(f"  {len(berechtigungen)} Berechtigungen zugewiesen.")

        # Alle HRMitarbeiter der IT-Helpdesk-OrgEinheit zuweisen
        try:
            from hr.models import HRMitarbeiter, OrgEinheit
            it_abt = OrgEinheit.objects.filter(
                bezeichnung__icontains="helpdesk"
            ).first()
            if not it_abt:
                it_abt = OrgEinheit.objects.filter(
                    kuerzel__icontains="it"
                ).first()

            if it_abt:
                mitarbeiter = HRMitarbeiter.objects.filter(
                    stelle__org_einheit=it_abt,
                    user__isnull=False,
                ).select_related("user")
                for ma in mitarbeiter:
                    ma.user.groups.add(gruppe)
                    self.stdout.write(f"  Mitarbeiter hinzugefuegt: {ma.user.username}")
                if not mitarbeiter:
                    self.stdout.write("  Keine Mitarbeiter in der IT-Abteilung gefunden.")
            else:
                self.stdout.write("  Keine IT-OrgEinheit gefunden – Mitarbeiter bitte manuell zuweisen.")
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Mitarbeiter-Zuweisung fehlgeschlagen: {exc}"))

        self.stdout.write(self.style.SUCCESS("Fertig."))
