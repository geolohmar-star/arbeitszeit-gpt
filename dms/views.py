"""DMS-Views: Dokumentenliste, Upload, Download, Zugriffsverwaltung, OnlyOffice-Integration."""
import json
import logging
import mimetypes

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models as db_models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from guardian.shortcuts import assign_perm, remove_perm

from .forms import DokumentKategorieForm, DokumentNeuForm, DokumentSucheForm, DokumentUploadForm, PaperlessWorkflowRegelForm, PersoenlicheAblageFreigabeForm, PersoenlicheAblageUploadForm, ZugriffsantragForm
from .models import DAUER_OPTIONEN, ApiToken, Dokument, DokumentKategorie, DokumentVersion, DokumentZugriffsschluessel, PaperlessWorkflowRegel, ZugriffsProtokoll
from workflow.models import WorkflowTemplate
from .services import lade_dokument, speichere_dokument, suchvektor_befuellen

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _get_user_orgeinheit_ids(user):
    """Gibt die OrgEinheit-IDs zurueck zu denen der User gehoert.

    Kette: user -> hr_mitarbeiter -> stelle -> org_einheit
    """
    try:
        ma = user.hr_mitarbeiter
        if ma.stelle and ma.stelle.org_einheit_id:
            return {ma.stelle.org_einheit_id}
    except Exception:
        pass
    return set()


def _get_ip(request):
    """Ermittelt die Client-IP."""
    ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip:
        return ip.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _protokolliere(request, dokument, aktion, notiz=""):
    """Schreibt einen ZugriffsProtokoll-Eintrag."""
    ZugriffsProtokoll.objects.create(
        dokument=dokument,
        user=request.user if request.user.is_authenticated else None,
        aktion=aktion,
        ip_adresse=_get_ip(request),
        notiz=notiz,
    )


def _hat_aktiven_zugriffsschluessel(user, dokument):
    """Prueft ob der User einen aktiven (gueltigen) Zugriffsschluessel hat."""
    return DokumentZugriffsschluessel.objects.filter(
        user=user,
        dokument=dokument,
        status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
        gueltig_bis__gt=timezone.now(),
    ).exists()


def _ist_azv_team_mitglied(user):
    """Gibt True zurueck wenn der User im AZV-Team (kuerzel='azv') ist."""
    from formulare.models import TeamQueue
    return TeamQueue.objects.filter(kuerzel="azv", mitglieder=user).exists()


def _ist_azv_dokument(dokument):
    """Gibt True zurueck wenn das Dokument zur Kategorie 'Arbeitszeitvereinbarungen' gehoert."""
    if not dokument.kategorie_id:
        return False
    from dms.models import DokumentKategorie
    try:
        kat = DokumentKategorie.objects.get(pk=dokument.kategorie_id)
        return kat.name == "Arbeitszeitvereinbarungen"
    except DokumentKategorie.DoesNotExist:
        return False


def _darf_sensibel_zugreifen(request, dokument):
    """Gibt True zurueck wenn der User auf ein sensibles Dokument zugreifen darf.

    Reihenfolge der Pruefung:
    1. Superuser: immer Zugriff
    2. Mitglied der Eigentuemer-OrgEinheit: direkter Zugriff ohne Schluessel
    3. Explizit freigegebene User (sichtbar_fuer)
    4. AZV-Team-Mitglied bei AZV-Dokumenten (dynamisch, unabhaengig von sichtbar_fuer)
    5. Alle anderen: nur mit aktivem Zugriffsschluessel
    """
    if not request.user.is_authenticated:
        return False
    # Superuser: immer Zugriff (keine Einschraenkung fuer Sysadmin)
    if request.user.is_superuser:
        return True
    # Eigentuemer eines persoenlichen Dokuments hat immer Zugriff
    if dokument.ist_persoenlich and dokument.erstellt_von_id == request.user.pk:
        return True
    # Mitglied der Eigentuemer-OrgEinheit: direkter Zugriff ohne Schluessel
    if dokument.eigentuemereinheit_id:
        if dokument.eigentuemereinheit_id in _get_user_orgeinheit_ids(request.user):
            return True
    # Explizit freigegebene User (sichtbar_fuer) haben ebenfalls Zugriff
    if dokument.sichtbar_fuer.filter(pk=request.user.pk).exists():
        return True
    # AZV-Team-Mitglieder haben automatisch Zugriff auf AZV-Dokumente (dynamisch)
    if _ist_azv_dokument(dokument) and _ist_azv_team_mitglied(request.user):
        return True
    # Workflow-Teilnehmer: User hat offenen Task auf diesem Dokument
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowInstance, WorkflowTask
    dok_ct = ContentType.objects.get_for_model(dokument)
    laufende_instanzen = WorkflowInstance.objects.filter(
        content_type=dok_ct,
        object_id=dokument.pk,
        status=WorkflowInstance.STATUS_LAUFEND,
    )
    for instanz in laufende_instanzen:
        offene_tasks = instanz.tasks.filter(
            status__in=[WorkflowTask.STATUS_OFFEN, WorkflowTask.STATUS_IN_BEARBEITUNG]
        )
        for task in offene_tasks:
            # Direkt an User zugewiesen?
            if task.zugewiesen_an_user_id == request.user.pk:
                return True
            # An die Stelle des Users zugewiesen?
            try:
                stelle = request.user.hr_mitarbeiter.stelle
                if task.zugewiesen_an_stelle_id == stelle.pk:
                    return True
            except Exception:
                pass
            # An ein Team zugewiesen, in dem der User ist?
            if task.zugewiesen_an_team_id:
                from hr.models import Team
                if Team.objects.filter(
                    pk=task.zugewiesen_an_team_id,
                    mitarbeiter__user=request.user,
                ).exists():
                    return True
    # Alle anderen (auch staff): nur mit aktivem Zugriffsschluessel
    return _hat_aktiven_zugriffsschluessel(request.user, dokument)


# ---------------------------------------------------------------------------
# Dokument-Liste
# ---------------------------------------------------------------------------

@login_required
def dokument_liste(request):
    """Listet alle fuer den User sichtbaren Dokumente mit Suche."""
    form = DokumentSucheForm(request.GET or None)
    # Persoenliche Dokumente werden in "Meine Ablage" angezeigt, nicht hier
    qs = Dokument.objects.filter(ist_persoenlich=False).select_related("kategorie", "eigentuemereinheit").prefetch_related("tags")

    # Sensible Dokumente: Sichtbarkeit nach Rolle und OrgEinheit-Zugehoerigkeit
    if not request.user.is_superuser and not request.user.is_staff:
        user_org_ids = _get_user_orgeinheit_ids(request.user)
        ist_azv = _ist_azv_team_mitglied(request.user)

        # Basis: offene Dokumente
        q_filter = db_models.Q(klasse="offen")

        # Sensible Dokumente der eigenen Abteilung
        if user_org_ids:
            q_filter |= db_models.Q(klasse="sensibel", eigentuemereinheit_id__in=user_org_ids)

        # Sensible Dokumente aus sichtbar_fuer
        q_filter |= db_models.Q(klasse="sensibel", sichtbar_fuer=request.user)

        # AZV-Team-Mitglieder sehen alle AZV-Dokumente (dynamisch)
        if ist_azv:
            from dms.models import DokumentKategorie
            azv_kat = DokumentKategorie.objects.filter(name="Arbeitszeitvereinbarungen").first()
            if azv_kat:
                q_filter |= db_models.Q(klasse="sensibel", kategorie=azv_kat)

        # Dokumente mit laufendem Workflow auf dem der User einen offenen Task hat
        from django.contrib.contenttypes.models import ContentType
        from workflow.models import WorkflowInstance, WorkflowTask
        dok_ct = ContentType.objects.get_for_model(Dokument)
        workflow_dok_ids = (
            WorkflowInstance.objects
            .filter(
                content_type=dok_ct,
                status=WorkflowInstance.STATUS_LAUFEND,
                tasks__status__in=[WorkflowTask.STATUS_OFFEN, WorkflowTask.STATUS_IN_BEARBEITUNG],
            )
            .filter(
                db_models.Q(tasks__zugewiesen_an_user=request.user)
                | db_models.Q(tasks__zugewiesen_an_team__mitglieder=request.user)
                | db_models.Q(tasks__zugewiesen_an_stelle=getattr(
                    getattr(getattr(request.user, "hr_mitarbeiter", None), "stelle", None),
                    "pk", None,
                ))
            )
            .values_list("object_id", flat=True)
            .distinct()
        )
        if workflow_dok_ids:
            q_filter |= db_models.Q(klasse="sensibel", pk__in=workflow_dok_ids)

        qs = qs.filter(q_filter).distinct()

    if form.is_valid():
        q = form.cleaned_data.get("q")
        klasse = form.cleaned_data.get("klasse")
        kategorie = form.cleaned_data.get("kategorie")
        tag = form.cleaned_data.get("tag")
        orgeinheit = form.cleaned_data.get("orgeinheit")

        if q:
            from django.db import connection
            if connection.vendor == "postgresql":
                from django.contrib.postgres.search import SearchQuery, SearchRank
                # Nutzt den GIN-Index auf suchvektor (tsvector-Spalte).
                # filter(suchvektor=query) aktiviert den Index; annotate ergaenzt die Rang-Sortierung.
                query = SearchQuery(q, config="german")
                qs = (
                    qs.filter(suchvektor=query)
                    .annotate(rank=SearchRank("suchvektor", query))
                    .order_by("-rank")
                )
            else:
                qs = qs.filter(
                    db_models.Q(titel__icontains=q) | db_models.Q(beschreibung__icontains=q)
                )
        if klasse:
            qs = qs.filter(klasse=klasse)
        if kategorie:
            qs = qs.filter(kategorie=kategorie)
        if tag:
            qs = qs.filter(tags=tag)
        if orgeinheit:
            qs = qs.filter(eigentuemereinheit=orgeinheit)

    # Pro Dokument: hat der aktuelle User einen aktiven Schluessel?
    aktive_schluessel_ids = set(
        DokumentZugriffsschluessel.objects.filter(
            user=request.user,
            status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
            gueltig_bis__gt=timezone.now(),
        ).values_list("dokument_id", flat=True)
    )

    paginator = Paginator(qs, 25)
    seite = paginator.get_page(request.GET.get("page"))

    # Workflow-Ampel: Status pro Dokument auf der aktuellen Seite
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowInstance
    dok_ids_seite = [d.pk for d in seite.object_list]
    dok_ct = ContentType.objects.get_for_model(Dokument)
    wf_laufend_ids = set()
    wf_abgeschlossen_ids = set()
    wf_abgebrochen_ids = set()
    if dok_ids_seite:
        instanzen = (
            WorkflowInstance.objects
            .filter(content_type=dok_ct, object_id__in=dok_ids_seite)
            .values("object_id", "status")
            .order_by("object_id", "-gestartet_am")
        )
        # Neueste Instanz pro Dokument – Prioritaet: laufend > abgeschlossen > abgebrochen
        seen = {}
        for inst in instanzen:
            oid = inst["object_id"]
            if oid not in seen:
                seen[oid] = inst["status"]
        for oid, status in seen.items():
            if status == WorkflowInstance.STATUS_LAUFEND:
                wf_laufend_ids.add(oid)
            elif status == "abgeschlossen":
                wf_abgeschlossen_ids.add(oid)
            elif status == "abgebrochen":
                wf_abgebrochen_ids.add(oid)

    # Posteingang: offene Workflow-Vorschlaege (nur eigene oder staff)
    posteingang_qs = Dokument.objects.filter(
        workflow_vorschlag__isnull=False,
        workflow_vorschlag_erledigt=False,
    ).select_related("workflow_vorschlag").order_by("-erstellt_am")
    if not request.user.is_staff and not request.user.is_superuser:
        user_org_ids = _get_user_orgeinheit_ids(request.user)
        if user_org_ids:
            posteingang_qs = posteingang_qs.filter(
                db_models.Q(klasse="offen")
                | db_models.Q(klasse="sensibel", eigentuemereinheit_id__in=user_org_ids)
            )
        else:
            posteingang_qs = posteingang_qs.filter(klasse="offen")
    posteingang = list(posteingang_qs[:20])

    # Persoenliche Ablage des eingeloggten Users (nur fuer ihn selbst sichtbar)
    meine_ablage_docs = (
        Dokument.objects
        .filter(ist_persoenlich=True, erstellt_von=request.user)
        .order_by("-erstellt_am")[:10]
    )
    meine_freigaben = (
        Dokument.objects
        .filter(ist_persoenlich=True, sichtbar_fuer=request.user)
        .exclude(erstellt_von=request.user)
        .order_by("-erstellt_am")[:5]
    )

    return render(request, "dms/dokument_liste.html", {
        "form": form,
        "seite": seite,
        "titel": "Dokumente",
        "aktive_schluessel_ids": aktive_schluessel_ids,
        "posteingang": posteingang,
        "wf_laufend_ids": wf_laufend_ids,
        "wf_abgeschlossen_ids": wf_abgeschlossen_ids,
        "wf_abgebrochen_ids": wf_abgebrochen_ids,
        "meine_ablage_docs": meine_ablage_docs,
        "meine_freigaben": meine_freigaben,
    })


