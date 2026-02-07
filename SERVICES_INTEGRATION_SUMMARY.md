# ✅ Services.py - Analyse-Integration abgeschlossen

**Datum:** 05.02.2026  
**Datei:** `schichtplan/services.py`

---

## Was wurde integriert?

### 1. ✅ Neue Felder laden (_load_preferences)

**Zeilen 78-119:** Erweitert um:
```python
# Fixe Tagdienst-Wochentage
'fixe_tag_wochentage': fixe_tage,  # MA1: [2], MA7: [1,3]

# Kategorie & Besetzung
'kategorie': 'kern'|'hybrid'|'zusatz'|'dauerkrank'
'zaehlt_zur_tagbesetzung': True|False
'zaehlt_zur_nachtbesetzung': True|False

# Wochenend-Blöcke
'wochenend_nachtdienst_block': True|False

# Min/Target Schichten
'min_tagschichten_pro_monat': 4 (für Typ B)
'min_nachtschichten_pro_monat': 4 (für Typ B)
'target_tagschichten_pro_monat': 6 (Soft Constraint)
'target_nachtschichten_pro_monat': 5 (Soft Constraint)
```

### 2. ✅ Verbesserte Debug-Ausgabe (Zeilen 125-157)

**NEU - Ausgabe zeigt:**
- Kategorie (HYBRID, ZUSATZ, DAUERKRANK)
- Fixe Tage (FIXE Mi, FIXE Di,Do)
- Besetzungslogik (T=ZUSÄTZLICH, N=NICHT)
- Wochenend-Block (WE-BLOCK)
- Min-Schichten (min 4T, min 4N)

**Beispiel-Ausgabe:**
```
→ MA1: FIXE Mi, N=NICHT, min 0T
→ MA7: HYBRID, FIXE Di,Do, T=ZUSÄTZLICH, WE-BLOCK, min 0T, min 0N
→ MA2: KERN, min 0T, min 0N
```

### 3. ✅ Fixe Tagdienste Constraint (B.11, Zeilen 402-419)

**Logik:**
- Liest `fixe_tag_wochentage` aus Präferenzen
- **Erzwingt** Tagdienst an diesen Wochentagen
- Ausnahme: Urlaub

**Code:**
```python
if fixe_tage:  # MA1: [2] (Mi), MA7: [1,3] (Di,Do)
    for tag in tage_liste:
        if tag.weekday() in fixe_tage and not is_urlaub:
            model.Add(vars_schichten[(ma.id, tag, 'T')] == 1)
```

**Effekt:**
- MA1: Jeden Mittwoch Tagdienst (außer Urlaub)
- MA7: Jeden Dienstag + Donnerstag Tagdienst (außer Urlaub)

### 4. ✅ Min Tagschichten Constraint (B.13, Zeilen 435-452)

**Logik:**
- Liest `min_tagschichten_pro_monat`
- Prüft verfügbare Tage (ohne Urlaub)
- Setzt Hard Constraint: `sum(T) >= min_t`
- Setzt Constraint aus bei zu wenig Tagen

**Code:**
```python
if pref['min_tagschichten_pro_monat']:
    if verfuegbare_tage >= min_t:
        model.Add(sum(tag_schichten) >= min_t)
```

**Effekt:**
- Typ B Mitarbeiter: Mindestens 4 Tagschichten
- Wird ausgesetzt bei zu viel Urlaub

### 5. ✅ Min Nachtschichten Constraint (B.14, Zeilen 454-470)

**Analog zu Min Tagschichten:**
```python
if pref['min_nachtschichten_pro_monat']:
    if verfuegbare_tage >= min_n:
        model.Add(sum(nacht_schichten) >= min_n)
```

**Effekt:**
- Typ B Mitarbeiter: Mindestens 4 Nachtschichten

### 6. ✅ Erlaubte Wochentage angepasst (B.12, Zeilen 421-433)

**Änderung:**
- Nur noch aktiv wenn **KEINE** fixen Tage gesetzt
- Verhindert Konflikt zwischen `fixe_tag_wochentage` und `erlaubte_wochentage`

