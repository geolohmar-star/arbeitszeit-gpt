import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AusschreibungForm, BewerbungForm, BewerbungStatusForm
from .models import Ausschreibung, Bewerbung

logger = logging.getLogger(__name__)

# OrgEinheit-Kuerzel der Personalgewinnung – darf das Stellenportal verwalten
VERWALTUNGS_ORG_KUERZEL = {"PG"}


def kann_verwalten(user):
    """Prueft ob der User das Stellenportal verwalten darf.

    Berechtigt sind: is_staff ODER Mitglieder der OrgEinheit(en) in VERWALTUNGS_ORG_KUERZEL
    (aktuell: PG – Personalgewinnung). Pruefung erfolgt dynamisch ueber die aktuelle
    Stelle des Users – neue PG-Mitglieder erhalten Zugang automatisch.
    """
    if user.is_staff:
        return True
    try:
        kuerzel = user.hr_mitarbeiter.stelle.org_einheit.kuerzel
        return kuerzel in VERWALTUNGS_ORG_KUERZEL
    except AttributeError:
        return False


# ---------------------------------------------------------------------------
# Mitarbeiter-Seiten
# ---------------------------------------------------------------------------

@login_required
def liste(request):
    """Uebersicht aller aktiven und veroeffentlichten Ausschreibungen."""
    ausschreibungen = (
        Ausschreibung.objects
        .filter(status="aktiv", veroeffentlicht=True)
        .select_related("orgeinheit")
        .prefetch_related("bewerbungen")
    )

    # PKs der Ausschreibungen, auf die der User bereits beworben hat
    eigene_bewerbungen = set(
        request.user.stellenbewerbungen
        .filter(ausschreibung__in=ausschreibungen)
        .values_list("ausschreibung_id", flat=True)
    )

    return render(request, "stellenportal/liste.html", {
        "ausschreibungen": ausschreibungen,
        "eigene_bewerbungen": eigene_bewerbungen,
        "kann_verwalten": kann_verwalten(request.user),
    })


@login_required
def detail(request, pk):
    """Detailseite einer Ausschreibung mit Bewerbungsformular."""
    ausschreibung = get_object_or_404(
        Ausschreibung.objects.select_related("orgeinheit", "stelle"),
        pk=pk,
    )

    # Nicht veroeffentlichte nur fuer HR sichtbar
    if not ausschreibung.veroeffentlicht and not request.user.is_staff:
        messages.warning(request, "Diese Ausschreibung ist noch nicht veroeffentlicht.")
        return redirect("stellenportal:liste")

    eigene_bewerbung = Bewerbung.objects.filter(
        ausschreibung=ausschreibung, bewerber=request.user
    ).first()

    form = None
    if ausschreibung.ist_offen and eigene_bewerbung is None:
        form = BewerbungForm()

    return render(request, "stellenportal/detail.html", {
        "ausschreibung": ausschreibung,
        "eigene_bewerbung": eigene_bewerbung,
        "form": form,
        "kann_verwalten": kann_verwalten(request.user),
    })


@login_required
def bewerben(request, pk):
    """Bewerbung auf eine Ausschreibung absenden."""
    ausschreibung = get_object_or_404(Ausschreibung, pk=pk, status="aktiv", veroeffentlicht=True)

    # Doppelte Bewerbung verhindern
    if Bewerbung.objects.filter(ausschreibung=ausschreibung, bewerber=request.user).exists():
        messages.info(request, "Du hast dich bereits auf diese Stelle beworben.")
        return redirect("stellenportal:detail", pk=pk)

    if request.method == "POST":
        form = BewerbungForm(request.POST)
        if form.is_valid():
            bewerbung = form.save(commit=False)
            bewerbung.ausschreibung = ausschreibung
            bewerbung.bewerber = request.user
            bewerbung.save()
            logger.info(
                "Neue interne Bewerbung: User %s auf Ausschreibung %s",
                request.user.username,
                ausschreibung.pk,
            )
            _starte_bewerbungs_workflow(bewerbung, request.user)
            messages.success(
                request,
                f"Bewerbung auf '{ausschreibung.titel}' erfolgreich eingereicht. HR wird sich melden.",
            )
            return redirect("stellenportal:meine_bewerbungen")
    else:
        form = BewerbungForm()

    return render(request, "stellenportal/detail.html", {
        "ausschreibung": ausschreibung,
        "eigene_bewerbung": None,
        "form": form,
        "kann_verwalten": kann_verwalten(request.user),
    })


@login_required
def bewerbung_zurueckziehen(request, pk):
    """Eigene Bewerbung zurueckziehen."""
    bewerbung = get_object_or_404(
        Bewerbung, pk=pk, bewerber=request.user
    )
    if request.method == "POST":
        bewerbung.status = "zurueckgezogen"
        bewerbung.save(update_fields=["status", "geaendert_am"])
        messages.info(request, "Bewerbung zurueckgezogen.")
    return redirect("stellenportal:meine_bewerbungen")


