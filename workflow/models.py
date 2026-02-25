"""Workflow-System Modelle

Dieses Modul definiert das Workflow-System bestehend aus:
- WorkflowTemplate: Wiederverwendbare Workflow-Definitionen (Blueprints)
- WorkflowStep: Einzelne Schritte innerhalb eines Templates
- WorkflowInstance: Konkrete laufende Workflow-Instanzen
- WorkflowTask: Tasks im Arbeitsstapel der Mitarbeiter
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class WorkflowTemplate(models.Model):
    """Wiederverwendbare Workflow-Definition (Blueprint).

    Ein Template beschreibt die Struktur eines Workflows:
    welche Schritte in welcher Reihenfolge durchlaufen werden,
    wer zustaendig ist, und welche Aktionen erforderlich sind.
    """

    KATEGORIE_GENEHMIGUNG = "genehmigung"
    KATEGORIE_PRUEFUNG = "pruefung"
    KATEGORIE_INFORMATION = "information"
    KATEGORIE_BEARBEITUNG = "bearbeitung"

    KATEGORIE_CHOICES = [
        (KATEGORIE_GENEHMIGUNG, "Genehmigung"),
        (KATEGORIE_PRUEFUNG, "Pruefung"),
        (KATEGORIE_INFORMATION, "Information"),
        (KATEGORIE_BEARBEITUNG, "Bearbeitung"),
    ]

    name = models.CharField(
        max_length=200,
        verbose_name="Name",
        help_text="Name des Workflows (z.B. Urlaubsantrag-Genehmigung)",
    )
    beschreibung = models.TextField(
        blank=True, verbose_name="Beschreibung", help_text="Was macht dieser Workflow?"
    )
    kategorie = models.CharField(
        max_length=50,
        choices=KATEGORIE_CHOICES,
        default=KATEGORIE_GENEHMIGUNG,
        verbose_name="Kategorie",
    )

    # Automatische Ausloesung
    trigger_event = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Trigger-Event",
        help_text="Event das diesen Workflow automatisch startet (z.B. zag_antrag_erstellt)",
    )

    # Status
    ist_aktiv = models.BooleanField(
        default=True, verbose_name="Aktiv", help_text="Inaktive Templates koennen nicht gestartet werden"
    )

    # Metadaten
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erstellte_workflows",
        verbose_name="Erstellt von",
    )
    aktualisiert_am = models.DateTimeField(
        auto_now=True, verbose_name="Aktualisiert am"
    )
    version = models.IntegerField(
        default=1,
        verbose_name="Version",
        help_text="Version fuer Aenderungsverfolgung",
    )

    # Visuelle Verbindungen (Edges) fuer Editor
    edges_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Verbindungen (Edges) - Legacy",
        help_text="DEPRECATED: Wird durch WorkflowTransition ersetzt. Nur fuer Abwaertskompatibilitaet.",
    )

    # NEU: Flag fuer Graph-basierte Workflows
    ist_graph_workflow = models.BooleanField(
        default=False,
        verbose_name="Graph-basierter Workflow",
        help_text="Wenn True, werden Transitions verwendet statt reihenfolge"
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Workflow-Template"
        verbose_name_plural = "Workflow-Templates"

    def __str__(self):
        return f"{self.name} (v{self.version})"

    @property
    def anzahl_schritte(self):
        """Anzahl der Schritte in diesem Template."""
        return self.schritte.count()

    @property
    def durchschnittliche_dauer(self):
        """Durchschnittliche Bearbeitungszeit aller abgeschlossenen Instanzen."""
        abgeschlossene = self.instanzen.filter(status=WorkflowInstance.STATUS_ABGESCHLOSSEN)
        if not abgeschlossene.exists():
            return None

        dauern = []
        for instanz in abgeschlossene:
            if instanz.abgeschlossen_am:
                dauer = (instanz.abgeschlossen_am - instanz.gestartet_am).total_seconds() / 3600
                dauern.append(dauer)

        return sum(dauern) / len(dauern) if dauern else None


class WorkflowStep(models.Model):
    """Ein einzelner Schritt innerhalb eines Workflow-Templates.

    Definiert was in diesem Schritt passieren soll, wer zustaendig ist,
    und welche Bedingungen gelten.
    """

    AKTION_GENEHMIGEN = "genehmigen"
    AKTION_PRUEFEN = "pruefen"
    AKTION_INFORMIEREN = "informieren"
    AKTION_BEARBEITEN = "bearbeiten"
    AKTION_ENTSCHEIDEN = "entscheiden"
    AKTION_BENACHRICHTIGEN = "benachrichtigen"
    AKTION_EMAIL = "email"
    AKTION_WEBHOOK = "webhook"
    AKTION_PYTHON_CODE = "python_code"

    AKTION_CHOICES = [
        (AKTION_GENEHMIGEN, "Genehmigen"),
        (AKTION_PRUEFEN, "Pruefen"),
        (AKTION_INFORMIEREN, "Informieren"),
        (AKTION_BEARBEITEN, "Bearbeiten"),
        (AKTION_ENTSCHEIDEN, "Entscheiden"),
        (AKTION_BENACHRICHTIGEN, "Benachrichtigung senden"),
        (AKTION_EMAIL, "Email senden"),
        (AKTION_WEBHOOK, "Webhook aufrufen"),
        (AKTION_PYTHON_CODE, "Python-Code ausfuehren"),
    ]

    ROLLE_DIREKTER_VORGESETZTER = "direkter_vorgesetzter"
    ROLLE_BEREICHSLEITER = "bereichsleiter"
    ROLLE_GESCHAEFTSFUEHRUNG = "geschaeftsfuehrung"
    ROLLE_HR = "hr"
    ROLLE_CONTROLLING = "controlling"
    ROLLE_SPEZIFISCHE_STELLE = "spezifische_stelle"
    ROLLE_SPEZIFISCHE_ORG = "spezifische_org"
    ROLLE_TEAM_QUEUE = "team_queue"

    ROLLE_CHOICES = [
        (ROLLE_DIREKTER_VORGESETZTER, "Direkter Vorgesetzter"),
        (ROLLE_BEREICHSLEITER, "Bereichsleiter"),
        (ROLLE_GESCHAEFTSFUEHRUNG, "Geschaeftsfuehrung"),
        (ROLLE_HR, "HR / Personalwesen"),
        (ROLLE_CONTROLLING, "Controlling"),
        (ROLLE_SPEZIFISCHE_STELLE, "Spezifische Stelle"),
        (ROLLE_SPEZIFISCHE_ORG, "Spezifische OrgEinheit"),
        (ROLLE_TEAM_QUEUE, "Team-Queue (Bearbeitungsstapel)"),
    ]

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="schritte",
        verbose_name="Template",
    )
    reihenfolge = models.IntegerField(
        verbose_name="Reihenfolge (Legacy)", help_text="Position im Workflow (1, 2, 3...) - DEPRECATED: Wird durch Transitions ersetzt"
    )

    # NEU: Schritt-Typ fuer Graph-Workflows
    schritt_typ = models.CharField(
        max_length=20,
        choices=[
            ("task", "Benutzer-Task (Standard)"),
            ("auto", "Automatische Aktion"),
            ("decision", "Entscheidungs-Node (mehrere Ausgaenge)"),
            ("sync", "Synchronisations-Point (warten auf alle Eingaenge)"),
        ],
        default="task",
        verbose_name="Schritt-Typ"
    )

    # Was soll passieren?
    titel = models.CharField(
        max_length=200,
        verbose_name="Titel",
        help_text="Kurzbeschreibung des Schritts (z.B. Bereichsleiter genehmigt)",
    )
    beschreibung = models.TextField(
        blank=True,
        verbose_name="Beschreibung",
        help_text="Detaillierte Anweisungen fuer den Bearbeiter",
    )
    aktion_typ = models.CharField(
        max_length=50,
        choices=AKTION_CHOICES,
        default=AKTION_PRUEFEN,
        verbose_name="Aktionstyp",
    )

    # Wer ist zustaendig?
    zustaendig_rolle = models.CharField(
        max_length=50,
        choices=ROLLE_CHOICES,
        default=ROLLE_DIREKTER_VORGESETZTER,
        verbose_name="Zustaendige Rolle",
    )
    zustaendig_stelle = models.ForeignKey(
        "hr.Stelle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_schritte",
        verbose_name="Spezifische Stelle",
        help_text="Nur bei Rolle 'Spezifische Stelle'",
    )
    zustaendig_org = models.ForeignKey(
        "hr.OrgEinheit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_schritte",
        verbose_name="Spezifische OrgEinheit",
        help_text="Nur bei Rolle 'Spezifische OrgEinheit'",
    )
    zustaendig_team = models.ForeignKey(
        "formulare.TeamQueue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_schritte",
        verbose_name="Team-Queue",
        help_text="Nur bei Rolle 'Team-Queue' - Team fuer Bearbeitungsstapel",
    )

    # Timing
    frist_tage = models.IntegerField(
        default=3,
        verbose_name="Frist (Tage)",
        help_text="Tage bis zur Bearbeitung",
    )
    ist_parallel = models.BooleanField(
        default=False,
        verbose_name="Parallel",
        help_text="Wird gleichzeitig mit naechstem Schritt ausgefuehrt",
    )

    # Bedingungen (optional)
    bedingung_feld = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bedingungsfeld",
        help_text="Feld das geprueft werden soll (z.B. dauer_tage)",
    )
    bedingung_operator = models.CharField(
        max_length=10,
        blank=True,
        choices=[
            (">", "Groesser als"),
            ("<", "Kleiner als"),
            ("==", "Gleich"),
            ("!=", "Ungleich"),
            (">=", "Groesser oder gleich"),
            ("<=", "Kleiner oder gleich"),
        ],
        verbose_name="Bedingungsoperator",
    )
    bedingung_wert = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bedingungswert",
        help_text="Wert zum Vergleichen",
    )

    # Eskalation
    eskalation_nach_tagen = models.IntegerField(
        default=0,
        verbose_name="Eskalation nach (Tage)",
        help_text="0 = keine Eskalation",
    )
    eskalation_an_stelle = models.ForeignKey(
        "hr.Stelle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eskalierte_schritte",
        verbose_name="Eskalation an Stelle",
    )

    # NEU: Konfiguration fuer automatische Aktionen
    auto_config = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Automatische Aktions-Konfiguration",
        help_text="""Format je nach aktion_typ:
