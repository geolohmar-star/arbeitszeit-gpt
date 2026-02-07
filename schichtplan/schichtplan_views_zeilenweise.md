# Zeilenweise Erklärung: schichtplan/views.py (Ausschnitt)

> Hinweis: Die Nummerierung folgt der Reihenfolge der geposteten Zeilen.  
> Ich gruppiere zusammengehörige Zeilen minimal (z. B. Decorator + Klasse), bleibe aber zeilennah.

---

## Header & Docstring

1. `# schichtplan/views.py - ANGEPASST für MA1-MA15 mit Präferenzen`  
   Kommentar: Datei-/Featurehinweis.

2. `"""`  
   Beginn Modul-Docstring.

3. `Views für das Schichtplan-Modul`  
   Kurzbeschreibung.

4. `ANGEPASST: Filtert nur Mitarbeiter mit Kennung MA1-MA15`  
   Hinweis auf Filterlogik.

5. ``  
   Leere Zeile im Docstring.

6. `"""`  
   Ende Docstring.

---

## Imports

7. `from django.db.models.functions import Length  # ← Für Sortierung`  
   Import für Sortierung nach Stringlänge.

8. `from django.shortcuts import render, redirect, get_object_or_404`  
   Standard View-Helper.

9. `from django.contrib.auth.decorators import login_required`  
   Decorator für Loginpflicht.

10. `from django.contrib import messages`  
    Flash-Messages.

11. `from django.db.models import Count`  
    Aggregationen.

12. `from django.http import JsonResponse`  
    JSON-Antworten.

13. `from django.views.generic.edit import CreateView`  
    Class-based CreateView.

14. `from django.urls import reverse_lazy`  
    Lazy URL-Reverse.

15. `from django.db import transaction`  
    DB-Transaktionen.

16. `from django import forms`  
    Django-Forms.

17. `from collections import defaultdict`  
    Dict mit Defaultwert.

18. ``  
    Leerzeile.

19. `from datetime import timedelta`  
    Zeitdifferenzen.

20. `from calendar import day_name`  
    Wochentagsnamen.

21. `import tempfile`  
    Temp-Dateien.

22. ``  
    Leerzeile.

23. `# Models`  
    Kommentar.

24. `from arbeitszeit.models import Mitarbeiter, MonatlicheArbeitszeitSoll`  
    Modelle aus arbeitszeit.

25. `from .models import Schichtplan, Schicht, Schichttyp, SchichtwunschPeriode, Schichtwunsch  # ← Schichtwunsch hinzufügen!`  
    Modelle der App.

26. ``  
    Leerzeile.

27. `# Forms`  
    Kommentar.

28. `from .forms import ExcelImportForm, SchichtplanForm, SchichtForm`  
    Formulare.

29. ``  
    Leerzeile.

30. `# Services`  
    Kommentar.

31. `from .services import SchichtplanGenerator`  
    Generator-Service.

32. ``  
    Leerzeile.

33. `# Utils`  
    Kommentar.

34. `try:`  
    Versuch: moderner Import.

35. `    from .utils.excel_import import SchichtplanImporter`  
    Import Excel-Importer.

36. `except ImportError:`  
    Fallback.

37. `    try:`  
    Zweiter Versuch.

38. `        from .utils.xls_importer import SchichtplanImporter`  
    Alternativer Import.

39. `    except ImportError:`  
    Wenn beides fehlt…

40. `        SchichtplanImporter = None`  
    Importer deaktivieren.

41. ``  
    Leerzeile.

42. `#Wunschplan`  
    Kommentar.

43. `from datetime import datetime, timedelta`  
    Datetime-Import (erneut).

44. `from calendar import monthrange`  
    Monatslänge.

45. `from django.utils import timezone`  
    Zeitzone.

46. ``  
    Leerzeile.

---

## Helper-Funktionen

47. `# ============================================================================`  
    Abschnittstrenner.

48. `# HELPER FUNKTIONEN`  
    Abschnittstitel.

49. `# ============================================================================`  
    Abschnittstrenner.

50. `def ist_schichtplaner(user):`  
    Helper: Prüft Planer-Rechte.

51. `    # DEBUG: Zeigt im Terminal an, wer gerade prüft`  
    Kommentar.

52. `    if user.is_anonymous:`  
    Wenn anonym…

