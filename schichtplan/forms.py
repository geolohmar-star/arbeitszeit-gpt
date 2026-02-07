# schichtplan/forms.py
"""
Formulare für das Schichtplan-Modul
KORRIGIERT: Feld 'bemerkung' aus SchichtForm entfernt
"""

from django import forms
from .models import Schichtplan, Schicht, Schichttyp
from datetime import date, timedelta
from calendar import monthrange


class SchichtplanForm(forms.ModelForm):
    """
    VEREINFACHTES Formular: Nur Monatsauswahl + KI-Generierung
    Start/Ende werden automatisch berechnet
    """
    
    # Dropdown für Monat/Jahr
    monat_jahr = forms.ChoiceField(
        label="Monat auswählen",
        widget=forms.Select(attrs={'class': 'form-select form-select-lg'}),
        help_text="Wähle den Monat für den Schichtplan"
    )
    
    vorschlag_generieren = forms.BooleanField(
        required=False,
        initial=True,  # Standard: aktiviert
        label="🤖 KI-Vorschlag automatisch generieren",
        help_text="Erstellt automatisch einen optimierten Schichtplan"
    )
    
    class Meta:
        model = Schichtplan
        fields = ['bemerkungen']  # Nur Bemerkungen, der Rest wird automatisch gesetzt
        
        widgets = {
            'bemerkungen': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optionale Notizen zum Plan...'
            }),
        }
        
        labels = {
            'bemerkungen': 'Bemerkungen (optional)'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Generiere Monatsliste: Aktueller Monat + 12 Monate voraus
        heute = date.today()
        monate = []
        
        # Deutsche Monatsnamen
        monat_namen = [
            'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
            'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
        ]
        
        for i in range(13):  # 13 Monate (aktueller + 12 nächste)
            monat_datum = heute.replace(day=1) + timedelta(days=32*i)
            monat_datum = monat_datum.replace(day=1)
            
            # Format: "2026-04" für April 2026
            wert = monat_datum.strftime('%Y-%m')
            # Anzeige: "April 2026" auf Deutsch
            anzeige = f"{monat_namen[monat_datum.month - 1]} {monat_datum.year}"
            
            monate.append((wert, anzeige))
        
        self.fields['monat_jahr'].choices = monate
    
    def save(self, commit=True):
        """Berechne Start/Ende automatisch aus monat_jahr"""
        instance = super().save(commit=False)
        
        # Parse monat_jahr (Format: "2026-04")
        monat_jahr_str = self.cleaned_data.get('monat_jahr')
        if monat_jahr_str:
            jahr, monat = map(int, monat_jahr_str.split('-'))
            
            # Setze Start = 1. des Monats
            instance.start_datum = date(jahr, monat, 1)
            
            # Setze Ende = Letzter Tag des Monats
            letzter_tag = monthrange(jahr, monat)[1]
            instance.ende_datum = date(jahr, monat, letzter_tag)
            
            # Setze Name automatisch
            monat_namen = [
                'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
            ]
            instance.name = f"{monat_namen[monat-1]} {jahr}"
            
            # Setze Status auf Entwurf
            if not instance.status:
                instance.status = 'entwurf'
        
        if commit:
            instance.save()
        
        return instance


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

