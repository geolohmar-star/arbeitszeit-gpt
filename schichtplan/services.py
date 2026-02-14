# schichtplan/services.py - MIT WUNSCH-INTEGRATION + SOLL-STUNDEN-VERRECHNUNG
"""
KI-gestützte Schichtplan-Generierung mit OR-Tools

VOLLSTÄNDIG mit:
- Typ A/B Klassifikation
- Typ B: Min 4T + 4N pro Monat
- Genau 2 Personen pro Schicht
- Fairness: Gleichmäßige Verteilung
- TODO: Quartals-Check fuer Fairness (fruehzeitig korrigieren)
- WUNSCH-INTEGRATION (Urlaub, Präferenzen)
- SOLL-STUNDEN-VERRECHNUNG (jeder arbeitet ca. gleich viel)
- AUTOMATISCHE ZUSATZDIENSTE zum Auffüllen
- INDIVIDUELLE VEREINBARUNGEN (erlaubte Tage, keine Zusatzdienste)
"""

import json
import datetime
import calendar
from collections import defaultdict
from decimal import Decimal
from datetime import date, timedelta
from ortools.sat.python import cp_model

from django.db.models import Q

from schichtplan.models import Schicht, Schichttyp, Schichtplan, Schichtwunsch
from arbeitszeit.models import MonatlicheArbeitszeitSoll


