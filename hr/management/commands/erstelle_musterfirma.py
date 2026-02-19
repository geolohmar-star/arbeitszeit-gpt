"""
Management Command: Erstellt 100 Mustermitarbeiter fuer Apex Solutions GmbH.
Inklusive Hierarchie, Stellvertreter und guardian-Permissions.

Aufruf: python manage.py erstelle_musterfirma
        python manage.py erstelle_musterfirma --loeschen  (vorher alles loeschen)
"""
import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from guardian.shortcuts import assign_perm

from hr.models import Bereich, Abteilung, Team, HRMitarbeiter


# Realistiscehe deutsche Namen
VORNAMEN_M = [
    "Thomas", "Andreas", "Stefan", "Michael", "Christian", "Martin",
    "Frank", "Peter", "Klaus", "Markus", "Juergen", "Ralf", "Dirk",
    "Tobias", "Sebastian", "Daniel", "Florian", "Matthias", "Oliver",
    "Alexander", "Jan", "Carsten", "Sven", "Jochen", "Bernd",
]
VORNAMEN_W = [
    "Sandra", "Sabine", "Andrea", "Petra", "Monika", "Nicole", "Anja",
    "Claudia", "Stefanie", "Susanne", "Julia", "Laura", "Sarah", "Anna",
    "Lisa", "Katharina", "Christina", "Melanie", "Jennifer", "Karin",
    "Birgit", "Heike", "Ursula", "Brigitte", "Marianne",
]
NACHNAMEN = [
    "Mueller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer",
    "Wagner", "Becker", "Schulz", "Hoffmann", "Schaefer", "Koch",
    "Bauer", "Richter", "Klein", "Wolf", "Schroeder", "Neumann",
    "Schwarz", "Zimmermann", "Braun", "Krueger", "Hartmann", "Lange",
    "Werner", "Schmitt", "Krause", "Meier", "Lehmann", "Keller",
    "Huber", "Frank", "Roth", "Gross", "Kaiser", "Fuchs", "Vogel",
    "Schubert", "Jung", "Winkler", "Berg", "Kraus", "Heinrich",
]

# Organisationsstruktur
STRUKTUR = {
    "Betrieb & Verwaltung": {
        "kuerzel": "BV",
        "abteilungen": {
            "Einkauf & Logistik": {
                "kuerzel": "EL",
                "teams": ["Einkaufsteam", "Versandteam"],
                "groesse": 7,
            },
            "Facility Management": {
                "kuerzel": "FM",
                "teams": ["Haustechnik-Team"],
                "groesse": 5,
            },
            "Qualitaetssicherung": {
                "kuerzel": "QS",
                "teams": ["QS-Team"],
                "groesse": 5,
            },
        },
    },
    "Finanzen & Controlling": {
        "kuerzel": "FC",
        "abteilungen": {
            "Buchhaltung": {
                "kuerzel": "BU",
                "teams": ["Debitoren-Team", "Kreditoren-Team"],
                "groesse": 4,
            },
            "Controlling": {
                "kuerzel": "CO",
                "teams": ["Reporting-Team"],
                "groesse": 3,
            },
            "Lohn & Gehalt": {
                "kuerzel": "LG",
                "teams": ["Lohnbuchhaltung-Team"],
                "groesse": 3,
            },
        },
    },
    "IT & Entwicklung": {
        "kuerzel": "IT",
        "abteilungen": {
            "Softwareentwicklung": {
                "kuerzel": "SE",
                "teams": ["Frontend-Team", "Backend-Team"],
                "groesse": 12,
            },
            "IT-Infrastruktur": {
                "kuerzel": "INF",
                "teams": ["Systemadministration-Team", "Helpdesk-Team"],
                "groesse": 8,
            },
            "Produktentwicklung": {
                "kuerzel": "PD",
                "teams": ["Produkt-Team", "UX-Team"],
                "groesse": 8,
            },
            "Daten & Analyse": {
                "kuerzel": "DA",
                "teams": ["Datenanalyse-Team"],
                "groesse": 5,
            },
        },
    },
    "Vertrieb & Marketing": {
        "kuerzel": "VM",
        "abteilungen": {
            "Aussendienst": {
                "kuerzel": "AD",
                "teams": ["Nord-Team", "Sued-Team"],
                "groesse": 8,
            },
            "Innendienst": {
                "kuerzel": "ID",
                "teams": ["Angebots-Team", "Auftragsabwicklung-Team"],
                "groesse": 6,
            },
            "Marketing": {
                "kuerzel": "MK",
                "teams": ["Online-Marketing-Team", "Kommunikations-Team"],
                "groesse": 5,
            },
        },
    },
    "Personal & Organisation": {
        "kuerzel": "PO",
        "abteilungen": {
            "Personalverwaltung": {
                "kuerzel": "PV",
                "teams": ["HR-Ops-Team", "Zeitwirtschaft-Team"],
                "groesse": 4,
            },
            "Personalgewinnung": {
                "kuerzel": "PG",
                "teams": ["Recruiting-Team"],
                "groesse": 3,
            },
            "Personalentwicklung": {
                "kuerzel": "PE",
                "teams": ["Weiterbildungs-Team"],
                "groesse": 3,
            },
        },
    },
}


