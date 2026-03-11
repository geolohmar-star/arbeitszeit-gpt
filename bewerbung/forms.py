from django import forms

from .models import Bewerbung, BewerbungDokument

ERLAUBTE_DOK_TYPEN = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}
MAX_DOK_GROESSE = 10 * 1024 * 1024  # 10 MB


class BewerbungForm(forms.ModelForm):
    """Hauptformular fuer den Bewerbungsbogen.

    Wird in Abschnitte aufgeteilt dargestellt (kein Wizard – eine Seite,
    per Abschnitt mit HTML fieldset strukturiert).
    """

    class Meta:
        model = Bewerbung
        exclude = [
            "status", "erstellt_am", "geaendert_am",
            "bearbeitet_von", "interne_notiz",
            "angestrebte_stelle", "geplantes_eintrittsdatum",
            "vertragsart", "probezeit_bis",
        ]
        widgets = {
            "geburtsdatum": forms.DateInput(attrs={"type": "date"}),
            "anrede": forms.Select(attrs={"class": "form-select"}),
            "familienstand": forms.Select(attrs={"class": "form-select"}),
            "konfession": forms.Select(attrs={"class": "form-select"}),
            "steuerklasse": forms.Select(attrs={"class": "form-select"}),
            "krankenversicherungsart": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-control")


class HREinstellungForm(forms.ModelForm):
    """Von HR ausgefuellte Felder beim Einstellungsgespraech."""

    class Meta:
        model = Bewerbung
        fields = [
            "angestrebte_stelle",
            "geplantes_eintrittsdatum",
            "vertragsart",
            "probezeit_bis",
            "interne_notiz",
        ]
        widgets = {
            "geplantes_eintrittsdatum": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "probezeit_bis": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "vertragsart": forms.Select(attrs={"class": "form-select"}),
            "interne_notiz": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["angestrebte_stelle"].widget.attrs["class"] = "form-select"
        self.fields["angestrebte_stelle"].required = False
        # Nur unbesetzte Stellen anzeigen (keine aktive HRMitarbeiter-Zuordnung)
        from hr.models import Stelle
        self.fields["angestrebte_stelle"].queryset = Stelle.objects.filter(
            hrmitarbeiter__isnull=True
        ).order_by("kuerzel")


class BewerbungDokumentForm(forms.Form):
    """Upload-Formular fuer ein einzelnes Bewerbungsdokument."""

    typ = forms.ChoiceField(
        choices=BewerbungDokument.TYP_CHOICES,
        label="Dokumenttyp",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    datei = forms.FileField(
        label="Datei",
        help_text="Erlaubt: PDF, JPG, PNG – max. 10 MB",
    )

    def clean_datei(self):
        datei = self.cleaned_data.get("datei")
        if datei:
            if datei.size > MAX_DOK_GROESSE:
                raise forms.ValidationError("Datei zu gross (max. 10 MB).")
            if datei.content_type not in ERLAUBTE_DOK_TYPEN:
                raise forms.ValidationError("Nur PDF, JPG oder PNG erlaubt.")
        return datei