# ---------------------------------------------------------------------------
# Tag anlegen (JSON-API fuer Inline-Erstellung im Upload-Formular)
# ---------------------------------------------------------------------------

@login_required
def tag_anlegen(request):
    """Legt einen neuen DokumentTag an und gibt ihn als JSON zurueck.

    POST-Parameter: name (str), farbe (str, Hex, optional)
    Antwort: {"ok": true, "id": .., "name": .., "farbe": ..}
             {"ok": false, "fehler": ".."}
    """
    if request.method != "POST":
        from django.http import JsonResponse
        return JsonResponse({"ok": False, "fehler": "Nur POST erlaubt."}, status=405)

    from django.http import JsonResponse
    from .models import DokumentTag

    name = request.POST.get("name", "").strip()
    farbe = request.POST.get("farbe", "#6c757d").strip()

    if not name:
        return JsonResponse({"ok": False, "fehler": "Name darf nicht leer sein."})
    if len(name) > 50:
        return JsonResponse({"ok": False, "fehler": "Name zu lang (max. 50 Zeichen)."})
    # Farbe validieren
    import re
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", farbe):
        farbe = "#6c757d"

    tag, erstellt = DokumentTag.objects.get_or_create(
        name=name,
        defaults={"farbe": farbe},
    )
    return JsonResponse({
        "ok": True,
        "id": tag.pk,
        "name": tag.name,
        "farbe": tag.farbe,
        "neu": erstellt,
    })


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@login_required
def dokument_upload(request):
    """Upload eines neuen Dokuments (Klasse 1 oder 2)."""
    # OrgEinheit des hochladenden Users als Vorauswahl ermitteln
    user_org_ids = _get_user_orgeinheit_ids(request.user)
    initial = {}
    if user_org_ids:
        initial["eigentuemereinheit"] = next(iter(user_org_ids))

    form = DokumentUploadForm(request.POST or None, request.FILES or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        datei = form.cleaned_data["datei"]
        inhalt_bytes = datei.read()
        mime = datei.content_type or mimetypes.guess_type(datei.name)[0] or "application/octet-stream"

        dok = form.save(commit=False)
        dok.dateiname = datei.name
        dok.dateityp = mime
        dok.groesse_bytes = len(inhalt_bytes)
        dok.erstellt_von = request.user

        try:
            speichere_dokument(dok, inhalt_bytes)
        except ValueError as exc:
            messages.error(request, f"Verschluesselung fehlgeschlagen: {exc}")
            return render(request, "dms/dokument_upload.html", {"form": form})

        dok.save()
        form.save_m2m()
        suchvektor_befuellen(dok)

        _protokolliere(request, dok, aktion="erstellt")
        messages.success(request, f'Dokument "{dok.titel}" wurde erfolgreich hochgeladen.')
        return redirect("dms:liste")

    return render(request, "dms/dokument_upload.html", {"form": form})


# ---------------------------------------------------------------------------
# Neues Dokument erstellen (leere Vorlage direkt in OnlyOffice oeffnen)
# ---------------------------------------------------------------------------

def _setze_docx_sprache_deutsch(doc) -> None:
    """Setzt die Dokumentsprache eines python-docx-Dokuments auf Deutsch (de-DE).

    Betrifft:
      - Normal-Stil (rPr/w:lang) – Rechtschreibpruefung aller Absaetze
      - Dokument-Settings (w:themeFontLang) – Standard-Thema-Schriftart
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    # Normal-Stil: Sprache im zeichenformatierenden Teil (rPr) setzen
    normal = doc.styles["Normal"]
    rpr = normal.element.get_or_add_rPr()
    for vorhandenes in rpr.findall(qn("w:lang")):
        rpr.remove(vorhandenes)
    lang = OxmlElement("w:lang")
    lang.set(qn("w:val"), "de-DE")
    lang.set(qn("w:eastAsia"), "zh-CN")
    lang.set(qn("w:bidi"), "ar-SA")
    rpr.append(lang)

    # Dokument-Settings: Thema-Schriftsprache
    settings_elem = doc.settings.element
    for vorhandenes in settings_elem.findall(qn("w:themeFontLang")):
        settings_elem.remove(vorhandenes)
    theme_lang = OxmlElement("w:themeFontLang")
    theme_lang.set(qn("w:val"), "de-DE")
    settings_elem.append(theme_lang)


def _setze_pptx_sprache_deutsch(prs) -> None:
    """Setzt die Dokumentsprache einer python-pptx-Praesentation auf Deutsch (de-DE).

    Schreibt das <a:lang>-Attribut im Default-Textstil der Praesentation.
    """
    from pptx.oxml.ns import qn as pqn
    from lxml import etree

    # defaultTextStyle im Presentation-XML anpassen
    prs_elem = prs.presentation
    dts = prs_elem.find(pqn("p:defaultTextStyle"))
    if dts is None:
        dts = etree.SubElement(prs_elem, pqn("p:defaultTextStyle"))

    # lvl1pPr sicherstellen
    lvl1 = dts.find(pqn("a:lvl1pPr"))
    if lvl1 is None:
        lvl1 = etree.SubElement(dts, pqn("a:lvl1pPr"))

    # defRPr (default run properties) sicherstellen
    def_rpr = lvl1.find(pqn("a:defRPr"))
    if def_rpr is None:
        def_rpr = etree.SubElement(lvl1, pqn("a:defRPr"))

    # a:lang setzen
    for vorhandenes in def_rpr.findall(pqn("a:lang")):
        def_rpr.remove(vorhandenes)
    lang_elem = etree.SubElement(def_rpr, pqn("a:lang"))
    lang_elem.set("val", "de-DE")


def _erstelle_leere_datei(dateityp: str) -> tuple[bytes, str, str]:
    """Gibt (inhalt_bytes, dateiname, mime_typ) fuer eine leere Vorlage zurueck.

    Unterstuetzte Typen: docx, xlsx, pptx
    Alle Dokumente werden mit Textsprache Deutsch (de-DE) erstellt.
    """
    import io

    if dateityp == "docx":
        from docx import Document
        doc = Document()
        _setze_docx_sprache_deutsch(doc)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue(), "dokument.docx", \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if dateityp == "xlsx":
        from openpyxl import Workbook
        buf = io.BytesIO()
        Workbook().save(buf)
        return buf.getvalue(), "tabelle.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    if dateityp == "pptx":
        from pptx import Presentation
        prs = Presentation()
        _setze_pptx_sprache_deutsch(prs)
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue(), "praesentation.pptx", \
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    raise ValueError(f"Unbekannter Dateityp: {dateityp}")


@login_required
def dokument_neu(request):
    """Erstellt ein neues leeres Dokument und oeffnet es sofort in OnlyOffice.

    Ablauf:
    1. User waehlt Titel, Typ (docx/xlsx) und Klasse
    2. PRIMA erzeugt leere Vorlage (python-docx / openpyxl)
    3. Dokument wird als Version 1 in der DB gespeichert
    4. Weiterleitung zum OnlyOffice-Editor
    """
    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "")
    if not onlyoffice_url:
        messages.error(request, "OnlyOffice ist nicht konfiguriert. Bitte zuerst hochladen.")
        return redirect("dms:upload")

    user_org_ids = _get_user_orgeinheit_ids(request.user)
    initial = {}
    if user_org_ids:
        initial["eigentuemereinheit"] = next(iter(user_org_ids))

    form = DokumentNeuForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        dateityp = form.cleaned_data["dateityp_neu"]
        try:
            inhalt_bytes, dateiname, mime = _erstelle_leere_datei(dateityp)
        except Exception as exc:
            messages.error(request, f"Vorlage konnte nicht erstellt werden: {exc}")
            return render(request, "dms/dokument_neu.html", {"form": form})

        dok = form.save(commit=False)
        dok.dateiname = dateiname
        dok.dateityp = mime
        dok.groesse_bytes = len(inhalt_bytes)
        dok.erstellt_von = request.user
        dok.version = 1

        try:
            speichere_dokument(dok, inhalt_bytes)
        except ValueError as exc:
            messages.error(request, f"Verschluesselung fehlgeschlagen: {exc}")
            return render(request, "dms/dokument_neu.html", {"form": form})

        dok.save()
        suchvektor_befuellen(dok)

        _protokolliere(request, dok, aktion="erstellt", notiz=f"Neues {dateityp.upper()} via OnlyOffice angelegt")
        return redirect("dms:onlyoffice_editor", pk=dok.pk)

    return render(request, "dms/dokument_neu.html", {"form": form})


# ---------------------------------------------------------------------------
# Download / Vorschau / Detail
# ---------------------------------------------------------------------------

@login_required
def dokument_download(request, pk):
    """Oeffnet OnlyOffice-Editor fuer unterstuetzte Typen, sonst Datei-Download.

    Sensible Dokumente: nur mit aktivem Zugriffsschluessel moeglich.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel fuer dieses Dokument.")
        return redirect("dms:zugriff_beantragen", pk=pk)

    # OnlyOffice-faehige Typen direkt im Editor oeffnen
    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "")
    if onlyoffice_url and dok.dateityp in _ONLYOFFICE_MIME_TYPEN:
        return redirect("dms:onlyoffice_editor", pk=pk)

    # Fallback: Datei herunterladen
    try:
        inhalt = lade_dokument(dok)
    except Exception as exc:
        logger.error("Download fehlgeschlagen fuer Dokument %s: %s", pk, exc)
        messages.error(request, "Das Dokument konnte nicht geladen werden.")
        return redirect("dms:liste")

    _protokolliere(request, dok, aktion="download")

    response = HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{dok.dateiname}"'
    response["Content-Length"] = len(inhalt)
    return response