@login_required
def meine_bewerbungen(request):
    """Uebersicht der eigenen Bewerbungen."""
    bewerbungen = (
        request.user.stellenbewerbungen
        .select_related("ausschreibung__orgeinheit")
        .order_by("-erstellt_am")
    )
    return render(request, "stellenportal/meine_bewerbungen.html", {
        "bewerbungen": bewerbungen,
    })


# ---------------------------------------------------------------------------
# HR-Seiten (nur is_staff)
# ---------------------------------------------------------------------------

def _verwaltung_required(request):
    """Hilfsfunktion: leitet Unbefugte auf die Uebersicht weiter."""
    if not kann_verwalten(request.user):
        messages.error(request, "Zugriff nur fuer Mitglieder der Personalgewinnung oder Administratoren.")
        return True
    return False


@login_required
def hr_dashboard(request):
    """HR-Uebersicht aller Ausschreibungen und Bewerbungseingaenge."""
    if _verwaltung_required(request):
        return redirect("stellenportal:liste")

    ausschreibungen = (
        Ausschreibung.objects
        .select_related("orgeinheit", "erstellt_von")
        .prefetch_related("bewerbungen")
        .order_by("-erstellt_am")
    )
    return render(request, "stellenportal/hr_dashboard.html", {
        "ausschreibungen": ausschreibungen,
    })


@login_required
def ausschreibung_erstellen(request):
    """HR erstellt eine neue Ausschreibung."""
    if _verwaltung_required(request):
        return redirect("stellenportal:liste")

    if request.method == "POST":
        form = AusschreibungForm(request.POST)
        if form.is_valid():
            ausschreibung = form.save(commit=False)
            ausschreibung.erstellt_von = request.user
            ausschreibung.save()
            messages.success(request, f"Ausschreibung '{ausschreibung.titel}' erstellt.")
            return redirect("stellenportal:hr_dashboard")
    else:
        form = AusschreibungForm()

    return render(request, "stellenportal/ausschreibung_form.html", {
        "form": form,
        "titel": "Neue Ausschreibung",
    })


@login_required
def ausschreibung_bearbeiten(request, pk):
    """HR bearbeitet eine bestehende Ausschreibung."""
    if _verwaltung_required(request):
        return redirect("stellenportal:liste")

    ausschreibung = get_object_or_404(Ausschreibung, pk=pk)

    if request.method == "POST":
        form = AusschreibungForm(request.POST, instance=ausschreibung)
        if form.is_valid():
            form.save()
            messages.success(request, "Ausschreibung aktualisiert.")
            return redirect("stellenportal:hr_dashboard")
    else:
        form = AusschreibungForm(instance=ausschreibung)

    return render(request, "stellenportal/ausschreibung_form.html", {
        "form": form,
        "titel": f"Bearbeiten: {ausschreibung.titel}",
        "ausschreibung": ausschreibung,
    })


@login_required
def bewerbungen_liste(request, pk):
    """HR sieht alle Bewerbungen auf eine Ausschreibung."""
    if _verwaltung_required(request):
        return redirect("stellenportal:liste")

    ausschreibung = get_object_or_404(
        Ausschreibung.objects.select_related("orgeinheit"), pk=pk
    )
    bewerbungen = (
        ausschreibung.bewerbungen
        .select_related("bewerber")
        .order_by("status", "-erstellt_am")
    )
    return render(request, "stellenportal/bewerbungen_liste.html", {
        "ausschreibung": ausschreibung,
        "bewerbungen": bewerbungen,
    })


