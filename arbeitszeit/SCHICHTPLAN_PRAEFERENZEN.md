# Schichtplan-Präferenzen - Neue Model-Felder

## Überblick

Die neuen Felder im `Mitarbeiter`-Model wurden basierend auf der Schichtplan-Analyse (6 Monate) hinzugefügt und ermöglichen präzise Schichtplanung gemäß den identifizierten Mustern.

---

## Neue Felder

### 1. `kategorie` (CharField)
**Choices:**
- `kern` - Kernteam - Reguläre Besetzung
- `hybrid` - Hybrid - Teilweise zur Besetzung
- `zusatz` - Zusatzkraft - Nicht zur Besetzung
- `dauerkrank` - Dauerkrank - Nicht verfügbar

**Verwendung:**
```python
ma = Mitarbeiter.objects.get(schichtplan_kennung='MA1')
ma.kategorie  # 'kern'

ma7 = Mitarbeiter.objects.get(schichtplan_kennung='MA7')
ma7.kategorie  # 'hybrid'
```

**Bedeutung:**
- Bestimmt ob MA zur regulären 2T/2N Besetzungsregel zählt
- Steuert die Planungslogik im Generator

---

### 2. `zaehlt_zur_tagbesetzung` (BooleanField)
**Default:** `True`

**Verwendung:**
- `True`: MA zählt zur regulären Tagschicht-Besetzung (2T-Regel)
- `False`: MA ist zusätzlich bei Tagdiensten (z.B. MA7: Di+Do zusätzlich)

**Beispiele:**
```python
ma1.zaehlt_zur_tagbesetzung  # True - zählt an Mittwoch zur Besetzung
ma7.zaehlt_zur_tagbesetzung  # False - Di+Do sind ZUSÄTZLICH
```

---

### 3. `zaehlt_zur_nachtbesetzung` (BooleanField)
**Default:** `True`

**Verwendung:**
- `True`: MA zählt zur regulären Nachtschicht-Besetzung (2N-Regel)
- `False`: MA nicht für Nachtdienste eingeplant

**Beispiele:**
```python
ma1.zaehlt_zur_nachtbesetzung  # False - MA1 macht keine Nachtdienste
ma7.zaehlt_zur_nachtbesetzung  # True - MA7 zählt am Wochenende zur Besetzung
```

---

### 4. `fixe_tag_wochentage` (JSONField)
**Default:** `None`

**Format:** `[0, 1, 2, 3, 4, 5, 6]` wobei 0=Montag, 6=Sonntag

**Verwendung:**
```python
ma1.fixe_tag_wochentage = [2]  # Jeden Mittwoch Tagdienst
ma7.fixe_tag_wochentage = [1, 3]  # Jeden Dienstag + Donnerstag Tagdienst
```

**Bedeutung:**
- Automatische Vorplanung für fixe Wochentage
- Generator setzt diese Dienste zuerst

**Abfrage im Generator:**
```python
if ma.fixe_tag_wochentage:
    for wochentag in ma.fixe_tag_wochentage:
        # Setze Tagdienst an diesem Wochentag
        pass
```

---

### 5. `wochenend_nachtdienst_block` (BooleanField)
**Default:** `False`

**Verwendung:**
- `True`: Nachtdienste am Wochenende immer als 2er-Block (Fr-Sa oder Sa-So)
- `False`: Einzelne Wochenend-Nachtdienste möglich

**Beispiel:**
```python
ma7.wochenend_nachtdienst_block = True
# Generator plant:
# - Freitag Nacht + Samstag Nacht ODER
# - Samstag Nacht + Sonntag Nacht
# Niemals: Nur Freitag ODER nur Samstag einzeln
```

---

### 6. `min_tagschichten_pro_monat` (IntegerField)
**Default:** `None`

**Verwendung:**
```python
# Typ B Mitarbeiter:
ma.schicht_typ = 'typ_b'
ma.min_tagschichten_pro_monat = 4  # Mind. 4 Tagschichten/Monat
```

**Validierung im Generator:**
```python
if ma.min_tagschichten_pro_monat:
    assert tagschichten_count >= ma.min_tagschichten_pro_monat
```

---

### 7. `min_nachtschichten_pro_monat` (IntegerField)
**Default:** `None`

**Verwendung:**
```python
# Typ B Mitarbeiter:
ma.min_nachtschichten_pro_monat = 4  # Mind. 4 Nachtschichten/Monat
```

---

### 8. `target_tagschichten_pro_monat` (IntegerField)
**Default:** `6`

**Verwendung:**
- Soft Constraint (Ziel, keine Pflicht)
- Generator versucht dieses Ziel zu erreichen
- Aus Analyse: Durchschnitt 5,4 Tagdienste/Monat → Ziel 6

