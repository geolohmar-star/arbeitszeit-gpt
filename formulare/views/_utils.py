# -*- coding: utf-8 -*-
"""Private Hilfsfunktionen fuer alle formulare-Views."""

import logging
from datetime import date as date_type, timedelta

logger = logging.getLogger(__name__)

# Wochentag-Mapping (weekday()-Index -> Feldname in Tagesarbeitszeit)
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


def _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum):
    """Gibt die aktive Arbeitszeitvereinbarung zum Datum zurueck oder None."""
    from arbeitszeit.models import Arbeitszeitvereinbarung
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
    from formulare.models import TeamQueue

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
