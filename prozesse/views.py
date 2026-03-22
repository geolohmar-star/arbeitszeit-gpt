import ast
import json
import operator
import re
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import FeldGruppe, FormularEintrag, FormularSchema


def _normalisiere_uhrzeit(wert):
    """Wandelt '1430' oder '14:30' oder '14.30' in '14:30' um.

    Gibt None zurueck wenn das Format ungueltig ist.
    """
    wert = wert.strip().replace(".", ":").replace(" ", "")
    if re.match(r"^\d{4}$", wert):
        wert = wert[:2] + ":" + wert[2:]
    if not re.match(r"^\d{1,2}:\d{2}$", wert):
        return None
    h, m = wert.split(":")
    h, m = int(h), int(m)
    if h > 23 or m > 59:
        return None
    return f"{h:02d}:{m:02d}"


# ---------------------------------------------------------------------------
# Formel-Evaluator (serverseitig, sicher via ast)
# Unterstuetzte Syntax:
#   Arithmetik:   + - * / ( )
#   Vergleich:    == != > < >= <=  (Ergebnis: True/False → 1/0 in Zahlen)
#   WENN(bed; ja; nein)
#   RUNDEN(wert; stellen)    ABS(wert)    MIN(a;b)    MAX(a;b)
#   TAGE(datum1; datum2)     → ganzzahlige Differenz in Tagen
#   STUNDEN(zeit1; zeit2)    → Dezimalstunden (z.B. 2.5 fuer 2h30)
#   MINUTEN(zeit1; zeit2)    → ganzzahlige Minuten
#   HEUTE()                  → aktuelles Datum als ISO-String
# ---------------------------------------------------------------------------

_ERLAUBTE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _parse_datum(wert):
    """Wandelt ISO-Datum-String (YYYY-MM-DD) in date-Objekt um."""
    if isinstance(wert, date):
        return wert
    wert = str(wert).strip()
    try:
        return date.fromisoformat(wert)
    except ValueError:
        raise ValueError(f"Kein gueltiges Datum: {wert!r}")


def _parse_uhrzeit_minuten(wert):
    """Gibt Uhrzeit als Minuten seit Mitternacht zurueck."""
    wert = _normalisiere_uhrzeit(str(wert).strip())
    if wert is None:
        raise ValueError("Keine gueltige Uhrzeit")
    h, m = wert.split(":")
    return int(h) * 60 + int(m)


def _ast_eval(node, feld_werte):
    """Wertet einen ast-Knoten sicher aus (nur erlaubte Konstrukte)."""
    # Zahl-Literal
    if isinstance(node, ast.Constant):
        return node.value

    # Variable: {{feld_id}} wurde vorab zu _F_feld_id ersetzt
    if isinstance(node, ast.Name):
        schluessel = node.id
        if schluessel not in feld_werte:
            raise ValueError(f"Unbekanntes Feld: {schluessel}")
        return feld_werte[schluessel]

    # Binaere Operation: +  -  *  /
    if isinstance(node, ast.BinOp):
        op = _ERLAUBTE_OPS.get(type(node.op))
        if op is None:
            raise ValueError("Nicht erlaubter Operator")
        l = _ast_eval(node.left, feld_werte)
        r = _ast_eval(node.right, feld_werte)
        if isinstance(node.op, ast.Div) and r == 0:
            raise ZeroDivisionError("Division durch Null")
        return op(float(l), float(r))

    # Vergleich: ==  !=  >  <  >=  <=
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = _ERLAUBTE_OPS.get(type(node.ops[0]))
        if op is None:
            raise ValueError("Nicht erlaubter Vergleichsoperator")
        l = _ast_eval(node.left, feld_werte)
        r = _ast_eval(node.comparators[0], feld_werte)
        return op(l, r)

    # Vorzeichen: -x
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -float(_ast_eval(node.operand, feld_werte))

    # Funktionsaufrufe
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id.upper()
        args = [_ast_eval(a, feld_werte) for a in node.args]

        if name == "WENN":
            if len(args) != 3:
                raise ValueError("WENN braucht 3 Argumente: WENN(bed; ja; nein)")
            return args[1] if args[0] else args[2]

        if name == "RUNDEN":
            if len(args) != 2:
                raise ValueError("RUNDEN braucht 2 Argumente: RUNDEN(wert; stellen)")
            return round(float(args[0]), int(args[1]))

        if name == "ABS":
            return abs(float(args[0]))

        if name == "MIN":
            return min(float(a) for a in args)

        if name == "MAX":
            return max(float(a) for a in args)

        if name == "HEUTE":
            return date.today().isoformat()

        if name == "TAGE":
            if len(args) != 2:
                raise ValueError("TAGE braucht 2 Argumente: TAGE(datum1; datum2)")
            d1 = _parse_datum(args[0])
            d2 = _parse_datum(args[1])
            return (d2 - d1).days

        if name == "STUNDEN":
            if len(args) != 2:
                raise ValueError("STUNDEN braucht 2 Argumente: STUNDEN(zeit1; zeit2)")
            m1 = _parse_uhrzeit_minuten(args[0])
            m2 = _parse_uhrzeit_minuten(args[1])
            diff = m2 - m1
            if diff < 0:
                diff += 24 * 60  # Mitternachts-Ueberlauf
            return round(diff / 60, 4)

        if name == "MINUTEN":
            if len(args) != 2:
                raise ValueError("MINUTEN braucht 2 Argumente: MINUTEN(zeit1; zeit2)")
            m1 = _parse_uhrzeit_minuten(args[0])
            m2 = _parse_uhrzeit_minuten(args[1])
            diff = m2 - m1
            if diff < 0:
                diff += 24 * 60
            return diff

        raise ValueError(f"Unbekannte Funktion: {name}")

    raise ValueError(f"Nicht erlaubter Ausdruck: {ast.dump(node)}")


