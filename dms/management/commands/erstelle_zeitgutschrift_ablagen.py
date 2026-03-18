"""
Management Command: erstelle_zeitgutschrift_ablagen

Legt DokumentKategorie-Eintraege fuer Zeitgutschrift-Workflows an (idempotent).
Strukturiert:
  Zeitgutschriften
    Betriebssport-Gutschriften
    Veranstaltungs-Gutschriften

Aufruf:
  python manage.py erstelle_zeitgutschrift_ablagen
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Legt DMS-Ablagen fuer Zeitgutschrift-Workflows an (idempotent)."

    def handle(self, *args, **options):
        from dms.models import DokumentKategorie

        eltern, erstellt = DokumentKategorie.objects.get_or_create(
            name="Zeitgutschriften",
            elternkategorie=None,
            defaults={
                "beschreibung": "Sammellisten und Nachweise fuer Zeitgutschriften",
                "klasse": "offen",
                "sortierung": 50,
            },
        )
        status = "neu" if erstellt else "vorhanden"
        self.stdout.write(f"  [{status.upper()}] Kategorie '{eltern}' (pk={eltern.pk})")

        for name, beschreibung, sortierung in [
            (
                "Betriebssport-Gutschriften",
                "Monatliche Zeitgutschrift-Sammellisten aus dem Betriebssport",
                1,
            ),
            (
                "Veranstaltungs-Gutschriften",
                "Zeitgutschrift-Sammellisten fuer Betriebsveranstaltungen",
                2,
            ),
        ]:
            kind, erstellt = DokumentKategorie.objects.get_or_create(
                name=name,
                elternkategorie=eltern,
                defaults={
                    "beschreibung": beschreibung,
                    "klasse": "offen",
                    "sortierung": sortierung,
                },
            )
            status = "neu" if erstellt else "vorhanden"
            self.stdout.write(f"  [{status.upper()}] Kategorie '{kind}' (pk={kind.pk})")

        self.stdout.write(self.style.SUCCESS("DMS-Ablagen fuer Zeitgutschriften eingerichtet."))
