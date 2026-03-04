import calendar
import json
import logging
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    KATEGORIE_CHOICES,
    FacilityEinstellungen,
    FacilityTeam,
    Stoermeldung,
    Textbaustein,
    Wartungsplan,
)

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


def _get_abteilungsleiter(bearbeiter_user):
    """Ermittelt den Abteilungsleiter fuer einen Bearbeiter.

    Prioritaet:
    1. FacilityTeam.teamleiter des Teams, dem der User angehoert
    2. HR-Vorgesetzter des Users
    """
    team = FacilityTeam.objects.filter(mitglieder=bearbeiter_user).first()
    if team and team.teamleiter:
        return team.teamleiter
    try:
        vg = bearbeiter_user.hr_mitarbeiter.vorgesetzter
        if vg and vg.user:
            return vg.user
    except Exception:
        pass
    return None


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


def _get_direkte_berichte(user):
    """Gibt HRMitarbeiter-Queryset der direkten Berichte zurueck (leer wenn kein Vorgesetzter)."""
    try:
        ma = user.hr_mitarbeiter
        return ma.direkte_berichte.all()
    except Exception:
        return None


def _ist_vorgesetzter_von(user, melder):
    """True wenn user direkter Vorgesetzter des Melders ist."""
    try:
        ma = user.hr_mitarbeiter
        return melder.vorgesetzter_id == ma.pk
    except Exception:
        return False


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
    # Zugriff: Melder, Facility-Team-Mitglied, Vorgesetzter des Melders oder Staff
    ist_melder = meldung.melder.user == request.user
    ist_vorgesetzter = _ist_vorgesetzter_von(request.user, meldung.melder)
    if (
        not ist_melder
        and not ist_vorgesetzter
        and not _hat_facility_zugang(request.user)
        and not _hat_al_zugang(request.user)
    ):
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


def _pruefe_faellige_wartungen(kategorien=None):
    """Erzeugt Stoermeldungen fuer faellige Wartungsplaene (ohne Duplikate).

    Wird beim Oeffnen der Facility-Queue aufgerufen.
    kategorien: Liste von Kategorie-Strings oder None (= alle).
    Gibt Anzahl neu erzeugter Meldungen zurueck.
    """
    from datetime import date as _date
    from hr.models import HRMitarbeiter

    # System-Platzhalter: erster aktiver HR-Mitarbeiter als Melder fuer Wartungsaufgaben
    system_melder = HRMitarbeiter.objects.filter(
        user__is_active=True
    ).order_by("pk").first()
    if not system_melder:
        logger.warning("Kein HR-Mitarbeiter fuer Wartungs-Ausloesung gefunden.")
        return 0

    qs = Wartungsplan.objects.filter(
        ist_aktiv=True,
        naechste_faelligkeit__lte=_date.today(),
    )
    if kategorien:
        qs = qs.filter(kategorie__in=kategorien)

    neu = 0
    for plan in qs:
        if plan.hat_offene_aufgabe():
            continue  # Duplikat vermeiden
        Stoermeldung.objects.create(
            melder=system_melder,
            melder_telefon="-",
            raumnummer=plan.raumnummer,
            raum_freitext=plan.raum_freitext,
            kategorie=plan.kategorie,
            beschreibung=f"Wartung: {plan.name}\n{plan.beschreibung}".strip(),
            prioritaet=plan.prioritaet,
            ist_wartung=True,
            wartungsplan=plan,
        )
        logger.info("Wartungsaufgabe ausgeloest: Wartungsplan %s (%s)", plan.pk, plan.name)
        neu += 1
    return neu


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

    # Faellige Wartungsplaene automatisch in Queue einstellen
    neu_erzeugt = _pruefe_faellige_wartungen(kategorien)
    if neu_erzeugt:
        messages.info(request, f"{neu_erzeugt} neue Wartungsaufgabe(n) automatisch eingestellt.")

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

    from datetime import date as _date
    kommentar = request.POST.get("kommentar", "").strip()
    meldung.status = "erledigt"
    meldung.bearbeitet_von = request.user
    meldung.bearbeitet_am = timezone.now()
    meldung.erledigungs_kommentar = kommentar
    meldung.save()
    logger.info("Stoermeldung %s erledigt von User %s", pk, request.user)

    # Wartungsplan: naechste Faelligkeit neu berechnen
    if meldung.ist_wartung and meldung.wartungsplan:
        plan = meldung.wartungsplan
        plan.letzte_ausfuehrung = _date.today()
        plan.naechste_faelligkeit = plan.berechne_naechste_faelligkeit(basis=_date.today())
        plan.save(update_fields=["letzte_ausfuehrung", "naechste_faelligkeit"])
        logger.info("Wartungsplan %s: naechste Faelligkeit %s", plan.pk, plan.naechste_faelligkeit)

    # WorkflowTask im Arbeitsstapel ebenfalls abschliessen
    _schliesse_facility_workflow_task(meldung, request.user, kommentar)
    messages.success(request, f"Stoermeldung {meldung.get_betreff()} wurde als erledigt markiert.")
    return redirect("facility:queue")


