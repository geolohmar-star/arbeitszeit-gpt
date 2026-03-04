import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import KATEGORIE_CHOICES, FacilityTeam, Stoermeldung, Textbaustein

# Alias fuer Template-Kontext
KATEGORIE_CHOICES_DISPLAY = KATEGORIE_CHOICES

logger = logging.getLogger(__name__)


def _starte_facility_workflow(meldung, user):
    """Startet einen Workflow fuer die Stoermeldung basierend auf der Kategorie.

    Trigger-Event-Name-Schema: 'stoermeldung_{kategorie}_erstellt'
    Erfordert ein aktives WorkflowTemplate mit passendem trigger_event
    und einem team_queue-Step der auf die korrekte formulare.TeamQueue zeigt.
    """
    from workflow.models import WorkflowInstance, WorkflowTemplate
    from workflow.services import WorkflowEngine

    trigger = f"stoermeldung_{meldung.kategorie}_erstellt"
    template = WorkflowTemplate.objects.filter(
        trigger_event=trigger, ist_aktiv=True
    ).first()

    if not template:
        logger.debug(
            "Kein aktives WorkflowTemplate fuer trigger_event='%s' – "
            "Stoermeldung landet nur in der Facility-Queue.",
            trigger,
        )
        return

    # Duplikat-Schutz
    ct = ContentType.objects.get_for_model(meldung)
    bereits_vorhanden = WorkflowInstance.objects.filter(
        template=template,
        content_type=ct,
        object_id=meldung.pk,
        status__in=["laufend", "wartend"],
    ).exists()
    if bereits_vorhanden:
        logger.warning(
            "Workflow '%s' fuer Stoermeldung %s bereits vorhanden.",
            template.name,
            meldung.pk,
        )
        return

    try:
        WorkflowEngine().start_workflow(template, meldung, user)
        logger.info(
            "Workflow '%s' gestartet fuer Stoermeldung pk=%s",
            template.name,
            meldung.pk,
        )
    except Exception as exc:
        logger.error(
            "Fehler beim Starten des Workflows fuer Stoermeldung %s: %s",
            meldung.pk,
            exc,
        )


def _schliesse_facility_workflow_task(meldung, user, kommentar=""):
    """Schliesst den offenen WorkflowTask zur Stoermeldung, falls vorhanden.

    Wird aufgerufen wenn eine Stoermeldung als erledigt oder unloesbar
    markiert wird, damit der Task auch im Arbeitsstapel abgehakt wird.
    """
    from workflow.models import WorkflowInstance, WorkflowTask
    from workflow.services import WorkflowEngine

    ct = ContentType.objects.get_for_model(meldung)
    instance = WorkflowInstance.objects.filter(
        content_type=ct,
        object_id=meldung.pk,
        status__in=["laufend", "wartend"],
    ).first()
    if not instance:
        return

    offener_task = WorkflowTask.objects.filter(
        instance=instance,
        status__in=[WorkflowTask.STATUS_OFFEN, WorkflowTask.STATUS_IN_BEARBEITUNG],
    ).first()
    if not offener_task:
        return

    try:
        entscheidung = (
            WorkflowTask.ENTSCHEIDUNG_GENEHMIGT
            if meldung.status == "erledigt"
            else WorkflowTask.ENTSCHEIDUNG_ABGELEHNT
        )
        WorkflowEngine().complete_task(
            offener_task, user, entscheidung=entscheidung, kommentar=kommentar
        )
        logger.info(
            "WorkflowTask %s fuer Stoermeldung %s abgeschlossen.",
            offener_task.pk,
            meldung.pk,
        )
    except Exception as exc:
        logger.error(
            "Fehler beim Abschliessen des WorkflowTask fuer Stoermeldung %s: %s",
            meldung.pk,
            exc,
        )


def _get_user_teams(user):
    """Gibt die Facility-Teams des Users zurueck (leer bei Staff = alle)."""
    return FacilityTeam.objects.filter(mitglieder=user)


