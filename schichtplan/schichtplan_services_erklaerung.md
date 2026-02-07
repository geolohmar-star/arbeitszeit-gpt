# Line-by-line Erklärung: schichtplan/services.py (Snippet)

> Hinweis: Die Nummerierung folgt der **Reihenfolge der Zeilen im von dir geposteten Ausschnitt**.  
> Ich erkläre jede Zeile/Gruppe exakt so, wie sie im Snippet steht.

---

## Header & Modulbeschreibung

1. `# schichtplan/services.py - MIT WUNSCH-INTEGRATION + SOLL-STUNDEN-VERRECHNUNG`  
   Kommentar mit Dateiname und Feature-Übersicht.

2. `"""`  
   Beginn des Modul-Docstrings (Mehrzeilen-String, reine Dokumentation).

3. `KI-gestützte Schichtplan-Generierung mit OR-Tools`  
   Kurzbeschreibung des Moduls.

4. ``
   Leere Zeile im Docstring (optische Trennung).

5. `VOLLSTÄNDIG mit:`  
   Start einer Featureliste.

6. `- Typ A/B Klassifikation`  
   Feature: Mitarbeiter werden in Typ A/B eingeteilt.

7. `- Typ B: Min 4T + 4N pro Monat`  
   Feature: Typ B braucht mindestens 4 Tag- und 4 Nachtschichten.

8. `- Genau 2 Personen pro Schicht`  
   Feature: Zielbesetzung pro Schicht.

9. `- Fairness: Gleichmäßige Verteilung`  
   Feature: gleichmäßigere Last.

10. `- WUNSCH-INTEGRATION (Urlaub, Präferenzen)`  
   Feature: Wünsche wie Urlaub etc.

11. `- SOLL-STUNDEN-VERRECHNUNG (jeder arbeitet ca. gleich viel)`  
   Feature: Sollstunden-Logik.

12. `- AUTOMATISCHE ZUSATZDIENSTE zum Auffüllen`  
   Feature: Zusatzdienste werden automatisch ergänzt.

13. `- INDIVIDUELLE VEREINBARUNGEN (erlaubte Tage, keine Zusatzdienste)`  
   Feature: spezielle Vereinbarungen.

14. `"""`  
   Ende des Docstrings.

---

## Imports

15. `import json`  
   JSON-Verarbeitung (z. B. bei erlaubten Wochentagen).

16. `import datetime`  
   Datumslogik (Tag-zu-Tag, Tage addieren).

17. `import calendar`  
   Monatslängen, z. B. letztes Tagesdatum.

18. `from collections import defaultdict`  
   Dict mit Standardwerten (z. B. Listen) für Wünsche/Urlaube.

19. `from decimal import Decimal`  
   Exakte Dezimalzahlen (in diesem Snippet nicht sichtbar genutzt).

20. `from ortools.sat.python import cp_model`  
   OR-Tools CP-SAT Modell.

21. `from django.db.models import Q`  
   Django Query-Logik (in diesem Snippet nicht sichtbar genutzt).

22. `from schichtplan.models import Schicht, Schichttyp, Schichtplan, Schichtwunsch`  
   Django-Modelle aus der App `schichtplan`.

23. `from arbeitszeit.models import MonatlicheArbeitszeitSoll`  
   Modell für Soll-Stunden.

---

## Klasse `SchichtplanGenerator`

24. `class SchichtplanGenerator:`  
   Definition der Hauptklasse.

25. `    def __init__(self, mitarbeiter_queryset):`  
   Konstruktor: nimmt Mitarbeiter-Queryset.

26. `        self.mitarbeiter_list = list(mitarbeiter_queryset)`  
   Queryset wird in Liste umgewandelt.

27. `        self.ma_map = {ma.id: ma for ma in self.mitarbeiter_list}`  
   Map von Mitarbeiter-ID → Mitarbeiter-Objekt.

28. `        `  
   Leere Zeile (Lesbarkeit).

29. `        try:`  
   Beginn eines Blocks, in dem Schichttypen geladen werden.

30. `            self.type_t = Schichttyp.objects.get(kuerzel='T')`  
   Schichttyp Tag (`T`) laden.

31. `            self.type_n = Schichttyp.objects.get(kuerzel='N')`  
   Schichttyp Nacht (`N`) laden.

32. `            try:`  
   Versuch, Zusatzdienst (`Z`) zu laden.

33. `                self.type_z = Schichttyp.objects.get(kuerzel='Z')`  
   Schichttyp `Z` laden.

34. `            except Schichttyp.DoesNotExist:`  
   Falls `Z` nicht existiert.

35. `                self.type_z = None`  
   `Z` nicht verfügbar → `None`.

36. `                print("   ⚠️ Schichttyp 'Z' nicht gefunden")`  
   Warnung in Konsole.

37. `        except Schichttyp.DoesNotExist:`  
   Falls `T` oder `N` fehlen.

38. `            raise Exception("Schichttypen 'T' und 'N' müssen existieren.")`  
   Harte Fehlermeldung.

39. `        `  
   Leere Zeile.

40. `        self.target_shifts = [self.type_t, self.type_n]`  
   Ziel-Schichttypen sind T und N.

41. `        self._load_preferences()`  
   Lädt Mitarbeiter-Präferenzen.

---

## Präferenzen laden

42. `    # ======================================================================`  
   Kommentar-Separator.

43. `    # PRÄFERENZEN LADEN`  
   Abschnittstitel.

44. `    # ======================================================================`  
   Kommentar-Separator.

45. `    def _load_preferences(self):`  
   Methode: Präferenzen laden.

46. `        """Lädt alle relevanten Präferenzen und erzwingt korrekte Datentypen"""`  
   Docstring: Zweck der Methode.

47. `        print("   Lade Mitarbeiter-Präferenzen...")`  
   Statusausgabe.

48. `        `  
   Leerzeile.

49. `        self.preferences = {}`  
   Leeres Dict für Präferenzen.

50. `        `  
   Leerzeile.

51. `        for ma in self.mitarbeiter_list:`  
   Iteration über alle Mitarbeiter.

52. `            schicht_typ = getattr(ma, 'schicht_typ', 'typ_a')`  
   Liest `schicht_typ` oder fallback `typ_a`.

53. `            `  
   Leerzeile.

54. `            # --- 1. Wochentage säubern → IMMER eine Liste von Ints ---`  
   Kommentar: Datensäuberung Wochentage.

55. `            raw_tage = getattr(ma, 'erlaubte_wochentage', None)`  
   Rohwert aus Mitarbeiterobjekt.

56. `            clean_tage = []`  
   Ziel: saubere Liste.

57. `            `  
   Leerzeile.

58. `            if raw_tage is not None:`  
   Nur wenn Rohwert existiert.

59. `                if isinstance(raw_tage, str):`  
   Fall: String gespeichert.

60. `                    try:`  
   JSON-Parsing versuchen.

61. `                        loaded = json.loads(raw_tage)`  
   String als JSON laden.

62. `                        if isinstance(loaded, list):`  
   Wenn JSON-Liste…

63. `                            clean_tage = [int(t) for t in loaded]`  
   …in Int-Liste umwandeln.

64. `                        elif isinstance(loaded, (int, float)):`  
   Wenn JSON-Zahl…

65. `                            clean_tage = [int(loaded)]`  
   …zu Liste mit einer Zahl machen.

66. `                    except (json.JSONDecodeError, ValueError):`  
   Fehler beim JSON-Laden.

67. `                        if raw_tage.strip().isdigit():`  
   Falls String nur Ziffern enthält…

68. `                            clean_tage = [int(raw_tage.strip())]`  
   …als einzelne Zahl interpretieren.

69. `                elif isinstance(raw_tage, list):`  
   Fall: bereits Liste.

70. `                    clean_tage = [int(t) for t in raw_tage]`  
   Liste in Ints konvertieren.

71. `                elif isinstance(raw_tage, (int, float)):`  
   Fall: einzelne Zahl.

72. `                    clean_tage = [int(raw_tage)]`  
   In Liste umwandeln.

73. `            `  
   Leerzeile.

74. `            # --- 2. Keine Zusatzdienste Flag ---`  
   Kommentar: Flag verarbeiten.

75. `            keine_z = bool(getattr(ma, 'keine_zusatzdienste', False))`  
   Bool-Wert aus Mitarbeiter.

76. `            `  
   Leerzeile.

77. `            pref = {`  
   Start des Präferenz-Dicts.

