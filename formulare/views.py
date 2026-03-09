import json
import logging
import uuid
from datetime import date as date_type, timedelta
from itertools import chain
from operator import attrgetter

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string

from arbeitszeit.models import (
    Arbeitszeitvereinbarung,
    Tagesarbeitszeit,
    Zeiterfassung,
    get_feiertagskalender,
)
from formulare.forms import (
    AenderungZeiterfassungForm,
    DienstreiseantragForm,
    ZeitgutschriftForm,
)
from formulare.models import (
    AenderungZeiterfassung,
    Dienstreiseantrag,
    ReisezeitTagebuchEintrag,
    TeamQueue,
    ZAGAntrag,
    ZAGStorno,
    Zeitgutschrift,
    ZeitgutschriftBeleg,
)

WOCHENTAG_MAP = {
    0: "montag",
    1: "dienstag",
    2: "mittwoch",
    3: "donnerstag",
    4: "freitag",
    5: "samstag",
    6: "sonntag",
}


def _starte_workflow_fuer_antrag(trigger_event, content_object, user):
    """Startet einen Workflow fuer einen neuen Antrag, falls ein aktives Template vorhanden ist.

    Sucht das erste aktive WorkflowTemplate mit passendem trigger_event und
    startet eine neue WorkflowInstance fuer das uebergebene Objekt.

    Args:
        trigger_event: String des Trigger-Events (z.B. 'zag_antrag_erstellt')
        content_object: Django-Model-Instanz (z.B. ZAGAntrag)
        user: Der ausloesendeUser (request.user)
    """
    from workflow.models import WorkflowTemplate
    from workflow.services import WorkflowEngine

    template = WorkflowTemplate.objects.filter(
        trigger_event=trigger_event,
        ist_aktiv=True,
    ).first()

    if not template:
        logger.debug(
            "Kein aktives Workflow-Template fuer trigger_event='%s' gefunden.",
            trigger_event,
        )
        return

    # Duplikat-Schutz: Kein zweiter Workflow fuer dasselbe Objekt + Template
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowInstance
    ct = ContentType.objects.get_for_model(content_object)
    bereits_vorhanden = WorkflowInstance.objects.filter(
        template=template,
        content_type=ct,
        object_id=content_object.pk,
        status__in=["laufend", "wartend"],
    ).exists()
    if bereits_vorhanden:
        logger.warning(
            "Workflow '%s' fuer %s pk=%s bereits vorhanden – wird nicht nochmals gestartet.",
            template.name,
            content_object.__class__.__name__,
            content_object.pk,
        )
        return

    try:
        WorkflowEngine().start_workflow(template, content_object, user)
        logger.info(
            "Workflow '%s' gestartet fuer %s pk=%s",
            template.name,
            content_object.__class__.__name__,
            content_object.pk,
        )
    except Exception as exc:
        logger.error(
            "Fehler beim Starten des Workflows '%s': %s",
            template.name,
            exc,
        )


def _signiere_pdf_sicher(pdf_bytes, user, dokument_name, **meta_kwargs):
    """Signiert ein PDF mit dem konfigurierten Backend (FES/QES).

    Gibt das signierte PDF zurueck. Falls kein Zertifikat vorhanden ist
    oder ein Fehler auftritt, wird das unsignierte PDF zurueckgegeben
    und eine Warnung geloggt.
    """
    try:
        from signatur.services import signiere_pdf
        return signiere_pdf(pdf_bytes, user, dokument_name=dokument_name, **meta_kwargs)
    except Exception as exc:
        logger.warning(
            "PDF-Signatur fehlgeschlagen fuer '%s' (User %s): %s – PDF wird unsigniert ausgeliefert.",
            dokument_name,
            user.username,
            exc,
        )
        return pdf_bytes


def _sammle_workflow_unterzeichner(antrag, antragsteller_user):
    """Gibt geordnete Liste aller Unterzeichner fuer ein Workflow-Antrag-PDF zurueck.

    Reihenfolge: Antragsteller zuerst, dann alle erledigten Workflow-Task-Bearbeiter
    in Schritt-Reihenfolge. Jeder User nur einmal (Duplikate werden entfernt).

    Verwendung in jedem mehrstufigen Workflow-PDF-View:
        unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
        for i, user in enumerate(unterzeichner):
            pdf_bytes = _signiere_pdf_sicher(pdf_bytes, user, dateiname)
    """
    unterzeichner = []
    if antragsteller_user:
        unterzeichner.append(antragsteller_user)

    try:
        instanz = getattr(antrag, "workflow_instance", None)
        if instanz:
            from workflow.models import WorkflowTask
            erledigte = (
                WorkflowTask.objects
                .filter(instance=instanz, status="erledigt")
                .select_related("erledigt_von", "step")
                .order_by("step__reihenfolge")
            )
            for task in erledigte:
                if task.erledigt_von and task.erledigt_von not in unterzeichner:
                    unterzeichner.append(task.erledigt_von)
    except Exception as exc:
        logger.warning("Workflow-Unterzeichner konnten nicht ermittelt werden: %s", exc)

    return unterzeichner


def _signiere_pdf_alle_unterzeichner(pdf_bytes, unterzeichner, dateiname):
    """Signiert ein PDF inkrementell fuer jeden Unterzeichner in der Liste.

    Gibt das (mehrfach-)signierte PDF zurueck. Einzelne Signatur-Fehler
    werden geloggt aber nicht weitergeworfen, damit das PDF immer ausgeliefert wird.
    """
    from signatur.services import signiere_pdf
    for i, user in enumerate(unterzeichner):
        try:
            pdf_bytes = signiere_pdf(
                pdf_bytes,
                user,
                dokument_name=dateiname,
            )
        except Exception as exc:
            logger.warning(
                "Signatur von %s fehlgeschlagen (Unterzeichner %s/%s, Dokument '%s'): %s",
                user.username, i + 1, len(unterzeichner), dateiname, exc,
            )
    return pdf_bytes


def _hole_antrag_signatur(content_type_str, object_id):
    """Gibt das SignaturProtokoll fuer einen Antrag zurueck (oder None)."""
    try:
        from signatur.models import SignaturJob
        job = SignaturJob.objects.filter(
            content_type=content_type_str,
            object_id=object_id,
            status="completed",
        ).order_by("-erstellt_am").first()
        return job.protokoll if job else None
    except Exception:
        return None


def _auto_signiere_antrag(antrag, request, content_type_str, pdf_template, extra_context=None):
    """Generisches Auto-Signatur-Pattern fuer alle Antragstypen.

    Rendert das PDF-Template, signiert es sofort und legt ein SignaturProtokoll an.
    Schlaegt still fehl – unterbricht nie die Formular-Einreichung.
    """
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        from signatur.services import signiere_pdf

        ctx = {"antrag": antrag, "betreff": antrag.get_betreff()}
        if extra_context:
            ctx.update(extra_context)

        html_string = render_to_string(pdf_template, ctx, request=request)
        pdf = HTML(
            string=html_string,
            base_url=request.build_absolute_uri(),
        ).write_pdf()
        dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
        signiere_pdf(
            pdf,
            antrag.antragsteller.user,
            dokument_name=dateiname,
            content_type=content_type_str,
            object_id=antrag.pk,
        )
        logger.info("Auto-Signatur OK: %s pk=%s", content_type_str, antrag.pk)
    except Exception as exc:
        logger.warning(
            "Auto-Signatur fehlgeschlagen: %s pk=%s – %s",
            content_type_str,
            antrag.pk,
            exc,
        )


def _auto_signiere_aenderungsantrag(antrag, request):
    """Aenderungsantrag nach Submit auto-signieren."""
    vereinbarung = _vereinbarung_fuer_mitarbeiter(
        antrag.antragsteller, antrag.erstellt_am.date()
    )
    _auto_signiere_antrag(
        antrag, request,
        content_type_str="aenderungzeiterfassung",
        pdf_template="formulare/pdf/aenderung_zeiterfassung_pdf.html",
        extra_context={"vereinbarung": vereinbarung},
    )


def _auto_signiere_zag(antrag, request):
    """ZAG-Antrag nach Submit auto-signieren."""
    _auto_signiere_antrag(
        antrag, request,
        content_type_str="zagantrag",
        pdf_template="formulare/pdf/zag_pdf.html",
        extra_context={"zag_daten_mit_tagen": [], "gesamt_tage": 0},
    )


def _auto_signiere_zeitgutschrift(antrag, request):
    """Zeitgutschrift nach Submit auto-signieren."""
    import datetime as _dt
    _auto_signiere_antrag(
        antrag, request,
        content_type_str="zeitgutschrift",
        pdf_template="formulare/pdf/zeitgutschrift_pdf.html",
        extra_context={
            "dienstreise": None,
            "tagebuch_tage": [],
            "tagebuch_gesamt_min": 0,
            "tagebuch_gesamt_hmin": "",
            "now": _dt.datetime.now(),
        },
    )


def _auto_signiere_dienstreise(antrag, request):
    """Dienstreise-Antrag nach Submit auto-signieren."""
    _auto_signiere_antrag(
        antrag, request,
        content_type_str="dienstreiseantrag",
        pdf_template="formulare/pdf/dienstreise_pdf.html",
        extra_context={
            "tage": [],
            "gesamt_min": 0,
            "gesamt_hmin": "",
            "reisezeit_gutschrift": None,
        },
    )


def _auto_signiere_genehmigung(antrag, antrag_typ, request):
    """Genehmiger signiert den Antrag nach seiner Entscheidung.

    Verwendet request.user als Unterzeichner (nicht den Antragsteller).
    Schlaegt still fehl.
    """
    ct_map = {
        "aenderung": (
            "aenderungzeiterfassung",
            "formulare/pdf/aenderung_zeiterfassung_pdf.html",
        ),
        "zag": (
            "zagantrag",
            "formulare/pdf/zag_pdf.html",
        ),
        "zag_storno": (
            "zagstorno",
            "formulare/pdf/zag_storno_pdf.html",
        ),
        "zeitgutschrift": (
            "zeitgutschrift",
            "formulare/pdf/zeitgutschrift_pdf.html",
        ),
    }
    entry = ct_map.get(antrag_typ)
    if not entry:
        return
    content_type_str, pdf_template = entry

    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        from signatur.services import signiere_pdf

        ctx = {"antrag": antrag, "betreff": antrag.get_betreff()}
        html_string = render_to_string(pdf_template, ctx, request=request)
        pdf = HTML(
            string=html_string,
            base_url=request.build_absolute_uri(),
        ).write_pdf()
        dateiname = f"Genehmigung_{antrag.get_betreff().replace(' ', '_')}.pdf"
        signiere_pdf(
            pdf,
            request.user,
            dokument_name=dateiname,
            content_type=content_type_str,
            object_id=antrag.pk,
        )
        logger.info(
            "Genehmiger-Signatur OK: %s pk=%s user=%s",
            content_type_str, antrag.pk, request.user.username,
        )
    except Exception as exc:
        logger.warning("Genehmiger-Signatur fehlgeschlagen (%s pk=%s): %s", antrag_typ, antrag.pk, exc)


@login_required
def dashboard(request):
    """Dashboard fuer die Formulare-App.

    Zeigt eine Uebersicht aller verfuegbaren Antragsformulare.
    """
    from workflow.models import WorkflowTask

    # Anzahl offener Workflow-Tasks im Team des eingeloggten Users
    team_stapel_anzahl = 0
    user_teams = TeamQueue.objects.filter(mitglieder=request.user)
    if user_teams.exists():
        team_stapel_anzahl = WorkflowTask.objects.filter(
            zugewiesen_an_team__in=user_teams,
            status="offen",
            claimed_von__isnull=True,
        ).count()

    context = {"team_stapel_anzahl": team_stapel_anzahl}

    # HTMX-Request: nur Partial zurueckgeben
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dashboard.html",
            context,
        )

    return render(request, "formulare/dashboard.html", context)


def _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum):
    """Gibt die aktive Arbeitszeitvereinbarung zum Datum zurueck oder None."""
    return (
        Arbeitszeitvereinbarung.objects
        .filter(mitarbeiter=mitarbeiter, gueltig_ab__lte=datum)
        .order_by("-gueltig_ab")
        .first()
    )


def _loeschgrenze_berechnen():
    """Berechnet das Loeschdatum: heute minus 2 Jahre plus 1 Tag.

    Beispiel: Heute 19.02.2026 -> Grenze 20.02.2024.
    Eintraege die vor diesem Datum erstellt wurden werden geloescht.
    """
    heute = date_type.today()
    try:
        zwei_jahre_zurueck = date_type(heute.year - 2, heute.month, heute.day)
    except ValueError:
        # 29. Februar in Schaltjahr: auf 28. Februar ausweichen
        zwei_jahre_zurueck = date_type(heute.year - 2, heute.month, 28)
    return zwei_jahre_zurueck - timedelta(days=1)


@login_required
def meine_antraege(request):
    """Liste aller eigenen Antraege, neueste zuerst, mit Paginierung.

    Loescht automatisch Eintraege die aelter als 2 Jahre minus 1 Tag sind.
    Zeigt sowohl AenderungZeiterfassung- als auch ZAGAntrag-Eintraege.
    """
    # Automatische Loeschung abgelaufener Eintraege (alle Nutzer, datenschutzkonform)
    loeschgrenze = _loeschgrenze_berechnen()
    AenderungZeiterfassung.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    ZAGAntrag.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    ZAGStorno.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    Zeitgutschrift.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()

    # Alle Antragstypen zusammenfuehren und nach Datum sortieren
    aenderungen = list(
        AenderungZeiterfassung.objects.filter(
            antragsteller__user=request.user
        )
    )
    for a in aenderungen:
        a.antrag_typ = "aenderung"

    zag_antraege = list(
        ZAGAntrag.objects.filter(
            antragsteller__user=request.user
        )
    )
    for z in zag_antraege:
        z.antrag_typ = "zag"

    zag_stornos = list(
        ZAGStorno.objects.filter(
            antragsteller__user=request.user
        )
    )
    for s in zag_stornos:
        s.antrag_typ = "zag_storno"

    zeitgutschriften = list(
        Zeitgutschrift.objects.filter(
            antragsteller__user=request.user
        )
    )
    for z in zeitgutschriften:
        z.antrag_typ = "zeitgutschrift"

    alle_antraege = sorted(
        chain(aenderungen, zag_antraege, zag_stornos, zeitgutschriften),
        key=attrgetter("erstellt_am"),
        reverse=True,
    )

    # WorkflowInstances fuer alle Antraege laden und anheften
    _annotiere_workflow_status(alle_antraege)

    paginator = Paginator(alle_antraege, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "formulare/meine_antraege.html",
        {
            "page_obj": page_obj,
            "loeschgrenze": loeschgrenze,
        },
    )


