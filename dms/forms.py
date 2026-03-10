"""DMS-Formulare fuer Upload, Suche und Zugriffsantraege."""
from django import forms

from hr.models import OrgEinheit

from .models import DAUER_OPTIONEN, Dokument, DokumentKategorie, DokumentTag, DokumentZugriffsschluessel, PaperlessWorkflowRegel


class DokumentUploadForm(forms.ModelForm):
    """Formular fuer manuellen Dokument-Upload."""

    datei = forms.FileField(
        label="Datei",
        help_text="PDF, Word, Excel oder Bild. Maximale Groesse: 25 MB.",
    )

    class Meta:
        model = Dokument
        fields = [
            "titel",
            "klasse",
            "kategorie",
            "eigentuemereinheit",
            "tags",
            "beschreibung",
            "gueltig_bis",
        ]
        widgets = {
            "titel": forms.TextInput(attrs={"class": "form-control"}),
            "klasse": forms.Select(attrs={"class": "form-select"}),
            "kategorie": forms.Select(attrs={"class": "form-select"}),
            "eigentuemereinheit": forms.Select(attrs={"class": "form-select"}),
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
    orgeinheit = forms.ModelChoiceField(
        required=False,
        queryset=OrgEinheit.objects.all(),
        label="Abteilung",
        empty_label="Alle Abteilungen",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class DokumentNeuForm(forms.ModelForm):
    """Formular fuer die Erstellung eines neuen leeren Dokuments via OnlyOffice."""

    DATEITYP_CHOICES = [
        ("docx", "Word-Dokument (.docx)"),
        ("xlsx", "Excel-Tabelle (.xlsx)"),
    ]

    dateityp_neu = forms.ChoiceField(
        choices=DATEITYP_CHOICES,
        label="Dokumenttyp",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Dokument
        fields = ["titel", "klasse", "kategorie", "eigentuemereinheit", "beschreibung"]
        widgets = {
            "titel": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "z.B. Besprechungsprotokoll 2026-03",
                "autofocus": True,
            }),
            "klasse": forms.Select(attrs={"class": "form-select"}),
            "kategorie": forms.Select(attrs={"class": "form-select"}),
            "eigentuemereinheit": forms.Select(attrs={"class": "form-select"}),
            "beschreibung": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class PaperlessWorkflowRegelForm(forms.ModelForm):
    """Formular zum Anlegen und Bearbeiten von Paperless-Workflow-Regeln."""

    class Meta:
        model = PaperlessWorkflowRegel
        fields = ["bezeichnung", "treffer_typ", "paperless_name", "workflow_template", "prioritaet", "aktiv"]
        widgets = {
            "bezeichnung": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "z.B. Eingangsrechnungen Elektro",
                "autofocus": True,
            }),
            "treffer_typ": forms.Select(attrs={"class": "form-select"}),
            "paperless_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "z.B. Rechnung  oder  elektro",
            }),
            "workflow_template": forms.Select(attrs={"class": "form-select"}),
            "prioritaet": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 999}),
            "aktiv": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "bezeichnung": "Bezeichnung",
            "treffer_typ": "Treffer-Typ",
            "paperless_name": "Paperless-Name (Dokumenttyp oder Tag)",
            "workflow_template": "Workflow-Template",
            "prioritaet": "Prioritaet (1 = hoechste)",
            "aktiv": "Aktiv",
        }
        help_texts = {
            "paperless_name": "Gross-/Kleinschreibung wird ignoriert. Exakter Name wie in Paperless-ngx.",
            "prioritaet": "Bei mehreren Treffern gewinnt die Regel mit der niedrigsten Prioritaetszahl.",
        }


class ZugriffsantragForm(forms.ModelForm):
    """Formular fuer Zugriffsantrag auf ein sensibles Dokument."""

    class Meta:
        model = DokumentZugriffsschluessel
        fields = ["antrag_grund", "gewuenschte_dauer_h"]
        widgets = {
            "antrag_grund": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Bitte begruenden Sie, warum Sie Zugriff auf dieses Dokument benoetigen...",
            }),
            "gewuenschte_dauer_h": forms.Select(
                choices=DAUER_OPTIONEN,
                attrs={"class": "form-select"},
            ),
        }
        labels = {
            "antrag_grund": "Begruendung",
            "gewuenschte_dauer_h": "Zugriffsdauer",
        }