@login_required
def dokument_vorschau(request, pk):
    """Oeffnet OnlyOffice-Editor fuer unterstuetzte Typen, sonst Inline-Anzeige.

    Sensible Dokumente: nur mit aktivem Zugriffsschluessel moeglich.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel fuer dieses Dokument.")
        return redirect("dms:zugriff_beantragen", pk=pk)

    # OnlyOffice-faehige Typen direkt im Editor oeffnen
    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "")
    if onlyoffice_url and dok.dateityp in _ONLYOFFICE_MIME_TYPEN:
        return redirect("dms:onlyoffice_editor", pk=pk)

    # Fallback: Inline-Anzeige (z.B. Bilder)
    try:
        inhalt = lade_dokument(dok)
    except Exception as exc:
        logger.error("Vorschau fehlgeschlagen fuer Dokument %s: %s", pk, exc)
        messages.error(request, "Das Dokument konnte nicht geladen werden.")
        return redirect("dms:liste")

    _protokolliere(request, dok, aktion="vorschau")

    response = HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="{dok.dateiname}"'
    return response


@login_required
def dokument_detail(request, pk):
    """Detailansicht eines Dokuments mit Metadaten und Zugriffsprotokoll."""
    dok = get_object_or_404(Dokument, pk=pk)

    # Sensible Dokumente: Zugriff nur fuer berechtigte User
    # (Superuser, OrgEinheit-Mitglied, sichtbar_fuer, aktiver Zugriffsschluessel)
    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Kein Zugriffsrecht fuer dieses Dokument.")
        return redirect("dms:liste")

    zugriffe = dok.zugriffe.select_related(
        "user", "user__hr_mitarbeiter__stelle"
    ).order_by("-zeitpunkt")[:20]
    aktiver_schluessel = None
    offener_antrag = None

    if dok.klasse == "sensibel":
        aktiver_schluessel = DokumentZugriffsschluessel.objects.filter(
            user=request.user,
            dokument=dok,
            status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
            gueltig_bis__gt=timezone.now(),
        ).first()
        offener_antrag = DokumentZugriffsschluessel.objects.filter(
            user=request.user,
            dokument=dok,
            status=DokumentZugriffsschluessel.STATUS_OFFEN,
        ).first()

    versionen = dok.versionen.select_related("erstellt_von").order_by("-version_nr")[:20]

    # Laufende Workflow-Instanzen fuer dieses Dokument laden
    from django.contrib.contenttypes.models import ContentType
    from workflow.models import WorkflowInstance, WorkflowTask
    dok_ct = ContentType.objects.get_for_model(Dokument)
    workflow_instanzen = list(
        WorkflowInstance.objects
        .filter(content_type=dok_ct, object_id=dok.pk)
        .select_related("template", "gestartet_von")
        .order_by("-gestartet_am")[:10]
    )
    # Offene Tasks pro Instanz vorladen (wer hat die Kugel gerade?)
    instanz_ids = [i.pk for i in workflow_instanzen]
    offene_tasks = (
        WorkflowTask.objects
        .filter(instance_id__in=instanz_ids, status__in=["offen", "in_bearbeitung"])
        .select_related("step", "zugewiesen_an_stelle", "zugewiesen_an_user",
                        "zugewiesen_an_team")
        .order_by("instance_id", "step__reihenfolge")
    )
    # Tasks nach Instanz gruppieren
    tasks_by_instanz = {}
    for task in offene_tasks:
        tasks_by_instanz.setdefault(task.instance_id, []).append(task)
    for inst in workflow_instanzen:
        inst.offene_tasks = tasks_by_instanz.get(inst.pk, [])

    return render(request, "dms/dokument_detail.html", {
        "dok": dok,
        "zugriffe": zugriffe,
        "versionen": versionen,
        "aktiver_schluessel": aktiver_schluessel,
        "offener_antrag": offener_antrag,
        "darf_zugreifen": _darf_sensibel_zugreifen(request, dok) if dok.klasse == "sensibel" else True,
        "bentopdf_url": getattr(django_settings, "BENTOPDF_URL", ""),
        "onlyoffice_url": getattr(django_settings, "ONLYOFFICE_URL", ""),
        "onlyoffice_unterstuetzt": dok.dateityp in _ONLYOFFICE_MIME_TYPEN,
        "workflow_instanzen": workflow_instanzen,
        "dms_kategorien": DokumentKategorie.objects.order_by("name"),
        "templates": WorkflowTemplate.objects.filter(ist_aktiv=True).order_by("kategorie", "name"),
        "ist_dms_admin": _ist_dms_admin(request.user) or request.user.is_staff,
    })


# ---------------------------------------------------------------------------
# Zugriffsschluessel – Beantragen
# ---------------------------------------------------------------------------

@login_required
def zugriff_beantragen(request, pk):
    """User beantragt zeitlich begrenzten Zugriff auf ein sensibles Dokument."""
    dok = get_object_or_404(Dokument, pk=pk, klasse="sensibel")

    # Bereits aktiven Schluessel → direkt weiterleiten
    if _darf_sensibel_zugreifen(request, dok):
        messages.info(request, "Sie haben bereits einen aktiven Zugriffsschluessel fuer dieses Dokument.")
        return redirect("dms:detail", pk=pk)

    # Offener Antrag → Hinweis
    offener_antrag = DokumentZugriffsschluessel.objects.filter(
        user=request.user,
        dokument=dok,
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    ).first()

    form = ZugriffsantragForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if offener_antrag:
            messages.warning(request, "Sie haben bereits einen offenen Antrag fuer dieses Dokument.")
            return redirect("dms:detail", pk=pk)

        schluessel = form.save(commit=False)
        schluessel.user = request.user
        schluessel.dokument = dok
        schluessel.status = DokumentZugriffsschluessel.STATUS_OFFEN
        schluessel.save()

        dauer_text = dict(DAUER_OPTIONEN).get(schluessel.gewuenschte_dauer_h, "?")
        _protokolliere(
            request, dok, aktion="zugriff_beantragt",
            notiz=f"Grund: {schluessel.antrag_grund} | Dauer: {dauer_text}",
        )

        messages.success(
            request,
            f'Ihr Zugriffsantrag fuer "{dok.titel}" wurde eingereicht. '
            "Ein Berechtigter wird ihn pruefen."
        )
        return redirect("dms:liste")

    return render(request, "dms/zugriff_beantragen.html", {
        "dok": dok,
        "form": form,
        "offener_antrag": offener_antrag,
        "dauer_optionen": DAUER_OPTIONEN,
    })


# ---------------------------------------------------------------------------
# Zugriffsschluessel – Verwaltung (DMS-Admin oder Dokumenten-Ersteller)
# ---------------------------------------------------------------------------

def _ist_dms_admin(user):
    """Gibt True zurueck wenn der User in der Gruppe 'DMS-Admin' oder im DMS-Team ist."""
    from formulare.models import TeamQueue
    return (
        user.groups.filter(name="DMS-Admin").exists()
        or TeamQueue.objects.filter(kuerzel="dms", mitglieder=user).exists()
    )


@login_required
def zugriffsantraege_liste(request):
    """DMS-Admin-View: Alle offenen und aktuellen Zugriffsantraege.

    DMS-Admins sehen alle Antraege. Dokumenten-Ersteller sehen nur Antraege
    auf ihre eigenen Dokumente.
    """
    ist_admin = _ist_dms_admin(request.user) or request.user.is_superuser

    if not ist_admin and not request.user.is_staff:
        # Pruefe ob User ueberhaupt Dokumente erstellt hat auf die Antraege existieren
        eigene_dok_ids = Dokument.objects.filter(
            erstellt_von=request.user
        ).values_list("id", flat=True)
        if not eigene_dok_ids:
            messages.error(request, "Keine Berechtigung.")
            return redirect("dms:liste")
        # Nur Antraege auf eigene Dokumente
        filter_dok = db_models.Q(dokument_id__in=eigene_dok_ids)
    else:
        filter_dok = db_models.Q()  # keine Einschraenkung

    offene = DokumentZugriffsschluessel.objects.filter(
        filter_dok,
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    ).select_related("user", "dokument").order_by("antrag_zeitpunkt")

    aktive = DokumentZugriffsschluessel.objects.filter(
        filter_dok,
        status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
        gueltig_bis__gt=timezone.now(),
    ).select_related("user", "dokument", "genehmigt_von").order_by("gueltig_bis")

    abgelaufen = DokumentZugriffsschluessel.objects.filter(filter_dok).exclude(
        status__in=[
            DokumentZugriffsschluessel.STATUS_OFFEN,
            DokumentZugriffsschluessel.STATUS_GENEHMIGT,
        ]
    ).select_related("user", "dokument", "genehmigt_von").order_by("-antrag_zeitpunkt")[:50]

    return render(request, "dms/zugriffsantraege.html", {
        "offene": offene,
        "aktive": aktive,
        "abgelaufen": abgelaufen,
        "ist_dms_admin": ist_admin,
    })


@login_required
def zugriff_genehmigen(request, schluessel_pk):
    """DMS-Admin oder Dokumenten-Ersteller genehmigt einen Zugriffsantrag."""
    schluessel_qs = get_object_or_404(
        DokumentZugriffsschluessel,
        pk=schluessel_pk,
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    )
    ist_admin = _ist_dms_admin(request.user) or request.user.is_superuser
    ist_ersteller = schluessel_qs.dokument.erstellt_von == request.user
    if not ist_admin and not ist_ersteller and not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:zugriffsantraege")

    schluessel = schluessel_qs

    if request.method == "POST":
        from datetime import timedelta
        schluessel.status = DokumentZugriffsschluessel.STATUS_GENEHMIGT
        schluessel.genehmigt_von = request.user
        schluessel.genehmigt_am = timezone.now()
        schluessel.gueltig_bis = timezone.now() + timedelta(hours=schluessel.gewuenschte_dauer_h)
        schluessel.save()

        # Guardian: Objekt-Berechtigung fuer diesen User auf dieses Dokument
        assign_perm("dms.view_dokument_sensibel", schluessel.user, schluessel.dokument)

        dauer_text = dict(DAUER_OPTIONEN).get(schluessel.gewuenschte_dauer_h, "?")
        _protokolliere(
            request, schluessel.dokument, aktion="zugriff_genehmigt",
            notiz=(
                f"Genehmigt von: {request.user.get_full_name() or request.user.username} | "
                f"Fuer: {schluessel.user.get_full_name() or schluessel.user.username} | "
                f"Dauer: {dauer_text} | Gueltig bis: {schluessel.gueltig_bis:%d.%m.%Y %H:%M}"
            ),
        )

        messages.success(
            request,
            f'Zugriff fuer {schluessel.user.get_full_name() or schluessel.user.username} '
            f'auf "{schluessel.dokument.titel}" genehmigt – {dauer_text}.'
        )

    return redirect("dms:zugriffsantraege")


@login_required
def zugriff_ablehnen(request, schluessel_pk):
    """DMS-Admin oder Dokumenten-Ersteller lehnt einen Zugriffsantrag ab."""
    schluessel_obj = get_object_or_404(
        DokumentZugriffsschluessel,
        pk=schluessel_pk,
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    )
    ist_admin = _ist_dms_admin(request.user) or request.user.is_superuser
    ist_ersteller = schluessel_obj.dokument.erstellt_von == request.user
    if not ist_admin and not ist_ersteller and not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:zugriffsantraege")

    schluessel = schluessel_obj

    if request.method == "POST":
        schluessel.status = DokumentZugriffsschluessel.STATUS_ABGELEHNT
        schluessel.genehmigt_von = request.user
        schluessel.genehmigt_am = timezone.now()
        schluessel.save()

        _protokolliere(
            request, schluessel.dokument, aktion="zugriff_abgelehnt",
            notiz=(
                f"Abgelehnt von: {request.user.get_full_name() or request.user.username} | "
                f"Antragsteller: {schluessel.user.get_full_name() or schluessel.user.username}"
            ),
        )

        messages.warning(
            request,
            f'Zugriffsantrag von {schluessel.user.get_full_name() or schluessel.user.username} '
            f'auf "{schluessel.dokument.titel}" abgelehnt.'
        )

    return redirect("dms:zugriffsantraege")


@login_required
def zugriff_widerrufen(request, schluessel_pk):
    """DMS-Admin oder Dokumenten-Ersteller widerruft einen aktiven Zugriffsschluessel."""
    schluessel_check = get_object_or_404(
        DokumentZugriffsschluessel,
        pk=schluessel_pk,
        status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
    )
    ist_admin = _ist_dms_admin(request.user) or request.user.is_superuser
    ist_ersteller = schluessel_check.dokument.erstellt_von == request.user
    if not ist_admin and not ist_ersteller and not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:zugriffsantraege")

    schluessel = schluessel_check

    if request.method == "POST":
        schluessel.status = DokumentZugriffsschluessel.STATUS_WIDERRUFEN
        schluessel.gueltig_bis = timezone.now()
        schluessel.save()

        # Guardian: Objekt-Berechtigung entziehen
        remove_perm("dms.view_dokument_sensibel", schluessel.user, schluessel.dokument)

        _protokolliere(
            request, schluessel.dokument, aktion="zugriff_widerrufen",
            notiz=(
                f"Widerrufen von: {request.user.get_full_name() or request.user.username} | "
                f"Betroffener User: {schluessel.user.get_full_name() or schluessel.user.username}"
            ),
        )

        messages.warning(
            request,
            f'Zugriffsschluessel von {schluessel.user.get_full_name() or schluessel.user.username} '
            f'auf "{schluessel.dokument.titel}" wurde widerrufen.'
        )

    return redirect("dms:zugriffsantraege")


# ---------------------------------------------------------------------------
# PDF-Export + digitale Signatur aus OnlyOffice heraus
# ---------------------------------------------------------------------------

def _konvertiere_dms_dok_zu_pdf(dok) -> bytes | None:
    """Schickt das DMS-Dokument als DOCX/XLSX an den OnlyOffice ConvertService.

    OnlyOffice konvertiert server-seitig zu PDF und gibt eine Download-URL zurueck.
    Gibt die PDF-Bytes zurueck oder None bei Fehler.
    """
    import hashlib
    import time
    import urllib.request as urlreq

    onlyoffice_internal = (
        getattr(django_settings, "ONLYOFFICE_INTERNAL_URL", "").rstrip("/")
        or getattr(django_settings, "ONLYOFFICE_URL", "").rstrip("/")
    )
    prima_base = (
        getattr(django_settings, "PRIMA_ONLYOFFICE_BASE_URL", "").rstrip("/")
        or getattr(django_settings, "PRIMA_BASE_URL", "").rstrip("/")
    )
    if not onlyoffice_internal or not prima_base:
        logger.error("OnlyOffice oder PRIMA-Base-URL nicht konfiguriert.")
        return None

    file_type = _MIME_ZU_EXT.get(dok.dateityp, "docx")
    if file_type == "pdf":
        # Bereits ein PDF – direkt Inhalt zurueckgeben
        return lade_dokument(dok)

    key = hashlib.md5(
        f"pdf-convert-{dok.pk}-v{dok.version}-{time.time()}".encode()
    ).hexdigest()[:20]

    nutzlast = {
        "async":      False,
        "filetype":   file_type,
        "key":        key,
        "outputtype": "pdf",
        "title":      dok.dateiname,
        "url":        f"{prima_base}/dms/{dok.pk}/onlyoffice/laden/",
    }
    nutzlast_bytes = json.dumps(nutzlast).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    secret = getattr(django_settings, "ONLYOFFICE_JWT_SECRET", "")
    if secret:
        import jwt as pyjwt
        token = pyjwt.encode(nutzlast, secret, algorithm="HS256")
        headers["Authorization"] = f"Bearer {token}"

    convert_url = f"{onlyoffice_internal}/ConvertService.ashx"
    try:
        req = urlreq.Request(convert_url, data=nutzlast_bytes, headers=headers, method="POST")
        with urlreq.urlopen(req, timeout=60) as resp:
            antwort_bytes = resp.read()
    except Exception as exc:
        logger.error("OnlyOffice Konvertierung fehlgeschlagen fuer Dokument %s: %s", dok.pk, exc)
        return None

    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(antwort_bytes)
        end_convert = (root.findtext("EndConvert") or "").strip().lower() == "true"
        pdf_url = (root.findtext("FileUrl") or "").strip()
        fehler_code = root.findtext("Error")
    except ET.ParseError as exc:
        logger.error("OnlyOffice XML-Antwort nicht parsebar fuer Dok %s: %s", dok.pk, exc)
        return None

    if fehler_code:
        logger.error("OnlyOffice Konvertierungsfehler fuer Dok %s: Fehlercode %s", dok.pk, fehler_code)
        return None
    if not end_convert or not pdf_url:
        logger.error("OnlyOffice Konvertierung unvollstaendig fuer Dok %s", dok.pk)
        return None

    try:
        with urlreq.urlopen(pdf_url, timeout=30) as resp:
            return resp.read()
    except Exception as exc:
        logger.error("PDF-Download von OnlyOffice fehlgeschlagen fuer Dok %s: %s", dok.pk, exc)
        return None


def _erstelle_dms_signaturseite(dok, request) -> bytes:
    """Erzeugt eine Signaturseite fuer das DMS-Dokument als PDF (WeasyPrint).

    Koordinaten des Stempelbereichs (A4 = 595x842pt):
      pyhanko box: (20, 539, 502, 667)
    """
    from weasyprint import HTML
    from django.template.loader import render_to_string
    from django.utils import timezone
    from django.conf import settings as conf

    unterzeichner_name = request.user.get_full_name() or request.user.username
    unterzeichner_funktion = ""
    try:
        hr = request.user.hr_mitarbeiter
        if hr.stelle:
            unterzeichner_funktion = hr.stelle.bezeichnung
    except Exception:
        pass

    backend_name = getattr(conf, "SIGNATUR_BACKEND", "intern")
    signatur_backend = "PRIMA FES (intern)" if backend_name == "intern" else "Bundesdruckerei sign-me (QES)"

    kontext = {
        "dok":                    dok,
        "unterzeichner_name":     unterzeichner_name,
        "unterzeichner_funktion": unterzeichner_funktion,
        "signiert_am":            timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M Uhr"),
        "signatur_backend":       signatur_backend,
    }
    html_string = render_to_string(
        "dms/signaturseite_pdf.html", kontext, request=request
    )
    return HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()


def _pdfs_zusammenfuehren_dms(pdf_a: bytes, pdf_b: bytes) -> bytes:
    """Haengt pdf_b seitenweise an pdf_a an."""
    import io
    from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf_a)).pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(pdf_b)).pages:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@login_required
def dokument_pdf_exportieren(request, pk):
    """Konvertiert ein DMS-Dokument zu PDF, haengt eine Signaturseite an und signiert digital.

    Ablauf:
      1. Dokument → PDF via OnlyOffice ConvertService (oder direkt bei PDF-Typ)
      2. Signaturseite als separates PDF erzeugen (WeasyPrint)
      3. Dokument-PDF + Signaturseite zusammenfuehren (pypdf)
      4. Gesamtes PDF digital signieren via signatur.services.signiere_pdf()
      5. Signiertes PDF als Download zurueckgeben
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel.")
        return redirect("dms:detail", pk=pk)

    file_type = _MIME_ZU_EXT.get(dok.dateityp, "docx")
    if file_type not in ("docx", "xlsx", "pptx", "odt", "ods", "odp", "pdf"):
        messages.error(request, "Dieser Dateityp unterstuetzt keinen PDF-Export.")
        return redirect("dms:detail", pk=pk)

    # Schritt 1: Dokument → PDF
    dok_pdf = _konvertiere_dms_dok_zu_pdf(dok)
    if not dok_pdf:
        messages.error(request, "PDF-Konvertierung fehlgeschlagen. OnlyOffice erreichbar?")
        return redirect("dms:detail", pk=pk)

    # Schritt 2: Signaturseite erzeugen
    try:
        sig_seite = _erstelle_dms_signaturseite(dok, request)
    except Exception as exc:
        logger.warning("Signaturseite konnte nicht erzeugt werden fuer Dok %s: %s", pk, exc)
        sig_seite = None

    # Schritt 3: Zusammenfuehren
    if sig_seite:
        try:
            pdf_bytes = _pdfs_zusammenfuehren_dms(dok_pdf, sig_seite)
        except Exception as exc:
            logger.warning("PDF-Merge fehlgeschlagen fuer Dok %s: %s", pk, exc)
            pdf_bytes = dok_pdf
    else:
        pdf_bytes = dok_pdf

    # Schritt 4: Signieren (letzte Seite = Signaturseite)
    dateiname = f"{dok.titel}_v{dok.version}_signiert.pdf".replace(" ", "_")
    try:
        from signatur.services import signiere_pdf
        pdf_bytes = signiere_pdf(
            pdf_bytes,
            request.user,
            dokument_name=dateiname,
            seite=-1,
            # Signaturseite hat dedizierten Stempelbereich (y 539..667)
            stempel_y_oben=667,
            stempel_hoehe=128,
        )
    except ValueError as exc:
        # Session-Key fehlt oder Zertifikat ungueltig – klare Fehlermeldung statt unsigniertes PDF
        logger.warning("PDF-Signierung fehlgeschlagen (ValueError) fuer Dok %s: %s", pk, exc)
        messages.error(request, f"Signierung fehlgeschlagen: {exc}")
        return redirect("dms:detail", pk=pk)
    except Exception as exc:
        logger.error("PDF-Signierung fehlgeschlagen fuer Dok %s: %s", pk, exc, exc_info=True)
        messages.error(request, "Signierung fehlgeschlagen – bitte Administrator informieren.")
        return redirect("dms:detail", pk=pk)

    _protokolliere(request, dok, aktion="download", notiz=f"PDF-Export + Signatur (Version {dok.version})")

    # Schritt 5: Download
    return HttpResponse(
        pdf_bytes,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


# ---------------------------------------------------------------------------
# OnlyOffice – Editor, Callback, Dokument-Serve, Version-Restore
# ---------------------------------------------------------------------------

# Dateiendung aus MIME-Typ ermitteln (OnlyOffice benoetigt fileType)
_MIME_ZU_EXT = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":        "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/msword":                                                         "doc",
    "application/vnd.ms-excel":                                                   "xls",
    "application/vnd.ms-powerpoint":                                              "ppt",
    "application/vnd.oasis.opendocument.text":                                   "odt",
    "application/vnd.oasis.opendocument.spreadsheet":                            "ods",
    "application/vnd.oasis.opendocument.presentation":                           "odp",
    "application/pdf":                                                            "pdf",
}

