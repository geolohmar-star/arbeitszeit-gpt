# CLAUDE.md – Django Style Guide

## Projektübersicht
- **Framework:** Django (klassisch mit Templates)
- **Sprache:** Python 3.11+
- **Typ:** Solo-Projekt
- **Apps:** `schichtplan`, `arbeitszeit`, `formulare`

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
- Alle Dateien mit **UTF-8** kodieren

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
- Partials immer in `partials/` Unterordner mit `_` Prefix benennen