class SchichtplanGenerator:
    def __init__(self, mitarbeiter_queryset, schichtplan_obj=None):
        self.mitarbeiter_list = list(mitarbeiter_queryset)
        self.ma_map = {ma.id: ma for ma in self.mitarbeiter_list}
        self.schichtplan_obj = schichtplan_obj  # Wird später gespeichert für Config-FK

        # === NEU: Konfiguration laden ===
        from schichtplan.models import SchichtplanKonfiguration
        self.config = SchichtplanKonfiguration.get_aktuelle()
        print(f"   [CONFIG] Lade Konfiguration v{self.config.version_nummer} (Config-ID: {self.config.id})")

        try:
            self.type_t = Schichttyp.objects.get(kuerzel='T')
            self.type_n = Schichttyp.objects.get(kuerzel='N')
            try:
                self.type_z = Schichttyp.objects.get(kuerzel='Z')
            except Schichttyp.DoesNotExist:
                self.type_z = None
                print("   [WARN] Schichttyp 'Z' nicht gefunden")
        except Schichttyp.DoesNotExist:
            raise Exception("Schichttypen 'T' und 'N' müssen existieren.")

        self.target_shifts = [self.type_t, self.type_n]
        self._load_preferences()

    # ======================================================================
    # PRÄFERENZEN LADEN
    # ======================================================================
    def _load_preferences(self):
        """Lädt alle relevanten Präferenzen und erzwingt korrekte Datentypen"""
        print("   Lade Mitarbeiter-Präferenzen...")
        
        self.preferences = {}
        
        for ma in self.mitarbeiter_list:
            schicht_typ = getattr(ma, 'schicht_typ', 'typ_a')
            
            # --- 1. Wochentage säubern -> IMMER eine Liste von Ints ---
            raw_tage = getattr(ma, 'erlaubte_wochentage', None)
            clean_tage = []
            
            if raw_tage is not None:
                if isinstance(raw_tage, str):
                    try:
                        loaded = json.loads(raw_tage)
                        if isinstance(loaded, list):
                            clean_tage = [int(t) for t in loaded]
                        elif isinstance(loaded, (int, float)):
                            clean_tage = [int(loaded)]
                    except (json.JSONDecodeError, ValueError):
                        if raw_tage.strip().isdigit():
                            clean_tage = [int(raw_tage.strip())]
                elif isinstance(raw_tage, list):
                    clean_tage = [int(t) for t in raw_tage]
                elif isinstance(raw_tage, (int, float)):
                    clean_tage = [int(raw_tage)]
            
            # --- 2. Fixe Tagdienst-Wochentage (NEU aus Analyse) ---
            raw_fixe_tage = getattr(ma, 'fixe_tag_wochentage', None)
            fixe_tage = []
            
            if raw_fixe_tage is not None:
                if isinstance(raw_fixe_tage, str):
                    try:
                        loaded = json.loads(raw_fixe_tage)
                        if isinstance(loaded, list):
                            fixe_tage = [int(t) for t in loaded]
                    except (json.JSONDecodeError, ValueError):
                        pass
                elif isinstance(raw_fixe_tage, list):
                    fixe_tage = [int(t) for t in raw_fixe_tage]
            
            # --- 3. Keine Zusatzdienste Flag ---
            keine_z = bool(getattr(ma, 'keine_zusatzdienste', False))

            # --- 4. NEU: MA7 bekommt automatisch wochenend_nachtdienst_block=True ---
            wochenend_block = getattr(ma, 'wochenend_nachtdienst_block', False)
            if ma.schichtplan_kennung == 'MA7':
                wochenend_block = True

            pref = {
                'kann_tagschicht': ma.kann_tagschicht,
                'kann_nachtschicht': ma.kann_nachtschicht,
                'nachtschicht_nur_wochenende': ma.nachtschicht_nur_wochenende,
                'nur_zusatzdienste_wochentags': ma.nur_zusatzdienste_wochentags,
                'max_wochenenden_pro_monat': ma.max_wochenenden_pro_monat,
                'max_schichten_pro_monat': ma.max_schichten_pro_monat or 999,
                'max_aufeinanderfolgende_tage': ma.max_aufeinanderfolgende_tage,
                'verfuegbarkeit': ma.verfuegbarkeit,
                'schicht_typ': schicht_typ,
                'planungs_prioritaet': ma.planungs_prioritaet,
                'erlaubte_wochentage': clean_tage,       # immer Liste
                'keine_zusatzdienste': keine_z,          # immer bool
                # === NEUE FELDER AUS ANALYSE ===
                'kategorie': getattr(ma, 'kategorie', 'kern'),
                'zaehlt_zur_tagbesetzung': getattr(ma, 'zaehlt_zur_tagbesetzung', True),
                'zaehlt_zur_nachtbesetzung': getattr(ma, 'zaehlt_zur_nachtbesetzung', True),
                'fixe_tag_wochentage': fixe_tage,        # immer Liste
                'wochenend_nachtdienst_block': wochenend_block,  # NEU: Jetzt echtes Constraint!
                'min_tagschichten_pro_monat': getattr(ma, 'min_tagschichten_pro_monat', None),
                'min_nachtschichten_pro_monat': getattr(ma, 'min_nachtschichten_pro_monat', None),
                'target_tagschichten_pro_monat': getattr(ma, 'target_tagschichten_pro_monat', 6),
                'target_nachtschichten_pro_monat': getattr(ma, 'target_nachtschichten_pro_monat', 5),
            }
            
            self.preferences[ma.id] = pref
            
            # Debug-Ausgabe
            debug_infos = []
            tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']
            
            # Kategorie
            if pref['kategorie'] != 'kern':
                debug_infos.append(f"{pref['kategorie'].upper()}")
            
            # Fixe Tage (WICHTIGER als erlaubte Tage)
            if fixe_tage:
                debug_infos.append(f"FIXE {','.join(tage_namen[t] for t in fixe_tage if 0 <= t <= 6)}")
            elif clean_tage:
                debug_infos.append(f"NUR {','.join(tage_namen[t] for t in clean_tage if 0 <= t <= 6)}")
            
            # Besetzung
            if not pref['zaehlt_zur_tagbesetzung']:
                debug_infos.append("T=ZUSÄTZLICH")
            if not pref['zaehlt_zur_nachtbesetzung']:
                debug_infos.append("N=NICHT")
            
            # Wochenend-Block
            if pref['wochenend_nachtdienst_block']:
                debug_infos.append("WE-BLOCK")
            
            # Min-Schichten
            if pref['min_tagschichten_pro_monat']:
                debug_infos.append(f"min {pref['min_tagschichten_pro_monat']}T")
            if pref['min_nachtschichten_pro_monat']:
                debug_infos.append(f"min {pref['min_nachtschichten_pro_monat']}N")
            
            if keine_z:
                debug_infos.append("KEINE Z-Dienste")
            
            if debug_infos:
                print(f"      -> {ma.schichtplan_kennung}: {', '.join(debug_infos)}")

    # ======================================================================
    # SOLL-STUNDEN LADEN
    # ======================================================================
    def _load_soll_stunden(self, jahr, monat):
        print("\n[STATS] Lade Soll-Stunden...")
        soll_stunden_map = {}
        soll_schichten_map = {}
        
        avg_tag_stunden = float(self.type_t.arbeitszeit_stunden)
        avg_nacht_stunden = float(self.type_n.arbeitszeit_stunden)
        avg_schicht_stunden = (avg_tag_stunden + avg_nacht_stunden) / 2
        
        print(f"   Schichtlängen: T={avg_tag_stunden}h, N={avg_nacht_stunden}h")
        print(f"   O Schichtlänge: {avg_schicht_stunden:.1f}h")
        
        for ma in self.mitarbeiter_list:
            soll_obj = MonatlicheArbeitszeitSoll.objects.filter(
                mitarbeiter=ma, jahr=jahr, monat=monat
            ).first()
            
            if soll_obj:
                soll_stunden = float(soll_obj.soll_stunden)
            else:
                soll_stunden = 144.0
                print(f"      {ma.schichtplan_kennung}: Fallback {soll_stunden}h (kein MonatlicheArbeitszeitSoll)")
            
            soll_schichten = soll_stunden / avg_schicht_stunden
            soll_stunden_map[ma.id] = soll_stunden
            soll_schichten_map[ma.id] = round(soll_schichten)
            print(f"      {ma.schichtplan_kennung}: {soll_stunden:.1f}h / {avg_schicht_stunden:.1f}h = {round(soll_schichten)} Schichten")
        
        return soll_stunden_map, soll_schichten_map

    # ======================================================================
    # KUMULATIVE T/N/Z/WE AUS VERÖFFENTLICHTEN PLÄNEN (Stand zur Genehmigung)
    # ======================================================================
    def _load_cumulative_veroeffentlicht(self, jahr, vor_monat_inklusive):
        """
        Lädt die kumulativen Schichtzahlen pro MA aus allen veröffentlichten
        Plänen des Jahres bis einschl. vor_monat_inklusive.
        Stand = nur status 'veroeffentlicht' (was der Schichtplaner freigegeben hat).
        """
        ma_ids = {ma.id for ma in self.mitarbeiter_list}
        cumulative = {ma.id: {'t': 0, 'n': 0, 'z': 0, 'we': 0} for ma in self.mitarbeiter_list}
        if vor_monat_inklusive < 1:
            return cumulative
        start_year = date(jahr, 1, 1)
        last_day = calendar.monthrange(jahr, vor_monat_inklusive)[1]
        end_prev = date(jahr, vor_monat_inklusive, last_day)
        plaene = Schichtplan.objects.filter(
            status='veroeffentlicht',
            start_datum__lte=end_prev,
            ende_datum__gte=start_year
        )
        schichten = Schicht.objects.filter(
            schichtplan__in=plaene,
            datum__gte=start_year,
            datum__lte=end_prev,
            mitarbeiter_id__in=ma_ids
        ).select_related('schichttyp')
        for s in schichten:
            if s.mitarbeiter_id not in cumulative:
                continue
            k = s.schichttyp.kuerzel
            if k == 'T':
                cumulative[s.mitarbeiter_id]['t'] += 1
            elif k == 'N':
                cumulative[s.mitarbeiter_id]['n'] += 1
            elif k == 'Z':
                cumulative[s.mitarbeiter_id]['z'] += 1
            if s.datum.weekday() >= 5:
                cumulative[s.mitarbeiter_id]['we'] += 1
        return cumulative

    # ======================================================================
    # HAUPTFUNKTION
    # ======================================================================
    def generiere_vorschlag(self, neuer_schichtplan_obj):
        start_datum = neuer_schichtplan_obj.start_datum
        
        if hasattr(neuer_schichtplan_obj, 'ende_datum') and neuer_schichtplan_obj.ende_datum:
            ende_datum = neuer_schichtplan_obj.ende_datum
        else:
            last_day = calendar.monthrange(start_datum.year, start_datum.month)[1]
            ende_datum = start_datum.replace(day=last_day)
        
        current = start_datum
        tage_liste = []
        while current <= ende_datum:
            tage_liste.append(current)
            current += datetime.timedelta(days=1)

        print(f"\n{'='*70}")
        print(f"[START] GENERIERE PLAN: {len(tage_liste)} Tage ({start_datum} bis {tage_liste[-1]})")
        print(f"{'='*70}\n")

        # ====================================================================
        # WÜNSCHE LADEN (nur aus der zugehoerigen Wunschperiode)
        # ====================================================================
        print("[LOAD] Lade Schichtwuensche...")

        wunsch_filter = {
            'datum__gte': start_datum,
            'datum__lte': ende_datum,
            'mitarbeiter__in': self.mitarbeiter_list,
        }
        # Nur Wuensche der zugehoerigen Periode laden (keine verwaisten)
        if hasattr(neuer_schichtplan_obj, 'wunschperiode') and neuer_schichtplan_obj.wunschperiode:
            wunsch_filter['periode'] = neuer_schichtplan_obj.wunschperiode
            print(f"   Periode: {neuer_schichtplan_obj.wunschperiode.name}")
        else:
            # Fallback: nur Wuensche MIT Periode laden
            wunsch_filter['periode__isnull'] = False
            print("   [WARN] Keine Wunschperiode am Plan - lade alle Wuensche mit Periode")

        wuensche = Schichtwunsch.objects.filter(
            **wunsch_filter
        ).select_related('mitarbeiter')

        print(f"   Zeitraum: {start_datum} bis {ende_datum}")
        print(f"   Gefunden: {wuensche.count()} Wünsche")

        wuensche_matrix = defaultdict(dict)
        urlaubs_tage = defaultdict(list)

        for w in wuensche:
            wuensche_matrix[w.mitarbeiter.id][w.datum] = w
            print(f"      -> {w.mitarbeiter.schichtplan_kennung}: {w.wunsch} am {w.datum}")
            if w.wunsch in ['urlaub', 'krank']:
                urlaubs_tage[w.mitarbeiter.id].append(w.datum)
            elif w.wunsch == 'gar_nichts' and w.genehmigt:
                urlaubs_tage[w.mitarbeiter.id].append(w.datum)

        # Bevorzugung: Wer wenige Wünsche geäußert hat, wird bei der Planung bevorzugt
        wunsch_anzahl_pro_ma = {ma.id: len(wuensche_matrix.get(ma.id, {})) for ma in self.mitarbeiter_list}
        wunsch_bonus = {}
        for ma in self.mitarbeiter_list:
            n = wunsch_anzahl_pro_ma.get(ma.id, 0)
            if n == 0:
                wunsch_bonus[ma.id] = self.config.wunsch_bonus_keine   # Keine Wünsche -> stärkste Bevorzugung
            elif n <= self.config.wunsch_bonus_threshold_wenige:
                wunsch_bonus[ma.id] = self.config.wunsch_bonus_wenige   # Wenige Angaben -> bevorzugt
            elif n <= self.config.wunsch_bonus_threshold_mittel:
                wunsch_bonus[ma.id] = self.config.wunsch_bonus_mittel   # Mittlere Beteiligung -> leicht bevorzugt
            else:
                wunsch_bonus[ma.id] = 0      # Viele Wünsche -> keine Extra-Bevorzugung
        for ma in self.mitarbeiter_list:
            b = wunsch_bonus.get(ma.id, 0)
            if b > 0:
                print(f"   [STATS] {ma.schichtplan_kennung}: {wunsch_anzahl_pro_ma.get(ma.id, 0)} Wunschtage -> Bevorzugung +{b}")

        # ====================================================================
        # SOLL-STUNDEN LADEN
        # ====================================================================
        jahr = start_datum.year
        monat = start_datum.month
        soll_stunden_map, soll_schichten_map = self._load_soll_stunden(jahr, monat)

        # ====================================================================
        # KUMULATIVE T/N/Z/WE (nur veröffentlichte Pläne = Stand zur Genehmigung)
        # ====================================================================
        cumulative = self._load_cumulative_veroeffentlicht(jahr, monat - 1)
        cumulative_t = {ma_id: cumulative[ma_id]['t'] for ma_id in cumulative}
        cumulative_n = {ma_id: cumulative[ma_id]['n'] for ma_id in cumulative}
        cumulative_we = {ma_id: cumulative[ma_id]['we'] for ma_id in cumulative}
        if any(cumulative[ma.id]['t'] or cumulative[ma.id]['n'] or cumulative[ma.id]['we'] for ma in self.mitarbeiter_list):
            print("\n[DATE] Jahressummen-Stand (veröffentlichte Pläne bis vorheriger Monat):")
            for ma in self.mitarbeiter_list:
                c = cumulative[ma.id]
                if c['t'] or c['n'] or c['z'] or c['we']:
                    print(f"   {ma.schichtplan_kennung}: T={c['t']} N={c['n']} Z={c['z']} WE={c['we']}")

        last_shifts = {}
        
        # ====================================================================
        # SOLVER SETUP
        # ====================================================================
        model = cp_model.CpModel()
        vars_schichten = {}

        print("\n[BUILD] Erstelle Constraint-Modell...")
        
        for ma in self.mitarbeiter_list:
            for tag in tage_liste:
                for stype in self.target_shifts:
                    vars_schichten[(ma.id, tag, stype.kuerzel)] = model.NewBoolVar(f'{ma.id}_{tag}_{stype.kuerzel}')
                vars_schichten[(ma.id, tag, 'Frei')] = model.NewBoolVar(f'{ma.id}_{tag}_Frei')

        # ====================================================================
        # A. BASIS-CONSTRAINTS
        # ====================================================================
        print("   [OK] Basis-Regeln")
        
        for ma in self.mitarbeiter_list:
            for tag in tage_liste:
                all_options = [vars_schichten[(ma.id, tag, st.kuerzel)] for st in self.target_shifts]
                all_options.append(vars_schichten[(ma.id, tag, 'Frei')])
                model.Add(sum(all_options) == 1)

            # Nacht -> nächster Tag keine Tagschicht
            for i in range(len(tage_liste) - 1):
                heute = tage_liste[i]
                morgen = tage_liste[i+1]
                model.Add(
                    vars_schichten[(ma.id, morgen, 'T')] == 0
                ).OnlyEnforceIf(vars_schichten[(ma.id, heute, 'N')])

        if tage_liste:
            erster_tag = tage_liste[0]
            for ma_id, last_k in last_shifts.items():
                if last_k == 'N' and (ma_id, erster_tag, 'T') in vars_schichten:
                    model.Add(vars_schichten[(ma_id, erster_tag, 'T')] == 0)

        # ====================================================================
        # B. MITARBEITER-PRÄFERENZEN + WÜNSCHE
        # ====================================================================
        print("   [OK] Präferenzen & Wünsche")
        
        # Initialisiere objective_terms HIER (wird in B.9 Typ B gebraucht)
        objective_terms = []
        
        for ma in self.mitarbeiter_list:
            pref = self.preferences[ma.id]
            
            # B.1 KANN NICHT TAGSCHICHT
            if not pref['kann_tagschicht']:
                for tag in tage_liste:
                    model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
            
            # B.2 KANN NICHT NACHTSCHICHT
            if not pref['kann_nachtschicht']:
                for tag in tage_liste:
                    model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
            
            # B.3 NACHTSCHICHT NUR WOCHENENDE
            if pref['nachtschicht_nur_wochenende']:
                for tag in tage_liste:
                    if tag.weekday() < 5:  # Mo-Fr
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
            
            # B.4 NUR ZUSATZDIENSTE WOCHENTAGS
            if pref['nur_zusatzdienste_wochentags']:
                for tag in tage_liste:
                    if tag.weekday() < 5:  # Mo-Fr
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
            
            # B.5 VERFÜGBARKEIT
            if pref['verfuegbarkeit'] == 'wochenende_only':
                for tag in tage_liste:
                    if tag.weekday() < 5:
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
            elif pref['verfuegbarkeit'] == 'wochentags_only':
                for tag in tage_liste:
                    if tag.weekday() >= 5:
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
            
            # B.6 MAX WOCHENENDEN
            max_we = pref['max_wochenenden_pro_monat']
            wochenenden = []
            current_we = None
            for tag in tage_liste:
                if tag.weekday() >= 5:
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
            
            # B.7 MAX SCHICHTEN PRO MONAT
            if pref['max_schichten_pro_monat'] < 999:
                alle_schichten = []
                for tag in tage_liste:
                    for stype in self.target_shifts:
                        alle_schichten.append(vars_schichten[(ma.id, tag, stype.kuerzel)])
                model.Add(sum(alle_schichten) <= pref['max_schichten_pro_monat'])
            
            # B.8 MAX AUFEINANDERFOLGENDE TAGE
            max_tage = pref['max_aufeinanderfolgende_tage']
            if max_tage and max_tage > 0:
                for i in range(len(tage_liste) - max_tage):
                    fenster = []
                    for j in range(max_tage + 1):
                        tag = tage_liste[i + j]
                        for stype in self.target_shifts:
                            fenster.append(vars_schichten[(ma.id, tag, stype.kuerzel)])
                    model.Add(sum(fenster) <= max_tage)
            
            # B.9 TYP B - MINDESTENS 4T + 4N (darf mehr sein)
            if pref['schicht_typ'] == 'typ_b':
                print(f"      [INFO] {ma.schichtplan_kennung}: Typ B erkannt (Min: 4T+4N, darf mehr sein)")
                
                # NEU: Berechne verfügbare Tage (ohne genehmigte Urlaube)
                verfuegbare_tage = 0
                for tag in tage_liste:
                    wunsch = wuensche_matrix.get(ma.id, {}).get(tag)
                    is_blocked = (wunsch and wunsch.wunsch in ['urlaub', 'krank', 'gar_nichts'] and wunsch.genehmigt)
                    if not is_blocked:
                        verfuegbare_tage += 1
                
                # Zähle Tag- und Nachtschichten für diesen MA
                tag_schichten = [vars_schichten[(ma.id, tag, 'T')] for tag in tage_liste]
                nacht_schichten = [vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste]
                
                count_t_var = model.NewIntVar(0, len(tage_liste), f'{ma.id}_typ_b_count_T')
                count_n_var = model.NewIntVar(0, len(tage_liste), f'{ma.id}_typ_b_count_N')
                model.Add(count_t_var == sum(tag_schichten))
                model.Add(count_n_var == sum(nacht_schichten))
                
                # NEU: HARD CONSTRAINT nur wenn genug Tage verfügbar!
                min_erforderlich = 8  # 4T + 4N
                
                if verfuegbare_tage >= min_erforderlich:
                    # Normal: Mindestens 4 Tag- und 4 Nachtschichten
                    model.Add(count_t_var >= 4)
                    model.Add(count_n_var >= 4)
                    print(f"         [OK] Typ B Constraint: Min 4T + 4N (verfügbar: {verfuegbare_tage} Tage)")
                    
                elif verfuegbare_tage > 0:
                    # Reduziert: So viele wie möglich, aber nicht erzwingen wenn unmöglich
                    max_moeglich = verfuegbare_tage // 2  # Hälftig aufteilen
                    if max_moeglich >= 2:
                        min_t = min(4, max_moeglich)
                        min_n = min(4, max_moeglich)
                        model.Add(count_t_var >= min_t)
                        model.Add(count_n_var >= min_n)
                        print(f"         [WARN] Typ B REDUZIERT: Min {min_t}T + {min_n}N (nur {verfuegbare_tage} Tage verfügbar)")
                    else:
                        print(f"         [WARN] Typ B ÜBERSPRUNGEN: Nur {verfuegbare_tage} Tag(e) verfügbar (zu wenig für Constraint)")
                        
                else:
                    # Komplett Urlaub: Constraint überspringen
                    print(f"         [WARN] Typ B ÜBERSPRUNGEN: {ma.schichtplan_kennung} hat 0 Tage verfügbar (kompletter Urlaub)")
                
                # SOFT CONSTRAINT: Bevorzuge etwa 4-6 Schichten (nur wenn genug Tage verfügbar)
                if verfuegbare_tage >= 6:
                    ueber_6_t = model.NewIntVar(0, 20, f'{ma.id}_typ_b_ueber_6_T')
                    model.Add(ueber_6_t >= count_t_var - 6)
                    model.Add(ueber_6_t >= 0)
                    
                    ueber_6_n = model.NewIntVar(0, 20, f'{ma.id}_typ_b_ueber_6_N')
                    model.Add(ueber_6_n >= count_n_var - 6)
                    model.Add(ueber_6_n >= 0)
                    
                    # Geringe Strafe: pro Schicht über Target
                    objective_terms.append(ueber_6_t * self.config.typ_b_overage_strafe)
                    objective_terms.append(ueber_6_n * self.config.typ_b_overage_strafe)

            # B.10 URLAUB / KRANK / GAR NICHTS -> Frei erzwingen
            for tag in tage_liste:
                wunsch = wuensche_matrix.get(ma.id, {}).get(tag)
                if wunsch and wunsch.wunsch in ['urlaub', 'krank', 'gar_nichts']:
                    model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                    model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                    model.Add(vars_schichten[(ma.id, tag, 'Frei')] == 1)

            # B.11 FIXE TAGDIENST-WOCHENTAGE (nur für MA1, NICHT MA7!)
            fixe_tage = pref['fixe_tag_wochentage']  # immer Liste

            # MA6 hat spezielle Regel: Nur Tagschichten Mo-Fr, kein Wochenende
            if ma.schichtplan_kennung == 'MA6':
                print(f"      [OK] MA6 SPEZIALREGEL: Nur Tagschichten Mo-Fr, keine Nachtschichten, kein Wochenende")
                for tag in tage_liste:
                    # Keine Nachtschichten (niemals)
                    model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)

                    if tag.weekday() >= 5:  # Sa-So
                        # Keine Schichten am Wochenende
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)

            # MA7 hat spezielle Regel: Mo-Do keine T/N (nur Z), Fr/Sa/So nur N
            elif ma.schichtplan_kennung == 'MA7':
                print(f"      [OK] MA7 SPEZIALREGEL: Mo-Do keine T/N (nur Zusatz), Fr/Sa/So nur N")
                for tag in tage_liste:
                    if tag.weekday() < 4:  # Mo-Do (0-3)
                        # Keine regulären Schichten Mo-Do
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
                    elif tag.weekday() == 4:  # Fr (4)
                        # Freitag: Nur Nachtschichten (Teil des Wochenendes)
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        # Nachtschicht erlaubt (wird nicht blockiert)
                    else:  # Sa-So (5-6)
                        # Nur Nachtschichten am Wochenende
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
            
            # B.11b WOCHENEND-NACHTDIENSTE ALS 2ER-BLOCK
            if pref['wochenend_nachtdienst_block']:
                print(f"      [OK] WOCHENEND-BLOCK: {ma.schichtplan_kennung} bevorzugt Nachtdienste am Wochenende in 2er-Blöcken (Fr+Sa oder Sa+So)")

                # Strafe für einzelne Nächte (nicht als Block)
                for i in range(len(tage_liste) - 1):
                    heute = tage_liste[i]
                    morgen = tage_liste[i + 1]

                    # Prüfe Fr+Sa oder Sa+So Paare
                    if (heute.weekday() == 4 and morgen.weekday() == 5) or \
                       (heute.weekday() == 5 and morgen.weekday() == 6):
                        heute_n = vars_schichten[(ma.id, heute, 'N')]
                        morgen_n = vars_schichten[(ma.id, morgen, 'N')]

                        # SOFT: Strafe wenn genau eine der beiden Schichten vergeben ist (XOR-Situation)
                        block_broken = model.NewBoolVar(f'{ma.id}_block_broken_{i}')

                        # heute_n + morgen_n == 1 bedeutet genau eine Schicht
                        summe = model.NewIntVar(0, 2, f'{ma.id}_block_sum_{i}')
                        model.Add(summe == heute_n + morgen_n)
                        model.Add(summe == 1).OnlyEnforceIf(block_broken)
                        model.Add(summe != 1).OnlyEnforceIf(block_broken.Not())

                        # Strafe für kaputte Blöcke
                        objective_terms.append(block_broken * self.config.wockenend_block_strafe)

            elif fixe_tage:  # MA1: [2] (Mi) - andere mit fixen Tagen
                # SOFT CONSTRAINT: Bevorzuge Tagdienst an diesen Tagen, aber erzwinge nicht
                tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']
                fixe_namen = [tage_namen[t] for t in fixe_tage if 0 <= t <= 6]
                print(f"      [INFO] BEVORZUGTE TAGDIENSTE: {ma.schichtplan_kennung} bevorzugt an {','.join(fixe_namen)} (Soft)")

                # Füge zu Objective hinzu statt Hard Constraint
                # Dies wird später in E.2 WÜNSCHE behandelt
            
            # B.12 ERLAUBTE WOCHENTAGE (HARD CONSTRAINT)
            # Nur anwenden wenn KEINE fixen Tage gesetzt sind
            erlaubte_tage = pref['erlaubte_wochentage']  # immer Liste (kann leer sein)
            
            if erlaubte_tage and not fixe_tage:  # nur wenn nicht leer UND keine fixen Tage
                tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']
                sichtbare_tage = [tage_namen[t] for t in erlaubte_tage if 0 <= t <= 6]
                print(f"      [OK] CONSTRAINT: {ma.schichtplan_kennung} nur an {','.join(sichtbare_tage)}")
                
                for tag in tage_liste:
                    if tag.weekday() not in erlaubte_tage:
                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)
                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)
            
            # B.13 MIN TAGSCHICHTEN als SOFT CONSTRAINT
            if pref['min_tagschichten_pro_monat']:
                min_t = pref['min_tagschichten_pro_monat']
                tag_schichten = [vars_schichten[(ma.id, tag, 'T')] for tag in tage_liste]
                
                # Prüfe verfügbare Tage
                verfuegbare_tage = 0
                for tag in tage_liste:
                    wunsch = wuensche_matrix.get(ma.id, {}).get(tag)
                    is_blocked = (wunsch and wunsch.wunsch in ['urlaub', 'krank', 'gar_nichts'])
                    if not is_blocked:
                        verfuegbare_tage += 1
                
                # SOFT: Nur als Warnung, kein Hard Constraint mehr
                print(f"      [INFO] MIN TAGSCHICHTEN: {ma.schichtplan_kennung} Ziel {min_t}T (verfügbar: {verfuegbare_tage} Tage)")
            
            # B.14 MIN NACHTSCHICHTEN als SOFT CONSTRAINT  
            if pref['min_nachtschichten_pro_monat']:
                min_n = pref['min_nachtschichten_pro_monat']
                nacht_schichten = [vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste]
                
                verfuegbare_tage = 0
                for tag in tage_liste:
                    wunsch = wuensche_matrix.get(ma.id, {}).get(tag)
                    is_blocked = (wunsch and wunsch.wunsch in ['urlaub', 'krank', 'gar_nichts'])
                    if not is_blocked:
                        verfuegbare_tage += 1
                
                # SOFT: Nur als Warnung, kein Hard Constraint mehr
                print(f"      [INFO] MIN NACHTSCHICHTEN: {ma.schichtplan_kennung} Ziel {min_n}N (verfügbar: {verfuegbare_tage} Tage)")

            # B.15 TAGSCHICHT-BLOCK-PRÄFERENZ (3er und 4er Blöcke bestrafen)
            if self.config:
                print(f"  [OK] TAGSCHICHT-BLÖCKE: Bevorzuge 2er-Blöcke, bestrafe 3er+")

                # 3er-Blöcke: Fenster von 3 aufeinanderfolgende Tagen
                for i in range(len(tage_liste) - 2):
                    heute = tage_liste[i]
                    morgen = tage_liste[i + 1]
                    uebermorgen = tage_liste[i + 2]

                    t_heute = vars_schichten[(ma.id, heute, 'T')]
                    t_morgen = vars_schichten[(ma.id, morgen, 'T')]
                    t_uebermorgen = vars_schichten[(ma.id, uebermorgen, 'T')]

                    # Detect 3-Block: Alle 3 Tage haben T-Schicht
                    block_3er = model.NewBoolVar(f'{ma.id}_tag_block_3er_{i}')
                    summe_3 = model.NewIntVar(0, 3, f'{ma.id}_tag_sum_3er_{i}')
                    model.Add(summe_3 == t_heute + t_morgen + t_uebermorgen)
                    model.Add(summe_3 == 3).OnlyEnforceIf(block_3er)
                    model.Add(summe_3 != 3).OnlyEnforceIf(block_3er.Not())

                    # Penalty für 3er-Blöcke
                    objective_terms.append(block_3er * self.config.tag_block_3er_strafe)

                # 4er+ Blöcke: Fenster von 4 aufeinanderfolgende Tagen (zusätzliche Penalty)
                for i in range(len(tage_liste) - 3):
                    heute = tage_liste[i]
                    morgen = tage_liste[i + 1]
                    uebermorgen = tage_liste[i + 2]
                    tag_4 = tage_liste[i + 3]

                    t_heute = vars_schichten[(ma.id, heute, 'T')]
                    t_morgen = vars_schichten[(ma.id, morgen, 'T')]
                    t_uebermorgen = vars_schichten[(ma.id, uebermorgen, 'T')]
                    t_4 = vars_schichten[(ma.id, tag_4, 'T')]

                    # Detect 4-Block
                    block_4er = model.NewBoolVar(f'{ma.id}_tag_block_4er_{i}')
                    summe_4 = model.NewIntVar(0, 4, f'{ma.id}_tag_sum_4er_{i}')
                    model.Add(summe_4 == t_heute + t_morgen + t_uebermorgen + t_4)
                    model.Add(summe_4 == 4).OnlyEnforceIf(block_4er)
                    model.Add(summe_4 != 4).OnlyEnforceIf(block_4er.Not())

                    # Zusatz-Penalty für 4er+ (zur 3er-Penalty addiert)
                    objective_terms.append(block_4er * self.config.tag_block_4er_strafe)

        # ====================================================================
        # C. BESETZUNG - HARD CONSTRAINT: GENAU 2 PRO SCHICHT
        # ====================================================================
        print("   [OK] Besetzung: GENAU 2 pro Schicht (Hard Constraint)")
        
        for tag in tage_liste:
            for stype in ['T', 'N']:
                # NUR Mitarbeiter zählen, die zur Besetzung beitragen
                # MA7: zählt nur zur Nachtbesetzung, nicht zur Tagbesetzung
                if stype == 'T':
                    relevante_ma = [m for m in self.mitarbeiter_list if self.preferences[m.id]['zaehlt_zur_tagbesetzung']]
                else:  # 'N'
                    relevante_ma = [m for m in self.mitarbeiter_list if self.preferences[m.id]['zaehlt_zur_nachtbesetzung']]
                
                schichten_pro_typ = [vars_schichten[(m.id, tag, stype)] for m in relevante_ma]
                summe_var = model.NewIntVar(0, 12, f'summe_{tag}_{stype}')
                model.Add(summe_var == sum(schichten_pro_typ))

                # HARD CONSTRAINT: GENAU 2 Personen pro Schicht
                model.Add(summe_var == 2)  # MUSS: Genau 2!
        # ====================================================================
        # D. FAIRNESS (T/N/WE Ausgleich) - NUR KERNTEAM, JAHRESZIEL
        # ====================================================================
        # Kumulative T/N/WE aus veröffentlichten Plänen werden einbezogen,
        # damit die Jahressummen am Jahresende in etwa gleich sind.
        # ====================================================================
        print("   [OK] Fairness (Tag/Nacht/Wochenende) - Kernteam, Jahressummen-Ausgleich")

        FAIRNESS_WEIGHT_T = self.config.fairness_weight_tagschichten
        FAIRNESS_WEIGHT_N = self.config.fairness_weight_nachtschichten
        FAIRNESS_WEIGHT_WE = self.config.fairness_weight_wochenenden

        # Fr (4), Sa (5), So (6) = Wochenende für Fairness
        weekend_days = [tag for tag in tage_liste if tag.weekday() >= 4]

        count_t = {}
        count_n = {}
        count_we = {}
        eligible_t = []  # Nur Kernteam
        eligible_n = []  # Nur Kernteam
        eligible_we = []  # Nur Kernteam

        for ma in self.mitarbeiter_list:
            pref = self.preferences[ma.id]
            ist_kernteam = (pref['kategorie'] == 'kern')

            # Tag-Schichten zählen
            t_vars = [vars_schichten[(ma.id, tag, 'T')] for tag in tage_liste]
            count_t_var = model.NewIntVar(0, len(tage_liste), f'{ma.id}_count_T')
            model.Add(count_t_var == sum(t_vars))
            count_t[ma.id] = count_t_var
            # NUR KERNTEAM in Fairness einbeziehen
            if ist_kernteam and pref['kann_tagschicht']:
                eligible_t.append(ma.id)

            # Nacht-Schichten zählen
            n_vars = [vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste]
            count_n_var = model.NewIntVar(0, len(tage_liste), f'{ma.id}_count_N')
            model.Add(count_n_var == sum(n_vars))
            count_n[ma.id] = count_n_var
            # NUR KERNTEAM in Fairness einbeziehen
            if ist_kernteam and pref['kann_nachtschicht']:
                eligible_n.append(ma.id)

            # Wochenend-Schichten zählen (T+N auf Sa/So)
            if weekend_days:
                we_vars = []
                for tag in weekend_days:
                    we_vars.append(vars_schichten[(ma.id, tag, 'T')])
                    we_vars.append(vars_schichten[(ma.id, tag, 'N')])
                max_we_shifts = len(weekend_days) * 2
                count_we_var = model.NewIntVar(0, max_we_shifts, f'{ma.id}_count_WE')
                model.Add(count_we_var == sum(we_vars))
                count_we[ma.id] = count_we_var

                # NUR KERNTEAM in Fairness einbeziehen
                if ist_kernteam and pref['verfuegbarkeit'] != 'wochentags_only' and pref['max_wochenenden_pro_monat'] > 0 and (pref['kann_tagschicht'] or pref['kann_nachtschicht']):
                    eligible_we.append(ma.id)

        def add_pairwise_balance(ids, count_map, max_diff, weight, label, cumulative_map=None):
            """Fairness: Ziel ist ausgeglichene Jahressumme. Mit cumulative_map wird
            |(count_i + cum_i) - (count_j + cum_j)| bestraft, also count_i - count_j ~ cum_j - cum_i."""
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    ma_i = ids[i]
                    ma_j = ids[j]
                    cum_i = (cumulative_map or {}).get(ma_i, 0)
                    cum_j = (cumulative_map or {}).get(ma_j, 0)
                    target = cum_j - cum_i  # gewünschte Differenz: count_i - count_j == target
                    diff = model.NewIntVar(-max_diff, max_diff, f'diff_{label}_{ma_i}_{ma_j}')
                    model.Add(diff == count_map[ma_i] - count_map[ma_j])
                    # Abweichung vom Jahresziel: (count_i - count_j) - target
                    balance_range = 2 * max_diff
                    balance = model.NewIntVar(-balance_range, balance_range, f'bal_{label}_{ma_i}_{ma_j}')
                    model.Add(balance == diff - target)
                    abs_balance = model.NewIntVar(0, balance_range, f'abs_{label}_{ma_i}_{ma_j}')
                    model.AddAbsEquality(abs_balance, balance)
                    objective_terms.append(abs_balance * weight)

        # Debug: Zeige welche Mitarbeiter im Fairness-Vergleich sind
        kernteam_kennungen_t = [self.ma_map[ma_id].schichtplan_kennung for ma_id in eligible_t]
        kernteam_kennungen_n = [self.ma_map[ma_id].schichtplan_kennung for ma_id in eligible_n]
        kernteam_kennungen_we = [self.ma_map[ma_id].schichtplan_kennung for ma_id in eligible_we]
        
        print(f"      -> Kernteam Fairness Tagschichten: {', '.join(kernteam_kennungen_t) if kernteam_kennungen_t else 'keine'}")
        print(f"      -> Kernteam Fairness Nachtschichten: {', '.join(kernteam_kennungen_n) if kernteam_kennungen_n else 'keine'}")
        print(f"      -> Kernteam Fairness Wochenenden: {', '.join(kernteam_kennungen_we) if kernteam_kennungen_we else 'keine'}")
        
        if len(eligible_t) >= 2:
            add_pairwise_balance(eligible_t, count_t, len(tage_liste), FAIRNESS_WEIGHT_T, 'T', cumulative_map=cumulative_t)
        if len(eligible_n) >= 2:
            add_pairwise_balance(eligible_n, count_n, len(tage_liste), FAIRNESS_WEIGHT_N, 'N', cumulative_map=cumulative_n)
        if weekend_days and len(eligible_we) >= 2:
            add_pairwise_balance(eligible_we, count_we, len(weekend_days) * 2, FAIRNESS_WEIGHT_WE, 'WE', cumulative_map=cumulative_we)

        # ====================================================================
        # E. OPTIMIERUNGSZIEL
        # ====================================================================
        print("   [OK] Optimierungsziel (Wünsche + Soll-Stunden)")
        
        for ma in self.mitarbeiter_list:
            pref = self.preferences[ma.id]
            soll_schichten = soll_schichten_map.get(ma.id, 10)
            
            # --- E.1 SOLL-STUNDEN (Abweichung bestrafen) ---
            normale_schichten = []
            for tag in tage_liste:
                if tag not in urlaubs_tage.get(ma.id, []):
                    for stype in ['T', 'N']:
                        normale_schichten.append(vars_schichten[(ma.id, tag, stype)])

            ist_schichten_var = model.NewIntVar(0, 100, f'{ma.id}_ist_schichten')
            model.Add(ist_schichten_var == sum(normale_schichten))

            abweichung_var = model.NewIntVar(-100, 100, f'{ma.id}_abweichung')
            model.Add(abweichung_var == ist_schichten_var - soll_schichten)

            abs_abweichung = model.NewIntVar(0, 100, f'{ma.id}_abs_abweichung')
            model.AddAbsEquality(abs_abweichung, abweichung_var)
            objective_terms.append(abs_abweichung * self.config.soll_stunden_abweichung_strafe)
            
            # --- E.2 WÜNSCHE + FIXE TAGE (Soft) ---
            fixe_tage = pref.get('fixe_tag_wochentage', [])
            
            for tag in tage_liste:
                wunsch = wuensche_matrix.get(ma.id, {}).get(tag)
                
                for stype in self.target_shifts:
                    kuerzel = stype.kuerzel
                    score = 0
                    
                    # Wünsche
                    if wunsch:
                        if wunsch.wunsch == 'tag_bevorzugt':
                            score = -self.config.wunsch_tag_bevorzugt if kuerzel == 'T' else self.config.wunsch_tag_bevorzugt
                        elif wunsch.wunsch == 'nacht_bevorzugt':
                            score = -self.config.wunsch_nacht_bevorzugt if kuerzel == 'N' else self.config.wunsch_nacht_bevorzugt
                        elif wunsch.wunsch == 'zusatzarbeit':
                            score = -self.config.wunsch_zusatzarbeit
                        elif wunsch.wunsch in ['urlaub', 'krank', 'gar_nichts'] and wunsch.genehmigt:
                            score = 1000000  # sollte durch B.10 nicht noetig sein, aber Safety

                    # Fixe Tagdienste als Soft Constraint (MA1: Mittwoch bevorzugt)
                    if fixe_tage and kuerzel == 'T' and tag.weekday() in fixe_tage:
                        score += -self.config.wunsch_fixe_tagdienste  # Starke Bevorzugung für Tagdienst an fixen Tagen

                    # Planungs-Priorität als Multiplikator
                    if pref['planungs_prioritaet'] == 'hoch':
                        score = int(score * float(self.config.priority_multiplier_hoch))
                    elif pref['planungs_prioritaet'] == 'niedrig':
                        score = int(score * float(self.config.priority_multiplier_niedrig))
                    
                    if score != 0:
                        objective_terms.append(vars_schichten[(ma.id, tag, kuerzel)] * score)

                    # Bevorzugung "wenige Wünsche": Wer selten Wünsche äußert, wird bei der Planung bevorzugt
                    bonus = wunsch_bonus.get(ma.id, 0)
                    if bonus > 0:
                        objective_terms.append(vars_schichten[(ma.id, tag, kuerzel)] * (-bonus))

        model.Minimize(sum(objective_terms))

        # ====================================================================
        # F. SOLVER STARTEN
        # ====================================================================
        # ====================================================================
