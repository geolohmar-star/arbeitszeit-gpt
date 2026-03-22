from django.contrib.auth.models import User
from django.db import models


class FeldGruppe(models.Model):
    """Wiederverwendbarer Feld-Baustein.

    Einmal definiert, in beliebig viele Formular-Schemata einfuegbar.
    Felder werden beim Einfuegen als Kopie in das Schema uebernommen.
    """

    beschreibung = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erstelle_feldgruppen",
    )
    felder_json = models.JSONField(default=dict)
    geaendert_am = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        verbose_name = "Feld-Baustein"
        verbose_name_plural = "Feld-Bausteine"

    def __str__(self):
        return self.name

    def felder(self):
        return self.felder_json.get("felder", [])


class FormularSchema(models.Model):
    """Definition eines Formulars als JSON-Schema.

    Wird vom Prozessverantwortlichen erstellt und gepflegt.
    Das schema_json enthaelt die Feld-Definitionen (Typ, Label, Pflicht, etc.).
    """

    aktiv = models.BooleanField(default=True)
    beschreibung = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erstelle_schemata",
    )
    geaendert_am = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=200)
    schema_json = models.JSONField(default=dict)

    class Meta:
        ordering = ["name"]
        verbose_name = "Formular-Schema"
        verbose_name_plural = "Formular-Schemata"

    def __str__(self):
        return self.name

    def felder(self):
        """Gibt die Feld-Liste aus dem schema_json zurueck."""
        return self.schema_json.get("felder", [])


class FormularEintrag(models.Model):
    """Ausgefuelltes Formular – ein konkreter Eintrag zu einem Schema."""

    daten_json = models.JSONField(default=dict)
    eingereicht_am = models.DateTimeField(auto_now_add=True)
    eingereicht_von = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formular_eintraege",
    )
    schema = models.ForeignKey(
        FormularSchema,
        on_delete=models.PROTECT,
        related_name="eintraege",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("eingereicht", "Eingereicht"),
            ("in_bearbeitung", "In Bearbeitung"),
            ("erledigt", "Erledigt"),
            ("abgelehnt", "Abgelehnt"),
        ],
        default="eingereicht",
    )

    class Meta:
        ordering = ["-eingereicht_am"]
        verbose_name = "Formular-Eintrag"
        verbose_name_plural = "Formular-Eintraege"

    def __str__(self):
        return f"{self.schema.name} – {self.eingereicht_von} ({self.eingereicht_am:%d.%m.%Y})"