# Alle MIME-Typen die OnlyOffice oeffnen kann (fuer Redirect-Logik)
_ONLYOFFICE_MIME_TYPEN = set(_MIME_ZU_EXT.keys())


def _onlyoffice_jwt(payload: dict) -> str:
    """Signiert den OnlyOffice-Konfigurations-Payload als HS256-JWT.

    OnlyOffice erwartet den Config-Dict direkt als JWT-Body (kein Wrapper).
    """
    import jwt
    secret = getattr(django_settings, "ONLYOFFICE_JWT_SECRET", "")
    if not secret:
        return ""
    return jwt.encode(payload, secret, algorithm="HS256")


@login_required
def onlyoffice_editor(request, pk):
    """Oeffnet das OnlyOffice-Editorfenster fuer ein DMS-Dokument.

    Generiert eine JWT-signierte Editor-Konfiguration und gibt die
    Editor-HTML-Seite zurueck. OnlyOffice laedt das Dokument anschliessend
    ueber onlyoffice_dokument_laden() vom PRIMA-Server.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Kein Zugriffsrecht fuer dieses Dokument.")
        return redirect("dms:detail", pk=pk)

    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "")
    # Interne URL fuer OnlyOffice-Server-Callbacks (erreichbar vom Docker-Container)
    prima_base = getattr(django_settings, "PRIMA_ONLYOFFICE_BASE_URL", "").rstrip("/") \
        or getattr(django_settings, "PRIMA_BASE_URL", "").rstrip("/")

    if not onlyoffice_url:
        messages.error(request, "OnlyOffice ist nicht konfiguriert.")
        return redirect("dms:detail", pk=pk)

    file_type = _MIME_ZU_EXT.get(dok.dateityp, "docx")
    # Eindeutiger Key pro Dokument + Version (OnlyOffice-Cache)
    doc_key = f"prima-{dok.pk}-v{dok.version}"

    config = {
        "document": {
            "fileType": file_type,
            "key":      doc_key,
            "title":    dok.dateiname,
            "url":      f"{prima_base}/dms/{dok.pk}/onlyoffice/laden/",
        },
        "documentType": _document_type(file_type),
        "editorConfig": {
            "callbackUrl": f"{prima_base}/dms/{dok.pk}/onlyoffice/callback/",
            "lang":        "de-DE",
            "mode":        "edit",
            "user": {
                "id":   str(request.user.pk),
                "name": request.user.get_full_name() or request.user.username,
            },
            "customization": {
                "spellcheck": True,
            },
        },
    }

    token = _onlyoffice_jwt(config)

    _protokolliere(request, dok, aktion="vorschau", notiz="OnlyOffice-Editor geoeffnet")

    return render(request, "dms/onlyoffice_editor.html", {
        "dok":            dok,
        "onlyoffice_url": onlyoffice_url,
        "oo_config":      config,
        "token":          token,
    })


def _document_type(file_type: str) -> str:
    """Gibt den OnlyOffice documentType zurueck (word/cell/slide)."""
    if file_type in ("docx", "doc", "odt", "pdf"):
        return "word"
    if file_type in ("xlsx", "xls", "ods"):
        return "cell"
    return "slide"


def onlyoffice_dokument_laden(request, pk):
    """Liefert den Dokumentinhalt an den OnlyOffice-Server aus.

    Diese URL wird vom OnlyOffice-Container server-seitig aufgerufen (kein Browser).
    Kein login_required – Authentifizierung erfolgt ausschliesslich per JWT.
    Ohne konfigurierten JWT-Secret wird der Zugriff ohne Pruefung erlaubt
    (nur fuer lokale Entwicklung akzeptabel).
    """
    import jwt

    # JWT-Authentifizierung pruefen (wenn Secret konfiguriert)
    secret = getattr(django_settings, "ONLYOFFICE_JWT_SECRET", "")
    if secret:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return HttpResponse("Unauthorized", status=401)
        token = auth_header[7:]
        try:
            jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return HttpResponse("Unauthorized", status=401)

    dok = get_object_or_404(Dokument, pk=pk)
    try:
        inhalt = lade_dokument(dok)
    except Exception as exc:
        logger.error("OnlyOffice Laden fehlgeschlagen fuer Dokument %s: %s", pk, exc)
        return HttpResponse("Fehler beim Laden", status=500)

    return HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")


@csrf_exempt
def onlyoffice_callback(request, pk):
    """Empfaengt die bearbeitete Datei vom OnlyOffice-Server und speichert sie
    als neue DokumentVersion.

    OnlyOffice ruft diesen Endpoint auf wenn:
    - status 2: Dokument ist bereit zum Speichern (alle Editoren haben geschlossen)
    - status 6: Dokument wurde forciert gespeichert

    Referenz: https://api.onlyoffice.com/editors/callback
    """
    import urllib.request
    import jwt

    if request.method != "POST":
        return JsonResponse({"error": 0})

    try:
        daten = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": 1})

    # JWT-Verifizierung
    secret = getattr(django_settings, "ONLYOFFICE_JWT_SECRET", "")
    if secret:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                jwt.decode(token, secret, algorithms=["HS256"])
            except jwt.PyJWTError:
                logger.warning("OnlyOffice Callback: ungueltige JWT fuer Dokument %s", pk)
                return JsonResponse({"error": 1})

    status = daten.get("status")
    # Status 2 = bereit zum Speichern, Status 6 = forciert gespeichert
    if status not in (2, 6):
        return JsonResponse({"error": 0})

    download_url = daten.get("url")
    if not download_url:
        return JsonResponse({"error": 0})

    # Download-URL auf interne OnlyOffice-URL umschreiben.
    # OnlyOffice generiert die URL mit seinem oeffentlichen Hostnamen
    # (z.B. https://office.georg-klein.com/cache/files/...).
    # Vom Docker-Container aus muss jedoch die interne URL verwendet werden,
    # da Cloudflare den Authorization-Header entfernt und JWT-Auth fehlschlaegt.
    onlyoffice_public   = getattr(django_settings, "ONLYOFFICE_URL", "").rstrip("/")
    onlyoffice_internal = getattr(django_settings, "ONLYOFFICE_INTERNAL_URL", "").rstrip("/")
    if onlyoffice_public and onlyoffice_internal and download_url.startswith(onlyoffice_public):
        download_url_intern = download_url.replace(onlyoffice_public, onlyoffice_internal, 1)
        logger.debug("OnlyOffice Callback: URL umgeschrieben %s -> %s", onlyoffice_public, onlyoffice_internal)
    else:
        download_url_intern = download_url

    logger.info("OnlyOffice Callback Dok %s: status=%s intern_url=%s", pk, status, download_url_intern)

    dok = get_object_or_404(Dokument, pk=pk)

    try:
        dl_req = urllib.request.Request(download_url_intern)
        if secret:
            dl_token = jwt.encode({"url": download_url_intern}, secret, algorithm="HS256")
            dl_req.add_header("Authorization", f"Bearer {dl_token}")
        with urllib.request.urlopen(dl_req, timeout=30) as resp:
            neuer_inhalt = resp.read()
    except Exception as exc:
        logger.error("OnlyOffice Callback: Download fehlgeschlagen Dok %s: %s | url=%s", pk, exc, download_url_intern)
        return JsonResponse({"error": 1})

    # Bearbeitenden User ermitteln (aus actions-Array wenn vorhanden)
    user = None
    actions = daten.get("actions", [])
    if actions:
        user_id_str = str(actions[0].get("userid", ""))
        try:
            from django.contrib.auth.models import User
            user = User.objects.filter(pk=int(user_id_str)).first()
        except (ValueError, TypeError):
            pass

    # Naechste Versionsnummer bestimmen
    letzte_nr = dok.versionen.aggregate(
        max_nr=db_models.Max("version_nr")
    )["max_nr"] or dok.version
    neue_nr = letzte_nr + 1

    # Neue Version speichern (gleiche Verschluesselungslogik wie Hauptdokument)
    version = DokumentVersion(
        dokument=dok,
        version_nr=neue_nr,
        dateiname=dok.dateiname,
        groesse_bytes=len(neuer_inhalt),
        erstellt_von=user,
        kommentar="via OnlyOffice",
    )
    if dok.klasse == "sensibel":
        from .services import verschluessel_inhalt
        verschluesselt, nonce_hex = verschluessel_inhalt(neuer_inhalt)
        version.inhalt_verschluesselt = verschluesselt
        version.verschluessel_nonce = nonce_hex
    else:
        version.inhalt_roh = neuer_inhalt
    version.save()

    # Hauptdokument aktualisieren (aktueller Inhalt + Versionszaehler)
    speichere_dokument(dok, neuer_inhalt)
    dok.version = neue_nr
    dok.groesse_bytes = len(neuer_inhalt)
    dok.save(update_fields=["inhalt_roh", "inhalt_verschluesselt",
                             "verschluessel_nonce", "version", "groesse_bytes"])
    # Suchvektor nach Aenderung neu aufbauen (Titel/Beschreibung unveraendert, ocr_text bleibt)
    suchvektor_befuellen(dok, dok.ocr_text)

    # Protokolleintrag ohne Request-Objekt (Callback kommt vom OnlyOffice-Server)
    ZugriffsProtokoll.objects.create(
        dokument=dok,
        user=user,
        aktion="onlyoffice_bearbeitet",
        notiz=f"Version {neue_nr} via OnlyOffice gespeichert",
    )

    logger.info("OnlyOffice Callback: Dokument %s als Version %s gespeichert", pk, neue_nr)
    return JsonResponse({"error": 0})


@login_required
def onlyoffice_version_check(request, pk):
    """Gibt die aktuelle Versionsnummer des Dokuments zurueck (fuer Polling)."""
    dok = get_object_or_404(Dokument, pk=pk)
    return JsonResponse({"version": dok.version})


@login_required
def onlyoffice_forcesave(request, pk):
    """Loest einen Force-Save im OnlyOffice Command Service aus.

    Wird vom 'Speichern & zurueck'-Button im Editor aufgerufen.
    OnlyOffice speichert das Dokument sofort und schickt danach
    den normalen Callback (status 6) an onlyoffice_callback().
    """
    import urllib.request as urlreq
    import urllib.parse

    if request.method != "POST":
        return JsonResponse({"ok": False, "fehler": "Nur POST erlaubt"})

    dok = get_object_or_404(Dokument, pk=pk)
    # Interne URL fuer API-Call zum OnlyOffice-Server (nicht durch Cloudflare)
    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_INTERNAL_URL", "").rstrip("/") \
        or getattr(django_settings, "ONLYOFFICE_URL", "").rstrip("/")

    if not onlyoffice_url:
        return JsonResponse({"ok": False, "fehler": "OnlyOffice nicht konfiguriert"})

    doc_key = f"prima-{dok.pk}-v{dok.version}"
    payload = json.dumps({"c": "forcesave", "key": doc_key}).encode("utf-8")

    command_url = f"{onlyoffice_url}/coauthoring/CommandService.ashx"
    req = urlreq.Request(
        command_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # JWT fuer Command Service
    secret = getattr(django_settings, "ONLYOFFICE_JWT_SECRET", "")
    if secret:
        import jwt
        token = jwt.encode({"c": "forcesave", "key": doc_key}, secret, algorithm="HS256")
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            antwort = json.loads(resp.read())
        # error 0 = OK, error 4 = kein aktiver Editor (auch OK – Tab bereits zu)
        if antwort.get("error") in (0, 4):
            return JsonResponse({"ok": True})
        return JsonResponse({"ok": False, "fehler": f"OnlyOffice Fehlercode {antwort.get('error')}"})
    except Exception as exc:
        logger.error("Force-Save fehlgeschlagen fuer Dokument %s: %s", pk, exc)
        return JsonResponse({"ok": False, "fehler": str(exc)})


@login_required
def version_restore(request, pk, version_nr):
    """Stellt eine aeltere DokumentVersion als aktuellen Inhalt wieder her.

    Erzeugt dabei eine neue Version mit dem alten Inhalt (kein Ueberschreiben).
    Nur Staff oder Mitglied der Eigentuemer-OrgEinheit darf wiederherstellen.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    # Berechtigung: Staff oder OrgEinheit-Mitglied
    ist_berechtigt = (
        request.user.is_staff
        or request.user.is_superuser
        or (dok.eigentuemereinheit_id and
            dok.eigentuemereinheit_id in _get_user_orgeinheit_ids(request.user))
    )
    if not ist_berechtigt:
        messages.error(request, "Keine Berechtigung zum Wiederherstellen von Versionen.")
        return redirect("dms:detail", pk=pk)

    alte_version = get_object_or_404(DokumentVersion, dokument=dok, version_nr=version_nr)

    if request.method == "POST":
        # Inhalt der alten Version lesen
        if dok.klasse == "sensibel":
            from .services import entschluessel_inhalt
            inhalt = entschluessel_inhalt(
                bytes(alte_version.inhalt_verschluesselt),
                alte_version.verschluessel_nonce,
            )
        else:
            inhalt = bytes(alte_version.inhalt_roh)

        # Neue Version erzeugen (Restore = neue Version, nicht Ueberschreiben)
        letzte_nr = dok.versionen.aggregate(
            max_nr=db_models.Max("version_nr")
        )["max_nr"] or dok.version
        neue_nr = letzte_nr + 1

        neue_version = DokumentVersion(
            dokument=dok,
            version_nr=neue_nr,
            dateiname=alte_version.dateiname,
            groesse_bytes=len(inhalt),
            erstellt_von=request.user,
            kommentar=f"Wiederhergestellt aus Version {version_nr}",
        )
        if dok.klasse == "sensibel":
            from .services import verschluessel_inhalt
            verschluesselt, nonce_hex = verschluessel_inhalt(inhalt)
            neue_version.inhalt_verschluesselt = verschluesselt
            neue_version.verschluessel_nonce = nonce_hex
        else:
            neue_version.inhalt_roh = inhalt
        neue_version.save()

        # Hauptdokument aktualisieren
        speichere_dokument(dok, inhalt)
        dok.version = neue_nr
        dok.groesse_bytes = len(inhalt)
        dok.save(update_fields=["inhalt_roh", "inhalt_verschluesselt",
                                 "verschluessel_nonce", "version", "groesse_bytes"])

        _protokolliere(
            request, dok, aktion="version_wiederhergestellt",
            notiz=f"Version {version_nr} wiederhergestellt als Version {neue_nr}",
        )

        messages.success(
            request,
            f'Version {version_nr} von "{dok.titel}" wurde als Version {neue_nr} wiederhergestellt.'
        )

    return redirect("dms:detail", pk=pk)