78. `                'kann_tagschicht': ma.kann_tagschicht,`  
   Kann Tagdienst?

79. `                'kann_nachtschicht': ma.kann_nachtschicht,`  
   Kann Nachtdienst?

80. `                'nachtschicht_nur_wochenende': ma.nachtschicht_nur_wochenende,`  
   Nacht nur am Wochenende?

81. `                'nur_zusatzdienste_wochentags': ma.nur_zusatzdienste_wochentags,`  
   Zusatzdienste nur an Wochentagen?

82. `                'max_wochenenden_pro_monat': ma.max_wochenenden_pro_monat,`  
   Max. Wochenenden pro Monat.

83. `                'max_schichten_pro_monat': ma.max_schichten_pro_monat or 999,`  
   Max. Schichten/Monat, fallback 999.

84. `                'max_aufeinanderfolgende_tage': ma.max_aufeinanderfolgende_tage,`  
   Max. zusammenhängende Arbeitstage.

85. `                'verfuegbarkeit': ma.verfuegbarkeit,`  
   Verfügbarkeit (z. B. nur Wochenende).

86. `                'schicht_typ': schicht_typ,`  
   Typ A/B.

87. `                'planungs_prioritaet': ma.planungs_prioritaet,`  
   Priorität bei Wünschen.

88. `                'erlaubte_wochentage': clean_tage,       # immer Liste`  
   Erlaubte Tage als Liste.

89. `                'keine_zusatzdienste': keine_z           # immer bool`  
   Flag „keine Zusatzdienste“.

90. `            }`  
   Ende des Präferenz-Dicts.

91. `            `  
   Leerzeile.

92. `            self.preferences[ma.id] = pref`  
   Präferenzen in Map speichern.

93. `            `  
   Leerzeile.

94. `            # Debug-Ausgabe`  
   Kommentar: Debug-Infos.

95. `            debug_infos = []`  
   Liste für Debug-Messages.

96. `            if clean_tage:`  
   Wenn Tage gesetzt…

97. `                tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']`  
   Namen für Ausgabe.

98. `                debug_infos.append(f"NUR {','.join(tage_namen[t] for t in clean_tage if 0 <= t <= 6)}")`  
   Debug‑Text für erlaubte Tage.

99. `            if keine_z:`  
   Wenn „keine Zusatzdienste“ aktiv…

100. `                debug_infos.append("KEINE Z-Dienste")`  
    …Debug-Ausgabe ergänzen.

101. `            if debug_infos:`  
    Wenn Debug-Infos existieren…

102. `                print(f"      → {ma.schichtplan_kennung}: {', '.join(debug_infos)}")`  
    Ausgabe pro Mitarbeiter.

---

## Soll-Stunden laden

103. `    # ======================================================================`  
     Abschnitts-Trenner.

104. `    # SOLL-STUNDEN LADEN`  
     Abschnittstitel.

105. `    # ======================================================================`  
     Abschnitts-Trenner.

106. `    def _load_soll_stunden(self, jahr, monat):`  
     Methode: Soll-Stunden laden.

107. `        print("\n📊 Lade Soll-Stunden...")`  
     Ausgabe: Start.

108. `        soll_stunden_map = {}`  
     Map Mitarbeiter → Sollstunden.

109. `        soll_schichten_map = {}`  
     Map Mitarbeiter → Sollschichten.

110. `        `  
     Leerzeile.

111. `        avg_tag_stunden = float(self.type_t.arbeitszeit_stunden)`  
     Stunden pro Tag-Schicht.

112. `        avg_nacht_stunden = float(self.type_n.arbeitszeit_stunden)`  
     Stunden pro Nacht-Schicht.

113. `        avg_schicht_stunden = (avg_tag_stunden + avg_nacht_stunden) / 2`  
     Durchschnittliche Schichtlänge.

114. `        `  
     Leerzeile.

115. `        print(f"   Schichtlängen: T={avg_tag_stunden}h, N={avg_nacht_stunden}h")`  
     Info: Länge T/N.

116. `        print(f"   Ø Schichtlänge: {avg_schicht_stunden:.1f}h")`  
     Info: Durchschnitt.

117. `        `  
     Leerzeile.

118. `        for ma in self.mitarbeiter_list:`  
     Über alle Mitarbeiter.

119. `            soll_obj = MonatlicheArbeitszeitSoll.objects.filter(`  
     Query: Soll-Stunden Objekt suchen…

120. `                mitarbeiter=ma, jahr=jahr, monat=monat`  
     …für MA und Monat/Jahr.

121. `            ).first()`  
     Erstes Ergebnis oder `None`.

122. `            `  
     Leerzeile.

123. `            if soll_obj:`  
     Wenn gefunden…

124. `                soll_stunden = float(soll_obj.soll_stunden)`  
     Sollstunden übernehmen.

125. `            else:`  
     Wenn nicht gefunden…

126. `                soll_stunden = 144.0`  
     Fallback.

127. `                print(f"      {ma.schichtplan_kennung}: Fallback {soll_stunden}h (kein MonatlicheArbeitszeitSoll)")`  
     Warnung per Konsole.

128. `            `  
     Leerzeile.

129. `            soll_schichten = soll_stunden / avg_schicht_stunden`  
     Berechnung Sollschichten.

130. `            soll_stunden_map[ma.id] = soll_stunden`  
     Sollstunden speichern.

131. `            soll_schichten_map[ma.id] = round(soll_schichten)`  
     Sollschichten gerundet speichern.

132. `            print(f"      {ma.schichtplan_kennung}: {soll_stunden:.1f}h ÷ {avg_schicht_stunden:.1f}h = {round(soll_schichten)} Schichten")`  
     Debugausgabe je MA.

133. `        `  
     Leerzeile.

134. `        return soll_stunden_map, soll_schichten_map`  
     Rückgabe beider Maps.

---

## Hauptfunktion `generiere_vorschlag`

135. `    # ======================================================================`  
     Abschnitts-Trenner.

136. `    # HAUPTFUNKTION`  
     Abschnittstitel.

137. `    # ======================================================================`  
     Abschnitts-Trenner.

138. `    def generiere_vorschlag(self, neuer_schichtplan_obj):`  
     Hauptmethode: generiert Plan.

139. `        start_datum = neuer_schichtplan_obj.start_datum`  
     Startdatum aus Schichtplanobjekt.

140. `        `  
     Leerzeile.

141. `        if hasattr(neuer_schichtplan_obj, 'ende_datum') and neuer_schichtplan_obj.ende_datum:`  
     Prüfen, ob Ende explizit gesetzt.

142. `            ende_datum = neuer_schichtplan_obj.ende_datum`  
     Ende aus Objekt.

143. `        else:`  
     Sonst…

144. `            last_day = calendar.monthrange(start_datum.year, start_datum.month)[1]`  
     Letzter Tag des Monats.

145. `            ende_datum = start_datum.replace(day=last_day)`  
     Ende = letzter Tag.

146. `        `  
     Leerzeile.

147. `        current = start_datum`  
     Start für Tagesliste.

148. `        tage_liste = []`  
     Liste aller Tage.

149. `        while current <= ende_datum:`  
     Schleife über Zeitraum.

150. `            tage_liste.append(current)`  
     Tag hinzufügen.

151. `            current += datetime.timedelta(days=1)`  
     Einen Tag weiter.

152. `        `  
     Leerzeile.

153. `        print(f"\n{'='*70}")`  
     Header-Zeile.

154. `        print(f"🚀 GENERIERE PLAN: {len(tage_liste)} Tage ({start_datum} bis {tage_liste[-1]})")`  
     Startausgabe mit Zeitraum.

155. `        print(f"{'='*70}\n")`  
     Abschlusslinie.

---

## Wünsche laden

156. `        # ====================================================================`  
     Abschnitts-Trenner.

157. `        # WÜNSCHE LADEN`  
     Abschnittstitel.

158. `        # ====================================================================`  
     Abschnitts-Trenner.

159. `        print("🗓️ Lade Schichtwünsche...")`  
     Statusausgabe.

160. `        `  
     Leerzeile.

161. `        wuensche = Schichtwunsch.objects.filter(`  
     Query: Wünsche im Zeitraum…

162. `            datum__gte=start_datum,`  
     …ab Startdatum.

163. `            datum__lte=ende_datum,`  
     …bis Enddatum.

164. `            mitarbeiter__in=self.mitarbeiter_list`  
     …für relevante Mitarbeiter.