def _annotiere_workflow_status(antraege):
    """Haengt WorkflowInstance und den naechsten Bearbeiter an jeden Antrag an.

    Setzt:
      antrag.workflow_instance  = WorkflowInstance oder None
      antrag.wf_naechste_stelle = Stelle.kuerzel des offenen Tasks oder None

    Nutzt Bulk-Abfragen um N+1 zu vermeiden.
    """
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowInstance, WorkflowTask

    if not antraege:
        return

    # ContentTypes fuer alle vorkommenden Klassen einmalig laden
    ct_cache = {}

    lookup_pairs = []
    for antrag in antraege:
        cls = type(antrag)
        if cls not in ct_cache:
            ct_cache[cls] = ContentType.objects.get_for_model(cls)
        lookup_pairs.append((ct_cache[cls].id, antrag.pk))

    ct_ids = list({p[0] for p in lookup_pairs})
    obj_ids = list({p[1] for p in lookup_pairs})

    # WorkflowInstanzen laden
    instanzen = WorkflowInstance.objects.filter(
        content_type_id__in=ct_ids,
        object_id__in=obj_ids,
    ).select_related("aktueller_schritt", "template").order_by("-gestartet_am")

    # Mapping (ct_id, obj_id) -> neueste Instanz
    instanz_map = {}
    for inst in instanzen:
        key = (inst.content_type_id, inst.object_id)
        if key not in instanz_map:
            instanz_map[key] = inst

    # Offene Tasks fuer alle Instanzen laden (ein Query)
    instanz_ids = [inst.pk for inst in instanz_map.values()]
    offene_tasks = WorkflowTask.objects.filter(
        instance_id__in=instanz_ids,
        status__in=["offen", "in_bearbeitung"],
    ).select_related(
        "zugewiesen_an_stelle",
        "zugewiesen_an_team",
        "zugewiesen_an_user",
        "claimed_von",
    ).order_by("frist")

    # Mapping instanz_id -> erster offener Task
    task_map = {}
    for task in offene_tasks:
        if task.instance_id not in task_map:
            task_map[task.instance_id] = task

    # An jeden Antrag haengen
    for antrag in antraege:
        ct_id = ct_cache[type(antrag)].id
        inst = instanz_map.get((ct_id, antrag.pk))
        antrag.workflow_instance = inst

        # Naechste Stelle / Bearbeiter ermitteln
        antrag.wf_naechste_stelle = None
        if inst:
            task = task_map.get(inst.pk)
            if task:
                if task.claimed_von:
                    # Task geclaimed: konkreten User anzeigen
                    antrag.wf_naechste_stelle = (
                        task.claimed_von.username.split(".")[0]
                        + "."
                        + (task.claimed_von.username.split(".")[1] if len(task.claimed_von.username.split(".")) > 1 else "")
                    ).strip(".")
                elif task.zugewiesen_an_stelle:
                    antrag.wf_naechste_stelle = task.zugewiesen_an_stelle.kuerzel
                elif task.zugewiesen_an_team:
                    antrag.wf_naechste_stelle = task.zugewiesen_an_team.name
                elif task.zugewiesen_an_user:
                    u = task.zugewiesen_an_user
                    teile = u.username.split(".")
                    antrag.wf_naechste_stelle = ".".join(teile[:2]) if len(teile) >= 2 else u.username


@login_required
def aenderung_zeiterfassung(request):
    """Formular fuer manuelle Aenderungen der Zeiterfassung."""
    form = AenderungZeiterfassungForm(request.POST or None)

    # Tagestausch nur bei individueller Vereinbarung erlaubt
    tausch_erlaubt = False
    if hasattr(request.user, "mitarbeiter"):
        vereinbarung = _vereinbarung_fuer_mitarbeiter(
            request.user.mitarbeiter,
            date_type.today(),
        )
        tausch_erlaubt = bool(
            vereinbarung
            and vereinbarung.arbeitszeit_typ == "individuell"
        )

    if request.method == "POST":
        if form.is_valid():
            antrag = form.save(commit=False)
            antrag.antragsteller = request.user.mitarbeiter

            # Zeitzeilen-Array-Daten aus POST sammeln und als JSON speichern
            tages_datums = request.POST.getlist("tages_datum")
            kommen_zeits = request.POST.getlist("kommen_zeit")
            pause_gehen_zeits = request.POST.getlist("pause_gehen_zeit")
            pause_kommen_zeits = request.POST.getlist("pause_kommen_zeit")
            gehen_zeits = request.POST.getlist("gehen_zeit")
            zeiten_daten = []
            for i in range(len(tages_datums)):
                zeile = {
                    "datum": tages_datums[i] if i < len(tages_datums) else "",
                    "kommen": kommen_zeits[i] if i < len(kommen_zeits) else "",
                    "pause_gehen": pause_gehen_zeits[i] if i < len(pause_gehen_zeits) else "",
                    "pause_kommen": pause_kommen_zeits[i] if i < len(pause_kommen_zeits) else "",
                    "gehen": gehen_zeits[i] if i < len(gehen_zeits) else "",
                }
                if any(zeile.values()):
                    zeiten_daten.append(zeile)
            antrag.zeiten_daten = zeiten_daten or None

            # Tauschzeilen-Array-Daten aus POST sammeln und als JSON speichern
            von_datums = request.POST.getlist("tausch_von_datum")
            zu_datums = request.POST.getlist("tausch_zu_datum")
            tausch_daten = []
            for i in range(len(von_datums)):
                zeile = {
                    "von_datum": von_datums[i] if i < len(von_datums) else "",
                    "zu_datum": zu_datums[i] if i < len(zu_datums) else "",
                }
                if any(zeile.values()):
                    tausch_daten.append(zeile)
            antrag.tausch_daten = tausch_daten or None

            antrag.save()

            # PDF generieren und sofort mit Antragsteller-Zertifikat signieren
            _auto_signiere_aenderungsantrag(antrag, request)

            # Workflow starten (falls aktives Template vorhanden)
            _starte_workflow_fuer_antrag("aenderung_erstellt", antrag, request.user)

            return redirect("formulare:aenderung_erfolg", pk=antrag.pk)

        # HTMX-POST mit Fehler: Formular-Partial zurueckgeben
        if request.headers.get("HX-Request"):
            art = request.POST.get("art", "")
            return render(
                request,
                "formulare/partials/_aenderung_felder.html",
                {"form": form, "art": art},
            )

    return render(
        request,
        "formulare/aenderung_zeiterfassung.html",
        {"form": form, "tausch_erlaubt": tausch_erlaubt},
    )


@login_required
def aenderung_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen eines Aenderungsantrags.

    Zeigt Betreffzeile mit Kopierfunktion, Antragsdetails und PDF-Download.
    Zugriff: Antragsteller, Staff, Genehmiger oder Team-Bearbeiter.
    """
    from django.http import HttpResponseForbidden

    antrag = get_object_or_404(AenderungZeiterfassung, pk=pk)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    vereinbarung = _vereinbarung_fuer_mitarbeiter(
        antrag.antragsteller,
        antrag.erstellt_am.date(),
    )

    # Fuer jeden Tausch-Eintrag die Sollzeit des Von-Datums aufschlagen
    tausch_mit_soll = []
    if antrag.tausch_daten:
        for zeile in antrag.tausch_daten:
            von_datum_str = zeile.get("von_datum", "")
            soll_text = ""
            if von_datum_str:
                try:
                    von_datum = date_type.fromisoformat(von_datum_str)
                    vb = _vereinbarung_fuer_mitarbeiter(
                        antrag.antragsteller, von_datum
                    )
                    if vb:
                        taz = (
                            Tagesarbeitszeit.objects
                            .filter(
                                vereinbarung=vb,
                                wochentag=WOCHENTAG_MAP[von_datum.weekday()],
                            )
                            .order_by("woche")
                            .first()
                        )
                        if taz:
                            soll_text = taz.formatierte_zeit()
                except (ValueError, AttributeError):
                    pass
            tausch_mit_soll.append({
                "von_datum": von_datum_str,
                "zu_datum": zeile.get("zu_datum", ""),
                "soll": soll_text,
            })

    # Signatur des Antragstellers laden (aus Auto-Sign beim Einreichen)
    from signatur.models import SignaturJob
    signatur_job = (
        SignaturJob.objects
        .filter(
            content_type="aenderungzeiterfassung",
            object_id=antrag.pk,
            status="completed",
            erstellt_von=antrag.antragsteller.user,
        )
        .select_related("protokoll", "protokoll__zertifikat")
        .first()
    )
    antrag_signatur = getattr(signatur_job, "protokoll", None) if signatur_job else None

    return render(
        request,
        "formulare/aenderung_erfolg.html",
        {
            "antrag": antrag,
            "vereinbarung": vereinbarung,
            "betreff": antrag.get_betreff(),
            "tausch_mit_soll": tausch_mit_soll,
            "team_bearbeiter_task": _get_team_bearbeiter_task(antrag),
            "queue_task": _get_queue_task_aus_request(request, antrag),
            "antrag_signatur": antrag_signatur,
        },
    )


@login_required
def aenderung_pdf(request, pk):
    """Gibt den Aenderungsantrag als PDF-Download zurueck."""
    from weasyprint import HTML

    antrag = get_object_or_404(AenderungZeiterfassung, pk=pk)

    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    vereinbarung = _vereinbarung_fuer_mitarbeiter(
        antrag.antragsteller,
        antrag.erstellt_am.date(),
    )

    workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    html_string = render_to_string(
        "formulare/pdf/aenderung_zeiterfassung_pdf.html",
        {
            "antrag": antrag,
            "vereinbarung": vereinbarung,
            "betreff": antrag.get_betreff(),
            "workflow_tasks": workflow_tasks,
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()
    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
    pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner, dateiname)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response


@login_required
def soll_fuer_datum(request):
    """HTMX-View - gibt Soll-Arbeitszeit fuer das gewaehlte Datum zurueck.

    Liest die aktive individuelle Vereinbarung des Mitarbeiters aus und
    zeigt die Sollzeit fuer den Wochentag des gewaehlten Datums.
    """
    # HTMX-View - gibt nur Partial zurueck
    datum_str = request.GET.get("tausch_von_datum", "")
    soll_text = ""

    if datum_str and hasattr(request.user, "mitarbeiter"):
        try:
            datum = date_type.fromisoformat(datum_str)
            wochentag = WOCHENTAG_MAP[datum.weekday()]

            vereinbarung = _vereinbarung_fuer_mitarbeiter(
                request.user.mitarbeiter, datum
            )

            if vereinbarung:
                taz = (
                    Tagesarbeitszeit.objects
                    .filter(
                        vereinbarung=vereinbarung,
                        wochentag=wochentag,
                    )
                    .order_by("woche")
                    .first()
                )
                if taz:
                    soll_text = taz.formatierte_zeit()

        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_soll_anzeige.html",
        {"soll_text": soll_text},
    )


@login_required
def neue_tauschzeile(request):
    """HTMX-View - gibt eine neue leere Tauschzeile als Partial zurueck.

    Jede Zeile bekommt eine eindeutige row_id fuer die HTMX-Kollisionsmeldung.
    """
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_tauschzeile.html",
        {"row_id": row_id},
    )


@login_required
def tausch_validierung(request):
    """HTMX-View - prueft ob der neue Tag laut Vereinbarung frei ist.

    Gibt eine Kollisionsmeldung zurueck wenn der neue Tag ein Arbeitstag ist.
    """
    # HTMX-View - gibt nur Partial zurueck
    datum_str = request.GET.get("tausch_zu_datum", "")
    row_id = request.GET.get("row_id", "")
    kollision = False
    datum_gueltig = False

    if datum_str and hasattr(request.user, "mitarbeiter"):
        try:
            datum = date_type.fromisoformat(datum_str)
            wochentag = WOCHENTAG_MAP[datum.weekday()]

            # Aktive Vereinbarung des Mitarbeiters zum gewaehlten Datum suchen
            vereinbarung = (
                Arbeitszeitvereinbarung.objects
                .filter(
                    mitarbeiter=request.user.mitarbeiter,
                    gueltig_ab__lte=datum,
                )
                .order_by("-gueltig_ab")
                .first()
            )

            if vereinbarung:
                taz = (
                    Tagesarbeitszeit.objects
                    .filter(
                        vereinbarung=vereinbarung,
                        wochentag=wochentag,
                    )
                    .first()
                )
                # Zeitwert > 0 bedeutet Arbeitstag -> Kollision
                if taz and taz.zeitwert > 0:
                    kollision = True
                else:
                    datum_gueltig = True

        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_tausch_kollision.html",
        {
            "kollision": kollision,
            "datum_gueltig": datum_gueltig,
            "row_id": row_id,
        },
    )


@login_required
def samstag_felder(request):
    """HTMX-View - gibt Samstags-Unterfelder basierend auf gewaehlter Art zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer eine Samstags-Option auswaehlt.
    """
    # HTMX-View - gibt nur Partial zurueck
    samstag_art = request.GET.get("samstag_art", "")
    form = AenderungZeiterfassungForm()
    return render(
        request,
        "formulare/partials/_samstag_felder.html",
        {"form": form, "samstag_art": samstag_art},
    )


@login_required
def neue_zeitzeile(request):
    """HTMX-View - gibt eine neue leere Zeitzeile als Partial zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer auf '+' klickt.
    """
    # HTMX-View - gibt nur Partial zurueck
    return render(request, "formulare/partials/_zeitzeile.html")


@login_required
def aenderung_felder(request):
    """HTMX-View - gibt Felder-Partial basierend auf gewaehlter Art zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer eine Art-Option auswaehlt.
    """
    # HTMX-View - gibt nur Partial zurueck
    art = request.GET.get("art", "")
    form = AenderungZeiterfassungForm()
    return render(
        request,
        "formulare/partials/_aenderung_felder.html",
        {"form": form, "art": art},
    )


# ---------------------------------------------------------------------------
# Z-AG Antrag
# ---------------------------------------------------------------------------

def _soll_minuten_fuer_datum(mitarbeiter, datum):
    """Berechnet Soll-Minuten aus Vereinbarung fuer ein Datum.

    Gibt None zurueck wenn keine Vereinbarung vorhanden.
    """
    if datum.weekday() >= 5:
        # Wochenenden haben keine Soll-Zeit
        return 0

    vereinbarung = _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum)
    if not vereinbarung:
        return None

    wochentag_name = WOCHENTAG_MAP[datum.weekday()]

    if vereinbarung.arbeitszeit_typ == "individuell":
        tage = Tagesarbeitszeit.objects.filter(
            vereinbarung=vereinbarung,
            wochentag=wochentag_name,
        )
        if tage.exists():
            gesamt = sum(t.zeit_in_minuten for t in tage)
            return int(round(gesamt / tage.count()))
        return 0

    if vereinbarung.wochenstunden:
        return int(round(float(vereinbarung.wochenstunden) / 5 * 60))
    return None


def _erstelle_zag_eintraege(mitarbeiter, datum_von, datum_bis, bemerkung):
    """Erstellt Zeiterfassungs-Eintraege fuer einen Z-AG-Zeitraum.

    Wochenenden und Feiertage (standortabhaengig) werden uebersprungen.
    Gibt die Anzahl erstellter Eintraege zurueck.
    """
    cal = get_feiertagskalender(mitarbeiter.standort)
    aktuell = datum_von
    anzahl = 0
    while aktuell <= datum_bis:
        # Nur Werktage (Mo-Fr) und keine Feiertage
        if aktuell.weekday() < 5 and not cal.is_holiday(aktuell):
            soll_minuten = _soll_minuten_fuer_datum(mitarbeiter, aktuell)
            Zeiterfassung.objects.update_or_create(
                mitarbeiter=mitarbeiter,
                datum=aktuell,
                defaults={
                    "art": "z_ag",
                    "arbeitsbeginn": None,
                    "arbeitsende": None,
                    "pause_minuten": 0,
                    "arbeitszeit_minuten": 0,
                    "soll_minuten": soll_minuten,
                    "bemerkung": bemerkung,
                },
            )
            anzahl += 1
        aktuell += timedelta(days=1)
    return anzahl


@login_required
def zag_antrag(request):
    """Formular fuer Z-AG Antrag mit mehreren Datumsbereichen."""
    if request.method == "POST":
        # Zeilen aus POST sammeln
        von_datums = request.POST.getlist("zag_von_datum")
        bis_datums = request.POST.getlist("zag_bis_datum")

        zag_daten = []
        fehler = []

        for i in range(len(von_datums)):
            von_str = von_datums[i] if i < len(von_datums) else ""
            bis_str = bis_datums[i] if i < len(bis_datums) else ""

            if not von_str and not bis_str:
                # Leere Zeile ueberspringen
                continue

            if not von_str or not bis_str:
                fehler.append(
                    f"Zeile {i + 1}: Bitte beide Datumsfelder ausfullen."
                )
                continue

            try:
                von = date_type.fromisoformat(von_str)
                bis = date_type.fromisoformat(bis_str)
            except ValueError:
                fehler.append(f"Zeile {i + 1}: Ungultiges Datum.")
                continue

            if bis < von:
                fehler.append(
                    f"Zeile {i + 1}: Bis-Datum darf nicht vor Von-Datum liegen."
                )
                continue

            zag_daten.append({"von_datum": von_str, "bis_datum": bis_str})

        if not zag_daten and not fehler:
            fehler.append("Bitte mindestens eine Zeile ausfullen.")

        # Pflichtfelder Vertretung
        vertretung_name = request.POST.get("vertretung_name", "").strip()
        vertretung_telefon = request.POST.get("vertretung_telefon", "").strip()
        if not vertretung_name:
            fehler.append("Bitte die Vertretung (Name) angeben.")
        if not vertretung_telefon:
            fehler.append("Bitte die Telefonnummer der Vertretung angeben.")

        if fehler:
            # Zeilen mit row_id fuer Tage-Zaehler wiederherstellen
            zag_raws = [
                {
                    "von": von_datums[i] if i < len(von_datums) else "",
                    "bis": bis_datums[i] if i < len(bis_datums) else "",
                    "row_id": uuid.uuid4().hex[:8],
                }
                for i in range(max(len(von_datums), len(bis_datums)))
            ]
            fehler_kontext = {
                "fehler": fehler,
                "zag_raws": zag_raws,
                "vertretung_name": vertretung_name,
                "vertretung_telefon": vertretung_telefon,
            }
            if hasattr(request.user, "mitarbeiter"):
                fehler_kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
            return render(request, "formulare/zag_antrag.html", fehler_kontext)

        # Antrag speichern
        mitarbeiter = request.user.mitarbeiter
        antrag = ZAGAntrag.objects.create(
            antragsteller=mitarbeiter,
            zag_daten=zag_daten,
            vertretung_name=request.POST.get("vertretung_name", "").strip(),
            vertretung_telefon=request.POST.get("vertretung_telefon", "").strip(),
        )

        # KEINE Zeiterfassungs-Eintraege beim Antragstellen mehr!
        # Werden erst bei Genehmigung erstellt (siehe genehmigung_entscheiden)

        _auto_signiere_zag(antrag, request)

        # Workflow starten (falls aktives Template vorhanden)
        _starte_workflow_fuer_antrag("zag_antrag_erstellt", antrag, request.user)

        return redirect("formulare:zag_erfolg", pk=antrag.pk)

    # Optionales Vorbefuellen des Von-Datums aus Query-Parameter
    first_von = request.GET.get("von", "")

    kontext = {
        "first_row_id": uuid.uuid4().hex[:8],
        "first_von": first_von,
    }
    if hasattr(request.user, "mitarbeiter"):
        kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
    return render(request, "formulare/zag_antrag.html", kontext)


@login_required
def zag_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen eines Z-AG-Antrags.

    Zeigt Betreffzeile mit Kopierfunktion, Datumsbereich(e) und PDF-Download.
    Zugriff: Antragsteller, Staff, Genehmiger oder Team-Bearbeiter.
    """
    from django.http import HttpResponseForbidden

    antrag = get_object_or_404(ZAGAntrag, pk=pk)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    queue_task = _get_queue_task_aus_request(request, antrag)
    kontext = {
        "antrag": antrag,
        "betreff": antrag.get_betreff(),
        "team_bearbeiter_task": _get_team_bearbeiter_task(antrag),
        "queue_task": queue_task,
        "antrag_signatur": _hole_antrag_signatur("zagantrag", antrag.pk),
    }
    kontext.update(_zag_jahres_kontext(antrag.antragsteller))
    return render(request, "formulare/zag_erfolg.html", kontext)