@login_required
def version_vorschau(request, pk, version_nr):
    """Zeigt eine archivierte Version inline im Browser.

    Office-Dateien werden in OnlyOffice (read-only) geöffnet.
    PDF/Bilder werden direkt inline ausgeliefert.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel.")
        return redirect("dms:detail", pk=pk)

    # Office-Dateien in OnlyOffice (read-only) oeffnen
    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "")
    if onlyoffice_url and dok.dateityp in _ONLYOFFICE_MIME_TYPEN and dok.dateityp != "application/pdf":
        return redirect("dms:version_onlyoffice", pk=pk, version_nr=version_nr)

    version = get_object_or_404(DokumentVersion, dokument=dok, version_nr=version_nr)

    if dok.klasse == "sensibel":
        from .services import entschluessel_inhalt
        inhalt = entschluessel_inhalt(
            bytes(version.inhalt_verschluesselt),
            version.verschluessel_nonce,
        )
    else:
        inhalt = bytes(version.inhalt_roh)

    _protokolliere(request, dok, "vorschau", f"Version {version_nr} (Archiv-Vorschau)")

    response = HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="{version.dateiname}"'
    return response


@login_required
def version_onlyoffice(request, pk, version_nr):
    """Oeffnet eine archivierte Dokumentversion read-only in OnlyOffice."""
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Kein Zugriffsrecht fuer dieses Dokument.")
        return redirect("dms:detail", pk=pk)

    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "")
    prima_base = getattr(django_settings, "PRIMA_ONLYOFFICE_BASE_URL", "").rstrip("/") \
        or getattr(django_settings, "PRIMA_BASE_URL", "").rstrip("/")

    if not onlyoffice_url:
        messages.error(request, "OnlyOffice ist nicht konfiguriert.")
        return redirect("dms:detail", pk=pk)

    version = get_object_or_404(DokumentVersion, dokument=dok, version_nr=version_nr)

    file_type = _MIME_ZU_EXT.get(dok.dateityp, "docx")
    # Eigener Key damit kein Konflikt mit dem aktiven Edit-Key entsteht
    doc_key = f"prima-{dok.pk}-archive-v{version_nr}"

    config = {
        "document": {
            "fileType": file_type,
            "key":      doc_key,
            "title":    version.dateiname,
            "url":      f"{prima_base}/dms/{dok.pk}/versionen/{version_nr}/onlyoffice/laden/",
            "permissions": {
                "edit":     False,
                "download": True,
                "print":    True,
            },
        },
        "documentType": _document_type(file_type),
        "editorConfig": {
            "lang": "de-DE",
            "mode": "view",
            "user": {
                "id":   str(request.user.pk),
                "name": request.user.get_full_name() or request.user.username,
            },
            "customization": {
                "spellcheck": True,
            },
        },
    }

    token = _onlyoffice_jwt(config)

    _protokolliere(request, dok, "vorschau",
                   f"Version {version_nr} in OnlyOffice (Archiv-Vorschau)")

    return render(request, "dms/onlyoffice_editor.html", {
        "dok":             dok,
        "onlyoffice_url":  onlyoffice_url,
        "oo_config":       config,
        "token":           token,
        "nur_lesezugriff": True,
    })


def onlyoffice_version_laden(request, pk, version_nr):
    """Liefert eine archivierte Version an OnlyOffice aus (JWT-gesichert).

    Wird server-seitig von OnlyOffice aufgerufen – kein login_required.
    """
    import jwt as pyjwt

    secret = getattr(django_settings, "ONLYOFFICE_JWT_SECRET", "")
    if secret:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return HttpResponse("Unauthorized", status=401)
        try:
            pyjwt.decode(auth_header[7:], secret, algorithms=["HS256"])
        except pyjwt.PyJWTError:
            return HttpResponse("Unauthorized", status=401)

    dok = get_object_or_404(Dokument, pk=pk)
    version = get_object_or_404(DokumentVersion, dokument=dok, version_nr=version_nr)

    if dok.klasse == "sensibel":
        from .services import entschluessel_inhalt
        inhalt = entschluessel_inhalt(
            bytes(version.inhalt_verschluesselt),
            version.verschluessel_nonce,
        )
    else:
        inhalt = bytes(version.inhalt_roh)

    return HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")


@login_required
def version_download(request, pk, version_nr):
    """Laedt eine bestimmte Version eines Dokuments herunter (ohne Restore)."""
    dok = get_object_or_404(Dokument, pk=pk)

    # Berechtigung: Staff, OrgEinheit-Mitglied oder Zugriffsschluessel (sensibel)
    if dok.klasse == "sensibel":
        darf = (
            request.user.is_staff
            or request.user.is_superuser
            or dok.eigentuemereinheit_id in _get_user_orgeinheit_ids(request.user)
        )
        if not darf:
            from django.utils import timezone as tz
            aktiver_schluessel = dok.zugriffsschluessel.filter(
                user=request.user,
                status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
                gueltig_bis__gt=tz.now(),
            ).first()
            darf = aktiver_schluessel is not None
        if not darf:
            messages.error(request, "Keine Berechtigung fuer dieses Dokument.")
            return redirect("dms:detail", pk=pk)

    version = get_object_or_404(DokumentVersion, dokument=dok, version_nr=version_nr)

    if dok.klasse == "sensibel":
        from .services import entschluessel_inhalt
        inhalt = entschluessel_inhalt(
            bytes(version.inhalt_verschluesselt),
            version.verschluessel_nonce,
        )
    else:
        inhalt = bytes(version.inhalt_roh)

    _protokolliere(request, dok, "download", f"Version {version_nr} (Archiv-Download)")

    response = HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")
    # Dateiname mit Versionsnummer kennzeichnen
    name_teile = version.dateiname.rsplit(".", 1)
    if len(name_teile) == 2:
        versioned_name = f"{name_teile[0]}_v{version_nr}.{name_teile[1]}"
    else:
        versioned_name = f"{version.dateiname}_v{version_nr}"
    response["Content-Disposition"] = f'attachment; filename="{versioned_name}"'
    return response


# ---------------------------------------------------------------------------
# DMS → Workflow-Integration
# ---------------------------------------------------------------------------

@login_required
def workflow_regeln_liste(request):
    """Staff-View: Liste aller Paperless-Workflow-Regeln."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

    regeln = PaperlessWorkflowRegel.objects.select_related("workflow_template").order_by("prioritaet", "bezeichnung")
    return render(request, "dms/workflow_regeln.html", {"regeln": regeln})


