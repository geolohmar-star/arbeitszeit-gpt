from datetime import datetime, timedelta
import openpyxl
from arbeitszeit.models import Mitarbeiter
from schichtplan.models import Schicht, Schichttyp  # Schichttyp und Schicht müssen hier importiert werden

class SchichtplanImporter:
    def import_excel_mit_zuordnung(self, file_path, schichtplan):
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active

        for row in sheet.iter_rows(min_row=2, values_only=True):
            tag = row[0]  # Tag-Nummer aus der ersten Spalte
            wochentag = row[1]  # Wochentag (z.B. Mo, Di, etc.)

            # Überprüfe, ob tag und schichtplan.start_datum gültige Werte haben
            if tag is None or schichtplan.start_datum is None:
                print(f"ERROR: Ungültige Daten für Tag {tag} oder Schichtplan-Datum {schichtplan.start_datum}. Überspringe diese Zeile.")
                continue

            # Kombiniere das Jahr und den Monat des Schichtplans mit dem Tag
            datum = datetime.combine(schichtplan.start_datum, datetime.min.time()) + timedelta(days=tag - 1)
            print(f"DEBUG: Verarbeite Schicht für Datum: {datum}")  # Debugging-Ausgabe

            # Schleife durch die Mitarbeiter (ab der 3. Spalte)
            for idx, value in enumerate(row[2:], start=1):  # MA1 bis MA15
                try:
                    mitarbeiter = Mitarbeiter.objects.get(schichtplan_kennung=f'MA{idx}')
                except Mitarbeiter.DoesNotExist:
                    print(f"ERROR: Mitarbeiter mit schichtplan_kennung MA{idx} nicht gefunden.")
                    continue

                if value == 'T':  # Tag-Schicht
                    try:
                        schichttyp = Schichttyp.objects.get(kuerzel='T')  # Tag-Schicht
                    except Schichttyp.DoesNotExist:
                        print(f"ERROR: Schichttyp für Tag-Schicht ('T') nicht gefunden.")
                        continue

                elif value == 'N':  # Nacht-Schicht
                    try:
                        schichttyp = Schichttyp.objects.get(kuerzel='N')  # Nachtschicht
                    except Schichttyp.DoesNotExist:
                        print(f"ERROR: Schichttyp für Nachtschicht ('N') nicht gefunden.")
                        continue
                else:
                    continue  # Leere Zellen ignorieren

                # Schicht erstellen
                try:
                    schicht = Schicht.objects.create(
                        schichtplan=schichtplan,
                        mitarbeiter=mitarbeiter,
                        datum=datum,
                        schichttyp=schichttyp
                    )
                    print(f"DEBUG: Schicht erstellt: {schicht.datum} für {schicht.mitarbeiter} mit Schichttyp {schicht.schichttyp}")  # Debugging-Ausgabe
                except Exception as e:
                    print(f"ERROR: Fehler beim Erstellen der Schicht: {str(e)}")