@login_required
def stoermeldung_weiterleiten(request, pk):
    """Stoermeldung an Abteilungsleiter weiterleiten (POST).

    Setzt Status auf 'weitergeleitet' und speichert Typ + Kommentar.
    Zugriff: Bearbeiter (claimed_von) oder Staff.
    """
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    if request.method != "POST":
        return redirect("facility:queue")

    meldung = get_object_or_404(Stoermeldung, pk=pk, status="in_bearbeitung")
    if meldung.claimed_von != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    eskalation_typ = request.POST.get("eskalation_typ", "").strip()
    eskalation_kommentar = request.POST.get("eskalation_kommentar", "").strip()

    if not eskalation_typ or not eskalation_kommentar:
        messages.error(request, "Typ und Kommentar sind Pflichtfelder.")
        return redirect("facility:queue")

    al = _get_abteilungsleiter(request.user)
    if not al:
        messages.error(
            request,
            "Kein Abteilungsleiter gefunden. Bitte Administrator kontaktieren.",
        )
        return redirect("facility:queue")

    meldung.status = "weitergeleitet"
    meldung.eskaliert_an = al
    meldung.eskaliert_am = timezone.now()
    meldung.eskalation_typ = eskalation_typ
    meldung.eskalation_kommentar = eskalation_kommentar
    meldung.save()
    logger.info(
        "Stoermeldung %s weitergeleitet von %s an %s",
        pk,
        request.user,
        al,
    )
    messages.success(
        request,
        f"Stoermeldung {meldung.get_betreff()} wurde an {al.get_full_name() or al.username} weitergeleitet.",
    )
    return redirect("facility:queue")


def _hat_al_zugang(user):
    """True wenn User als Abteilungsleiter gilt: Teamleiter, HR-Vorgesetzter oder Staff."""
    if user.is_staff:
        return True
    if FacilityTeam.objects.filter(teamleiter=user).exists():
        return True
    try:
        return user.hr_mitarbeiter.direkte_berichte.exists()
    except Exception:
        return False


@login_required
def al_queue(request):
    """AL-Eingang: Uebersicht der weitergeleiteten Stoermeldungen.

    Staff sieht alle; AL sieht nur die explizit an ihn weitergeleiteten.
    Zugang: FacilityTeam-Teamleiter, HR-Vorgesetzter oder Staff.
    """
    if not _hat_al_zugang(request.user):
        return HttpResponseForbidden()

    if request.user.is_staff:
        meldungen = Stoermeldung.objects.filter(status="weitergeleitet").order_by(
            "-eskaliert_am"
        )
    else:
        meldungen = Stoermeldung.objects.filter(
            status="weitergeleitet", eskaliert_an=request.user
        ).order_by("-eskaliert_am")

    return render(
        request,
        "facility/al_queue.html",
        {"meldungen": meldungen},
    )


