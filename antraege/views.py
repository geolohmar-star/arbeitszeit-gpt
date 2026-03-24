"""Antrags-Pfad Views: visueller Editor + Player (Schritt-fuer-Schritt).

Editor-Flow:
  pfad_liste        → Uebersicht aller Pfade
  pfad_editor       → visueller Graph-Editor (vis.js)
  pfad_editor_laden → GET JSON: Pfad-Daten fuer Editor
  pfad_editor_speichern → POST JSON: Pfad speichern

Player-Flow:
  pfad_starten      → neue Sitzung anlegen, zum Start-Schritt weiterleiten
  pfad_schritt      → aktuellen Schritt anzeigen + POST verarbeiten
  pfad_abgeschlossen→ Abschluss-Seite
"""
import ast
import json
import operator
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import (
    AntragsPfad,
    AntragsPfadSchritt,
    AntragsPfadSitzung,
    AntragsPfadTransition,
)

# ---------------------------------------------------------------------------
# Berechtigungspruefung
# ---------------------------------------------------------------------------

def _ist_editor(user):
    """Darf Pfade anlegen/bearbeiten (Staff oder Prozessverantwortliche)."""
    if user.is_staff:
        return True
    try:
        from berechtigungen.models import Rolle
        return user.gruppen_berechtigungen.filter(
            gruppe__name__icontains="prozessverantwortlich"
        ).exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Formel-Evaluator (vereinfacht; Kern aus prozesse/views.py)
# ---------------------------------------------------------------------------

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}


def _ast_eval(node, werte):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return werte.get(node.id, "")
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError("Nicht erlaubter Operator")
        l, r = _ast_eval(node.left, werte), _ast_eval(node.right, werte)
        if isinstance(node.op, ast.Div) and r == 0:
            return None
        try:
            return op(float(l), float(r))
        except (TypeError, ValueError):
            return op(l, r)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = _OPS.get(type(node.ops[0]))
        if op is None:
            raise ValueError("Nicht erlaubter Vergleichsoperator")
        l = _ast_eval(node.left, werte)
        r = _ast_eval(node.comparators[0], werte)
        return op(l, r)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -float(_ast_eval(node.operand, werte))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id.upper()
        args = [_ast_eval(a, werte) for a in node.args]
        if name == "WENN":
            return args[1] if args[0] else args[2]
        if name == "RUNDEN":
            return round(float(args[0]), int(args[1]))
        if name == "ABS":
            return abs(float(args[0]))
    raise ValueError(f"Nicht erlaubter Ausdruck: {ast.dump(node)}")


def _pruefe_bedingung(bedingung, gesammelte_daten):
    """Wertet eine Bedingungsformel gegen die gesammelten Daten aus.

    Leer = immer wahr.
    Gibt True/False zurueck (bei Fehler: False).
    """
    if not bedingung or not bedingung.strip():
        return True
    ausdruck = bedingung.replace(";", ",")
    ausdruck = re.sub(r"\{\{(\w+)\}\}", r"_F_\1", ausdruck)
    werte = {}
    for k, v in gesammelte_daten.items():
        try:
            werte["_F_" + k] = float(str(v).replace(",", ".")) if v not in ("", None) else ""
        except (ValueError, TypeError):
            werte["_F_" + k] = str(v) if v is not None else ""
    try:
        tree = ast.parse(ausdruck, mode="eval")
        ergebnis = _ast_eval(tree.body, werte)
        return bool(ergebnis)
    except Exception:
        return False


def _naechster_schritt(schritt, gesammelte_daten):
    """Ermittelt den naechsten Schritt anhand der Transitionen.

    Gibt das AntragsPfadTransition-Objekt zurueck dessen Bedingung erfuellt ist,
    oder None wenn keine passt.
    """
    for transition in schritt.ausgaende.select_related("zu_schritt").order_by("reihenfolge", "pk"):
        if _pruefe_bedingung(transition.bedingung, gesammelte_daten):
            return transition
    return None