53. `        return False`  
    …keine Rechte.

54. `    `  
    Leerzeile.

55. `    # 1. Admin/Superuser (funktioniert immer)`  
    Kommentar.

56. `    if user.is_superuser or user.is_staff:`  
    Admins dürfen.

57. `        return True`  
    Rückgabe.

58. `    `  
    Leerzeile.

59. `    # 2. Gruppen-Prüfung (WICHTIG: Name muss exakt stimmen)`  
    Kommentar.

60. `    # Wir prüfen, ob der User in der Gruppe "Schichtplaner" ist`  
    Kommentar.

61. `    ergebnis = user.groups.filter(name='Schichtplaner').exists()`  
    Gruppencheck.

62. `    `  
    Leerzeile.

63. `    # DEBUG-Ausgabe für dich im Terminal:`  
    Kommentar.

64. `    print(f"--- Berechtigungs-Check für {user.username} ---")`  
    Debug: Username.

65. `    print(f"Ist Staff: {user.is_staff}")`  
    Debug: Staff.

66. `    print(f"In Gruppe Schichtplaner: {ergebnis}")`  
    Debug: Gruppe.

67. `    `  
    Leerzeile.

68. `    return ergebnis`  
    Rückgabe der Gruppenprüfung.

69. ``  
    Leerzeile.

70. `#def ist_schichtplaner(user):`  
    Auskommentierte Alternative.

71. `#    """Prüft, ob der User Schichtplaner-Rechte hat"""`  
    Docstring (kommentiert).

72. `#    if user.is_staff or user.is_superuser:`  
    Alternative Logik.

73. `#        return True`  
    Rückgabe.

74. `#    `  
    Leerzeile.

75. `#    if hasattr(user, 'mitarbeiter'):`  
    Mitarbeiterrolle prüfen.

76. `#        return user.mitarbeiter.rolle == 'schichtplaner'`  
    Rollencheck.

77. `#    `  
    Leerzeile.

78. `#    return False`  
    Fallback.

79. ``  
    Leerzeile.

80. `def get_planbare_mitarbeiter():`  
    Helper: filtert planbare MA.

81. `    """`  
    Docstring 시작.

82. `    Gibt nur Mitarbeiter zurück, die für Schichtplanung relevant sind.`  
    Beschreibung.

83. `    `  
    Leerzeile.

84. `    Kriterien:`  
    Aufzählung.

85. `    - Aktiv = True`  
    Aktiv-Filter.

86. `    - Kennung = MA1 bis MA15`  
    Kennungsfilter.

87. `    - Verfügbarkeit != 'dauerkrank'`  
    Ausschluss Dauerkrank.

88. `    """`  
    Ende Docstring.

89. `    gueltige_kennungen = [f'MA{i}' for i in range(1, 16)]  # MA1 bis MA15`  
    Erzeugt Kennungsliste.

90. `    `  
    Leerzeile.

91. `    return Mitarbeiter.objects.filter(`  
    Query starten.

92. `        aktiv=True,`  
    Filter aktiv.

93. `        schichtplan_kennung__in=gueltige_kennungen`  
    Filter Kennung.

94. `    ).exclude(`  
    Exclude.

95. `        verfuegbarkeit='dauerkrank'`  
    Ausschluss.

96. `    ).select_related('user')`  
    Join User.

---

## Wunsch-Periode CreateView

97. `class WunschPeriodeCreateView(CreateView):`  
    Class-based View.

98. `    model = SchichtwunschPeriode`  
    Modellzuordnung.

99. `    template_name = 'schichtplan/periode_form.html'`  
    Template.

100. `    fields = ['name', 'fuer_monat', 'eingabe_start', 'eingabe_ende', 'status']`  
     Formularfelder.

101. `    success_url = reverse_lazy('schichtplan:wunsch_perioden_liste')`  
     Weiterleitung.

102. ``  
     Leerzeile.

103. `    def get_form(self, form_class=None):`  
     Override: Form anpassen.

104. `        form = super().get_form(form_class)`  
     Standard-Form holen.

105. `        `  
     Leerzeile.

106. `        # 1. Datumsauswahl (Nur Tag/Monat/Jahr)`  
     Kommentar.

107. `        form.fields['fuer_monat'].widget = forms.DateInput(`  
     Widget für Datum.

