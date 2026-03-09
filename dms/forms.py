"""DMS-Formulare fuer Upload und Suche."""
from django import forms

from .models import Dokument, DokumentKategorie, DokumentTag


class DokumentUploadForm(forms.ModelForm):
    """Formular fuer manuellen Dokument-Upload."""

    datei = forms.FileField(
        label="Datei",
        help_text="PDF, Word, Excel oder Bild. Maximale Groesse: 25 MB.",
    )

    class Meta:
        model = Dokument
        fields = ["titel", "klasse", "kategorie", "tags", "beschreibung", "gueltig_bis"]
        widgets = {
            "titel": forms.TextInput(attrs={"class": "form-control"}),
            "klasse": forms.Select(attrs={"class": "form-select"}),
            "kategorie": forms.Select(attrs={"class": "form-select"}),
            "tags": forms.SelectMultiple(attrs={"class": "form-select", "size": "5"}),
            "beschreibung": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "gueltig_bis": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def clean_datei(self):
        datei = self.cleaned_data.get("datei")
        if datei:
            if datei.size > 25 * 1024 * 1024:
                raise forms.ValidationError(
                    "Die Datei ist zu gross. Maximale Groesse: 25 MB."
                )
        return datei


class DokumentSucheForm(forms.Form):
    """Suchformular fuer DMS-Dokumente."""

    q = forms.CharField(
        required=False,
        label="Suchbegriff",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Volltext suchen...",
            "autofocus": True,
        }),
    )
    klasse = forms.ChoiceField(
        required=False,
        choices=[("", "Alle"), ("offen", "Offen"), ("sensibel", "Sensibel")],
        label="Klasse",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    kategorie = forms.ModelChoiceField(
        required=False,
        queryset=DokumentKategorie.objects.all(),
        label="Kategorie",
        empty_label="Alle Kategorien",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    tag = forms.ModelChoiceField(
        required=False,
        queryset=DokumentTag.objects.all(),
        label="Tag",
        empty_label="Alle Tags",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