@login_required
def al_antwort(request, pk):
    """AL antwortet auf eine weitergeleitete Stoermeldung (POST).

    aktion='zurueck' → Status 'in_bearbeitung' (zurueck ans Team)
    aktion='erledigt' → Status 'erledigt' (AL hat selbst erledigt)
    """
    if request.method != "POST":
        return redirect("facility:al_queue")

    meldung = get_object_or_404(Stoermeldung, pk=pk, status="weitergeleitet")
    # Nur der adressierte AL oder Staff darf antworten
    if meldung.eskaliert_an != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    aktion = request.POST.get("aktion", "").strip()
    antwort = request.POST.get("eskalation_antwort", "").strip()
    meldung.eskalation_antwort = antwort

    if aktion == "zurueck":
        meldung.status = "in_bearbeitung"
        meldung.save()
        logger.info(
            "Stoermeldung %s vom AL %s zurueck ans Team gegeben.", pk, request.user
        )
        messages.info(
            request,
            f"Stoermeldung {meldung.get_betreff()} wurde zurueck ans Team gegeben.",
        )
    elif aktion == "erledigt":
        meldung.status = "erledigt"
        meldung.bearbeitet_von = request.user
        meldung.bearbeitet_am = timezone.now()
        meldung.save()
        _schliesse_facility_workflow_task(meldung, request.user, antwort)
        logger.info(
            "Stoermeldung %s vom AL %s als erledigt markiert.", pk, request.user
        )
        messages.success(
            request,
            f"Stoermeldung {meldung.get_betreff()} wurde als erledigt markiert.",
        )
    else:
        messages.error(request, "Unbekannte Aktion.")

    return redirect("facility:al_queue")


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
# Wartungsplan CRUD
# ---------------------------------------------------------------------------

@login_required
def wartungsplan_liste(request):
    """Uebersicht aller Wartungsplaene."""
    if not _hat_facility_zugang(request.user):
        return HttpResponseForbidden()
    plaene = Wartungsplan.objects.all().order_by("naechste_faelligkeit")
    return render(request, "facility/wartungsplan_liste.html", {"plaene": plaene})


@login_required
def wartungsplan_erstellen(request):
    """Neuen Wartungsplan anlegen."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()

    fehler = {}
    daten = {}

    if request.method == "POST":
        daten = request.POST
        fehler = _wartungsplan_validieren(daten)
        if not fehler:
            from datetime import date as _date
            intervall_wert = int(daten["intervall_wert"])
            intervall_einheit = daten["intervall_einheit"]
            # Erste Faelligkeit aus dem eingegebenen Startdatum
            start = _date.fromisoformat(daten["naechste_faelligkeit"])
            plan = Wartungsplan(
                name=daten["name"].strip(),
                beschreibung=daten.get("beschreibung", "").strip(),
                kategorie=daten["kategorie"],
                raumnummer=daten["raumnummer"].strip(),
                raum_freitext=daten.get("raum_freitext", "").strip(),
                prioritaet=daten.get("prioritaet", "normal"),
                intervall_wert=intervall_wert,
                intervall_einheit=intervall_einheit,
                naechste_faelligkeit=start,
                ist_aktiv=True,
                erstellt_von=request.user,
            )
            plan.save()
            messages.success(request, f"Wartungsplan '{plan.name}' wurde angelegt.")
            return redirect("facility:wartungsplan_liste")

    return render(request, "facility/wartungsplan_form.html", {
        "daten": daten,
        "fehler": fehler,
        "KATEGORIE_CHOICES": KATEGORIE_CHOICES,
        "titel": "Neuer Wartungsplan",
        "aktion": "Anlegen",
    })


@login_required
def wartungsplan_bearbeiten(request, pk):
    """Vorhandenen Wartungsplan bearbeiten."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()

    plan = get_object_or_404(Wartungsplan, pk=pk)
    fehler = {}

    if request.method == "POST":
        daten = request.POST
        fehler = _wartungsplan_validieren(daten)
        if not fehler:
            from datetime import date as _date
            plan.name = daten["name"].strip()
            plan.beschreibung = daten.get("beschreibung", "").strip()
            plan.kategorie = daten["kategorie"]
            plan.raumnummer = daten["raumnummer"].strip()
            plan.raum_freitext = daten.get("raum_freitext", "").strip()
            plan.prioritaet = daten.get("prioritaet", "normal")
            plan.intervall_wert = int(daten["intervall_wert"])
            plan.intervall_einheit = daten["intervall_einheit"]
            plan.naechste_faelligkeit = _date.fromisoformat(daten["naechste_faelligkeit"])
            plan.ist_aktiv = "ist_aktiv" in daten
            plan.save()
            messages.success(request, f"Wartungsplan '{plan.name}' wurde gespeichert.")
            return redirect("facility:wartungsplan_liste")
        daten = request.POST
    else:
        daten = {
            "name": plan.name,
            "beschreibung": plan.beschreibung,
            "kategorie": plan.kategorie,
            "raumnummer": plan.raumnummer,
            "raum_freitext": plan.raum_freitext,
            "prioritaet": plan.prioritaet,
            "intervall_wert": plan.intervall_wert,
            "intervall_einheit": plan.intervall_einheit,
            "naechste_faelligkeit": plan.naechste_faelligkeit.isoformat(),
            "ist_aktiv": plan.ist_aktiv,
        }

    return render(request, "facility/wartungsplan_form.html", {
        "plan": plan,
        "daten": daten,
        "fehler": fehler,
        "KATEGORIE_CHOICES": KATEGORIE_CHOICES,
        "titel": f"Wartungsplan bearbeiten – {plan.name}",
        "aktion": "Speichern",
    })


