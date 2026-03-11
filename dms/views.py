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

from .forms import DokumentNeuForm, DokumentSucheForm, DokumentUploadForm, PaperlessWorkflowRegelForm, ZugriffsantragForm
from .models import DAUER_OPTIONEN, ApiToken, Dokument, DokumentVersion, DokumentZugriffsschluessel, PaperlessWorkflowRegel, ZugriffsProtokoll
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
            if task.ist_zugewiesen_an(request.user):
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
    qs = Dokument.objects.select_related("kategorie", "eigentuemereinheit").prefetch_related("tags")

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

    return render(request, "dms/dokument_liste.html", {
        "form": form,
        "seite": seite,
        "titel": "Dokumente",
        "aktive_schluessel_ids": aktive_schluessel_ids,
        "posteingang": posteingang,
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

def _erstelle_leere_datei(dateityp: str) -> tuple[bytes, str, str]:
    """Gibt (inhalt_bytes, dateiname, mime_typ) fuer eine leere Vorlage zurueck.

    Unterstuetzte Typen: docx, xlsx
    """
    import io

    if dateityp == "docx":
        from docx import Document
        buf = io.BytesIO()
        Document().save(buf)
        return buf.getvalue(), "dokument.docx", \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if dateityp == "xlsx":
        from openpyxl import Workbook
        buf = io.BytesIO()
        Workbook().save(buf)
        return buf.getvalue(), "tabelle.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

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

    zugriffe = dok.zugriffe.select_related("user").order_by("-zeitpunkt")[:20]
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
    from workflow.models import WorkflowInstance
    dok_ct = ContentType.objects.get_for_model(Dokument)
    workflow_instanzen = (
        WorkflowInstance.objects
        .filter(content_type=dok_ct, object_id=dok.pk)
        .select_related("template", "gestartet_von")
        .order_by("-gestartet_am")[:10]
    )

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
    prima_base = getattr(django_settings, "PRIMA_BASE_URL", "").rstrip("/")

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
            "lang":        "de",
            "mode":        "edit",
            "user": {
                "id":   str(request.user.pk),
                "name": request.user.get_full_name() or request.user.username,
            },
        },
    }

    token = _onlyoffice_jwt(config)

    _protokolliere(request, dok, aktion="vorschau", notiz="OnlyOffice-Editor geoeffnet")

    return render(request, "dms/onlyoffice_editor.html", {
        "dok": dok,
        "onlyoffice_url": onlyoffice_url,
        "config_json":    json.dumps(config),
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

    dok = get_object_or_404(Dokument, pk=pk)

    try:
        # Datei vom OnlyOffice-Server herunterladen
        with urllib.request.urlopen(download_url, timeout=30) as resp:
            neuer_inhalt = resp.read()
    except Exception as exc:
        logger.error("OnlyOffice Callback: Download fehlgeschlagen fuer Dok %s: %s", pk, exc)
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
    onlyoffice_url = getattr(django_settings, "ONLYOFFICE_URL", "").rstrip("/")

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
    """Zeigt eine archivierte Version inline im Browser (PDF, Bilder)."""
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel.")
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

    _protokolliere(request, dok, "vorschau", f"Version {version_nr} (Archiv-Vorschau)")

    response = HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="{version.dateiname}"'
    return response


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