@login_required
def workflow_regel_erstellen(request):
    """Staff-View: Neue Paperless-Workflow-Regel anlegen."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

    form = PaperlessWorkflowRegelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Regel "{form.cleaned_data["bezeichnung"]}" wurde angelegt.')
        return redirect("dms:workflow_regeln")

    return render(request, "dms/workflow_regel_form.html", {"form": form, "neu": True})


@login_required
def workflow_regel_bearbeiten(request, regel_pk):
    """Staff-View: Vorhandene Paperless-Workflow-Regel bearbeiten."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

    regel = get_object_or_404(PaperlessWorkflowRegel, pk=regel_pk)
    form = PaperlessWorkflowRegelForm(request.POST or None, instance=regel)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Regel "{regel.bezeichnung}" wurde gespeichert.')
        return redirect("dms:workflow_regeln")

    return render(request, "dms/workflow_regel_form.html", {"form": form, "regel": regel, "neu": False})


@login_required
def workflow_regel_loeschen(request, regel_pk):
    """Staff-View: Paperless-Workflow-Regel loeschen (POST)."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

    regel = get_object_or_404(PaperlessWorkflowRegel, pk=regel_pk)
    if request.method == "POST":
        name = regel.bezeichnung
        regel.delete()
        messages.success(request, f'Regel "{name}" wurde geloescht.')
    return redirect("dms:workflow_regeln")


@login_required
def workflow_vorschlag_verwerfen(request, pk):
    """Markiert den automatischen Workflow-Vorschlag als erledigt (ohne Workflow zu starten).

    Wird aufgerufen wenn der User den Banner-Vorschlag manuell verwirft.
    """
    if request.method != "POST":
        return redirect("dms:detail", pk=pk)
    dok = get_object_or_404(Dokument, pk=pk)
    if dok.workflow_vorschlag_id:
        dok.workflow_vorschlag_erledigt = True
        dok.save(update_fields=["workflow_vorschlag_erledigt"])
        _protokolliere(request, dok, "geaendert", "Workflow-Vorschlag manuell verworfen.")
    return redirect("dms:detail", pk=pk)

@login_required
def dms_workflow_starten(request, pk):
    """Startet einen Workflow fuer ein DMS-Dokument.

    GET:  Gibt das Modal-Partial mit Auswahl der verfuegbaren Templates zurueck.
    POST: Startet den gewaehlten Workflow und leitet zurueck zur Detailseite.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    # Sensible Dokumente: Zugriff pruefen
    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel um einen Workflow zu starten.")
        return redirect("dms:detail", pk=pk)

    if request.method == "POST":
        from workflow.models import WorkflowTemplate
        from workflow.services import WorkflowEngine

        template_id = request.POST.get("template_id")
        if not template_id:
            messages.error(request, "Kein Workflow-Template ausgewaehlt.")
            return redirect("dms:detail", pk=pk)

        template = get_object_or_404(WorkflowTemplate, pk=template_id, ist_aktiv=True)
        try:
            engine = WorkflowEngine()
            instance = engine.start_workflow(template, dok, request.user)
            # Workflow-Vorschlag als erledigt markieren
            if dok.workflow_vorschlag_id:
                dok.workflow_vorschlag_erledigt = True
                dok.save(update_fields=["workflow_vorschlag_erledigt"])
            _protokolliere(
                request, dok, "geaendert",
                f"Workflow gestartet: {template.name} (Instanz #{instance.pk})",
            )
            messages.success(
                request,
                f'Workflow "{template.name}" wurde gestartet. '
                f'Die Aufgaben erscheinen jetzt im Arbeitsstapel der zustaendigen Mitarbeiter.'
            )
        except Exception as exc:
            logger.error("Workflow-Start fehlgeschlagen fuer Dokument %s: %s", pk, exc)
            messages.error(request, f"Fehler beim Starten des Workflows: {exc}")

        return redirect("dms:detail", pk=pk)

    # GET: Modal-Partial rendern
    from workflow.models import WorkflowTemplate
    templates = WorkflowTemplate.objects.filter(ist_aktiv=True).order_by("kategorie", "name")
    return render(request, "dms/partials/_workflow_starten_modal.html", {
        "dok": dok,
        "templates": templates,
    })


