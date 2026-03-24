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
import logging
import operator
import re

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from workflow.models import WorkflowTemplate
from workflow.services import WorkflowEngine

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
    if isinstance(node, ast.BoolOp):
        werte_liste = [_ast_eval(v, werte) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(werte_liste)
        if isinstance(node.op, ast.Or):
            return any(werte_liste)
        raise ValueError("Nicht erlaubter Bool-Operator")
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


def _berechne_formel(formel, werte):
    """Wertet eine Berechnungsformel aus (gleiche Engine wie _pruefe_bedingung).

    Gibt einen int oder float zurueck, oder None bei Fehler.
    Ganze Zahlen werden als int zurueckgegeben (kein Dezimalpunkt).
    Fehlende Variablen werden als 0 behandelt.
    """
    if not formel or not formel.strip():
        return None

    def _var_zu_zahl(match):
        """Ersetzt {{feld_id}} durch den numerischen Wert aus werte (0 wenn fehlt)."""
        v = werte.get(match.group(1))
        if v in ("", None):
            return "0"
        try:
            return str(float(str(v).replace(",", ".")))
        except (ValueError, TypeError):
            return "0"

    ausdruck = re.sub(r"\{\{(\w+)\}\}", _var_zu_zahl, formel.replace(";", ","))
    try:
        tree = ast.parse(ausdruck, mode="eval")
        # Keine Variablen mehr im Ausdruck – leeres Werte-Dict genuegt
        ergebnis = _ast_eval(tree.body, {})
        if ergebnis is None:
            return None
        ergebnis = float(ergebnis)
        # Ganze Zahlen ohne Nachkommastelle speichern
        if ergebnis == int(ergebnis):
            return int(ergebnis)
        return round(ergebnis, 2)
    except Exception:
        return None


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

_KEINE_EINGABE = {"textblock", "abschnitt", "trennlinie", "leerblock", "link", "berechnung", "zusammenfassung"}

# Typen die auch in der Zusammenfassung nicht angezeigt werden (rein strukturell)
_KEINE_ANZEIGE = {"textblock", "abschnitt", "trennlinie", "leerblock", "link", "zusammenfassung"}


def _eingabefelder(schritt):
    """Gibt alle Eingabefelder eines Schritts zurueck (ohne Struktur-Typen)."""
    return [f for f in schritt.felder() if f.get("typ") not in _KEINE_EINGABE]


def _anzeigefelder(schritt):
    """Gibt alle Felder fuer die Zusammenfassung zurueck (incl. Berechnungsfelder)."""
    return [f for f in schritt.felder() if f.get("typ") not in _KEINE_ANZEIGE]


def _baue_zusammenfassung(sitzung):
    """Baut Label+Wert-Liste aus allen bisher gesammelten Daten."""
    zusammenfassung = []
    for schritt_node_id in sitzung.besuchte_schritte:
        try:
            schritt = sitzung.pfad.schritte.get(node_id=schritt_node_id)
        except AntragsPfadSchritt.DoesNotExist:
            continue
        for feld in _anzeigefelder(schritt):
            feld_id = feld.get("id", "")
            wert = sitzung.gesammelte_daten.get(feld_id, "")
            if wert != "" and wert is not None:
                # Berechnungsfeld: Einheit anhaengen wenn vorhanden
                if feld.get("typ") == "berechnung" and feld.get("einheit"):
                    wert = f"{wert} {feld['einheit']}"
                zusammenfassung.append({
                    "label": feld.get("label", feld_id),
                    "wert": wert,
                    "typ": feld.get("typ", "text"),
                })
    return zusammenfassung


def _validiere_schritt(schritt, post_data, vorige_daten=None):
    """Prueft Pflichtfelder und gibt (daten_dict, fehler_liste) zurueck.

    vorige_daten: bereits gesammelte Daten der Sitzung (fuer Berechnungsfelder
    die auf vorherige Schritte referenzieren).
    """
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

    # Berechnungsfelder serverseitig auswerten – Client-Wert wird ignoriert
    alle_werte = dict(vorige_daten or {})
    alle_werte.update(daten)
    for feld in schritt.felder():
        if feld.get("typ") != "berechnung":
            continue
        feld_id = feld.get("id", "")
        formel = feld.get("formel", "")
        if not feld_id or not formel:
            continue
        ergebnis = _berechne_formel(formel, alle_werte)
        if ergebnis is not None:
            daten[feld_id] = ergebnis
            alle_werte[feld_id] = ergebnis  # Folgeketten unterstuetzen

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
# Workflow-Start nach Pfad-Abschluss
# ---------------------------------------------------------------------------

def _starte_workflow_wenn_konfiguriert(sitzung, user):
    """Startet einen Workflow wenn der Pfad ein Template konfiguriert hat.

    Die AntragsPfadSitzung wird als content_object der WorkflowInstance genutzt,
    damit der Workflow direkt mit den gesammelten Formulardaten verknuepft ist.
    """
    if not sitzung.pfad.workflow_template_id:
        return
    try:
        engine = WorkflowEngine()
        instanz = engine.start_workflow(
            sitzung.pfad.workflow_template, sitzung, user
        )
        sitzung.workflow_instance = instanz
        sitzung.save(update_fields=["workflow_instance"])
    except Exception:
        logger.exception(
            "Workflow-Start fuer Sitzung %s fehlgeschlagen", sitzung.pk
        )


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
    workflow_templates = WorkflowTemplate.objects.filter(ist_aktiv=True).order_by("name")
    return render(request, "antraege/pfad_editor.html", {
        "pfad": pfad,
        "workflow_templates": workflow_templates,
    })


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
        "workflow_template_id": pfad.workflow_template_id or "",
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

    # Workflow-Template aufloesen (None wenn leer oder nicht vorhanden)
    wt_id = daten.get("workflow_template_id") or None
    wt_obj = None
    if wt_id:
        try:
            wt_obj = WorkflowTemplate.objects.get(pk=int(wt_id))
        except (WorkflowTemplate.DoesNotExist, ValueError, TypeError):
            wt_obj = None

    if pk:
        pfad = get_object_or_404(AntragsPfad, pk=pk)
        pfad.name = name
        pfad.beschreibung = daten.get("beschreibung", "")
        pfad.aktiv = daten.get("aktiv", True)
        pfad.workflow_template = wt_obj
        pfad.save()
        # Alte Schritte + Transitionen loeschen und neu anlegen
        pfad.transitionen.all().delete()
        pfad.schritte.all().delete()
    else:
        pfad = AntragsPfad.objects.create(
            name=name,
            beschreibung=daten.get("beschreibung", ""),
            aktiv=daten.get("aktiv", True),
            workflow_template=wt_obj,
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
        schritt_daten, fehler = _validiere_schritt(schritt, request.POST, sitzung.gesammelte_daten)

        if fehler:
            return render(request, "antraege/pfad_schritt.html", {
                "sitzung": sitzung,
                "schritt": schritt,
                "fehler": fehler,
                "vorwerte": request.POST,
                "fortschritt": round(besucht / gesamt * 100) if gesamt else 0,
                "gesammelte_daten_json": json.dumps(sitzung.gesammelte_daten, ensure_ascii=False),
            })

        # Daten zur Sitzung hinzufuegen
        sitzung.gesammelte_daten.update(schritt_daten)

        # Endknoten erreicht?
        if schritt.ist_ende:
            sitzung.abschliessen()
            _starte_workflow_wenn_konfiguriert(sitzung, request.user)
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
                "gesammelte_daten_json": json.dumps(sitzung.gesammelte_daten, ensure_ascii=False),
            })

        naechster = transition.zu_schritt
        besucht_liste = sitzung.besuchte_schritte + [naechster.node_id]
        sitzung.aktueller_schritt = naechster
        sitzung.besuchte_schritte = besucht_liste
        sitzung.save(update_fields=["aktueller_schritt", "besuchte_schritte", "gesammelte_daten"])

        # Endknoten direkt ueberspringen nur wenn er keinerlei Felder hat
        if naechster.ist_ende and not naechster.felder():
            sitzung.abschliessen()
            _starte_workflow_wenn_konfiguriert(sitzung, request.user)
            return redirect("antraege:pfad_abgeschlossen", sitzung_pk=sitzung.pk)

        return redirect("antraege:pfad_schritt", sitzung_pk=sitzung.pk)

    zusammenfassung = _baue_zusammenfassung(sitzung) if schritt.ist_ende else []
    return render(request, "antraege/pfad_schritt.html", {
        "sitzung": sitzung,
        "schritt": schritt,
        "fehler": [],
        "vorwerte": {},
        "fortschritt": round(besucht / gesamt * 100) if gesamt else 0,
        "gesammelte_daten_json": json.dumps(sitzung.gesammelte_daten, ensure_ascii=False),
        "zusammenfassung": zusammenfassung,
    })


@login_required
def pfad_abgeschlossen(request, sitzung_pk):
    """Abschluss-Seite nach erfolgreichem Durchlauf."""
    sitzung = get_object_or_404(
        AntragsPfadSitzung.objects.select_related("workflow_instance__template"),
        pk=sitzung_pk,
        user=request.user,
    )
    return render(request, "antraege/pfad_abgeschlossen.html", {
        "sitzung": sitzung,
        "zusammenfassung": _baue_zusammenfassung(sitzung),
        "workflow_instance": sitzung.workflow_instance,
    })


@login_required
def meine_antraege(request):
    """Alle eigenen Sitzungen des Nutzers."""
    sitzungen = AntragsPfadSitzung.objects.filter(user=request.user).select_related("pfad")
    return render(request, "antraege/meine_antraege.html", {"sitzungen": sitzungen})
