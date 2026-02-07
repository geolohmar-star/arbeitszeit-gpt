# Analyse: schichtplan/views.py (Funktionsbeschreibung)

> Grundlage: Der von dir gepostete Ausschnitt aus `schichtplan/views.py`.

---

## Modul-Header & Imports

- **Kommentar + Docstring**: Beschreibt, dass die Views für MA1–MA15 angepasst sind.
- **Django-Imports**: Standard-View-Tools, Auth, Messages, Query-Funktionen, Transaktionen.
- **Weitere Imports**: `defaultdict`, Datumsfunktionen, `tempfile`.
- **Models**: `Mitarbeiter`, `MonatlicheArbeitszeitSoll`, `Schichtplan`, `Schicht`, `Schichttyp`, `SchichtwunschPeriode`, `Schichtwunsch`.
- **Forms**: `ExcelImportForm`, `SchichtplanForm`, `SchichtForm`.
- **Service**: `SchichtplanGenerator` (KI-Planung).
- **Utils**: dynamischer Import eines Excel-Importers.

---

## Helper-Funktionen

### `ist_schichtplaner(user)`
Prüft, ob ein User Schichtplaner-Rechte hat:
- `anonymous` → False
- `is_superuser` oder `is_staff` → True
- sonst Gruppencheck `Schichtplaner`
Gibt Debug-Ausgaben ins Terminal.

### `get_planbare_mitarbeiter()`
Liefert Mitarbeiter, die in der Planung verwendet werden:
- `aktiv=True`
- `schichtplan_kennung` in `MA1…MA15`
- `verfuegbarkeit != 'dauerkrank'`
Mit `select_related('user')` für effizientere Queries.

---

## Views: Wunsch-Periode

### `WunschPeriodeCreateView`
CreateView für `SchichtwunschPeriode`:
- Felder: `name`, `fuer_monat`, `eingabe_start`, `eingabe_ende`, `status`
- `get_form`: setzt Widgets (DateInput/DateTimeInput + CSS).
- `form_valid`: setzt `erstellt_von` = aktueller User.

---

## Views: Schichtplan erzeugen

### `SchichtplanCreateView`
Erstellt einen neuen Schichtplan.
- `dispatch`: Berechtigungscheck via `ist_schichtplaner`.
- `form_valid`: speichert Plan, optional KI‑Generierung.
- `_generate_with_ai`:
  - prüft planbare MA
  - prüft Schichttypen `T/N`
  - löscht alte Schichten für Plan
  - ruft `SchichtplanGenerator` auf
  - schreibt Erfolgsmeldung/Fehler.

---

## Excel-Import

### `excel_import_view`
Importiert Excel in bestehenden Schichtplan:
- Berechtigungscheck
- Upload in temp-Datei
- Import über `SchichtplanImporter`.

### `excel_analyse_view`
Stub-Ansicht für Analyse (noch nicht implementiert).

---

## Dashboards & Übersichten

### `planer_dashboard`
Dashboard für Schichtplaner:
- Zugriffscheck
- Zählt aktive Pläne und Entwürfe
- Zeigt nur planbare MA in Statistiken.

### `mitarbeiter_uebersicht`
Übersicht aller planbaren MA:
- Zugriff prüfen
- Zählt zugeordnet/nicht zugeordnet/dauerkrank
- Filtert nach Standort.

---

## Schichtplan-Detail

### `schichtplan_detail`
Detailansicht für einen Schichtplan:
- Zugriff prüfen
- Lädt Schichten mit Typ/Mitarbeiter
- Baut `kalender_daten` (Tage, Wochentag, Wochenenden)
- Berechnet Statistik pro MA:
  - T/N/Z-Schichten
  - Stunden Ist/Soll
  - Wochenenden gearbeitet
- Sortiert Statistik nach Kennung (MA1, MA2, …).

---

## Schichten manuell

### `schicht_zuweisen`
Manuelles Zuweisen von Schichten:
- Zugriff prüfen
- POST: Formular speichern, Rückgabe per JSON oder Redirect.

### `schicht_loeschen`
Löscht eine Schicht nach Bestätigung (POST).

---

## Wunsch-Logik (Mitarbeiter & Planer)

### `wunsch_perioden_liste`
Listet Wunschperioden für Mitarbeiter:
- Nur User mit Mitarbeiterprofil
- Nur MA1–MA15 oder Planer.

### `wunsch_eingeben`
Formular zum Eintragen/Bearbeiten von Wünschen:
- Planer dürfen für alle MA eintragen
- MA dürfen nur für sich
- Datums- & Monatsprüfung
- `Schichtwunsch` wird erstellt/aktualisiert.

### `wunsch_ansehen`
Transparente Übersicht aller Wünsche:
- Berechtigung MA1–MA15 oder Planer
- Kalenderstruktur
- Konflikt-Tage markieren (zu viele frei/Urlaub).

---

## Genehmigungen & Löschungen

### `wuensche_genehmigen` (Liste)
Zeigt genehmigungspflichtige Wünsche:
- Planer-only
- Genehmigen/Ablehnen via POST
- Statistik: offen/genehmigt/gesamt.

### `wunsch_genehmigen` (Einzelwunsch)
Genehmigt oder lehnt einen Wunsch ab:
- Planer-only
- Update von `genehmigt`, `genehmigt_von`, `genehmigt_am`.

### `wunsch_loeschen`
Löscht Wunsch:
- Nur Planer oder Besitzer
- POST löscht, GET zeigt Bestätigung.

---

## Wunschperioden-Verwaltung

### `wunschperioden_liste`
Planer-only Liste aller Wunschperioden.