# ---------------------------------------------------------------------------
# Hilfsfunktionen Player
# ---------------------------------------------------------------------------

_KEINE_EINGABE = {"textblock", "abschnitt", "trennlinie", "leerblock", "link", "berechnung"}


def _eingabefelder(schritt):
    """Gibt alle Eingabefelder eines Schritts zurueck (ohne Struktur-Typen)."""
    return [f for f in schritt.felder() if f.get("typ") not in _KEINE_EINGABE]


def _validiere_schritt(schritt, post_data):
    """Prueft Pflichtfelder und gibt (daten_dict, fehler_liste) zurueck."""
    daten = {}
    fehler = []
    for feld in _eingabefelder(schritt):
        feld_id = feld.get("id", "")
        typ = feld.get("typ", "text")
        pflicht = feld.get("pflicht", False)
        if typ == "bool":
            wert = feld_id in post_data
        elif typ == "checkboxen":
            wert = ", ".join(post_data.getlist(feld_id))
        else:
            wert = post_data.get(feld_id, "").strip()
        if pflicht and not wert and wert != 0:
            fehler.append(f'"{feld.get("label", feld_id)}" ist ein Pflichtfeld.')
        # Uhrzeit normalisieren
        if typ == "uhrzeit" and wert:
            normiert = _normalisiere_uhrzeit(wert)
            if normiert is None:
                fehler.append(f'"{feld.get("label", feld_id)}" ist keine gueltige Uhrzeit.')
            else:
                wert = normiert
        # IBAN: nur Buchstaben und Ziffern, 15-34 Zeichen
        if typ == "iban" and wert:
            iban_bereinigt = wert.replace(" ", "").upper()
            if not re.match(r"^[A-Z]{2}[0-9A-Z]{13,32}$", iban_bereinigt):
                fehler.append(f'"{feld.get("label", feld_id)}" ist keine gueltige IBAN.')
            else:
                wert = iban_bereinigt
        daten[feld_id] = wert
    return daten, fehler


def _normalisiere_uhrzeit(wert):
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
# Pfad-Liste
# ---------------------------------------------------------------------------

@login_required
def pfad_liste(request):
    """Uebersicht aller Antrags-Pfade."""
    if _ist_editor(request.user):
        pfade = AntragsPfad.objects.all()
    else:
        pfade = AntragsPfad.objects.filter(aktiv=True)
    return render(request, "antraege/pfad_liste.html", {
        "pfade": pfade,
        "ist_editor": _ist_editor(request.user),
    })


# ---------------------------------------------------------------------------
# Visueller Editor
# ---------------------------------------------------------------------------

@login_required
def pfad_editor(request, pk=None):
    """Visueller Pfad-Editor (vis.js). Neuer oder bestehender Pfad."""
    if not _ist_editor(request.user):
        messages.error(request, "Kein Zugriff.")
        return redirect("antraege:pfad_liste")
    pfad = get_object_or_404(AntragsPfad, pk=pk) if pk else None
    return render(request, "antraege/pfad_editor.html", {"pfad": pfad})


@login_required
def pfad_editor_laden(request, pk):
    """GET: Gibt Pfad-Daten als JSON fuer den Editor zurueck."""
    pfad = get_object_or_404(AntragsPfad, pk=pk)
    schritte = []
    for s in pfad.schritte.all():
        schritte.append({
            "id": s.pk,
            "node_id": s.node_id,
            "titel": s.titel,
            "felder_json": s.felder_json,
            "ist_start": s.ist_start,
            "ist_ende": s.ist_ende,
            "pos_x": s.pos_x,
            "pos_y": s.pos_y,
        })
    transitionen = []
    for t in pfad.transitionen.all():
        transitionen.append({
            "id": t.pk,
            "von": t.von_schritt.node_id,
            "zu": t.zu_schritt.node_id,
            "bedingung": t.bedingung,
            "label": t.label,
            "reihenfolge": t.reihenfolge,
        })
    return JsonResponse({
        "pk": pfad.pk,
        "name": pfad.name,
        "beschreibung": pfad.beschreibung,
        "aktiv": pfad.aktiv,
        "schritte": schritte,
        "transitionen": transitionen,
    })


