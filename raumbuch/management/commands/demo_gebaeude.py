"""Management-Command: Musterdaten fuer das Raumbuch anlegen.

Legt an:
  - 1 Hauptstandort
  - Gebaeude A: Hauptverwaltung (breit: 14 Raeume/Etage)
      UG: Keller/Technik-Funktionsraeume (keine Belegung)
      EG: Eingang, Empfang, Konferenz, GF-Bueros
      1.OG - N.OG: Abteilungs-Bueros (2 MA/Buero, Etagen nach Bedarf)
  - Gebaeude B: Erweiterungsbau Reserve (4 Stockwerke, Leerstand)
  - Treppenhaeuser
  - Schluesselverwaltung (General + Gruppen + Einzelschluessel)
  - Zutrittsprofile + Tokens (Muster)
  - Reinigungsplaene fuer alle Raeume
  - Buchungen und Besuchsanmeldungen (Muster)

Aufruf:
    python manage.py demo_gebaeude
    python manage.py demo_gebaeude --reset  # loescht vorhandene Raumbuch-Daten zunaechst
"""
import math
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from hr.models import Abteilung, HRMitarbeiter
from raumbuch.models import (
    Belegung,
    Besuchsanmeldung,
    Gebaeude,
    Geschoss,
    Raum,
    RaumbuchLog,
    Raumbuchung,
    RaumArbeitsschutzDaten,
    RaumElektroDaten,
    RaumFacilityDaten,
    RaumInstallationDaten,
    RaumNetzwerkDaten,
    Reinigungsplan,
    ReinigungsQuittung,
    Schluessel,
    SchluesselAusgabe,
    Standort,
    Treppenhaus,
    ZutrittsProfil,
    ZutrittsToken,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Konstanten Gebaeudelayout (breit)
# ---------------------------------------------------------------------------
# Bueros pro Etage je Fluegel (2 Fluegel = doppelt)
BUEROS_JE_FLUEGEL = 5
FLUEGEL_ANZ = 2
BUEROS_JE_ETAGE = BUEROS_JE_FLUEGEL * FLUEGEL_ANZ   # 10 Bueros / Etage
MA_JE_BUERO = 2                                      # 2er-Belegung
MA_JE_ETAGE = BUEROS_JE_ETAGE * MA_JE_BUERO         # 20 MA / Etage

HEUTE = date.today()


class Command(BaseCommand):
    help = "Legt Muster-Gebaeudestruktur + Mitarbeiter-Belegung im Raumbuch an."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Loescht alle Raumbuch-Daten vor dem Anlegen (Standorte, Gebaeude, Raeume, ...)",
        )

    # -----------------------------------------------------------------------
    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Raumbuch Musterdaten anlegen ===\n"))

        standort = self._standort()
        gebaeude_a = self._gebaeude_a(standort)
        gebaeude_b = self._gebaeude_b_reserve(standort)

        # Treppenhaeuser
        self._treppenhaeuser(gebaeude_a, gebaeude_b)

        # Mitarbeiter laden und gruppieren
        gruppen = self._mitarbeiter_gruppen()
        gesamt_ma = sum(len(v) for v in gruppen.values())
        self.stdout.write(f"  Mitarbeiter: {gesamt_ma} in {len(gruppen)} Gruppe(n)")

        # Etagen berechnen
        og_bedarf = max(1, math.ceil(gesamt_ma / MA_JE_ETAGE))
        self.stdout.write(f"  Benoetigte Buero-Etagen: {og_bedarf}")

        # Gebaeude A aufbauen
        geschoss_ug = self._geschoss(gebaeude_a, "UG", "Untergeschoss (Keller)", 0)
        geschoss_eg = self._geschoss(gebaeude_a, "EG", "Erdgeschoss", 1)
        og_geschosse = []
        for nr in range(1, og_bedarf + 1):
            kuerzel = str(nr)
            bezeichnung = f"{nr}. Obergeschoss"
            og_geschosse.append(self._geschoss(gebaeude_a, kuerzel, bezeichnung, nr + 1))

        # Raeume anlegen
        self._ug_raeume(geschoss_ug, gebaeude_a)
        gf_raeume = self._eg_raeume(geschoss_eg, gebaeude_a)
        buero_raeume = []
        for g in og_geschosse:
            buero_raeume.extend(self._og_raeume(g, gebaeude_a))

        # Belegungen zuweisen
        self._belegungen_zuweisen(gruppen, gf_raeume, buero_raeume)

        # Gebaeude B (Reserve)
        self._reserve_raeume(gebaeude_b)

        # Datenschichten befuellen (Muster)
        self._datenschichten_befuellen(gebaeude_a)

        # Schluesselverwaltung
        self._schluessel(gebaeude_a)

        # Zutrittsprofile + Tokens
        self._zutrittsprofile()

        # Reinigungsplaene
        self._reinigungsplaene()

        # Musterbuchungen und Besuche
        self._musterbuchungen(geschoss_eg, og_geschosse)
        self._musterbesuche()

        self.stdout.write(self.style.SUCCESS("\n=== Fertig! Raumbuch erfolgreich aufgebaut. ===\n"))

    # -----------------------------------------------------------------------
    # Reset
    # -----------------------------------------------------------------------
    def _reset(self):
        self.stdout.write(self.style.WARNING("  Loesche vorhandene Raumbuch-Daten..."))
        RaumbuchLog.objects.all().delete()
        ReinigungsQuittung.objects.all().delete()
        Reinigungsplan.objects.all().delete()
        Belegung.objects.all().delete()
        Raumbuchung.objects.all().delete()
        Besuchsanmeldung.objects.all().delete()
        SchluesselAusgabe.objects.all().delete()
        ZutrittsToken.objects.all().delete()
        ZutrittsProfil.objects.all().delete()
        Schluessel.objects.all().delete()
        Treppenhaus.objects.all().delete()
        Raum.objects.all().delete()
        Geschoss.objects.all().delete()
        Gebaeude.objects.all().delete()
        Standort.objects.all().delete()

    # -----------------------------------------------------------------------
    # Standort
    # -----------------------------------------------------------------------
    def _standort(self):
        obj, created = Standort.objects.get_or_create(
            kuerzel="HS",
            defaults={
                "name": "Hauptstandort",
                "adresse": "Musterstrasse 1\n12345 Musterstadt",
            },
        )
        self._log_erstellt("Standort", obj, created)
        return obj

    # -----------------------------------------------------------------------
    # Gebaeude A
    # -----------------------------------------------------------------------
    def _gebaeude_a(self, standort):
        obj, created = Gebaeude.objects.get_or_create(
            kuerzel="A",
            standort=standort,
            defaults={
                "bezeichnung": "Verwaltungsgebaeude A",
                "baujahr": 1998,
            },
        )
        self._log_erstellt("Gebaeude A", obj, created)
        return obj

    # -----------------------------------------------------------------------
    # Gebaeude B (Reserve)
    # -----------------------------------------------------------------------
    def _gebaeude_b_reserve(self, standort):
        obj, created = Gebaeude.objects.get_or_create(
            kuerzel="B",
            standort=standort,
            defaults={
                "bezeichnung": "Erweiterungsbau B (Reserve)",
                "baujahr": 2005,
            },
        )
        self._log_erstellt("Gebaeude B", obj, created)
        return obj

    # -----------------------------------------------------------------------
    # Treppenhaeuser
    # -----------------------------------------------------------------------
    def _treppenhaeuser(self, geb_a, geb_b):
        daten = [
            (geb_a, "Haupttreppenhaus A-Nord", "haupt", "UG-4.OG"),
            (geb_a, "Nebentreppenhaus A-Sued", "neben", "EG-4.OG"),
            (geb_b, "Haupttreppenhaus B", "haupt", "EG-4.OG"),
        ]
        for geb, bez, typ, verbindet in daten:
            obj, created = Treppenhaus.objects.get_or_create(
                gebaeude=geb,
                bezeichnung=bez,
                defaults={
                    "typ": typ,
                    "verbindet_geschosse": verbindet,
                    "lichte_breite_cm": 150,
                    "kapazitaet_personen": 30,
                    "zustand": "gut",
                    "naechste_pruefung": HEUTE + timedelta(days=365),
                },
            )
            self._log_erstellt(f"Treppenhaus {bez}", obj, created)

    # -----------------------------------------------------------------------
    # Geschoss-Hilfsfunktion
    # -----------------------------------------------------------------------
    def _geschoss(self, gebaeude, kuerzel, bezeichnung, reihenfolge):
        obj, created = Geschoss.objects.get_or_create(
            gebaeude=gebaeude,
            kuerzel=kuerzel,
            defaults={"bezeichnung": bezeichnung, "reihenfolge": reihenfolge},
        )
        if created:
            self.stdout.write(f"    + Geschoss {kuerzel} ({bezeichnung})")
        return obj

    # -----------------------------------------------------------------------
    # UG: Keller / Funktionsraeume
    # -----------------------------------------------------------------------
    def _ug_raeume(self, geschoss, gebaeude):
        """Nur Funktionsraeume im Keller – keine Mitarbeiter-Belegung."""
        keller_raeume = [
            ("K01", "heizungsraum", "Heizungsraum / Kesselraum",         40, False),
            ("K02", "lueftungsraum", "Lueftungszentrale",                 60, False),
            ("K03", "elektroverteilung", "Elektroverteilerraum (HV)",     25, False),
            ("K04", "serverraum", "Serverraum / Rechenzentrum",           35, False),
            ("K05", "it_verteiler", "IT-Verteiler Keller",                15, False),
            ("K06", "lager", "Lager 1 (Allgemein)",                      80, False),
            ("K07", "lager", "Lager 2 (Archivgut)",                      80, False),
            ("K08", "archiv", "Altarchiv",                               120, False),
            ("K09", "putzraum", "Putzraum Keller",                        8, False),
            ("K10", "abstellraum", "Abstellraum / Hausmeister",           20, False),
            ("K11", "wc_herren", "WC Herren Keller",                      12, False),
            ("K12", "wc_damen", "WC Damen Keller",                        12, False),
            ("K13", "lager", "Lager 3 (Verbrauchsmaterial)",              50, False),
            ("K14", "abstellraum", "Fahrrradkeller / Abstellflaeche",     30, False),
            ("K15", "flur", "Flur Keller",                               60, False),
        ]
        anzahl = 0
        for nr, typ, name, flaeche, leer in keller_raeume:
            r, created = Raum.objects.get_or_create(
                geschoss=geschoss,
                raumnummer=nr,
                defaults={
                    "raumname": name,
                    "raumtyp": typ,
                    "flaeche_m2": flaeche,
                    "ist_leer": leer,
                    "nutzungsmodell": "statisch",
                },
            )
            if created:
                anzahl += 1
        self.stdout.write(f"    + UG: {anzahl} Keller-Funktionsraeume angelegt")

    # -----------------------------------------------------------------------
    # EG: Eingang, Empfang, Besprechung, GF
    # -----------------------------------------------------------------------
    def _eg_raeume(self, geschoss, gebaeude):
        """EG: Eingangsbereich + Management-Bueros. Gibt GF-Bueros zurueck."""
        eg_raeume = [
            # (raumnummer, raumtyp, raumname,         flaeche, buchbar)
            ("E01", "windfang",    "Haupteingang / Windfang",      20, False),
            ("E02", "eingang",     "Empfangsbereich / Rezeption",  45, False),
            ("E03", "besprechung", "Besprechungsraum EG-Klein 1",  20, True),
            ("E04", "besprechung", "Besprechungsraum EG-Klein 2",  20, True),
            ("E05", "konferenz",   "Konferenzraum Hauptgebaeude",  80, True),
            ("E06", "schulung",    "Schulungsraum",                60, True),
            ("E07", "einzelbuero", "Geschaeftsfuehrung",           30, False),
            ("E08", "einzelbuero", "Assistent/in Geschaeftsfuehrung", 20, False),
            ("E09", "besprechung", "Besprechungsraum Leitungsebene", 25, False),
            ("E10", "teekueche",   "Teekueche EG",                 18, False),
            ("E11", "pausenraum",  "Pausenraum / Kantine EG",      40, False),
            ("E12", "wc_herren",   "WC Herren EG",                 12, False),
            ("E13", "wc_damen",    "WC Damen EG",                  12, False),
            ("E14", "wc_barrierefrei", "WC Barrierefrei EG",       15, False),
            ("E15", "druckerraum", "Druckerraum / Kopiercenter EG", 15, False),
        ]
        gf_buero_nummern = {"E07", "E08"}
        gf_raeume = []
        anzahl = 0
        for nr, typ, name, flaeche, buchbar in eg_raeume:
            r, created = Raum.objects.get_or_create(
                geschoss=geschoss,
                raumnummer=nr,
                defaults={
                    "raumname": name,
                    "raumtyp": typ,
                    "flaeche_m2": flaeche,
                    "nutzungsmodell": "dynamisch" if buchbar else "statisch",
                    "kapazitaet": flaeche // 4 if buchbar else None,
                    "ist_leer": False,
                },
            )
            if created:
                anzahl += 1
            if nr in gf_buero_nummern:
                gf_raeume.append(r)
        self.stdout.write(f"    + EG: {anzahl} Raeume angelegt")
        return gf_raeume

    # -----------------------------------------------------------------------
    # OG: Buero-Etagen (breit = 2 Fluegel x 5 Bueros + Nebenraeume)
    # -----------------------------------------------------------------------
    def _og_raeume(self, geschoss, gebaeude):
        """Erstellt eine Buero-Etage (breit). Gibt Liste der Buero-Raeume zurueck."""
        kuerzel = geschoss.kuerzel   # z.B. "1", "2", ...
        prefix = kuerzel             # Raumnummer-Prefix

        buero_raeume = []
        raeume_def = []

        # Fluegel A (Nord) – 5 Bueros
        for i in range(1, BUEROS_JE_FLUEGEL + 1):
            nr = f"{prefix}A{i:02d}"
            raeume_def.append((nr, "einzelbuero", f"Buero A{i} ({kuerzel}.OG Nord)", 20, False))

        # Fluegel B (Sued) – 5 Bueros
        for i in range(1, BUEROS_JE_FLUEGEL + 1):
            nr = f"{prefix}B{i:02d}"
            raeume_def.append((nr, "einzelbuero", f"Buero B{i} ({kuerzel}.OG Sued)", 20, False))

        # Nebenraeume
        raeume_def.extend([
            (f"{prefix}K01", "konferenz",   f"Besprechungsraum {kuerzel}.OG",     30, True),
            (f"{prefix}K02", "teekueche",   f"Teekueche {kuerzel}.OG",            14, False),
            (f"{prefix}K03", "wc_herren",   f"WC Herren {kuerzel}.OG",            10, False),
            (f"{prefix}K04", "wc_damen",    f"WC Damen {kuerzel}.OG",             10, False),
        ])

        anzahl = 0
        for nr, typ, name, flaeche, buchbar in raeume_def:
            r, created = Raum.objects.get_or_create(
                geschoss=geschoss,
                raumnummer=nr,
                defaults={
                    "raumname": name,
                    "raumtyp": typ,
                    "flaeche_m2": flaeche,
                    "kapazitaet": 2 if typ == "einzelbuero" else (flaeche // 4 if buchbar else None),
                    "nutzungsmodell": "dynamisch" if buchbar else "statisch",
                    "ist_leer": False,
                },
            )
            if created:
                anzahl += 1
            if typ == "einzelbuero":
                buero_raeume.append(r)

        self.stdout.write(f"    + {kuerzel}.OG: {anzahl} Raeume ({BUEROS_JE_ETAGE} Bueros) angelegt")
        return buero_raeume

    # -----------------------------------------------------------------------
    # Reserve-Gebaeude B (4 Stockwerke, alles Leerstand)
    # -----------------------------------------------------------------------
    def _reserve_raeume(self, gebaeude):
        """Gebaeude B: 5 Geschosse (EG-4.OG), alle Raeume als Leerstand."""
        stock_daten = [
            ("EG", "Erdgeschoss Reserve", 1),
            ("1",  "1. OG Reserve", 2),
            ("2",  "2. OG Reserve", 3),
            ("3",  "3. OG Reserve", 4),
            ("4",  "4. OG Reserve", 5),
        ]
        gesamt = 0
        for kuerzel, bezeichnung, reihenfolge in stock_daten:
            g = self._geschoss(gebaeude, kuerzel, bezeichnung, reihenfolge)
            # Reserviert: gleiche Struktur wie OG in Gebaeude A, aber leer
            for seite in ("A", "B"):
                for i in range(1, BUEROS_JE_FLUEGEL + 1):
                    nr = f"R{kuerzel}{seite}{i:02d}"
                    r, created = Raum.objects.get_or_create(
                        geschoss=g,
                        raumnummer=nr,
                        defaults={
                            "raumname": f"Reserve-Buero {seite}{i} ({kuerzel})",
                            "raumtyp": "einzelbuero",
                            "flaeche_m2": 20,
                            "kapazitaet": 2,
                            "nutzungsmodell": "statisch",
                            "ist_leer": True,
                        },
                    )
                    if created:
                        gesamt += 1
        self.stdout.write(f"    + Gebaeude B: {gesamt} Reserve-Raeume (Leerstand) angelegt")

    # -----------------------------------------------------------------------
    # Mitarbeiter gruppieren nach Abteilung
    # -----------------------------------------------------------------------
    def _mitarbeiter_gruppen(self):
        """Gibt dict {gruppenname: [HRMitarbeiter, ...]} zurueck.

        Gruppierung: Abteilung > Bereich > "Ohne Zuordnung"
        Fuehrungskraefte (GF, Bereichsleiter) kommen in Gruppe "GF/Leitung".
        """
        gruppen = {}

        alle = HRMitarbeiter.objects.select_related(
            "abteilung__bereich", "bereich"
        ).order_by("abteilung__bereich__name", "abteilung__name", "nachname")

        for ma in alle:
            if ma.rolle in ("gf", "bereichsleiter"):
                key = "GF und Bereichsleitung"
            elif ma.abteilung:
                key = ma.abteilung.name
            elif ma.bereich:
                key = f"{ma.bereich.name} (ohne Abteilung)"
            else:
                key = "Ohne Zuordnung"

            gruppen.setdefault(key, []).append(ma)

        return gruppen

    # -----------------------------------------------------------------------
    # Belegungen zuweisen
    # -----------------------------------------------------------------------
    def _belegungen_zuweisen(self, gruppen, gf_raeume, buero_raeume):
        """Weist Mitarbeiter den Bueros zu: 2 MA / Raum.

        GF/Leitung bevorzugt EG-Bueros, Overflow und alle anderen -> OG-Bueros.
        Wenn alle Bueros voll sind, wird das letzte Buero weiter aufgefuellt.
        """
        erstellt = 0

        # Gemeinsamer globaler Pool: GF-Bueros zuerst, dann OG-Bueros
        alle_bueros = list(gf_raeume) + list(buero_raeume)

        def _belegen(raum, ma):
            nonlocal erstellt
            _, created = Belegung.objects.get_or_create(
                raum=raum,
                mitarbeiter=ma,
                defaults={"von": HEUTE},
            )
            if created:
                erstellt += 1

        # Flache MA-Liste: GF/Leitung zuerst, dann Abteilungen
        gf_ma = []
        abt_ma_gruppen = {}
        for gruppenname, ma_liste in gruppen.items():
            if gruppenname == "GF und Bereichsleitung":
                gf_ma = ma_liste
            else:
                abt_ma_gruppen[gruppenname] = ma_liste

        # Globaler Buero-Index (schiebefenster, 2 MA pro Raum)
        buero_index = 0
        ma_im_buero = 0   # Zaehlt wie viele MA bereits im aktuellen Buero

        def _naechstes_buero_belegen(ma):
            nonlocal buero_index, ma_im_buero
            if not alle_bueros:
                return
            if buero_index >= len(alle_bueros):
                buero_index = len(alle_bueros) - 1   # Overflow: letztes Buero
            _belegen(alle_bueros[buero_index], ma)
            ma_im_buero += 1
            if ma_im_buero >= MA_JE_BUERO:
                buero_index += 1
                ma_im_buero = 0

        # GF/Leitung zuerst verteilen
        for ma in gf_ma:
            _naechstes_buero_belegen(ma)

        # Abteilungen: Gruppen zusammenhalten (nicht mitten in Gruppe trennen)
        for gruppenname, ma_liste in abt_ma_gruppen.items():
            for ma in ma_liste:
                _naechstes_buero_belegen(ma)

        self.stdout.write(f"    + {erstellt} Belegungen eingetragen")

    # -----------------------------------------------------------------------
    # Datenschichten befuellen (Muster fuer wichtige Raeume)
    # -----------------------------------------------------------------------
    def _datenschichten_befuellen(self, gebaeude):
        """Befuellt Datenschichten fuer Serverraum, Elektro, Konferenz."""
        serverraeume = Raum.objects.filter(
            geschoss__gebaeude=gebaeude, raumtyp="serverraum"
        )
        for raum in serverraeume:
            nw, _ = RaumNetzwerkDaten.objects.get_or_create(raum=raum)
            nw.switch_name = "Core-Switch-01"
            nw.switch_port = "Rack A, Port 24"
            nw.lan_ports_anzahl = 48
            nw.wlan_abdeckung = "gut"
            nw.ip_adressen = "192.168.10.1 – 192.168.10.50"
            nw.save()

            el, _ = RaumElektroDaten.objects.get_or_create(raum=raum)
            el.usv_gesichert = True
            el.drehstrom = True
            el.stromkreise_beschreibung = "UK-Server 1 + UK-Server 2 (USV-gesichert)"
            el.notbeleuchtung = True
            el.save()

            as_, _ = RaumArbeitsschutzDaten.objects.get_or_create(raum=raum)
            as_.rauchmelder = True
            as_.feuerloesch_typ = "CO2-Loescher"
            as_.feuerloesch_nummer = "FL-K04-01"
            as_.feuerloesch_naechste_pruefung = HEUTE + timedelta(days=180)
            as_.brandabschnitt = "Brandabschnitt A"
            as_.gefahrstoffe_vorhanden = False
            as_.save()

        # Konferenzraum EG mit Facility-Daten
        konferenzraeume = Raum.objects.filter(
            geschoss__gebaeude=gebaeude, raumtyp="konferenz"
        )
        for raum in konferenzraeume:
            fac, _ = RaumFacilityDaten.objects.get_or_create(raum=raum)
            fac.bodenbelag = "Teppich (Blau)"
            fac.fenster_anzahl = 4
            fac.fenster_verdunkelbar = True
            fac.klima_typ = "Klimaanlage Split-Geraet"
            fac.lueftungsanlage = True
            fac.flaeche_m2 = raum.flaeche_m2
            fac.moebelliste = "Konferenztisch (14 Plaetze)\n14 Konferenzstühle\nWhiteboard\nPresenter-Bildschirm 75\""
            fac.save()

            nw, _ = RaumNetzwerkDaten.objects.get_or_create(raum=raum)
            nw.lan_ports_anzahl = 8
            nw.wlan_abdeckung = "gut"
            nw.save()

        # Heizungsraum mit Installations-Daten
        heizungsraeume = Raum.objects.filter(
            geschoss__gebaeude=gebaeude, raumtyp="heizungsraum"
        )
        for raum in heizungsraeume:
            inst, _ = RaumInstallationDaten.objects.get_or_create(raum=raum)
            inst.absperrhaehne = "HA-K01 (Hauptabsperrung Erdgas)\nHA-K02 (Heizkreis Nord)\nHA-K03 (Heizkreis Sued)"
            inst.glt_adressen = "GLT-HZ-01 / Raum K01"
            inst.save()

            as_, _ = RaumArbeitsschutzDaten.objects.get_or_create(raum=raum)
            as_.rauchmelder = True
            as_.feuerloesch_typ = "Kohlensaeure-Loescher 5 kg"
            as_.feuerloesch_nummer = "FL-K01-01"
            as_.feuerloesch_naechste_pruefung = HEUTE + timedelta(days=365)
            as_.gefahrstoffe_vorhanden = True
            as_.gefahrstoffe_beschreibung = "Heizoel / Erdgas – Betriebsraeume"
            as_.save()

        self.stdout.write("    + Datenschichten (Server, Konferenz, Heizung) befuellt")

    # -----------------------------------------------------------------------
    # Schluesselverwaltung
    # -----------------------------------------------------------------------
    def _schluessel(self, gebaeude):
        """Erstellt Generalschluessel, Etagen-Gruppen und Einzelschluessel."""
        # Alle aktiven Raeume des Gebaeudes
        alle_raeume = list(Raum.objects.filter(geschoss__gebaeude=gebaeude))

        schluessel_daten = [
            ("GEN-001", "Generalschluessel Gebaeude A",  "general",  "TS-2000", 3, alle_raeume),
            ("GRP-UG",  "Kellerschluessel",               "gruppe",   "TS-2000", 5, list(Raum.objects.filter(geschoss__gebaeude=gebaeude, geschoss__kuerzel="UG"))),
            ("GRP-EG",  "Erdgeschoss-Schluessel",         "gruppe",   "TS-2000", 8, list(Raum.objects.filter(geschoss__gebaeude=gebaeude, geschoss__kuerzel="EG"))),
            ("SRV-001", "Schluessel Serverraum",          "einzel",   "TS-2000", 2, list(Raum.objects.filter(geschoss__gebaeude=gebaeude, raumtyp="serverraum"))),
            ("ELK-001", "Schluessel Elektroverteiler",    "einzel",   "TS-2000", 2, list(Raum.objects.filter(geschoss__gebaeude=gebaeude, raumtyp="elektroverteilung"))),
        ]

        erstellt = 0
        for nr, bez, typ, anlage, kopien, raeume in schluessel_daten:
            s, created = Schluessel.objects.get_or_create(
                schluesselnummer=nr,
                defaults={
                    "bezeichnung": bez,
                    "schliessanlage_typ": typ,
                    "schliessanlage": anlage,
                    "anzahl_kopien": kopien,
                },
            )
            if raeume:
                s.raeume.set(raeume)
            if created:
                erstellt += 1

        self.stdout.write(f"    + {erstellt} Schluessel angelegt")

    # -----------------------------------------------------------------------
    # Zutrittsprofile + Token
    # -----------------------------------------------------------------------
    def _zutrittsprofile(self):
        """Erstellt 3 Muster-Zutrittsprofile."""
        server_raeume = list(Raum.objects.filter(raumtyp__in=["serverraum", "it_verteiler", "elektroverteilung"]))
        alle_buero = list(Raum.objects.filter(raumtyp="einzelbuero"))

        profile_daten = [
            ("Allgemeiner Zugang",   "Zugang zu Bueros, EG und Fluren", alle_buero),
            ("IT-Administrator",     "Vollzugang inklusive Serverraeume und Verteiler", server_raeume + alle_buero),
            ("Leitungsebene EG",     "Zugang zu GF-Bueros und Konferenzraum EG", list(Raum.objects.filter(geschoss__kuerzel="EG"))),
        ]

        erstellt = 0
        for bez, beschr, raeume in profile_daten:
            p, created = ZutrittsProfil.objects.get_or_create(
                bezeichnung=bez, defaults={"beschreibung": beschr}
            )
            if raeume:
                p.raeume.set(raeume)
            if created:
                erstellt += 1

        # Muster-Token fuer ersten MA mit Abteilung (wenn vorhanden)
        token_erstellt = 0
        ma_qs = HRMitarbeiter.objects.filter(abteilung__isnull=False)[:3]
        profil_allgemein = ZutrittsProfil.objects.filter(bezeichnung="Allgemeiner Zugang").first()
        for i, ma in enumerate(ma_qs):
            t, created = ZutrittsToken.objects.get_or_create(
                badge_id=f"BADGE-{10001 + i}",
                defaults={
                    "mitarbeiter": ma,
                    "status": "aktiv",
                    "ausgestellt_am": HEUTE - timedelta(days=90),
                    "gueltig_bis": HEUTE + timedelta(days=365),
                    "ablauf_warnung_tage": 30,
                },
            )
            if profil_allgemein:
                t.profile.set([profil_allgemein])
            if created:
                token_erstellt += 1

        self.stdout.write(f"    + {erstellt} Zutrittsprofile, {token_erstellt} Muster-Tokens angelegt")

    # -----------------------------------------------------------------------
    # Reinigungsplaene
    # -----------------------------------------------------------------------
    def _reinigungsplaene(self):
        """Erstellt Reinigungsplan fuer alle Raeume (nach Typ differenziert)."""
        erstellt = 0
        taeglich = {"einzelbuero", "grossraumbuero", "teambuero", "wc_herren", "wc_damen", "wc_barrierefrei",
                    "teekueche", "eingang", "flur", "windfang"}
        woechentlich = {"besprechung", "konferenz", "schulung", "pausenraum", "kantine", "druckerraum"}

        for raum in Raum.objects.all():
            intervall = "taeglich" if raum.raumtyp in taeglich else \
                        "woechentlich" if raum.raumtyp in woechentlich else "monatlich"
            _, created = Reinigungsplan.objects.get_or_create(
                raum=raum,
                defaults={
                    "intervall": intervall,
                    "zustaendig": "Reinigungsdienst",
                    "letzte_reinigung": HEUTE - timedelta(days=1),
                },
            )
            if created:
                erstellt += 1

        self.stdout.write(f"    + {erstellt} Reinigungsplaene angelegt")

    # -----------------------------------------------------------------------
    # Musterbuchungen
    # -----------------------------------------------------------------------
    def _musterbuchungen(self, geschoss_eg, og_geschosse):
        """Legt einige Raumbuchungen fuer Konferenzraeume an."""
        buchbare = list(Raum.objects.filter(nutzungsmodell="dynamisch")[:5])
        if not buchbare:
            return

        admin_user = User.objects.filter(is_staff=True).first()
        if not admin_user:
            return

        buchungs_daten = [
            (buchbare[0], HEUTE, "08:00", "10:00", "Teammeeting Montag", 6),
            (buchbare[0], HEUTE, "14:00", "16:00", "Projektbesprechung", 4),
            (buchbare[min(1, len(buchbare)-1)], HEUTE + timedelta(days=1), "09:00", "11:00", "Bereichsleitungs-Jour-Fixe", 8),
            (buchbare[0], HEUTE + timedelta(days=2), "10:00", "12:00", "Personalgespraech", 2),
        ]

        erstellt = 0
        for raum, datum, von, bis, betreff, teilnehmer in buchungs_daten:
            nr = Raumbuchung.generiere_buchungsnummer()
            _, created = Raumbuchung.objects.get_or_create(
                raum=raum,
                datum=datum,
                von=von,
                bis=bis,
                defaults={
                    "betreff": betreff,
                    "teilnehmerzahl": teilnehmer,
                    "buchender": admin_user,
                    "buchungs_nr": nr,
                    "status": "bestaetigt",
                },
            )
            if created:
                erstellt += 1

        self.stdout.write(f"    + {erstellt} Muster-Buchungen angelegt")

    # -----------------------------------------------------------------------
    # Muster-Besuchsanmeldungen
    # -----------------------------------------------------------------------
    def _musterbesuche(self):
        """Legt 2 Beispiel-Besuchsanmeldungen an."""
        admin_user = User.objects.filter(is_staff=True).first()
        if not admin_user:
            return

        gastgeber = HRMitarbeiter.objects.first()
        if not gastgeber:
            return

        konferenz = Raum.objects.filter(raumtyp="konferenz").first()

        besuche = [
            {
                "besucher_vorname": "Max",
                "besucher_nachname": "Mustermann",
                "besucher_firma": "Muster GmbH",
                "datum": HEUTE + timedelta(days=1),
                "von": "10:00",
                "bis": "12:00",
                "zweck": "Produktpraesentation neue Software",
                "status": "angemeldet",
            },
            {
                "besucher_vorname": "Erika",
                "besucher_nachname": "Beispiel",
                "besucher_firma": "Beispiel AG",
                "datum": HEUTE + timedelta(days=3),
                "von": "14:00",
                "bis": "16:30",
                "zweck": "Vertragsgespraech",
                "status": "angemeldet",
            },
        ]

        erstellt = 0
        for daten in besuche:
            _, created = Besuchsanmeldung.objects.get_or_create(
                besucher_nachname=daten["besucher_nachname"],
                besucher_vorname=daten["besucher_vorname"],
                datum=daten["datum"],
                defaults={
                    **daten,
                    "gastgeber": gastgeber,
                    "zielraum": konferenz,
                    "erstellt_von": admin_user,
                },
            )
            if created:
                erstellt += 1

        self.stdout.write(f"    + {erstellt} Muster-Besuchsanmeldungen angelegt")

    # -----------------------------------------------------------------------
    # Hilfsmethode
    # -----------------------------------------------------------------------
    def _log_erstellt(self, bezeichnung, obj, created):
        if created:
            self.stdout.write(f"  + {bezeichnung} angelegt: {obj}")
        else:
            self.stdout.write(f"  ~ {bezeichnung} bereits vorhanden: {obj}")