@login_required
def bewerbung_aktion(request, pk):
    """HR fuehrt eine Statusaktion auf eine Bewerbung aus (strukturierter Workflow).

    Erlaubte Aktionen und Uebergaenge:
      eingegangen  --in_pruefung--> sichtung
      sichtung     --gespraech---> gespraech
      gespraech    --angebot-----> angeboten
      *            --absagen-----> abgesagt
    """
    if _verwaltung_required(request):
        return redirect("stellenportal:liste")

    bewerbung = get_object_or_404(
        Bewerbung.objects.select_related("ausschreibung", "bewerber"), pk=pk
    )

    UEBERGAENGE = {
        "in_pruefung": ("eingegangen", "sichtung"),
        "gespraech": ("sichtung", "gespraech"),
        "angebot": ("gespraech", "angeboten"),
        "absagen": (None, "abgesagt"),  # None = jeder Ausgangsstatus erlaubt
    }

    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion not in UEBERGAENGE:
            messages.error(request, "Unbekannte Aktion.")
            return redirect("stellenportal:bewerbungen_liste", pk=bewerbung.ausschreibung.pk)

        erlaubter_ausgangsstatus, neuer_status = UEBERGAENGE[aktion]

        if erlaubter_ausgangsstatus and bewerbung.status != erlaubter_ausgangsstatus:
            messages.error(
                request,
                f"Aktion '{aktion}' ist im aktuellen Status '{bewerbung.get_status_display()}' nicht erlaubt.",
            )
            return redirect("stellenportal:bewerbungen_liste", pk=bewerbung.ausschreibung.pk)

        alter_status = bewerbung.get_status_display()
        bewerbung.status = neuer_status
        bewerbung.save(update_fields=["status", "geaendert_am"])

        # Workflow-Entscheidung ableiten und Task weiterschieben
        workflow_entscheidung_map = {
            "in_pruefung": "genehmigt",
            "gespraech": "genehmigt",
            "angebot": "genehmigt",
            "absagen": "abgelehnt",
        }
        _schliesse_bewerbungs_workflow_task(
            bewerbung,
            entscheidung=workflow_entscheidung_map.get(aktion, "genehmigt"),
            user=request.user,
        )

        bewerber_name = bewerbung.bewerber.get_full_name() or bewerbung.bewerber.username
        logger.info(
            "Stellenportal Aktion '%s': Bewerbung %s (%s) -> %s durch %s",
            aktion, pk, alter_status, neuer_status, request.user.username,
        )
        messages.success(
            request,
            f"Bewerbung von {bewerber_name}: Status geaendert zu '{bewerbung.get_status_display()}'.",
        )

    return redirect("stellenportal:bewerbungen_liste", pk=bewerbung.ausschreibung.pk)


def _starte_bewerbungs_workflow(bewerbung, user):
    """Startet den Workflow 'Interne Stellenbewerbung' fuer eine neue Bewerbung.

    Schlaegt still fehl wenn kein aktives Template mit dem Trigger-Event gefunden wird.
    """
    from workflow.models import WorkflowTemplate
    from workflow.services import WorkflowEngine

    try:
        template = WorkflowTemplate.objects.get(
            trigger_event="stellenbewerbung_eingegangen",
            ist_aktiv=True,
        )
        engine = WorkflowEngine()
        engine.start_workflow(template, bewerbung, user)
        logger.info("Workflow 'Interne Stellenbewerbung' fuer Bewerbung %s gestartet.", bewerbung.pk)
    except WorkflowTemplate.DoesNotExist:
        logger.warning(
            "Kein aktives WorkflowTemplate fuer 'stellenbewerbung_eingegangen' gefunden – "
            "Bewerbung %s laeuft ohne Workflow-Tracking.",
            bewerbung.pk,
        )
    except Exception as exc:
        logger.error("Workflow-Start fuer Bewerbung %s fehlgeschlagen: %s", bewerbung.pk, exc)


def _schliesse_bewerbungs_workflow_task(bewerbung, entscheidung, user):
    """Schliesst den offenen WorkflowTask zur Bewerbung ab und rueckt weiter.

    Wird von bewerbung_aktion() aufgerufen wenn ein Statuswechsel erfolgt.
    """
    from workflow.models import WorkflowInstance, WorkflowTask
    from workflow.services import WorkflowEngine
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(Bewerbung)
    instance = WorkflowInstance.objects.filter(
        content_type=ct,
        object_id=bewerbung.pk,
        status="laufend",
    ).first()

    if not instance:
        return

    offener_task = instance.tasks.filter(
        status__in=["offen", "in_bearbeitung"]
    ).order_by("frist").first()

    if not offener_task:
        return

    try:
        engine = WorkflowEngine()
        engine.complete_task(offener_task, entscheidung, "", user)
        logger.info(
            "WorkflowTask %s fuer Bewerbung %s abgeschlossen (%s).",
            offener_task.pk, bewerbung.pk, entscheidung,
        )
    except Exception as exc:
        logger.error("Workflow-Task-Abschluss fehlgeschlagen: %s", exc)


@login_required
def bewerbung_status_setzen(request, pk):
    """HR setzt Status und Notiz einer Bewerbung."""
    if _verwaltung_required(request):
        return redirect("stellenportal:liste")

    bewerbung = get_object_or_404(
        Bewerbung.objects.select_related("ausschreibung", "bewerber"), pk=pk
    )
    if request.method == "POST":
        form = BewerbungStatusForm(request.POST, instance=bewerbung)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Status fuer {bewerbung.bewerber.get_full_name() or bewerbung.bewerber.username} aktualisiert.",
            )
        return redirect("stellenportal:bewerbungen_liste", pk=bewerbung.ausschreibung.pk)

    form = BewerbungStatusForm(instance=bewerbung)
    return render(request, "stellenportal/bewerbung_status_form.html", {
        "bewerbung": bewerbung,
        "form": form,
    })