165. `        ).select_related('mitarbeiter')`  
     Optimierung: Mitarbeiter gleich mitladen.

166. `        `  
     Leerzeile.

167. `        print(f"   Zeitraum: {start_datum} bis {ende_datum}")`  
     Debugzeitraum.

168. `        print(f"   Gefunden: {wuensche.count()} Wünsche")`  
     Anzahl Wünsche.

169. `        `  
     Leerzeile.

170. `        wuensche_matrix = defaultdict(dict)`  
     Wünsche-Matrix (ma_id → datum → wunsch).

171. `        urlaubs_tage = defaultdict(list)`  
     Urlaubstage je MA.

172. `        `  
     Leerzeile.

173. `        for w in wuensche:`  
     Schleife über Wünsche.

174. `            wuensche_matrix[w.mitarbeiter.id][w.datum] = w`  
     Wunsch in Matrix speichern.

175. `            print(f"      → {w.mitarbeiter.schichtplan_kennung}: {w.wunsch} am {w.datum}")`  
     Debugausgabe je Wunsch.

176. `            if w.wunsch == 'urlaub':`  
     Wenn Urlaub…

177. `                urlaubs_tage[w.mitarbeiter.id].append(w.datum)`  
     …Tag als Urlaub markieren.

178. `            elif w.wunsch == 'gar_nichts' and w.genehmigt:`  
     Wenn „gar_nichts“ + genehmigt…

179. `                urlaubs_tage[w.mitarbeiter.id].append(w.datum)`  
     …auch als Urlaubstag werten.

---

## Soll‑Stunden laden

180. `        # ====================================================================`  
     Abschnitts-Trenner.

181. `        # SOLL-STUNDEN LADEN`  
     Abschnittstitel.

182. `        # ====================================================================`  
     Abschnitts-Trenner.

183. `        jahr = start_datum.year`  
     Jahr ermitteln.

184. `        monat = start_datum.month`  
     Monat ermitteln.

185. `        soll_stunden_map, soll_schichten_map = self._load_soll_stunden(jahr, monat)`  
     Soll-Stunden/Schichten laden.

186. `        `  
     Leerzeile.

187. `        last_shifts = {}`  
     Map für letzte Schichten (hier nicht befüllt).

---

## Solver Setup (Variablen)

188. `        # ====================================================================`  
     Abschnitts-Trenner.

189. `        # SOLVER SETUP`  
     Abschnittstitel.

190. `        # ====================================================================`  
     Abschnitts-Trenner.

191. `        model = cp_model.CpModel()`  
     Neues CP-SAT Modell.

192. `        vars_schichten = {}`  
     Container für Bool-Variablen.

193. `        `  
     Leerzeile.

194. `        print("\n🔧 Erstelle Constraint-Modell...")`  
     Debugausgabe.

195. `        `  
     Leerzeile.

196. `        for ma in self.mitarbeiter_list:`  
     Schleife über Mitarbeiter…

197. `            for tag in tage_liste:`  
     …über Tage…

198. `                for stype in self.target_shifts:`  
     …über Schichttypen T/N.

199. `                    vars_schichten[(ma.id, tag, stype.kuerzel)] = model.NewBoolVar(f'{ma.id}_{tag}_{stype.kuerzel}')`  
     Bool‑Variable „MA arbeitet in Typ“.

200. `                vars_schichten[(ma.id, tag, 'Frei')] = model.NewBoolVar(f'{ma.id}_{tag}_Frei')`  
     Bool‑Variable „MA hat frei“.

---

## A. Basis‑Constraints

201. `        # ====================================================================`  
     Abschnitts-Trenner.

202. `        # A. BASIS-CONSTRAINTS`  
     Abschnittstitel.

203. `        # ====================================================================`  
     Abschnitts-Trenner.

204. `        print("   ✓ Basis-Regeln")`  
     Statusausgabe.

205. `        `  
     Leerzeile.

206. `        for ma in self.mitarbeiter_list:`  
     Schleife über Mitarbeiter.

207. `            for tag in tage_liste:`  
     Schleife über Tage.

208. `                all_options = [vars_schichten[(ma.id, tag, st.kuerzel)] for st in self.target_shifts]`  
     Alle Schicht-Optionen (T/N) sammeln.

209. `                all_options.append(vars_schichten[(ma.id, tag, 'Frei')])`  
     „Frei“ als Option ergänzen.

210. `                model.Add(sum(all_options) == 1)`  
     Genau eine Option pro Tag.

211. `            `  
     Leerzeile.

212. `            # Nacht → nächster Tag keine Tagschicht`  
     Kommentar zur Regel.

213. `            for i in range(len(tage_liste) - 1):`  
     Alle Tage außer letzter.

214. `                heute = tage_liste[i]`  
     Heute.

215. `                morgen = tage_liste[i+1]`  
     Morgen.

216. `                model.Add(`  
     Constraint beginnt.

217. `                    vars_schichten[(ma.id, morgen, 'T')] == 0`  
     Morgen keine Tag-Schicht…

218. `                ).OnlyEnforceIf(vars_schichten[(ma.id, heute, 'N')])`  
     …nur wenn heute Nacht-Schicht.

219. `        `  
     Leerzeile.

220. `        if tage_liste:`  
     Falls Tage existieren…

221. `            erster_tag = tage_liste[0]`  
     Erster Tag.

222. `            for ma_id, last_k in last_shifts.items():`  
     Über letzte Schichten iterieren (falls befüllt).

223. `                if last_k == 'N' and (ma_id, erster_tag, 'T') in vars_schichten:`  
     Wenn letzte Schicht Nacht war…

224. `                    model.Add(vars_schichten[(ma_id, erster_tag, 'T')] == 0)`  
     …am ersten Tag keine Tag-Schicht.

---

## B. Präferenzen & Wünsche

225. `        # ====================================================================`  
     Abschnitts-Trenner.

226. `        # B. MITARBEITER-PRÄFERENZEN + WÜNSCHE`  
     Abschnittstitel.

227. `        # ====================================================================`  
     Abschnitts-Trenner.

228. `        print("   ✓ Präferenzen & Wünsche")`  
     Statusausgabe.

229. `        `  
     Leerzeile.

230. `        for ma in self.mitarbeiter_list:`  
     Schleife über Mitarbeiter.

231. `            pref = self.preferences[ma.id]`  
     Präferenzen holen.

232. `            `  
     Leerzeile.

233. `            # B.1 KANN NICHT TAGSCHICHT`  
     Kommentar.

234. `            if not pref['kann_tagschicht']:`  
     Wenn Tagdienst verboten…

235. `                for tag in tage_liste:`  
     …für jeden Tag…

236. `                    model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)`  
     …Tagdienst = 0.

237. `            `  
     Leerzeile.

238. `            # B.2 KANN NICHT NACHTSCHICHT`  
     Kommentar.

239. `            if not pref['kann_nachtschicht']:`  
     Wenn Nachtdienst verboten…

240. `                for tag in tage_liste:`  
     …für jeden Tag…

241. `                    model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     …Nachtdienst = 0.

242. `            `  
     Leerzeile.

243. `            # B.3 NACHTSCHICHT NUR WOCHENENDE`  
     Kommentar.

244. `            if pref['nachtschicht_nur_wochenende']:`  
     Wenn Nacht nur Wochenende…

245. `                for tag in tage_liste:`  
     …für jeden Tag…

246. `                    if tag.weekday() < 5:  # Mo-Fr`  
     Werktag?

247. `                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     Nacht am Werktag verboten.

248. `            `  
     Leerzeile.

249. `            # B.4 NUR ZUSATZDIENSTE WOCHENTAGS`  
     Kommentar.

250. `            if pref['nur_zusatzdienste_wochentags']:`  
     Wenn nur Zusatzdienste wochentags…

251. `                for tag in tage_liste:`  
     …für jeden Tag…

252. `                    if tag.weekday() < 5:  # Mo-Fr`  
     Werktag?

253. `                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)`  
     Tagdienst verboten.

254. `                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     Nachtdienst verboten.

255. `            `  
     Leerzeile.

256. `            # B.5 VERFÜGBARKEIT`  
     Kommentar.

257. `            if pref['verfuegbarkeit'] == 'wochenende_only':`  
     Wenn nur Wochenende…

258. `                for tag in tage_liste:`  
     …für jeden Tag…

259. `                    if tag.weekday() < 5:`  
     Werktag?

