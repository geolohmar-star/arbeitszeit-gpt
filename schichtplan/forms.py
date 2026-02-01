# schichtplan/forms.py
"""
Formulare für das Schichtplan-Modul
KORRIGIERT: Feld 'bemerkung' aus SchichtForm entfernt
"""

from django import forms
from .models import Schichtplan, Schicht, Schichttyp


class SchichtplanForm(forms.ModelForm):
    """
    Formular zum Erstellen und Bearbeiten von Schichtplänen.
    Enthält optionales Feld für KI-gestützte Generierung.
    """
    
    vorschlag_generieren = forms.BooleanField(
        required=False,
        initial=False,
        label="🤖 KI-Vorschlag automatisch generieren",
        help_text=(
            "Das System analysiert historische Schichtdaten der letzten Monate "
            "und erstellt einen optimierten Dienstplan unter Berücksichtigung von "
            "Ruhezeiten, Mitarbeiter-Präferenzen und fairer Verteilung."
        )
    )
    
    class Meta:
        model = Schichtplan
        fields = ['name', 'start_datum', 'ende_datum', 'status', 'bemerkungen']
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'z.B. "Dezember 2025"'
            }),
            'start_datum': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'ende_datum': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'bemerkungen': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optionale Notizen zum Plan...'
            }),
        }
        
        labels = {
            'name': 'Plan-Name',
            'start_datum': 'Startdatum',
            'ende_datum': 'Enddatum',
            'status': 'Status',
            'bemerkungen': 'Bemerkungen'
        }
    
    def clean(self):
        """Validierung des gesamten Formulars"""
        cleaned_data = super().clean()
        start_datum = cleaned_data.get('start_datum')
        ende_datum = cleaned_data.get('ende_datum')
        
        # Prüfe ob Ende nach Start liegt
        if start_datum and ende_datum:
            if ende_datum <= start_datum:
                raise forms.ValidationError(
                    "Das Enddatum muss nach dem Startdatum liegen!"
                )
        
        return cleaned_data


class SchichtForm(forms.ModelForm):
    """
    Formular zum manuellen Zuweisen einzelner Schichten
    KORRIGIERT: 'bemerkung' Feld entfernt (existiert nicht im Model)
    """
    
    class Meta:
        model = Schicht
        fields = ['mitarbeiter', 'datum', 'schichttyp']  # ✅ KORRIGIERT - bemerkung entfernt
        
        widgets = {
            'mitarbeiter': forms.Select(attrs={
                'class': 'form-select'
            }),
            'datum': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'schichttyp': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        
        labels = {
            'mitarbeiter': 'Mitarbeiter',
            'datum': 'Datum',
            'schichttyp': 'Schichttyp',
        }
    
    def __init__(self, *args, **kwargs):
        """
        Initialisierung: Zeige nur aktive Mitarbeiter und Schichttypen
        """
        super().__init__(*args, **kwargs)
        
        # Nur aktive Mitarbeiter anzeigen
        from arbeitszeit.models import Mitarbeiter
        self.fields['mitarbeiter'].queryset = Mitarbeiter.objects.filter(
            aktiv=True
        ).order_by('user__last_name', 'user__first_name')
        
        # Nur aktive Schichttypen anzeigen
        self.fields['schichttyp'].queryset = Schichttyp.objects.filter(
            aktiv=True
        ).order_by('kuerzel')


class ExcelImportForm(forms.Form):
    """
    Formular zum Hochladen von Excel-Dateien für den Import
    """
    
    excel_file = forms.FileField(
        label="Excel-Datei",
        help_text="Erlaubte Formate: .xlsx, .xls (max. 5 MB)",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx,.xls'
        })
    )
    
    def clean_excel_file(self):
        """Validiere die hochgeladene Datei"""
        file = self.cleaned_data.get('excel_file')
        
        if file:
            # Prüfe Dateigröße (max 5 MB)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    "Die Datei ist zu groß! Maximale Größe: 5 MB"
                )
            
            # Prüfe Dateiendung
            valid_extensions = ['.xlsx', '.xls']
            file_name = file.name.lower()
            
            if not any(file_name.endswith(ext) for ext in valid_extensions):
                raise forms.ValidationError(
                    f"Ungültiges Dateiformat! Erlaubt: {', '.join(valid_extensions)}"
                )
        
        return file