```python
if erlaubte_tage and not fixe_tage:  # ← Neue Bedingung
    # ... alte Logik
```

---

## Noch NICHT implementiert (für später)

### 1. Wochenend-Nachtdienst-Blöcke
**Wo:** Nach B.8 (max aufeinanderfolgende Tage)  
**Logik:**
```python
# B.X WOCHENEND-NACHTDIENST-BLÖCKE
if pref['wochenend_nachtdienst_block']:
    # Finde Wochenenden (Fr-Sa, Sa-So)
    wochenenden = []
    for i, tag in enumerate(tage_liste):
        if tag.weekday() == 4:  # Freitag
            if i+1 < len(tage_liste):
                wochenenden.append((tag, tage_liste[i+1]))  # Fr-Sa
        if tag.weekday() == 5:  # Samstag
            if i+1 < len(tage_liste):
                wochenenden.append((tag, tage_liste[i+1]))  # Sa-So
    
    # Erzwinge Blöcke
    for tag1, tag2 in wochenenden:
        # Wenn Nachtschicht an tag1, dann auch an tag2
        model.Add(
            vars_schichten[(ma.id, tag2, 'N')] == 1
        ).OnlyEnforceIf(vars_schichten[(ma.id, tag1, 'N')])
```

**Vorteil:**
- MA7 bekommt automatisch Fr-Sa oder Sa-So Blöcke
- Keine einzelnen Wochenend-Nachtdienste

### 2. Target-Schichten im Optimierungsziel
**Wo:** In E.1 (Soll-Stunden) ergänzen  
**Logik:**
```python
# --- E.1b TARGET-SCHICHTEN (SOFT) ---
target_t = pref['target_tagschichten_pro_monat']
target_n = pref['target_nachtschichten_pro_monat']

# Zähle tatsächliche Schichten
ist_t = sum([vars_schichten[(ma.id, tag, 'T')] for tag in tage_liste])
ist_n = sum([vars_schichten[(ma.id, tag, 'N')] for tag in tage_liste])

# Abweichung von Target bestrafen
abweichung_t = model.NewIntVar(-50, 50, f'{ma.id}_target_abw_t')
model.Add(abweichung_t == ist_t - target_t)
abs_abw_t = model.NewIntVar(0, 50, f'{ma.id}_target_abs_t')
model.AddAbsEquality(abs_abw_t, abweichung_t)
objective_terms.append(abs_abw_t * 1000)  # Soft Constraint

# Gleich für Nachtschichten
```

**Vorteil:**
- Generator versucht 6T/5N pro Monat zu erreichen
- MA1 bekommt automatisch weniger (target=4T/0N)
- Soft Constraint (kein MUSS)

### 3. Besetzung nach Kategorie filtern
**Wo:** In C. (Besetzung)  
**Aktuell:** Alle Mitarbeiter zählen zur Besetzung  
**NEU:**
```python
# C. BESETZUNG - nur MA die zur Besetzung zählen
for tag in tage_liste:
    # TAGSCHICHTEN - nur MA mit zaehlt_zur_tagbesetzung=True
    tag_eligible = [
        vars_schichten[(m.id, tag, 'T')] 
        for m in self.mitarbeiter_list 
        if self.preferences[m.id]['zaehlt_zur_tagbesetzung']
    ]
    summe_t = model.NewIntVar(0, 12, f'summe_{tag}_T')
    model.Add(summe_t == sum(tag_eligible))
    model.Add(summe_t >= 2)  # HART: min 2 zur Besetzung
    model.Add(summe_t <= 4)
    
    # NACHTSCHICHTEN - nur MA mit zaehlt_zur_nachtbesetzung=True
    nacht_eligible = [
        vars_schichten[(m.id, tag, 'N')] 
        for m in self.mitarbeiter_list 
        if self.preferences[m.id]['zaehlt_zur_nachtbesetzung']
    ]
    summe_n = model.NewIntVar(0, 12, f'summe_{tag}_N')
    model.Add(summe_n == sum(nacht_eligible))
    model.Add(summe_n >= 2)  # HART: min 2 zur Besetzung
    model.Add(summe_n <= 4)
```