260. `                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)`  
     Tagdienst verboten.

261. `                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     Nachtdienst verboten.

262. `            elif pref['verfuegbarkeit'] == 'wochentags_only':`  
     Wenn nur wochentags…

263. `                for tag in tage_liste:`  
     …für jeden Tag…

264. `                    if tag.weekday() >= 5:`  
     Wochenende?

265. `                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)`  
     Tagdienst verboten.

266. `                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     Nachtdienst verboten.

267. `            `  
     Leerzeile.

268. `            # B.6 MAX WOCHENENDEN`  
     Kommentar.

269. `            max_we = pref['max_wochenenden_pro_monat']`  
     Max Wochenenden.

270. `            wochenenden = []`  
     Liste der Wochenenden.

271. `            current_we = None`  
     Hilfsvariable.

272. `            for tag in tage_liste:`  
     Schleife über Tage.

273. `                if tag.weekday() >= 5:`  
     Wochenende?

274. `                    week_num = tag.isocalendar()[1]`  
     Kalenderwoche.

275. `                    if current_we != week_num:`  
     Neues Wochenende?

276. `                        current_we = week_num`  
     Aktualisieren.

277. `                        wochenenden.append([])`  
     Neue Wochenendliste anlegen.

278. `                    wochenenden[-1].append(tag)`  
     Tag ins aktuelle Wochenende.

279. `            `  
     Leerzeile.

280. `            if max_we < len(wochenenden):`  
     Wenn Limit niedriger als Anzahl Wochenenden…

281. `                we_vars = []`  
     Bool-Variablen je Wochenende.

282. `                for we_tage in wochenenden:`  
     Für jedes Wochenende…

283. `                    we_var = model.NewBoolVar(f'{ma.id}_we_{we_tage[0]}')`  
     Bool: „arbeitet an diesem Wochenende“.

284. `                    schichten_am_we = []`  
     Schichten am Wochenende sammeln.

285. `                    for tag in we_tage:`  
     Für alle Tage des Wochenendes…

286. `                        for stype in self.target_shifts:`  
     …für T/N…

287. `                            schichten_am_we.append(vars_schichten[(ma.id, tag, stype.kuerzel)])`  
     …Variablen sammeln.

288. `                    model.Add(sum(schichten_am_we) >= 1).OnlyEnforceIf(we_var)`  
     we_var = 1 ⇒ mind. 1 Schicht am Wochenende.

289. `                    model.Add(sum(schichten_am_we) == 0).OnlyEnforceIf(we_var.Not())`  
     we_var = 0 ⇒ keine Schicht.

290. `                    we_vars.append(we_var)`  
     we_var sammeln.

291. `                model.Add(sum(we_vars) <= max_we)`  
     Maximal erlaubte Wochenenden.

292. `            `  
     Leerzeile.

293. `            # B.7 MAX SCHICHTEN PRO MONAT`  
     Kommentar.

294. `            if pref['max_schichten_pro_monat'] < 999:`  
     Nur wenn Limit gesetzt…

295. `                alle_schichten = []`  
     Liste aller Schichtvariablen.

296. `                for tag in tage_liste:`  
     Für jeden Tag…

297. `                    for stype in self.target_shifts:`  
     …für T/N…

298. `                        alle_schichten.append(vars_schichten[(ma.id, tag, stype.kuerzel)])`  
     Variable sammeln.

299. `                model.Add(sum(alle_schichten) <= pref['max_schichten_pro_monat'])`  
     Maximal-Schichten-Constraint.

300. `            `  
     Leerzeile.

301. `            # B.8 MAX AUFEINANDERFOLGENDE TAGE`  
     Kommentar.

302. `            max_tage = pref['max_aufeinanderfolgende_tage']`  
     Limit der Streak.

303. `            if max_tage and max_tage > 0:`  
     Falls gesetzt und > 0…

304. `                for i in range(len(tage_liste) - max_tage):`  
     Gleitfenster über Tage.

305. `                    fenster = []`  
     Liste Schichten im Fenster.

306. `                    for j in range(max_tage + 1):`  
     Fenstergröße = max_tage+1.

307. `                        tag = tage_liste[i + j]`  
     Aktueller Tag im Fenster.

308. `                        for stype in self.target_shifts:`  
     Für T/N…

309. `                            fenster.append(vars_schichten[(ma.id, tag, stype.kuerzel)])`  
     Schichtvariable sammeln.

310. `                    model.Add(sum(fenster) <= max_tage)`  
     Nicht mehr als max_tage in diesem Fenster.

311. `            `  
     Leerzeile.

312. `            # B.9 TYP B - MINDESTENS 4T + 4N (MIT SICHERHEITS-CHECK)`  
     Kommentar.

313. `            # NUR EINMAL! (vorher war es doppelt)`  
     Hinweis zur Korrektur.

314. `            if pref['schicht_typ'] == 'typ_b':`  
     Nur Typ B.

315. `                tag_schichten = [vars_schichten[(ma.id, tag, 'T')] for tag in tage_liste]`  
     Alle Tag-Schichten des MA.

316. `                nacht_schichten = [vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste]`  
     Alle Nacht-Schichten des MA.

317. `                `  
     Leerzeile.

318. `                verfuegbare_tage_count = 0`  
     Zähler verfügbarer Tage.

319. `                for tag in tage_liste:`  
     Für jeden Tag…

320. `                    wunsch = wuensche_matrix.get(ma.id, {}).get(tag)`  
     Wunsch für diesen Tag.

321. `                    is_blocked = (wunsch and wunsch.wunsch in ['urlaub', 'gar_nichts'] and wunsch.genehmigt)`  
     Blockiert, wenn Urlaub/gar_nichts genehmigt.

322. `                    if not is_blocked:`  
     Wenn nicht blockiert…

323. `                        verfuegbare_tage_count += 1`  
     Zähler erhöhen.

324. `                `  
     Leerzeile.

325. `                if verfuegbare_tage_count >= 10:`  
     Nur wenn genug Tage verfügbar…

326. `                    model.Add(sum(tag_schichten) >= 4)`  
     Mindestens 4 Tag-Schichten.

327. `                    model.Add(sum(nacht_schichten) >= 4)`  
     Mindestens 4 Nacht-Schichten.

328. `                else:`  
     Wenn zu wenig Tage…

329. `                    print(f"      ⚠️ {ma.schichtplan_kennung}: Typ B Regel ausgesetzt ({verfuegbare_tage_count} Tage verfügbar)")`  
     Hinweis: Regel deaktiviert.

330. `            `  
     Leerzeile.

331. `            # B.10 URLAUB / GAR NICHTS → Frei erzwingen`  
     Kommentar.

332. `            for tag in tage_liste:`  
     Für jeden Tag…

333. `                wunsch = wuensche_matrix.get(ma.id, {}).get(tag)`  
     Wunsch holen.

334. `                if wunsch and wunsch.wunsch in ['urlaub', 'gar_nichts'] and wunsch.genehmigt:`  
     Wenn Urlaub/gar_nichts genehmigt…

335. `                    model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)`  
     Tag-Schicht verbieten.

336. `                    model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     Nacht-Schicht verbieten.

337. `                    model.Add(vars_schichten[(ma.id, tag, 'Frei')] == 1)`  
     Frei erzwingen.

338. `            `  
     Leerzeile.

339. `            # B.11 ERLAUBTE WOCHENTAGE (HARD CONSTRAINT)`  
     Kommentar.

340. `            erlaubte_tage = pref['erlaubte_wochentage']  # immer Liste (kann leer sein)`  
     Erlaubte Tage holen.

341. `            `  
     Leerzeile.

342. `            if erlaubte_tage:  # nur wenn nicht leer`  
     Nur wenn Liste nicht leer…

343. `                tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']`  
     Wochentagsnamen.

344. `                sichtbare_tage = [tage_namen[t] for t in erlaubte_tage if 0 <= t <= 6]`  
     Liste der erlaubten Namen.

345. `                print(f"      ✓ CONSTRAINT: {ma.schichtplan_kennung} nur an {','.join(sichtbare_tage)}")`  
     Debugausgabe.

346. `                `  
     Leerzeile.

347. `                for tag in tage_liste:`  
     Für jeden Tag…

348. `                    if tag.weekday() not in erlaubte_tage:`  
     Wenn nicht erlaubt…

349. `                        model.Add(vars_schichten[(ma.id, tag, 'T')] == 0)`  
     Tag-Schicht verbieten.