def _berechne_formel(formel, feld_werte):
    """Wertet eine Formel-Zeichenkette sicher aus.

    feld_werte: dict {feld_id: wert} (Strings aus dem Formular)
    Gibt das Ergebnis zurueck oder None bei Fehler.
    """
    if not formel:
        return None

    # Semikolon → Komma (Funktions-Trennzeichen), {{feld_id}} → _F_feld_id
    ausdruck = formel.replace(";", ",")
    ausdruck = re.sub(r"\{\{(\w+)\}\}", r"_F_\1", ausdruck)

    # feld_werte mit _F_-Prefix aufbauen (verhindert Name-Kollisionen)
    vorbereitet = {}
    for k, v in feld_werte.items():
        # Zahlen umwandeln wo moeglich
        try:
            vorbereitet["_F_" + k] = float(str(v).replace(",", ".")) if v not in ("", None) else ""
        except (ValueError, TypeError):
            vorbereitet["_F_" + k] = str(v) if v is not None else ""

    try:
        tree = ast.parse(ausdruck, mode="eval")
        return _ast_eval(tree.body, vorbereitet)
    except Exception:
        return None


def _validiere_iban(iban):
    """Prueft IBAN via Modulo-97-Algorithmus (ISO 13616)."""
    iban = iban.replace(" ", "").upper()
    if len(iban) < 15 or len(iban) > 34:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = ""
    for c in rearranged:
        if c.isalpha():
            numeric += str(ord(c) - ord("A") + 10)
        elif c.isdigit():
            numeric += c
        else:
            return False
    return int(numeric) % 97 == 1