@login_required
def stelle_autocomplete(request):
    """JSON-Autocomplete fuer Stellen (Kuerzel + Bezeichnung).

    GET ?q=ma_el → gibt passende Stellen zurueck.
    Wird vom Laufzettel-Builder verwendet.
    """
    from hr.models import Stelle
    q = request.GET.get("q", "").strip()
    stellen = Stelle.objects.select_related("org_einheit").order_by("kuerzel")
    if q:
        stellen = stellen.filter(
            db_models.Q(kuerzel__icontains=q) | db_models.Q(bezeichnung__icontains=q)
        )
    ergebnis = [
        {
            "id": s.pk,
            "kuerzel": s.kuerzel,
            "bezeichnung": s.bezeichnung,
            "org": s.org_einheit.bezeichnung if s.org_einheit else "",
            "label": f"{s.kuerzel} – {s.bezeichnung}",
        }
        for s in stellen[:20]
    ]
    return JsonResponse({"stellen": ergebnis})


@login_required
def dms_laufzettel_starten(request, pk):
    """Erstellt einen ad-hoc Laufzettel und startet den Workflow.

    POST-Body (JSON):
        steps: [{stelle_id, aktion, titel}, ...]
        vorlage_name: optional – speichert als Laufzettel-Vorlage
        ablage_kategorie_id: optional – setzt Kategorie am Ende
    """
    from workflow.models import WorkflowTemplate, WorkflowStep
    from workflow.services import WorkflowEngine
    from hr.models import Stelle

    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        return JsonResponse({"fehler": "Kein Zugriffsrecht."}, status=403)

    if request.method != "POST":
        return JsonResponse({"fehler": "Nur POST erlaubt."}, status=405)

    try:
        daten = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"fehler": "Ungueltige JSON-Daten."}, status=400)

    schritte = daten.get("steps", [])
    if not schritte:
        return JsonResponse({"fehler": "Mindestens ein Schritt erforderlich."}, status=400)

    vorlage_name = daten.get("vorlage_name", "").strip()
    ablage_kategorie_id = daten.get("ablage_kategorie_id")

    # Auto-Name aus Kuerzeln bauen
    AKTION_KUERZEL = {
        "pruefen": "PR",
        "genehmigen": "GEN",
        "bearbeiten": "BE",
        "informieren": "KEN",
        "entscheiden": "ENT",
    }
    kuerzel_kette = []
    for schritt in schritte:
        try:
            stelle = Stelle.objects.get(pk=schritt["stelle_id"])
            aktion_kz = AKTION_KUERZEL.get(schritt["aktion"], schritt["aktion"].upper()[:3])
            kuerzel_kette.append(f"{stelle.kuerzel}:{aktion_kz}")
        except (Stelle.DoesNotExist, KeyError):
            return JsonResponse({"fehler": f"Stelle {schritt.get('stelle_id')} nicht gefunden."}, status=400)

    auto_name = " → ".join(kuerzel_kette)
    template_name = vorlage_name or f"Laufzettel {auto_name}"

    # WorkflowTemplate erstellen (oder als Vorlage speichern)
    template = WorkflowTemplate.objects.create(
        name=template_name,
        beschreibung=f"Laufzettel: {auto_name}",
        kategorie="bearbeitung",
        ist_aktiv=True,
        ist_laufzettel=True,
        ist_graph_workflow=False,
        erstellt_von=request.user,
        trigger_event="",
    )

    # Schritte anlegen
    for i, schritt_daten in enumerate(schritte, start=1):
        stelle = Stelle.objects.get(pk=schritt_daten["stelle_id"])
        aktion = schritt_daten["aktion"]
        WorkflowStep.objects.create(
            template=template,
            reihenfolge=i,
            titel=schritt_daten.get("titel") or f"{stelle.kuerzel} – {aktion.capitalize()}",
            aktion_typ=aktion,
            zustaendig_rolle="spezifische_stelle",
            zustaendig_stelle=stelle,
            frist_tage=3,
            ist_parallel=False,
        )

    # Optionaler Ablage-Schritt (auto)
    if ablage_kategorie_id:
        WorkflowStep.objects.create(
            template=template,
            reihenfolge=len(schritte) + 1,
            titel="Ablage",
            aktion_typ="python_code",
            zustaendig_rolle="direkter_vorgesetzter",
            frist_tage=0,
            ist_parallel=False,
            auto_config={"ablage_kategorie_id": ablage_kategorie_id},
            schritt_typ="auto",
        )

    # Workflow starten
    try:
        engine = WorkflowEngine()
        instance = engine.start_workflow(template, dok, request.user)
        # Kein Vorlage-Namen → Template ist einmalig, nach Nutzung als inaktiv markieren
        if not vorlage_name:
            template.ist_aktiv = False
            template.save(update_fields=["ist_aktiv"])

        _protokolliere(
            request, dok, "geaendert",
            f"Laufzettel gestartet: {auto_name} (Instanz #{instance.pk})",
        )
        return JsonResponse({
            "ok": True,
            "instanz_id": instance.pk,
            "name": auto_name,
            "redirect": f"/dms/{pk}/",
        })
    except Exception as exc:
        logger.error("Laufzettel-Start fehlgeschlagen fuer Dokument %s: %s", pk, exc)
        template.delete()
        return JsonResponse({"fehler": str(exc)}, status=500)


@login_required
def laufzettel_vorlagen(request):
    """Gibt gespeicherte Laufzettel-Vorlagen des aktuellen Users als JSON zurueck."""
    from workflow.models import WorkflowTemplate, WorkflowStep
    vorlagen = (
        WorkflowTemplate.objects
        .filter(ist_laufzettel=True, ist_aktiv=True)
        .prefetch_related("schritte__zustaendig_stelle")
        .order_by("-erstellt_am")[:50]
    )
    ergebnis = []
    for v in vorlagen:
        schritte_liste = []
        for s in v.schritte.order_by("reihenfolge"):
            if s.zustaendig_stelle:
                schritte_liste.append({
                    "stelle_id": s.zustaendig_stelle_id,
                    "kuerzel": s.zustaendig_stelle.kuerzel,
                    "bezeichnung": s.zustaendig_stelle.bezeichnung,
                    "aktion": s.aktion_typ,
                    "titel": s.titel,
                })
        ergebnis.append({
            "id": v.pk,
            "name": v.name,
            "erstellt_von": v.erstellt_von.get_full_name() if v.erstellt_von else "",
            "steps": schritte_liste,
        })
    return JsonResponse({"vorlagen": ergebnis})


@login_required
def api_dokumentation(request):
    """Zeigt die API-Dokumentation fuer externe Systeme (SAP, Paperless, etc.)."""
    from django.conf import settings as conf_settings
    basis_url = getattr(conf_settings, "PRIMA_BASE_URL", request.build_absolute_uri("/").rstrip("/"))
    api_tokens = ApiToken.objects.all() if request.user.is_staff else ApiToken.objects.none()
    return render(request, "dms/api_dokumentation.html", {
        "basis_url": basis_url,
        "api_tokens": api_tokens,
        "api_version": "1.0",
    })


# ---------------------------------------------------------------------------
# Ablage-Kategorien verwalten (DMS-Admin)
# ---------------------------------------------------------------------------

@login_required
def ablage_liste(request):
    """Liste aller Ablage-Kategorien mit Anlegen-Moeglichkeit."""
    if not (_ist_dms_admin(request.user) or request.user.is_staff):
        messages.error(request, "Keine Berechtigung fuer diese Seite.")
        return redirect("dms:liste")

    kategorien = DokumentKategorie.objects.select_related("elternkategorie").order_by("sortierung", "name")
    form = DokumentKategorieForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        kat = form.save()
        messages.success(request, f'Ablage "{kat.name}" wurde angelegt.')
        return redirect("dms:ablage_liste")

    return render(request, "dms/ablage_liste.html", {
        "kategorien": kategorien,
        "form": form,
    })


@login_required
def ablage_bearbeiten(request, pk):
    """Ablage-Kategorie bearbeiten."""
    if not (_ist_dms_admin(request.user) or request.user.is_staff):
        messages.error(request, "Keine Berechtigung fuer diese Seite.")
        return redirect("dms:liste")

    kat = get_object_or_404(DokumentKategorie, pk=pk)
    form = DokumentKategorieForm(request.POST or None, instance=kat)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Ablage "{kat.name}" wurde gespeichert.')
        return redirect("dms:ablage_liste")

    return render(request, "dms/ablage_bearbeiten.html", {
        "kat": kat,
        "form": form,
    })


@login_required
def ablage_loeschen(request, pk):
    """Ablage-Kategorie loeschen (nur wenn keine Dokumente zugeordnet)."""
    if not (_ist_dms_admin(request.user) or request.user.is_staff):
        messages.error(request, "Keine Berechtigung fuer diese Seite.")
        return redirect("dms:liste")

    kat = get_object_or_404(DokumentKategorie, pk=pk)

    if request.method == "POST":
        anzahl = kat.dokumente.count()
        if anzahl > 0:
            messages.error(request, f'Ablage "{kat.name}" kann nicht geloescht werden – {anzahl} Dokument(e) zugeordnet.')
        else:
            name = kat.name
            kat.delete()
            messages.success(request, f'Ablage "{name}" wurde geloescht.')
        return redirect("dms:ablage_liste")

    return render(request, "dms/ablage_loeschen.html", {"kat": kat})


# ---------------------------------------------------------------------------
# Loeschplanung (DMS-Admin + DSB-Workflow)
# ---------------------------------------------------------------------------

