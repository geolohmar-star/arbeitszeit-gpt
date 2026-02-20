"""Management Command: Erstellt komplette Org-Struktur mit sprechenden Kuerzeln.

Neue Namenskonvention: <rolle>_<bereich><nummer>
- Rolle: gf, bl, al, tl, sv, ma
- Bereich: 2-3 Buchstaben-Kuerzel (se, pr, da, pe, mk, fm, etc.)
- Nummer: laufende Nummer innerhalb des Bereichs

Beispiel: ma_se1 = Mitarbeiter Softwareentwicklung Nr. 1
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from hr.models import HRMitarbeiter, OrgEinheit, Stelle
from arbeitszeit.models import Mitarbeiter


class Command(BaseCommand):
    help = "Erstellt komplette Org-Struktur mit sprechenden Kuerzeln"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loeschen",
            action="store_true",
            help="Loescht bestehende Struktur vor dem Erstellen",
        )

    def handle(self, *args, **options):
        if options["loeschen"]:
            self._loesche_alte_struktur()

        with transaction.atomic():
            self.stdout.write(self.style.WARNING("\nErstelle Org-Struktur mit sprechenden Kuerzeln...\n"))

            # Haupteinheiten sicherstellen
            gf = self._sicherstelle_orgeinheit("GF", "Geschaeftsfuehrung")
            it = self._sicherstelle_orgeinheit("IT", "Informationstechnik")
            bv = self._sicherstelle_orgeinheit("BV", "Betrieb und Verwaltung")
            hr = self._sicherstelle_orgeinheit("HR", "Human Resources", uebergeordnet=bv)

            # ZUERST Geschaeftsfuehrung erstellen (oberste Ebene)
            gf_tech, gf_verw = self._erstelle_gf_struktur(gf)

            # DANN Bereiche mit GF als Vorgesetzte
            self._erstelle_it_struktur(it, gf_tech)
            self._erstelle_bv_struktur(bv, gf_verw)
            self._erstelle_hr_struktur(hr, bv)

            self.stdout.write(self.style.SUCCESS("\n=== Struktur erfolgreich erstellt! ==="))
            self.stdout.write("Alle User haben Passwort: testpass123\n")

    def _loesche_alte_struktur(self):
        """Loescht alte Stellen, HRMitarbeiter und HR-User.

        WICHTIG: User mit arbeitszeit.Mitarbeiter bleiben erhalten!
        """
        self.stdout.write(self.style.WARNING("Loesche alte HR-Struktur..."))

        # Finde User die KEINE arbeitszeit.Mitarbeiter haben
        # Diese koennen geloescht werden (sind reine HR-User)
        user_mit_az_ma = Mitarbeiter.objects.values_list('user_id', flat=True)
        hr_user = User.objects.filter(is_superuser=False).exclude(id__in=user_mit_az_ma)
        geloeschte_user = hr_user.count()
        hr_user.delete()
        self.stdout.write(f"  {geloeschte_user} HR-User geloescht (arbeitszeit.Mitarbeiter-User bleiben)")

        # Alle Stellen loeschen
        geloeschte_stellen = Stelle.objects.all().delete()[0]
        self.stdout.write(f"  {geloeschte_stellen} Stellen geloescht\n")

    def _sicherstelle_orgeinheit(self, kuerzel, bezeichnung, uebergeordnet=None):
        """Erstellt oder holt OrgEinheit."""
        einheit, created = OrgEinheit.objects.get_or_create(
            kuerzel=kuerzel,
            defaults={
                "bezeichnung": bezeichnung,
                "uebergeordnet": uebergeordnet,
            },
        )
        if created:
            self.stdout.write(f"  OrgEinheit {kuerzel} erstellt")
        return einheit

    def _erstelle_gf_struktur(self, gf):
        """Erstellt Geschaeftsfuehrung (oberste Ebene).

        Returns: (gf_tech, gf_verw) Stellen
        """
        self.stdout.write(self.style.SUCCESS("\n--- Geschaeftsfuehrung (oberste Ebene) ---"))

        gf_tech = self._erstelle_stelle_und_person(
            "gf_tech", "Geschaeftsfuehrung Technik", gf, None,
            "Thomas", "Schmidt", "GF-TECH-001"
        )
        gf_verw = self._erstelle_stelle_und_person(
            "gf_verw", "Geschaeftsfuehrung Verwaltung", gf, None,
            "Maria", "Mueller", "GF-VERW-001"
        )

        return gf_tech, gf_verw

    def _erstelle_it_struktur(self, it, gf_tech):
        """Erstellt IT & Entwicklung Struktur."""
        self.stdout.write(self.style.SUCCESS("\n--- IT & Entwicklung ---"))

        # Bereichsleiter (unter GF Technik)
        bl_it = self._erstelle_stelle_und_person(
            "bl_it", "Bereichsleiter IT & Entwicklung", it, gf_tech,
            "Stefan", "Weber", "IT-BL-001"
        )

        # Softwareentwicklung (SE)
        self.stdout.write("\nSoftwareentwicklung (SE):")
        se = self._sicherstelle_orgeinheit("SE", "Softwareentwicklung", it)
        al_se = self._erstelle_stelle_und_person(
            "al_se", "Abteilungsleiter Softwareentwicklung", se, bl_it,
            "Michael", "Fischer", "SE-AL-001"
        )
        sv_se = self._erstelle_stelle_und_person(
            "sv_se", "Stellvertreter Softwareentwicklung", se, al_se,
            "Julia", "Wagner", "SE-SV-001"
        )
        # Delegation
        al_se.delegiert_an = sv_se
        al_se.save()

        # 10 Mitarbeiter SE
        for i in range(1, 11):
            self._erstelle_stelle_und_person(
                f"ma_se{i}", f"Mitarbeiter Softwareentwicklung {i}", se, al_se,
                f"MA_SE_{i}", f"Nachname_SE_{i}", f"SE-MA-{i:03d}"
            )

        # Produktentwicklung (PR)
        self.stdout.write("\nProduktentwicklung (PR):")
        pr = self._sicherstelle_orgeinheit("PR", "Produktentwicklung", it)
        al_pr = self._erstelle_stelle_und_person(
            "al_pr", "Abteilungsleiter Produktentwicklung", pr, bl_it,
            "Andreas", "Becker", "PR-AL-001"
        )
        sv_pr = self._erstelle_stelle_und_person(
            "sv_pr", "Stellvertreter Produktentwicklung", pr, al_pr,
            "Sandra", "Koch", "PR-SV-001"
        )
        al_pr.delegiert_an = sv_pr
        al_pr.save()

        for i in range(1, 8):
            self._erstelle_stelle_und_person(
                f"ma_pr{i}", f"Mitarbeiter Produktentwicklung {i}", pr, al_pr,
                f"MA_PR_{i}", f"Nachname_PR_{i}", f"PR-MA-{i:03d}"
            )

        # Daten & Analyse (DA)
        self.stdout.write("\nDaten & Analyse (DA):")
        da = self._sicherstelle_orgeinheit("DA", "Daten & Analyse", it)
        al_da = self._erstelle_stelle_und_person(
            "al_da", "Abteilungsleiter Daten & Analyse", da, bl_it,
            "Petra", "Hoffmann", "DA-AL-001"
        )
        sv_da = self._erstelle_stelle_und_person(
            "sv_da", "Stellvertreter Daten & Analyse", da, al_da,
            "Martin", "Schulz", "DA-SV-001"
        )
        al_da.delegiert_an = sv_da
        al_da.save()

        for i in range(1, 6):
            self._erstelle_stelle_und_person(
                f"ma_da{i}", f"Mitarbeiter Daten & Analyse {i}", da, al_da,
                f"MA_DA_{i}", f"Nachname_DA_{i}", f"DA-MA-{i:03d}"
            )

        # IT-Infrastruktur (II)
        self.stdout.write("\nIT-Infrastruktur (II):")
        ii = self._sicherstelle_orgeinheit("II", "IT-Infrastruktur", it)
        al_ii = self._erstelle_stelle_und_person(
            "al_ii", "Abteilungsleiter IT-Infrastruktur", ii, bl_it,
            "Frank", "Richter", "II-AL-001"
        )
        sv_ii = self._erstelle_stelle_und_person(
            "sv_ii", "Stellvertreter IT-Infrastruktur", ii, al_ii,
            "Sabine", "Klein", "II-SV-001"
        )
        al_ii.delegiert_an = sv_ii
        al_ii.save()

        for i in range(1, 8):
            self._erstelle_stelle_und_person(
                f"ma_ii{i}", f"Mitarbeiter IT-Infrastruktur {i}", ii, al_ii,
                f"MA_II_{i}", f"Nachname_II_{i}", f"II-MA-{i:03d}"
            )

    def _erstelle_bv_struktur(self, bv, gf_verw):
        """Erstellt Betrieb & Verwaltung Struktur."""
        self.stdout.write(self.style.SUCCESS("\n--- Betrieb & Verwaltung ---"))

        # Bereichsleiter (alle unter GF Verwaltung)
        bl_bv1 = self._erstelle_stelle_und_person(
            "bl_bv1", "Bereichsleiter Betrieb & Verwaltung", bv, gf_verw,
            "Klaus", "Meier", "BV-BL-001"
        )
        bl_bv2 = self._erstelle_stelle_und_person(
            "bl_bv2", "Bereichsleiter Finanzen & Controlling", bv, gf_verw,
            "Ursula", "Schmidt", "BV-BL-002"
        )
        bl_bv3 = self._erstelle_stelle_und_person(
            "bl_bv3", "Bereichsleiter Personal & Organisation", bv, gf_verw,
            "Hans", "Bauer", "BV-BL-003"
        )
        bl_bv4 = self._erstelle_stelle_und_person(
            "bl_bv4", "Bereichsleiter Vertrieb & Marketing", bv, gf_verw,
            "Monika", "Wolf", "BV-BL-004"
        )

        # Facility Management (FM) - unter bl_bv1
        self.stdout.write("\nFacility Management (FM):")
        fm = self._sicherstelle_orgeinheit("FM", "Facility Management", bv)
        self._erstelle_abteilung_mit_team(fm, "fm", "Facility Management", bl_bv1, 4)

        # Einkauf & Logistik (EL) - unter bl_bv1
        self.stdout.write("\nEinkauf & Logistik (EL):")
        el = self._sicherstelle_orgeinheit("EL", "Einkauf & Logistik", bv)
        self._erstelle_abteilung_mit_team(el, "el", "Einkauf & Logistik", bl_bv1, 6)

        # Qualitaetssicherung (QS) - unter bl_bv1
        self.stdout.write("\nQualitaetssicherung (QS):")
        qs = self._sicherstelle_orgeinheit("QS", "Qualitaetssicherung", bv)
        self._erstelle_abteilung_mit_team(qs, "qs", "Qualitaetssicherung", bl_bv1, 4)

        # Controlling (CO) - unter bl_bv2
        self.stdout.write("\nControlling (CO):")
        co = self._sicherstelle_orgeinheit("CO", "Controlling", bv)
        self._erstelle_abteilung_mit_team(co, "co", "Controlling", bl_bv2, 3)

        # Buchhaltung (BH) - unter bl_bv2
        self.stdout.write("\nBuchhaltung (BH):")
        bh = self._sicherstelle_orgeinheit("BH", "Buchhaltung", bv)
        self._erstelle_abteilung_mit_team(bh, "bh", "Buchhaltung", bl_bv2, 3)

        # Lohn & Gehalt (LG) - unter bl_bv2
        self.stdout.write("\nLohn & Gehalt (LG):")
        lg = self._sicherstelle_orgeinheit("LG", "Lohn & Gehalt", bv)
        self._erstelle_abteilung_mit_team(lg, "lg", "Lohn & Gehalt", bl_bv2, 3)

        # Personalentwicklung (PE) - unter bl_bv3
        self.stdout.write("\nPersonalentwicklung (PE):")
        pe = self._sicherstelle_orgeinheit("PE", "Personalentwicklung", bv)
        self._erstelle_abteilung_mit_team(pe, "pe", "Personalentwicklung", bl_bv3, 3)

        # Personalgewinnung (PG) - unter bl_bv3
        self.stdout.write("\nPersonalgewinnung (PG):")
        pg = self._sicherstelle_orgeinheit("PG", "Personalgewinnung", bv)
        self._erstelle_abteilung_mit_team(pg, "pg", "Personalgewinnung", bl_bv3, 2)

        # Personalverwaltung (PV) - unter bl_bv3
        self.stdout.write("\nPersonalverwaltung (PV):")
        pv = self._sicherstelle_orgeinheit("PV", "Personalverwaltung", bv)
        self._erstelle_abteilung_mit_team(pv, "pv", "Personalverwaltung", bl_bv3, 3)

        # Marketing (MK) - unter bl_bv4
        self.stdout.write("\nMarketing (MK):")
        mk = self._sicherstelle_orgeinheit("MK", "Marketing", bv)
        self._erstelle_abteilung_mit_team(mk, "mk", "Marketing", bl_bv4, 4)

        # Innendienst (ID) - unter bl_bv4
        self.stdout.write("\nInnendienst (ID):")
        id_org = self._sicherstelle_orgeinheit("ID", "Innendienst", bv)
        self._erstelle_abteilung_mit_team(id_org, "id", "Innendienst", bl_bv4, 6)

        # Aussendienst (AD) - unter bl_bv4
        self.stdout.write("\nAussendienst (AD):")
        ad = self._sicherstelle_orgeinheit("AD", "Aussendienst", bv)
        self._erstelle_abteilung_mit_team(ad, "ad", "Aussendienst", bl_bv4, 6)

    def _erstelle_hr_struktur(self, hr, bv):
        """Erstellt HR-Struktur."""
        self.stdout.write(self.style.SUCCESS("\n--- Human Resources ---"))

        # HR gehoert unter bl_bv3 (Personal & Organisation)
        bl_bv3 = Stelle.objects.get(kuerzel="bl_bv3")

        # Zeit/Abrechnung (ZA)
        self.stdout.write("\nZeit/Abrechnung (ZA):")
        za = self._sicherstelle_orgeinheit("ZA", "Zeit & Abrechnung", hr)

        tl_za = self._erstelle_stelle_und_person(
            "tl_za", "Teamleiter Zeit & Abrechnung", za, bl_bv3,
            "Max", "Mustermann", "ZA-TL-001"
        )
        sv_za = self._erstelle_stelle_und_person(
            "sv_za", "Stellvertreter Zeit & Abrechnung", za, tl_za,
            "Anna", "Schmidt", "ZA-SV-001"
        )
        tl_za.delegiert_an = sv_za
        tl_za.save()

        # 10 Mitarbeiter
        vornamen = ["Lisa", "Tom", "Julia", "Markus", "Sarah", "Tim", "Laura", "Felix", "Nina", "Leon"]
        nachnamen = ["Mueller", "Weber", "Wagner", "Becker", "Schulz", "Hoffmann", "Koch", "Bauer", "Richter", "Klein"]

        for i in range(1, 11):
            self._erstelle_stelle_und_person(
                f"ma_za{i}", f"Mitarbeiter Zeit & Abrechnung {i}", za, tl_za,
                vornamen[i-1], nachnamen[i-1], f"ZA-MA-{i:03d}"
            )

    def _erstelle_abteilung_mit_team(self, org_einheit, kuerzel, bezeichnung, vorgesetzter, anzahl_ma):
        """Hilfsfunktion: Erstellt Abteilungsleiter, Stellvertreter und Mitarbeiter."""
        al = self._erstelle_stelle_und_person(
            f"al_{kuerzel}", f"Abteilungsleiter {bezeichnung}", org_einheit, vorgesetzter,
            f"AL_{kuerzel.upper()}", f"Nachname_AL", f"{kuerzel.upper()}-AL-001"
        )
        sv = self._erstelle_stelle_und_person(
            f"sv_{kuerzel}", f"Stellvertreter {bezeichnung}", org_einheit, al,
            f"SV_{kuerzel.upper()}", f"Nachname_SV", f"{kuerzel.upper()}-SV-001"
        )
        al.delegiert_an = sv
        al.save()

        for i in range(1, anzahl_ma + 1):
            self._erstelle_stelle_und_person(
                f"ma_{kuerzel}{i}", f"Mitarbeiter {bezeichnung} {i}", org_einheit, al,
                f"MA_{kuerzel.upper()}_{i}", f"Nachname_MA", f"{kuerzel.upper()}-MA-{i:03d}"
            )

    def _erstelle_stelle_und_person(self, kuerzel, bezeichnung, org_einheit,
                                     uebergeordnete_stelle, vorname, nachname, personalnummer):
        """Erstellt Stelle, User und HRMitarbeiter.

        WICHTIG: Erstellt KEINE arbeitszeit.Mitarbeiter - diese bleiben
        unabhaengig fuer Schichtplanung/Zeiterfassung bestehen!
        """
        # Stelle
        stelle, created = Stelle.objects.get_or_create(
            kuerzel=kuerzel,
            defaults={
                "bezeichnung": bezeichnung,
                "org_einheit": org_einheit,
                "uebergeordnete_stelle": uebergeordnete_stelle,
            },
        )
        if created:
            self.stdout.write(f"  {kuerzel}")

        # User
        user, created = User.objects.get_or_create(
            username=kuerzel,
            defaults={
                "first_name": vorname,
                "last_name": nachname,
                "email": f"{kuerzel}@firma.de",
            },
        )
        if created:
            user.set_password("testpass123")
            user.save()

        # HRMitarbeiter
        hr_ma, created = HRMitarbeiter.objects.get_or_create(
            personalnummer=personalnummer,
            defaults={
                "user": user,
                "vorname": vorname,
                "nachname": nachname,
                "stelle": stelle,
                "email": stelle.email,
                "eintrittsdatum": timezone.now().date(),
            },
        )

        # arbeitszeit.Mitarbeiter werden NICHT erstellt - die sind unabhaengig!
        # Sie bleiben fuer Schichtplanung/Zeiterfassung erhalten

        return stelle
