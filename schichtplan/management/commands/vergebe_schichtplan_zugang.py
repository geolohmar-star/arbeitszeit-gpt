"""
Management Command: Vergibt die schichtplan_zugang-Permission.

Nur Mitarbeiter (arbeitszeit.Mitarbeiter) mit gesetzter schichtplan_kennung
erhalten Zugang zur Schichtplanung. Staff und Superuser bekommen die Permission
ebenfalls, allerdings greifen diese sowieso immer via hat_schichtplan_zugang().

Aufruf:
    python manage.py vergebe_schichtplan_zugang
    python manage.py vergebe_schichtplan_zugang --entziehen anna.schmidt
    python manage.py vergebe_schichtplan_zugang --vergeben ma1_username
"""
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from arbeitszeit.models import Mitarbeiter
from schichtplan.models import Schichtplan


class Command(BaseCommand):
    help = (
        "Vergibt schichtplan_zugang an Mitarbeiter mit Schichtplan-Kennung, "
        "entzieht sie allen anderen."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--entziehen",
            nargs="+",
            metavar="USERNAME",
            default=[],
            help="Diesen Usern die Permission manuell entziehen",
        )
        parser.add_argument(
            "--vergeben",
            nargs="+",
            metavar="USERNAME",
            default=[],
            help="Diesen Usern die Permission manuell vergeben",
        )

    def handle(self, *args, **options):
        # Permission-Objekt laden
        ct = ContentType.objects.get_for_model(Schichtplan)
        try:
            perm = Permission.objects.get(
                codename="schichtplan_zugang",
                content_type=ct,
            )
        except Permission.DoesNotExist:
            self.stderr.write(
                "Permission 'schichtplan_zugang' nicht gefunden. "
                "Bitte zuerst Migration ausfuehren: python manage.py migrate"
            )
            return

        # -- Manuelle Einzelaktion: entziehen --
        if options["entziehen"]:
            for username in options["entziehen"]:
                try:
                    user = User.objects.get(username=username)
                    user.user_permissions.remove(perm)
                    self.stdout.write(f"  Entzogen: {username}")
                except User.DoesNotExist:
                    self.stderr.write(f"  User nicht gefunden: {username}")
            return

        # -- Manuelle Einzelaktion: vergeben --
        if options["vergeben"]:
            for username in options["vergeben"]:
                try:
                    user = User.objects.get(username=username)
                    user.user_permissions.add(perm)
                    self.stdout.write(f"  Vergeben: {username}")
                except User.DoesNotExist:
                    self.stderr.write(f"  User nicht gefunden: {username}")
            return

        # -- Automatisch: Permission nach schichtplan_kennung verteilen --
        # User-IDs mit gueltiger Schichtplan-Kennung ermitteln (z.B. MA1, MA2, ...)
        # Leere Strings, "keine" und sonstige Platzhalter werden ausgeschlossen
        berechtigte_user_ids = set(
            Mitarbeiter.objects.filter(
                schichtplan_kennung__iregex=r"^MA\d+$",
                user__isnull=False,
            ).values_list("user_id", flat=True)
        )

        vergeben = 0
        entzogen = 0

        for user in User.objects.filter(is_active=True).prefetch_related(
            "user_permissions"
        ):
            # Nur echte Superuser bekommen automatisch Zugang (nicht is_staff allein)
            if user.is_superuser:
                user.user_permissions.add(perm)
                vergeben += 1
            elif user.id in berechtigte_user_ids:
                user.user_permissions.add(perm)
                vergeben += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  Vergeben: {user.username}")
                )
            else:
                user.user_permissions.remove(perm)
                entzogen += 1
                self.stdout.write(f"  Entzogen:  {user.username}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFertig: {vergeben} User erhalten Zugang, "
                f"{entzogen} User ohne Zugang."
            )
        )