@login_required
def dokument_loeschen_planen(request, pk):
    """DMS-Admin plant die Loeschung eines Dokuments.

    Setzt loeschen_am + loeschen_begruendung, startet den DSB-Loeschworkflow.
    Dreifache Sicherheitsabfrage erfolgt im Frontend (dms_loeschen_planung.js).
    Nur DMS-Admin oder Staff darf diese View aufrufen.
    """
    if not (_ist_dms_admin(request.user) or request.user.is_staff):
        return JsonResponse({"ok": False, "fehler": "Keine Berechtigung."}, status=403)

    dok = get_object_or_404(Dokument, pk=pk)

    if request.method != "POST":
        return JsonResponse({"ok": False, "fehler": "Nur POST erlaubt."}, status=405)

    # Bereits ein aktiver Loeschantrag?
    if dok.loeschen_am and dok.loeschen_genehmigt:
        return JsonResponse(
            {"ok": False, "fehler": "Loeschung bereits freigegeben – Dokument wird am geplanten Datum geloescht."},
            status=400,
        )

    import re
    from datetime import date

    loeschen_am_str = request.POST.get("loeschen_am", "").strip()
    begruendung = request.POST.get("begruendung", "").strip()
    bestaetigung = request.POST.get("bestaetigung", "").strip()

    # Pflichtfelder
    if not loeschen_am_str:
        return JsonResponse({"ok": False, "fehler": "Loeschdatum ist Pflichtfeld."})
    if not begruendung:
        return JsonResponse({"ok": False, "fehler": "Begruendung ist Pflichtfeld."})
    if bestaetigung != "LOESCHEN":
        return JsonResponse({"ok": False, "fehler": "Bestaetigung muss exakt 'LOESCHEN' lauten."})

    # Datum parsen
    try:
        loeschen_am = date.fromisoformat(loeschen_am_str)
    except ValueError:
        return JsonResponse({"ok": False, "fehler": "Ungaeltiges Datum (erwartet YYYY-MM-DD)."})

    if loeschen_am < date.today():
        return JsonResponse({"ok": False, "fehler": "Loeschdatum muss in der Zukunft liegen."})

    # Loeschkennzeichen setzen
    dok.loeschen_am = loeschen_am
    dok.loeschen_begruendung = begruendung
    dok.loeschen_beantragt_von = request.user
    dok.loeschen_genehmigt = False
    dok.save(update_fields=[
        "loeschen_am", "loeschen_begruendung", "loeschen_beantragt_von", "loeschen_genehmigt"
    ])

    # Protokoll
    ZugriffsProtokoll.objects.create(
        dokument=dok,
        user=request.user,
        aktion="loeschen",
        zeitpunkt=timezone.now(),
        notiz=(
            f"Loeschantrag gestellt. Geplantes Datum: {loeschen_am}. "
            f"Begruendung: {begruendung}"
        ),
    )

    # DSB-Workflow starten
    try:
        from workflow.models import WorkflowTemplate
        from workflow.services import WorkflowEngine
        template = WorkflowTemplate.objects.filter(
            trigger_event="dms_loeschantrag_eingereicht", ist_aktiv=True
        ).first()
        if template:
            engine = WorkflowEngine()
            engine.start_workflow(template, dok, request.user)
        else:
            logger.warning(
                "DSB-Loeschworkflow-Template nicht gefunden – Loeschantrag ohne Workflow gesetzt."
            )
    except Exception as exc:
        logger.error("Fehler beim Starten des DSB-Loeschworkflows: %s", exc)

    return JsonResponse({
        "ok": True,
        "meldung": (
            f"Loeschantrag gestellt. Dokument wird am {loeschen_am:%d.%m.%Y} "
            "geloescht – sobald der DSB die Freigabe erteilt."
        ),
    })


# ---------------------------------------------------------------------------
# Persoenliche Ablage
# ---------------------------------------------------------------------------

@login_required
def meine_ablage(request):
    """Zeigt die persoenliche Ablage des eingeloggten Users.

    Zwei Abschnitte:
    - Meine Dokumente: selbst hochgeladen (erstellt_von=user)
    - Freigaben: andere haben diese Dokumente fuer mich freigegeben (sichtbar_fuer=user)
    """
    eigene = (
        Dokument.objects
        .filter(ist_persoenlich=True, erstellt_von=request.user)
        .order_by("-erstellt_am")
    )
    freigaben = (
        Dokument.objects
        .filter(ist_persoenlich=True, sichtbar_fuer=request.user)
        .exclude(erstellt_von=request.user)
        .order_by("-erstellt_am")
    )
    return render(request, "dms/meine_ablage.html", {
        "eigene": eigene,
        "freigaben": freigaben,
    })


@login_required
def meine_ablage_upload(request):
    """Upload eines Dokuments in die persoenliche Ablage mit Virenscan."""
    from utils.virusscanner import scan_datei

    form = PersoenlicheAblageUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        datei = form.cleaned_data["datei"]

        # Virenscan vor dem Speichern
        scan = scan_datei(datei)
        if not scan.sauber:
            if scan.bedrohung:
                messages.error(
                    request,
                    f"Upload abgelehnt: Virenscanner hat eine Bedrohung gefunden ({scan.bedrohung}).",
                )
            else:
                messages.error(request, f"Upload abgelehnt: {scan.fehler}")
            return render(request, "dms/meine_ablage_upload.html", {"form": form})

        inhalt_bytes = datei.read()
        mime = datei.content_type or mimetypes.guess_type(datei.name)[0] or "application/octet-stream"

        dok = Dokument(
            titel=form.cleaned_data["titel"],
            klasse=form.cleaned_data["klasse"],
            beschreibung=form.cleaned_data["beschreibung"],
            dateiname=datei.name,
            dateityp=mime,
            groesse_bytes=len(inhalt_bytes),
            erstellt_von=request.user,
            ist_persoenlich=True,
        )

        try:
            speichere_dokument(dok, inhalt_bytes)
        except ValueError as exc:
            messages.error(request, f"Verschluesselung fehlgeschlagen: {exc}")
            return render(request, "dms/meine_ablage_upload.html", {"form": form})

        dok.save()
        suchvektor_befuellen(dok)
        _protokolliere(request, dok, aktion="erstellt", notiz="Persoenliche Ablage")
        messages.success(request, f'"{dok.titel}" wurde in deine persoenliche Ablage hochgeladen.')
        return redirect("dms:meine_ablage")

    return render(request, "dms/meine_ablage_upload.html", {"form": form})


@login_required
def meine_ablage_freigabe(request, pk):
    """Verwaltet Freigaben eines persoenlichen Dokuments.

    Nur der Eigentuemer darf Freigaben verwalten.
    """
    dok = get_object_or_404(Dokument, pk=pk, ist_persoenlich=True, erstellt_von=request.user)
    form = PersoenlicheAblageFreigabeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ziel_user = form.cleaned_data["user"]
        if ziel_user == request.user:
            messages.warning(request, "Du hast bereits Zugriff auf dein eigenes Dokument.")
        elif dok.sichtbar_fuer.filter(pk=ziel_user.pk).exists():
            messages.warning(request, f"{ziel_user.get_full_name() or ziel_user.username} hat bereits Zugriff.")
        else:
            dok.sichtbar_fuer.add(ziel_user)
            _protokolliere(
                request, dok, aktion="zugriff_genehmigt",
                notiz=f"Freigabe fuer {ziel_user.username} durch Eigentuemer",
            )
            messages.success(
                request,
                f"Dokument fuer {ziel_user.get_full_name() or ziel_user.username} freigegeben.",
            )
        return redirect("dms:meine_ablage_freigabe", pk=pk)

    freigegebene = dok.sichtbar_fuer.all().order_by("last_name", "first_name")
    return render(request, "dms/meine_ablage_freigabe.html", {
        "dok": dok,
        "freigegebene": freigegebene,
        "form": form,
    })


@login_required
def meine_ablage_freigabe_entfernen(request, pk, user_pk):
    """Entfernt die Freigabe eines Users von einem persoenlichen Dokument (POST)."""
    from django.contrib.auth.models import User as AuthUser

    dok = get_object_or_404(Dokument, pk=pk, ist_persoenlich=True, erstellt_von=request.user)
    ziel_user = get_object_or_404(AuthUser, pk=user_pk)

    if request.method == "POST":
        dok.sichtbar_fuer.remove(ziel_user)
        _protokolliere(
            request, dok, aktion="zugriff_widerrufen",
            notiz=f"Freigabe fuer {ziel_user.username} entfernt durch Eigentuemer",
        )
        messages.success(
            request,
            f"Freigabe fuer {ziel_user.get_full_name() or ziel_user.username} wurde entfernt.",
        )

    return redirect("dms:meine_ablage_freigabe", pk=pk)


@login_required
def meine_ablage_loeschen(request, pk):
    """Loescht ein persoenliches Dokument (nur Eigentuemer, POST)."""
    dok = get_object_or_404(Dokument, pk=pk, ist_persoenlich=True, erstellt_von=request.user)

    if request.method == "POST":
        titel = dok.titel
        dok.delete()
        messages.success(request, f'"{titel}" wurde geloescht.')
        return redirect("dms:meine_ablage")

    return redirect("dms:meine_ablage")


# ---------------------------------------------------------------------------
# Dokument loeschen (DMS-Admin / Staff) mit dauerhaftem Protokoll
# ---------------------------------------------------------------------------

@login_required
def dokument_loeschen(request, pk):
    """DMS-Admin loescht ein Dokument mit Pflichtbegruendung.

    GET  -> HTMX-Modal mit Bestaetigunsformular
    POST -> Protokolleintrag anlegen, dann Dokument loeschen, HX-Redirect zur Liste

    Der ZugriffsProtokoll-Eintrag ueberlebt die Loeschung (SET_NULL-FK + dokument_titel).
    """
    from django.http import HttpResponse

    if not (_ist_dms_admin(request.user) or request.user.is_staff):
        return HttpResponse("Keine Berechtigung.", status=403)

    dok = get_object_or_404(Dokument, pk=pk)

    if request.method == "POST":
        begruendung = request.POST.get("begruendung", "").strip()
        bestaetigung = request.POST.get("bestaetigung", "").strip()

        fehler = None
        if not begruendung:
            fehler = "Begruendung ist Pflichtfeld."
        elif bestaetigung != "LOESCHEN":
            fehler = "Bitte exakt 'LOESCHEN' als Bestaetigung eingeben."

        if fehler:
            return render(request, "dms/partials/_loeschen_modal.html", {
                "dok": dok, "fehler": fehler,
            })

        titel = dok.titel
        pk_gespeichert = dok.pk

        # Protokolleintrag VOR der Loeschung – bleibt dauerhaft erhalten (SET_NULL-FK)
        ZugriffsProtokoll.objects.create(
            dokument=dok,
            dokument_titel=titel,
            user=request.user,
            aktion="geloescht",
            notiz=(
                f"Dokument dauerhaft geloescht (pk={pk_gespeichert}). "
                f"Begruendung: {begruendung}"
            ),
        )

        dok.delete()
        logger.info(
            "Dokument '%s' (pk=%s) geloescht von %s. Begruendung: %s",
            titel, pk_gespeichert, request.user.username, begruendung,
        )

        messages.success(request, '"%s" wurde dauerhaft geloescht. Protokoll bleibt erhalten.' % titel)
        response = HttpResponse()
        response["HX-Redirect"] = "/dms/"
        return response

    # GET: Modal rendern
    return render(request, "dms/partials/_loeschen_modal.html", {
        "dok": dok, "fehler": None,
    })


@login_required
def loeschprotokoll(request):
    """Listet alle Loeschaktionen im Audit-Trail (nur DMS-Admin / Staff)."""
    if not (_ist_dms_admin(request.user) or request.user.is_staff):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Keine Berechtigung.")

    eintraege = (
        ZugriffsProtokoll.objects
        .filter(aktion__in=["geloescht", "loeschen"])
        .select_related("user", "dokument")
        .order_by("-zeitpunkt")
    )
    return render(request, "dms/loeschprotokoll.html", {"eintraege": eintraege})
