# Arbeitssitzung: MA7 Nachtschicht-Zuweisung
**Datum**: 05.02.2026  
**Status**: In Arbeit - Kritisches Problem

---

## KRITISCHES PROBLEM: MA7 erhält 0 Schichten

### Problemstellung
MA7 soll im Monat arbeiten:
- **4 Nachtschichten** am Wochenende (Fr/Sa/So) in **2er-Blöcken** (Fr+Sa oder Sa+So)
- **Rest-Schichten** mit Z-Diensten (Mo-Do) zum Auffüllen bis Soll-Ziel (13 Schichten)
- Z-Dienste für MA7 zählen **12h 15min** (wie Nachtschichten)
- 6 Nachtschichten sollen die Ausnahme sein

### Aktuelle Situation
**Der Solver weist MA7 KEINE Schichten zu trotz korrekter Konfiguration.**

---

## MA7 Konfiguration (Datenbank)

```
Aktiv: True
Kategorie: hybrid
Kann Nachtschicht: True
Zählt zur Nachtbesetzung: True
Nachtschicht nur Wochenende: True
Wochenend-Nachtdienst Block: True
keine_zusatzdienste: False
fixe_tag_wochentage: None (wurde gefixt - war [Di,Do])
Wochenstunden: 39.00h
```

---

## Durchgeführte Lösungsversuche

### Versuch 1: Fixe Wochentage entfernt
**Problem**: MA7 hatte `fixe_tag_wochentage=[Di,Do]` was mit Nachtschicht-Regel kollidierte
**Lösung**: Auf `None` gesetzt
**Ergebnis**: ❌ Keine Besserung

### Versuch 2: Block-Constraint von Hard auf Soft
**Problem**: Hard Constraint `model.Add(heute_n == morgen_n)` war zu restriktiv
**Lösung**: Soft Constraint mit Strafe 50.000 für kaputte Blöcke
**Ergebnis**: ❌ Keine Besserung

### Versuch 3: Freitag-Nachtschichten erlaubt
**Problem**: Constraint erlaubte nur Sa/So Nächte (`weekday >= 5`)
**Lösung**: Geändert zu `weekday >= 4` (Fr erlaubt) und `weekday < 4` für Mo-Do
**Ergebnis**: ❌ Keine Besserung

### Versuch 4: Strafen drastisch reduziert (AKTUELL)
**Problem**: Zu hohe Strafen machten MA7-Zuweisung für Solver unattraktiv
**Lösung**: Strafen reduziert:
- Block gebrochen: 50.000 → **5.000**
- Abweichung von 4 Nächten: 8.000 → **1.000**
- Über 4 Nächte: 20.000 → **3.000**

**Datei**: `schichtplan/services.py` Zeilen 467-497
**Status**: ⏳ Noch nicht getestet

---

## Relevanter Code: MA7 Spezialregel

**Datei**: `schichtplan/services.py` (Zeilen 432-497)

### Schicht-Blockierung (Mo-Do)
```python
if ma.id == 7:
    for tag in tage:
        weekday = tag.weekday()
        
        # Mo-Do: blockiere T und N (nur Z via Post-Processing)
        if weekday < 4:
            model.Add(shifts[(ma.id, tag, 'T')] == 0)
            model.Add(shifts[(ma.id, tag, 'N')] == 0)
        
        # Fr: blockiere T, erlaube N
        elif weekday == 4:
            model.Add(shifts[(ma.id, tag, 'T')] == 0)
        
        # Sa-So: blockiere T, erlaube N
        else:  # weekday >= 5
            model.Add(shifts[(ma.id, tag, 'T')] == 0)
```

### Block-Constraint (2er-Blöcke)
```python
if ma.wochenend_nachtdienst_block and ma.id == 7:
    wochenend_tage = [t for t in tage if t.weekday() >= 4]  # Fr/Sa/So
    
    for i in range(len(wochenend_tage) - 1):
        heute = wochenend_tage[i]
        morgen = wochenend_tage[i + 1]
        
        if (morgen - heute).days == 1:
            heute_n = shifts[(ma.id, heute, 'N')]
            morgen_n = shifts[(ma.id, morgen, 'N')]
            
            block_broken = model.NewBoolVar(f'{ma.id}_block_broken_{heute}')
            model.Add(heute_n != morgen_n).OnlyEnforceIf(block_broken)
            model.Add(heute_n == morgen_n).OnlyEnforceIf(block_broken.Not())
            
            # Strafe für kaputte Blöcke (AKTUELL: 5.000)
            objective_terms.append(block_broken * 5000)
```

