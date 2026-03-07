"""Management Command: Generiert eine SVG-Gebaeudeuebersicht aus der Raumbuch-DB.

Erzeugt ein Schnittbild-Schaubild mit allen Etagen und Raeumen,
farbkodiert nach Raumtyp.

Ausgabe: docs/gebaeude_plan.svg
"""
import os

from django.core.management.base import BaseCommand


FARBEN = {
    "einzelbuero":       "#3B82F6",   # Blau
    "konferenz":         "#F59E0B",   # Amber
    "besprechung":       "#FCD34D",   # Gelb
    "schulung":          "#F97316",   # Orange
    "teekueche":         "#10B981",   # Gruen
    "pausenraum":        "#34D399",   # Hellgruen
    "wc_herren":         "#94A3B8",   # Grau
    "wc_damen":          "#CBD5E1",   # Hellgrau
    "wc_barrierefrei":   "#E2E8F0",   # Sehr hell
    "druckerraum":       "#8B5CF6",   # Violett
    "eingang":           "#FEF3C7",   # Cremeweis
    "windfang":          "#FEF9C3",   # Hellgelb
    "flur":              "#E5E7EB",   # Grau
    "heizungsraum":      "#EF4444",   # Rot
    "lueftungsraum":     "#F87171",   # Hellrot
    "elektroverteilung": "#DC2626",   # Dunkelrot
    "serverraum":        "#B91C1C",   # Tiefrot
    "it_verteiler":      "#991B1B",   # Sehr dunkelrot
    "lager":             "#D97706",   # Braun-Amber
    "archiv":            "#B45309",   # Dunkelbraun
    "abstellraum":       "#92400E",   # Tief braun
    "putzraum":          "#78350F",   # Sehr dunkel
}

FARBE_FALLBACK = "#9CA3AF"


