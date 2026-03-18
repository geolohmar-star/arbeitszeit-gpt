from datetime import date

from django import forms

from .models import Briefvorlage, Briefvorgang


class BriefvorgangForm(forms.ModelForm):
    """Formular zum Erstellen eines neuen Briefvorgangs."""

    class Meta:
        model = Briefvorgang
        fields = [
            "vorlage",
            # Absender
            "absender_name",
            "absender_strasse",
            "absender_ort",
            "absender_telefon",
            "absender_email",
            # Empfaenger
            "empfaenger_name",
            "empfaenger_zusatz",
            "empfaenger_strasse",
            "empfaenger_plz_ort",
            "empfaenger_land",
            # Briefinhalt
            "ort",
            "datum",
            "betreff",
            "anrede",
            "brieftext",
            "grussformel",
            "unterschrift_name",
            "unterschrift_titel",
        ]
        widgets = {
            "vorlage": forms.Select(attrs={"class": "form-select"}),
            "absender_name":    forms.TextInput(attrs={"class": "form-control"}),
            "absender_strasse": forms.TextInput(attrs={"class": "form-control"}),
            "absender_ort":     forms.TextInput(attrs={"class": "form-control"}),
            "absender_telefon": forms.TextInput(attrs={"class": "form-control"}),
            "absender_email":   forms.EmailInput(attrs={"class": "form-control"}),
            "empfaenger_name":    forms.TextInput(attrs={"class": "form-control"}),
            "empfaenger_zusatz":  forms.TextInput(attrs={"class": "form-control"}),
            "empfaenger_strasse": forms.TextInput(attrs={"class": "form-control"}),
            "empfaenger_plz_ort": forms.TextInput(attrs={"class": "form-control"}),
            "empfaenger_land":    forms.TextInput(attrs={"class": "form-control"}),
            "ort":    forms.TextInput(attrs={"class": "form-control"}),
            "datum":  forms.DateInput(
                attrs={"class": "form-control", "placeholder": "TT.MM.JJJJ"},
                format="%d.%m.%Y",
            ),
            "betreff": forms.TextInput(attrs={"class": "form-control"}),
            "anrede":  forms.TextInput(attrs={"class": "form-control"}),
            "brieftext": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "grussformel":      forms.TextInput(attrs={"class": "form-control"}),
            "unterschrift_name":  forms.TextInput(attrs={"class": "form-control"}),
            "unterschrift_titel": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {
            "vorlage":            "Briefvorlage",
            "absender_name":      "Name / Firma",
            "absender_strasse":   "Straße und Hausnummer",
            "absender_ort":       "PLZ und Ort",
            "absender_telefon":   "Telefon",
            "absender_email":     "E-Mail",
            "empfaenger_name":    "Name",
            "empfaenger_zusatz":  "Zusatz (z. B. Abteilung)",
            "empfaenger_strasse": "Straße und Hausnummer",
            "empfaenger_plz_ort": "PLZ und Ort",
            "empfaenger_land":    "Land (leer lassen für Deutschland)",
            "ort":     "Ort",
            "datum":   "Datum",
            "betreff": "Betreff",
            "anrede":  "Anrede (z. B. Sehr geehrte Frau Müller,)",
            "brieftext":          "Brieftext",
            "grussformel":        "Grußformel",
            "unterschrift_name":  "Unterzeichner (Name)",
            "unterschrift_titel": "Funktion / Titel",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nur aktive Vorlagen anzeigen
        self.fields["vorlage"].queryset = Briefvorlage.objects.filter(ist_aktiv=True)
        # Deutsches Datumsformat: Eingabe und Anzeige als TT.MM.JJJJ
        self.fields["datum"].input_formats = ["%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"]
        # Standardwert: heutiges Datum
        if not self.initial.get("datum"):
            self.initial["datum"] = date.today().strftime("%d.%m.%Y")
