# CLAUDE.md – Django Style Guide

## Session-Start (PFLICHT)

**Am Anfang jeder Arbeitssession IMMER zuerst ausfuehren:**

```bash
docker compose up -d
```

Danach kurz pruefen ob der Container laeuft:

```bash
docker compose ps
```

Der PostgreSQL-Container muss `Up` zeigen bevor `manage.py` aufgerufen wird.

---

## Projektübersicht
- **Framework:** Django (klassisch mit Templates)
- **Sprache:** Python 3.11+
- **Typ:** Solo-Projekt
- **Apps:** `schichtplan`, `arbeitszeit`, `formulare`, `hr`, `berechtigungen`
- **Deployment:** Intranet (kein Internet)

---

## ⚠️ KRITISCHE ANFORDERUNG: Offline-Betrieb

**Die Anwendung muss vollständig OFFLINE im Intranet ohne Internet-Anbindung funktionieren.**

### Regeln für externe Ressourcen:

❌ **VERBOTEN:**
- CDN-Links (z.B. `https://cdn.jsdelivr.net/...`)
- Externe API-Aufrufe
- Google Fonts, Font Awesome über CDN
- Einbindung von Libraries über externe URLs

✅ **ERLAUBT:**
- Lokale Dateien in `/static/`
- Alle JavaScript-Libraries lokal gespeichert
- Alle CSS-Frameworks lokal gespeichert
- Schriftarten lokal in `/static/fonts/`

### Beispiel für korrekte Einbindung:

```html
<!-- FALSCH (CDN) -->
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>

<!-- RICHTIG (lokal) -->
{% load static %}
<script src="{% static 'js/d3.v7.min.js' %}"></script>
```

### Checklist vor Deployment:

- [ ] Alle `<script src="https://...">` durch lokale Dateien ersetzt
- [ ] Alle `<link href="https://...">` durch lokale Dateien ersetzt
- [ ] Keine `@import url('https://...')` in CSS
- [ ] Keine externen API-Calls im JavaScript-Code
- [ ] Alle Libraries in `/static/js/` oder `/static/css/` vorhanden

### Aktuell verwendete externe Libraries (müssen lokal sein):

- **D3.js v7** (`/static/js/d3.v7.min.js`) - für Organigramm in hr-App
- **Bootstrap 5** (falls verwendet) - in `/static/css/` und `/static/js/`
- **HTMX** (falls verwendet) - in `/static/js/htmx.min.js`

---

## Apps & ihre Regeln

| App | Ansatz | JavaScript | Besonderheit |
|---|---|---|---|
| `schichtplan` | Klassisches Django | Kein JS | Standard FBVs + Templates |
| `arbeitszeit` | Klassisches Django | Kein JS | Standard FBVs + Templates |
| `formulare` | Django + HTMX | HTMX + minimales Vanilla JS | Partial Rendering, Inline-Validierung |

> **Wichtig für Claude Code:** Bevor du Code schreibst, prüfe immer in welcher App du arbeitest und halte die app-spezifischen Regeln ein. Mische niemals HTMX-Patterns in `schichtplan` oder `arbeitszeit` ein.

---

## Python & Django Konventionen (alle Apps)

### Allgemein
- Folge **PEP 8** für den gesamten Python-Code
- Maximale Zeilenlänge: **88 Zeichen** (Black-Standard)
- Einrückung: **4 Spaces** (keine Tabs)
- Strings: **doppelte Anführungszeichen** `"`
- Alle Dateien mit **UTF-8** kodieren – das gilt ABSOLUT fuer alle Dateitypen: `.py`, `.html`, `.json`, `.txt`, `.md`, `.toml`

### Benennung
| Element | Stil | Beispiel |
|---|---|---|
| Variablen & Funktionen | snake_case | `user_profile` |
| Klassen | PascalCase | `UserProfile` |
| Konstanten | UPPER_SNAKE_CASE | `MAX_UPLOAD_SIZE` |
| URLs (name) | snake_case | `user_detail` |
| Templates | snake_case.html | `user_detail.html` |
| Apps | snake_case, singular | `schichtplan` |

---

## Projektstruktur

