"""
Forms fuer die workflow-App.
"""
from django import forms

from .models import ProzessAntrag


class ProzessAntragForm(forms.ModelForm):
    """Formular zum Einreichen eines neuen Prozessantrags."""

    class Meta:
        model = ProzessAntrag
        fields = [
            "name",
            "ziel",
            "ausloeser_typ",
            "ausloeser_detail",
            "team_benoetigt",
            "team_vorschlag",
            "pdf_benoetigt",
            "bemerkungen",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "z.B. Rechnungspruefung Elektro Klein",
            }),
            "ziel": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Was soll am Ende des Prozesses erreicht sein?",
            }),
            "ausloeser_typ": forms.Select(
                attrs={"class": "form-select", "id": "id_ausloeser_typ"}
            ),
            "ausloeser_detail": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": (
                    "z.B. Dokument mit Tag 'Eingangsrechnung' "
                    "kommt aus Paperless"
                ),
            }),
            "team_vorschlag": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "z.B. Anna Schmidt, Frank Huber",
            }),
            "bemerkungen": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Alles was sonst noch wichtig ist ...",
            }),
        }