108. `            attrs={'type': 'date', 'class': 'form-control'}`  
     HTML-Input + CSS.

109. `        )`  
     Ende.

110. `        `  
     Leerzeile.

111. `        # 2. Datum mit Uhrzeit (Für den Eingabezeitraum)`  
     Kommentar.

112. `        form.fields['eingabe_start'].widget = forms.DateTimeInput(`  
     Startzeit-Widget.

113. `            attrs={'type': 'datetime-local', 'class': 'form-control'}`  
     HTML-Input + CSS.

114. `        )`  
     Ende.

115. `        form.fields['eingabe_ende'].widget = forms.DateTimeInput(`  
     Endzeit-Widget.

116. `            attrs={'type': 'datetime-local', 'class': 'form-control'}`  
     HTML-Input + CSS.

117. `        )`  
     Ende.

118. `        `  
     Leerzeile.

119. `        # Styling für die anderen Felder`  
     Kommentar.

120. `        form.fields['name'].widget.attrs.update({'class': 'form-control'})`  
     CSS-Klasse.

121. `        form.fields['status'].widget.attrs.update({'class': 'form-control'})`  
     CSS-Klasse.

122. `        `  
     Leerzeile.

123. `        return form`  
     Form zurückgeben.

124. ``  
     Leerzeile.

125. `    def form_valid(self, form):`  
     Override: Save-Hook.

126. `        form.instance.erstellt_von = self.request.user`  
     Creator setzen.

127. `        return super().form_valid(form)`  
     Standardverhalten.

---

## Schichtplan erstellen (Class-Based View)

128. `# ============================================================================`  
     Abschnittstrenner.

129. `# CLASS-BASED VIEW: Schichtplan erstellen`  
     Abschnittstitel.

130. `# ============================================================================`  
     Abschnittstrenner.

131. `class SchichtplanCreateView(CreateView):`  
     CreateView.

132. `    """`  
     Docstring.

133. `    Erstellt einen neuen Schichtplan.`  
     Beschreibung.

134. `    Verwendet nur Mitarbeiter mit Kennung MA1-MA15.`  
     Hinweis auf Filter.

135. `    """`  
     Ende Docstring.

136. `    `  
     Leerzeile.

137. `    model = Schichtplan`  
     Modell.

138. `    form_class = SchichtplanForm`  
     Formular.

139. `    template_name = 'schichtplan/schichtplan_erstellen.html'`  
     Template.

140. `    success_url = reverse_lazy('schichtplan:dashboard')`  
     Erfolg-URL.

141. ``  
     Leerzeile.

142. `    def dispatch(self, request, *args, **kwargs):`  
     Zugriffskontrolle.

143. `        """Berechtigungsprüfung"""`  
     Docstring.

144. `        if not ist_schichtplaner(request.user):`  
     Rechte prüfen.

145. `            messages.error(request, "❌ Keine Berechtigung für diese Aktion.")`  
     Fehlermeldung.

146. `            return redirect('arbeitszeit:dashboard')`  
     Redirect.

147. `        return super().dispatch(request, *args, **kwargs)`  
     Standard-Dispatch.

148. ``  
     Leerzeile.

149. `    def form_valid(self, form):`  
     Speichern-Hook.

150. `        """Speichern + Optional KI-Generierung"""`  
     Docstring.

151. `        `  
     Leerzeile.

152. `        ki_aktiviert = form.cleaned_data.get('vorschlag_generieren', False)`  
     Flag aus Form.

153. `        `  
     Leerzeile.

154. `        try:`  
     Fehlerbehandlung.

155. `            with transaction.atomic():`  
     Transaktion.

156. `                # 1. Schichtplan speichern`  
     Kommentar.

157. `                self.object = form.save(commit=False)`  
     Objekt erzeugen.

158. `                `  
     Leerzeile.

159. `                if hasattr(self.object, 'erstellt_von'):`  
     Wenn Feld existiert…

160. `                    self.object.erstellt_von = self.request.user`  
     …Creator setzen.

161. `                `  
     Leerzeile.

162. `                self.object.save()`  
     Speichern.

163. `                `  
     Leerzeile.

164. `                print(f"✅ Schichtplan '{self.object.name}' (ID={self.object.pk}) gespeichert")`  
     Debug-Ausgabe.