```python
# Kernteam:
ma.target_tagschichten_pro_monat = 6  # Ziel: 5-6 Tagdienste

# MA1 (Mittwochskraft):
ma1.target_tagschichten_pro_monat = 4  # Ziel: 3-4 Tagdienste
```

---

### 9. `target_nachtschichten_pro_monat` (IntegerField)
**Default:** `5`

**Verwendung:**
- Soft Constraint
- Aus Analyse: Durchschnitt 5,4 Nachtdienste/Monat → Ziel 5-6

```python
# Kernteam:
ma.target_nachtschichten_pro_monat = 5  # Ziel: 5-6 Nachtdienste

# MA1 (keine Nachtdienste):
ma1.target_nachtschichten_pro_monat = 0
```

---

## Vorkonfigurierte Mitarbeiter (nach Migration)

### MA1 - Mittwochskraft
```python
kategorie = 'kern'
zaehlt_zur_tagbesetzung = True
zaehlt_zur_nachtbesetzung = False
fixe_tag_wochentage = [2]  # Mittwoch
target_tagschichten_pro_monat = 4
target_nachtschichten_pro_monat = 0
```

### MA7 - Hybrid-Rolle
```python
kategorie = 'hybrid'
zaehlt_zur_tagbesetzung = False  # Di+Do ZUSÄTZLICH
zaehlt_zur_nachtbesetzung = True  # Wochenende REGULÄR
fixe_tag_wochentage = [1, 3]  # Di, Do
wochenend_nachtdienst_block = True
nachtschicht_nur_wochenende = True
target_tagschichten_pro_monat = 7
target_nachtschichten_pro_monat = 5
```

### MA3 - Dauerkrank
```python
kategorie = 'dauerkrank'
aktiv = False
zaehlt_zur_tagbesetzung = False
zaehlt_zur_nachtbesetzung = False
```

### MA12 - Zusatzkraft
```python
kategorie = 'zusatz'
zaehlt_zur_tagbesetzung = False
zaehlt_zur_nachtbesetzung = False
nur_zusatzarbeiten = True
```

### Kernteam (MA2, MA4, MA5, MA8, MA9, MA10, MA11, MA13, MA14, MA15)
```python
kategorie = 'kern'
zaehlt_zur_tagbesetzung = True
zaehlt_zur_nachtbesetzung = True
target_tagschichten_pro_monat = 6
target_nachtschichten_pro_monat = 5

# Zusätzlich für Typ B:
if schicht_typ == 'typ_b':
    min_tagschichten_pro_monat = 4
    min_nachtschichten_pro_monat = 4
```

---

## Verwendung im Schichtplan-Generator

### 1. Mitarbeiter-Pool ermitteln

```python
def get_verfuegbare_mitarbeiter_tagdienst(datum):
    """Holt alle MA die an diesem Tag für Tagdienste verfügbar sind"""
    
    wochentag = datum.weekday()
    
    return Mitarbeiter.objects.filter(
        aktiv=True,
        kategorie__in=['kern', 'hybrid'],  # Nicht: zusatz, dauerkrank
        zaehlt_zur_tagbesetzung=True,  # Nur MA die zur Besetzung zählen
    ).exclude(
        # Ausschlüsse: Urlaub, Krank, bereits eingeplant, etc.
    )

def get_verfuegbare_mitarbeiter_nachtdienst(datum):
    """Holt alle MA die an diesem Tag für Nachtdienste verfügbar sind"""
    
    wochentag = datum.weekday()
    
    return Mitarbeiter.objects.filter(
        aktiv=True,
        kategorie__in=['kern', 'hybrid'],
        zaehlt_zur_nachtbesetzung=True,
        kann_nachtschicht=True,
    ).exclude(
        # Ausschlüsse
    )
```

### 2. Fixe Dienste vorplanen

```python
def plane_fixe_dienste(monat, jahr):
    """Plant fixe Wochentage zuerst (MA1, MA7)"""
    
    # Finde alle MA mit fixen Wochentagen
    fixe_mas = Mitarbeiter.objects.filter(
        fixe_tag_wochentage__isnull=False
    )
    
    for ma in fixe_mas:
        for wochentag in ma.fixe_tag_wochentage:
            # Finde alle Tage dieses Wochentags im Monat
            tage = get_tage_im_monat(jahr, monat, wochentag)
            
            for datum in tage:
                # Prüfe Urlaub/Krank
                if not ist_verfuegbar(ma, datum):
                    continue
                
                # Setze Tagdienst
                Schicht.objects.create(
                    mitarbeiter=ma,
                    datum=datum,
                    schichttyp='T',
                    ist_fixe_schicht=True  # Markierung
                )
```