@login_required
def zag_pdf(request, pk):
    """Gibt den Z-AG-Antrag als PDF-Download zurueck.

    Zugriff: Antragsteller selbst ODER Staff ODER Team-Mitglied mit Claim.
    """
    from weasyprint import HTML

    antrag = get_object_or_404(ZAGAntrag, pk=pk)

    # Berechtigungspruefung
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()

    if not (ist_antragsteller or ist_staff or ist_team or ist_genehmiger):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")

    # Arbeitstage pro Zeitraum berechnen
    mitarbeiter = antrag.antragsteller
    zag_daten_mit_tagen = []
    gesamt_tage = 0
    for zeile in (antrag.zag_daten or []):
        try:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            tage = _zaehle_zag_tage(mitarbeiter, von, bis)
        except (KeyError, ValueError, TypeError):
            von = None
            bis = None
            tage = None
        zag_daten_mit_tagen.append({
            "von_datum": von,
            "bis_datum": bis,
            "tage": tage,
        })
        if tage:
            gesamt_tage += tage

    workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    html_string = render_to_string(
        "formulare/pdf/zag_pdf.html",
        {
            "antrag": antrag,
            "betreff": antrag.get_betreff(),
            "zag_daten_mit_tagen": zag_daten_mit_tagen,
            "gesamt_tage": gesamt_tage,
            "workflow_tasks": workflow_tasks,
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()
    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
    pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner, dateiname)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response


def _zag_jahres_kontext(mitarbeiter):
    """Berechnet Z-AG-Tage des laufenden Jahres fuer den Kontext."""
    jahr = date_type.today().year
    z_ag_tage_jahr = Zeiterfassung.objects.filter(
        mitarbeiter=mitarbeiter,
        datum__year=jahr,
        art="z_ag",
    ).count()
    return {"z_ag_tage_jahr": z_ag_tage_jahr, "z_ag_jahr": jahr}


def _zaehle_zag_tage(mitarbeiter, datum_von, datum_bis):
    """Zaehlt Arbeitstage im Zeitraum exklusive Wochenenden, Feiertage
    und (bei individueller Vereinbarung) vertragsfreier Wochentage.
    """
    cal = get_feiertagskalender(mitarbeiter.standort)

    # Vereinbarung zum Startdatum (wird fuer gesamten Zeitraum genutzt)
    vereinbarung = _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum_von)

    # Freie Wochentage aus individueller Vereinbarung ermitteln
    freie_wochentage = set()
    if vereinbarung and vereinbarung.arbeitszeit_typ == "individuell":
        for wt_num in range(5):  # Mo-Fr
            wt_name = WOCHENTAG_MAP[wt_num]
            tage_vb = Tagesarbeitszeit.objects.filter(
                vereinbarung=vereinbarung,
                wochentag=wt_name,
            )
            if not tage_vb.exists() or all(t.zeitwert == 0 for t in tage_vb):
                freie_wochentage.add(wt_num)

    aktuell = datum_von
    anzahl = 0
    while aktuell <= datum_bis:
        if (
            aktuell.weekday() < 5
            and not cal.is_holiday(aktuell)
            and aktuell.weekday() not in freie_wochentage
        ):
            anzahl += 1
        aktuell += timedelta(days=1)
    return anzahl


@login_required
def zag_tage_zaehlen(request):
    """HTMX-View - berechnet Arbeitstage fuer einen Z-AG-Zeitraum.

    Beruecksichtigt Wochenenden, standortabhaengige Feiertage und
    freie Wochentage aus individueller Arbeitszeitvereinbarung.
    """
    # HTMX-View - gibt nur Partial zurueck
    von_str = request.GET.get("zag_von_datum", "")
    bis_str = request.GET.get("zag_bis_datum", "")
    tage_anzahl = None

    if von_str and bis_str and hasattr(request.user, "mitarbeiter"):
        try:
            von = date_type.fromisoformat(von_str)
            bis = date_type.fromisoformat(bis_str)
            if bis >= von:
                tage_anzahl = _zaehle_zag_tage(
                    request.user.mitarbeiter, von, bis
                )
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_zag_tage.html",
        {"tage_anzahl": tage_anzahl},
    )


@login_required
def neue_zag_zeile(request):
    """HTMX-View - gibt eine neue leere Z-AG-Zeile als Partial zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer auf '+' klickt.
    """
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_zag_zeile.html",
        {"row_id": row_id},
    )


# ---------------------------------------------------------------------------
# Z-AG Storno
# ---------------------------------------------------------------------------

def _storniere_zag_eintraege(mitarbeiter, datum_von, datum_bis):
    """Loescht Z-AG-Zeiterfassungs-Eintraege im Zeitraum.

    Gibt die Anzahl tatsaechlich geloeschter Eintraege zurueck.
    """
    deleted, _ = Zeiterfassung.objects.filter(
        mitarbeiter=mitarbeiter,
        art="z_ag",
        datum__gte=datum_von,
        datum__lte=datum_bis,
    ).delete()
    return deleted


@login_required
def zag_storno_tage_zaehlen(request):
    """HTMX-View - zeigt vorhandene Z-AG-Tage im gewaehlten Zeitraum.

    Berechnet wie viele Zeiterfassungs-Eintraege mit art='z_ag'
    tatsaechlich vorhanden sind und storniert wuerden.
    """
    # HTMX-View - gibt nur Partial zurueck
    von_str = request.GET.get("storno_von_datum", "")
    bis_str = request.GET.get("storno_bis_datum", "")
    tage_anzahl = None

    if von_str and bis_str and hasattr(request.user, "mitarbeiter"):
        try:
            von = date_type.fromisoformat(von_str)
            bis = date_type.fromisoformat(bis_str)
            if bis >= von:
                tage_anzahl = Zeiterfassung.objects.filter(
                    mitarbeiter=request.user.mitarbeiter,
                    art="z_ag",
                    datum__gte=von,
                    datum__lte=bis,
                ).count()
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_zag_storno_tage.html",
        {"tage_anzahl": tage_anzahl},
    )


@login_required
def neue_zag_storno_zeile(request):
    """HTMX-View - gibt eine neue leere Storno-Zeile als Partial zurueck."""
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_zag_storno_zeile.html",
        {"row_id": row_id},
    )