@require_POST
@login_required
def pfad_editor_speichern(request):
    """POST JSON: Speichert einen Pfad (neu oder bestehend)."""
    if not _ist_editor(request.user):
        return JsonResponse({"ok": False, "fehler": "Kein Zugriff"}, status=403)
    try:
        daten = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "fehler": "Ungueltige JSON-Daten"}, status=400)

    pk = daten.get("pk")
    name = daten.get("name", "").strip()
    if not name:
        return JsonResponse({"ok": False, "fehler": "Name ist Pflichtfeld"}, status=400)

    if pk:
        pfad = get_object_or_404(AntragsPfad, pk=pk)
        pfad.name = name
        pfad.beschreibung = daten.get("beschreibung", "")
        pfad.aktiv = daten.get("aktiv", True)
        pfad.save()
        # Alte Schritte + Transitionen loeschen und neu anlegen
        pfad.transitionen.all().delete()
        pfad.schritte.all().delete()
    else:
        pfad = AntragsPfad.objects.create(
            name=name,
            beschreibung=daten.get("beschreibung", ""),
            aktiv=daten.get("aktiv", True),
            erstellt_von=request.user,
        )

    # Schritte anlegen
    schritt_map = {}  # node_id → AntragsPfadSchritt
    for s in daten.get("schritte", []):
        node_id = s.get("node_id", "")
        if not node_id:
            continue
        obj = AntragsPfadSchritt.objects.create(
            pfad=pfad,
            node_id=node_id,
            titel=s.get("titel", "Schritt"),
            felder_json=s.get("felder_json", []),
            ist_start=s.get("ist_start", False),
            ist_ende=s.get("ist_ende", False),
            pos_x=s.get("pos_x", 200),
            pos_y=s.get("pos_y", 200),
        )
        schritt_map[node_id] = obj

    # Transitionen anlegen
    for t in daten.get("transitionen", []):
        von = schritt_map.get(t.get("von"))
        zu = schritt_map.get(t.get("zu"))
        if not von or not zu:
            continue
        AntragsPfadTransition.objects.create(
            pfad=pfad,
            von_schritt=von,
            zu_schritt=zu,
            bedingung=t.get("bedingung", ""),
            label=t.get("label", ""),
            reihenfolge=t.get("reihenfolge", 0),
        )

    return JsonResponse({"ok": True, "pk": pfad.pk, "name": pfad.name})


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

@login_required
def pfad_starten(request, pk):
    """Startet eine neue Sitzung und leitet zum ersten Schritt weiter."""
    pfad = get_object_or_404(AntragsPfad, pk=pk, aktiv=True)
    start = pfad.start_schritt()
    if not start:
        messages.error(request, "Dieser Pfad hat keinen Start-Schritt.")
        return redirect("antraege:pfad_liste")
    sitzung = AntragsPfadSitzung.objects.create(
        pfad=pfad,
        user=request.user,
        aktueller_schritt=start,
        besuchte_schritte=[start.node_id],
    )
    return redirect("antraege:pfad_schritt", sitzung_pk=sitzung.pk)


