"""Musteranleitungen als PDF – beschreibt Formularprozesse anhand des Workflow-Editors.

Jede Anleitung liest den aktiven Workflow-Template aus der DB und stellt alle
Prozessschritte mit Zustaendigkeiten, Stellenkuerzeln und Teilnehmerliste dar.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


@login_required
def anleitung_aenderung_pdf(request):
    """Erzeugt eine Musteranleitung fuer die Aenderungsmeldung Zeiterfassung als PDF.

    Liest den aktiven Workflow-Template aus der Datenbank und stellt alle
    Prozessschritte mit Zustaendigkeiten und Stellenkuerzeln dar.
    """
    from weasyprint import HTML

    from formulare.models import AenderungZeiterfassung
    from hr.models import HRMitarbeiter
    from workflow.models import WorkflowStep, WorkflowTemplate

    # Aktiven Workflow-Template fuer Aenderungsmeldung laden
    template_qs = WorkflowTemplate.objects.filter(
        trigger_event="aenderung_erstellt",
        ist_aktiv=True,
    ).prefetch_related(
        "schritte__zustaendig_stelle__org_einheit",
        "schritte__zustaendig_team",
        "schritte__eskalation_an_stelle",
    )
    workflow_template = template_qs.first()

    schritte = []
    if workflow_template:
        schritte = list(
            WorkflowStep.objects
            .filter(template=workflow_template)
            .select_related(
                "zustaendig_stelle__org_einheit",
                "zustaendig_org",
                "zustaendig_team",
                "eskalation_an_stelle",
            )
            .order_by("reihenfolge")
        )

    # Alle Mitarbeiter mit Stelle, Vorgesetztem und Org-Einheit
    mitarbeiter_liste = list(
        HRMitarbeiter.objects
        .select_related(
            "stelle__org_einheit",
            "vorgesetzter__stelle",
            "user",
        )
        .order_by("stelle__org_einheit__bezeichnung", "nachname", "vorname")
    )

    # Rollen-Beschreibungen fuer die Anleitung
    rollen_erklaerung = {
        "direkter_vorgesetzter": "Direkte Fuehrungskraft des Antragstellers",
        "bereichsleiter": "Bereichsleiter der zugeordneten Organisationseinheit",
        "geschaeftsfuehrung": "Geschaeftsfuehrung",
        "hr": "HR-Abteilung",
        "controlling": "Controlling",
        "team_queue": "Bearbeitungsstapel des zugewiesenen Teams",
        "spezifische_stelle": "Konkret benannte Stelle (Stellenkuerzel)",
        "spezifische_org": "Alle Mitglieder der Organisationseinheit",
    }

    kontext = {
        "workflow_template": workflow_template,
        "schritte": schritte,
        "mitarbeiter_liste": mitarbeiter_liste,
        "rollen_erklaerung": rollen_erklaerung,
        "erstellt_am": timezone.localtime(timezone.now()),
        "titel": "Musteranleitung: Aenderungsmeldung Zeiterfassung",
    }

    html_string = render_to_string(
        "formulare/anleitung_aenderung_pdf.html", kontext, request=request
    )

    try:
        pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
    except Exception:
        logger.exception("Fehler beim Erzeugen der Anleitung-PDF")
        return HttpResponse("PDF-Erzeugung fehlgeschlagen.", status=500)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        'inline; filename="Musteranleitung_Aenderungsmeldung.pdf"'
    )
    return response


@login_required
def anleitung_zeitgutschrift_pdf(request):
    """Erzeugt eine Musteranleitung fuer den Zeitgutschrift-Antrag als PDF.

    Liest den aktiven Workflow-Template aus der Datenbank und stellt alle
    Prozessschritte mit Zustaendigkeiten und Stellenkuerzeln dar.
    """
    from weasyprint import HTML

    from hr.models import HRMitarbeiter
    from workflow.models import WorkflowStep, WorkflowTemplate

    workflow_template = (
        WorkflowTemplate.objects
        .filter(trigger_event="zeitgutschrift_erstellt", ist_aktiv=True)
        .first()
    )

    schritte = []
    if workflow_template:
        schritte = list(
            WorkflowStep.objects
            .filter(template=workflow_template)
            .select_related(
                "zustaendig_stelle__org_einheit",
                "zustaendig_org",
                "zustaendig_team",
                "eskalation_an_stelle",
            )
            .order_by("reihenfolge")
        )

    mitarbeiter_liste = list(
        HRMitarbeiter.objects
        .select_related(
            "stelle__org_einheit",
            "vorgesetzter__stelle",
            "abteilung",
            "user",
        )
        .order_by("stelle__org_einheit__bezeichnung", "nachname", "vorname")
    )

    rollen_erklaerung = {
        "direkter_vorgesetzter": "Direkte Fuehrungskraft des Antragstellers",
        "direkte_fuehrungskraft": "Direkte Fuehrungskraft (Teamleiter) des Antragstellers",
        "abteilungsleitung": "Abteilungsleiter der zugeordneten Abteilung",
        "bereichsleiter": "Bereichsleiter der Organisationseinheit",
        "geschaeftsfuehrung": "Geschaeftsfuehrung",
        "hr": "HR / Personalwesen",
        "controlling": "Controlling",
        "antragsteller": "Der Antragsteller selbst (Rueckmeldung / Kenntnisnahme)",
        "team_queue": "Bearbeitungsstapel des zugewiesenen Teams",
        "spezifische_stelle": "Konkret benannte Stelle (Stellenkuerzel)",
        "spezifische_org": "Alle Mitglieder der Organisationseinheit",
    }

    kontext = {
        "workflow_template": workflow_template,
        "schritte": schritte,
        "mitarbeiter_liste": mitarbeiter_liste,
        "rollen_erklaerung": rollen_erklaerung,
        "erstellt_am": timezone.localtime(timezone.now()),
        "titel": "Musteranleitung: Zeitgutschrift-Antrag",
    }

    html_string = render_to_string(
        "formulare/anleitung_zeitgutschrift_pdf.html", kontext, request=request
    )

    try:
        pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
    except Exception:
        logger.exception("Fehler beim Erzeugen der Zeitgutschrift-Anleitung-PDF")
        return HttpResponse("PDF-Erzeugung fehlgeschlagen.", status=500)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        'inline; filename="Musteranleitung_Zeitgutschrift.pdf"'
    )
    return response
