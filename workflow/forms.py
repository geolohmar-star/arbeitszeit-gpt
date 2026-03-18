"""
Forms fuer die workflow-App.
"""
from django import forms
from django.contrib.contenttypes.models import ContentType

from .models import ProzessAntrag, WorkflowTrigger


def _app_content_types():
    """Gibt ContentTypes nur fuer eigene Apps zurueck (kein Django-Intern)."""
    eigene_apps = [
        "formulare", "workflow", "arbeitszeit", "schichtplan",
        "hr", "betriebssport", "veranstaltungen", "berechtigungen",
        "dms", "raumbuch",
    ]
    return ContentType.objects.filter(app_label__in=eigene_apps).order_by(
        "app_label", "model"
    )


class WorkflowTriggerForm(forms.ModelForm):
    """Formular zum Anlegen und Bearbeiten von WorkflowTriggern."""

    content_type = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Django-Model",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Welches Model loest diesen Trigger aus?",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content_type"].queryset = _app_content_types()

    class Meta:
        model = WorkflowTrigger
        fields = [
            "name",
            "beschreibung",
            "trigger_event",
            "content_type",
            "trigger_auf",
            "antragsteller_pfad",
            "workflow_instance_feld",
            "ist_aktiv",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "z.B. Dienstreiseantrag eingereicht",
            }),
            "beschreibung": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Was loest dieser Trigger aus?",
            }),
            "trigger_event": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "z.B. dienstreise_erstellt",
            }),
            "trigger_auf": forms.Select(attrs={"class": "form-select"}),
            "antragsteller_pfad": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "antragsteller.user",
            }),
            "workflow_instance_feld": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "workflow_instance",
            }),
            "ist_aktiv": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


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