- benachrichtigen: {"nachricht": "Text", "user_ids": [1,2,3]}
- email: {"betreff": "...", "text": "...", "empfaenger": "payroll@firma.de"}
- webhook: {"url": "https://...", "method": "POST", "data": {...}}
- python_code: {"code": "print('hello')"}"""
    )

    class Meta:
        ordering = ["template", "reihenfolge"]
        verbose_name = "Workflow-Schritt"
        verbose_name_plural = "Workflow-Schritte"
        unique_together = ["template", "reihenfolge"]

    def __str__(self):
        return f"{self.template.name} - Schritt {self.reihenfolge}: {self.titel}"

    def bedingung_erfuellt(self, content_object):
        """Prueft ob die Bedingung fuer diesen Schritt erfuellt ist."""
        if not self.bedingung_feld:
            return True

        try:
            wert = getattr(content_object, self.bedingung_feld)
            bedingung_wert = float(self.bedingung_wert) if self.bedingung_wert else 0

            if self.bedingung_operator == ">":
                return wert > bedingung_wert
            elif self.bedingung_operator == "<":
                return wert < bedingung_wert
            elif self.bedingung_operator == "==":
                return wert == bedingung_wert
            elif self.bedingung_operator == "!=":
                return wert != bedingung_wert
            elif self.bedingung_operator == ">=":
                return wert >= bedingung_wert
            elif self.bedingung_operator == "<=":
                return wert <= bedingung_wert
        except (AttributeError, ValueError, TypeError):
            return True

        return True


class WorkflowTransition(models.Model):
    """Definiert Uebergaenge zwischen Workflow-Schritten (Graph-basiert).

    Ersetzt die implizite lineare Reihenfolge durch explizite Uebergaenge
    mit optionalen Bedingungen.
    """

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="transitions",
        verbose_name="Template"
    )

    von_schritt = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        related_name="ausgaenge",
        verbose_name="Von Schritt"
    )

    zu_schritt = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        related_name="eingaenge",
        verbose_name="Zu Schritt",
        null=True,
        blank=True,
        help_text="NULL = Ende-Node"
    )

    # Bedingung fuer diesen Uebergang
    bedingung_typ = models.CharField(
        max_length=20,
        choices=[
            ("immer", "Immer (keine Bedingung)"),
            ("entscheidung", "Basierend auf Task-Entscheidung"),
            ("feld_wert", "Basierend auf Feld-Wert"),
            ("python", "Custom Python-Code"),
        ],
        default="immer",
        verbose_name="Bedingungstyp"
    )

    # Bei bedingung_typ == "entscheidung"
    bedingung_entscheidung = models.CharField(
        max_length=30,
        choices=[
            ("genehmigt", "Genehmigt"),
            ("abgelehnt", "Abgelehnt"),
            ("weitergeleitet", "Weitergeleitet"),
            ("rueckfrage", "Rueckfrage"),
            ("zurueck_genehmiger", "Zurueck an Genehmiger"),
            ("zurueck_antragsteller", "Zurueck an Antragsteller"),
        ],
        null=True,
        blank=True,
        verbose_name="Erwartete Entscheidung"
    )

    # Bei bedingung_typ == "feld_wert"
    bedingung_feld = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bedingungsfeld"
    )
    bedingung_operator = models.CharField(
        max_length=10,
        choices=[
            ("==", "Gleich"),
            ("!=", "Ungleich"),
            (">", "Groesser als"),
            ("<", "Kleiner als"),
            (">=", "Groesser oder gleich"),
            ("<=", "Kleiner oder gleich"),
            ("in", "Enthalten in"),
        ],
        blank=True,
        verbose_name="Operator"
    )
    bedingung_wert = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Bedingungswert"
    )

    # Bei bedingung_typ == "python"
    bedingung_python_code = models.TextField(
        blank=True,
        verbose_name="Python-Code",
        help_text="Python-Code der True/False zurueckgibt. Verfuegbare Variablen: task, instance, content_object"
    )

    # Label fuer Editor
    label = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Beschriftung fuer Editor",
        help_text="z.B. 'genehmigt', 'abgelehnt'"
    )

    prioritaet = models.IntegerField(
        default=1,
        verbose_name="Prioritaet",
        help_text="Bei mehreren zutreffenden Transitions"
    )

    class Meta:
        ordering = ["prioritaet"]
        verbose_name = "Workflow-Uebergang"
        verbose_name_plural = "Workflow-Uebergaenge"

    def __str__(self):
        zu = self.zu_schritt.titel if self.zu_schritt else "Ende"
        return f"{self.von_schritt.titel} -> {zu} ({self.get_bedingung_typ_display()})"

    def evaluate(self, task, content_object):
        """Evaluiert ob diese Transition greifen soll.

        Args:
            task: WorkflowTask Instanz
            content_object: Verknuepftes Objekt (z.B. ZAGAntrag)

        Returns:
            bool: True wenn Transition greifen soll
        """
        if self.bedingung_typ == "immer":
            return True

        elif self.bedingung_typ == "entscheidung":
            return task.entscheidung == self.bedingung_entscheidung

        elif self.bedingung_typ == "feld_wert":
            # Hole Feld-Wert vom content_object
            try:
                wert = getattr(content_object, self.bedingung_feld)
                return self._compare(wert, self.bedingung_operator, self.bedingung_wert)
            except AttributeError:
                return False

        elif self.bedingung_typ == "python":
            # Evaluiere Python-Code (VORSICHT: Sicherheitsrisiko!)
            try:
                local_vars = {
                    "task": task,
                    "instance": task.instance,
                    "content_object": content_object
                }
                return eval(self.bedingung_python_code, {}, local_vars)
            except Exception:
                return False

        return False

    def _compare(self, wert, operator, ziel_wert):
        """Vergleicht Werte basierend auf Operator.

        Args:
            wert: Aktueller Wert vom Objekt
            operator: Vergleichsoperator
            ziel_wert: Zielwert zum Vergleichen

        Returns:
            bool: Ergebnis des Vergleichs
        """
        # Typ-Konvertierung versuchen
        try:
            if isinstance(wert, (int, float)):
                ziel_wert = float(ziel_wert)
        except (ValueError, TypeError):
            pass

        if operator == "==":
            return wert == ziel_wert
        elif operator == "!=":
            return wert != ziel_wert
        elif operator == ">":
            return wert > ziel_wert
        elif operator == "<":
            return wert < ziel_wert
        elif operator == ">=":
            return wert >= ziel_wert
        elif operator == "<=":
            return wert <= ziel_wert
        elif operator == "in":
            return ziel_wert in str(wert)

        return False


class WorkflowInstance(models.Model):
    """Eine konkrete laufende Instanz eines Workflows.

    Repraesentiert einen spezifischen Durchlauf eines Workflow-Templates
    fuer ein bestimmtes Objekt (z.B. einen Z-AG Antrag).
    """

    STATUS_LAUFEND = "laufend"
    STATUS_ABGESCHLOSSEN = "abgeschlossen"
    STATUS_ABGEBROCHEN = "abgebrochen"
    STATUS_PAUSIERT = "pausiert"

    STATUS_CHOICES = [
        (STATUS_LAUFEND, "Laufend"),
        (STATUS_ABGESCHLOSSEN, "Abgeschlossen"),
        (STATUS_ABGEBROCHEN, "Abgebrochen"),
        (STATUS_PAUSIERT, "Pausiert"),
    ]

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.PROTECT,
        related_name="instanzen",
        verbose_name="Template",
    )

    # GenericForeignKey zum verknuepften Objekt (z.B. ZAGAntrag)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Status
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default=STATUS_LAUFEND,
        verbose_name="Status",
    )
    gestartet_am = models.DateTimeField(
        auto_now_add=True, verbose_name="Gestartet am"
    )
    gestartet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="gestartete_workflow_instanzen",
        verbose_name="Gestartet von",
    )
    abgeschlossen_am = models.DateTimeField(
        null=True, blank=True, verbose_name="Abgeschlossen am"
    )

    # Aktueller Stand
    aktueller_schritt = models.ForeignKey(
        WorkflowStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aktive_instanzen",
        verbose_name="Aktueller Schritt",
    )
    fortschritt = models.IntegerField(
        default=0, verbose_name="Fortschritt (%)", help_text="0-100"
    )

    class Meta:
        ordering = ["-gestartet_am"]
        verbose_name = "Workflow-Instanz"
        verbose_name_plural = "Workflow-Instanzen"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["status", "gestartet_am"]),
        ]

    def __str__(self):
        return f"{self.template.name} #{self.id} ({self.get_status_display()})"

    @property
    def ist_laufend(self):
        """Prueft ob der Workflow noch laeuft."""
        return self.status == self.STATUS_LAUFEND

    @property
    def ist_abgeschlossen(self):
        """Prueft ob der Workflow abgeschlossen ist."""
        return self.status == self.STATUS_ABGESCHLOSSEN

    @property
    def dauer_stunden(self):
        """Berechnet die bisherige Dauer in Stunden."""
        if self.abgeschlossen_am:
            return (self.abgeschlossen_am - self.gestartet_am).total_seconds() / 3600
        return (timezone.now() - self.gestartet_am).total_seconds() / 3600

    def berechne_fortschritt(self):
        """Berechnet den Fortschritt basierend auf erledigten Tasks."""
        alle_tasks = self.tasks.count()
        if alle_tasks == 0:
            return 0
        erledigte_tasks = self.tasks.filter(status=WorkflowTask.STATUS_ERLEDIGT).count()
        return int((erledigte_tasks / alle_tasks) * 100)

    def update_fortschritt(self):
        """Aktualisiert den Fortschritt und speichert."""
        self.fortschritt = self.berechne_fortschritt()
        self.save(update_fields=["fortschritt"])


class WorkflowTask(models.Model):
    """Ein Task im Arbeitsstapel eines Mitarbeiters.

    Repraesentiert eine konkrete Aufgabe die aus einem Workflow-Schritt
    resultiert und von einer bestimmten Stelle bearbeitet werden muss.
    """

    STATUS_OFFEN = "offen"
    STATUS_IN_BEARBEITUNG = "in_bearbeitung"
    STATUS_ERLEDIGT = "erledigt"
    STATUS_UEBERSPRUNGEN = "uebersprungen"
    STATUS_ESKALIERT = "eskaliert"

    STATUS_CHOICES = [
        (STATUS_OFFEN, "Offen"),
        (STATUS_IN_BEARBEITUNG, "In Bearbeitung"),
        (STATUS_ERLEDIGT, "Erledigt"),
        (STATUS_UEBERSPRUNGEN, "Uebersprungen"),
        (STATUS_ESKALIERT, "Eskaliert"),
    ]

    ENTSCHEIDUNG_GENEHMIGT = "genehmigt"
    ENTSCHEIDUNG_ABGELEHNT = "abgelehnt"
    ENTSCHEIDUNG_WEITERGELEITET = "weitergeleitet"
    ENTSCHEIDUNG_RUECKFRAGE = "rueckfrage"
    ENTSCHEIDUNG_ZURUECK_GENEHMIGER = "zurueck_genehmiger"
    ENTSCHEIDUNG_ZURUECK_ANTRAGSTELLER = "zurueck_antragsteller"

    ENTSCHEIDUNG_CHOICES = [
        (ENTSCHEIDUNG_GENEHMIGT, "Genehmigt"),
        (ENTSCHEIDUNG_ABGELEHNT, "Abgelehnt"),
        (ENTSCHEIDUNG_WEITERGELEITET, "Weitergeleitet"),
        (ENTSCHEIDUNG_RUECKFRAGE, "Rueckfrage"),
        (ENTSCHEIDUNG_ZURUECK_GENEHMIGER, "Zurueck an Genehmiger"),
        (ENTSCHEIDUNG_ZURUECK_ANTRAGSTELLER, "Zurueck an Antragsteller"),
    ]

    instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Workflow-Instanz",
    )
    step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Workflow-Schritt",
    )

    # Zustaendigkeit
    zugewiesen_an_stelle = models.ForeignKey(
        "hr.Stelle",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_tasks",
        verbose_name="Zugewiesen an Stelle",
        help_text="Entweder Stelle ODER Team-Queue",
    )
    zugewiesen_an_team = models.ForeignKey(
        "formulare.TeamQueue",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_tasks",
        verbose_name="Zugewiesen an Team-Queue",
        help_text="Entweder Stelle ODER Team-Queue",
    )
    zugewiesen_an_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_tasks",
        verbose_name="Zugewiesen an User",
        help_text="Falls konkrete Person statt nur Stelle",
    )

    # Status & Timing
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default=STATUS_OFFEN,
        verbose_name="Status",
    )
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    frist = models.DateTimeField(verbose_name="Frist")
    gestartet_am = models.DateTimeField(
        null=True, blank=True, verbose_name="Gestartet am"
    )
    erledigt_am = models.DateTimeField(
        null=True, blank=True, verbose_name="Erledigt am"
    )
    erledigt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erledigte_workflow_tasks",
        verbose_name="Erledigt von",
    )

    # Ergebnis
    entscheidung = models.CharField(
        max_length=50,
        choices=ENTSCHEIDUNG_CHOICES,
        blank=True,
        verbose_name="Entscheidung",
    )
    kommentar = models.TextField(blank=True, verbose_name="Kommentar")

    class Meta:
        ordering = ["frist", "-erstellt_am"]
        verbose_name = "Workflow-Task"
        verbose_name_plural = "Workflow-Tasks"
        indexes = [
            models.Index(fields=["zugewiesen_an_stelle", "status", "frist"]),
            models.Index(fields=["status", "frist"]),
        ]

    def __str__(self):
        return f"Task #{self.id}: {self.step.titel} ({self.get_status_display()})"

    @property
    def ist_ueberfaellig(self):
        """Prueft ob der Task ueberfaellig ist."""
        if self.status in [self.STATUS_ERLEDIGT, self.STATUS_UEBERSPRUNGEN]:
            return False
        return timezone.now() > self.frist

    @property
    def ist_heute_faellig(self):
        """Prueft ob der Task heute faellig ist."""
        if self.status in [self.STATUS_ERLEDIGT, self.STATUS_UEBERSPRUNGEN]:
            return False
        return self.frist.date() == timezone.now().date()

    @property
    def tage_bis_frist(self):
        """Berechnet Tage bis zur Frist (negativ = ueberfaellig)."""
        if self.status in [self.STATUS_ERLEDIGT, self.STATUS_UEBERSPRUNGEN]:
            return None
        delta = self.frist - timezone.now()
        return delta.days

    def kann_bearbeiten(self, user):
        """Prueft ob der User diesen Task bearbeiten darf."""
        if self.status not in [self.STATUS_OFFEN, self.STATUS_IN_BEARBEITUNG]:
            return False

        # Spezifischer User zugewiesen
        if self.zugewiesen_an_user:
            return user == self.zugewiesen_an_user

        # Team zugewiesen - pruefe ob User Mitglied des Teams ist
        if self.zugewiesen_an_team:
            return self.zugewiesen_an_team.mitglieder.filter(id=user.id).exists()

        # Stelle zugewiesen - pruefe ob User diese Stelle hat
        if self.zugewiesen_an_stelle:
            try:
                return user.hr_mitarbeiter.stelle == self.zugewiesen_an_stelle
            except AttributeError:
                return False

        return False