350. `                        model.Add(vars_schichten[(ma.id, tag, 'N')] == 0)`  
     Nacht-Schicht verbieten.

---

## C. Besetzung – Soft Target

351. `        # ====================================================================`  
     Abschnitts-Trenner.

352. `        # C. BESETZUNG - SOFT TARGET (Ziel: 2 pro Schicht)`  
     Abschnittstitel.

353. `        # ====================================================================`  
     Abschnitts-Trenner.

354. `        print("   ✓ Besetzung (Ziel: 2, erlaubt: 0-4)")`  
     Statusausgabe.

355. `        `  
     Leerzeile.

356. `        objective_terms = []  # hier initialisieren`  
     Liste der Zielfunktions-Terme.

357. `        `  
     Leerzeile.

358. `        for tag in tage_liste:`  
     Für jeden Tag…

359. `            for stype in ['T', 'N']:`  
     …für T und N.

360. `                schichten_pro_typ = [vars_schichten[(m.id, tag, stype)] for m in self.mitarbeiter_list]`  
     Alle MA‑Variablen für diesen Tag/Typ.

361. `                summe_var = model.NewIntVar(0, 12, f'summe_{tag}_{stype}')`  
     Int‑Variable für Anzahl der Schichten.

362. `                model.Add(summe_var == sum(schichten_pro_typ))`  
     Summe der Bool-Variablen = Anzahl.

363. `                `  
     Leerzeile.

364. `                model.Add(summe_var >= 0)`  
     Untergrenze (redundant, aber klar).

365. `                model.Add(summe_var <= 4)`  
     Obergrenze: max 4.

366. `                `  
     Leerzeile.

367. `                # Abweichung von Ziel 2 bestrafen`  
     Kommentar.

368. `                abweichung = model.NewIntVar(0, 4, f'abweichung_{tag}_{stype}')`  
     Variable für Abweichung.

369. `                model.Add(abweichung >= summe_var - 2)`  
     Abweichung ≥ (Anzahl − 2).

370. `                model.Add(abweichung >= 2 - summe_var)`  
     Abweichung ≥ (2 − Anzahl).

371. `                objective_terms.append(abweichung * 50000)`  
     Abweichung stark bestrafen.

372. `                `  
     Leerzeile.

373. `                # Leere Schicht = Extremstrafe`  
     Kommentar.

374. `                ist_null = model.NewBoolVar(f'{tag}_{stype}_ist_null')`  
     Bool: Schicht ist leer.

375. `                model.Add(summe_var == 0).OnlyEnforceIf(ist_null)`  
     ist_null ⇒ Summe = 0.

376. `                model.Add(summe_var > 0).OnlyEnforceIf(ist_null.Not())`  
     nicht ist_null ⇒ Summe > 0.

377. `                objective_terms.append(ist_null * 1000000)`  
     Leere Schicht sehr stark bestrafen.

---

## E. Optimierungsziel

378. `        # ====================================================================`  
     Abschnitts-Trenner.

379. `        # E. OPTIMIERUNGSZIEL`  
     Abschnittstitel.

380. `        # ====================================================================`  
     Abschnitts-Trenner.

381. `        print("   ✓ Optimierungsziel (Wünsche + Soll-Stunden)")`  
     Statusausgabe.

382. `        `  
     Leerzeile.

383. `        for ma in self.mitarbeiter_list:`  
     Für jeden Mitarbeiter…

384. `            pref = self.preferences[ma.id]`  
     Präferenzen holen.

385. `            soll_schichten = soll_schichten_map.get(ma.id, 10)`  
     Soll‑Schichten (Fallback 10).

386. `            `  
     Leerzeile.

387. `            # --- E.1 SOLL-STUNDEN (Abweichung bestrafen) ---`  
     Kommentar.

388. `            normale_schichten = []`  
     Liste normaler Schichten.

389. `            for tag in tage_liste:`  
     Für jeden Tag…

390. `                if tag not in urlaubs_tage.get(ma.id, []):`  
     Nur wenn kein Urlaubstag…

391. `                    for stype in ['T', 'N']:`  
     …für T/N…

392. `                        normale_schichten.append(vars_schichten[(ma.id, tag, stype)])`  
     Variable hinzufügen.

393. `            `  
     Leerzeile.

394. `            ist_schichten_var = model.NewIntVar(0, 100, f'{ma.id}_ist_schichten')`  
     Int‑Var für tatsächliche Schichten.

395. `            model.Add(ist_schichten_var == sum(normale_schichten))`  
     Summe der Schichten.

396. `            `  
     Leerzeile.

397. `            abweichung_var = model.NewIntVar(-100, 100, f'{ma.id}_abweichung')`  
     Abweichung (mit Vorzeichen).

398. `            model.Add(abweichung_var == ist_schichten_var - soll_schichten)`  
     Abweichung = Ist − Soll.

399. `            `  
     Leerzeile.

400. `            abs_abweichung = model.NewIntVar(0, 100, f'{ma.id}_abs_abweichung')`  
     Absolutwert.

401. `            model.AddAbsEquality(abs_abweichung, abweichung_var)`  
     abs_abweichung = |abweichung_var|.

402. `            objective_terms.append(abs_abweichung * 2000)`  
     Abweichung bestrafen.

403. `            `  
     Leerzeile.

404. `            # --- E.2 WÜNSCHE ---`  
     Kommentar.

405. `            for tag in tage_liste:`  
     Für jeden Tag…

406. `                wunsch = wuensche_matrix.get(ma.id, {}).get(tag)`  
     Wunsch für diesen Tag.

407. `                `  
     Leerzeile.

408. `                for stype in self.target_shifts:`  
     Für jeden Schichttyp T/N…

409. `                    kuerzel = stype.kuerzel`  
     Kürzel `T` oder `N`.

410. `                    score = 0`  
     Score initial.

411. `                    `  
     Leerzeile.

412. `                    if wunsch:`  
     Wenn es einen Wunsch gibt…

413. `                        if wunsch.wunsch == 'tag_bevorzugt':`  
     Wunsch: Tag bevorzugt.

414. `                            score = -25000 if kuerzel == 'T' else 25000`  
     Tagdienst belohnen (negativ minimiert), Nacht bestrafen.

415. `                        elif wunsch.wunsch == 'nacht_bevorzugt':`  
     Wunsch: Nacht bevorzugt.

416. `                            score = -25000 if kuerzel == 'N' else 25000`  
     Nacht belohnen, Tag bestrafen.

417. `                        elif wunsch.wunsch == 'zusatzarbeit':`  
     Wunsch: Zusatzarbeit.

418. `                            score = -5000`  
     Leichter Bonus.

419. `                        elif wunsch.wunsch in ['urlaub', 'gar_nichts'] and wunsch.genehmigt:`  
     Urlaub/gar_nichts genehmigt…

420. `                            score = 1000000  # sollte durch B.10 nicht nötig sein, aber Safety`  
     Sehr hohe Strafe als Safety.

421. `                    `  
     Leerzeile.

422. `                    # Planungs-Priorität als Multiplikator`  
     Kommentar.

423. `                    if pref['planungs_prioritaet'] == 'hoch':`  
     Hohe Priorität…

424. `                        score = int(score * 1.5)`  
     Score erhöhen.

425. `                    elif pref['planungs_prioritaet'] == 'niedrig':`  
     Niedrige Priorität…

426. `                        score = int(score * 0.8)`  
     Score reduzieren.

427. `                    `  
     Leerzeile.

428. `                    if score != 0:`  
     Nur wenn Score != 0…

429. `                        objective_terms.append(vars_schichten[(ma.id, tag, kuerzel)] * score)`  
     Score zur Zielfunktion hinzufügen.

430. `        `  
     Leerzeile.

431. `        model.Minimize(sum(objective_terms))`  
     Zielfunktion: Summe minimieren.

---

## F. Solver starten

432. `        # ====================================================================`  
     Abschnitts-Trenner.

433. `        # F. SOLVER STARTEN`  
     Abschnittstitel.

434. `        # ====================================================================`  
     Abschnitts-Trenner.

435. `        print("\n" + "="*70)`  
     Ausgabe: Trenner.

436. `        print("🔍 CONSTRAINT-ANALYSE")`  
     Überschrift.

437. `        print("="*70)`  
     Zweite Trennerzeile.