@login_required
def zag_storno(request):
    """Formular fuer Z-AG Stornierung mit mehreren Datumsbereichen."""
    if request.method == "POST":
        von_datums = request.POST.getlist("storno_von_datum")
        bis_datums = request.POST.getlist("storno_bis_datum")

        storno_daten = []
        fehler = []

        for i in range(len(von_datums)):
            von_str = von_datums[i] if i < len(von_datums) else ""
            bis_str = bis_datums[i] if i < len(bis_datums) else ""

            if not von_str and not bis_str:
                continue

            if not von_str or not bis_str:
                fehler.append(
                    f"Zeile {i + 1}: Bitte beide Datumsfelder ausfullen."
                )
                continue

            try:
                von = date_type.fromisoformat(von_str)
                bis = date_type.fromisoformat(bis_str)
            except ValueError:
                fehler.append(f"Zeile {i + 1}: Ungultiges Datum.")
                continue

            if bis < von:
                fehler.append(
                    f"Zeile {i + 1}: Bis-Datum darf nicht vor Von-Datum liegen."
                )
                continue

            storno_daten.append({"von_datum": von_str, "bis_datum": bis_str})

        if not storno_daten and not fehler:
            fehler.append("Bitte mindestens eine Zeile ausfullen.")

        if fehler:
            storno_raws = [
                {
                    "von": von_datums[i] if i < len(von_datums) else "",
                    "bis": bis_datums[i] if i < len(bis_datums) else "",
                    "row_id": uuid.uuid4().hex[:8],
                }
                for i in range(max(len(von_datums), len(bis_datums)))
            ]
            fehler_kontext = {
                "fehler": fehler,
                "storno_raws": storno_raws,
            }
            if hasattr(request.user, "mitarbeiter"):
                fehler_kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
            return render(request, "formulare/zag_storno.html", fehler_kontext)

        # Storno-Antrag speichern
        mitarbeiter = request.user.mitarbeiter
        antrag = ZAGStorno.objects.create(
            antragsteller=mitarbeiter,
            storno_daten=storno_daten,
        )

        # Workflow starten (falls aktives Template vorhanden)
        _starte_workflow_fuer_antrag("zag_storno_erstellt", antrag, request.user)

        return redirect("formulare:zag_storno_erfolg", pk=antrag.pk)

    kontext = {"first_row_id": uuid.uuid4().hex[:8]}
    if hasattr(request.user, "mitarbeiter"):
        mitarbeiter = request.user.mitarbeiter
        kontext.update(_zag_jahres_kontext(mitarbeiter))
        # Zukuenftige Z-AG-Eintraege des laufenden Jahres zur Orientierung
        heute = date_type.today()
        kontext["zag_zukunft"] = (
            Zeiterfassung.objects
            .filter(
                mitarbeiter=mitarbeiter,
                art="z_ag",
                datum__gte=heute,
                datum__year=heute.year,
            )
            .order_by("datum")
        )
    return render(request, "formulare/zag_storno.html", kontext)