**Effekt:**
- MA7 (Di+Do) zählt NICHT zur 2T-Regel
- MA1 zählt NICHT zur 2N-Regel
- Besetzung wird korrekt geprüft

---

## Testing

### Test 1: MA1 (Mittwochskraft)
**Erwartung:**
- Jeden Mittwoch Tagdienst
- Keine Nachtdienste
- Ca. 4 Schichten/Monat

**Prüfen:**
```python
ma1_schichten = Schicht.objects.filter(mitarbeiter__schichtplan_kennung='MA1')
mittwochs = [s for s in ma1_schichten if s.datum.weekday() == 2]
assert len(mittwochs) > 0, "MA1 muss Mittwochs arbeiten"
assert ma1_schichten.filter(schichttyp__kuerzel='N').count() == 0, "MA1 keine Nachtdienste"
```

### Test 2: MA7 (Hybrid)
**Erwartung:**
- Jeden Dienstag + Donnerstag Tagdienst
- Nachtdienste nur am Wochenende
- Wochenend-Nachtdienste als Blöcke (später)

**Prüfen:**
```python
ma7_schichten = Schicht.objects.filter(mitarbeiter__schichtplan_kennung='MA7')
dienstags = [s for s in ma7_schichten if s.datum.weekday() == 1 and s.schichttyp.kuerzel == 'T']
donnerstags = [s for s in ma7_schichten if s.datum.weekday() == 3 and s.schichttyp.kuerzel == 'T']
assert len(dienstags) > 0, "MA7 muss Dienstags arbeiten"
assert len(donnerstags) > 0, "MA7 muss Donnerstags arbeiten"

nachtdienste = ma7_schichten.filter(schichttyp__kuerzel='N')
for nd in nachtdienste:
    assert nd.datum.weekday() >= 4, "MA7 Nachtdienste nur Fr/Sa/So"
```

### Test 3: Typ B Mitarbeiter
**Erwartung:**
- Mindestens 4 Tagschichten
- Mindestens 4 Nachtschichten

**Prüfen:**
```python
typ_b_mas = Mitarbeiter.objects.filter(schicht_typ='typ_b')
for ma in typ_b_mas:
    t_count = Schicht.objects.filter(mitarbeiter=ma, schichttyp__kuerzel='T').count()
    n_count = Schicht.objects.filter(mitarbeiter=ma, schichttyp__kuerzel='N').count()
    
    # Mit Toleranz für Urlaub
    if t_count + n_count >= 10:  # Genug Tage gearbeitet
        assert t_count >= 4, f"{ma.schichtplan_kennung}: Typ B braucht min 4T"
        assert n_count >= 4, f"{ma.schichtplan_kennung}: Typ B braucht min 4N"
```

---

## Zusammenfassung

### ✅ Implementiert:
1. Neue Felder laden (kategorie, fixe_tag_wochentage, zaehlt_zur_*, min_*, target_*)
2. Verbesserte Debug-Ausgabe
3. Fixe Tagdienste Constraint (MA1: Mi, MA7: Di+Do)
4. Min Tagschichten Constraint
5. Min Nachtschichten Constraint
6. Erlaubte Wochentage Anpassung (kein Konflikt mehr)

### 📋 TODO (Optional):
1. Wochenend-Nachtdienst-Blöcke (Fr-Sa, Sa-So)
2. Target-Schichten im Optimierungsziel (Soft Constraint)
3. Besetzung nach Kategorie filtern (zaehlt_zur_tagbesetzung/nachtbesetzung)

### 🎯 Nächste Schritte:
1. Plan generieren und testen
2. MA1, MA7 Regeln überprüfen
3. Bei Bedarf: Wochenend-Blöcke + Target-Schichten implementieren

**Die kritischsten Regeln aus der Analyse sind jetzt implementiert!** 🎉