@login_required
def wartungsplan_loeschen(request, pk):
    """Wartungsplan loeschen (POST mit Bestaetigung)."""
    if not _hat_textbaustein_zugang(request.user):
        return HttpResponseForbidden()
    plan = get_object_or_404(Wartungsplan, pk=pk)
    if request.method == "POST":
        name = plan.name
        plan.delete()
        messages.success(request, f"Wartungsplan '{name}' wurde geloescht.")
        return redirect("facility:wartungsplan_liste")
    return render(request, "facility/wartungsplan_loeschen.html", {"plan": plan})


def _wartungsplan_validieren(daten) -> dict:
    """Validiert POST-Daten fuer Wartungsplan. Gibt Fehler-Dict zurueck."""
    fehler = {}
    if not daten.get("name", "").strip():
        fehler["name"] = "Bezeichnung ist Pflicht."
    if not daten.get("kategorie"):
        fehler["kategorie"] = "Kategorie ist Pflicht."
    if not daten.get("raumnummer", "").strip():
        fehler["raumnummer"] = "Raumnummer ist Pflicht."
    try:
        wert = int(daten.get("intervall_wert", 0))
        if wert <= 0:
            raise ValueError
    except (ValueError, TypeError):
        fehler["intervall_wert"] = "Intervall muss eine positive Zahl sein."
    if daten.get("intervall_einheit") not in ("tage", "wochen", "monate"):
        fehler["intervall_einheit"] = "Ungueltige Einheit."
    if not daten.get("naechste_faelligkeit"):
        fehler["naechste_faelligkeit"] = "Erste Faelligkeit ist Pflicht."
    else:
        try:
            from datetime import date as _date
            _date.fromisoformat(daten["naechste_faelligkeit"])
        except ValueError:
            fehler["naechste_faelligkeit"] = "Ungueliges Datumsformat."
    return fehler


@login_required
def vorgesetzter_stoermeldungen(request):
    """Gesamtuebersicht aller Stoermeldungen fuer Abteilungsleiter.

    Zeigt ALLE Stoermeldungen im System – nicht nur die eigener Berichte.
    Zugang: User mit direkten Berichten (ist_vorgesetzter) oder Staff.
    """
    if not _hat_al_zugang(request.user):
        return HttpResponseForbidden()

    basis = Stoermeldung.objects.select_related(
        "melder", "melder__user", "claimed_von"
    )

    # Offen: alles was noch nicht abgeschlossen ist
    offen = basis.filter(
        status__in=["offen", "in_bearbeitung", "weitergeleitet"]
    ).order_by("-prioritaet", "erstellt_am")

    # Abgeschlossen: erledigt oder unloesbar
    erledigt = basis.filter(
        status__in=["erledigt", "unloesbar"]
    ).order_by("-bearbeitet_am")

    return render(
        request,
        "facility/vorgesetzter_stoermeldungen.html",
        {
            "offen": offen,
            "erledigt": erledigt,
        },
    )