class Command(BaseCommand):
    help = "Generiert docs/gebaeude_plan.svg aus der Raumbuch-Datenbank"

    def handle(self, *args, **options):
        from raumbuch.models import Gebaeude, Geschoss, Raum

        gebaeude_liste = list(Gebaeude.objects.prefetch_related(
            "geschosse"
        ).order_by("pk"))

        # --- Layout-Konstanten ---
        BREITE_GESAMT = 1300
        ETAGEN_HOEHE = 58
        LABEL_BREITE = 130
        ABSTAND = 30          # zwischen Gebaeuden
        KOPF_HOEHE = 80
        LEGENDE_HOEHE = 120
        RAND = 20

        # Nutzbare Breite pro Gebaeude aufteilen
        anz_gebaeude = len(gebaeude_liste)
        nutzbreite = BREITE_GESAMT - 2 * RAND - LABEL_BREITE - (anz_gebaeude - 1) * ABSTAND
        gebaeude_breiten = []
        # Hauptgebaeude bekommt 70%, Rest verteilt sich
        if anz_gebaeude == 2:
            gebaeude_breiten = [int(nutzbreite * 0.70), int(nutzbreite * 0.30)]
        else:
            anteil = nutzbreite // anz_gebaeude
            gebaeude_breiten = [anteil] * anz_gebaeude

        # Hoechste Etagen-Anzahl bestimmen fuer Gesamthoehe
        max_etagen = max(
            g.geschosse.count() for g in gebaeude_liste
        )
        hoehe_gesamt = (
            KOPF_HOEHE + max_etagen * ETAGEN_HOEHE + LEGENDE_HOEHE + 2 * RAND
        )

        # --- SVG aufbauen ---
        linien = []
        linien.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{BREITE_GESAMT}" height="{hoehe_gesamt}" '
            f'viewBox="0 0 {BREITE_GESAMT} {hoehe_gesamt}" '
            f'font-family="Arial, Helvetica, sans-serif">'
        )

        # Hintergrund
        linien.append(
            f'<rect width="{BREITE_GESAMT}" height="{hoehe_gesamt}" '
            f'fill="#F8FAFC" rx="8"/>'
        )

        # Titel
        linien.append(
            f'<text x="{BREITE_GESAMT // 2}" y="35" '
            f'text-anchor="middle" font-size="20" font-weight="bold" fill="#1E293B">'
            f'Gebaeudeuebersicht – Raumbuch</text>'
        )

        # --- Jedes Gebaeude zeichnen ---
        x_start = RAND + LABEL_BREITE
        for g_idx, gebaeude in enumerate(gebaeude_liste):
            gb_breite = gebaeude_breiten[g_idx]
            geschosse = list(
                gebaeude.geschosse.all().order_by("-reihenfolge")
            )  # Oberste Etage zuerst

            # Gebaeude-Bezeichnung
            label_x = x_start + gb_breite // 2
            linien.append(
                f'<text x="{label_x}" y="62" text-anchor="middle" '
                f'font-size="13" font-weight="bold" fill="#475569">'
                f'{gebaeude.bezeichnung} ({gebaeude.kuerzel})</text>'
            )

            for e_idx, geschoss in enumerate(geschosse):
                y_top = KOPF_HOEHE + e_idx * ETAGEN_HOEHE

                # Etagen-Bezeichnung (nur beim ersten Gebaeude)
                if g_idx == 0:
                    linien.append(
                        f'<rect x="{RAND}" y="{y_top}" '
                        f'width="{LABEL_BREITE - 4}" height="{ETAGEN_HOEHE - 2}" '
                        f'fill="#1E293B" rx="3"/>'
                    )
                    linien.append(
                        f'<text x="{RAND + LABEL_BREITE // 2 - 2}" '
                        f'y="{y_top + ETAGEN_HOEHE // 2 + 1}" '
                        f'text-anchor="middle" dominant-baseline="middle" '
                        f'font-size="11" font-weight="bold" fill="white">'
                        f'{geschoss.kuerzel}</text>'
                    )
                    linien.append(
                        f'<text x="{RAND + LABEL_BREITE // 2 - 2}" '
                        f'y="{y_top + ETAGEN_HOEHE // 2 + 13}" '
                        f'text-anchor="middle" '
                        f'font-size="9" fill="#94A3B8">'
                        f'{geschoss.bezeichnung[:16]}</text>'
                    )

                # Raeume dieser Etage
                raeume = list(
                    Raum.objects.filter(geschoss=geschoss).order_by("raumnummer")
                )
                if not raeume:
                    continue

                raum_breite = gb_breite / len(raeume)

                for r_idx, raum in enumerate(raeume):
                    rx = x_start + r_idx * raum_breite
                    ry = y_top + 1
                    rw = raum_breite - 1
                    rh = ETAGEN_HOEHE - 3
                    farbe = FARBEN.get(raum.raumtyp, FARBE_FALLBACK)

                    # Raum-Rechteck
                    linien.append(
                        f'<rect x="{rx:.1f}" y="{ry}" '
                        f'width="{rw:.1f}" height="{rh}" '
                        f'fill="{farbe}" stroke="white" stroke-width="1" rx="2">'
                        f'<title>{raum.raumnummer} – {raum.raumname} ({raum.raumtyp})</title>'
                        f'</rect>'
                    )

                    # Raumnummer (wenn breit genug)
                    if rw >= 28:
                        mitte_x = rx + rw / 2
                        linien.append(
                            f'<text x="{mitte_x:.1f}" y="{ry + rh / 2 - 4:.1f}" '
                            f'text-anchor="middle" dominant-baseline="middle" '
                            f'font-size="8" font-weight="bold" fill="white" '
                            f'paint-order="stroke" stroke="#0000003A" stroke-width="2">'
                            f'{raum.raumnummer}</text>'
                        )
                        # Raumtyp-Kuerzel
                        typ_kurz = raum.raumtyp[:4] if raum.raumtyp else ""
                        linien.append(
                            f'<text x="{mitte_x:.1f}" y="{ry + rh / 2 + 7:.1f}" '
                            f'text-anchor="middle" dominant-baseline="middle" '
                            f'font-size="7" fill="white" opacity="0.85">'
                            f'{typ_kurz}</text>'
                        )

            x_start += gb_breite + ABSTAND

        # --- Legende ---
        ley = KOPF_HOEHE + max_etagen * ETAGEN_HOEHE + 15
        linien.append(
            f'<text x="{RAND}" y="{ley + 14}" '
            f'font-size="12" font-weight="bold" fill="#475569">Legende:</text>'
        )
        legende_eintraege = [
            ("Einzelbuero",       FARBEN["einzelbuero"]),
            ("Konferenz / Besprechung", FARBEN["konferenz"]),
            ("Schulung",          FARBEN["schulung"]),
            ("Teekueche / Pause", FARBEN["teekueche"]),
            ("WC / Sanitaer",     FARBEN["wc_herren"]),
            ("Technik / Server",  FARBEN["serverraum"]),
            ("Lager / Archiv",    FARBEN["lager"]),
            ("Eingang / Flur",    FARBEN["eingang"]),
            ("Drucker / Kopie",   FARBEN["druckerraum"]),
        ]
        spalten = 3
        eintraege_pro_spalte = (len(legende_eintraege) + spalten - 1) // spalten
        spalte_breite = (BREITE_GESAMT - 2 * RAND) // spalten

        for i, (label, farbe) in enumerate(legende_eintraege):
            spalte = i // eintraege_pro_spalte
            zeile = i % eintraege_pro_spalte
            lx = RAND + spalte * spalte_breite
            ly = ley + 25 + zeile * 20
            linien.append(
                f'<rect x="{lx}" y="{ly}" width="14" height="14" '
                f'fill="{farbe}" rx="2"/>'
            )
            linien.append(
                f'<text x="{lx + 20}" y="{ly + 11}" '
                f'font-size="11" fill="#334155">{label}</text>'
            )

        # Fusszeile
        linien.append(
            f'<text x="{BREITE_GESAMT - RAND}" y="{hoehe_gesamt - 8}" '
            f'text-anchor="end" font-size="9" fill="#94A3B8">'
            f'Generiert aus Raumbuch-Datenbank</text>'
        )

        linien.append("</svg>")

        # --- Speichern ---
        os.makedirs("docs", exist_ok=True)
        pfad = os.path.join("docs", "gebaeude_plan.svg")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("\n".join(linien))

        self.stdout.write(self.style.SUCCESS(f"SVG gespeichert: {pfad}"))