# F. SOLVER STARTEN
# ====================================================================
        print("\n" + "="*70)
        print("[DBG] CONSTRAINT-ANALYSE")
        print("="*70)
        print(f"Zeitraum: {len(tage_liste)} Tage | Mitarbeiter: {len(self.mitarbeiter_list)}")
        kann_tag = sum(1 for ma in self.mitarbeiter_list if self.preferences[ma.id]['kann_tagschicht'])
        kann_nacht = sum(1 for ma in self.mitarbeiter_list if self.preferences[ma.id]['kann_nachtschicht'])
        print(f"Können Tagschicht: {kann_tag} | Können Nachtschicht: {kann_nacht}")
        urlaubs_gesamt = sum(len(tage) for tage in urlaubs_tage.values())
        print(f"Urlaubstage gesamt: {urlaubs_gesamt}")
        typ_b_mas = [ma for ma in self.mitarbeiter_list if self.preferences[ma.id]['schicht_typ'] == 'typ_b']
        if typ_b_mas:
            print(f"Typ B: {len(typ_b_mas)} Mitarbeiter")
            for ma in typ_b_mas:
                verfuegbar = len(tage_liste) - len(urlaubs_tage.get(ma.id, []))
                print(f"   {ma.schichtplan_kennung}: {verfuegbar} Tage verfügbar")
        print("="*70 + "\n")

        print(f"[SOLVER] Starte Solver mit {self.config.solver_num_workers} CPU-Kernen...")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.solver_timeout_sekunden
        solver.parameters.num_search_workers = self.config.solver_num_workers
        solver.parameters.log_search_progress = True  # Debug Info
        solver.parameters.linearization_level = self.config.solver_linearization_level  # Bessere Linearisierung
        solver.parameters.relative_gap_limit = float(self.config.solver_relative_gap_limit)  # Stoppt bei X% vom Optimum
        status = solver.Solve(model)
        if status == cp_model.OPTIMAL:
            print('[OK] OPTIMAL gefunden!')
        elif status == cp_model.FEASIBLE:
            print(f'[WARN] FEASIBLE - Objective: {solver.ObjectiveValue()}')
            print(f'Best Bound: {solver.BestObjectiveBound()}')
        else:
            print('[FAIL] INFEASIBLE oder UNKNOWN')
        print(f"   Status: {solver.StatusName(status)}")
        
        # ====================================================================
        # G. ERGEBNISSE SPEICHERN
        # ====================================================================
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"\n[OK] Lösung gefunden! Status: {solver.StatusName(status)}\n")
            
            ergebnis_count = 0
            ist_schichten_pro_ma = defaultdict(int)
            
            for ma in self.mitarbeiter_list:
                for tag in tage_liste:
                    if solver.Value(vars_schichten[(ma.id, tag, 'T')]) == 1:
                        Schicht.objects.create(
                            schichtplan=neuer_schichtplan_obj,
                            mitarbeiter=ma, datum=tag, schichttyp=self.type_t
                        )
                        ergebnis_count += 1
                        ist_schichten_pro_ma[ma.id] += 1
                    elif solver.Value(vars_schichten[(ma.id, tag, 'N')]) == 1:
                        Schicht.objects.create(
                            schichtplan=neuer_schichtplan_obj,
                            mitarbeiter=ma, datum=tag, schichttyp=self.type_n
                        )
                        ergebnis_count += 1
                        ist_schichten_pro_ma[ma.id] += 1
            
            print(f"[SAVE] {ergebnis_count} Schichten gespeichert.")
            
            # ================================================================
            # H. ZUSATZDIENSTE GENERIEREN
            # ================================================================
            if self.type_z:
                print("\n[+] Generiere Zusatzdienste zum Auffüllen...")
                
                z_ist_tag = True 
                if self.type_z.start_zeit and self.type_z.start_zeit.hour >= 18: 
                    z_ist_tag = False
                
                zusatz_count = 0
                ma_bedarf = []

                for ma in self.mitarbeiter_list:
                    pref = self.preferences[ma.id]
                    
                    # SKIP: keine_zusatzdienste
                    if pref['keine_zusatzdienste']:
                        print(f"   [SKIP]  {ma.schichtplan_kennung}: Übersprungen (Vereinbarung: keine Z)")
                        continue
                        
                    # SKIP: Kann Schichttyp nicht
                    if z_ist_tag and not pref['kann_tagschicht']:
                        continue
                    if not z_ist_tag and not pref['kann_nachtschicht']:
                        continue

                    soll = soll_schichten_map.get(ma.id, 10)
                    ist = ist_schichten_pro_ma[ma.id]
                    fehlt = soll - ist
                    
                    if fehlt > 0:
                        erlaubte_tage = pref['erlaubte_wochentage']  # Liste oder leer
                        freie_tage = []
                        
                        for tag in tage_liste:
                            # Mo-Fr für Z (0=Mo, 1=Di, 2=Mi, 3=Do, 4=Fr)
                            if tag.weekday() not in [0, 1, 2, 3, 4]:
                                continue
                            # Kein Urlaub
                            if tag in urlaubs_tage.get(ma.id, []):
                                continue
                            # Erlaubte Wochentage prüfen
                            if erlaubte_tage and tag.weekday() not in erlaubte_tage:
                                continue
                            # Muss "Frei" sein
                            if solver.Value(vars_schichten[(ma.id, tag, 'Frei')]) == 1:
                                
                                # Safety: Kein Z nach Nachtschicht
                                gestern = tag - datetime.timedelta(days=1)
                                if gestern in tage_liste:
                                    if solver.Value(vars_schichten[(ma.id, gestern, 'N')]) == 1:
                                        continue

                                # Safety: Max aufeinanderfolgende Tage prüfen
                                # Zähle nur TATSÄCHLICH zugewiesene Schichten (T/N vom Solver)
                                # Z-Dienste die WIR gerade vergeben werden HIER noch nicht gezählt
                                morgen = tag + datetime.timedelta(days=1)
                                work_streak = 1
                                
                                check_tag = gestern
                                while check_tag in tage_liste:
                                    if solver.Value(vars_schichten[(ma.id, check_tag, 'Frei')]) == 0:
                                        work_streak += 1
                                    else:
                                        break
                                    check_tag -= datetime.timedelta(days=1)
                                
                                check_tag = morgen
                                while check_tag in tage_liste:
                                    if solver.Value(vars_schichten[(ma.id, check_tag, 'Frei')]) == 0:
                                        work_streak += 1
                                    else:
                                        break
                                    check_tag += datetime.timedelta(days=1)
                                
                                max_tage = pref['max_aufeinanderfolgende_tage'] or 999
                                if work_streak > max_tage:
                                    continue

                                freie_tage.append(tag)
                        
                        if freie_tage:
                            ma_bedarf.append({
                                'ma': ma,
                                'bedarf': fehlt,
                                'zugewiesen': 0,
                                'freie_tage': freie_tage
                            })
                            print(f"   {ma.schichtplan_kennung}: fehlt {fehlt} Schichten, {len(freie_tage)} Tage verfügbar")
                
                # ============================================================
                # H.2 VERTEILUNG: Pro-MA Durchlauf, max 2 Z pro Tag
                # ============================================================
                if ma_bedarf:
                    # Sortiere: Wer am meisten braucht -> zuerst; bei gleichem Bedarf: wer weniger Z im Jahr hat -> zuerst (Jahresausgleich)
                    ma_bedarf.sort(key=lambda x: (-x['bedarf'], cumulative.get(x['ma'].id, {}).get('z', 0)))
                    
                    # Zähle wie viele Z pro Tag vergeben werden (max konfiguriert)
                    z_pro_tag = defaultdict(int)
                    MAX_Z_PRO_TAG = self.config.max_zusatzdienste_pro_tag
                    
                    # Zähle auch bereits vergebene Z pro MA (aus Solver T/N + neue Z)
                    # damit max_aufeinanderfolgende_tage korrekt bleibt
                    ma_arbeits_tage = {}  # {ma.id: set(datum)} -- alle Tage wo MA arbeitet
                    for ma_info in ma_bedarf:
                        arbeits_tage = set()
                        for tag in tage_liste:
                            if solver.Value(vars_schichten[(ma_info['ma'].id, tag, 'Frei')]) == 0:
                                arbeits_tage.add(tag)
                        ma_arbeits_tage[ma_info['ma'].id] = arbeits_tage

                    for ma_info in ma_bedarf:
                        ma_id = ma_info['ma'].id
                        max_tage = self.preferences[ma_id]['max_aufeinanderfolgende_tage'] or 999
                        
                        for tag in ma_info['freie_tage']:
                            # Genug für diesen MA?
                            if ma_info['zugewiesen'] >= ma_info['bedarf']:
                                break
                            # Tag voll (max 2 Z)?
                            if z_pro_tag[tag] >= MAX_Z_PRO_TAG:
                                continue
                            # Duplikat-Check: MA hat schon eine Schicht an diesem Tag
                            if tag in ma_arbeits_tage[ma_id]:
                                continue
                            
                            # Safety: max aufeinanderfolgende Tage prüfen
                            # Zähle zusammenhängende Arbeits-Tage INCLUSIVE diesen Tag
                            streak = 1
                            check = tag - datetime.timedelta(days=1)
                            while check in ma_arbeits_tage[ma_id]:
                                streak += 1
                                check -= datetime.timedelta(days=1)
                            check = tag + datetime.timedelta(days=1)
                            while check in ma_arbeits_tage[ma_id]:
                                streak += 1
                                check += datetime.timedelta(days=1)
                            
                            if streak > max_tage:
                                continue

                            # [OK] Vergeben
                            Schicht.objects.create(
                                schichtplan=neuer_schichtplan_obj,
                                mitarbeiter=ma_info['ma'],
                                datum=tag,
                                schichttyp=self.type_z
                            )
                            ma_info['zugewiesen'] += 1
                            z_pro_tag[tag] += 1
                            ma_arbeits_tage[ma_id].add(tag)  # <- Tag merken für nächste Streak-Prüfung
                            zusatz_count += 1
                    
                    print(f"   [+] {zusatz_count} Zusatzdienste vergeben.")

            # ================================================================
            # I. STATISTIKEN
            # ================================================================
            self._print_statistics(neuer_schichtplan_obj, tage_liste, soll_stunden_map, soll_schichten_map, wuensche_matrix)

            # ================================================================
            # J. KONFIGURATION SPEICHERN für Rückverfolgbarkeit
            # ================================================================
            if self.schichtplan_obj:
                self.schichtplan_obj.konfiguration = self.config
                self.schichtplan_obj.save(update_fields=['konfiguration'])
                print(f"   [CONFIG] Konfiguration v{self.config.version_nummer} mit Plan gespeichert.\n")

        else:
            error_msg = (
                "Keine gültige Lösung gefunden. Mögliche Ursachen: "
                "zu wenige MA für Besetzung (2 pro Schicht), "
                "zu viele Urlaube an denselben Tagen, "
                "oder Typ B + Wünsche unvereinbar."
            )
            print("[FAIL] Solver-Fehler:", error_msg)
            raise Exception(error_msg)

    # ======================================================================
    # STATISTIKEN
    # ======================================================================
    def _print_statistics(self, schichtplan, tage_liste, soll_stunden_map, soll_schichten_map, wuensche_matrix):
        print("\n" + "="*70)
        print("[STATS] PLAN-STATISTIKEN")
        print("="*70)
        
        schichten = Schicht.objects.filter(schichtplan=schichtplan)
        
        # Wunsch-Analyse
        print("\n[DBG] WUNSCH-ANALYSE:")
        for ma in self.mitarbeiter_list:
            ma_wuensche = wuensche_matrix.get(ma.id, {})
            for datum, wunsch in ma_wuensche.items():
                schicht_an_tag = schichten.filter(mitarbeiter=ma, datum=datum).first()
                ist = schicht_an_tag.schichttyp.kuerzel if schicht_an_tag else "Frei"
                
                if wunsch.wunsch in ['urlaub', 'krank']:
                    status = "OK" if not schicht_an_tag else "FEHLER"
                elif wunsch.wunsch == 'tag_bevorzugt':
                    status = "[OK]" if ist == 'T' else ("[WARN] SOFT" if ist != 'Frei' else "[INFO]")
                elif wunsch.wunsch == 'nacht_bevorzugt':
                    status = "[OK]" if ist == 'N' else ("[WARN] SOFT" if ist != 'Frei' else "[INFO]")
                elif wunsch.wunsch == 'gar_nichts':
                    status = "[OK]" if not schicht_an_tag else ("[FAIL] FEHLER" if wunsch.genehmigt else "[WARN]")
                else:
                    status = "[INFO]"
                
                print(f"   {status} {ma.schichtplan_kennung}: {wunsch.wunsch} am {datum} -> {ist}")
        
        # Verteilung pro MA
        print("\n[STATS] SCHICHT-VERTEILUNG:")
        tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']
        
        for ma in self.mitarbeiter_list:
            ma_schichten = schichten.filter(mitarbeiter=ma)
            anzahl_t = ma_schichten.filter(schichttyp=self.type_t).count()
            anzahl_n = ma_schichten.filter(schichttyp=self.type_n).count()
            anzahl_z = ma_schichten.filter(schichttyp=self.type_z).count() if self.type_z else 0
            gesamt = anzahl_t + anzahl_n + anzahl_z
            
            soll_schichten = soll_schichten_map.get(ma.id, 0)
            soll_stunden = soll_stunden_map.get(ma.id, 0)
            diff = gesamt - soll_schichten
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            typ_label = "B" if self.preferences[ma.id]['schicht_typ'] == 'typ_b' else "A"
            
            # Vereinbarungen anzeigen (eigene Variablen, nicht 't' überschreiben!)
            vereinbarungen = []
            erlaubte = self.preferences[ma.id]['erlaubte_wochentage']
            if erlaubte:
                vereinbarungen.append(', '.join(tage_namen[d] for d in erlaubte if 0 <= d <= 6))
            if self.preferences[ma.id]['keine_zusatzdienste']:
                vereinbarungen.append("keine Z")
            vereinbarungen_str = f" [{', '.join(vereinbarungen)}]" if vereinbarungen else ""
            
            print(f"   {ma.schichtplan_kennung} (Typ {typ_label}){vereinbarungen_str}: {anzahl_t}T + {anzahl_n}N + {anzahl_z}Z = {gesamt} (Soll: {soll_schichten}, {diff_str}) | {soll_stunden}h")
        
        print("="*70 + "\n")
