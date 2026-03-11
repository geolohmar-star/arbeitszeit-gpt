# hr/forms.py
from django import forms

from .models import Personalstammdaten


class PersonalstammdatenForm(forms.ModelForm):
    """Formular fuer HR zur Ansicht und Bearbeitung der Personalstammdaten."""

    class Meta:
        model = Personalstammdaten
        exclude = ["mitarbeiter", "angelegt_am", "geaendert_am", "angelegt_von"]
        widgets = {
            "anrede": forms.Select(attrs={"class": "form-select"}),
            "familienstand": forms.Select(attrs={"class": "form-select"}),
            "konfession": forms.Select(attrs={"class": "form-select"}),
            "steuerklasse": forms.Select(attrs={"class": "form-select"}),
            "krankenversicherungsart": forms.Select(attrs={"class": "form-select"}),
            "vertragsart": forms.Select(attrs={"class": "form-select"}),
            "geburtsdatum": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "probezeit_bis": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "austrittsdatum": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.Select, forms.DateInput)):
                field.widget.attrs.setdefault("class", "form-control")
