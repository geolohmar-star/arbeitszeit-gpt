"""
Management Command: erstelle_muster_ausschreibung

Erstellt eine Muster-Stellenausschreibung aus einer unbesetzten Planstelle.
Hilfreich fuer Demo-Zwecke und als Vorlage fuer HR-Mitarbeiter.

Aufruf:
  python manage.py erstelle_muster_ausschreibung
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from stellenportal.models import Ausschreibung


class Command(BaseCommand):
    help = "Erstellt eine Muster-Stellenausschreibung aus einer freien Planstelle."

    def handle(self, *args, **options):
        # Bereits eine Muster-Ausschreibung vorhanden?
        if Ausschreibung.objects.filter(titel__startswith="[MUSTER]").exists():
            self.stdout.write("  [SKIP] Muster-Ausschreibung bereits vorhanden.")
            return

        from hr.models import OrgEinheit, Stelle

        # Erste unbesetzte Fachkraft-Stelle suchen
        stelle = (
            Stelle.objects
            .filter(hrmitarbeiter__isnull=True, kategorie="fachkraft")
            .select_related("org_einheit")
            .first()
        )

        if stelle is None:
            # Fallback: irgendeine unbesetzte Stelle
            stelle = Stelle.objects.filter(hrmitarbeiter__isnull=True).first()

        if stelle is None:
            self.stdout.write(self.style.WARNING(
                "  [WARN] Keine unbesetzte Stelle gefunden – Muster wird ohne Stellenverknuepfung erstellt."
            ))
            orgeinheit = OrgEinheit.objects.first()
        else:
            orgeinheit = stelle.org_einheit
            self.stdout.write(
                f"  [INFO] Verwende Planstelle: {stelle.kuerzel} – {stelle.bezeichnung}"
            )

        # Erstell-User: erster Superuser oder erster aktiver User
        user = (
            User.objects.filter(is_superuser=True, is_active=True).first()
            or User.objects.filter(is_active=True).first()
        )
        if user is None:
            self.stdout.write(self.style.ERROR("  [ERROR] Kein aktiver User gefunden."))
            return

        abteilung_name = orgeinheit.bezeichnung if orgeinheit else "Unser Unternehmen"
        stellen_bezeichnung = stelle.bezeichnung if stelle else "Mitarbeiter/in"

        Ausschreibung.objects.create(
            titel=f"[MUSTER] {stellen_bezeichnung}",
            orgeinheit=orgeinheit,
            stelle=stelle,
            beschaeftigungsart="vollzeit",
            veroeffentlicht=True,
            status="aktiv",
            erstellt_von=user,
            beschreibung=(
                f"Wir suchen zum naechstmoeglichen Zeitpunkt eine/n engagierte/n "
                f"{stellen_bezeichnung} (m/w/d) fuer unseren Bereich {abteilung_name}.\n\n"
                f"Du wirst Teil eines motivierten Teams und traegest aktiv zur "
                f"Weiterentwicklung unserer internen Prozesse bei. "
                f"Die Stelle ist im Stellenplan unter dem Kuerzel "
                f"{'»' + stelle.kuerzel + '«' if stelle else 'TBD'} gefuehrt.\n\n"
                f"Wir legen grossen Wert auf ein kollegiales Miteinander, "
                f"kurze Entscheidungswege und die persoenliche Weiterentwicklung "
                f"jedes Teammitglieds.\n\n"
                f"[Dieser Text ist ein Muster – bitte durch HR anpassen und veroeffentlichen.]"
            ),
            aufgaben=(
                "- Eigenverantwortliche Bearbeitung der anfallenden Aufgaben im Bereich "
                f"{abteilung_name}\n"
                "- Enge Zusammenarbeit mit den Kolleginnen und Kollegen im Team\n"
                "- Mitwirkung bei der Optimierung bestehender Ablaeufe\n"
                "- [Weitere Aufgaben hier ergaenzen]\n"
                "- [Weitere Aufgaben hier ergaenzen]"
            ),
            anforderungen=(
                "- Abgeschlossene Ausbildung oder Studium im relevanten Fachbereich (oder "
                "vergleichbare Qualifikation)\n"
                "- Erste Berufserfahrung von Vorteil, aber keine Voraussetzung\n"
                "- Teamfaehigkeit, Zuverlaessigkeit und selbststaendige Arbeitsweise\n"
                "- Gute Kenntnisse der gaengigen Office-Anwendungen\n"
                "- [Weitere Anforderungen hier ergaenzen]"
            ),
        )

        self.stdout.write(self.style.SUCCESS(
            f"  [OK]   Muster-Ausschreibung '{stellen_bezeichnung}' erstellt und veroeffentlicht."
        ))