### Target-Constraint (4 Nächte)
```python
if ma.id == 7:
    wochenend_tage = [t for t in tage if t.weekday() >= 4]  # Fr/Sa/So
    
    ma7_we_n_count = sum(
        shifts[(ma.id, tag, 'N')] for tag in wochenend_tage
    )
    
    # Abweichung von 4 berechnen
    ma7_abs_abw = model.NewIntVar(0, 20, f'{ma.id}_ma7_abs_abw')
    model.AddAbsEquality(ma7_abs_abw, ma7_we_n_count - 4)
    
    # Basis-Strafe: 1.000 pro Abweichung (AKTUELL)
    objective_terms.append(ma7_abs_abw * 1000)
    
    # Extra-Strafe für 6+ Nachtschichten
    ma7_ueber_4 = model.NewIntVar(0, 10, f'{ma.id}_ma7_ueber_4')
    model.Add(ma7_ueber_4 >= ma7_we_n_count - 4)
    model.Add(ma7_ueber_4 >= 0)
    
    # Zusätzliche 3.000 Strafe für jede Schicht über 4 (AKTUELL)
    objective_terms.append(ma7_ueber_4 * 3000)
```

---

## IST-Stunden Berechnung für MA7

**Datei**: `schichtplan/views.py` (Zeilen 445-461)

```python
# Spezialfall MA7: Z-Dienste = 12.25h wie Nachtschichten
if ma_id == 7 and schichttyp == 'Z':
    ist_stunden += Decimal('12.25')
elif arbeitszeitvereinbarung:
    # Z-Dienste = Wochenstunden / 5
    ist_stunden += wochenstunden / Decimal('5')
else:
    # Standard: Schichttyp-Dauer
    ist_stunden += schichttyp_obj.dauer()
```

---

## Weitere abgeschlossene Arbeiten

### 1. Typ B Flexibilität ✅
- **Vorher**: Genau 4T + 4N (hart)
- **Nachher**: Mindestens 4T + 4N, kann auch 5-6 arbeiten
- **Strafe**: 2.000 pro Schicht über 6

### 2. Fairness nur für Kernteam ✅
- Nur `kategorie='kern'` in Fairness-Berechnungen
- MA7 (hybrid) und MA12 (zusatz) ausgenommen

### 3. Exakt 2 Mitarbeiter pro Schicht ✅
- `model.Add(summe_var == 2)` für T und N
- Hard Constraint (vorher 2-4 flexibel)

### 4. Z-Schicht Stundenberechnung ✅
- MA7: 12h 15min (12.25h)
- MA1: 12h 15min wöchentlich, nur Mittwoch, keine_zusatzdienste=True
- MA12: 39h/5 = 7.8h pro Z-Dienst
- Andere mit Arbeitszeitvereinbarung: wochenstunden/5

---

## Vermutete Ursachen (noch zu prüfen)

1. **Constraint-Konflikte**: 
   - "Exakt 2 pro Schicht" + MA7-Regeln = Unlösbar?
   - Solver findet keine gültige Kombination

2. **Wochenend-Definition**:
   - Zeile 471: `wochenend_tage = [t for t in tage if t.weekday() >= 4]`
   - Sollte Freitag enthalten, aber prüfen ob korrekt verwendet

3. **Solver-Timout**:
   - Eventuell findet Solver keine Lösung in Zeit-Limit
   - Prüfen: Solver-Status (OPTIMAL/FEASIBLE/INFEASIBLE)

4. **Konkurrierende Constraints**:
   - Soll-Ziel 13 Schichten vs. max ~12 Wochenend-Nächte im Monat
   - Block-Constraint + 2-pro-Schicht = zu restriktiv?

---

## Nächste Schritte

### Sofort testen:
1. **Server starten** und neuen Plan generieren
2. **Solver-Status prüfen**: OPTIMAL, FEASIBLE oder INFEASIBLE?
3. **MA7-Schichten zählen**: Wochenend-Nächte und Z-Dienste

### Falls immer noch 0 Schichten:
1. **Debug-Output erweitern**:
   - Relevante MA für Nachtbesetzung ausgeben
   - Wochenend-Tage-Liste für MA7 ausgeben
   - Constraint-Violations loggen

2. **Weitere Lockerungen**:
   - Block-Strafe weiter reduzieren (5.000 → 500)
   - Target-Strafe weiter reduzieren (1.000 → 100)
   - Solver-Timeout erhöhen

3. **Alternative Ansätze**:
   - MA7 aus "exakt 2 pro Schicht" teilweise ausnehmen?
   - Separate Nachtbesetzungs-Logik für Hybrid-Mitarbeiter?
   - Erst MA7 fest einplanen, dann Rest optimieren?

---

## Wichtige Dateien

- `schichtplan/services.py` - Hauptlogik, MA7-Regeln (Zeilen 432-497)
- `schichtplan/views.py` - IST-Stunden-Berechnung (Zeilen 445-461)
- `schichtplan/models.py` - Mitarbeiter-Modell mit Konfiguration

---

## Kontakt-Informationen

**Zuletzt bearbeitet**: 05.02.2026 23:08 UTC  
**Git Branch**: main  
**Nächste Sitzung**: In ~6 Stunden

---

## Quick-Start für nächste Sitzung

```powershell
cd C:\Users\georg\Arbeitszeit_gpt
python manage.py runserver
# Browser: http://127.0.0.1:8000/schichtplan/dienstplan/
# "Plan generieren" klicken und MA7-Zeile prüfen
```