### 3. Wochenend-Nachtdienst-Blöcke

```python
def plane_wochenend_nachtdienste(monat, jahr):
    """Plant Wochenend-Nachtdienste als Blöcke"""
    
    # MA mit Block-Präferenz
    block_mas = Mitarbeiter.objects.filter(
        wochenend_nachtdienst_block=True
    )
    
    for ma in block_mas:
        # Finde Wochenenden
        wochenenden = get_wochenenden(jahr, monat)
        
        for we in wochenenden:
            # Variante 1: Fr-Sa
            # Variante 2: Sa-So
            
            # Prüfe Verfügbarkeit für BEIDE Tage
            if ist_verfuegbar(ma, we.freitag) and ist_verfuegbar(ma, we.samstag):
                # Plane Fr-Sa Block
                Schicht.objects.create(ma, we.freitag, 'N')
                Schicht.objects.create(ma, we.samstag, 'N')
            # ... oder Sa-So
```

### 4. Target-Schichten berücksichtigen

```python
def verteile_restliche_schichten(monat, jahr):
    """Verteilt restliche Schichten gleichmäßig"""
    
    for ma in kernteam:
        # Hole bereits geplante Schichten
        geplante_t = Schicht.objects.filter(
            mitarbeiter=ma,
            datum__month=monat,
            schichttyp='T'
        ).count()
        
        geplante_n = Schicht.objects.filter(
            mitarbeiter=ma,
            datum__month=monat,
            schichttyp='N'
        ).count()
        
        # Berechne noch benötigte Schichten
        target_t = ma.target_tagschichten_pro_monat or 6
        target_n = ma.target_nachtschichten_pro_monat or 5
        
        noch_t = max(0, target_t - geplante_t)
        noch_n = max(0, target_n - geplante_n)
        
        # Plane weitere Schichten...
```

### 5. Min-Schichten validieren

```python
def validiere_mindestanforderungen(monat, jahr):
    """Prüft ob Min-Schichten erfüllt sind"""
    
    fehler = []
    
    for ma in Mitarbeiter.objects.filter(aktiv=True):
        if ma.min_tagschichten_pro_monat:
            count_t = Schicht.objects.filter(
                mitarbeiter=ma,
                datum__month=monat,
                schichttyp='T'
            ).count()
            
            if count_t < ma.min_tagschichten_pro_monat:
                fehler.append(
                    f"{ma.vollname}: Nur {count_t}/{ma.min_tagschichten_pro_monat} "
                    f"Tagschichten (Mindestanforderung nicht erfüllt)"
                )
        
        # Gleich für Nachtschichten...
    
    return fehler
```

---

## Admin-Interface

Die Felder sind automatisch im Django Admin verfügbar. Empfohlene Fieldsets:

```python
# admin.py
class MitarbeiterAdmin(admin.ModelAdmin):
    fieldsets = [
        ('Basisdaten', {
            'fields': ['personalnummer', 'vorname', 'nachname', 'abteilung', 'standort']
        }),
        ('Schichtplan-Kategorie', {
            'fields': [
                'kategorie',
                'zaehlt_zur_tagbesetzung',
                'zaehlt_zur_nachtbesetzung',
            ],
            'classes': ['collapse'],
        }),
        ('Fixe Dienste & Präferenzen', {
            'fields': [
                'fixe_tag_wochentage',
                'wochenend_nachtdienst_block',
            ],
            'classes': ['collapse'],
        }),
        ('Schicht-Ziele', {
            'fields': [
                'min_tagschichten_pro_monat',
                'min_nachtschichten_pro_monat',
                'target_tagschichten_pro_monat',
                'target_nachtschichten_pro_monat',
            ],
            'classes': ['collapse'],
        }),
    ]
```

---

## Zusammenfassung

✅ **9 neue Felder** hinzugefügt  
✅ **Migration 0012** - Schema-Änderungen  
✅ **Migration 0013** - Daten-Konfiguration  
✅ **Vorkonfiguriert** - MA1, MA7, MA3, MA12, Kernteam  

**Die Felder ermöglichen:**
- Präzise Hybrid-Rollen (MA7)
- Fixe Wochentage (MA1, MA7)
- Flexible Besetzungslogik (2T/2N)
- Soft & Hard Constraints
- Wochenend-Blöcke
- Target-basierte Optimierung

**Nächste Schritte:**
1. Schichtplan-Generator implementieren
2. OR-Tools Constraints mit neuen Feldern verknüpfen
3. Admin-Interface testen