def _verarbeite_schema(schema):
    """Bereitet das Schema fuer den Renderer vor.

    Gibt render_items zurueck – eine geordnete Liste von Render-Anweisungen:
    - 'standalone': normales Eingabefeld
    - 'textblock':  Fliesstext mit eingebetteten Inline-Feldern (segmente)
    - 'abschnitt':  Abschnitts-Ueberschrift / Hinweistext
    - 'trennlinie': Horizontale Trennlinie
    """
    alle_felder = schema.felder()
    # Map aller Eingabefelder fuer schnelle Referenz
    feld_map = {
        f["id"]: f for f in alle_felder
        if f.get("typ") not in ("textblock", "abschnitt", "trennlinie")
    }

    # Felder-IDs die in Textblöcken eingebettet sind → nicht standalone rendern
    inline_ids = set()
    for f in alle_felder:
        if f.get("typ") == "textblock":
            for m in re.finditer(r"\{\{(\w+)\}\}", f.get("text", "")):
                inline_ids.add(m.group(1))

    render_items = []
    for f in alle_felder:
        typ = f.get("typ", "text")
        breite = f.get("breite", 100)

        if typ == "textblock":
            # Text in Segmente aufteilen: abwechselnd Text und Feld-Referenzen
            text = f.get("text", "")
            teile = re.split(r"\{\{(\w+)\}\}", text)
            segmente = []
            for i, teil in enumerate(teile):
                if i % 2 == 0:
                    segmente.append({"typ": "text", "inhalt": teil})
                else:
                    ref = feld_map.get(teil)
                    if ref:
                        segmente.append({"typ": "feld", "feld": ref})
                    else:
                        segmente.append({"typ": "text", "inhalt": "{{" + teil + "}}"})
            render_items.append({
                "render_typ": "textblock",
                "breite": breite,
                "segmente": segmente,
            })

        elif typ == "abschnitt":
            render_items.append({
                "render_typ": "abschnitt",
                "breite": breite,
                "text": f.get("text", ""),
                "groesse": f.get("groesse", "mittel"),
                "ausrichtung": f.get("ausrichtung", "links"),
                "stil": f.get("stil", "normal"),
            })

        elif typ == "trennlinie":
            render_items.append({"render_typ": "trennlinie", "breite": breite})

        elif typ == "leerblock":
            render_items.append({"render_typ": "leerblock", "breite": breite})

        elif typ == "link":
            render_items.append({
                "render_typ": "link",
                "breite": breite,
                "link_text": f.get("link_text", ""),
                "url": f.get("url", "#"),
                "newtab": f.get("newtab", True),
            })

        elif typ == "berechnung":
            render_items.append({
                "render_typ": "berechnung",
                "breite": breite,
                "id": f.get("id", ""),
                "label": f.get("label", ""),
                "formel": f.get("formel", ""),
                "einheit": f.get("einheit", ""),
                "dezimalstellen": f.get("dezimalstellen", 2),
            })

        elif f.get("id") not in inline_ids:
            # Nur standalone rendern wenn nicht in einem Textblock eingebettet
            render_items.append({
                "render_typ": "standalone",
                "breite": breite,
                "feld": f,
            })

    return render_items


_KEINE_EINGABEFELDER = {"textblock", "abschnitt", "trennlinie", "leerblock", "link", "berechnung"}


def _alle_eingabefelder(schema):
    """Gibt alle Eingabefelder (nicht Struktur- oder Berechnungstypen) zurueck."""
    return [
        f for f in schema.felder()
        if f.get("typ") not in _KEINE_EINGABEFELDER
    ]


