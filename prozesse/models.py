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

    SICHTBARKEIT_INTERN = "intern"
    SICHTBARKEIT_EXTERN = "extern"
    SICHTBARKEIT_CHOICES = [
        ("intern", "Intern (Login erforderlich)"),
        ("extern", "Extern (oeffentlich, Kiosk)"),
    ]

    aktiv = models.BooleanField(default=True)
    beschreibung = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    kuerzel = models.CharField(
        max_length=6,
        blank=True,
        verbose_name="Kürzel",
        help_text="2-6 Grossbuchstaben, z.B. HUN fuer Hundesteuer. Wird fuer Vorgangsnummern verwendet.",
    )
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
    sichtbarkeit = models.CharField(
        max_length=10,
        choices=SICHTBARKEIT_CHOICES,
        default="intern",
        verbose_name="Sichtbarkeit",
    )
    workflow_template = models.ForeignKey(
        "workflow.WorkflowTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formular_schemata",
        verbose_name="Workflow bei Eingang",
        help_text=(
            "Welcher Workflow automatisch gestartet wird wenn ein unterschriebenes "
            "Dokument per Paperless erkannt wird (Vorgangsnummer-Match)."
        ),
    )

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
    paperless_dokument_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Paperless-Dokument-ID",
        help_text="Wird gesetzt wenn ein physisch unterschriebenes Dokument in Paperless erkannt wurde.",
    )
    workflow_instance = models.OneToOneField(
        "workflow.WorkflowInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formular_eintrag",
        verbose_name="Workflow-Instanz",
        help_text="Wird automatisch gesetzt wenn nach Paperless-Eingang ein Workflow gestartet wurde.",
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
    vorgangsnummer = models.CharField(
        max_length=30,
        blank=True,
        unique=True,
        null=True,
        verbose_name="Vorgangsnummer",
    )

    class Meta:
        ordering = ["-eingereicht_am"]
        verbose_name = "Formular-Eintrag"
        verbose_name_plural = "Formular-Eintraege"

    def __str__(self):
        return f"{self.schema.name} – {self.eingereicht_von} ({self.eingereicht_am:%d.%m.%Y})"

    @staticmethod
    def generiere_vorgangsnummer(schema):
        """Erzeugt eine eindeutige Vorgangsnummer im Format KÜRZEL-LFDNR-DATUM-UHRZEIT.

        Beispiel: HUN-00042-20260323-1423
        Ohne Kuerzel: FORM-00042-20260323-1423
        """
        from django.utils import timezone as tz
        kuerzel = (schema.kuerzel or "FORM").upper().strip()
        jetzt = tz.localtime()
        # Laufende Nummer: hoechste bisherige + 1
        letzte = FormularEintrag.objects.filter(
            vorgangsnummer__startswith=kuerzel + "-"
        ).order_by("-pk").first()
        if letzte and letzte.vorgangsnummer:
            try:
                lfd = int(letzte.vorgangsnummer.split("-")[1]) + 1
            except (IndexError, ValueError):
                lfd = 1
        else:
            lfd = 1
        return f"{kuerzel}-{lfd:05d}-{jetzt.strftime('%Y%m%d')}-{jetzt.strftime('%H%M')}"
