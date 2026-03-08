"""Management Command: Befuellt die Netzwerkinfrastruktur im Raumbuch.

Legt an:
- RaumNetzwerkDaten fuer alle Bueros (4 Dosen x Anzahl Arbeitsplaetze)
- NetzwerkKomponenten fuer Serverraum (K04) und IT-Verteiler (K05)
- Glasfaserverbindungen UG -> alle Etagen

Idempotent: bestehende Eintraege werden nicht dupliziert.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


# ---------------------------------------------------------------------------
# Netzwerk-Adressplan
# ---------------------------------------------------------------------------
VLAN_MAP = {
    "UG": {"vlan": "VLAN 20", "netz": "10.10.2"},
    "EG": {"vlan": "VLAN 30", "netz": "10.10.3"},
    "1":  {"vlan": "VLAN 41", "netz": "10.10.4"},
    "2":  {"vlan": "VLAN 42", "netz": "10.10.5"},
    "3":  {"vlan": "VLAN 43", "netz": "10.10.6"},
    "4":  {"vlan": "VLAN 44", "netz": "10.10.7"},
    "5":  {"vlan": "VLAN 45", "netz": "10.10.8"},
    "6":  {"vlan": "VLAN 46", "netz": "10.10.9"},
    "7":  {"vlan": "VLAN 47", "netz": "10.10.10"},
}

SWITCH_MAP = {
    "UG": "SW-DIST-UG",
    "EG": "SW-EV-EG",
    "1":  "SW-EV-OG1",
    "2":  "SW-EV-OG2",
    "3":  "SW-EV-OG3",
    "4":  "SW-EV-OG4",
    "5":  "SW-EV-OG5",
    "6":  "SW-EV-OG6",
    "7":  "SW-EV-OG7",
}


class Command(BaseCommand):
    help = "Befuellt Netzwerkdaten, Rack-Komponenten und Glasfaser-Verbindungen"

    def handle(self, *args, **options):
        from raumbuch.models import (
            Glasfaserverbindung, NetzwerkKomponente,
            Raum, RaumNetzwerkDaten,
        )

        with transaction.atomic():
            self._befuelle_buero_netzwerk()
            self._befuelle_sonstige_raeume()
            k04 = self._befuelle_serverraum_k04()
            k05 = self._befuelle_it_verteiler_k05()
            if k04 and k05:
                self._erstelle_glasfaserverbindungen(k04, k05)

        self.stdout.write(self.style.SUCCESS("Netzwerk-Seed abgeschlossen."))

    # ------------------------------------------------------------------
    # Hilfsfunktion: RaumNetzwerkDaten anlegen / aktualisieren
    # ------------------------------------------------------------------
    def _netz(self, raum, **kwargs):
        from raumbuch.models import RaumNetzwerkDaten
        nd, created = RaumNetzwerkDaten.objects.get_or_create(raum=raum)
        for k, v in kwargs.items():
            setattr(nd, k, v)
        nd.save()
        return created

    def _komp(self, raum, bezeichnung, **kwargs):
        """Anlegen wenn noch nicht vorhanden (nach Bezeichnung+Raum)."""
        from raumbuch.models import NetzwerkKomponente
        obj, created = NetzwerkKomponente.objects.get_or_create(
            raum=raum,
            bezeichnung=bezeichnung,
            defaults=kwargs,
        )
        if created:
            self.stdout.write(f"  + {bezeichnung} in {raum.raumnummer}")
        return obj

    # ------------------------------------------------------------------
    # 1. Buero-Raeume: 4 Dosen pro Arbeitsplatz (Belegung), min. 4
    # ------------------------------------------------------------------
    def _befuelle_buero_netzwerk(self):
        from raumbuch.models import Raum
        bueros = Raum.objects.filter(
            raumtyp__in=["einzelbuero", "grossraumbuero", "teambuero", "homeoffice_pool"]
        ).prefetch_related("belegungen", "geschoss")

        erstellt = 0
        for raum in bueros:
            ma_count = raum.belegungen.count()
            dosen = max(ma_count, 1) * 4  # mindestens 4, normalerweise 8
            geschoss_kuerzel = raum.geschoss.kuerzel
            vlan_info = VLAN_MAP.get(geschoss_kuerzel, {"vlan": "VLAN 99", "netz": "10.10.99"})
            switch_name = SWITCH_MAP.get(geschoss_kuerzel, "SW-UNBEKANNT")

            # Raumnummer als Patch-Port-Basis
            patch_nr = _patch_port_fuer_raum(raum.raumnummer)

            created = self._netz(
                raum,
                lan_ports_anzahl=dosen,
                lan_ports_beschreibung=(
                    f"{dosen} x CAT7 RJ45 | "
                    f"{ma_count} Arbeitsplaetze x 4 Dosen | "
                    f"Patchfeld-Ports {patch_nr}-{patch_nr + dosen - 1}"
                ),
                switch_name=switch_name,
                switch_port=f"Port {patch_nr}-{patch_nr + dosen - 1}",
                telefondosen=max(ma_count, 1),
                wlan_abdeckung="gut",
                vlan=vlan_info["vlan"],
            )
            if created:
                erstellt += 1

        self.stdout.write(f"Bueros: {erstellt} neu, {bueros.count() - erstellt} schon vorhanden")

    # ------------------------------------------------------------------
    # 2. Sonstige Raumtypen (Konferenz, Schulung, Drucker etc.)
    # ------------------------------------------------------------------
    def _befuelle_sonstige_raeume(self):
        from raumbuch.models import Raum

        konfig = {
            "konferenz":   {"dosen": 8, "wlan": "gut",    "tel": 2, "info": "8 x CAT7 | Beamer, Videokonferenz, 8 Pax"},
            "besprechung": {"dosen": 4, "wlan": "gut",    "tel": 1, "info": "4 x CAT7 | Besprechung bis 4 Pax"},
            "schulung":    {"dosen": 24,"wlan": "gut",    "tel": 1, "info": "24 x CAT7 | 12 Schulungsplaetze x 2 Dosen"},
            "teekueche":   {"dosen": 2, "wlan": "mittel", "tel": 0, "info": "2 x CAT7 | Kaffeemaschine, Kuehlschrank"},
            "druckerraum": {"dosen": 4, "wlan": "mittel", "tel": 0, "info": "4 x CAT7 | Drucker, Kopierer, Scanner"},
            "pausenraum":  {"dosen": 2, "wlan": "gut",    "tel": 0, "info": "2 x CAT7 | Infoscreen"},
            "eingang":     {"dosen": 4, "wlan": "gut",    "tel": 2, "info": "4 x CAT7 | Empfang, Zutrittskontrolle"},
            "flur":        {"dosen": 2, "wlan": "gut",    "tel": 0, "info": "2 x CAT7 | Access Points"},
        }
        erstellt = 0
        for raumtyp, cfg in konfig.items():
            for raum in Raum.objects.filter(raumtyp=raumtyp):
                geschoss_kuerzel = raum.geschoss.kuerzel
                vlan_info = VLAN_MAP.get(geschoss_kuerzel, {"vlan": "VLAN 99", "netz": "10.10.99"})
                switch_name = SWITCH_MAP.get(geschoss_kuerzel, "SW-UNBEKANNT")
                patch_nr = _patch_port_fuer_raum(raum.raumnummer)
                created = self._netz(
                    raum,
                    lan_ports_anzahl=cfg["dosen"],
                    lan_ports_beschreibung=cfg["info"],
                    switch_name=switch_name,
                    switch_port=f"Port {patch_nr}-{patch_nr + cfg['dosen'] - 1}",
                    telefondosen=cfg["tel"],
                    wlan_abdeckung=cfg["wlan"],
                    vlan=vlan_info["vlan"],
                )
                if created:
                    erstellt += 1
        self.stdout.write(f"Sonstige Raeume: {erstellt} neu angelegt")

    # ------------------------------------------------------------------
    # 3. Serverraum K04 – Core-Schicht
    # ------------------------------------------------------------------
    def _befuelle_serverraum_k04(self):
        from raumbuch.models import Raum
        try:
            k04 = Raum.objects.get(raumnummer="K04")
        except Raum.DoesNotExist:
            self.stdout.write(self.style.WARNING("Raum K04 nicht gefunden – uebersprungen"))
            return None

        self._netz(
            k04,
            lan_ports_anzahl=96,
            lan_ports_beschreibung="2 x 48-Port Core-Switch | 10GbE Uplinks | Backbone",
            switch_name="SW-CORE",
            switch_port="alle",
            wlan_abdeckung="keine",
            ip_adressen="10.10.1.1 (SW-CORE) | 10.10.1.2 (Firewall) | 10.10.1.3 (Router)",
            vlan="VLAN 10 (Management)",
        )

        # 42 HE Rack – von oben nach unten
        komponenten = [
            # (bezeichnung, typ, rack_start, rack_u, ports_ges, ports_bel, ip, hersteller, modell, vlan, bemerkung)
            ("USV-CORE", "ups", 39, 4, None, None, "", "APC", "Smart-UPS 3000VA RM",
             "", "Absicherung gesamter Rack | Autonomie ca. 15 min"),
            ("PDU-A", "sonstiges", 38, 1, None, None, "", "APC", "Rack PDU 24-fach",
             "", "Stromverteilung Rack"),
            ("FW-01", "firewall", 36, 2, 8, 5, "10.10.1.2", "Fortinet", "FortiGate 200E",
             "VLAN 10", "UTM Firewall | Stateful | IPS | AV"),
            ("RTR-WAN", "router", 34, 2, 4, 2, "10.10.1.3", "Cisco", "ISR 4331",
             "VLAN 10", "WAN-Anbindung | DSL 1000/100 | LTE Backup"),
            ("SW-CORE", "core_switch", 32, 2, 52, 18, "10.10.1.1", "Cisco",
             "Catalyst 9300-48P PoE+", "VLAN 10", "Core Switch | 48x1GbE PoE+ | 4x10G SFP+ Uplinks"),
            ("LWL-CORE", "glasfaser_verteiler", 30, 1, 24, 14, "", "Telegaertner",
             "LWL-Patchfeld 24 x LC Duplex", "VLAN 10", "OM4 Faserverteilung Backbone Etagen"),
            ("KVM-01", "kvm", 29, 1, 8, 2, "10.10.1.10", "ATEN", "CS1716A 16-Port",
             "VLAN 10", "KVM ueber IP fuer Serverkonsolen"),
            ("SRV-01", "server", 25, 4, None, None, "10.10.1.20", "Dell",
             "PowerEdge R750 | 2x Xeon Gold | 256 GB RAM", "VLAN 10",
             "Primärserver | AD, DNS, DHCP | RAID 10 | 2x 960GB SSD"),
            ("SRV-02", "server", 21, 4, None, None, "10.10.1.21", "Dell",
             "PowerEdge R750 | 2x Xeon Gold | 256 GB RAM", "VLAN 10",
             "Sekundaerserver | Backup-DC | Virtualisierung | vSphere"),
            ("NAS-01", "nas", 17, 4, None, None, "10.10.1.30", "QNAP",
             "TS-h1290FX | 12x 10TB SAS | 100TB raw", "VLAN 10",
             "Netzwerkspeicher | Dateiserver | Backup-Ziel"),
            ("PP-UG-1", "patch_panel", 10, 1, 24, 18, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 20", "UG Raeume K01-K12"),
            ("PP-UG-2", "patch_panel", 9, 1, 24, 15, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 20", "UG Raeume K13-K24"),
            ("PP-EG-1", "patch_panel", 8, 1, 24, 22, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 30", "EG Raeume E01-E08"),
            ("PP-EG-2", "patch_panel", 7, 1, 24, 20, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 30", "EG Raeume E09-E15"),
        ]
        for komp in komponenten:
            bez, typ, rack_s, rack_u, p_ges, p_bel, ip, herst, modell, vlan, bem = komp
            self._komp(
                k04, bez,
                typ=typ,
                rack_einheit_start=rack_s,
                rack_einheiten=rack_u,
                ports_gesamt=p_ges,
                ports_belegt=p_bel,
                ip_adresse=ip,
                hersteller=herst,
                modell=modell,
                vlan=vlan,
                bemerkung=bem,
            )

        self.stdout.write(f"  Serverraum K04: {k04.netzwerk_komponenten.count()} Komponenten")
        return k04

    # ------------------------------------------------------------------
    # 4. IT-Verteiler K05 – Distribution-Schicht
    # ------------------------------------------------------------------
    def _befuelle_it_verteiler_k05(self):
        from raumbuch.models import Raum
        try:
            k05 = Raum.objects.get(raumnummer="K05")
        except Raum.DoesNotExist:
            self.stdout.write(self.style.WARNING("Raum K05 nicht gefunden – uebersprungen"))
            return None

        self._netz(
            k05,
            lan_ports_anzahl=0,
            lan_ports_beschreibung="Nur Backbone / keine Endgeraete",
            switch_name="SW-CORE",
            switch_port="Uplink",
            wlan_abdeckung="keine",
            ip_adressen="10.10.1.40-49 (Etagenswitches)",
            vlan="VLAN 10 (Management)",
        )

        # Etagenswitches + Patchfelder im K05-Rack (2x 42HE Schraenke)
        etagen_komponenten = [
            # Schrank 1: OG 1-4
            ("LWL-DIST", "glasfaser_verteiler", 42, 2, 48, 14, "",
             "Telegaertner", "LWL-Patchfeld 48 x LC Duplex", "VLAN 10",
             "Backbone Einspeisung von K04 | alle Etagen"),
            ("SW-DIST-UG", "distribution_switch", 40, 2, 52, 28, "10.10.1.40",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 20",
             "Distribution UG | 48x1GbE | 4xSFP+ 10G Uplink zu SW-CORE"),
            ("SW-EV-EG", "access_switch", 38, 2, 52, 32, "10.10.1.41",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 30",
             "Etagen-Switch EG | 48x1GbE | PoE+ fuer APs | Uplink via LWL"),
            ("SW-EV-OG1", "access_switch", 36, 2, 52, 28, "10.10.1.42",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 41",
             "Etagen-Switch 1. OG | 48x1GbE | Uplink via LWL OM4"),
            ("SW-EV-OG2", "access_switch", 34, 2, 52, 28, "10.10.1.43",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 42",
             "Etagen-Switch 2. OG | 48x1GbE | Uplink via LWL OM4"),
            ("SW-EV-OG3", "access_switch", 32, 2, 52, 28, "10.10.1.44",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 43",
             "Etagen-Switch 3. OG | 48x1GbE | Uplink via LWL OM4"),
            ("SW-EV-OG4", "access_switch", 30, 2, 52, 28, "10.10.1.45",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 44",
             "Etagen-Switch 4. OG | 48x1GbE | Uplink via LWL OM4"),
            ("SW-EV-OG5", "access_switch", 28, 2, 52, 28, "10.10.1.46",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 45",
             "Etagen-Switch 5. OG | 48x1GbE | Uplink via LWL OM4"),
            ("SW-EV-OG6", "access_switch", 26, 2, 52, 24, "10.10.1.47",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 46",
             "Etagen-Switch 6. OG | 48x1GbE | Uplink via LWL OM4"),
            ("SW-EV-OG7", "access_switch", 24, 2, 52, 24, "10.10.1.48",
             "HPE", "Aruba 2930F-48G PoE+", "VLAN 47",
             "Etagen-Switch 7. OG | 48x1GbE | Uplink via LWL OM4"),
            # Patchfelder OG 1-4
            ("PP-OG1-1", "patch_panel", 20, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 41", "1. OG Nord (A-Seite)"),
            ("PP-OG1-2", "patch_panel", 19, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 41", "1. OG Sued (B-Seite)"),
            ("PP-OG2-1", "patch_panel", 18, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 42", "2. OG Nord"),
            ("PP-OG2-2", "patch_panel", 17, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 42", "2. OG Sued"),
            ("PP-OG3-1", "patch_panel", 16, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 43", "3. OG Nord"),
            ("PP-OG3-2", "patch_panel", 15, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 43", "3. OG Sued"),
            ("PP-OG4-1", "patch_panel", 14, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 44", "4. OG Nord"),
            ("PP-OG4-2", "patch_panel", 13, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 44", "4. OG Sued"),
            # Patchfelder OG 5-7
            ("PP-OG5-1", "patch_panel", 12, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 45", "5. OG Nord"),
            ("PP-OG5-2", "patch_panel", 11, 1, 24, 24, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 45", "5. OG Sued"),
            ("PP-OG6-1", "patch_panel", 10, 1, 24, 22, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 46", "6. OG Nord"),
            ("PP-OG6-2", "patch_panel", 9, 1, 24, 22, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 46", "6. OG Sued"),
            ("PP-OG7-1", "patch_panel", 8, 1, 24, 20, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 47", "7. OG Nord"),
            ("PP-OG7-2", "patch_panel", 7, 1, 24, 20, "", "Telegaertner",
             "Patchfeld CAT7 24-Port", "VLAN 47", "7. OG Sued"),
            ("USV-DIST", "ups", 3, 4, None, None, "", "APC",
             "Smart-UPS 1500VA RM", "", "Absicherung Etagenswitches"),
        ]
        for komp in etagen_komponenten:
            bez, typ, rack_s, rack_u, p_ges, p_bel, ip, herst, modell, vlan, bem = komp
            self._komp(
                k05, bez,
                typ=typ,
                rack_einheit_start=rack_s,
                rack_einheiten=rack_u,
                ports_gesamt=p_ges,
                ports_belegt=p_bel,
                ip_adresse=ip,
                hersteller=herst,
                modell=modell,
                vlan=vlan,
                bemerkung=bem,
            )

        self.stdout.write(f"  IT-Verteiler K05: {k05.netzwerk_komponenten.count()} Komponenten")
        return k05

    # ------------------------------------------------------------------
    # 5. Glasfaserverbindungen: K04 -> K05, K05 -> virtuelle Etagenports
    # ------------------------------------------------------------------
    def _erstelle_glasfaserverbindungen(self, k04, k05):
        from raumbuch.models import Glasfaserverbindung

        verbindungen = [
            # (bezeichnung, von, nach, kabel, stecker, fasern, bw, laenge, bem)
            ("Backbone K04-K05", k04, k05, "om4", "mtp_12", 24, "10 GbE", 15,
             "Haupt-Backbone Core zu Distribution | OM4 Kassette 24F"),
            ("EV-EG Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 25,
             "Etagen-Uplink EG | EG liegt direkt ueber UG | SW-EV-EG Uplink"),
            ("EV-OG1 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 30,
             "Etagen-Uplink 1. OG | ca. 30m Steigtrasse"),
            ("EV-OG2 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 45,
             "Etagen-Uplink 2. OG | ca. 45m"),
            ("EV-OG3 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 60,
             "Etagen-Uplink 3. OG | ca. 60m"),
            ("EV-OG4 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 75,
             "Etagen-Uplink 4. OG | ca. 75m"),
            ("EV-OG5 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 90,
             "Etagen-Uplink 5. OG | ca. 90m"),
            ("EV-OG6 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 105,
             "Etagen-Uplink 6. OG | ca. 105m"),
            ("EV-OG7 Uplink", k05, k05, "om4", "lc_duplex", 2, "10 GbE", 120,
             "Etagen-Uplink 7. OG | ca. 120m"),
        ]

        erstellt = 0
        for bez, von, nach, kabel, stecker, fasern, bw, laenge, bem in verbindungen:
            _, created = Glasfaserverbindung.objects.get_or_create(
                bezeichnung=bez,
                defaults={
                    "von_raum": von,
                    "nach_raum": nach,
                    "kabel_typ": kabel,
                    "stecker_typ": stecker,
                    "fasern_anzahl": fasern,
                    "bandbreite": bw,
                    "laenge_m": laenge,
                    "bemerkung": bem,
                },
            )
            if created:
                erstellt += 1

        self.stdout.write(f"  Glasfaserverbindungen: {erstellt} neu angelegt")


# ---------------------------------------------------------------------------
# Hilfsfunktion: Patch-Port-Nummer aus Raumnummer ableiten
# ---------------------------------------------------------------------------
def _patch_port_fuer_raum(raumnummer: str) -> int:
    """Berechnet einen deterministischen Patch-Port-Offset aus der Raumnummer.

    Extraktion der numerischen Anteile und Modulo 24 (Ports pro Panel).
    Ergebnis: 1-24 (immer gueltiger Patch-Port).
    """
    import re
    ziffern = re.findall(r"\d+", raumnummer)
    if not ziffern:
        return 1
    wert = int("".join(ziffern)) % 24
    return wert + 1  # 1-basiert