```
projekt/
├── manage.py
├── requirements.txt
├── CLAUDE.md
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── schichtplan/         # Klassisches Django
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── forms.py
│   │   ├── admin.py
│   │   └── templates/
│   │       └── schichtplan/
│   ├── arbeitszeit/         # Klassisches Django
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── forms.py
│   │   ├── admin.py
│   │   └── templates/
│   │       └── arbeitszeit/
│   └── formulare/           # HTMX-App
│       ├── models.py
│       ├── views.py
│       ├── urls.py
│       ├── forms.py
│       ├── admin.py
│       └── templates/
│           └── formulare/
│               ├── partials/    # Nur HTMX-Partial-Templates hier!
│               └── *.html
├── static/
│   ├── css/
│   ├── js/
│   │   └── formulare.js     # Vanilla JS nur für formulare App
│   └── images/
└── templates/
    └── base.html
```

---

## App: `schichtplan` & `arbeitszeit` (Klassisches Django)

### Views
- Ausschließlich **Function-Based Views (FBVs)**
- Kein JavaScript, kein HTMX
- Immer `login_required` bei geschützten Views

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

@login_required
def schicht_detail(request, pk):
    schicht = get_object_or_404(Schicht, pk=pk)
    return render(request, "schichtplan/schicht_detail.html", {"schicht": schicht})
```

### Templates
- Keine HTMX-Attribute (`hx-*`) in diesen Apps
- Keine `<script>`-Tags direkt in Templates
- Nur Standard Django Template Tags

```html
{% extends "base.html" %}

{% block content %}
  <h1>{{ schicht.bezeichnung }}</h1>
{% endblock %}
```

### Forms
- Klassische Django-Forms mit POST und Seitenneuladen
- Immer `{% csrf_token %}`

```html
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Speichern</button>
</form>
```

---

## App: `formulare` (HTMX + Vanilla JS)

### Grundprinzip
- **HTMX** übernimmt alle dynamischen Interaktionen
- **Vanilla JS** nur für das, was HTMX nicht kann (z.B. DOM-Manipulation vor dem Request)
- Kein jQuery, kein großes JS-Framework
- HTMX via CDN oder lokal in `base.html` einbinden

### Views – HTMX-Pattern
- Views erkennen ob es ein HTMX-Request ist via `request.headers.get("HX-Request")`
- Bei HTMX-Request → nur Partial-Template zurückgeben
- Bei normalem Request → volles Template zurückgeben

```python
from django.shortcuts import render, get_object_or_404

