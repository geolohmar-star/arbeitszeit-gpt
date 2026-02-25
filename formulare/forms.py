from django import forms

from formulare.models import (
    AenderungZeiterfassung,
    Dienstreiseantrag,
    Zeitgutschrift,
)


class AenderungZeiterfassungForm(forms.ModelForm):
    """Formular fuer manuelle Aenderungen der Zeiterfassung."""

    class Meta:
        model = AenderungZeiterfassung
        fields = [
            "art",
            "gehen_datum",
            "gehen_terminal",
            "kommen_datum",
            "kommen_terminal",
            "ktaste_datum",
            "ktaste_terminal",
            "tages_datum",
            "kommen_zeit",
            "pause_gehen_zeit",
            "pause_kommen_zeit",
            "gehen_zeit",
            "samstag_art",
            "samstag_beginn",
            "samstag_datum",
            "samstag_ende",
            "samstag_freigabe_ab",
            "samstag_freigabe_bis",
            "samstag_vereinbarungsnummer",
        ]
        widgets = {
            "art": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "gehen_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "gehen_terminal": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "kommen_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "kommen_terminal": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "ktaste_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "ktaste_terminal": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "samstag_art": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "samstag_beginn": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "samstag_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "samstag_ende": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "samstag_freigabe_ab": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "samstag_freigabe_bis": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "samstag_vereinbarungsnummer": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "tages_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "kommen_zeit": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "pause_gehen_zeit": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "pause_kommen_zeit": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "gehen_zeit": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
        }

    def clean(self):
        """Pflichtfelder je nach gewaehlter Art pruefen.

        Bei beruflich_unterwegs und b_taste genuegt es, entweder Kommen
        oder Gehen auszufuellen (ODER-Verknuepfung). Wird eine Seite
        teilweise ausgefuellt, muessen beide Felder dieser Seite komplett sein.
        """
        cleaned_data = super().clean()
        art = cleaned_data.get("art")

        if art in ("beruflich_unterwegs", "b_taste"):
            kommen_datum = cleaned_data.get("kommen_datum")
            kommen_terminal = cleaned_data.get("kommen_terminal")
            gehen_datum = cleaned_data.get("gehen_datum")
            gehen_terminal = cleaned_data.get("gehen_terminal")

            kommen_komplett = kommen_datum and kommen_terminal
            gehen_komplett = gehen_datum and gehen_terminal

            # Mindestens Kommen oder Gehen muss vollstaendig ausgefuellt sein
            if not kommen_komplett and not gehen_komplett:
                self.add_error(
                    None,
                    "Mindestens Kommen oder Gehen muss vollstaendig "
                    "ausgefuellt sein.",
                )

            # Teilweise Eingaben: beide Felder der angefangenen Seite erzwingen
            if kommen_datum and not kommen_terminal:
                self.add_error("kommen_terminal", "Bitte auswaehlen.")
            if kommen_terminal and not kommen_datum:
                self.add_error("kommen_datum", "Datum ist erforderlich.")
            if gehen_datum and not gehen_terminal:
                self.add_error("gehen_terminal", "Bitte auswaehlen.")
            if gehen_terminal and not gehen_datum:
                self.add_error("gehen_datum", "Datum ist erforderlich.")

        elif art == "k_taste":
            if not cleaned_data.get("ktaste_datum"):
                self.add_error("ktaste_datum", "Datum ist erforderlich.")
            if not cleaned_data.get("ktaste_terminal"):
                self.add_error("ktaste_terminal", "Bitte auswaehlen.")

        # Samstagsarbeit: Datum muss ein Samstag sein
        samstag_datum = cleaned_data.get("samstag_datum")
        if samstag_datum and samstag_datum.weekday() != 5:
            self.add_error(
                "samstag_datum",
                "Bitte nur einen Samstag auswaehlen.",
            )

        # Samstagsarbeit: Pflichtfelder je nach Art
        samstag_art = cleaned_data.get("samstag_art")
        if samstag_art == "ausserhalb":
            if not cleaned_data.get("samstag_beginn"):
                self.add_error("samstag_beginn", "Anfangszeit erforderlich.")
            if not cleaned_data.get("samstag_ende"):
                self.add_error("samstag_ende", "Endzeit erforderlich.")
        elif samstag_art == "dauerfreigabe":
            if not cleaned_data.get("samstag_vereinbarungsnummer"):
                self.add_error(
                    "samstag_vereinbarungsnummer",
                    "Vereinbarungsnummer erforderlich.",
                )
            if not cleaned_data.get("samstag_freigabe_ab"):
                self.add_error("samstag_freigabe_ab", "Datum erforderlich.")
            if not cleaned_data.get("samstag_freigabe_bis"):
                self.add_error("samstag_freigabe_bis", "Datum erforderlich.")

        return cleaned_data