# ---------------------------------------------------------------------------
# AL-Monatsreport
# ---------------------------------------------------------------------------

# Standardwerte (werden durch FacilityEinstellungen aus der DB ueberschrieben)
TREND_SCHWELLE_DEFAULT = 3
TREND_TAGE_DEFAULT = 90

# Monatsnamen ohne Umlaute fuer Python-Strings
MONATE_DE = {
    1: "Januar", 2: "Februar", 3: "Maerz", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}


@login_required
def al_monatsreport(request):
    """Monatsbericht fuer den Abteilungsleiter.

    Zeigt Zusammenfassung, Kategorieverteilung, Top-Raeume und
    Tendenz-Erkennung (wiederkehrende Stoerungen am selben Ort).
    Zugang: ALs und Staff.
    """
    from django.db.models import Count

    if not _hat_al_zugang(request.user):
        return HttpResponseForbidden()

    # --- Einstellungen aus DB laden ---
    einstellungen = FacilityEinstellungen.laden()
    TREND_SCHWELLE = einstellungen.trend_schwelle
    TREND_TAGE = einstellungen.trend_tage

    # --- Zeitraum bestimmen ---
    heute = date.today()
    monat_str = request.GET.get("monat", f"{heute.year}-{heute.month:02d}")
    try:
        teile = monat_str.split("-")
        jahr = int(teile[0])
        monat = int(teile[1])
        if not (1 <= monat <= 12):
            raise ValueError
    except (ValueError, IndexError, AttributeError):
        jahr, monat = heute.year, heute.month
        monat_str = f"{jahr}-{monat:02d}"

    letzter_tag = calendar.monthrange(jahr, monat)[1]
    von = timezone.make_aware(datetime(jahr, monat, 1, 0, 0, 0))
    bis = timezone.make_aware(datetime(jahr, monat, letzter_tag, 23, 59, 59))

    qs = Stoermeldung.objects.filter(erstellt_am__range=(von, bis))
    gesamt = qs.count()

    offen_count = qs.filter(
        status__in=["offen", "in_bearbeitung", "weitergeleitet"]
    ).count()
    erledigt_count = qs.filter(status="erledigt").count()
    unloesbar_count = qs.filter(status="unloesbar").count()

    # --- Durchschnittliche Bearbeitungszeit (Stunden) ---
    avg_stunden = None
    erledigte = list(
        qs.filter(status="erledigt", bearbeitet_am__isnull=False).values_list(
            "erstellt_am", "bearbeitet_am"
        )
    )
    if erledigte:
        zeiten = [
            (bearbeitet - erstellt).total_seconds() / 3600
            for erstellt, bearbeitet in erledigte
        ]
        avg_stunden = round(sum(zeiten) / len(zeiten), 1)

    # --- Nach Kategorie ---
    kategorie_label = dict(KATEGORIE_CHOICES)
    nach_kategorie_raw = (
        qs.values("kategorie")
        .annotate(anzahl=Count("pk"))
        .order_by("-anzahl")
    )
    nach_kategorie = []
    for eintrag in nach_kategorie_raw:
        anteil = round(eintrag["anzahl"] / gesamt * 100) if gesamt else 0
        nach_kategorie.append({
            "label": kategorie_label.get(eintrag["kategorie"], eintrag["kategorie"]),
            "anzahl": eintrag["anzahl"],
            "anteil": anteil,
        })

    # --- Top-Raeume (raumnummer + kategorie, Top 10) ---
    top_raeume_raw = (
        qs.values("raumnummer", "kategorie")
        .annotate(anzahl=Count("pk"))
        .order_by("-anzahl")[:10]
    )
    top_raeume = [
        {
            "raum": r["raumnummer"],
            "kategorie": kategorie_label.get(r["kategorie"], r["kategorie"]),
            "anzahl": r["anzahl"],
        }
        for r in top_raeume_raw
    ]

    # --- Tendenz-Erkennung: gleicher Raum + Kategorie >= TREND_SCHWELLE in TREND_TAGE ---
    grenze = timezone.now() - timedelta(days=TREND_TAGE)
    tendenzen_raw = (
        Stoermeldung.objects.filter(erstellt_am__gte=grenze)
        .values("raumnummer", "kategorie")
        .annotate(anzahl=Count("pk"))
        .filter(anzahl__gte=TREND_SCHWELLE)
        .order_by("-anzahl")
    )
    tendenzen = [
        {
            "raum": t["raumnummer"],
            "kategorie": kategorie_label.get(t["kategorie"], t["kategorie"]),
            "anzahl": t["anzahl"],
        }
        for t in tendenzen_raw
    ]

    # --- Monatsauswahl (letzte 12 Monate) ---
    monate_auswahl = []
    for i in range(12):
        j = heute.year
        m = heute.month - i
        while m <= 0:
            m += 12
            j -= 1
        monate_auswahl.append({
            "wert": f"{j}-{m:02d}",
            "label": f"{MONATE_DE[m]} {j}",
            "aktiv": (j == jahr and m == monat),
        })

    return render(
        request,
        "facility/al_monatsreport.html",
        {
            "monat": monat,
            "jahr": jahr,
            "monat_str": monat_str,
            "monat_label": MONATE_DE[monat],
            "gesamt": gesamt,
            "offen_count": offen_count,
            "erledigt_count": erledigt_count,
            "unloesbar_count": unloesbar_count,
            "avg_stunden": avg_stunden,
            "nach_kategorie": nach_kategorie,
            "top_raeume": top_raeume,
            "tendenzen": tendenzen,
            "monate_auswahl": monate_auswahl,
            "TREND_SCHWELLE": TREND_SCHWELLE,
            "TREND_TAGE": TREND_TAGE,
        },
    )