165. `                `  
     Leerzeile.

166. `                # 2. KI-Generierung (falls aktiviert)`  
     Kommentar.

167. `                if ki_aktiviert:`  
     Wenn aktiv…

168. `                    self._generate_with_ai()`  
     Generator ausführen.

169. `                else:`  
     Sonst…

170. `                    messages.success(`  
     Erfolgsmeldung.

171. `                        self.request,`  
     Request.

172. `                        f"✅ Plan '{self.object.name}' wurde leer angelegt."`  
     Text.

173. `                    )`  
     Ende.

174. `            `  
     Leerzeile.

175. `            return redirect(self.get_success_url())`  
     Redirect.

176. `            `  
     Leerzeile.

177. `        except Exception as e:`  
     Fehlerbehandlung.

178. `            import traceback`  
     Traceback-Modul.

179. `            traceback.print_exc()`  
     Stacktrace.

180. `            `  
     Leerzeile.

181. `            messages.error(`  
     Fehlermeldung.

182. `                self.request,`  
     Request.

183. `                f"❌ Fehler beim Erstellen des Plans: {str(e)}"`  
     Text.

184. `            )`  
     Ende.

185. `            return self.form_invalid(form)`  
     Form-Fehler.

186. ``  
     Leerzeile.

187. `    def _generate_with_ai(self):`  
     Interne KI-Generierung.

188. `      `  
     Leerzeile (Indent).

189. `        print(f"🤖 KI-Generierung für Plan '{self.object.name}' (ID={self.object.pk}) gestartet...")`  
     Debug-Ausgabe.

190. `        `  
     Leerzeile.

191. `        # 1. BASIS-CHECK: Mitarbeiter vorhanden?`  
     Kommentar.

192. `        planbare_mitarbeiter = get_planbare_mitarbeiter()`  
     MA filtern.

193. `        `  
     Leerzeile.

194. `        if not planbare_mitarbeiter.exists():`  
     Wenn keine MA…

195. `            messages.warning(`  
     Warnung.

196. `                self.request,`  
     Request.

197. `                "⚠️ Keine planbaren Mitarbeiter gefunden (MA1-MA15 aktiv/nicht dauerkrank)."`  
     Text.

198. `            )`  
     Ende.

199. `            return`  
     Abbruch.

200. `        `  
     Leerzeile.

201. `        # 2. BASIS-CHECK: Schichttypen vorhanden?`  
     Kommentar.

202. `        required_types = ['T', 'N']`  
     Pflichttypen.

203. `        existing_types = list(Schichttyp.objects.filter(kuerzel__in=required_types).values_list('kuerzel', flat=True))`  
     Vorhandene Typen.

204. `        `  
     Leerzeile.

205. `        if len(existing_types) != len(required_types):`  
     Wenn fehlt…

206. `            missing = set(required_types) - set(existing_types)`  
     Fehlende ermitteln.

207. `            raise Exception(f"Schichttypen fehlen: {', '.join(missing)}. Bitte im Admin anlegen.")`  
     Fehler werfen.

208. `        `  
     Leerzeile.

209. `        # 3. HINWEIS: Wünsche werden automatisch vom Generator geladen`  
     Kommentar.

210. `        print(f"   ℹ️ Wünsche werden automatisch aus DB geladen (falls vorhanden)")`  
     Hinweis.

211. `        `  
     Leerzeile.

212. `        # 4. GENERATOR STARTEN (Genau ein Aufruf)`  
     Kommentar.

213. `        try:`  
     Fehlerbehandlung.

214. `            # WICHTIG: Nur ein Positionsargument!`  
     Kommentar.

215. `            # Alte Schichten löschen (falls Plan neu generiert wird)`  
     Kommentar.

216. `            Schicht.objects.filter(schichtplan=self.object).delete()`  
     Löscht alte Schichten.

217. `            generator = SchichtplanGenerator(planbare_mitarbeiter)`  
     Generator instanziieren.

218. `            `  
     Leerzeile.

219. `            generator.generiere_vorschlag(self.object)`  
     Plan generieren.

220. `            `  
     Leerzeile.

221. `            schichten_anzahl = self.object.schichten.count()`  
     Anzahl Schichten.

222. `            `  
     Leerzeile.

223. `            messages.success(`  
     Erfolgsmeldung.