def _hat_facility_zugang(user):
    """True wenn User Facility-Mitglied oder Staff ist."""
    if user.is_staff:
        return True
    return FacilityTeam.objects.filter(mitglieder=user).exists()


def _hat_textbaustein_zugang(user):
    """True wenn User Staff oder Teamleiter eines Facility-Teams ist."""
    if user.is_staff:
        return True
    return FacilityTeam.objects.filter(teamleiter=user).exists()


# ---------------------------------------------------------------------------
# Melder-seitige Views
# ---------------------------------------------------------------------------


@login_required
def stoermeldung_erstellen(request):
    """Formular zum Erfassen einer Stoermeldung."""
    # Melder-Profil ermitteln
    try:
        melder = request.user.hr_mitarbeiter
    except Exception:
        melder = None

    fehler = {}
    formwerte = {}

    if request.method == "POST":
        formwerte = request.POST

        raumnummer = request.POST.get("raumnummer", "").strip()
        melder_telefon = request.POST.get("melder_telefon", "").strip()
        kategorie = request.POST.get("kategorie", "").strip()
        textbaustein_id = request.POST.get("textbaustein", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        raum_freitext = request.POST.get("raum_freitext", "").strip()
        prioritaet = request.POST.get("prioritaet", "normal").strip()

        if not raumnummer:
            fehler["raumnummer"] = "Bitte Raumnummer angeben."
        if not melder_telefon:
            fehler["melder_telefon"] = "Bitte Telefonnummer angeben."
        if not kategorie:
            fehler["kategorie"] = "Bitte Kategorie waehlen."
        if not melder:
            fehler["melder"] = "Kein HR-Mitarbeiterprofil gefunden. Bitte Administrator kontaktieren."

        if not fehler:
            textbaustein = None
            if textbaustein_id:
                try:
                    textbaustein = Textbaustein.objects.get(pk=int(textbaustein_id))
                except (Textbaustein.DoesNotExist, ValueError):
                    pass

            meldung = Stoermeldung.objects.create(
                melder=melder,
                melder_telefon=melder_telefon,
                raumnummer=raumnummer,
                raum_freitext=raum_freitext,
                kategorie=kategorie,
                textbaustein=textbaustein,
                beschreibung=beschreibung,
                prioritaet=prioritaet,
            )
            logger.info("Stoermeldung %s erstellt von User %s", meldung.pk, request.user)
            # Workflow-Trigger: Meldung in die richtige Team-Queue einreihen
            _starte_facility_workflow(meldung, request.user)
            return redirect("facility:erfolg", pk=meldung.pk)

    # Aktive Textbausteine zur Vorauswahl (leer, Laden per HTMX)
    kategorien = [
        {"wert": k, "label": v}
        for k, v in Stoermeldung._meta.get_field("kategorie").choices
    ]
    prioritaeten = Stoermeldung.PRIORITAET_CHOICES

    return render(
        request,
        "facility/stoermeldung_erstellen.html",
        {
            "fehler": fehler,
            "formwerte": formwerte,
            "kategorien": kategorien,
            "prioritaeten": prioritaeten,
            "melder": melder,
        },
    )


@login_required
def stoermeldung_erfolg(request, pk):
    """Erfolgsseite nach Abschicken einer Stoermeldung."""
    meldung = get_object_or_404(Stoermeldung, pk=pk)
    # Zugriff: nur Melder oder Staff
    if meldung.melder.user != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    return render(request, "facility/stoermeldung_erfolg.html", {"meldung": meldung})


@login_required
def stoermeldung_detail(request, pk):
    """Detailansicht einer Stoermeldung."""
    meldung = get_object_or_404(Stoermeldung, pk=pk)
    # Zugriff: Melder, Facility-Team-Mitglied oder Staff
    ist_melder = meldung.melder.user == request.user
    if not ist_melder and not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    return render(
        request,
        "facility/stoermeldung_detail.html",
        {
            "meldung": meldung,
            "ist_melder": ist_melder,
            "hat_facility_zugang": _hat_facility_zugang(request.user),
        },
    )


@login_required
def meine_stoermeldungen(request):
    """Liste der eigenen Stoermeldungen."""
    try:
        melder = request.user.hr_mitarbeiter
        meldungen = Stoermeldung.objects.filter(melder=melder).order_by("-erstellt_am")
    except Exception:
        meldungen = Stoermeldung.objects.none()
        melder = None
    return render(
        request,
        "facility/meine_stoermeldungen.html",
        {"meldungen": meldungen, "melder": melder},
    )


# ---------------------------------------------------------------------------
# HTMX-Partial
# ---------------------------------------------------------------------------


@login_required
def textbausteine_laden(request):
    """HTMX-View: Gibt Textbaustein-Optionen fuer eine Kategorie zurueck."""
    kategorie = request.GET.get("kategorie", "")
    bausteine = Textbaustein.objects.filter(
        kategorie=kategorie, ist_aktiv=True
    )
    return render(
        request,
        "facility/partials/_textbausteine.html",
        {"bausteine": bausteine},
    )


# ---------------------------------------------------------------------------
# Facility-Queue (Team-Bearbeitung)
# ---------------------------------------------------------------------------


@login_required
def facility_queue(request):
    """Facility-Team-Queue mit 4 Tabs."""
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()

    user_teams = _get_user_teams(request.user)
    kategorien = (
        list(user_teams.values_list("kategorie", flat=True))
        if not request.user.is_staff
        else None
    )

    qs = Stoermeldung.objects.all()
    if kategorien is not None:
        qs = qs.filter(kategorie__in=kategorien)

    vor_30_tagen = timezone.now() - timedelta(days=30)

    offene = qs.filter(status="offen").order_by("-prioritaet", "erstellt_am")
    meine = qs.filter(status="in_bearbeitung", claimed_von=request.user)
    team_in_bearbeitung = qs.filter(status="in_bearbeitung").exclude(
        claimed_von=request.user
    )
    erledigt = qs.filter(
        status__in=["erledigt", "unloesbar"],
        bearbeitet_am__gte=vor_30_tagen,
    ).order_by("-bearbeitet_am")

    return render(
        request,
        "facility/facility_queue.html",
        {
            "offene": offene,
            "meine": meine,
            "team_in_bearbeitung": team_in_bearbeitung,
            "erledigt": erledigt,
        },
    )


@login_required
def stoermeldung_claimen(request, pk):
    """Stoermeldung in eigene Bearbeitung uebernehmen (POST)."""
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    if request.method != "POST":
        return redirect("facility:queue")

    meldung = get_object_or_404(Stoermeldung, pk=pk, status="offen")
    meldung.claimed_von = request.user
    meldung.claimed_am = timezone.now()
    meldung.status = "in_bearbeitung"
    meldung.save()
    logger.info("Stoermeldung %s geclaimed von User %s", pk, request.user)
    messages.success(request, f"Stoermeldung {meldung.get_betreff()} wurde uebernommen.")
    return redirect("facility:queue")


@login_required
def stoermeldung_freigeben(request, pk):
    """Stoermeldung zurueck in den offenen Pool (POST)."""
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    if request.method != "POST":
        return redirect("facility:queue")

    meldung = get_object_or_404(Stoermeldung, pk=pk, status="in_bearbeitung")
    # Nur der Claimer oder Staff darf freigeben
    if meldung.claimed_von != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    meldung.claimed_von = None
    meldung.claimed_am = None
    meldung.status = "offen"
    meldung.save()
    logger.info("Stoermeldung %s freigegeben von User %s", pk, request.user)
    messages.info(request, f"Stoermeldung {meldung.get_betreff()} wurde freigegeben.")
    return redirect("facility:queue")


@login_required
def stoermeldung_erledigen(request, pk):
    """Stoermeldung als erledigt markieren mit Kommentar (POST)."""
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    if request.method != "POST":
        return redirect("facility:queue")

    meldung = get_object_or_404(Stoermeldung, pk=pk, status="in_bearbeitung")
    if meldung.claimed_von != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    kommentar = request.POST.get("kommentar", "").strip()
    meldung.status = "erledigt"
    meldung.bearbeitet_von = request.user
    meldung.bearbeitet_am = timezone.now()
    meldung.erledigungs_kommentar = kommentar
    meldung.save()
    logger.info("Stoermeldung %s erledigt von User %s", pk, request.user)
    # WorkflowTask im Arbeitsstapel ebenfalls abschliessen
    _schliesse_facility_workflow_task(meldung, request.user, kommentar)
    messages.success(request, f"Stoermeldung {meldung.get_betreff()} wurde als erledigt markiert.")
    return redirect("facility:queue")


@login_required
def stoermeldung_unloesbar(request, pk):
    """Stoermeldung als unloesbar / eskaliert markieren (POST)."""
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    if request.method != "POST":
        return redirect("facility:queue")

    meldung = get_object_or_404(Stoermeldung, pk=pk, status="in_bearbeitung")
    if meldung.claimed_von != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    kommentar = request.POST.get("kommentar", "").strip()
    meldung.status = "unloesbar"
    meldung.bearbeitet_von = request.user
    meldung.bearbeitet_am = timezone.now()
    meldung.erledigungs_kommentar = kommentar
    meldung.save()
    logger.info("Stoermeldung %s als unloesbar markiert von User %s", pk, request.user)
    # WorkflowTask im Arbeitsstapel ebenfalls abschliessen
    _schliesse_facility_workflow_task(meldung, request.user, kommentar)
    messages.warning(request, f"Stoermeldung {meldung.get_betreff()} wurde als unloesbar eskaliert.")
    return redirect("facility:queue")


# ---------------------------------------------------------------------------
# Textbaustein-Verwaltung
# ---------------------------------------------------------------------------


@login_required
def textbaustein_liste(request):
    """Uebersicht aller Textbausteine gruppiert nach Kategorie."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()

    bausteine = Textbaustein.objects.all().order_by("kategorie", "reihenfolge", "text")
    # Gruppierung nach Kategorie
    gruppen = {}
    for b in bausteine:
        label = b.get_kategorie_display()
        gruppen.setdefault(label, []).append(b)

    return render(
        request,
        "facility/textbaustein_liste.html",
        {"gruppen": gruppen},
    )


@login_required
def textbaustein_erstellen(request):
    """Neuen Textbaustein anlegen."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()

    fehler = {}
    formwerte = {}
    kategorien = KATEGORIE_CHOICES_DISPLAY

    if request.method == "POST":
        formwerte = request.POST
        kategorie = request.POST.get("kategorie", "").strip()
        text = request.POST.get("text", "").strip()
        reihenfolge = request.POST.get("reihenfolge", "0").strip()
        ist_aktiv = "ist_aktiv" in request.POST

        if not kategorie:
            fehler["kategorie"] = "Bitte Kategorie waehlen."
        if not text:
            fehler["text"] = "Bitte Text eingeben."

        try:
            reihenfolge_int = int(reihenfolge)
        except ValueError:
            reihenfolge_int = 0
            fehler["reihenfolge"] = "Bitte eine Zahl eingeben."

        if not fehler:
            Textbaustein.objects.create(
                kategorie=kategorie,
                text=text,
                reihenfolge=reihenfolge_int,
                ist_aktiv=ist_aktiv,
            )
            messages.success(request, "Textbaustein wurde angelegt.")
            return redirect("facility:textbaustein_liste")

    return render(
        request,
        "facility/textbaustein_form.html",
        {
            "fehler": fehler,
            "formwerte": formwerte,
            "kategorien": kategorien,
            "aktion": "Neu anlegen",
        },
    )


@login_required
def textbaustein_bearbeiten(request, pk):
    """Bestehenden Textbaustein bearbeiten."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()

    baustein = get_object_or_404(Textbaustein, pk=pk)
    fehler = {}
    kategorien = KATEGORIE_CHOICES_DISPLAY

    if request.method == "POST":
        kategorie = request.POST.get("kategorie", "").strip()
        text = request.POST.get("text", "").strip()
        reihenfolge = request.POST.get("reihenfolge", "0").strip()
        ist_aktiv = "ist_aktiv" in request.POST

        if not kategorie:
            fehler["kategorie"] = "Bitte Kategorie waehlen."
        if not text:
            fehler["text"] = "Bitte Text eingeben."

        try:
            reihenfolge_int = int(reihenfolge)
        except ValueError:
            reihenfolge_int = 0
            fehler["reihenfolge"] = "Bitte eine Zahl eingeben."

        if not fehler:
            baustein.kategorie = kategorie
            baustein.text = text
            baustein.reihenfolge = reihenfolge_int
            baustein.ist_aktiv = ist_aktiv
            baustein.save()
            messages.success(request, "Textbaustein wurde gespeichert.")
            return redirect("facility:textbaustein_liste")

        formwerte = request.POST
    else:
        formwerte = {
            "kategorie": baustein.kategorie,
            "text": baustein.text,
            "reihenfolge": baustein.reihenfolge,
            "ist_aktiv": baustein.ist_aktiv,
        }

    return render(
        request,
        "facility/textbaustein_form.html",
        {
            "fehler": fehler,
            "formwerte": formwerte,
            "kategorien": kategorien,
            "baustein": baustein,
            "aktion": "Bearbeiten",
        },
    )


@login_required
def facility_workflow_anleitung(request):
    """Anleitung zum Einrichten der Facility-Workflows im Workflow-Editor."""
    if not request.user.is_staff:
        return HttpResponseForbidden()
    return render(request, "facility/workflow_anleitung.html")


@login_required
def textbaustein_loeschen(request, pk):
    """Textbaustein loeschen (POST mit Bestaetigung)."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()

    baustein = get_object_or_404(Textbaustein, pk=pk)

    if request.method == "POST":
        baustein.delete()
        messages.success(request, "Textbaustein wurde geloescht.")
        return redirect("facility:textbaustein_liste")

    return render(
        request,
        "facility/textbaustein_loeschen.html",
        {"baustein": baustein},
    )


# ---------------------------------------------------------------------------
# FacilityTeam – Member-Management (JSON-API fuer Team-Builder)
# ---------------------------------------------------------------------------

@login_required
def facility_team_mitglied_hinzufuegen(request, pk):
    """API: Mitglied zum FacilityTeam hinzufuegen (JSON POST)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Kein Zugriff"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from django.contrib.auth import get_user_model
    User = get_user_model()

    team = get_object_or_404(FacilityTeam, pk=pk)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        if not user_id:
            return JsonResponse({"error": "User-ID erforderlich"}, status=400)
        user = get_object_or_404(User, pk=user_id)
        if team.mitglieder.filter(id=user.id).exists():
            return JsonResponse({"error": "User ist bereits Mitglied"}, status=400)
        team.mitglieder.add(user)
        return JsonResponse({
            "success": True,
            "message": f"{user.username} zu '{team.get_kategorie_display()}' hinzugefuegt",
        })
    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def facility_team_mitglied_entfernen(request, pk):
    """API: Mitglied aus FacilityTeam entfernen (JSON POST)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Kein Zugriff"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from django.contrib.auth import get_user_model
    User = get_user_model()

    team = get_object_or_404(FacilityTeam, pk=pk)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        if not user_id:
            return JsonResponse({"error": "User-ID erforderlich"}, status=400)
        user = get_object_or_404(User, pk=user_id)
        team.mitglieder.remove(user)
        return JsonResponse({
            "success": True,
            "message": f"{user.username} aus '{team.get_kategorie_display()}' entfernt",
        })
    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
