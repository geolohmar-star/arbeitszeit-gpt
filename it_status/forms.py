from django import forms
from django.utils import timezone

from .models import ITStatusMeldung, ITSystem, ITWartung


class StatusMeldungForm(forms.ModelForm):
    """Formular fuer neue Statusmeldungen (Stoerung, Warnung, Wartung)."""

    class Meta:
        model = ITStatusMeldung
        fields = ["system", "status", "titel", "beschreibung"]
        widgets = {
            "system": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "titel": forms.TextInput(attrs={"class": "form-control", "placeholder": "Kurze Beschreibung der Meldung"}),
            "beschreibung": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Details (optional)"}),
        }


class StatusMeldungSchliessenForm(forms.ModelForm):
    """Markiert eine Meldung als geloest."""

    class Meta:
        model = ITStatusMeldung
        fields = ["geloest_am"]
        widgets = {
            "geloest_am": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["geloest_am"].required = True
        # Voreinstellung: jetzt
        if not self.initial.get("geloest_am"):
            self.initial["geloest_am"] = timezone.now().strftime("%Y-%m-%dT%H:%M")


class WartungForm(forms.ModelForm):
    """Formular fuer geplante Wartungsfenster."""

    class Meta:
        model = ITWartung
        fields = ["system", "titel", "beschreibung", "start", "ende"]
        widgets = {
            "system": forms.Select(attrs={"class": "form-select"}),
            "titel": forms.TextInput(attrs={"class": "form-control", "placeholder": "z.B. Update OnlyOffice"}),
            "beschreibung": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Details (optional)"}),
            "start": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "ende": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start")
        ende = cleaned.get("ende")
        if start and ende and ende <= start:
            raise forms.ValidationError("Ende muss nach dem Start liegen.")
        return cleaned


class SystemStatusForm(forms.ModelForm):
    """Schnell-Aenderung des System-Status direkt in der Uebersicht."""

    class Meta:
        model = ITSystem
        fields = ["status"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
        }


class ITSystemForm(forms.ModelForm):
    """Formular zum Anlegen und Bearbeiten eines IT-Systems."""

    class Meta:
        model = ITSystem
        fields = ["bezeichnung", "beschreibung", "ping_url", "reihenfolge", "aktiv"]
        widgets = {
            "bezeichnung": forms.TextInput(attrs={"class": "form-control", "placeholder": "z.B. E-Mail-Server"}),
            "beschreibung": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Kurze Beschreibung (optional)"}),
            "ping_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://... (optional)"}),
            "reihenfolge": forms.NumberInput(attrs={"class": "form-control"}),
            "aktiv": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