438. `        print(f"Zeitraum: {len(tage_liste)} Tage | Mitarbeiter: {len(self.mitarbeiter_list)}")`  
     Ausgabe: Tage/Mitarbeiter.

439. `        `  
     Leerzeile.

440. `        kann_tag = sum(1 for ma in self.mitarbeiter_list if self.preferences[ma.id]['kann_tagschicht'])`  
     Zählt MA, die Tagdienst können.

441. `        kann_nacht = sum(1 for ma in self.mitarbeiter_list if self.preferences[ma.id]['kann_nachtschicht'])`  
     Zählt MA, die Nachtdienst können.

442. `        print(f"Können Tagschicht: {kann_tag} | Können Nachtschicht: {kann_nacht}")`  
     Ausgabe der Summen.

443. `        `  
     Leerzeile.

444. `        urlaubs_gesamt = sum(len(tage) for tage in urlaubs_tage.values())`  
     Gesamtzahl Urlaubstage.

445. `        print(f"Urlaubstage gesamt: {urlaubs_gesamt}")`  
     Ausgabe.

446. `        `  
     Leerzeile.

447. `        typ_b_mas = [ma for ma in self.mitarbeiter_list if self.preferences[ma.id]['schicht_typ'] == 'typ_b']`  
     Liste Typ-B Mitarbeiter.

448. `        if typ_b_mas:`  
     Falls es welche gibt…

449. `            print(f"Typ B: {len(typ_b_mas)} Mitarbeiter")`  
     Anzahl Typ B ausgeben.

450. `            for ma in typ_b_mas:`  
     Für jeden Typ-B MA…

451. `                verfuegbar = len(tage_liste) - len(urlaubs_tage.get(ma.id, []))`  
     Verfügbare Tage = Gesamt − Urlaub.

452. `                print(f"   {ma.schichtplan_kennung}: {verfuegbar} Tage verfügbar")`  
     Ausgabe je MA.

453. `        `  
     Leerzeile.

454. `        print("="*70 + "\n")`  
     Abschluss-Trenner.

455. `        `  
     Leerzeile.

456. `        print("⚙️ Starte Solver...")`  
     Startmeldung.

457. `        solver = cp_model.CpSolver()`  
     Solver-Instanz.

458. `        solver.parameters.max_time_in_seconds = 360.0`  
     Zeitlimit.

459. `        status = solver.Solve(model)`  
     Modell lösen.

460. `        print(f"   Status: {solver.StatusName(status)}")`  
     Solver-Status ausgeben.

---

## G. Ergebnisse speichern

461. `        # ====================================================================`  
     Abschnitts-Trenner.

462. `        # G. ERGEBNISSE SPEICHERN`  
     Abschnittstitel.

463. `        # ====================================================================`  
     Abschnitts-Trenner.

464. `        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:`  
     Nur wenn Lösung gefunden.

465. `            print(f"\n✅ Lösung gefunden! Status: {solver.StatusName(status)}\n")`  
     Erfolgsausgabe.

466. `            `  
     Leerzeile.

467. `            ergebnis_count = 0`  
     Zähler gespeicherter Schichten.

468. `            ist_schichten_pro_ma = defaultdict(int)`  
     Map MA → Anzahl Schichten.

469. `            `  
     Leerzeile.

470. `            for ma in self.mitarbeiter_list:`  
     Für jeden Mitarbeiter…

471. `                for tag in tage_liste:`  
     …für jeden Tag…

472. `                    if solver.Value(vars_schichten[(ma.id, tag, 'T')]) == 1:`  
     Wenn Tag-Schicht gewählt…

473. `                        Schicht.objects.create(`  
     Schicht-Datensatz anlegen.

474. `                            schichtplan=neuer_schichtplan_obj,`  
     Zuordnung Schichtplan.

475. `                            mitarbeiter=ma, datum=tag, schichttyp=self.type_t`  
     MA, Datum, Typ T.

476. `                        )`  
     Ende create.

477. `                        ergebnis_count += 1`  
     Zähler erhöhen.

478. `                        ist_schichten_pro_ma[ma.id] += 1`  
     MA-Zähler erhöhen.

479. `                    elif solver.Value(vars_schichten[(ma.id, tag, 'N')]) == 1:`  
     Sonst wenn Nacht-Schicht gewählt…

480. `                        Schicht.objects.create(`  
     Schicht anlegen.

481. `                            schichtplan=neuer_schichtplan_obj,`  
     Zuordnung.

482. `                            mitarbeiter=ma, datum=tag, schichttyp=self.type_n`  
     Typ N.

483. `                        )`  
     Ende create.

484. `                        ergebnis_count += 1`  
     Zähler erhöhen.

485. `                        ist_schichten_pro_ma[ma.id] += 1`  
     MA-Zähler erhöhen.

486. `            `  
     Leerzeile.

487. `            print(f"💾 {ergebnis_count} Schichten gespeichert.")`  
     Ausgabe: Anzahl gespeicherter Schichten.

---

## H. Zusatzdienste generieren

488. `            # ================================================================`  
     Abschnitts-Trenner.

489. `            # H. ZUSATZDIENSTE GENERIEREN`  
     Abschnittstitel.

490. `            # ================================================================`  
     Abschnitts-Trenner.

491. `            if self.type_z:`  
     Nur wenn Z-Schichttyp existiert.

492. `                print("\n➕ Generiere Zusatzdienste zum Auffüllen...")`  
     Statusausgabe.

493. `                `  
     Leerzeile.

494. `                z_ist_tag = True `  
     Annahme: Z ist Tagdienst.

495. `                if self.type_z.start_zeit and self.type_z.start_zeit.hour >= 18: `  
     Wenn Startzeit ab 18 Uhr…

496. `                    z_ist_tag = False`  
     …dann als Nachtdienst behandeln.

497. `                `  
     Leerzeile.

498. `                zusatz_count = 0`  
     Zähler Z‑Dienste.

499. `                ma_bedarf = []`  
     Liste der MA mit Bedarf.

500. `                `  
     Leerzeile.

501. `                for ma in self.mitarbeiter_list:`  
     Für jeden MA…

502. `                    pref = self.preferences[ma.id]`  
     Präferenzen holen.

503. `                    `  
     Leerzeile.

504. `                    # SKIP: keine_zusatzdienste`  
     Kommentar.

505. `                    if pref['keine_zusatzdienste']:`  
     Wenn keine Z erlaubt…

506. `                        print(f"   ⏭️  {ma.schichtplan_kennung}: Übersprungen (Vereinbarung: keine Z)")`  
     Überspringen mit Ausgabe.

507. `                        continue`  
     Nächster MA.

508. `                        `  
     Leerzeile (im Code).

509. `                    # SKIP: Kann Schichttyp nicht`  
     Kommentar.

510. `                    if z_ist_tag and not pref['kann_tagschicht']:`  
     Tagdienst-Z aber MA kann Tag nicht…

511. `                        continue`  
     Überspringen.

512. `                    if not z_ist_tag and not pref['kann_nachtschicht']:`  
     Nachtdienst-Z aber MA kann Nacht nicht…

513. `                        continue`  
     Überspringen.

514. `                    `  
     Leerzeile.

515. `                    soll = soll_schichten_map.get(ma.id, 10)`  
     Soll-Schichten.

516. `                    ist = ist_schichten_pro_ma[ma.id]`  
     Ist-Schichten.

517. `                    fehlt = soll - ist`  
     Fehlende Schichten.

518. `                    `  
     Leerzeile.

519. `                    if fehlt > 0:`  
     Nur wenn Bedarf.

520. `                        erlaubte_tage = pref['erlaubte_wochentage']  # Liste oder leer`  
     Erlaubte Tage.

521. `                        freie_tage = []`  
     Liste freier Tage.

522. `                        `  
     Leerzeile.

523. `                        for tag in tage_liste:`  
     Für jeden Tag…

524. `                            # Nur Di-Fr für Z`  
     Kommentar.

525. `                            if tag.weekday() not in [1, 2, 3, 4]:`  
     Falls nicht Di‑Fr…

526. `                                continue`  
     Überspringen.

527. `                            # Kein Urlaub`  
     Kommentar.

528. `                            if tag in urlaubs_tage.get(ma.id, []):`  
     Wenn Urlaub…

529. `                                continue`  
     Überspringen.

530. `                            # Erlaubte Wochentage prüfen`  
     Kommentar.

531. `                            if erlaubte_tage and tag.weekday() not in erlaubte_tage:`  
     Wenn Tag nicht erlaubt…