@login_required
def zag_storno_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen einer Z-AG Stornierung.

    Zugriff: Antragsteller, Staff, Genehmiger oder Team-Bearbeiter.
    """
    from django.http import HttpResponseForbidden

    antrag = get_object_or_404(ZAGStorno, pk=pk)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    kontext = {
        "antrag": antrag,
        "betreff": antrag.get_betreff(),
        "team_bearbeiter_task": _get_team_bearbeiter_task(antrag),
        "queue_task": _get_queue_task_aus_request(request, antrag),
    }
    kontext.update(_zag_jahres_kontext(antrag.antragsteller))
    return render(request, "formulare/zag_storno_erfolg.html", kontext)


@login_required
def zag_storno_pdf(request, pk):
    """Gibt die Z-AG Stornierung als PDF-Download zurueck."""
    from weasyprint import HTML

    antrag = get_object_or_404(ZAGStorno, pk=pk)

    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_staff = request.user.is_staff or request.user.is_superuser
    ist_genehmiger = _offene_antraege_fuer_user(request.user).filter(
        pk=antrag.antragsteller.pk
    ).exists()
    ist_team = _ist_team_mitglied_fuer_antrag(request.user, antrag)
    if not (ist_antragsteller or ist_staff or ist_genehmiger or ist_team):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung fuer diesen Antrag.")
    workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    html_string = render_to_string(
        "formulare/pdf/zag_storno_pdf.html",
        {
            "antrag": antrag,
            "betreff": antrag.get_betreff(),
            "workflow_tasks": workflow_tasks,
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()
    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    unterzeichner = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
    pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner, dateiname)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response


# ============================================================================
# GENEHMIGUNGSWORKFLOW
# ============================================================================

def _genehmiger_mitarbeiter(user):
    """Gibt QuerySet aller Mitarbeiter zurueck, fuer die der User
    die guardian-Permission 'genehmigen_antraege' besitzt.

    Superuser und Staff sehen alle Mitarbeiter.
    Wird spaeter durch _offene_antraege_fuer_user ersetzt.
    """
    from arbeitszeit.models import Mitarbeiter
    if user.is_superuser or user.is_staff:
        return Mitarbeiter.objects.all()
    from guardian.shortcuts import get_objects_for_user
    return get_objects_for_user(
        user,
        "genehmigen_antraege",
        Mitarbeiter,
    )


def _get_team_bearbeiter_task(content_object):
    """Gibt den abgeschlossenen Team-Bearbeiter-Task fuer ein Antrag-Objekt zurueck.

    Sucht den erledigten WorkflowTask mit aktion_typ='bearbeiten' der zum
    Antrag gehoert – das ist der Task den Nicole Schwarz abgeschlossen hat.
    Gibt None zurueck wenn noch kein solcher Task existiert.
    """
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowTask

    ct = ContentType.objects.get_for_model(content_object)
    return (
        WorkflowTask.objects.filter(
            instance__content_type=ct,
            instance__object_id=content_object.pk,
            step__aktion_typ="bearbeiten",
            status="erledigt",
        )
        .select_related("erledigt_von")
        .order_by("-erledigt_am")
        .first()
    )


def _ist_team_mitglied_fuer_antrag(user, content_object):
    """Prueft ob der User Mitglied eines Teams ist, das einen Task fuer dieses Objekt hat.

    Erlaubt Team-Bearbeitern Zugriff auf Details/PDF auch vor dem Claimen.
    """
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowTask

    user_teams = TeamQueue.objects.filter(mitglieder=user)
    if not user_teams.exists():
        return False
    ct = ContentType.objects.get_for_model(content_object)
    return WorkflowTask.objects.filter(
        zugewiesen_an_team__in=user_teams,
        instance__content_type=ct,
        instance__object_id=content_object.pk,
    ).exists()


def _get_queue_task_aus_request(request, content_object):
    """Liest queue_task GET-Parameter und prueft ob User diesen Task geclaimed hat.

    Gibt den WorkflowTask zurueck oder None.
    """
    from workflow.models import WorkflowTask
    from django.contrib.contenttypes.models import ContentType

    queue_task_pk = request.GET.get("queue_task")
    if not queue_task_pk:
        return None
    try:
        ct = ContentType.objects.get_for_model(content_object)
        return WorkflowTask.objects.select_related("step").get(
            pk=queue_task_pk,
            claimed_von=request.user,
            status="in_bearbeitung",
            instance__content_type=ct,
            instance__object_id=content_object.pk,
        )
    except WorkflowTask.DoesNotExist:
        return None


def _genehmigende_stelle(antragsteller_ma, dauer_tage=0):
    """Delegiert an formulare.utils.genehmigende_stelle.

    Bleibt als privater Alias erhalten damit bestehende interne Aufrufe
    unveraendert funktionieren.
    """
    from formulare.utils import genehmigende_stelle
    return genehmigende_stelle(antragsteller_ma, dauer_tage)


def _offene_antraege_fuer_user(user):
    """Gibt QuerySet der Mitarbeiter zurueck, deren Antraege der User sehen darf.

    Logik:
    - Superuser/Staff: alle Mitarbeiter
    - Sonst: Mitarbeiter deren uebergeordnete_stelle.verantwortliche_stelle() == user_stelle
      Das beruecksichtigt automatisch Delegation und temporaere Vertretung.

    Faellt auf guardian-Permissions zurueck wenn kein Stellensystem vorhanden.
    """
    from arbeitszeit.models import Mitarbeiter
    from hr.models import HRMitarbeiter, Stelle

    if user.is_superuser or user.is_staff:
        return Mitarbeiter.objects.all()

    # Stelle des eingeloggten Users ermitteln
    try:
        hr_ma = user.hr_mitarbeiter
        user_stelle = hr_ma.stelle
    except Exception:
        user_stelle = None

    if user_stelle is not None:
        # Alle Stellen mit uebergeordneter Stelle laden
        stellen_mit_vorgesetztem = Stelle.objects.filter(
            uebergeordnete_stelle__isnull=False
        ).select_related("uebergeordnete_stelle")

        # Berechtigte Stellen: user_stelle ist die DIREKTE uebergeordnete Stelle (Heike sieht Alex)
        # ODER user_stelle ist die verantwortliche Stelle per Delegation (Alex sieht als Delegierter)
        # ABER: keine Selbst-Genehmigung (eigene Stelle nie in der Liste)
        berechtigte_stellen = []
        for stelle in stellen_mit_vorgesetztem:
            # Nie eigene Stelle aufnehmen (Selbst-Genehmigung verhindern)
            if stelle.pk == user_stelle.pk:
                continue
            ug = stelle.uebergeordnete_stelle
            # Direkte Hierarchie
            direkt_zustaendig = ug.pk == user_stelle.pk
            # Delegation: user_stelle ist der Delegat von ug
            verantwortliche = ug.verantwortliche_stelle()
            als_delegat_zustaendig = (
                verantwortliche is not None and verantwortliche.pk == user_stelle.pk
            )
            if direkt_zustaendig or als_delegat_zustaendig:
                berechtigte_stellen.append(stelle.pk)

        if berechtigte_stellen:
            # HRMitarbeiter dieser Stellen
            untergebene_hr = HRMitarbeiter.objects.filter(
                stelle__pk__in=berechtigte_stellen
            )
            untergebene_user_ids = untergebene_hr.values_list("user_id", flat=True)
            # arbeitszeit.Mitarbeiter der Untergebenen
            stellen_ma = Mitarbeiter.objects.filter(user__in=untergebene_user_ids)
            if stellen_ma.exists():
                return stellen_ma

    # Fallback: guardian-Permissions (wird spaeter entfernt)
    from guardian.shortcuts import get_objects_for_user
    return get_objects_for_user(user, "genehmigen_antraege", Mitarbeiter)


@login_required
def genehmigung_uebersicht(request):
    """Weitergeleitet an den neuen Workflow-Arbeitsstapel.

    Die alte Genehmigungsansicht ist abgeschaltet. Alle Genehmigungen
    laufen jetzt ueber /workflow/.
    """
    return redirect("workflow:arbeitsstapel")


@login_required
def _genehmigung_uebersicht_alt(request):
    """VERALTET – wird nicht mehr aufgerufen. Nur zur Referenz.

    Ehemals: Uebersicht aller offenen Antraege fuer den eingeloggten Genehmiger.
    """
    berechtigte_ma = _offene_antraege_fuer_user(request.user)

    if not berechtigte_ma.exists():
        return render(
            request,
            "formulare/genehmigung_uebersicht.html",
            {"kein_zugang": True},
        )

    aenderungen = (
        AenderungZeiterfassung.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )
    zag_antraege = (
        ZAGAntrag.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )
    zag_stornos = (
        ZAGStorno.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )
    zeitgutschriften = (
        Zeitgutschrift.objects.filter(
            antragsteller__in=berechtigte_ma,
            status="beantragt",
        )
        .select_related("antragsteller")
        .order_by("erstellt_am")
    )

    # Zuletzt erledigte Antraege fuer Historie
    aenderungen_erledigt = (
        AenderungZeiterfassung.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )
    zag_erledigt = (
        ZAGAntrag.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )
    zag_storno_erledigt = (
        ZAGStorno.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )
    zeitgutschriften_erledigt = (
        Zeitgutschrift.objects.filter(
            antragsteller__in=berechtigte_ma,
            status__in=["genehmigt", "abgelehnt"],
        )
        .select_related("antragsteller", "bearbeitet_von")
        .order_by("-bearbeitet_am")[:10]
    )

    gesamt_offen = (
        aenderungen.count() + zag_antraege.count() +
        zag_stornos.count() + zeitgutschriften.count()
    )

    return render(
        request,
        "formulare/genehmigung_uebersicht.html",
        {
            "aenderungen": aenderungen,
            "zag_antraege": zag_antraege,
            "zag_stornos": zag_stornos,
            "zeitgutschriften": zeitgutschriften,
            "aenderungen_erledigt": aenderungen_erledigt,
            "zag_erledigt": zag_erledigt,
            "zag_storno_erledigt": zag_storno_erledigt,
            "zeitgutschriften_erledigt": zeitgutschriften_erledigt,
            "gesamt_offen": gesamt_offen,
            "kein_zugang": False,
        },
    )


@login_required
def genehmigung_entscheiden(request, antrag_typ, pk):
    """Genehmigt oder lehnt einen einzelnen Antrag ab.

    # HTMX-View - gibt bei HTMX-Request nur das erledigte Zeilen-Partial zurueck.

    antrag_typ: 'aenderung' | 'zag' | 'zag_storno' | 'zeitgutschrift'
    """
    from django.utils import timezone

    if request.method != "POST":
        return redirect("formulare:genehmigung_uebersicht")

    model_map = {
        "aenderung": AenderungZeiterfassung,
        "zag": ZAGAntrag,
        "zag_storno": ZAGStorno,
        "zeitgutschrift": Zeitgutschrift,
    }
    Model = model_map.get(antrag_typ)
    if Model is None:
        return redirect("formulare:genehmigung_uebersicht")

    antrag = get_object_or_404(Model, pk=pk)

    # Berechtigungspruefung: stellenbasiert mit guardian-Fallback
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    if antrag.antragsteller not in berechtigte_ma:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<span class="badge bg-danger">Keine Berechtigung</span>',
                status=403,
            )
        return redirect("formulare:genehmigung_uebersicht")

    neue_status = request.POST.get("status")
    if neue_status not in ("genehmigt", "abgelehnt"):
        return redirect("formulare:genehmigung_uebersicht")

    antrag.status = neue_status
    antrag.bearbeitet_von = request.user
    antrag.bearbeitet_am = timezone.now()
    antrag.bemerkung_bearbeiter = request.POST.get("bemerkung", "").strip()
    antrag.save()

    # Genehmiger signiert den Antrag digital
    _auto_signiere_genehmigung(antrag, antrag_typ, request)

    # Automatische Buchung bei Z-AG Antraegen
    if antrag_typ == "zag" and neue_status == "genehmigt":
        # Z-AG genehmigt → Zeiterfassungs-Eintraege erstellen
        gesamt_tage = 0
        for zeile in antrag.zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            bemerkung = f"Z-AG genehmigt von {request.user.get_full_name() or request.user.username}"
            gesamt_tage += _erstelle_zag_eintraege(
                antrag.antragsteller, von, bis, bemerkung
            )

    elif antrag_typ == "zag" and neue_status == "abgelehnt":
        # Z-AG abgelehnt → Zeiterfassungs-Eintraege loeschen (falls vorhanden)
        for zeile in antrag.zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            aktuell = von
            while aktuell <= bis:
                Zeiterfassung.objects.filter(
                    mitarbeiter=antrag.antragsteller,
                    datum=aktuell,
                    art="z_ag",
                ).delete()
                aktuell += timedelta(days=1)

    elif antrag_typ == "zag_storno" and neue_status == "genehmigt":
        # Z-AG Storno genehmigt → Zeiterfassungs-Eintraege loeschen
        for zeile in antrag.storno_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            aktuell = von
            while aktuell <= bis:
                Zeiterfassung.objects.filter(
                    mitarbeiter=antrag.antragsteller,
                    datum=aktuell,
                    art="z_ag",
                ).delete()
                aktuell += timedelta(days=1)

    # HTMX: Zeile durch erledigtes Partial ersetzen
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_genehmigung_zeile_erledigt.html",
            {
                "antrag": antrag,
                "antrag_typ": antrag_typ,
            },
        )

    return redirect("formulare:genehmigung_uebersicht")

# ============================================================================
# DIENSTREISE-VIEWS
# ============================================================================


@login_required
def dienstreise_erstellen(request):
    """Erstelle einen neuen Dienstreiseantrag.

    HTMX-Pattern: Inline-Validierung + Partial-Rendering.
    """
    mitarbeiter = get_object_or_404(
        request.user.mitarbeiter.__class__,
        user=request.user
    )

    if request.method == "POST":
        form = DienstreiseantragForm(request.POST)
        if form.is_valid():
            antrag = form.save(commit=False)
            antrag.antragsteller = mitarbeiter
            antrag.save()

            _auto_signiere_dienstreise(antrag, request)

            # Workflow automatisch starten (via Signal - siehe signals.py)

            # HTMX: Erfolgs-Partial
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "formulare/partials/_dienstreise_erfolg.html",
                    {"antrag": antrag},
                )

            return redirect("formulare:dienstreise_uebersicht")

        # HTMX: Formular mit Fehlern zurueckgeben
        if request.headers.get("HX-Request"):
            return render(
                request,
                "formulare/partials/_dienstreise_formular.html",
                {"form": form},
            )

    else:
        form = DienstreiseantragForm()

    context = {"form": form}

    # HTMX: Nur Formular-Partial
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dienstreise_formular.html",
            context,
        )

    return render(request, "formulare/dienstreise_erstellen.html", context)


@login_required
def dienstreise_bearbeiten(request, pk):
    """Bearbeite einen bestehenden Dienstreiseantrag.

    Nur der Antragsteller kann seinen eigenen Antrag bearbeiten.
    Wird verwendet wenn Antrag zur Ueberarbeitung zurueckgesendet wurde.
    """
    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    # Pruefe Berechtigung: Nur Antragsteller darf bearbeiten
    if request.user != antrag.antragsteller.user:
        messages.error(request, "Sie koennen nur Ihre eigenen Antraege bearbeiten.")
        return redirect("formulare:meine_dienstreisen")

    if request.method == "POST":
        form = DienstreiseantragForm(request.POST, instance=antrag)
        if form.is_valid():
            antrag = form.save()

            messages.success(
                request,
                "Ihre Aenderungen wurden gespeichert. "
                "Bitte kehren Sie zum Workflow-Task zurueck um die Bearbeitung abzuschliessen."
            )

            # Zurueck zur Workflow-Task-Ansicht falls task_id uebergeben
            task_id = request.GET.get("task_id")
            if task_id:
                return redirect("workflow:task_detail", pk=task_id)

            return redirect("formulare:meine_dienstreisen")

        # HTMX: Formular mit Fehlern
        if request.headers.get("HX-Request"):
            return render(
                request,
                "formulare/partials/_dienstreise_formular.html",
                {"form": form, "bearbeiten": True},
            )

    else:
        form = DienstreiseantragForm(instance=antrag)

    context = {
        "form": form,
        "antrag": antrag,
        "bearbeiten": True,
    }

    # HTMX: Nur Formular-Partial
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dienstreise_formular.html",
            context,
        )

    return render(request, "formulare/dienstreise_bearbeiten.html", context)


@login_required
def dienstreise_uebersicht(request):
    """Zeigt alle Dienstreiseantraege des Users."""
    mitarbeiter = get_object_or_404(
        request.user.mitarbeiter.__class__,
        user=request.user
    )

    antraege = Dienstreiseantrag.objects.filter(
        antragsteller=mitarbeiter
    ).select_related("workflow_instance").order_by("-erstellt_am")

    context = {"antraege": antraege}

    # HTMX: Partial
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dienstreise_liste.html",
            context,
        )

    return render(request, "formulare/dienstreise_uebersicht.html", context)


@login_required
def api_team_queues(request):
    """API-Endpunkt: Gibt alle Team-Queues als JSON zurueck.

    Wird vom Workflow-Editor verwendet um Team-Dropdown zu befuellen.
    """
    teams = TeamQueue.objects.all().order_by("name")

    data = {
        "teams": [
            {
                "id": team.id,
                "name": team.name,
            }
            for team in teams
        ]
    }

    return JsonResponse(data)


# ============================================================================
# TEAM-BUILDER
# ============================================================================

@login_required
def team_builder(request):
    """Team-Builder: Visuelle Verwaltung von Team-Queues."""
    from django.contrib.auth import get_user_model
    from hr.models import OrgEinheit

    User = get_user_model()

    # OrgEinheit aus Query-Parameter
    org_kuerzel = request.GET.get("org")
    org = None
    if org_kuerzel:
        try:
            org = OrgEinheit.objects.get(kuerzel=org_kuerzel)
        except OrgEinheit.DoesNotExist:
            pass

    teams = TeamQueue.objects.all().prefetch_related("mitglieder").order_by("name")

    from facility.models import FacilityTeam
    facility_teams = FacilityTeam.objects.all().prefetch_related("mitglieder").select_related("teamleiter")

    def _mit_stelle(qs):
        """Reichert User-Queryset mit Stellen-Info an."""
        result = []
        for user in qs:
            stelle_info = ""
            try:
                ma = user.hr_mitarbeiter
                if ma.stelle:
                    stelle_info = f"{ma.stelle.kuerzel} – {ma.stelle.bezeichnung}"
            except Exception:
                pass
            result.append({
                "id": user.id,
                "name": user.get_full_name() or user.username,
                "username": user.username,
                "stelle": stelle_info,
            })
        return result

    # User-Liste: Wenn OrgEinheit angegeben, zuerst deren Mitarbeiter
    org_users = None
    other_users = None
    all_users = None

    if org:
        org_qs = User.objects.filter(
            is_active=True,
            hr_mitarbeiter__stelle__org_einheit=org
        ).distinct().order_by("last_name", "first_name", "username")

        other_qs = User.objects.filter(is_active=True).exclude(
            id__in=org_qs.values_list("id", flat=True)
        ).order_by("last_name", "first_name", "username")

        org_users = _mit_stelle(org_qs)
        other_users = _mit_stelle(other_qs)
    else:
        all_qs = User.objects.filter(is_active=True).order_by(
            "last_name", "first_name", "username"
        )
        all_users = _mit_stelle(all_qs)

    # Alle User als Python-Liste fuer json_script im Template
    if org:
        alle_fuer_json = (org_users or []) + (other_users or [])
    else:
        alle_fuer_json = all_users or []

    context = {
        "teams": teams,
        "facility_teams": facility_teams,
        "all_users": all_users,
        "org_users": org_users,
        "other_users": other_users,
        "org": org,
        "org_kuerzel": org_kuerzel,
        "users_json": alle_fuer_json,
    }

    return render(request, "formulare/team_builder.html", context)


@login_required
def team_builder_detail(request, pk):
    """API: Team-Details laden."""
    team = get_object_or_404(TeamQueue, pk=pk)

    data = {
        "id": team.id,
        "name": team.name,
        "beschreibung": team.beschreibung,
        "antragstypen": team.antragstypen or [],
    }

    return JsonResponse(data)


@login_required
def team_builder_create(request):
    """API: Neues Team erstellen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        beschreibung = data.get("beschreibung", "").strip()
        antragstypen = data.get("antragstypen", [])

        if not name:
            return JsonResponse({"error": "Name erforderlich"}, status=400)

        # Kuerzel aus Name ableiten (lowercase, nur Buchstaben/Zahlen)
        import re
        basis = re.sub(r"[^a-z0-9]", "", name.lower())[:18] or "team"
        kuerzel = basis
        zaehler = 2
        while TeamQueue.objects.filter(kuerzel=kuerzel).exists():
            kuerzel = f"{basis}{zaehler}"
            zaehler += 1

        team = TeamQueue.objects.create(
            name=name,
            beschreibung=beschreibung,
            kuerzel=kuerzel,
            antragstypen=antragstypen,
        )

        return JsonResponse({
            "success": True,
            "id": team.id,
            "message": f"Team '{team.name}' erstellt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def team_builder_update(request, pk):
    """API: Team bearbeiten."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    team = get_object_or_404(TeamQueue, pk=pk)

    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        beschreibung = data.get("beschreibung", "").strip()
        antragstypen = data.get("antragstypen", [])

        if not name:
            return JsonResponse({"error": "Name erforderlich"}, status=400)

        team.name = name
        team.beschreibung = beschreibung
        team.antragstypen = antragstypen
        team.save()

        return JsonResponse({
            "success": True,
            "message": f"Team '{team.name}' aktualisiert"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def team_builder_delete(request, pk):
    """API: Team loeschen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    team = get_object_or_404(TeamQueue, pk=pk)

    # Pruefe ob Team in Workflows verwendet wird
    from workflow.models import WorkflowStep, WorkflowTask

    verwendung_steps = WorkflowStep.objects.filter(zustaendig_team=team).count()
    verwendung_tasks = WorkflowTask.objects.filter(zugewiesen_an_team=team).count()

    if verwendung_steps > 0 or verwendung_tasks > 0:
        return JsonResponse({
            "error": f"Team wird in {verwendung_steps} Workflow-Schritten und {verwendung_tasks} Tasks verwendet"
        }, status=400)

    team_name = team.name
    team.delete()

    return JsonResponse({
        "success": True,
        "message": f"Team '{team_name}' geloescht"
    })


@login_required
def team_builder_add_member(request, pk):
    """API: Mitglied zum Team hinzufuegen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from django.contrib.auth import get_user_model

    User = get_user_model()
    team = get_object_or_404(TeamQueue, pk=pk)

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
            "message": f"{user.username} zu '{team.name}' hinzugefuegt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def team_builder_remove_member(request, pk):
    """API: Mitglied aus Team entfernen."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from django.contrib.auth import get_user_model

    User = get_user_model()
    team = get_object_or_404(TeamQueue, pk=pk)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "User-ID erforderlich"}, status=400)

        user = get_object_or_404(User, pk=user_id)
        team.mitglieder.remove(user)

        return JsonResponse({
            "success": True,
            "message": f"{user.username} aus '{team.name}' entfernt"
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Ungueltige JSON-Daten"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def meine_dienstreisen(request):
    """Uebersicht ueber alle Dienstreisen des aktuellen Users.

    Zeigt Status, Workflow-Fortschritt und ermoeglicht Zugriff
    auf detaillierte Workflow-Status-Ansicht.
    """
    # Hole Mitarbeiter des Users
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        # User hat keinen Mitarbeiter -> keine Dienstreisen
        return render(request, "formulare/meine_dienstreisen.html", {
            "antraege": [],
            "anzahl_beantragt": 0,
            "anzahl_genehmigt": 0,
            "anzahl_abgelehnt": 0,
        })

    # Hole alle Dienstreiseantraege des Mitarbeiters
    antraege = Dienstreiseantrag.objects.filter(
        antragsteller=mitarbeiter
    ).select_related(
        "workflow_instance",
        "workflow_instance__template",
        "workflow_instance__aktueller_schritt",
    ).order_by("-erstellt_am")

    # Statistiken
    anzahl_beantragt = antraege.filter(
        status__in=["beantragt", "in_bearbeitung"]
    ).count()
    anzahl_genehmigt = antraege.filter(status="genehmigt").count()
    anzahl_abgelehnt = antraege.filter(status="abgelehnt").count()

    context = {
        "antraege": antraege,
        "anzahl_beantragt": anzahl_beantragt,
        "anzahl_genehmigt": anzahl_genehmigt,
        "anzahl_abgelehnt": anzahl_abgelehnt,
    }

    return render(request, "formulare/meine_dienstreisen.html", context)


def _dezimal_zu_hmin(stunden):
    """Konvertiert Dezimalstunden in 'Xh YYmin' Format. Z.B. 7.8 -> '7h 48min'."""
    h = int(stunden)
    m = round((stunden - h) * 60)
    if m == 60:
        h += 1
        m = 0
    return f"{h}h {m:02d}min"


def _berechne_fortbildung(mitarbeiter, von_datum, bis_datum, wochenstunden_regulaer):
    """Berechnet Zeitgutschrift fuer ganztaegige Fortbildung.

    Iteriert ueber Arbeitstage (Mo-Fr ohne Feiertage) und vergleicht:
    - Fortbildungs-Soll (eingegebene taegliche Sollzeit)
    - Vereinbarungs-Soll (aus get_aktuelle_vereinbarung)

    Gibt JSON-Struktur mit Zeilen, Summen und Differenz zurueck.
    """
    try:
        # Feiertagskalender
        feiertage = get_feiertagskalender(mitarbeiter.standort)

        # Taegliche Sollzeit aus eingegebenen Wochenstunden
        taegliche_sollzeit = wochenstunden_regulaer / 5

        zeilen = []
        summe_fortbildung = 0
        summe_vereinbarung = 0

        # Iteriere ueber Datumsbereich
        aktuell = von_datum
        while aktuell <= bis_datum:
            # Nur Arbeitstage (Mo-Fr ohne Feiertage) - workalendar-API verwenden
            if feiertage.is_working_day(aktuell):
                # Vereinbarungs-Soll holen (taegliche Sollzeit aus Wochenstunden)
                vereinbarung = mitarbeiter.get_aktuelle_vereinbarung(aktuell)
                if vereinbarung and vereinbarung.wochenstunden:
                    vereinbarung_soll = float(vereinbarung.wochenstunden) / 5
                else:
                    vereinbarung_soll = 0

                # Wochentag als Text
                wochentag_text = [
                    "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                    "Samstag", "Sonntag"
                ][aktuell.weekday()]

                zeilen.append({
                    "datum": aktuell.strftime("%d.%m.%Y"),
                    "wochentag": wochentag_text,
                    "fortbildung_soll": _dezimal_zu_hmin(float(taegliche_sollzeit)),
                    "vereinbarung_soll": _dezimal_zu_hmin(float(vereinbarung_soll)),
                })

                summe_fortbildung += float(taegliche_sollzeit)
                summe_vereinbarung += float(vereinbarung_soll)

            aktuell += timedelta(days=1)

        # Differenz berechnen
        differenz = abs(summe_fortbildung - summe_vereinbarung)
        differenz_hoeherer = (
            "fortbildung" if summe_fortbildung > summe_vereinbarung
            else "vereinbarung"
        )

        return {
            "zeilen": zeilen,
            "summe_fortbildung": _dezimal_zu_hmin(summe_fortbildung),
            "summe_vereinbarung": _dezimal_zu_hmin(summe_vereinbarung),
            "differenz": _dezimal_zu_hmin(differenz),
            "differenz_hoeherer": differenz_hoeherer,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Fehler in _berechne_fortbildung: %s", e)
        return None


@login_required
def zeitgutschrift_antrag(request):
    """Haupt-View fuer Zeitgutschrift-Antraege.

    Unterstuetzt drei Arten:
    - Haertefallregelung
    - Ehrenamt
    - Fortbildung (mit Berechnung)
    """
    form = ZeitgutschriftForm(request.POST or None, request.FILES or None)

    if request.method == "POST":
        if form.is_valid():
            antrag = form.save(commit=False)
            antrag.antragsteller = request.user.mitarbeiter

            # Art-spezifische Verarbeitung
            art = antrag.art

            if art in ("haertefall", "ehrenamt"):
                # Zeilen aus POST sammeln
                zeile_datums = request.POST.getlist("zeile_datum")
                zeile_von_zeits = request.POST.getlist("zeile_von_zeit")
                zeile_bis_zeits = request.POST.getlist("zeile_bis_zeit")

                zeilen_daten = []
                for i in range(len(zeile_datums)):
                    zeile = {
                        "datum": zeile_datums[i] if i < len(zeile_datums) else "",
                        "von_zeit": zeile_von_zeits[i] if i < len(zeile_von_zeits) else "",
                        "bis_zeit": zeile_bis_zeits[i] if i < len(zeile_bis_zeits) else "",
                    }
                    if any(zeile.values()):
                        zeilen_daten.append(zeile)

                if not zeilen_daten:
                    form.add_error(None, "Mindestens eine Zeile ist erforderlich.")
                    context = {"form": form}
                    return render(
                        request,
                        "formulare/zeitgutschrift_antrag.html",
                        context,
                    )

                antrag.zeilen_daten = zeilen_daten

            elif art in ("erkrankung_angehoerige", "erkrankung_kind", "erkrankung_betreuung"):
                from decimal import Decimal, InvalidOperation
                erkrankung_typ = request.POST.get("erkrankung_typ", "")
                datum_str = request.POST.get("erkrankung_datum", "")
                antrag.erkrankung_typ = erkrankung_typ

                if datum_str:
                    from datetime import datetime as dt
                    try:
                        erkrankung_datum = dt.strptime(datum_str, "%Y-%m-%d").date()
                        # Wochenende pruefen
                        if erkrankung_datum.weekday() >= 5:
                            wochentag = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                                         "Freitag", "Samstag", "Sonntag"][erkrankung_datum.weekday()]
                            form.add_error(None, f"Das Datum ist ein {wochentag} – kein Arbeitstag.")
                            return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                        # Feiertag pruefen
                        cal = get_feiertagskalender(request.user.mitarbeiter.standort)
                        if cal.is_holiday(erkrankung_datum):
                            from arbeitszeit.models import feiertag_name_deutsch
                            name = feiertag_name_deutsch(cal, erkrankung_datum)
                            form.add_error(None, f"Das Datum ist ein Feiertag ({name}).")
                            return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                        antrag.erkrankung_datum = erkrankung_datum
                    except ValueError:
                        form.add_error(None, "Ungaeltiges Datum.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

                if erkrankung_typ == "regulaer":
                    try:
                        wochenstunden = Decimal(request.POST.get("erkrankung_wochenstunden", ""))
                        antrag.erkrankung_wochenstunden = wochenstunden
                        antrag.erkrankung_gutschrift_stunden = (wochenstunden / 5) / 2
                    except InvalidOperation:
                        form.add_error(None, "Bitte gueltige Wochenstunden eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

                elif erkrankung_typ == "individuell":
                    try:
                        tagesstunden = Decimal(request.POST.get("erkrankung_tagesstunden", ""))
                        antrag.erkrankung_tagesstunden = tagesstunden
                        antrag.erkrankung_gutschrift_stunden = tagesstunden / 2
                    except InvalidOperation:
                        form.add_error(None, "Bitte gueltige Tagesstunden eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                else:
                    form.add_error(None, "Bitte Art der Arbeitszeit auswaehlen.")
                    return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

            elif art == "sonstige":
                try:
                    antrag.mehrarbeit_buchungsmonat = int(request.POST.get("mehrarbeit_buchungsmonat", 0))
                    antrag.mehrarbeit_buchungsjahr = int(request.POST.get("mehrarbeit_buchungsjahr", 0))
                    antrag.mehrarbeit_stunden = int(request.POST.get("mehrarbeit_stunden", 0))
                    antrag.mehrarbeit_minuten = int(request.POST.get("mehrarbeit_minuten", 0))
                    antrag.mehrarbeit_begruendung = request.POST.get("mehrarbeit_begruendung", "")
                    vorzeichen = request.POST.get("sonstige_vorzeichen", "")
                    if vorzeichen not in ("+", "-"):
                        form.add_error(None, "Bitte Plus oder Minus auswaehlen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    antrag.sonstige_vorzeichen = vorzeichen
                    if not (1 <= antrag.mehrarbeit_buchungsmonat <= 12):
                        form.add_error(None, "Bitte einen gueltigen Monat auswaehlen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if antrag.mehrarbeit_stunden == 0 and antrag.mehrarbeit_minuten == 0:
                        form.add_error(None, "Bitte Stunden oder Minuten eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if not (0 <= antrag.mehrarbeit_minuten <= 59):
                        form.add_error(None, "Minuten muessen zwischen 0 und 59 liegen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                except (ValueError, TypeError):
                    form.add_error(None, "Ungueltige Eingabe.")
                    return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

            elif art in ("mehrarbeit", "mehrarbeit_buchung", "ueberstunden_buchung", "rufbereitschaft_buchung"):
                try:
                    antrag.mehrarbeit_buchungsmonat = int(request.POST.get("mehrarbeit_buchungsmonat", 0))
                    antrag.mehrarbeit_buchungsjahr = int(request.POST.get("mehrarbeit_buchungsjahr", 0))
                    antrag.mehrarbeit_stunden = int(request.POST.get("mehrarbeit_stunden", 0))
                    antrag.mehrarbeit_minuten = int(request.POST.get("mehrarbeit_minuten", 0))
                    antrag.mehrarbeit_begruendung = request.POST.get("mehrarbeit_begruendung", "")
                    if not (1 <= antrag.mehrarbeit_buchungsmonat <= 12):
                        form.add_error(None, "Bitte einen gueltigen Monat auswaehlen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if antrag.mehrarbeit_stunden == 0 and antrag.mehrarbeit_minuten == 0:
                        form.add_error(None, "Bitte Stunden oder Minuten eingeben.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                    if not (0 <= antrag.mehrarbeit_minuten <= 59):
                        form.add_error(None, "Minuten muessen zwischen 0 und 59 liegen.")
                        return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})
                except (ValueError, TypeError):
                    form.add_error(None, "Ungueltige Eingabe.")
                    return render(request, "formulare/zeitgutschrift_antrag.html", {"form": form})

            elif art == "fortbildung" and antrag.fortbildung_aktiv:
                # Berechnung durchfuehren
                berechnung = _berechne_fortbildung(
                    request.user.mitarbeiter,
                    antrag.fortbildung_von_datum,
                    antrag.fortbildung_bis_datum,
                    antrag.fortbildung_wochenstunden_regulaer,
                )
                antrag.fortbildung_berechnung = berechnung

            # Antrag speichern
            antrag.save()

            # Belege hochladen (mit optionalem Virenscan)
            from utils.virusscanner import scan_mehrere_dateien
            belege = request.FILES.getlist("belege")
            if belege:
                alle_sauber, ergebnisse = scan_mehrere_dateien(belege)
                if not alle_sauber:
                    infizierte = [
                        e.bedrohung for e in ergebnisse if not e.sauber
                    ]
                    messages.error(
                        request,
                        f"Upload abgelehnt: Bedrohung gefunden – {', '.join(infizierte)}",
                    )
                    antrag.delete()
                    return redirect("formulare:zeitgutschrift_antrag")
            for beleg in belege:
                ZeitgutschriftBeleg.objects.create(
                    zeitgutschrift=antrag,
                    datei=beleg,
                    dateiname_original=beleg.name,
                )

            _auto_signiere_zeitgutschrift(antrag, request)

            # Workflow starten (falls aktives Template vorhanden)
            _starte_workflow_fuer_antrag("zeitgutschrift_erstellt", antrag, request.user)

            # Erfolgs-Seite
            return redirect("formulare:zeitgutschrift_erfolg", pk=antrag.pk)

        # Fehler: HTMX-Support
        if request.headers.get("HX-Request"):
            return render(
                request,
                "formulare/partials/_zeitgutschrift_felder.html",
                {"form": form},
            )

    context = {"form": form}
    return render(request, "formulare/zeitgutschrift_antrag.html", context)


@login_required
def zeitgutschrift_felder(request):
    """HTMX-View: Gibt Art-abhaengige Felder zurueck."""
    from django.utils import timezone

    art = request.GET.get("art", "")
    individ = request.GET.get("individ_bestaetigung", "")
    erkrankung_typ = request.GET.get("erkrankung_typ", "")
    form = ZeitgutschriftForm(initial={"art": art})

    heute = timezone.localdate()
    monate = [
        (1, "Januar"), (2, "Februar"), (3, "Maerz"), (4, "April"),
        (5, "Mai"), (6, "Juni"), (7, "Juli"), (8, "August"),
        (9, "September"), (10, "Oktober"), (11, "November"), (12, "Dezember"),
    ]
    jahre = list(range(heute.year - 1, heute.year + 2))

    context = {
        "form": form,
        "art": art,
        "individ": individ,
        "erkrankung_typ": erkrankung_typ,
        "monate": monate,
        "jahre": jahre,
        "aktuelles_monat": heute.month,
        "aktuelles_jahr": heute.year,
    }
    response = render(
        request,
        "formulare/partials/_zeitgutschrift_felder.html",
        context,
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
def neue_zeitgutschrift_zeile(request):
    """HTMX-View: Gibt neue leere Zeile zurueck."""
    return render(request, "formulare/partials/_zeitgutschrift_zeile.html")


@login_required
def zeitgutschrift_fortbildung_berechnen(request):
    """HTMX-View: Live-Berechnung fuer Fortbildung."""
    # Daten aus POST holen
    von_datum_str = request.POST.get("fortbildung_von_datum")
    bis_datum_str = request.POST.get("fortbildung_bis_datum")
    wochenstunden_str = request.POST.get("fortbildung_wochenstunden_regulaer")

    berechnung = None

    try:
        if von_datum_str and bis_datum_str and wochenstunden_str:
            from datetime import datetime
            von_datum = datetime.strptime(von_datum_str, "%Y-%m-%d").date()
            bis_datum = datetime.strptime(bis_datum_str, "%Y-%m-%d").date()
            wochenstunden = float(wochenstunden_str)

            berechnung = _berechne_fortbildung(
                request.user.mitarbeiter,
                von_datum,
                bis_datum,
                wochenstunden,
            )
    except (ValueError, AttributeError):
        pass

    context = {"berechnung": berechnung}
    return render(
        request,
        "formulare/partials/_fortbildung_berechnung.html",
        context,
    )


@login_required
def zeitgutschrift_datum_pruefen(request):
    """HTMX-View: Prueft ob ein Datum ein gueltiger Arbeitstag ist (kein Wochenende/Feiertag)."""
    from datetime import datetime as dt

    datum_str = request.POST.get("erkrankung_datum", "")
    fehler = None
    warnung = None

    if datum_str:
        try:
            datum = dt.strptime(datum_str, "%Y-%m-%d").date()
            mitarbeiter = request.user.mitarbeiter

            if datum.weekday() >= 5:
                wochentag = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                             "Freitag", "Samstag", "Sonntag"][datum.weekday()]
                fehler = f"{datum.strftime('%d.%m.%Y')} ist ein {wochentag} – kein Arbeitstag."
            else:
                cal = get_feiertagskalender(mitarbeiter.standort)
                if cal.is_holiday(datum):
                    from arbeitszeit.models import feiertag_name_deutsch
                    name = feiertag_name_deutsch(cal, datum)
                    fehler = f"{datum.strftime('%d.%m.%Y')} ist ein Feiertag ({name})."
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_erkrankung_datum_pruefung.html",
        {"fehler": fehler},
    )


@login_required
def zeitgutschrift_erkrankung_berechnen(request):
    """HTMX-View: Live-Berechnung der Zeitgutschrift fuer Erkrankung eines Angehoerigen."""
    from decimal import Decimal, InvalidOperation

    erkrankung_typ = request.POST.get("erkrankung_typ", "")
    gutschrift = None
    fehler = None

    try:
        if erkrankung_typ == "regulaer":
            wochenstunden = Decimal(request.POST.get("erkrankung_wochenstunden", ""))
            tageszeit = wochenstunden / 5
            gutschrift = tageszeit / 2
        elif erkrankung_typ == "individuell":
            tagesstunden = Decimal(request.POST.get("erkrankung_tagesstunden", ""))
            gutschrift = tagesstunden / 2
    except InvalidOperation:
        fehler = "Bitte gueltige Stunden eingeben."

    gutschrift_hmin = _dezimal_zu_hmin(float(gutschrift)) if gutschrift is not None else None
    context = {"gutschrift": gutschrift, "gutschrift_hmin": gutschrift_hmin, "fehler": fehler}
    return render(
        request,
        "formulare/partials/_erkrankung_berechnung.html",
        context,
    )


@login_required
def zeitgutschrift_detail(request, pk):
    """Detail-Ansicht fuer Genehmiger, Antragsteller und Workflow-Bearbeiter."""
    antrag = get_object_or_404(Zeitgutschrift, pk=pk)

    # Berechtigungspruefung: Antragsteller oder Genehmiger
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_genehmiger = antrag.antragsteller in berechtigte_ma

    # Workflow-Berechtigung: Hat User einen Task fuer diesen Antrag?
    hat_workflow_task = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        # Direkt zugewiesene Tasks
        hat_workflow_task = WorkflowTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung"],
            zugewiesen_an_user=request.user
        ).exists()

        # Oder Tasks an die Stelle des Users
        if not hat_workflow_task and hasattr(request.user, "hr_mitarbeiter"):
            stelle = request.user.hr_mitarbeiter.stelle
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_stelle=stelle
            ).exists()

        # Oder Tasks an ein Team, in dem der User Mitglied ist
        if not hat_workflow_task:
            from formulare.models import TeamQueue
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_team__in=user_teams
            ).exists()

    # Team-Queue-Berechtigung: Hat User den Antrag geclaimed?
    hat_antrag_geclaimed = antrag.claimed_von == request.user

    # Staff und Superuser haben immer Lesezugriff
    ist_admin = request.user.is_superuser or request.user.is_staff

    if not (ist_antragsteller or ist_genehmiger or hat_workflow_task
            or hat_antrag_geclaimed or ist_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Optional: aus Team-Queue geoeffnet → queue_task fuer Erledigen-Button
    queue_task = None
    queue_task_pk = request.GET.get("queue_task")
    if queue_task_pk:
        from workflow.models import WorkflowTask
        try:
            queue_task = WorkflowTask.objects.select_related("step").get(
                pk=queue_task_pk,
                claimed_von=request.user,
                status="in_bearbeitung",
            )
        except WorkflowTask.DoesNotExist:
            pass

    context = {
        "antrag": antrag,
        "ist_genehmiger": ist_genehmiger,
        "ist_antragsteller": ist_antragsteller,
        "queue_task": queue_task,
    }
    return render(request, "formulare/zeitgutschrift_detail.html", context)


@login_required
def zeitgutschrift_erfolg(request, pk):
    """Erfolgs-Seite nach Antragstellung."""
    antrag = get_object_or_404(Zeitgutschrift, pk=pk)

    # Berechtigungspruefung: Antragsteller oder Genehmiger
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    if (
        antrag.antragsteller.user != request.user
        and antrag.antragsteller not in berechtigte_ma
    ):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    context = {
        "antrag": antrag,
        "antrag_signatur": _hole_antrag_signatur("zeitgutschrift", antrag.pk),
    }
    return render(request, "formulare/zeitgutschrift_erfolg.html", context)


@login_required
def zeitgutschrift_pdf(request, pk):
    """PDF-Download fuer Zeitgutschrift-Antrag."""
    antrag = get_object_or_404(Zeitgutschrift, pk=pk)

    # Berechtigungspruefung: Antragsteller, Genehmiger oder Workflow-Bearbeiter
    berechtigte_ma = _offene_antraege_fuer_user(request.user)
    ist_antragsteller = antrag.antragsteller.user == request.user
    ist_genehmiger = antrag.antragsteller in berechtigte_ma

    # Workflow-Berechtigung: Hat User einen Task fuer diesen Antrag?
    hat_workflow_task = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        # Direkt zugewiesene Tasks
        hat_workflow_task = WorkflowTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung"],
            zugewiesen_an_user=request.user
        ).exists()

        # Oder Tasks an die Stelle des Users
        if not hat_workflow_task and hasattr(request.user, "hr_mitarbeiter"):
            stelle = request.user.hr_mitarbeiter.stelle
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_stelle=stelle
            ).exists()

        # Oder Tasks an ein Team, in dem der User Mitglied ist
        if not hat_workflow_task:
            from formulare.models import TeamQueue
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_workflow_task = WorkflowTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_team__in=user_teams
            ).exists()

    # Team-Queue-Berechtigung: Hat User den Antrag geclaimed?
    hat_antrag_geclaimed = antrag.claimed_von == request.user

    ist_admin = request.user.is_superuser or request.user.is_staff

    if not (ist_antragsteller or ist_genehmiger or hat_workflow_task
            or hat_antrag_geclaimed or ist_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Bei Reisezeit-Tagebuch: Tagebuch-Daten fuer PDF aufbereiten
    import datetime as _dt
    tagebuch_tage = []
    tagebuch_gesamt_min = 0
    tagebuch_gesamt_hmin = ""
    dienstreise = None

    if antrag.art == "reisezeit_tagebuch":
        try:
            dienstreise = antrag.reisezeit_dienstreise
        except Exception:
            dienstreise = None

        if dienstreise:
            WOCHENTAGE = [
                "Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag",
            ]
            mitarbeiter = dienstreise.antragsteller
            aktuell = dienstreise.von_datum
            while aktuell <= dienstreise.bis_datum:
                eintraege = dienstreise.tagebuch_eintraege.filter(datum=aktuell)
                regel_minuten = _regelarbeitszeit_fuer_tag(mitarbeiter, aktuell)
                eintraege_info = []
                for e in eintraege:
                    gutschrift_min = _gutschrift_minuten_fuer_eintrag(
                        e, regel_minuten
                    )
                    eintraege_info.append({
                        "eintrag": e,
                        "gutschrift_min": gutschrift_min,
                        "gutschrift_hmin": (
                            _minuten_zu_hmin(gutschrift_min)
                            if e.fall != 1 else "-"
                        ),
                    })
                tagebuch_tage.append({
                    "datum": aktuell,
                    "wochentag": WOCHENTAGE[aktuell.weekday()],
                    "ist_wochenende": aktuell.weekday() >= 5,
                    "regel_minuten": regel_minuten,
                    "eintraege": eintraege_info,
                })
                aktuell += _dt.timedelta(days=1)

            tagebuch_gesamt_min = _berechne_tagebuch_gesamt(
                dienstreise, mitarbeiter
            )
            tagebuch_gesamt_hmin = _minuten_zu_hmin(tagebuch_gesamt_min)

    # PDF mit WeasyPrint generieren
    try:
        from weasyprint import HTML
        import datetime as dt

        zg_workflow_tasks = []
        if antrag.workflow_instance:
            from workflow.models import WorkflowTask
            zg_workflow_tasks = list(
                WorkflowTask.objects
                .filter(instance=antrag.workflow_instance)
                .select_related("step", "erledigt_von")
                .order_by("step__reihenfolge")
            )

        html_string = render_to_string(
            "formulare/pdf/zeitgutschrift_pdf.html",
            {
                "antrag": antrag,
                "dienstreise": dienstreise,
                "tagebuch_tage": tagebuch_tage,
                "tagebuch_gesamt_min": tagebuch_gesamt_min,
                "tagebuch_gesamt_hmin": tagebuch_gesamt_hmin,
                "workflow_tasks": zg_workflow_tasks,
                "now": dt.datetime.now(),
            },
        )

        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()
        dateiname_zg = f"zeitgutschrift_{antrag.id}.pdf"
        unterzeichner_zg = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
        pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner_zg, dateiname_zg)

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="zeitgutschrift_{antrag.id}.pdf"'
        )
        return response
    except ImportError:
        return HttpResponse(
            "WeasyPrint nicht installiert. Bitte 'weasyprint' installieren.",
            status=500,
        )


# ---------------------------------------------------------------------------
# Dienstreise-Tagebuch
# ---------------------------------------------------------------------------

def _regelarbeitszeit_fuer_tag(mitarbeiter, datum):
    """Regelarbeitszeit in Minuten fuer einen bestimmten Tag.

    Beruecksichtigt Arbeitszeitvereinbarung und Mehrwochenmodelle.
    Gibt 0 zurueck fuer Wochenenden oder wenn keine Vereinbarung vorhanden.
    """
    import datetime as _dt

    if datum.weekday() >= 5:
        return 0

    vereinbarung = mitarbeiter.get_aktuelle_vereinbarung(stichtag=datum)
    if not vereinbarung:
        return 0

    if vereinbarung.arbeitszeit_typ == "regelmaessig" and vereinbarung.wochenstunden:
        return round(float(vereinbarung.wochenstunden) * 60 / 5)

    if vereinbarung.arbeitszeit_typ == "individuell":
        wt_map = {
            0: "montag", 1: "dienstag", 2: "mittwoch",
            3: "donnerstag", 4: "freitag",
        }
        wochentag = wt_map.get(datum.weekday())
        woche = vereinbarung.zyklus_woche_fuer_datum(datum) or 1
        ta = vereinbarung.tagesarbeitszeiten.filter(
            wochentag=wochentag, woche=woche
        ).first()
        if ta and ta.zeitwert:
            return (ta.zeitwert // 100) * 60 + (ta.zeitwert % 100)

    return 0


def _gutschrift_minuten_fuer_eintrag(eintrag, regel_minuten):
    """Gutschrift in Minuten fuer einen einzelnen Tagebucheintrag.

    Fall 1: 0 (Terminalerfassung genuegt)
    Fall 2: tatsaechliche Zeit - Regelarbeitszeit (kann negativ sein)
    Fall 3: tatsaechliche Zeit / 3
    """
    if eintrag.fall == 1:
        return 0
    if eintrag.fall == 2:
        return eintrag.dauer_minuten - regel_minuten
    if eintrag.fall == 3:
        return round(eintrag.dauer_minuten / 3)
    return 0


def _berechne_tagebuch_gesamt(antrag, mitarbeiter):
    """Gesamtgutschrift aller Tagebucheintraege in Minuten (kann negativ sein)."""
    total = 0
    for eintrag in antrag.tagebuch_eintraege.all():
        regel = _regelarbeitszeit_fuer_tag(mitarbeiter, eintrag.datum)
        total += _gutschrift_minuten_fuer_eintrag(eintrag, regel)
    return total


def _minuten_zu_hmin(minuten):
    """Formatiert Minuten (auch negativ) als '+Xh MMmin' oder '-Xh MMmin'."""
    vorzeichen = "-" if minuten < 0 else "+"
    abs_min = abs(minuten)
    h = abs_min // 60
    m = abs_min % 60
    return f"{vorzeichen}{h}h {m:02d}min"


@login_required
def dienstreise_tagebuch_auswahl(request):
    """Auswahl eines genehmigten Dienstreiseantrags fuer das Tagebuch.

    Zeigt Pulldown der genehmigten Dienstreisen des Users.
    Nach Auswahl Weiterleitung zum Tagebuch.
    """
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return redirect("arbeitszeit:dashboard")

    antraege = Dienstreiseantrag.objects.filter(
        antragsteller=mitarbeiter,
        status__in=["genehmigt", "erledigt"],
    ).order_by("-von_datum")

    if request.method == "POST":
        antrag_pk = request.POST.get("dienstreise_pk")
        if antrag_pk:
            return redirect("formulare:dienstreise_tagebuch", pk=antrag_pk)

    return render(
        request,
        "formulare/dienstreise_tagebuch_auswahl.html",
        {"antraege": antraege},
    )


@login_required
def dienstreise_tagebuch(request, pk):
    """Tagebuch-Hauptseite fuer eine Dienstreise.

    Zugaenglich fuer Antragsteller (Lesen + Schreiben) und
    Pruefer mit aktivem Workflow-Task (nur Lesen).
    """
    import datetime as _dt
    from formulare.models import TeamQueue

    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    # Berechtigungspruefung
    ist_antragsteller = (
        hasattr(request.user, "mitarbeiter")
        and antrag.antragsteller == request.user.mitarbeiter
    )
    hat_pruefer_zugang = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask as WfTask
        # Offen, in Bearbeitung UND erledigt – damit auch nach Abschluss Zugang besteht
        alle_stati = ["offen", "in_bearbeitung", "erledigt"]
        hat_pruefer_zugang = WfTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=alle_stati,
            zugewiesen_an_user=request.user,
        ).exists()
        if not hat_pruefer_zugang and hasattr(request.user, "hr_mitarbeiter"):
            stelle = getattr(request.user.hr_mitarbeiter, "stelle", None)
            if stelle:
                hat_pruefer_zugang = WfTask.objects.filter(
                    instance=antrag.workflow_instance,
                    status__in=alle_stati,
                    zugewiesen_an_stelle=stelle,
                ).exists()
        if not hat_pruefer_zugang:
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_pruefer_zugang = WfTask.objects.filter(
                instance=antrag.workflow_instance,
                zugewiesen_an_team__in=user_teams,
            ).exists()
    # Auch Claim-Zugang beruecksichtigen
    if not hat_pruefer_zugang:
        hat_pruefer_zugang = antrag.claimed_von == request.user

    # Superuser haben immer Zugang
    if request.user.is_superuser or request.user.is_staff:
        hat_pruefer_zugang = True

    if not (ist_antragsteller or hat_pruefer_zugang):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    mitarbeiter = antrag.antragsteller

    WOCHENTAGE = [
        "Montag", "Dienstag", "Mittwoch", "Donnerstag",
        "Freitag", "Samstag", "Sonntag",
    ]

    tage = []
    aktuell = antrag.von_datum
    while aktuell <= antrag.bis_datum:
        eintraege = antrag.tagebuch_eintraege.filter(datum=aktuell)
        regel_minuten = _regelarbeitszeit_fuer_tag(mitarbeiter, aktuell)
        eintraege_info = []
        for e in eintraege:
            gutschrift_min = _gutschrift_minuten_fuer_eintrag(e, regel_minuten)
            eintraege_info.append({
                "eintrag": e,
                "gutschrift_min": gutschrift_min,
                "gutschrift_hmin": (
                    _minuten_zu_hmin(gutschrift_min) if e.fall != 1 else "-"
                ),
            })
        tage.append({
            "datum": aktuell,
            "wochentag": WOCHENTAGE[aktuell.weekday()],
            "ist_wochenende": aktuell.weekday() >= 5,
            "regel_minuten": regel_minuten,
            "eintraege": eintraege_info,
        })
        aktuell += _dt.timedelta(days=1)

    gesamt_min = _berechne_tagebuch_gesamt(antrag, mitarbeiter)
    gesamt_hmin = _minuten_zu_hmin(gesamt_min)

    bestehende_gutschrift = antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).first()

    return render(
        request,
        "formulare/dienstreise_tagebuch.html",
        {
            "antrag": antrag,
            "tage": tage,
            "gesamt_min": gesamt_min,
            "gesamt_hmin": gesamt_hmin,
            "bestehende_gutschrift": bestehende_gutschrift,
            "ist_antragsteller": ist_antragsteller,
        },
    )


@login_required
def dienstreise_tagebuch_eintrag_neu(request, pk):
    """Einen oder mehrere Tagebucheintraege fuer einen Tag speichern.

    POST: Alle ausgefuellten Zeilen des Formulars speichern.
    GET:  Weiterleitung zur Tagebuch-Uebersicht.
    """
    import datetime as _dt

    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return HttpResponse(status=403)

    antrag = get_object_or_404(
        Dienstreiseantrag, pk=pk, antragsteller=mitarbeiter
    )

    datum_str = request.POST.get("datum", "")
    try:
        datum = _dt.date.fromisoformat(datum_str)
    except ValueError:
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    if request.method != "POST":
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    # Alle Zeilen einlesen (mehrere Eintraege pro Submit moeglich)
    falls = request.POST.getlist("fall")
    von_zeiten = request.POST.getlist("von_zeit")
    bis_zeiten = request.POST.getlist("bis_zeit")
    bemerkungen = request.POST.getlist("bemerkung")

    fehler = []
    gespeichert = 0

    for i in range(len(falls)):
        fall_str = falls[i] if i < len(falls) else ""
        von_zeit_str = von_zeiten[i] if i < len(von_zeiten) else ""
        bis_zeit_str = bis_zeiten[i] if i < len(bis_zeiten) else ""
        bemerkung = bemerkungen[i] if i < len(bemerkungen) else ""

        # Leere Zeilen ueberspringen
        if not fall_str and not von_zeit_str and not bis_zeit_str:
            continue

        zeile_nr = i + 1
        if not fall_str or fall_str not in ("1", "2", "3"):
            fehler.append(f"Zeile {zeile_nr}: Bitte einen Fall auswaehlen.")
            continue
        if not von_zeit_str:
            fehler.append(f"Zeile {zeile_nr}: Bitte Von-Zeit angeben.")
            continue
        if not bis_zeit_str:
            fehler.append(f"Zeile {zeile_nr}: Bitte Bis-Zeit angeben.")
            continue

        try:
            von_h, von_m = map(int, von_zeit_str.split(":"))
            bis_h, bis_m = map(int, bis_zeit_str.split(":"))
            von_zeit = _dt.time(von_h, von_m)
            bis_zeit = _dt.time(bis_h, bis_m)
            if bis_zeit <= von_zeit:
                fehler.append(
                    f"Zeile {zeile_nr}: Bis-Zeit muss nach Von-Zeit liegen."
                )
                continue
        except (ValueError, AttributeError):
            fehler.append(f"Zeile {zeile_nr}: Ungueltige Zeitangabe (HH:MM).")
            continue

        ReisezeitTagebuchEintrag.objects.create(
            dienstreise=antrag,
            datum=datum,
            fall=int(fall_str),
            von_zeit=von_zeit,
            bis_zeit=bis_zeit,
            bemerkung=bemerkung,
        )
        gespeichert += 1

    if fehler:
        for f in fehler:
            messages.error(request, f)
    elif gespeichert > 0:
        messages.success(
            request,
            f"{gespeichert} Eintrag{'e' if gespeichert > 1 else ''} gespeichert."
        )

    return redirect(
        reverse("formulare:dienstreise_tagebuch", args=[antrag.pk])
        + f"#tag-{datum.isoformat()}"
    )


@login_required
def dienstreise_tagebuch_eintrag_loeschen(request, eintrag_pk):
    """Tagebucheintrag loeschen."""
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return redirect("arbeitszeit:dashboard")

    eintrag = get_object_or_404(
        ReisezeitTagebuchEintrag,
        pk=eintrag_pk,
        dienstreise__antragsteller=mitarbeiter,
    )
    antrag = eintrag.dienstreise
    datum = eintrag.datum
    if request.method == "POST":
        eintrag.delete()
    return redirect(
        reverse("formulare:dienstreise_tagebuch", args=[antrag.pk])
        + f"#tag-{datum.isoformat()}"
    )


@login_required
def dienstreise_gutschrift_beantragen(request, pk):
    """Gutschrift aus Dienstreise-Tagebuch beantragen.

    Erstellt einen Zeitgutschrift-Antrag aus allen Tagebucheintraegen
    (Fall 2 + Fall 3). Nur per POST erlaubt.
    """
    try:
        mitarbeiter = request.user.mitarbeiter
    except AttributeError:
        return redirect("arbeitszeit:dashboard")

    antrag = get_object_or_404(
        Dienstreiseantrag, pk=pk, antragsteller=mitarbeiter
    )

    if request.method != "POST":
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    # Keine doppelten Antraege
    if antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).exists():
        messages.warning(request, "Es wurde bereits ein Gutschrift-Antrag gestellt.")
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    gesamt_min = _berechne_tagebuch_gesamt(antrag, mitarbeiter)

    if gesamt_min == 0:
        messages.error(
            request,
            "Keine Gutschrift berechenbar – bitte Eintraege pruefen.",
        )
        return redirect("formulare:dienstreise_tagebuch", pk=pk)

    stunden = abs(gesamt_min) // 60
    minuten = abs(gesamt_min) % 60
    vorzeichen = "+" if gesamt_min >= 0 else "-"

    buchungsmonat = antrag.von_datum.month
    buchungsjahr = antrag.von_datum.year

    von_str = antrag.von_datum.strftime("%d.%m.%Y")
    bis_str = antrag.bis_datum.strftime("%d.%m.%Y")

    zg = Zeitgutschrift.objects.create(
        antragsteller=mitarbeiter,
        art="reisezeit_tagebuch",
        status="beantragt",
        reisezeit_dienstreise=antrag,
        mehrarbeit_buchungsmonat=buchungsmonat,
        mehrarbeit_buchungsjahr=buchungsjahr,
        mehrarbeit_stunden=stunden,
        mehrarbeit_minuten=minuten,
        sonstige_vorzeichen=vorzeichen,
        mehrarbeit_begruendung=(
            f"Reisezeit-Tagebuch fuer Dienstreise nach {antrag.ziel} "
            f"({von_str} - {bis_str})"
        ),
    )

    # Workflow starten
    _starte_workflow_fuer_antrag("zeitgutschrift_erstellt", zg, request.user)

    messages.success(
        request,
        f"Gutschrift-Antrag wurde gestellt ({_minuten_zu_hmin(gesamt_min)}).",
    )
    return redirect("formulare:dienstreise_tagebuch", pk=pk)


