"""
Management-Command: Zeigt den Verschluesselungs-Status aller Mitarbeiter-Schluessel.

Verwendung:
    python manage.py schluessel_status

Ausgabe:
    - Wie viele Schluessel bereits verschluesselt sind
    - Welche User noch Plaintext-Schluessel haben (warten auf Login)
    - Warnung falls noch unverschluesselte Schluessel vorhanden

Die Migration erfolgt automatisch beim naechsten Login des jeweiligen Mitarbeiters.
"""
from django.core.management.base import BaseCommand

from signatur.models import MitarbeiterZertifikat


class Command(BaseCommand):
    help = "Zeigt den PBKDF2-Verschluesselungs-Status aller Mitarbeiter-Schluessel."

    def handle(self, *args, **options):
        alle = MitarbeiterZertifikat.objects.select_related("user").order_by("user__username")

        verschluesselt = []
        plaintext = []

        for zert in alle:
            if zert.key_ist_verschluesselt:
                verschluesselt.append(zert)
            else:
                plaintext.append(zert)

        self.stdout.write(self.style.SUCCESS(
            f"\n=== Signatur-Schluessel Status ==="
        ))
        self.stdout.write(f"Gesamt:        {alle.count()}")
        self.stdout.write(self.style.SUCCESS(
            f"Verschluesselt: {len(verschluesselt)}"
        ))

        if plaintext:
            self.stdout.write(self.style.WARNING(
                f"Plaintext:      {len(plaintext)}  (werden beim naechsten Login migriert)"
            ))
            self.stdout.write(self.style.WARNING("\nNoch nicht migriert:"))
            for zert in plaintext:
                self.stdout.write(
                    f"  - {zert.user.username:20s}  {zert.user.get_full_name()}"
                )
            self.stdout.write(self.style.WARNING(
                "\nHinweis: Migration erfolgt automatisch beim naechsten Login."
                " Solange wird der Plaintext-Schluessel weiterhin verwendet."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nAlle Schluessel sind PBKDF2+AES-256-GCM verschluesselt."
            ))
