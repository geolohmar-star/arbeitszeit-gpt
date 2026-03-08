from django import forms
from django.contrib.auth.models import User

from .models import SensiblesDokument

# Erlaubte MIME-Typen fuer den Upload
ERLAUBTE_TYPEN = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_GROESSE_BYTES = 15 * 1024 * 1024  # 15 MB


class DokumentHochladenForm(forms.Form):
    """Formular fuer den verschluesselten Dokument-Upload.

    Fuer Staff-User wird das ziel_user-Feld angezeigt (Upload fuer andere MA).
    Normale User laden nur fuer sich selbst hoch.
    """

    ziel_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("last_name", "first_name"),
        label="Mitarbeiter (fuer wen)",
        required=False,
        help_text="Nur fuer HR/Staff: Dokument einem anderen Mitarbeiter zuordnen.",
    )
    kategorie = forms.ChoiceField(
        choices=SensiblesDokument.KATEGORIE_CHOICES,
        label="Kategorie",
    )
    datei = forms.FileField(
        label="Datei",
        help_text="Erlaubt: PDF, JPG, PNG, DOCX – max. 15 MB",
    )
    beschreibung = forms.CharField(
        max_length=500,
        required=False,
        label="Beschreibung",
        widget=forms.TextInput(attrs={"placeholder": "Optional: z.B. 'Abschlusszeugnis 2019'"}),
    )
    gueltig_bis = forms.DateField(
        required=False,
        label="Gueltig bis",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Optional: z.B. Ablaufdatum eines Fuehrerscheins",
    )

    def __init__(self, *args, is_staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_staff:
            # Normaler User sieht kein User-Auswahlfeld
            self.fields.pop("ziel_user")

    def clean_datei(self):
        datei = self.cleaned_data.get("datei")
        if datei:
            if datei.size > MAX_GROESSE_BYTES:
                raise forms.ValidationError(
                    f"Datei zu gross ({datei.size // (1024*1024):.1f} MB). Maximale Groesse: 15 MB."
                )
            if datei.content_type not in ERLAUBTE_TYPEN:
                raise forms.ValidationError(
                    "Dateityp nicht erlaubt. Bitte nur PDF, JPG, PNG oder DOCX hochladen."
                )
        return datei
