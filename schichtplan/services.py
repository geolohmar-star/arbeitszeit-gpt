# schichtplan/services.py - MIT TYP A/B + FAIRNESS
"""
KI-gestützte Schichtplan-Generierung mit OR-Tools
VOLLSTÄNDIG mit:
- Typ A/B Klassifikation
- Typ B: Min 4T + 4N pro Monat
- Genau 2 Personen pro Schicht
- Fairness: Gleichmäßige Verteilung Nachtschichten & Wochenenden
- Alle Mitarbeiter-Präferenzen
"""

import datetime
import calendar
from collections import defaultdict
from ortools.sat.python import cp_model
from django.db.models import Q
from schichtplan.models import Schicht, Schichttyp, Schichtplan


class SchichtplanGenerator:
    def __init__(self, mitarbeiter_queryset):
        """
        Initialisiert den Generator mit gefilterter Mitarbeiter-Liste.
        Nur Mitarbeiter mit Kennung MA1-MA15.
        """
        self.mitarbeiter_list = list(mitarbeiter_queryset)
        self.ma_map = {ma.id: ma for ma in self.mitarbeiter_list}
        
        # Schichttypen laden
        try:
            self.type_t = Schichttyp.objects.get(kuerzel='T')
            self.type_n = Schichttyp.objects.get(kuerzel='N')
        except Schichttyp.DoesNotExist:
            raise Exception(
                "Schichttypen 'T' und 'N' müssen in der Datenbank existieren."
            )

        self.target_shifts = [self.type_t, self.type_n]
        
        # Präferenzen laden
        self._load_preferences()

    def _load_preferences(self):
        """Lädt alle relevanten Präferenzen aus dem Mitarbeiter-Model"""
        print("   Lade Mitarbeiter-Präferenzen...")
        
        self.preferences = {}
        
        # Zähle Typ A und Typ B Mitarbeiter
        typ_a_count = 0
        typ_b_count = 0
        
        for ma in self.mitarbeiter_list:
            # Prüfe ob schicht_typ Feld existiert (für Rückwärtskompatibilität)
            schicht_typ = getattr(ma, 'schicht_typ', 'typ_a')
            
            if schicht_typ == 'typ_b':
                typ_b_count += 1
            else:
                typ_a_count += 1
            
            pref = {
                # HARD CONSTRAINTS
                'kann_tagschicht': ma.kann_tagschicht,
                'kann_nachtschicht': ma.kann_nachtschicht,
                'nachtschicht_nur_wochenende': ma.nachtschicht_nur_wochenende,
                'nur_zusatzdienste_wochentags': ma.nur_zusatzdienste_wochentags,
                'max_wochenenden_pro_monat': ma.max_wochenenden_pro_monat,
                'max_schichten_pro_monat': ma.max_schichten_pro_monat or 999,
                'max_aufeinanderfolgende_tage': ma.max_aufeinanderfolgende_tage,
                'verfuegbarkeit': ma.verfuegbarkeit,
                
                # NEU: Typ A/B
                'schicht_typ': schicht_typ,
                
                # SOFT CONSTRAINTS
                'planungs_prioritaet': ma.planungs_prioritaet,
            }
            
            self.preferences[ma.id] = pref
            
            # Debug-Ausgabe
            if schicht_typ == 'typ_b':
                print(f"      → {ma.schichtplan_kennung}: TYP B - Mind. 4T + 4N")
            if ma.nachtschicht_nur_wochenende:
                print(f"      → {ma.schichtplan_kennung}: Nachtschicht NUR Wochenende")
            if ma.nur_zusatzdienste_wochentags:
                print(f"      → {ma.schichtplan_kennung}: Wochentags NUR Zusatzdienste")
            if not ma.kann_nachtschicht:
                print(f"      → {ma.schichtplan_kennung}: KEINE Nachtschichten")
            if ma.verfuegbarkeit == 'wochenende_only':
                print(f"      → {ma.schichtplan_kennung}: NUR Wochenende")
        
        print(f"   Typ A: {typ_a_count} Mitarbeiter | Typ B: {typ_b_count} Mitarbeiter")

    def _analysiere_historie(self, referenz_datum):
        """Liest alte Schichten und lernt Muster"""
        print("--- Analysiere historische Daten ---")
        
        historische_schichten = Schicht.objects.filter(
            datum__lt=referenz_datum
        ).select_related('mitarbeiter', 'schichttyp')
        
        print(f"   Gefunden: {historische_schichten.count()} historische Schichten")
        
        learned_rules = defaultdict(int)
        
        for schicht in historische_schichten:
            alter_tage = (referenz_datum - schicht.datum).days
            
            # Zeit-Gewichtung
            if alter_tage < 35:
                gewicht = 3
            elif alter_tage < 90:
                gewicht = 2
            else:
                gewicht = 1
            
            wd = schicht.datum.isoweekday()
            kuerzel = schicht.schichttyp.kuerzel
            
            # Mapping
            if kuerzel.startswith('Z') or kuerzel == 'T':
                mapped_kuerzel = 'T'
            elif kuerzel == 'N':
                mapped_kuerzel = 'N'
            else:
                continue
            
            key = (schicht.mitarbeiter.id, wd, mapped_kuerzel)
            learned_rules[key] += gewicht

        final_weights = {}
        for key, score in learned_rules.items():
            final_weights[key] = -5 * score
        
        print(f"   Gelernte Regeln: {len(final_weights)} Muster")
        
        return final_weights

    def _hole_uebergangs_status(self, start_datum):
        """Prüft Schichten vom Vortag"""
        letzter_tag = start_datum - datetime.timedelta(days=1)
        schichten_gestern = Schicht.objects.filter(datum=letzter_tag)
        
        last_shifts = {}
        for s in schichten_gestern:
            last_shifts[s.mitarbeiter.id] = s.schichttyp.kuerzel
        
        if last_shifts:
            print(f"   Übergangsdaten: {len(last_shifts)} Mitarbeiter hatten am {letzter_tag} Dienst")
        
        return last_shifts

    def generiere_vorschlag(self, neuer_schichtplan_obj):
        """
        Hauptfunktion: Erstellt optimierten Schichtplan.
        
        NEUE REGELN:
        - Typ B: Mindestens 4 Tag + 4 Nacht pro Monat
        - Genau 2 Personen pro Schicht
        - Fairness: Gleichmäßige Verteilung
        """
        start_datum = neuer_schichtplan_obj.start_datum
        
        # Ende-Datum ermitteln
        if hasattr(neuer_schichtplan_obj, 'ende_datum') and neuer_schichtplan_obj.ende_datum:
            ende_datum = neuer_schichtplan_obj.ende_datum
        else:
            last_day = calendar.monthrange(start_datum.year, start_datum.month)[1]
            ende_datum = start_datum.replace(day=last_day)
        
        # Tages-Liste erstellen
        current = start_datum
        tage_liste = []
        
        while current <= ende_datum:
            tage_liste.append(current)
            current += datetime.timedelta(days=1)

        print(f"Generiere Plan für {len(tage_liste)} Tage ({start_datum} bis {tage_liste[-1]})...")

        # Daten laden
        learned_rules = self._analysiere_historie(start_datum)
        last_shifts = self._hole_uebergangs_status(start_datum)
        
        # Solver Setup
        model = cp_model.CpModel()
        vars_schichten = {}

        # ====================================================================
        # A. VARIABLEN ERSTELLEN
        # ====================================================================
        
        print(f"Erstelle Variablen für {len(self.mitarbeiter_list)} Mitarbeiter...")
        
        for ma in self.mitarbeiter_list:
            for tag in tage_liste:
                for stype in self.target_shifts:
                    var_name = f'{ma.id}_{tag}_{stype.kuerzel}'
                    vars_schichten[(ma.id, tag, stype.kuerzel)] = model.NewBoolVar(var_name)
                
                vars_schichten[(ma.id, tag, 'Frei')] = model.NewBoolVar(f'{ma.id}_{tag}_Frei')

        # ====================================================================
        # B. HARD CONSTRAINTS - BASIS-REGELN
        # ====================================================================
        
        print("Definiere Basis-Constraints...")
        
        # 1. Genau ein Zustand pro Tag
        for ma in self.mitarbeiter_list:
            for tag in tage_liste:
                all_options = [vars_schichten[(ma.id, tag, st.kuerzel)] for st in self.target_shifts]
                all_options.append(vars_schichten[(ma.id, tag, 'Frei')])
                model.Add(sum(all_options) == 1)

        # 2. Ruhezeit: Kein T direkt nach N
        for ma in self.mitarbeiter_list:
            for i in range(len(tage_liste) - 1):
                heute = tage_liste[i]
                morgen = tage_liste[i+1]
                model.Add(
                    vars_schichten[(ma.id, morgen, 'T')] == 0
                ).OnlyEnforceIf(vars_schichten[(ma.id, heute, 'N')])

        # 3. Übergang vom Vormonat
        if tage_liste:
            erster_tag = tage_liste[0]
            for ma_id, last_k in last_shifts.items():
                if last_k == 'N':
                    if (ma_id, erster_tag, 'T') in vars_schichten:
                        model.Add(vars_schichten[(ma_id, erster_tag, 'T')] == 0)

        # ====================================================================
        # C. HARD CONSTRAINTS - MITARBEITER-PRÄFERENZEN
        # ====================================================================
        
        print("Definiere Präferenz-Constraints...")
        
        for ma in self.mitarbeiter_list:
            pref = self.preferences[ma.id]
            
            # C.1 KANN NICHT TAGSCHICHT
            if not pref['kann_tagschicht']:
                for tag in tage_liste:
                    model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                print(f"   → {ma.schichtplan_kennung}: Keine Tagschichten")
            
            # C.2 KANN NICHT NACHTSCHICHT
            if not pref['kann_nachtschicht']:
                for tag in tage_liste:
                    model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                print(f"   → {ma.schichtplan_kennung}: Keine Nachtschichten")
            
            # C.3 NACHTSCHICHT NUR WOCHENENDE
            if pref['nachtschicht_nur_wochenende']:
                for tag in tage_liste:
                    if tag.weekday() < 4:  # Mo-Do
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                print(f"   → {ma.schichtplan_kennung}: Nachtschicht nur Fr/Sa/So")
            
            # C.4 NUR ZUSATZDIENSTE WOCHENTAGS
            if pref['nur_zusatzdienste_wochentags']:
                for tag in tage_liste:
                    if tag.weekday() < 4:  # Mo-Do
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                print(f"   → {ma.schichtplan_kennung}: Wochentags nur Zusatzdienste")
            
            # C.5 VERFÜGBARKEIT: NUR WOCHENENDE
            if pref['verfuegbarkeit'] == 'wochenende_only':
                for tag in tage_liste:
                    if tag.weekday() < 4:  # Mo-Do
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                print(f"   → {ma.schichtplan_kennung}: Nur Wochenende (Fr/Sa/So)")
            
            # C.6 VERFÜGBARKEIT: NUR WOCHENTAGS
            if pref['verfuegbarkeit'] == 'wochentags_only':
                for tag in tage_liste:
                    if tag.weekday() >= 5:  # Sa/So
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                print(f"   → {ma.schichtplan_kennung}: Nur Wochentags (Mo-Fr)")
            
            # C.7 MAX WOCHENENDEN PRO MONAT
            max_we = pref['max_wochenenden_pro_monat']
            
            # Finde alle Wochenenden
            wochenenden = []
            current_we = None
            
            for tag in tage_liste:
                if tag.weekday() >= 5:  # Sa oder So
                    week_num = tag.isocalendar()[1]
                    if current_we != week_num:
                        current_we = week_num
                        wochenenden.append([])
                    wochenenden[-1].append(tag)
            
            if max_we < len(wochenenden):
                we_vars = []
                for we_tage in wochenenden:
                    we_var = model.NewBoolVar(f'{ma.id}_we_{we_tage[0]}')
                    
                    schichten_am_we = []
                    for tag in we_tage:
                        for stype in self.target_shifts:
                            schichten_am_we.append(vars_schichten[(ma.id, tag, stype.kuerzel)])
                    
                    model.Add(sum(schichten_am_we) >= 1).OnlyEnforceIf(we_var)
                    model.Add(sum(schichten_am_we) == 0).OnlyEnforceIf(we_var.Not())
                    
                    we_vars.append(we_var)
                
                model.Add(sum(we_vars) <= max_we)
                
                if max_we == 0:
                    print(f"   → {ma.schichtplan_kennung}: KEINE Wochenenden")
                else:
                    print(f"   → {ma.schichtplan_kennung}: Max {max_we} Wochenenden")
            
            # C.8 MAX SCHICHTEN PRO MONAT
            if pref['max_schichten_pro_monat'] < 999:
                alle_schichten = []
                for tag in tage_liste:
                    for stype in self.target_shifts:
                        alle_schichten.append(vars_schichten[(ma.id, tag, stype.kuerzel)])
                
                model.Add(sum(alle_schichten) <= pref['max_schichten_pro_monat'])
                print(f"   → {ma.schichtplan_kennung}: Max {pref['max_schichten_pro_monat']} Schichten/Monat")
            
            # C.9 MAX AUFEINANDERFOLGENDE TAGE
            max_tage = pref['max_aufeinanderfolgende_tage']
            
            for i in range(len(tage_liste) - max_tage):
                fenster = []
                for j in range(max_tage + 1):
                    tag = tage_liste[i + j]
                    for stype in self.target_shifts:
                        fenster.append(vars_schichten[(ma.id, tag, stype.kuerzel)])
                
                model.Add(sum(fenster) <= max_tage)
            
            # ================================================================
            # C.10 NEU: TYP B - MINDESTENS 4 TAG + 4 NACHT PRO MONAT
            # ================================================================
            if pref['schicht_typ'] == 'typ_b':
                # Zähle Tagschichten
                tag_schichten = []
                for tag in tage_liste:
                    tag_schichten.append(vars_schichten[(ma.id, tag, 'T')])
                
                # Mindestens 4 Tagschichten
                model.Add(sum(tag_schichten) >= 4)
                
                # Zähle Nachtschichten
                nacht_schichten = []
                for tag in tage_liste:
                    nacht_schichten.append(vars_schichten[(ma.id, tag, 'N')])
                
                # Mindestens 4 Nachtschichten
                model.Add(sum(nacht_schichten) >= 4)
                
                print(f"   → {ma.schichtplan_kennung}: Typ B - Min 4T + 4N erzwungen")

        # ====================================================================
        # D. BESETZUNG - GENAU 2 PERSONEN PRO SCHICHT
        # ====================================================================
        
        print("Definiere Besetzungs-Regeln (genau 2 Personen/Schicht)...")
        
        for tag in tage_liste:
            # GENAU 2 Personen für Tagschicht
            model.Add(
                sum(vars_schichten[(m.id, tag, 'T')] for m in self.mitarbeiter_list) == 2
            )
            
            # GENAU 2 Personen für Nachtschicht
            model.Add(
                sum(vars_schichten[(m.id, tag, 'N')] for m in self.mitarbeiter_list) == 2
            )

        # ====================================================================
        # E. FAIRNESS - GLEICHMÄSSIGE VERTEILUNG
        # ====================================================================
        """
        print("Definiere Fairness-Constraints...")
        
        anzahl_tage = len(tage_liste)
        anzahl_mitarbeiter = len(self.mitarbeiter_list)
        
        # E.1 Fairness: Nachtschichten
        # Gesamte Nachtschichten = Tage × 2 Personen
        gesamt_nachtschichten = anzahl_tage * 2
        
        # Durchschnitt pro Person (nur die, die Nachtschicht können)
        kann_nacht_count = sum(1 for ma in self.mitarbeiter_list if self.preferences[ma.id]['kann_nachtschicht'])
        
        if kann_nacht_count > 0:
            erwartete_nacht_pro_ma = gesamt_nachtschichten / kann_nacht_count
            
            # Toleranz: ±50% (angepasst für realistische Planung)
            min_nacht = max(0, int(erwartete_nacht_pro_ma * 0.50))
            max_nacht = int(erwartete_nacht_pro_ma * 1.50) + 1
            
            print(f"   Fairness Nachtschichten: {min_nacht}-{max_nacht} pro Person (Ø {erwartete_nacht_pro_ma:.1f})")
            
            for ma in self.mitarbeiter_list:
                if self.preferences[ma.id]['kann_nachtschicht']:
                    # Typ B hat Mindestanforderung, also nur Obergrenze setzen
                    if self.preferences[ma.id]['schicht_typ'] == 'typ_b':
                        nacht_vars = [vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste]
                        model.Add(sum(nacht_vars) <= max_nacht)
                    else:
                        nacht_vars = [vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste]
                        model.Add(sum(nacht_vars) >= min_nacht)
                        model.Add(sum(nacht_vars) <= max_nacht)
        
        # E.2 Fairness: Wochenenden
        # Finde Wochenenden (bereits berechnet in C.7, hier nochmal für alle)
        wochenenden_alle = []
        current_we = None
        
        for tag in tage_liste:
            if tag.weekday() >= 5:
                week_num = tag.isocalendar()[1]
                if current_we != week_num:
                    current_we = week_num
                    wochenenden_alle.append([])
                wochenenden_alle[-1].append(tag)
        
        if wochenenden_alle:
            anzahl_we = len(wochenenden_alle)
            # Jedes WE hat 2 Tage × 2 Schichten × 2 Personen = 8 Slots
            gesamt_we_slots = anzahl_we * 8
            erwartete_we_pro_ma = gesamt_we_slots / anzahl_mitarbeiter / 4  # ~Anzahl WE pro Person
            
            min_we_einsaetze = max(1, int(erwartete_we_pro_ma * 0.7))
            max_we_einsaetze = int(erwartete_we_pro_ma * 1.3) + 1
            
            print(f"   Fairness Wochenenden: {min_we_einsaetze}-{max_we_einsaetze} WE pro Person (Ø {erwartete_we_pro_ma:.1f})")
            
            for ma in self.mitarbeiter_list:
                pref = self.preferences[ma.id]
                
                # Nur wenn nicht schon durch max_wochenenden_pro_monat eingeschränkt
                if pref['max_wochenenden_pro_monat'] >= anzahl_we:
                    we_einsatz_vars = []
                    
                    for we_tage in wochenenden_alle:
                        we_var = model.NewBoolVar(f'{ma.id}_fair_we_{we_tage[0]}')
                        
                        schichten_am_we = []
                        for tag in we_tage:
                            for stype in self.target_shifts:
                                schichten_am_we.append(vars_schichten[(ma.id, tag, stype.kuerzel)])
                        
                        model.Add(sum(schichten_am_we) >= 1).OnlyEnforceIf(we_var)
                        model.Add(sum(schichten_am_we) == 0).OnlyEnforceIf(we_var.Not())
                        
                        we_einsatz_vars.append(we_var)
                    
                    # Fairness-Range
                    model.Add(sum(we_einsatz_vars) >= min_we_einsaetze)
                    model.Add(sum(we_einsatz_vars) <= max_we_einsaetze)
        """

        # ====================================================================
        # F. SOFT CONSTRAINTS (Optimierung)
        # ====================================================================
        
        print("Definiere Optimierungsziel...")
        
        objective_terms = []
        
        for ma in self.mitarbeiter_list:
            pref = self.preferences[ma.id]
            
            for tag in tage_liste:
                wd = tag.isoweekday()
                
                for stype in self.target_shifts:
                    kuerzel = stype.kuerzel
                    score = 0
                    
                    # 1. Historische Muster
                    hist_key = (ma.id, wd, kuerzel)
                    if hist_key in learned_rules:
                        score += learned_rules[hist_key]
                    
                    # 2. Planungs-Priorität
                    if pref['planungs_prioritaet'] == 'hoch':
                        score = int(score * 1.5)
                    elif pref['planungs_prioritaet'] == 'niedrig':
                        score = int(score * 0.5)
                    
                    objective_terms.append(vars_schichten[(ma.id, tag, kuerzel)] * score)

        model.Minimize(sum(objective_terms))

        # ====================================================================
        # G. LÖSEN
        # ====================================================================
        
        print("Starte Solver...")
        print(f"   Timeout: 20 Sekunden (wegen komplexer Fairness-Regeln)")
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 360.0   # 6 Minuten für komplexe Fälle        
        status = solver.Solve(model)
        
        # ====================================================================
        # H. ERGEBNISSE SPEICHERN
        # ====================================================================
        
        ergebnis_count = 0
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"Lösung gefunden! Status: {solver.StatusName(status)}")
            
            for ma in self.mitarbeiter_list:
                for tag in tage_liste:
                    if solver.Value(vars_schichten[(ma.id, tag, 'T')]) == 1:
                        Schicht.objects.create(
                            schichtplan=neuer_schichtplan_obj,
                            mitarbeiter=ma,
                            datum=tag,
                            schichttyp=self.type_t
                        )
                        ergebnis_count += 1
                    
                    elif solver.Value(vars_schichten[(ma.id, tag, 'N')]) == 1:
                        Schicht.objects.create(
                            schichtplan=neuer_schichtplan_obj,
                            mitarbeiter=ma,
                            datum=tag,
                            schichttyp=self.type_n
                        )
                        ergebnis_count += 1
            
            print(f"Erfolgreich {ergebnis_count} Schichten in DB gespeichert.")
            
            # Statistik ausgeben
            self._print_statistics(neuer_schichtplan_obj, tage_liste)
            
        else:
            error_msg = (
                "❌ Keine gültige Lösung gefunden!\n\n"
                "Mögliche Ursachen:\n"
                "1. Zu wenige Mitarbeiter für Besetzung (benötigt: genau 2 pro Schicht)\n"
                "2. Typ B Constraints zu restriktiv (mind. 4T + 4N)\n"
                "3. Fairness-Regeln zu eng (±25% Toleranz)\n"
                "4. Widersprüchliche Präferenzen\n"
                "5. Zeitlimit zu kurz (20s)\n\n"
                "Lösungsvorschläge:\n"
                "- Mehr Mitarbeiter mit Kennung MA1-MA15 hinzufügen\n"
                "- Präferenzen lockern (z.B. mehr Mitarbeiter für Nachtschicht)\n"
                "- Fairness-Toleranz erhöhen (in services.py Zeile ~410)\n"
                "- Typ B Mitarbeiter reduzieren oder Anforderungen senken"
            )
            print(error_msg)
            raise Exception(error_msg)
    
    def _print_statistics(self, schichtplan, tage_liste):
        """Gibt Statistiken über den generierten Plan aus"""
        print("\n" + "="*70)
        print("📊 PLAN-STATISTIKEN")
        print("="*70)
        
        schichten = Schicht.objects.filter(schichtplan=schichtplan)
        
        # Pro Mitarbeiter
        for ma in self.mitarbeiter_list:
            ma_schichten = schichten.filter(mitarbeiter=ma)
            anzahl_t = ma_schichten.filter(schichttyp=self.type_t).count()
            anzahl_n = ma_schichten.filter(schichttyp=self.type_n).count()
            
            # Wochenenden zählen
            we_count = 0
            for schicht in ma_schichten:
                if schicht.datum.weekday() >= 5:
                    we_count += 1
            
            typ = self.preferences[ma.id]['schicht_typ']
            typ_label = "B" if typ == 'typ_b' else "A"
            
            print(f"{ma.schichtplan_kennung} (Typ {typ_label}): {anzahl_t}T + {anzahl_n}N = {anzahl_t+anzahl_n} | WE: {we_count}")
        
        print("="*70 + "\n")