@login_required
def dienstreise_detail(request, pk):
    """Detail-Ansicht fuer einen Dienstreiseantrag.

    Zugaenglich fuer: Antragsteller, Vorgesetzte (Workflow-Task),
    Mitglieder des Reisemanagement-Teams mit aktivem Task.
    Zeigt alle Antragsdaten sowie Tagebuch-Eintraege falls vorhanden.
    Ermoeglicht das Erledigen via Team-Stapel (queue_task-Parameter).
    """
    from formulare.models import TeamQueue

    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    ist_antragsteller = antrag.antragsteller.user == request.user

    # Berechtigung via Workflow-Task
    hat_workflow_task = False
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask as WfTask
        hat_workflow_task = WfTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung"],
            zugewiesen_an_user=request.user,
        ).exists()

        if not hat_workflow_task and hasattr(request.user, "hr_mitarbeiter"):
            stelle = getattr(request.user.hr_mitarbeiter, "stelle", None)
            if stelle:
                hat_workflow_task = WfTask.objects.filter(
                    instance=antrag.workflow_instance,
                    status__in=["offen", "in_bearbeitung"],
                    zugewiesen_an_stelle=stelle,
                ).exists()

        if not hat_workflow_task:
            user_teams = TeamQueue.objects.filter(mitglieder=request.user)
            hat_workflow_task = WfTask.objects.filter(
                instance=antrag.workflow_instance,
                status__in=["offen", "in_bearbeitung"],
                zugewiesen_an_team__in=user_teams,
            ).exists()

    # Berechtigung via Claim (alter Weg)
    hat_geclaimed = antrag.claimed_von == request.user

    if not (ist_antragsteller or hat_workflow_task or hat_geclaimed):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Optional: aus Team-Stapel geoeffnet
    queue_task = None
    queue_task_pk = request.GET.get("queue_task")
    if queue_task_pk:
        from workflow.models import WorkflowTask as WfTask
        try:
            queue_task = WfTask.objects.select_related("step").get(
                pk=queue_task_pk,
                claimed_von=request.user,
                status="in_bearbeitung",
            )
        except Exception:
            pass

    # Tagebuch-Eintraege und Gutschrift
    tagebuch_eintraege = antrag.tagebuch_eintraege.all().order_by("datum", "von_zeit")
    reisezeit_gutschrift = antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).first()

    return render(
        request,
        "formulare/dienstreise_detail.html",
        {
            "antrag": antrag,
            "ist_antragsteller": ist_antragsteller,
            "queue_task": queue_task,
            "tagebuch_eintraege": tagebuch_eintraege,
            "reisezeit_gutschrift": reisezeit_gutschrift,
            "antrag_signatur": _hole_antrag_signatur("dienstreiseantrag", antrag.pk),
        },
    )