224. `                self.request,`  
     Request.

225. `                f"✅ Plan '{self.object.name}' wurde erfolgreich erstellt! "`  
     Text.

226. `                f"🚀 {schichten_anzahl} Schichten für {planbare_mitarbeiter.count()} "`  
     Text.

227. `                f"Mitarbeiter automatisch generiert."`  
     Text.

228. `            )`  
     Ende.

229. `            print(f"✅ Erfolg: {schichten_anzahl} Schichten generiert.")`  
     Debug.

230. `            `  
     Leerzeile.

231. `        except Exception as e:`  
     Fehlerbehandlung.

232. `            import traceback`  
     Traceback.

233. `            traceback.print_exc()`  
     Stacktrace.

234. `            raise Exception(f"Die KI-Generierung schlug fehl: {str(e)}")`  
     Fehler weiterwerfen.

---

## REST DER VIEWS (Ausschnitt, Überblick zeilennah)

235. `@login_required`  
     Loginpflicht.

236. `def excel_import_view(request, pk):`  
     View: Excel-Import.

237. `    """Importiert Excel-Datei in einen bestehenden Schichtplan"""`  
     Docstring.

238. `    schichtplan = get_object_or_404(Schichtplan, pk=pk)`  
     Schichtplan laden.

239. `    `  
     Leerzeile.

240. `    if not ist_schichtplaner(request.user):`  
     Berechtigungscheck.

241. `        messages.error(request, "❌ Keine Berechtigung.")`  
     Fehlermeldung.

242. `        return redirect('schichtplan:dashboard')`  
     Redirect.

243. `    `  
     Leerzeile.

244. `    if request.method == 'POST':`  
     POST prüfen.

245. `        form = ExcelImportForm(request.POST, request.FILES)`  
     Formular.

246. `        `  
     Leerzeile.

247. `        if form.is_valid():`  
     Validierung.

248. `            excel_file = request.FILES['excel_file']`  
     Datei holen.

249. `            `  
     Leerzeile.

250. `            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:`  
     Temp-Datei anlegen.

251. `                for chunk in excel_file.chunks():`  
     Datei schreiben.

252. `                    tmp.write(chunk)`  
     Chunk schreiben.

253. `                tmp_path = tmp.name`  
     Pfad merken.

254. `            `  
     Leerzeile.

255. `            try:`  
     Fehlerbehandlung.

256. `                if SchichtplanImporter is None:`  
     Importer vorhanden?

257. `                    raise Exception("Excel-Importer nicht verfügbar!")`  
     Fehler.

258. `                `  
     Leerzeile.

259. `                importer = SchichtplanImporter()`  
     Importer instanziieren.

260. `                importer.import_excel_mit_zuordnung(tmp_path, schichtplan)`  
     Import durchführen.

261. `                `  
     Leerzeile.

262. `                messages.success(request, "✅ Excel-Datei erfolgreich importiert!")`  
     Erfolgsmeldung.

263. `                return redirect('schichtplan:detail', pk=schichtplan.pk)`  
     Redirect.

264. `            `  
     Leerzeile.

265. `            except Exception as e:`  
     Fehlerfall.

266. `                messages.error(request, f"❌ Fehler beim Import: {str(e)}")`  
     Fehlermeldung.

267. `    `  
     Leerzeile.

268. `    else:`  
     GET-Fall.

269. `        form = ExcelImportForm()`  
     Leeres Formular.

270. `    `  
     Leerzeile.

271. `    return render(request, 'schichtplan/excel_import.html', {`  
     Template rendern.

272. `        'form': form,`  
     Kontext.

273. `        'schichtplan': schichtplan`  
     Kontext.

274. `    })`  
     Ende.

---

## Hinweis

Die restlichen View-Funktionen (`excel_analyse_view`, `planer_dashboard`, `mitarbeiter_uebersicht`,  
`schichtplan_detail`, `schicht_zuweisen`, `schicht_loeschen`, `wunsch_*`) folgen derselben Logik wie in der Funktionsanalyse:  
Zugriffsprüfung → Daten laden/filtern → Kontext bauen → Template rendern.  

Wenn du die **komplette, wirklich lückenlose Zeilen-Erklärung** für *alle* restlichen Funktionen willst,  
sag mir kurz Bescheid – ich ergänze die Datei vollständig.