# ---------------------------------------------------------------------------
# Facility-Einstellungen (Trend-Konfiguration)
# ---------------------------------------------------------------------------


@login_required
def facility_einstellungen(request):
    """UI fuer den Abteilungsleiter: Trend-Einstellungen anpassen."""
    if not _hat_al_zugang(request.user):
        return HttpResponseForbidden()

    einstellungen = FacilityEinstellungen.laden()
    fehler = {}

    if request.method == "POST":
        schwelle_str = request.POST.get("trend_schwelle", "").strip()
        tage_str = request.POST.get("trend_tage", "").strip()

        try:
            schwelle = int(schwelle_str)
            if schwelle < 2:
                fehler["trend_schwelle"] = "Mindestens 2 Meldungen erforderlich."
        except ValueError:
            fehler["trend_schwelle"] = "Bitte eine ganze Zahl eingeben."
            schwelle = einstellungen.trend_schwelle

        try:
            tage = int(tage_str)
            if tage < 7:
                fehler["trend_tage"] = "Mindestens 7 Tage erforderlich."
        except ValueError:
            fehler["trend_tage"] = "Bitte eine ganze Zahl eingeben."
            tage = einstellungen.trend_tage

        if not fehler:
            einstellungen.trend_schwelle = schwelle
            einstellungen.trend_tage = tage
            einstellungen.save()
            logger.info(
                "Facility-Einstellungen geaendert von %s: Schwelle=%s, Tage=%s",
                request.user,
                schwelle,
                tage,
            )
            messages.success(request, "Einstellungen wurden gespeichert.")
            return redirect("facility:einstellungen")

    # Schnellauswahl-Vorschlaege fuer den Beobachtungszeitraum
    zeitraum_vorschlaege = [
        {"tage": 30, "label": "1 Monat"},
        {"tage": 60, "label": "2 Monate"},
        {"tage": 90, "label": "1 Quartal"},
        {"tage": 180, "label": "Halbjahr"},
        {"tage": 365, "label": "1 Jahr"},
    ]

    return render(
        request,
        "facility/facility_einstellungen.html",
        {
            "einstellungen": einstellungen,
            "fehler": fehler,
            "zeitraum_vorschlaege": zeitraum_vorschlaege,
        },
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
