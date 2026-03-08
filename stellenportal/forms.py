from django import forms

from .models import Ausschreibung, Bewerbung


class AusschreibungForm(forms.ModelForm):
    """Formular fuer HR zum Erstellen und Bearbeiten von Ausschreibungen."""

    class Meta:
        model = Ausschreibung
        fields = [
            "titel",
            "orgeinheit",
            "stelle",
            "beschaeftigungsart",
            "beschreibung",
            "aufgaben",
            "anforderungen",
            "bewerbungsfrist",
            "status",
            "veroeffentlicht",
        ]
        widgets = {
            "beschreibung": forms.Textarea(attrs={"rows": 8}),
            "aufgaben": forms.Textarea(attrs={"rows": 6}),
            "anforderungen": forms.Textarea(attrs={"rows": 6}),
            "bewerbungsfrist": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nur unbesetzte Stellen zur Auswahl anbieten
        from hr.models import Stelle
        self.fields["stelle"].queryset = Stelle.objects.filter(
            hrmitarbeiter__isnull=True
        ).select_related("org_einheit")
        self.fields["stelle"].empty_label = "— keine Stelle verknuepft —"
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-check-input")


class BewerbungForm(forms.ModelForm):
    """Kurzes Bewerbungsformular fuer Mitarbeiter."""

    class Meta:
        model = Bewerbung
        fields = ["motivationstext"]
        widgets = {
            "motivationstext": forms.Textarea(
                attrs={
                    "rows": 8,
                    "class": "form-control",
                    "placeholder": (
                        "Beschreibe kurz, warum du dich fuer diese Stelle interessierst "
                        "und was du mitbringst. Neue Qualifikationsnachweise kannst du "
                        "separat ueber den sicheren Dokumentenkanal an HR senden."
                    ),
                }
            )
        }
        labels = {
            "motivationstext": "Warum interessiert dich diese Stelle?",
        }


class BewerbungStatusForm(forms.ModelForm):
    """HR-Formular zum Setzen des Bewerbungsstatus und einer internen Notiz."""

    class Meta:
        model = Bewerbung
        fields = ["status", "hr_notiz"]
        widgets = {
            "hr_notiz": forms.Textarea(
                attrs={"rows": 4, "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].widget.attrs["class"] = "form-select"
        self.fields["hr_notiz"].label = "Interne Notiz (nicht sichtbar fuer Bewerber)"
