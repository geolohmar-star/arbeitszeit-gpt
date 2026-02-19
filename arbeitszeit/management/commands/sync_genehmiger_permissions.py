"""
Management Command: Synchronisiert genehmigen_antraege-Permissions
anhand des vorgesetzter-Feldes in arbeitszeit.Mitarbeiter.

- Mitarbeiter hat Vorgesetzten mit User -> Permission vergeben
- Mitarbeiter hat keinen Vorgesetzten -> Permission aller bisherigen
  Genehmiger entziehen

Aufruf:
    python manage.py sync_genehmiger_permissions
    python manage.py sync_genehmiger_permissions --dry-run
"""
from django.core.management.base import BaseCommand
from guardian.shortcuts import assign_perm, remove_perm, get_users_with_perms

from arbeitszeit.models import Mitarbeiter


class Command(BaseCommand):
    help = "Synchronisiert genehmigen_antraege-Permissions nach vorgesetzter-Feld"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt Aenderungen an ohne sie durchzufuehren",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        vergeben = 0
        entzogen = 0

        for ma in Mitarbeiter.objects.select_related(
            "vorgesetzter", "vorgesetzter__user"
        ).all():
            # Aktuell berechtigte User fuer diesen Mitarbeiter
            berechtigte = get_users_with_perms(
                ma,
                attach_perms=True,
                with_group_users=False,
            )
            # Nur jene mit genehmigen_antraege
            aktuelle_genehmiger = {
                user
                for user, perms in berechtigte.items()
                if "genehmigen_antraege" in perms
            }

            vg = ma.vorgesetzter
            vg_user = vg.user if vg and vg.user_id else None

            # Permission an aktuellen Vorgesetzten vergeben
            if vg_user and vg_user not in aktuelle_genehmiger:
                if not dry:
                    assign_perm("genehmigen_antraege", vg_user, ma)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Vergeben: {vg_user.username} -> {ma}"
                    )
                )
                vergeben += 1

            # Veraltete Permissions entziehen (User ist kein Vorgesetzter mehr)
            for user in aktuelle_genehmiger:
                if user != vg_user:
                    if not dry:
                        remove_perm("genehmigen_antraege", user, ma)
                    self.stdout.write(
                        f"  Entzogen: {user.username} -> {ma}"
                    )
                    entzogen += 1

        prefix = "[DRY-RUN] " if dry else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Fertig: {vergeben} vergeben, {entzogen} entzogen."
            )
        )