def _zufallsname():
    geschlecht = random.choice(["m", "w"])
    vorname = random.choice(VORNAMEN_M if geschlecht == "m" else VORNAMEN_W)
    nachname = random.choice(NACHNAMEN)
    return vorname, nachname


def _zufallsdatum():
    start = date(2010, 1, 1)
    tage = random.randint(0, (date(2024, 12, 31) - start).days)
    return start + timedelta(days=tage)


def _erstelle_user(vorname, nachname, persnr, system_user):
    username = f"{vorname.lower()}.{nachname.lower()}.{persnr}"[:30]
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": vorname,
            "last_name": nachname,
            "email": f"{username}@apex-solutions.de",
        },
    )
    return user


class Command(BaseCommand):
    help = "Erstellt 100 Mustermitarbeiter fuer Apex Solutions GmbH"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loeschen",
            action="store_true",
            help="Alle vorhandenen HR-Daten vorher loeschen",
        )

    def handle(self, *args, **options):
        if options["loeschen"]:
            HRMitarbeiter.objects.all().delete()
            Team.objects.all().delete()
            Abteilung.objects.all().delete()
            Bereich.objects.all().delete()
            self.stdout.write("Vorhandene HR-Daten geloescht.")

        # System-User fuer Protokoll
        system_user = User.objects.filter(is_superuser=True).first()

        persnr_zaehler = 1000
        alle_mitarbeiter = []  # fuer spaetere Permissions

        # --- Geschaeftsfuehrung (3 MA) ---
        gf_bereich, _ = Bereich.objects.get_or_create(
            kuerzel="GF",
            defaults={"name": "Geschaeftsfuehrung"},
        )
        gf_rollen = [
            ("Gerhard", "Vogt", "gf"),
            ("Ingrid", "Hartmann", "gf"),
            ("Markus", "Brandt", "gf"),
        ]
        gf_personen = []
        for vorname, nachname, rolle in gf_rollen:
            persnr = f"AP-{persnr_zaehler:04d}"
            persnr_zaehler += 1
            user = _erstelle_user(vorname, nachname, persnr, system_user)
            ma, _ = HRMitarbeiter.objects.get_or_create(
                personalnummer=persnr,
                defaults={
                    "vorname": vorname,
                    "nachname": nachname,
                    "rolle": rolle,
                    "bereich": gf_bereich,
                    "user": user,
                    "eintrittsdatum": _zufallsdatum(),
                    "email": f"{vorname.lower()}.{nachname.lower()}@apex-solutions.de",
                },
            )
            gf_personen.append(ma)
            alle_mitarbeiter.append(ma)

        ceo = gf_personen[0]

        # --- Bereiche, Abteilungen, Teams, Mitarbeiter ---
        abteilungsleiter_liste = []

        for bereich_name, bereich_data in STRUKTUR.items():
            bereich, _ = Bereich.objects.get_or_create(
                kuerzel=bereich_data["kuerzel"],
                defaults={"name": bereich_name},
            )

            # Bereichsleiter
            vn, nn = _zufallsname()
            persnr = f"AP-{persnr_zaehler:04d}"
            persnr_zaehler += 1
            user = _erstelle_user(vn, nn, persnr, system_user)
            bl, _ = HRMitarbeiter.objects.get_or_create(
                personalnummer=persnr,
                defaults={
                    "vorname": vn,
                    "nachname": nn,
                    "rolle": "bereichsleiter",
                    "bereich": bereich,
                    "vorgesetzter": ceo,
                    "user": user,
                    "eintrittsdatum": _zufallsdatum(),
                    "email": f"{vn.lower()}.{nn.lower()}@apex-solutions.de",
                },
            )
            alle_mitarbeiter.append(bl)

            for abt_name, abt_data in bereich_data["abteilungen"].items():
                abteilung, _ = Abteilung.objects.get_or_create(
                    kuerzel=abt_data["kuerzel"],
                    bereich=bereich,
                    defaults={"name": abt_name},
                )

                # Teams anlegen
                team_objekte = []
                for team_name in abt_data["teams"]:
                    team, _ = Team.objects.get_or_create(
                        name=team_name,
                        abteilung=abteilung,
                    )
                    team_objekte.append(team)

                # Abteilungsleiter
                vn, nn = _zufallsname()
                persnr = f"AP-{persnr_zaehler:04d}"
                persnr_zaehler += 1
                user = _erstelle_user(vn, nn, persnr, system_user)
                al, _ = HRMitarbeiter.objects.get_or_create(
                    personalnummer=persnr,
                    defaults={
                        "vorname": vn,
                        "nachname": nn,
                        "rolle": "abteilungsleiter",
                        "bereich": bereich,
                        "abteilung": abteilung,
                        "vorgesetzter": bl,
                        "user": user,
                        "eintrittsdatum": _zufallsdatum(),
                        "email": f"{vn.lower()}.{nn.lower()}@apex-solutions.de",
                    },
                )
                alle_mitarbeiter.append(al)
                abteilungsleiter_liste.append((al, abteilung))

                # 1-2 Assistenten (Stellvertreter)
                anzahl_assistenten = random.randint(1, 2)
                assistenten = []
                for _ in range(anzahl_assistenten):
                    vn, nn = _zufallsname()
                    persnr = f"AP-{persnr_zaehler:04d}"
                    persnr_zaehler += 1
                    user = _erstelle_user(vn, nn, persnr, system_user)
                    assi, _ = HRMitarbeiter.objects.get_or_create(
                        personalnummer=persnr,
                        defaults={
                            "vorname": vn,
                            "nachname": nn,
                            "rolle": "assistent",
                            "bereich": bereich,
                            "abteilung": abteilung,
                            "vorgesetzter": al,
                            "stellvertretung_fuer": al,
                            "user": user,
                            "eintrittsdatum": _zufallsdatum(),
                            "email": f"{vn.lower()}.{nn.lower()}@apex-solutions.de",
                        },
                    )
                    alle_mitarbeiter.append(assi)
                    assistenten.append(assi)

                # Teammitglieder aufteilen
                groesse = abt_data["groesse"]
                teams_count = len(team_objekte)
                for idx in range(groesse):
                    vn, nn = _zufallsname()
                    persnr = f"AP-{persnr_zaehler:04d}"
                    persnr_zaehler += 1
                    team = team_objekte[idx % teams_count]
                    user = _erstelle_user(vn, nn, persnr, system_user)
                    ma, _ = HRMitarbeiter.objects.get_or_create(
                        personalnummer=persnr,
                        defaults={
                            "vorname": vn,
                            "nachname": nn,
                            "rolle": "mitarbeiter",
                            "bereich": bereich,
                            "abteilung": abteilung,
                            "team": team,
                            "vorgesetzter": al,
                            "user": user,
                            "eintrittsdatum": _zufallsdatum(),
                            "email": f"{vn.lower()}.{nn.lower()}@apex-solutions.de",
                        },
                    )
                    alle_mitarbeiter.append(ma)

        # --- Guardian-Permissions vergeben ---
        self.stdout.write("Vergebe guardian-Permissions...")
        for al, abteilung in abteilungsleiter_liste:
            # Alle MA der Abteilung
            abt_mitarbeiter = HRMitarbeiter.objects.filter(abteilung=abteilung)
            stellvertreter = al.stellvertreter.all()

            for ziel_ma in abt_mitarbeiter:
                if ziel_ma == al:
                    continue
                # Abteilungsleiter bekommt Permissions
                if al.user:
                    assign_perm("genehmigen_antraege", al.user, ziel_ma)
                    assign_perm("view_zeiterfassung", al.user, ziel_ma)

                # Assistenten erben dieselben Permissions
                for assi in stellvertreter:
                    if assi.user:
                        assign_perm("genehmigen_antraege", assi.user, ziel_ma)
                        assign_perm("view_zeiterfassung", assi.user, ziel_ma)

        gesamt = HRMitarbeiter.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Fertig! {gesamt} HR-Mitarbeiter angelegt. "
                f"Bereiche: {Bereich.objects.count()}, "
                f"Abteilungen: {Abteilung.objects.count()}, "
                f"Teams: {Team.objects.count()}"
            )
        )
