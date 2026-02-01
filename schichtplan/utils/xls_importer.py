from datetime import datetime, timedelta
import openpyxl
from arbeitszeit.models import Mitarbeiter
from schichtplan.models import Schicht, Schichttyp

class SchichtplanImporter:
    def import_excel_mit_zuordnung(self, file_path, schichtplan):
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active

        # ---------------------------------------------------------------
        # OPTIMIERUNG: Caching der Schichttypen
        # Anstatt in jeder Zelle die DB zu fragen (macht den Import langsam),
        # laden wir einmal alle Typen in den Speicher.
        # ---------------------------------------------------------------
        # Erstellt ein Dictionary: {'T': <Objekt T>, 'N': <Objekt N>, 'Z8': <Objekt Z8> ...}
        db_schichttypen = {t.kuerzel: t for t in Schichttyp.objects.all()}

        # Definition der erlaubten Codes aus deiner Excel
        # Format: 'Excel-Wert': 'DB-Kürzel' (meistens identisch)
        # Hier kannst du jederzeit neue Codes hinzufügen!
        erlaubte_codes = [
            'T', 'N',           # Standard
            'Z8', 'Z8,2', 'BS8',      # Zusatzdienste
            'U', 'U8', 'U8,2'   # Urlaub
        ]

        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_tag = row[0]  # Rohdaten aus Excel (kann Text oder Zahl sein)
            wochentag = row[1] 

            # --- FEHLERBEHEBUNG START ---
            # 1. Leere Zeilen überspringen
            if raw_tag is None:
                continue

            # 2. Versuchen, den Tag in eine ganze Zahl (Integer) umzuwandeln
            try:
                tag = int(raw_tag)
            except ValueError:
                # Falls in der Spalte Text steht (z.B. eine Fußzeile mit "Gesamt"), überspringen
                print(f"DEBUG: Zeile übersprungen. '{raw_tag}' ist keine gültige Tag-Nummer.")
                continue
            # --- FEHLERBEHEBUNG ENDE ---

            # Überprüfe, ob schichtplan.start_datum vorhanden ist
            if schichtplan.start_datum is None:
                print(f"ERROR: Schichtplan-Datum fehlt. Überspringe Zeile.")
                continue

            # Jetzt können wir sicher rechnen: tag ist jetzt garantiert eine Zahl
            datum = datetime.combine(schichtplan.start_datum, datetime.min.time()) + timedelta(days=tag - 1)

            datum = datetime.combine(schichtplan.start_datum, datetime.min.time()) + timedelta(days=tag - 1)
            print(f"DEBUG: Verarbeite Schicht für Datum: {datum}")

            # Schleife durch die Mitarbeiter
            for idx, raw_value in enumerate(row[2:], start=1):
                # Leere Zellen überspringen
                if raw_value is None or raw_value == '':
                    continue

                # 1. Wert bereinigen
                # Excel speichert "8,2" manchmal als Float 8.2 oder als String "8,2"
                # Wir wandeln alles sicher in einen String um und entfernen Leerzeichen
                value_str = str(raw_value).strip().replace('.', ',') 

                # 2. Prüfen, ob der Code relevant ist
                if value_str not in erlaubte_codes:
                    # Falls da was steht, was wir nicht kennen (z.B. Notizen), ignorieren
                    continue

                try:
                    mitarbeiter = Mitarbeiter.objects.get(schichtplan_kennung=f'MA{idx}')
                except Mitarbeiter.DoesNotExist:
                    print(f"ERROR: Mitarbeiter MA{idx} nicht gefunden.")
                    continue

                # 3. Schichttyp aus dem Cache holen
                if value_str in db_schichttypen:
                    schichttyp = db_schichttypen[value_str]
                else:
                    print(f"ERROR: Schichttyp '{value_str}' steht in Excel, fehlt aber in der Datenbank (Tabelle Schichttyp)!")
                    continue

                # 4. Schicht erstellen
                try:
                    # Prüfen ob Schicht schon existiert, um Duplikate zu vermeiden (update_or_create)
                    Schicht.objects.update_or_create(
                        schichtplan=schichtplan,
                        mitarbeiter=mitarbeiter,
                        datum=datum,
                        defaults={'schichttyp': schichttyp}
                    )
                    # print(f"  -> {mitarbeiter}: {schichttyp.kuerzel}") # Optionales Logging
                except Exception as e:
                    print(f"ERROR: Fehler beim Speichern: {str(e)}")