def _ist_prozessverantwortlicher(user):
    """Hilfsfunktion: prueft ob User Prozessverantwortlicher ist."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name="Prozessverantwortliche").exists()


# ---------------------------------------------------------------------------
# Bausteine (FeldGruppe)
# ---------------------------------------------------------------------------

@login_required
def baustein_liste(request):
    """Uebersicht aller Bausteine (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")
    bausteine = FeldGruppe.objects.all()
    return render(request, "prozesse/baustein_liste.html", {"bausteine": bausteine})


@login_required
def baustein_erstellen(request):
    """Neuen Baustein erstellen (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        schema_raw = request.POST.get("schema_json", "{}")
        try:
            felder_json = json.loads(schema_raw)
        except json.JSONDecodeError:
            felder_json = {"felder": []}

        if not name:
            messages.error(request, "Name ist Pflichtfeld.")
            return render(request, "prozesse/baustein_editor.html", {
                "schema_json_str": schema_raw,
                "name": name,
                "beschreibung": beschreibung,
            })

        baustein = FeldGruppe.objects.create(
            name=name,
            beschreibung=beschreibung,
            felder_json=felder_json,
            erstellt_von=request.user,
        )
        messages.success(request, f'Baustein "{baustein.name}" wurde erstellt.')
        return redirect("prozesse:baustein_bearbeiten", pk=baustein.pk)

    return render(request, "prozesse/baustein_editor.html", {
        "schema_json_str": json.dumps({"felder": []}, ensure_ascii=False),
        "name": "",
        "beschreibung": "",
    })


@login_required
def baustein_bearbeiten(request, pk):
    """Baustein bearbeiten (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    baustein = get_object_or_404(FeldGruppe, pk=pk)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        schema_raw = request.POST.get("schema_json", "{}")
        try:
            felder_json = json.loads(schema_raw)
        except json.JSONDecodeError:
            messages.error(request, "Ungueltige JSON-Struktur.")
            return render(request, "prozesse/baustein_editor.html", {
                "baustein": baustein,
                "schema_json_str": schema_raw,
            })

        baustein.name = name
        baustein.beschreibung = beschreibung
        baustein.felder_json = felder_json
        baustein.save()
        messages.success(request, f'Baustein "{baustein.name}" gespeichert.')
        return redirect("prozesse:baustein_bearbeiten", pk=baustein.pk)

    return render(request, "prozesse/baustein_editor.html", {
        "baustein": baustein,
        "schema_json_str": json.dumps(baustein.felder_json, ensure_ascii=False),
    })


@login_required
@require_POST
def baustein_loeschen(request, pk):
    """Baustein loeschen (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")
    baustein = get_object_or_404(FeldGruppe, pk=pk)
    name = baustein.name
    baustein.delete()
    messages.success(request, f'Baustein "{name}" geloescht.')
    return redirect("prozesse:baustein_liste")


@login_required
def baustein_liste_json(request):
    """JSON-Endpunkt: alle Bausteine mit ihren Feldern (fuer Schema-Editor)."""
    if not _ist_prozessverantwortlicher(request.user):
        return JsonResponse({"fehler": "Kein Zugriff."}, status=403)
    bausteine = []
    for b in FeldGruppe.objects.all():
        felder = b.felder()
        bausteine.append({
            "id": b.pk,
            "name": b.name,
            "beschreibung": b.beschreibung,
            "anzahl_felder": len(felder),
            "felder": felder,
        })
    return JsonResponse({"bausteine": bausteine})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    """Uebersicht aller aktiven Formular-Schemata."""
    ist_pv = _ist_prozessverantwortlicher(request.user)

    if ist_pv:
        schemata = FormularSchema.objects.all().order_by("name")
    else:
        schemata = FormularSchema.objects.filter(aktiv=True).order_by("name")

    return render(request, "prozesse/dashboard.html", {
        "schemata": schemata,
        "ist_prozessverantwortlicher": ist_pv,
    })


# ---------------------------------------------------------------------------
# Schema-Editor (nur Prozessverantwortliche)
# ---------------------------------------------------------------------------

@login_required
def schema_erstellen(request):
    """Neues Formular-Schema erstellen (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        aktiv = request.POST.get("aktiv") == "on"
        schema_raw = request.POST.get("schema_json", "{}")

        try:
            schema_json = json.loads(schema_raw)
        except json.JSONDecodeError:
            schema_json = {"felder": []}

        if not name:
            messages.error(request, "Name ist Pflichtfeld.")
            return render(request, "prozesse/schema_editor.html", {
                "schema_json_str": schema_raw,
                "name": name,
                "beschreibung": beschreibung,
                "aktiv": aktiv,
            })

        schema = FormularSchema.objects.create(
            name=name,
            beschreibung=beschreibung,
            aktiv=aktiv,
            schema_json=schema_json,
            erstellt_von=request.user,
        )
        messages.success(request, f'Schema "{schema.name}" wurde erstellt.')
        return redirect("prozesse:schema_bearbeiten", pk=schema.pk)

    return render(request, "prozesse/schema_editor.html", {
        "schema_json_str": json.dumps({"felder": []}, ensure_ascii=False),
        "name": "",
        "beschreibung": "",
        "aktiv": True,
    })


@login_required
def schema_bearbeiten(request, pk):
    """Bestehendes Formular-Schema bearbeiten (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    schema = get_object_or_404(FormularSchema, pk=pk)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        aktiv = request.POST.get("aktiv") == "on"
        schema_raw = request.POST.get("schema_json", "{}")

        try:
            schema_json = json.loads(schema_raw)
        except json.JSONDecodeError:
            messages.error(request, "Ungueltige JSON-Struktur.")
            return render(request, "prozesse/schema_editor.html", {
                "schema": schema,
                "schema_json_str": schema_raw,
            })

        if not name:
            messages.error(request, "Name ist Pflichtfeld.")
            return render(request, "prozesse/schema_editor.html", {
                "schema": schema,
                "schema_json_str": schema_raw,
            })

        schema.name = name
        schema.beschreibung = beschreibung
        schema.aktiv = aktiv
        schema.schema_json = schema_json
        schema.save()
        messages.success(request, f'Schema "{schema.name}" gespeichert.')
        return redirect("prozesse:schema_bearbeiten", pk=schema.pk)

    return render(request, "prozesse/schema_editor.html", {
        "schema": schema,
        "schema_json_str": json.dumps(schema.schema_json, ensure_ascii=False),
    })


@login_required
@require_POST
def schema_loeschen(request, pk):
    """Schema loeschen – nur wenn keine Eintraege vorhanden (Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    schema = get_object_or_404(FormularSchema, pk=pk)

    if schema.eintraege.exists():
        messages.error(
            request,
            f'Schema "{schema.name}" hat {schema.eintraege.count()} Eintraege '
            f'und kann nicht geloescht werden. Deaktivieren statt loeschen.',
        )
        return redirect("prozesse:dashboard")

    name = schema.name
    schema.delete()
    messages.success(request, f'Schema "{name}" wurde geloescht.')
    return redirect("prozesse:dashboard")


# ---------------------------------------------------------------------------
# Formular ausfuellen (alle eingeloggten User)
# ---------------------------------------------------------------------------

def _hole_profil_vorwerte(user, schema):
    """Liest UserProfil und gibt dict {feld_id: wert} fuer vorausfuellen-Felder zurueck."""
    try:
        from hr.models import UserProfil
        profil = UserProfil.objects.filter(user=user).first()
        if not profil:
            return {}
        profil_map = {
            "vorname": profil.vorname,
            "nachname": profil.nachname,
            "abteilung": profil.abteilung,
            "telefon": profil.telefon,
        }
        ergebnis = {}
        for feld in schema.felder():
            vf = feld.get("vorausfuellen")
            if vf and vf in profil_map and profil_map[vf]:
                ergebnis[feld["id"]] = profil_map[vf]
        return ergebnis
    except Exception:
        return {}


def _injiziere_vorwerte(render_items, vorwerte):
    """Schreibt vorwert-Attribut in jedes Eingabefeld (standalone + textblock-inline) fuer das Template."""
    for item in render_items:
        if item.get("render_typ") == "standalone":
            feld_id = item["feld"].get("id", "")
            item["feld"]["vorwert"] = vorwerte.get(feld_id, "")
        elif item.get("render_typ") == "textblock":
            for seg in item.get("segmente", []):
                if seg.get("typ") == "feld" and seg.get("feld"):
                    feld_id = seg["feld"].get("id", "")
                    seg["feld"]["vorwert"] = vorwerte.get(feld_id, "")


@login_required
def formular_ausfuellen(request, pk):
    """Generischer Renderer: zeigt ein Schema als ausfuellbares Formular."""
    schema = get_object_or_404(FormularSchema, pk=pk, aktiv=True)
    render_items = _verarbeite_schema(schema)
    eingabefelder = _alle_eingabefelder(schema)

    if request.method == "POST":
        daten = {}
        fehler = []

        for feld in eingabefelder:
            feld_id = feld.get("id", "")
            typ = feld.get("typ", "text")
            pflicht = feld.get("pflicht", False)

            if typ == "bool":
                wert = feld_id in request.POST
            elif typ == "checkboxen":
                # Mehrere Werte moeglich (getlist)
                wert = ", ".join(request.POST.getlist(feld_id))
            else:
                wert = request.POST.get(feld_id, "").strip()

            if pflicht and not wert and wert != 0:
                fehler.append(f'"{feld.get("label", feld_id)}" ist ein Pflichtfeld.')

            if typ == "iban" and wert:
                if not _validiere_iban(wert):
                    fehler.append(f'"{feld.get("label", feld_id)}" ist keine gueltige IBAN.')
                else:
                    # Normalisiert speichern (Leerzeichen entfernen, Grossbuchstaben)
                    wert = wert.replace(" ", "").upper()

            if typ == "uhrzeit" and wert:
                normiert = _normalisiere_uhrzeit(wert)
                if normiert is None:
                    fehler.append(
                        f'"{feld.get("label", feld_id)}" ist keine gueltige Uhrzeit (z.B. 14:30 oder 1430).'
                    )
                else:
                    wert = normiert

            if typ == "zahl" and wert:
                try:
                    wert = float(str(wert).replace(",", "."))
                except ValueError:
                    fehler.append(f'"{feld.get("label", feld_id)}" muss eine Zahl sein.')

            daten[feld_id] = wert

        if fehler:
            _injiziere_vorwerte(render_items, request.POST)
            return render(request, "prozesse/formular_ausfuellen.html", {
                "schema": schema,
                "render_items": render_items,
                "fehler": fehler,
            })

        # Berechnungsfelder auswerten und in daten eintragen
        for feld in schema.felder():
            if feld.get("typ") == "berechnung":
                ergebnis = _berechne_formel(feld.get("formel", ""), daten)
                if ergebnis is not None:
                    dez = int(feld.get("dezimalstellen", 2))
                    try:
                        daten[feld["id"]] = round(float(ergebnis), dez) if dez > 0 else int(round(float(ergebnis)))
                    except (TypeError, ValueError):
                        daten[feld["id"]] = ergebnis  # Text-Ergebnis (z.B. aus WENN)

        eintrag = FormularEintrag.objects.create(
            schema=schema,
            daten_json=daten,
            eingereicht_von=request.user,
        )
        messages.success(request, "Formular erfolgreich eingereicht.")
        return redirect("prozesse:eintrag_detail", pk=eintrag.pk)

    # GET: Profil-Vorwerte einsetzen
    profil_vorwerte = _hole_profil_vorwerte(request.user, schema)
    _injiziere_vorwerte(render_items, profil_vorwerte)
    return render(request, "prozesse/formular_ausfuellen.html", {
        "schema": schema,
        "render_items": render_items,
        "fehler": [],
    })


@login_required
def eintrag_detail(request, pk):
    """Einzelnen Formular-Eintrag anzeigen."""
    eintrag = get_object_or_404(FormularEintrag, pk=pk)

    # Nur eigene Eintraege oder Prozessverantwortliche
    if eintrag.eingereicht_von != request.user and not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    # Felder mit gespeicherten Werten zusammenfuehren (Struktur-Typen ueberspringen)
    daten = eintrag.daten_json or {}
    felder_anzeige = []
    for feld in eintrag.schema.felder():
        typ = feld.get("typ", "text")
        if typ in _KEINE_EINGABEFELDER - {"berechnung"}:
            continue  # Textblock, Abschnitt, Trennlinie etc. nicht anzeigen
        feld_id = feld.get("id", "")
        wert = daten.get(feld_id, "")
        felder_anzeige.append({
            "label": feld.get("label", feld_id),
            "typ": typ,
            "wert": wert,
            "einheit": feld.get("einheit", ""),
            "dezimalstellen": feld.get("dezimalstellen", 2),
        })

    return render(request, "prozesse/eintrag_detail.html", {
        "eintrag": eintrag,
        "felder_anzeige": felder_anzeige,
        "ist_prozessverantwortlicher": _ist_prozessverantwortlicher(request.user),
    })


@login_required
def eintrag_liste(request, schema_pk):
    """Alle Eintraege zu einem Schema (nur Prozessverantwortliche)."""
    if not _ist_prozessverantwortlicher(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("prozesse:dashboard")

    schema = get_object_or_404(FormularSchema, pk=schema_pk)
    eintraege = schema.eintraege.select_related("eingereicht_von").order_by("-eingereicht_am")

    return render(request, "prozesse/eintrag_liste.html", {
        "schema": schema,
        "eintraege": eintraege,
    })


# ---------------------------------------------------------------------------
# HTMX: Schema-Vorschau (JSON → HTML-Vorschau)
# ---------------------------------------------------------------------------

@login_required
def schema_vorschau(request):
    """HTMX-View: rendert JSON-Schema als Formular-Vorschau (Partial)."""
    # HTMX-View
    schema_raw = request.POST.get("schema_json", "{}")
    try:
        schema_json = json.loads(schema_raw)
    except json.JSONDecodeError:
        schema_json = {"felder": []}

    felder = schema_json.get("felder", [])
    return render(request, "prozesse/partials/_vorschau.html", {
        "felder": felder,
    })
