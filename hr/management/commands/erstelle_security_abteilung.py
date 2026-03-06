"""Management Command: Erstellt Security-Abteilung mit Tokenverwaltungs-Queue.

Struktur:
- OrgEinheit: Security (SEC) unter Verwaltung (VW)
- Stelle: al_sec (Abteilungsleiter)
- Stelle: sv_sec (Stellvertreter)
- Stellen: ma_sec1 bis ma_sec4 (Sicherheitsmitarbeiter)
- Stelle: pf_sec (Pfoertner)
- TeamQueue: sec-token (Tokenverwaltung / -beantragung)

Alle User erhalten Passwort: testpass123
"""
import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from formulare.models import TeamQueue
from hr.models import HRMitarbeiter, OrgEinheit, Stelle


class Command(BaseCommand):
    help = "Erstellt Security-Abteilung mit 7 Personen und Token-TeamQueue"

    def handle(self, *args, **options):
        with transaction.atomic():
            self.stdout.write("Erstelle Security-Abteilung...")

            # --- OrgEinheit ---
            try:
                verwaltung = OrgEinheit.objects.get(kuerzel="VW")
            except OrgEinheit.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        "OrgEinheit 'VW' (Verwaltung) nicht gefunden. "
                        "Bitte zuerst seed_initial_data ausfuehren."
                    )
                )
                return

            sec_einheit, created = OrgEinheit.objects.get_or_create(
                kuerzel="SEC",
                defaults={
                    "bezeichnung": "Security",
                    "ist_reserviert": True,
                    "uebergeordnet": verwaltung,
                },
            )
            self.stdout.write(
                self.style.SUCCESS(f"  OrgEinheit SEC {'erstellt' if created else 'vorhanden'}")
            )

            # --- Stellen ---
            al_stelle = self._erstelle_stelle(
                kuerzel="al_sec",
                bezeichnung="Abteilungsleiter Security",
                org_einheit=sec_einheit,
                kategorie="leitung",
                uebergeordnete_stelle=None,
            )
            sv_stelle = self._erstelle_stelle(
                kuerzel="sv_sec",
                bezeichnung="Stellvertreter Security",
                org_einheit=sec_einheit,
                kategorie="stab",
                uebergeordnete_stelle=al_stelle,
            )
            # Delegation AL -> Stellvertreter
            if not al_stelle.delegiert_an:
                al_stelle.delegiert_an = sv_stelle
                al_stelle.save(update_fields=["delegiert_an"])
                self.stdout.write("  Delegation al_sec -> sv_sec eingerichtet")

            ma_stellen = []
            for i in range(1, 5):
                ma_stellen.append(
                    self._erstelle_stelle(
                        kuerzel=f"ma_sec{i}",
                        bezeichnung=f"Sicherheitsmitarbeiter/in {i}",
                        org_einheit=sec_einheit,
                        kategorie="fachkraft",
                        uebergeordnete_stelle=al_stelle,
                    )
                )

            pf_stelle = self._erstelle_stelle(
                kuerzel="pf_sec",
                bezeichnung="Pfoertner/in Security",
                org_einheit=sec_einheit,
                kategorie="fachkraft",
                uebergeordnete_stelle=al_stelle,
            )

            # --- Personen anlegen ---
            self.stdout.write("\nErstelle User und HRMitarbeiter...")

            al_hr = self._erstelle_person(
                username="al_sec",
                vorname="Klaus",
                nachname="Weber",
                rolle="abteilungsleiter",
                stelle=al_stelle,
                personalnummer="SEC-AL-001",
            )
            sv_hr = self._erstelle_person(
                username="sv_sec",
                vorname="Markus",
                nachname="Braun",
                rolle="assistent",
                stelle=sv_stelle,
                personalnummer="SEC-SV-001",
                stellvertretung_fuer=al_hr,
            )

            ma_vornamen = ["Thomas", "Sandra", "Peter", "Claudia"]
            ma_nachnamen = ["Fischer", "Mueller", "Hoffmann", "Schneider"]
            ma_hrs = []
            for i, stelle in enumerate(ma_stellen, start=1):
                ma_hrs.append(
                    self._erstelle_person(
                        username=f"ma_sec{i}",
                        vorname=ma_vornamen[i - 1],
                        nachname=ma_nachnamen[i - 1],
                        rolle="mitarbeiter",
                        stelle=stelle,
                        personalnummer=f"SEC-MA-{i:03d}",
                        vorgesetzter=al_hr,
                    )
                )

            pf_hr = self._erstelle_person(
                username="pf_sec",
                vorname="Hans",
                nachname="Gruber",
                rolle="mitarbeiter",
                stelle=pf_stelle,
                personalnummer="SEC-PF-001",
                vorgesetzter=al_hr,
            )

            # Stellvertreter-Vorgesetzter setzen
            if sv_hr.vorgesetzter != al_hr:
                sv_hr.vorgesetzter = al_hr
                sv_hr.save(update_fields=["vorgesetzter"])

            # --- TeamQueue ---
            sec_queue, created = TeamQueue.objects.get_or_create(
                kuerzel="sec-token",
                defaults={
                    "name": "Security – Tokenverwaltung",
                    "beschreibung": "Bearbeitet Token-Antraege und verwaltet Zutrittsbadges.",
                    "antragstypen": [],
                },
            )
            self.stdout.write(
                self.style.SUCCESS(f"  TeamQueue sec-token {'erstellt' if created else 'vorhanden'}")
            )

            # Alle Security-User zur Queue hinzufuegen
            queue_users = [
                al_hr.user, sv_hr.user, pf_hr.user,
            ] + [ma.user for ma in ma_hrs if ma.user]
            for user in queue_users:
                if user:
                    sec_queue.mitglieder.add(user)
            self.stdout.write(
                f"  {len(queue_users)} Mitglieder der Queue hinzugefuegt"
            )

            # OrgEinheit leitende Stelle nachpflegen
            if not sec_einheit.leitende_stelle:
                sec_einheit.leitende_stelle = al_stelle
                sec_einheit.save(update_fields=["leitende_stelle"])

            # --- Raumbelegung ---
            self._belege_raeume(
                al_hr, sv_hr, ma_hrs, pf_hr
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "\nSecurity-Abteilung erfolgreich erstellt!"
                    "\n- Abteilungsleiter: al_sec / Klaus Weber"
                    "\n- Stellvertreter:   sv_sec / Markus Braun"
                    "\n- Mitarbeiter:      ma_sec1 bis ma_sec4"
                    "\n- Pfoertner:        pf_sec / Hans Gruber"
                    "\n- TeamQueue:        sec-token"
                    "\n\nAlle User haben Passwort: testpass123"
                )
            )

    # --- Hilfsmethoden ---

    def _belege_raeume(self, al_hr, sv_hr, ma_hrs, pf_hr):
        """Weist Security-Mitarbeitern Bueros im Raumbuch zu."""
        import datetime
        from raumbuch.models import Belegung, Raum

        heute = datetime.date.today()
        zuteilungen = [
            (al_hr,     "REGA01"),
            (sv_hr,     "REGA02"),
            (pf_hr,     "E02"),
        ]
        for i, ma in enumerate(ma_hrs, start=3):
            raumnummer = f"REG{'A' if i <= 5 else 'B'}{(i - 2) if i <= 5 else (i - 5):02d}"
            zuteilungen.append((ma, raumnummer))

        self.stdout.write("\n  Raumbelegung Security:")
        for ma, raumnummer in zuteilungen:
            try:
                raum = Raum.objects.get(raumnummer=raumnummer)
                _, created = Belegung.objects.get_or_create(
                    raum=raum,
                    mitarbeiter=ma,
                    defaults={"von": heute, "notiz": "Security-Abteilung"},
                )
                self.stdout.write(
                    f"    {ma.user.username} -> {raumnummer} "
                    f"({'erstellt' if created else 'vorhanden'})"
                )
            except Raum.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"    Raum {raumnummer} nicht gefunden – uebersprungen"
                    )
                )

    def _erstelle_stelle(
        self, kuerzel, bezeichnung, org_einheit, kategorie, uebergeordnete_stelle
    ):
        """Erstellt oder gibt vorhandene Stelle zurueck."""
        stelle, created = Stelle.objects.get_or_create(
            kuerzel=kuerzel,
            defaults={
                "bezeichnung": bezeichnung,
                "org_einheit": org_einheit,
                "kategorie": kategorie,
                "uebergeordnete_stelle": uebergeordnete_stelle,
            },
        )
        self.stdout.write(
            f"  Stelle {kuerzel} {'erstellt' if created else 'vorhanden'}"
        )
        return stelle

    def _erstelle_person(
        self,
        username,
        vorname,
        nachname,
        rolle,
        stelle,
        personalnummer,
        vorgesetzter=None,
        stellvertretung_fuer=None,
    ):
        """Erstellt User und HRMitarbeiter, gibt HRMitarbeiter zurueck."""
        from arbeitszeit.models import Mitarbeiter

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": vorname,
                "last_name": nachname,
                "email": f"{username}@firma.de",
            },
        )
        if created:
            user.set_password("testpass123")
            user.save()
            self.stdout.write(f"    User {username} erstellt")

        defaults = {
            "user": user,
            "vorname": vorname,
            "nachname": nachname,
            "stelle": stelle,
            "rolle": rolle,
            "eintrittsdatum": datetime.date(2024, 1, 1),
        }
        if vorgesetzter:
            defaults["vorgesetzter"] = vorgesetzter
        if stellvertretung_fuer:
            defaults["stellvertretung_fuer"] = stellvertretung_fuer

        hr_ma, created = HRMitarbeiter.objects.get_or_create(
            personalnummer=personalnummer,
            defaults=defaults,
        )
        if not created:
            hr_ma.user = user
            hr_ma.stelle = stelle
            hr_ma.rolle = rolle
            hr_ma.save(update_fields=["user", "stelle", "rolle"])
        self.stdout.write(
            f"    HRMitarbeiter {personalnummer} {'erstellt' if created else 'aktualisiert'}"
        )

        # arbeitszeit.Mitarbeiter sicherstellen
        Mitarbeiter.objects.get_or_create(
            user=user,
            defaults={
                "vorname": vorname,
                "nachname": nachname,
                "personalnummer": personalnummer,
                "abteilung": "Security",
            },
        )

        return hr_ma