532. `                                continue`  
     Überspringen.

533. `                            # Muss "Frei" sein`  
     Kommentar.

534. `                            if solver.Value(vars_schichten[(ma.id, tag, 'Frei')]) == 1:`  
     Nur wenn an diesem Tag „Frei“.

535. `                                `  
     Leerzeile.

536. `                                # Safety: Kein Z nach Nachtschicht`  
     Kommentar.

537. `                                gestern = tag - datetime.timedelta(days=1)`  
     Gestern.

538. `                                if gestern in tage_liste:`  
     Wenn gestern im Zeitraum…

539. `                                    if solver.Value(vars_schichten[(ma.id, gestern, 'N')]) == 1:`  
     …und gestern Nacht-Schicht…

540. `                                        continue`  
     …dann kein Z.

541. `                                `  
     Leerzeile.

542. `                                # Safety: Max aufeinanderfolgende Tage prüfen`  
     Kommentar.

543. `                                # Zähle nur TATSÄCHLICH zugewiesene Schichten (T/N vom Solver)`  
     Kommentar.

544. `                                # Z-Dienste die WIR gerade vergeben werden HIER noch nicht gezählt`  
     Kommentar.

545. `                                morgen = tag + datetime.timedelta(days=1)`  
     Morgen.

546. `                                work_streak = 1`  
     Start Streak.

547. `                                `  
     Leerzeile.

548. `                                check_tag = gestern`  
     Start rückwärts.

549. `                                while check_tag in tage_liste:`  
     Solange Tag im Zeitraum…

550. `                                    if solver.Value(vars_schichten[(ma.id, check_tag, 'Frei')]) == 0:`  
     Wenn gearbeitet…

551. `                                        work_streak += 1`  
     Streak erhöhen.

552. `                                    else:`  
     Sonst…

553. `                                        break`  
     …Streak beenden.

554. `                                    check_tag -= datetime.timedelta(days=1)`  
     Einen Tag zurück.

555. `                                `  
     Leerzeile.

556. `                                check_tag = morgen`  
     Vorwärts prüfen.

557. `                                while check_tag in tage_liste:`  
     Solange im Zeitraum…

558. `                                    if solver.Value(vars_schichten[(ma.id, check_tag, 'Frei')]) == 0:`  
     Wenn gearbeitet…

559. `                                        work_streak += 1`  
     Streak erhöhen.

560. `                                    else:`  
     Sonst…

561. `                                        break`  
     …Streak beenden.

562. `                                    check_tag += datetime.timedelta(days=1)`  
     Einen Tag vor.

563. `                                `  
     Leerzeile.

564. `                                max_tage = pref['max_aufeinanderfolgende_tage'] or 999`  
     Max-Streak Limit.

565. `                                if work_streak > max_tage:`  
     Wenn überschritten…

566. `                                    continue`  
     …Z nicht vergeben.

567. `                                `  
     Leerzeile.

568. `                                freie_tage.append(tag)`  
     Tag als freier Z‑Kandidat.

569. `                        `  
     Leerzeile.

570. `                        if freie_tage:`  
     Wenn es freie Tage gibt…

571. `                            ma_bedarf.append({`  
     MA in Bedarfsliste eintragen.

572. `                                'ma': ma,`  
     Mitarbeiter.

573. `                                'bedarf': fehlt,`  
     Benötigte Schichten.

574. `                                'zugewiesen': 0,`  
     Bisher zugewiesen.

575. `                                'freie_tage': freie_tage`  
     Kandidaten-Tage.

576. `                            })`  
     Ende Dict.

577. `                            print(f"   {ma.schichtplan_kennung}: fehlt {fehlt} Schichten, {len(freie_tage)} Tage verfügbar")`  
     Debugausgabe.

---

## H.2 Verteilung Zusatzdienste

578. `                # ============================================================`  
     Abschnitts-Trenner.

579. `                # H.2 VERTEILUNG: Pro-MA Durchlauf, max 2 Z pro Tag`  
     Abschnittstitel.

580. `                # ============================================================`  
     Abschnitts-Trenner.

581. `                if ma_bedarf:`  
     Nur wenn Bedarfsliste nicht leer.

582. `                    # Sortiere: Wer am meisten braucht → zuerst bedienen`  
     Kommentar.

583. `                    ma_bedarf.sort(key=lambda x: x['bedarf'], reverse=True)`  
     Sortierung nach Bedarf absteigend.

584. `                    `  
     Leerzeile.

585. `                    # Zähle wie viele Z pro Tag vergeben werden (max 2)`  
     Kommentar.

586. `                    z_pro_tag = defaultdict(int)`  
     Z‑Zählung pro Tag.

587. `                    MAX_Z_PRO_TAG = 2`  
     Max Z pro Tag.

588. `                    `  
     Leerzeile.

589. `                    # Zähle auch bereits vergebene Z pro MA (aus Solver T/N + neue Z)`  
     Kommentar.

590. `                    # damit max_aufeinanderfolgende_tage korrekt bleibt`  
     Kommentar.

591. `                    ma_arbeits_tage = {}  # {ma.id: set(datum)} — alle Tage wo MA arbeitet`  
     Map: MA → Arbeitstage.

592. `                    for ma_info in ma_bedarf:`  
     Für jeden Bedarfseintrag…

593. `                        arbeits_tage = set()`  
     Set für Arbeitstage.

594. `                        for tag in tage_liste:`  
     Für jeden Tag…

595. `                            if solver.Value(vars_schichten[(ma_info['ma'].id, tag, 'Frei')]) == 0:`  
     Wenn nicht Frei…

596. `                                arbeits_tage.add(tag)`  
     Tag merken.

597. `                        ma_arbeits_tage[ma_info['ma'].id] = arbeits_tage`  
     Set speichern.

598. `                    `  
     Leerzeile.

599. `                    for ma_info in ma_bedarf:`  
     Durch Bedarfsliste iterieren.

600. `                        ma_id = ma_info['ma'].id`  
     MA-ID.

601. `                        max_tage = self.preferences[ma_id]['max_aufeinanderfolgende_tage'] or 999`  
     Max-Streak des MA.

602. `                        `  
     Leerzeile.

603. `                        for tag in ma_info['freie_tage']:`  
     Über freie Kandidaten-Tage.

604. `                            # Genug für diesen MA?`  
     Kommentar.

605. `                            if ma_info['zugewiesen'] >= ma_info['bedarf']:`  
     Wenn Bedarf gedeckt…

606. `                                break`  
     …weiter zum nächsten MA.

607. `                            # Tag voll (max 2 Z)?`  
     Kommentar.

608. `                            if z_pro_tag[tag] >= MAX_Z_PRO_TAG:`  
     Wenn Tageslimit erreicht…

609. `                                continue`  
     …nächster Tag.

610. `                            # Duplikat-Check: MA hat schon eine Schicht an diesem Tag`  
     Kommentar.

611. `                            if tag in ma_arbeits_tage[ma_id]:`  
     Wenn MA bereits arbeitet…

612. `                                continue`  
     …nächster Tag.

613. `                            `  
     Leerzeile.

614. `                            # Safety: max aufeinanderfolgende Tage prüfen`  
     Kommentar.

615. `                            # Zähle zusammenhängende Arbeits-Tage INCLUSIVE diesen Tag`  
     Kommentar.

616. `                            streak = 1`  
     Start Streak mit diesem Tag.

617. `                            check = tag - datetime.timedelta(days=1)`  
     Einen Tag zurück.

618. `                            while check in ma_arbeits_tage[ma_id]:`  
     Rückwärts Streak zählen…

619. `                                streak += 1`  
     Streak erhöhen.

620. `                                check -= datetime.timedelta(days=1)`  
     Einen Tag weiter zurück.

621. `                            check = tag + datetime.timedelta(days=1)`  
     Vorwärts prüfen.

622. `                            while check in ma_arbeits_tage[ma_id]:`  
     Vorwärts Streak zählen…

623. `                                streak += 1`  
     Streak erhöhen.

624. `                                check += datetime.timedelta(days=1)`  
     Einen Tag vor.

625. `                            `  
     Leerzeile.

626. `                            if streak > max_tage:`  
     Wenn Streak zu lang…

627. `                                continue`  
     …kein Z an diesem Tag.

628. `                            `  
     Leerzeile.

629. `                            # ✅ Vergeben`  
     Kommentar.