def formular_erstellen(request):
    form = MeinFormular(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            form.save()
            # Bei HTMX: Erfolgsmeldung als Partial zurückgeben
            if request.headers.get("HX-Request"):
                return render(request, "formulare/partials/_erfolg.html")
        # Bei HTMX + Fehler: Formular als Partial zurückgeben
        if request.headers.get("HX-Request"):
            return render(request, "formulare/partials/_formular.html", {"form": form})

    return render(request, "formulare/formular_erstellen.html", {"form": form})
```

### Inline-Validierung
- Einzelne Felder per `hx-post` validieren
- Fehler als kleines Partial zurückgeben

```html
<input
  type="text"
  name="name"
  hx-post="{% url 'formulare:validate_name' %}"
  hx-trigger="blur"
  hx-target="#name-fehler"
  hx-swap="innerHTML"
>
<div id="name-fehler"></div>
```

### Dynamische Felder (Zeilen hinzufügen)
- Neue Zeilen per `hx-get` nachladen
- Partial-Template für jede neue Zeile

```html
<button
  hx-get="{% url 'formulare:neue_zeile' %}"
  hx-target="#zeilen-container"
  hx-swap="beforeend"
>
  + Zeile hinzufügen
</button>
```

### Modals / Overlays
- Modal-Inhalt per HTMX nachladen
- Modal-Container immer in `base.html` vorhanden
- Schließen per `hx-on` oder kleines Vanilla JS

```html
<!-- In base.html -->
<div id="modal-container"></div>

<!-- Trigger -->
<button
  hx-get="{% url 'formulare:modal_inhalt' %}"
  hx-target="#modal-container"
  hx-swap="innerHTML"
>
  Öffnen
</button>
```

### Live-Suche
- Suche mit `hx-trigger="keyup changed delay:300ms"` entprellen
- Ergebnisse als Partial zurückgeben

```html
<input
  type="search"
  name="q"
  hx-get="{% url 'formulare:suche' %}"
  hx-trigger="keyup changed delay:300ms"
  hx-target="#suchergebnisse"
  placeholder="Suchen..."
>
<div id="suchergebnisse"></div>
```

### Partial Templates
- Alle Partials liegen in `formulare/templates/formulare/partials/`
- Benennung mit Unterstrich-Prefix: `_formular.html`, `_zeile.html`, `_modal.html`
- Partials haben **keinen** `{% extends %}`-Block

### Vanilla JS in `formulare`
- Nur in `static/js/formulare.js`
- Kein Inline-JS in Templates
- Nur für Dinge die HTMX nicht kann (z.B. Datei-Previews, komplexe DOM-Manipulationen)
- HTMX-Events nutzen wenn möglich (`htmx:afterSwap`, `htmx:beforeRequest`)

```javascript
// formulare.js
document.addEventListener("htmx:afterSwap", function(event) {
    // z.B. nach HTMX-Swap neue Felder initialisieren
});
```

### CSRF bei HTMX
- CSRF-Token global per HTMX-Event setzen – einmalig in `base.html`

```html
<!-- In base.html -->
<meta name="csrf-token" content="{{ csrf_token }}">
<script>
  document.addEventListener("DOMContentLoaded", function() {
    document.body.addEventListener("htmx:configRequest", function(event) {
      event.detail.headers["X-CSRFToken"] = document.querySelector("meta[name='csrf-token']").content;
    });
  });
</script>
```

---

## Models (alle Apps)

- Jedes Model bekommt eine `__str__()` Methode
- Felder alphabetisch sortieren (außer `id`)
- `Meta`-Klasse immer angeben

```python
class Schicht(models.Model):
    bezeichnung = models.CharField(max_length=200)
    ende = models.TimeField()
    start = models.TimeField()

    class Meta:
        ordering = ["start"]
        verbose_name = "Schicht"
        verbose_name_plural = "Schichten"

    def __str__(self):
        return self.bezeichnung
```

---

## URLs (alle Apps)

- URL-Namen immer vergeben (`name=`)
- Namespaces pro App (`app_name`)
- Nie hartcodierte URLs – immer `{% url %}` in Templates

```python
# apps/formulare/urls.py
app_name = "formulare"

urlpatterns = [
    path("", views.formular_liste, name="liste"),
    path("erstellen/", views.formular_erstellen, name="erstellen"),
    path("validate/name/", views.validate_name, name="validate_name"),
    path("neue-zeile/", views.neue_zeile, name="neue_zeile"),
    path("suche/", views.suche, name="suche"),
]
```

---

## Admin (alle Apps)

```python
@admin.register(Schicht)
class SchichtAdmin(admin.ModelAdmin):
    list_display = ["bezeichnung", "start", "ende"]
    list_filter = ["start"]
    search_fields = ["bezeichnung"]
```

---

## Kommentare & Docstrings

- Kommentare auf **Deutsch**
- Komplexe Funktionen mit Docstring
- HTMX-Views zusätzlich mit `# HTMX-View` kennzeichnen

```python
def neue_zeile(request):
    """Gibt eine neue leere Formularzeile als Partial zurück.

    Wird per HTMX aufgerufen wenn der Nutzer auf '+ Zeile hinzufügen' klickt.
    """
    # HTMX-View – gibt nur Partial zurück
    return render(request, "formulare/partials/_zeile.html")
```

---

## Digitale Signaturen in Workflow-PDFs (GRUNDSATZ)

**Jedes PDF das aus einem mehrstufigen Workflow-Prozess entsteht, muss mehrere digitale Signaturen tragen – eine pro Bearbeiter in Schritt-Reihenfolge.**

### Pflichtbestandteile jedes Workflow-PDFs

1. **Bearbeitungsverlauf-Tabelle** im Template (`workflow_tasks` im Kontext):
   - Alle Schritte der Workflow-Instanz
   - Bearbeiter, Erledigungsdatum, Entscheidung pro Schritt

2. **Digitale Signaturen** im View (inkrementell, eine pro Bearbeiter):
   - Antragsteller zuerst
   - Dann alle `erledigt_von`-User aus WorkflowTasks in `step__reihenfolge`

3. **Signatur-Sektion** im PDF-Template:
   - Zeigt Namen + Datum aller Unterzeichner visuell an

### Standard-Implementierung im View

```python
# 1. Workflow-Tasks laden
workflow_tasks = []
if antrag.workflow_instance:
    from workflow.models import WorkflowTask
    workflow_tasks = list(
        WorkflowTask.objects
        .filter(instance=antrag.workflow_instance)
        .select_related("step", "erledigt_von")
        .order_by("step__reihenfolge")
    )

# 2. Template-Kontext: workflow_tasks mitgeben
html_string = render_to_string("...", {"antrag": antrag, "workflow_tasks": workflow_tasks, ...})
pdf = HTML(...).write_pdf()

# 3. Mehrfach signieren mit Hilfsfunktionen aus formulare/views.py
unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner, dateiname)
```

### Bestehende Hilfsfunktionen (formulare/views.py)

- `_sammle_workflow_unterzeichner(antrag, antragsteller_user)` → Liste aller Unterzeichner
- `_signiere_pdf_alle_unterzeichner(pdf_bytes, unterzeichner, dateiname)` → inkrementell signiertes PDF

### Wichtig: Backend-Logik (signatur/backends/intern.py)

Das Backend zaehlt vorhandene Signaturen selbst (`reader.embedded_signatures`)
und vergibt automatisch eindeutige Feldnamen (`Signatur_1`, `Signatur_2`, ...).
Stempel werden nebeneinander positioniert. Kein manuelles Zaehlen im View noetig.

### Checklist neues Workflow-PDF

- [ ] `workflow_tasks` in Template-Kontext
- [ ] Bearbeitungsverlauf-Tabelle im Template
- [ ] Signatur-Sektion im Template
- [ ] `_sammle_workflow_unterzeichner` im View
- [ ] `_signiere_pdf_alle_unterzeichner` statt `_signiere_pdf_sicher`

---

## Sicherheit

- Niemals `DEBUG = True` in Produktion
- Geheime Schlüssel immer in `.env` (nie im Code)
- `.env` immer in `.gitignore`
- `python-decouple` für Umgebungsvariablen

```python
from decouple import config

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
```

---

## Content Security Policy (CSP) – Pflichtregeln

**Hintergrund:** AdGuard (und andere Browser-Extensions) injizieren einen strikten
`script-src 'self'`-Header. Das blockiert jeden inline JS-Code im Browser.

### Was VERBOTEN ist (CSP-Violation):

```html
<!-- FALSCH: Inline-Script-Block -->
<script>
  var x = 1;
</script>

<!-- FALSCH: Inline-Event-Handler -->
<button onclick="tuWas()">Klick</button>
<select onchange="ladeEtwas()">...</select>
<input oninput="filtere()">

<!-- FALSCH: Server-Daten direkt in Script einspeisen -->
<script>var DATA = {{ daten|safe }};</script>
```

### Was KORREKT ist:

**1. JS immer in externe Dateien auslagern:**
```html
<!-- Template: nur externe Datei laden -->
{% load static %}
<script src="{% static 'js/meine_seite.js' %}"></script>
```

**2. Event-Handler via addEventListener verdrahten:**
```javascript
// static/js/meine_seite.js
document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("mein-btn").addEventListener("click", tuWas);
    document.getElementById("mein-select").addEventListener("change", ladeEtwas);
});
```

**3. Event Delegation fuer dynamisch gerenderte Elemente:**
```html
<!-- Template: data-action statt onclick -->
<button data-action="loeschen" data-id="{{ obj.pk }}">Loeschen</button>
```
```javascript
// JS: ein einziger Listener fuer alle data-action-Buttons
document.body.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-action]");
    if (!btn) return;
    var action = btn.dataset.action;
    if (action === "loeschen") { loeschen(btn.dataset.id); }
});
```

**4. Server-Daten CSP-sicher einbetten (json_script):**
```html
<!-- Template: json_script-Filter erzeugt <script type="application/json"> -->
{{ meine_daten|json_script:"meine-daten" }}
```
```javascript
// JS: sicher auslesen (kein eval, kein inline)
var data = JSON.parse(document.getElementById("meine-daten").textContent);
```
> **WICHTIG:** Den View-Wert als Python-Objekt (list/dict) uebergeben – NICHT
> vorher mit `json.dumps()` serialisieren, sonst liest `JSON.parse()` einen
> String statt ein Array (doppelte Serialisierung).

**5. Print-Button und aehnliche Einzeiler:**
```html
<button id="btn-print">Drucken</button>
{% block extra_js %}
{% load static %}
<script src="{% static 'js/meine_seite.js' %}"></script>
{% endblock %}
```
```javascript
document.getElementById("btn-print").addEventListener("click", function () {
    window.print();
});
```

### base.html – verfuegbare Bloecke fuer JS:

```html
{% block extra_js %}{% endblock %}  <!-- direkt vor </body> -->
```

### Dateinamen-Konvention fuer seitenspezifische JS-Dateien:

| Template | JS-Datei |
|---|---|
| `formulare/team_builder.html` | `static/js/team_builder.js` |
| `workflow/workflow_editor.html` | `static/js/workflow_editor.js` |
| `veranstaltungen/gutschrift_pdf.html` | `static/js/gutschrift_pdf.js` |
| `xyz/meine_seite.html` | `static/js/meine_seite.js` |

---

## Was Claude Code tun soll

- Code immer auf **Deutsch** kommentieren
- **Vor jedem Code prüfen:** In welcher App wird gearbeitet?
  - `schichtplan` / `arbeitszeit` → kein HTMX, kein JS, klassisches Django
  - `formulare` → HTMX-Patterns verwenden, Partials in `partials/`
- PEP 8 und diesen Style Guide strikt einhalten
- Neue Features als eigene Django-App anlegen
- Keine externen Pakete ohne Rückfrage installieren
- Bei Datenbankänderungen immer Migrations erstellen
- Keine `print()`-Statements – stattdessen `logging`
- **Keine Emojis in Python-Code** (auch nicht in Strings, Kommentaren oder Logs) – Windows cp1252 kann Unicode-Emojis nicht kodieren und wirft `UnicodeEncodeError`
- **Umlaute (ä, ö, ü, ß, Ä, Ö, Ü) in HTML-Templates erlaubt** – Templates sind UTF-8 kodiert, Umlaute dürfen direkt verwendet werden. Nur in Python-Dateien weiterhin ausschreiben (ae, oe, ue usw.)
- **Fixtures immer als UTF-8 speichern** – `dumpdata` schreibt manchmal cp1252 (Windows). Nach jedem `dumpdata` pruefen: `python -c "open('datei.json', encoding='utf-8').read()"`. Falls Fehler: `json.load(open(..., encoding='cp1252'))` lesen, dann als UTF-8 neu schreiben. Werkzeug dafuer: `python manage.py dumpdata ... | python -c "import sys,json; json.dump(json.load(sys.stdin), open('datei.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)"`
- Partials immer in `partials/` Unterordner mit `_` Prefix benennen

---

# Geplante Features (Roadmap)

## 🎯 Visueller Workflow-Builder (Stichwort: "workflow plannen")

**Status:** Geplant, noch nicht implementiert
**Prioritaet:** Mittel
**Aufwand:** 5-7 Arbeitstage

### Beschreibung

Ein visueller Workflow-Builder aehnlich bubble-charts/Flussdiagrammen, mit dem Workflows per Drag & Drop erstellt werden koennen.

**Use Case:** Z-AG Workflow visuell definieren:
```
MA stellt Antrag
  → Vorgesetzter prueft
  → Entscheidung (genehmigt/abgelehnt)
     → JA: Team-Queue → Erledigt
     → NEIN: Zurueck an MA
```

### Features

**Node-Typen:**
- Start-Node: Antrag wird erstellt
- Genehmigung-Node: User mit Rolle muss genehmigen (konfigurierbar: Vorgesetzter, GF, etc.)
- Entscheidungs-Node: Verzweigung (ja/nein, genehmigt/abgelehnt)
- Team-Queue-Node: Antrag landet in Team-Bearbeitungsstapel
- Aktion-Node: Python-Code oder Webhook (Email, PDF, Zeiterfassung buchen)
- Warte-Node: Timeout mit Eskalation
- Ende-Node: Final-Status (erledigt, abgelehnt)

**Funktionen:**
- Drag & Drop Editor
- Nodes verbinden mit Edges
- Konfiguration pro Node (Rolle, Team, Bedingung)
- Workflow als JSON speichern
- Workflow-Templates (vordefinierte Standard-Workflows)
- Workflow-Versionierung

**Zusaetzliche Features (spaeter):**
- Kommentare an Nodes
- Parallele Pfade (mehrere Genehmiger gleichzeitig)
- Sub-Workflows
- Bedingungen mit Logik (IF Dauer > 5 Tage THEN andere Genehmiger)

### Technologie

**Frontend:**
- **Rete.js** (MIT Lizenz, vanilla JS) - Empfohlen fuer Django-Setup
- Alternative: jsPlumb, React Flow

**Backend:**
- Model: `WorkflowDefinition` (name, definition_json)
- Model: `WorkflowInstance` (antrag, current_node, history)
- Workflow-Engine: JSON-Definition interpretieren und ausfuehren

**JSON-Struktur:**
```json
{
  "name": "Z-AG Standard",
  "version": "1.0",
  "nodes": [
    {"id": "node-1", "type": "start", "label": "MA stellt Antrag"},
    {"id": "node-2", "type": "approval", "label": "Vorgesetzter",
     "config": {"role": "vorgesetzter", "timeout_days": 3}},
    {"id": "node-3", "type": "decision", "label": "Genehmigt?"},
    {"id": "node-4", "type": "team_queue", "label": "Team",
     "config": {"team": "zeit"}},
    {"id": "node-5", "type": "end", "label": "Erledigt"}
  ],
  "edges": [
    {"from": "node-1", "to": "node-2"},
    {"from": "node-2", "to": "node-3"},
    {"from": "node-3", "to": "node-4", "condition": "genehmigt"},
    {"from": "node-3", "to": "node-6", "condition": "abgelehnt"}
  ]
}
```

### Implementierungsplan

**Phase 1: Basis-Editor (2 Tage)**
- Rete.js lokal einbinden (static/js/)
- 3 Node-Typen: Start, Aktion, Ende
- Nodes verbinden (Drag & Drop)
- JSON speichern/laden via Django-Backend

**Phase 2: Alle Node-Typen (1-2 Tage)**
- Genehmigung-Node mit Rollen-Auswahl
- Entscheidungs-Node mit Bedingungen
- Team-Queue-Node mit Team-Auswahl
- Konfigurations-Panel fuer Nodes

**Phase 3: Workflow-Engine (2 Tage)**
- JSON → Workflow-Instanz erstellen
- Status-Maschine (aktueller Node, naechster Node)
- Routing bei Entscheidungen
- Integration mit bestehendem Antragssystem (ZAGAntrag, etc.)

**Phase 4: Features (1 Tag)**
- Workflow-Templates (Standard-Workflows vordefiniert)
- Testen-Modus (Workflow durchspielen ohne echte Daten)
- Versionierung

### Voraussetzungen

- Team-Queue-System muss existieren (bereits implementiert ✓)
- Stellenbasierte Genehmigungen (bereits implementiert ✓)

### Erinnerung an Implementierung

**Wenn User sagt:** "workflow plannen", "workflows bauen", "Workflow-Builder"
**Dann:** Diese Sektion zeigen und fragen ob jetzt implementiert werden soll.

### Offline-Anforderung

**WICHTIG:** Rete.js muss lokal gespeichert werden:
```bash
# Download von https://github.com/retejs/rete
# Speichern unter: static/js/rete.min.js
```

Keine CDN-Links verwenden!