@login_required
def pfad_schritt(request, sitzung_pk):
    """Zeigt den aktuellen Schritt und verarbeitet die Formulardaten."""
    sitzung = get_object_or_404(
        AntragsPfadSitzung, pk=sitzung_pk, user=request.user, status=AntragsPfadSitzung.STATUS_LAUFEND
    )
    schritt = sitzung.aktueller_schritt
    if not schritt:
        messages.error(request, "Sitzung hat keinen aktuellen Schritt.")
        return redirect("antraege:pfad_liste")

    # Fortschritts-Info: wie viele Schritte besucht vs. Gesamtschritte (Schaetzung)
    gesamt = sitzung.pfad.schritte.count()
    besucht = len(sitzung.besuchte_schritte)

    if request.method == "POST":
        schritt_daten, fehler = _validiere_schritt(schritt, request.POST)

        if fehler:
            return render(request, "antraege/pfad_schritt.html", {
                "sitzung": sitzung,
                "schritt": schritt,
                "fehler": fehler,
                "vorwerte": request.POST,
                "fortschritt": round(besucht / gesamt * 100) if gesamt else 0,
            })

        # Daten zur Sitzung hinzufuegen
        sitzung.gesammelte_daten.update(schritt_daten)

        # Endknoten erreicht?
        if schritt.ist_ende:
            sitzung.abschliessen()
            return redirect("antraege:pfad_abgeschlossen", sitzung_pk=sitzung.pk)

        # Naechsten Schritt ermitteln
        transition = _naechster_schritt(schritt, sitzung.gesammelte_daten)
        if transition is None:
            fehler = ["Es gibt keinen passenden naechsten Schritt. Bitte pruefen Sie Ihre Eingaben."]
            return render(request, "antraege/pfad_schritt.html", {
                "sitzung": sitzung,
                "schritt": schritt,
                "fehler": fehler,
                "vorwerte": request.POST,
                "fortschritt": round(besucht / gesamt * 100) if gesamt else 0,
            })

        naechster = transition.zu_schritt
        besucht_liste = sitzung.besuchte_schritte + [naechster.node_id]
        sitzung.aktueller_schritt = naechster
        sitzung.besuchte_schritte = besucht_liste
        sitzung.save(update_fields=["aktueller_schritt", "besuchte_schritte", "gesammelte_daten"])

        # Endknoten direkt erkennen (ohne Felder)
        if naechster.ist_ende and not _eingabefelder(naechster):
            sitzung.abschliessen()
            return redirect("antraege:pfad_abgeschlossen", sitzung_pk=sitzung.pk)

        return redirect("antraege:pfad_schritt", sitzung_pk=sitzung.pk)

    import json as _json
    return render(request, "antraege/pfad_schritt.html", {
        "sitzung": sitzung,
        "schritt": schritt,
        "fehler": [],
        "vorwerte": {},
        "fortschritt": round(besucht / gesamt * 100) if gesamt else 0,
        "gesammelte_daten_json": _json.dumps(sitzung.gesammelte_daten, ensure_ascii=False),
    })


@login_required
def pfad_abgeschlossen(request, sitzung_pk):
    """Abschluss-Seite nach erfolgreichem Durchlauf."""
    sitzung = get_object_or_404(AntragsPfadSitzung, pk=sitzung_pk, user=request.user)
    # Felder mit Labels anreichern fuer die Zusammenfassung
    zusammenfassung = []
    for schritt_node_id in sitzung.besuchte_schritte:
        try:
            schritt = sitzung.pfad.schritte.get(node_id=schritt_node_id)
        except AntragsPfadSchritt.DoesNotExist:
            continue
        for feld in _eingabefelder(schritt):
            feld_id = feld.get("id", "")
            wert = sitzung.gesammelte_daten.get(feld_id, "")
            if wert != "":
                zusammenfassung.append({
                    "label": feld.get("label", feld_id),
                    "wert": wert,
                    "typ": feld.get("typ", "text"),
                })
    return render(request, "antraege/pfad_abgeschlossen.html", {
        "sitzung": sitzung,
        "zusammenfassung": zusammenfassung,
    })


@login_required
def meine_antraege(request):
    """Alle eigenen Sitzungen des Nutzers."""
    sitzungen = AntragsPfadSitzung.objects.filter(user=request.user).select_related("pfad")
    return render(request, "antraege/meine_antraege.html", {"sitzungen": sitzungen})