630. `                            Schicht.objects.create(`  
     Zusatzdienst erstellen.

631. `                                schichtplan=neuer_schichtplan_obj,`  
     Schichtplan zuordnen.

632. `                                mitarbeiter=ma_info['ma'],`  
     Mitarbeiter.

633. `                                datum=tag,`  
     Datum.

634. `                                schichttyp=self.type_z`  
     Z-Schichttyp.

635. `                            )`  
     Ende create.

636. `                            ma_info['zugewiesen'] += 1`  
     Zuweisungszähler erhöhen.

637. `                            z_pro_tag[tag] += 1`  
     Tageszähler erhöhen.

638. `                            ma_arbeits_tage[ma_id].add(tag)`  
     Tag in Arbeitsliste aufnehmen.

639. `                            zusatz_count += 1`  
     Gesamtzähler.

640. `                    `  
     Leerzeile.

641. `                    print(f"   ➕ {zusatz_count} Zusatzdienste vergeben.")`  
     Ausgabe der Anzahl.

---

## I. Statistiken

642. `            # ================================================================`  
     Abschnitts-Trenner.

643. `            # I. STATISTIKEN`  
     Abschnittstitel.

644. `            # ================================================================`  
     Abschnitts-Trenner.

645. `            self._print_statistics(neuer_schichtplan_obj, tage_liste, soll_stunden_map, soll_schichten_map, wuensche_matrix)`  
     Statistik-Ausgabe aufrufen.

646. `        `  
     Leerzeile.

647. `        else:`  
     Wenn keine Lösung gefunden…

648. `            error_msg = (`  
     Fehlermeldung definieren.

649. `                "❌ Keine gültige Lösung gefunden!\n"`  
     Zeile 1.

650. `                "Mögliche Ursachen:\n"`  
     Zeile 2.

651. `                "1. Zu wenige MA für Besetzung (2 pro Schicht)\n"`  
     Ursache 1.

652. `                "2. Zu viele Urlaube an denselben Tagen\n"`  
     Ursache 2.

653. `                "3. Typ B + Wünsche unvereinbar\n"`  
     Ursache 3.

654. `            )`  
     Ende String.

655. `            print(error_msg)`  
     Ausgabe.

656. `            raise Exception(error_msg)`  
     Exception werfen.

---

## Statistik-Funktion

657. `    # ======================================================================`  
     Abschnitts-Trenner.

658. `    # STATISTIKEN`  
     Abschnittstitel.

659. `    # ======================================================================`  
     Abschnitts-Trenner.

660. `    def _print_statistics(self, schichtplan, tage_liste, soll_stunden_map, soll_schichten_map, wuensche_matrix):`  
     Methode: Statistik ausgeben.

661. `        print("\n" + "="*70)`  
     Header.

662. `        print("📊 PLAN-STATISTIKEN")`  
     Titel.

663. `        print("="*70)`  
     Trennlinie.

664. `        `  
     Leerzeile.

665. `        schichten = Schicht.objects.filter(schichtplan=schichtplan)`  
     Alle Schichten für Plan laden.

666. `        `  
     Leerzeile.

667. `        # Wunsch-Analyse`  
     Kommentar.

668. `        print("\n🔍 WUNSCH-ANALYSE:")`  
     Abschnittstitel.

669. `        for ma in self.mitarbeiter_list:`  
     Für jeden Mitarbeiter…

670. `            ma_wuensche = wuensche_matrix.get(ma.id, {})`  
     Wünsche dieses MA.

671. `            for datum, wunsch in ma_wuensche.items():`  
     Für jeden Wunsch…

672. `                schicht_an_tag = schichten.filter(mitarbeiter=ma, datum=datum).first()`  
     Prüfen ob Schicht existiert.

673. `                ist = schicht_an_tag.schichttyp.kuerzel if schicht_an_tag else "Frei"`  
     Ist-Schicht (oder Frei).

674. `                `  
     Leerzeile.

675. `                if wunsch.wunsch == 'urlaub':`  
     Wunsch Urlaub.

676. `                    status = "✅" if not schicht_an_tag else "❌ FEHLER"`  
     Urlaub erfüllt? (keine Schicht).

677. `                elif wunsch.wunsch == 'tag_bevorzugt':`  
     Wunsch Tagdienst.

678. `                    status = "✅" if ist == 'T' else ("⚠️ SOFT" if ist != 'Frei' else "ℹ️")`  
     Tagdienst erfüllt / soft / frei.

679. `                elif wunsch.wunsch == 'nacht_bevorzugt':`  
     Wunsch Nachtdienst.

680. `                    status = "✅" if ist == 'N' else ("⚠️ SOFT" if ist != 'Frei' else "ℹ️")`  
     Nacht erfüllt / soft / frei.

681. `                elif wunsch.wunsch == 'gar_nichts':`  
     Wunsch „gar nichts“.

682. `                    status = "✅" if not schicht_an_tag else ("❌ FEHLER" if wunsch.genehmigt else "⚠️")`  
     Status je nach Genehmigung.

683. `                else:`  
     Sonstiger Wunsch.

684. `                    status = "ℹ️"`  
     Info.

685. `                `  
     Leerzeile.

686. `                print(f"   {status} {ma.schichtplan_kennung}: {wunsch.wunsch} am {datum} → {ist}")`  
     Ausgabe je Wunsch.

687. `        `  
     Leerzeile.

688. `        # Verteilung pro MA`  
     Kommentar.

689. `        print("\n📊 SCHICHT-VERTEILUNG:")`  
     Abschnittstitel.

690. `        tage_namen = ['Mo','Di','Mi','Do','Fr','Sa','So']`  
     Wochentagsnamen.

691. `        `  
     Leerzeile.

692. `        for ma in self.mitarbeiter_list:`  
     Für jeden MA…

693. `            ma_schichten = schichten.filter(mitarbeiter=ma)`  
     Schichten des MA.

694. `            anzahl_t = ma_schichten.filter(schichttyp=self.type_t).count()`  
     Anzahl Tag-Schichten.

695. `            anzahl_n = ma_schichten.filter(schichttyp=self.type_n).count()`  
     Anzahl Nacht-Schichten.

696. `            anzahl_z = ma_schichten.filter(schichttyp=self.type_z).count() if self.type_z else 0`  
     Anzahl Z-Schichten (falls existiert).

697. `            gesamt = anzahl_t + anzahl_n + anzahl_z`  
     Gesamtanzahl Schichten.

698. `            `  
     Leerzeile.

699. `            soll_schichten = soll_schichten_map.get(ma.id, 0)`  
     Soll-Schichten.

700. `            soll_stunden = soll_stunden_map.get(ma.id, 0)`  
     Soll-Stunden.

701. `            diff = gesamt - soll_schichten`  
     Differenz Ist − Soll.

702. `            diff_str = f"+{diff}" if diff > 0 else str(diff)`  
     Schönes Vorzeichenformat.

703. `            typ_label = "B" if self.preferences[ma.id]['schicht_typ'] == 'typ_b' else "A"`  
     Typ-Label A/B.

704. `            `  
     Leerzeile.

705. `            # Vereinbarungen anzeigen (eigene Variablen, nicht 't' überschreiben!)`  
     Kommentar.

706. `            vereinbarungen = []`  
     Liste Vereinbarungen.

707. `            erlaubte = self.preferences[ma.id]['erlaubte_wochentage']`  
     Erlaubte Tage.

708. `            if erlaubte:`  
     Wenn gesetzt…

709. `                vereinbarungen.append(', '.join(tage_namen[d] for d in erlaubte if 0 <= d <= 6))`  
     Wochentage als Text.

710. `            if self.preferences[ma.id]['keine_zusatzdienste']:`  
     Wenn keine Z…

711. `                vereinbarungen.append("keine Z")`  
     Zusatzinfo.

712. `            vereinbarungen_str = f" [{', '.join(vereinbarungen)}]" if vereinbarungen else ""`  
     Optionaler Text.

713. `            `  
     Leerzeile.

714. `            print(f"   {ma.schichtplan_kennung} (Typ {typ_label}){vereinbarungen_str}: {anzahl_t}T + {anzahl_n}N + {anzahl_z}Z = {gesamt} (Soll: {soll_schichten}, {diff_str}) | {soll_stunden}h")`  
     Ausgabe je Mitarbeiter.

715. `        `  
     Leerzeile.

716. `        print("="*70 + "\n")`  
     Abschlusslinie.