class DienstreiseantragForm(forms.ModelForm):
    """Formular fuer Dienstreiseantraege."""

    class Meta:
        model = Dienstreiseantrag
        fields = [
            "von_datum",
            "bis_datum",
            "ziel",
            "zweck",
            "geschaetzte_kosten",
        ]
        widgets = {
            "von_datum": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "bis_datum": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "ziel": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "z.B. München, Berlin, Paris",
                }
            ),
            "zweck": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Beschreiben Sie den Grund und das Ziel der Dienstreise...",
                }
            ),
            "geschaetzte_kosten": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),
        }

    def clean(self):
        """Validiere Datumsbereiche."""
        cleaned_data = super().clean()
        von_datum = cleaned_data.get("von_datum")
        bis_datum = cleaned_data.get("bis_datum")

        if von_datum and bis_datum:
            if bis_datum < von_datum:
                self.add_error(
                    "bis_datum",
                    "Reiseende muss nach Reisebeginn liegen."
                )

        return cleaned_data


class ZeitgutschriftForm(forms.ModelForm):
    """Formular fuer Zeitgutschriften.

    Unterstuetzt drei Arten:
    - Haertefallregelung (dynamische Zeilen)
    - Ehrenamt (dynamische Zeilen)
    - Fortbildung (Checkbox-gesteuert mit Berechnung)
    """

    # Multi-File-Upload fuer Belege
    belege = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),
        label="Belege (optional)",
        help_text="PDF, JPG oder PNG, max. 10 MB pro Datei",
    )

    class Meta:
        model = Zeitgutschrift
        fields = [
            "art",
            "fortbildung_aktiv",
            "fortbildung_typ",
            "fortbildung_wochenstunden_regulaer",
            "fortbildung_von_datum",
            "fortbildung_bis_datum",
            "fortbildung_massnahme_nr",
        ]
        widgets = {
            "art": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "fortbildung_aktiv": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "fortbildung_typ": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "fortbildung_wochenstunden_regulaer": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "fortbildung_von_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "fortbildung_bis_datum": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "fortbildung_massnahme_nr": forms.TextInput(
                attrs={"class": "form-control"}
            ),
        }

    def clean(self):
        """Validierung je nach Art."""
        cleaned_data = super().clean()
        art = cleaned_data.get("art")

        # Fortbildung: Wenn aktiviert, alle Felder Pflicht
        if art == "fortbildung" and cleaned_data.get("fortbildung_aktiv"):
            erforderlich = [
                ("fortbildung_typ", "Typ ist erforderlich."),
                (
                    "fortbildung_wochenstunden_regulaer",
                    "Wochenstunden sind erforderlich.",
                ),
                ("fortbildung_von_datum", "Von-Datum ist erforderlich."),
                ("fortbildung_bis_datum", "Bis-Datum ist erforderlich."),
                ("fortbildung_massnahme_nr", "Massnahmen-Nr ist erforderlich."),
            ]

            for feld, fehlertext in erforderlich:
                if not cleaned_data.get(feld):
                    self.add_error(feld, fehlertext)

            # Von-Bis-Validierung
            von_datum = cleaned_data.get("fortbildung_von_datum")
            bis_datum = cleaned_data.get("fortbildung_bis_datum")
            if von_datum and bis_datum and bis_datum < von_datum:
                self.add_error(
                    "fortbildung_bis_datum",
                    "Bis-Datum muss nach Von-Datum liegen.",
                )

        return cleaned_data

    def clean_belege(self):
        """Validiere Upload-Dateien."""
        dateien = self.files.getlist("belege")
        erlaubte_typen = ["pdf", "jpg", "jpeg", "png"]
        max_groesse = 10 * 1024 * 1024  # 10 MB

        for datei in dateien:
            # Dateityp pruefen
            dateiname = datei.name.lower()
            erweiterung = dateiname.split(".")[-1]
            if erweiterung not in erlaubte_typen:
                raise forms.ValidationError(
                    f"Ungueltige Datei '{datei.name}'. Nur PDF, JPG, PNG erlaubt."
                )

            # Dateigroesse pruefen
            if datei.size > max_groesse:
                raise forms.ValidationError(
                    f"Datei '{datei.name}' ist zu gross (max. 10 MB)."
                )

        return dateien