@login_required
def dienstreise_pdf(request, pk):
    """PDF-Ausdruck eines Dienstreiseantrags inkl. Tagebuch und Gutschrift."""
    import datetime as _dt
    from formulare.models import TeamQueue

    antrag = get_object_or_404(Dienstreiseantrag, pk=pk)

    ist_antragsteller = (
        hasattr(request.user, "mitarbeiter")
        and antrag.antragsteller == request.user.mitarbeiter
    )
    hat_zugang = ist_antragsteller or antrag.claimed_von == request.user
    if not hat_zugang and antrag.workflow_instance:
        from workflow.models import WorkflowTask as WfTask
        user_teams = TeamQueue.objects.filter(mitglieder=request.user)
        hat_zugang = WfTask.objects.filter(
            instance=antrag.workflow_instance,
            status__in=["offen", "in_bearbeitung", "erledigt"],
        ).filter(
            zugewiesen_an_user=request.user,
        ).exists() or WfTask.objects.filter(
            instance=antrag.workflow_instance,
            zugewiesen_an_team__in=user_teams,
        ).exists()

    if not hat_zugang:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung")

    # Tagebuch mit Gutschrift-Berechnung aufbereiten
    mitarbeiter = antrag.antragsteller
    WOCHENTAGE = [
        "Montag", "Dienstag", "Mittwoch", "Donnerstag",
        "Freitag", "Samstag", "Sonntag",
    ]
    tage = []
    aktuell = antrag.von_datum
    while aktuell <= antrag.bis_datum:
        eintraege = antrag.tagebuch_eintraege.filter(datum=aktuell)
        regel_minuten = _regelarbeitszeit_fuer_tag(mitarbeiter, aktuell)
        eintraege_info = []
        for e in eintraege:
            gutschrift_min = _gutschrift_minuten_fuer_eintrag(e, regel_minuten)
            eintraege_info.append({
                "eintrag": e,
                "gutschrift_min": gutschrift_min,
                "gutschrift_hmin": (
                    _minuten_zu_hmin(gutschrift_min) if e.fall != 1 else "-"
                ),
            })
        tage.append({
            "datum": aktuell,
            "wochentag": WOCHENTAGE[aktuell.weekday()],
            "ist_wochenende": aktuell.weekday() >= 5,
            "regel_minuten": regel_minuten,
            "eintraege": eintraege_info,
        })
        aktuell += _dt.timedelta(days=1)

    gesamt_min = _berechne_tagebuch_gesamt(antrag, mitarbeiter)
    gesamt_hmin = _minuten_zu_hmin(gesamt_min)
    reisezeit_gutschrift = antrag.reisezeit_gutschriften.filter(
        status__in=["beantragt", "genehmigt", "in_bearbeitung", "erledigt"]
    ).first()

    dr_workflow_tasks = []
    if antrag.workflow_instance:
        from workflow.models import WorkflowTask
        dr_workflow_tasks = list(
            WorkflowTask.objects
            .filter(instance=antrag.workflow_instance)
            .select_related("step", "erledigt_von")
            .order_by("step__reihenfolge")
        )

    try:
        from weasyprint import HTML
        import datetime as dt

        html_string = render_to_string(
            "formulare/pdf/dienstreise_pdf.html",
            {
                "antrag": antrag,
                "tage": tage,
                "gesamt_min": gesamt_min,
                "gesamt_hmin": gesamt_hmin,
                "reisezeit_gutschrift": reisezeit_gutschrift,
                "workflow_tasks": dr_workflow_tasks,
                "now": dt.datetime.now(),
            },
        )
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()
        dateiname_dr = f"dienstreise_{antrag.pk}_{antrag.ziel}.pdf"
        unterzeichner_dr = _sammle_workflow_unterzeichner(antrag, antrag.antragsteller.user)
        pdf = _signiere_pdf_alle_unterzeichner(pdf, unterzeichner_dr, dateiname_dr)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="{dateiname_dr}"'
        )
        return response
    except ImportError:
        return HttpResponse(
            "WeasyPrint nicht installiert.",
            status=500,
        )
