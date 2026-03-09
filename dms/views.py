"""DMS-Views: Dokumentenliste, Upload, Download, Zugriffsverwaltung."""
import logging
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models as db_models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from guardian.shortcuts import assign_perm, remove_perm

from .forms import DokumentSucheForm, DokumentUploadForm, ZugriffsantragForm
from .models import DAUER_OPTIONEN, Dokument, DokumentZugriffsschluessel, ZugriffsProtokoll
from .services import lade_dokument, speichere_dokument

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

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


def _darf_sensibel_zugreifen(request, dokument):
    """Gibt True zurueck wenn der User auf ein sensibles Dokument zugreifen darf.

    Staff mit aktivem Zugriffsschluessel ODER Staff ohne Einschraenkung
    (nur wenn kein Zugriffsschluessel-System noetig, z.B. Admin-Superuser).
    Normale User brauchen immer einen aktiven Zugriffsschluessel.
    """
    if not request.user.is_authenticated:
        return False
    # Superuser: immer Zugriff (keine Einschraenkung fuer Sysadmin)
    if request.user.is_superuser:
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
    qs = Dokument.objects.select_related("kategorie").prefetch_related("tags")

    # Sensible Dokumente nur fuer Staff und Superuser sichtbar (Metadaten)
    if not request.user.is_staff:
        qs = qs.filter(klasse="offen")

    if form.is_valid():
        q = form.cleaned_data.get("q")
        klasse = form.cleaned_data.get("klasse")
        kategorie = form.cleaned_data.get("kategorie")
        tag = form.cleaned_data.get("tag")

        if q:
            from django.db import connection
            if connection.vendor == "postgresql":
                from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
                vektor = SearchVector("titel", weight="A") + SearchVector("beschreibung", weight="B")
                query = SearchQuery(q, config="german")
                qs = (
                    qs.annotate(rank=SearchRank(vektor, query))
                    .filter(rank__gte=0.01)
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

    return render(request, "dms/dokument_liste.html", {
        "form": form,
        "seite": seite,
        "titel": "Dokumente",
        "aktive_schluessel_ids": aktive_schluessel_ids,
    })


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@login_required
def dokument_upload(request):
    """Upload eines neuen Dokuments (Klasse 1 oder 2)."""
    form = DokumentUploadForm(request.POST or None, request.FILES or None)

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

        _protokolliere(request, dok, aktion="erstellt")
        messages.success(request, f'Dokument "{dok.titel}" wurde erfolgreich hochgeladen.')
        return redirect("dms:liste")

    return render(request, "dms/dokument_upload.html", {"form": form})


# ---------------------------------------------------------------------------
# Download / Vorschau / Detail
# ---------------------------------------------------------------------------

@login_required
def dokument_download(request, pk):
    """Laedt das Dokument herunter – entschluesselt falls noetig.

    Sensible Dokumente: nur mit aktivem Zugriffsschluessel moeglich.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel fuer dieses Dokument.")
        return redirect("dms:zugriff_beantragen", pk=pk)

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
    """Zeigt das Dokument inline im Browser (PDF, Bilder).

    Sensible Dokumente: nur mit aktivem Zugriffsschluessel moeglich.
    """
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not _darf_sensibel_zugreifen(request, dok):
        messages.error(request, "Sie benoetigen einen gueltigen Zugriffsschluessel fuer dieses Dokument.")
        return redirect("dms:zugriff_beantragen", pk=pk)

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

    # Sensible: Metadaten sichtbar, aber Zugriffsstatus anzeigen
    if dok.klasse == "sensibel" and not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
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

    return render(request, "dms/dokument_detail.html", {
        "dok": dok,
        "zugriffe": zugriffe,
        "aktiver_schluessel": aktiver_schluessel,
        "offener_antrag": offener_antrag,
        "darf_zugreifen": _darf_sensibel_zugreifen(request, dok) if dok.klasse == "sensibel" else True,
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
# Zugriffsschluessel – Staff-Verwaltung
# ---------------------------------------------------------------------------

@login_required
def zugriffsantraege_liste(request):
    """Staff-View: Alle offenen und aktuellen Zugriffsantraege."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

    offene = DokumentZugriffsschluessel.objects.filter(
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    ).select_related("user", "dokument").order_by("antrag_zeitpunkt")

    aktive = DokumentZugriffsschluessel.objects.filter(
        status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
        gueltig_bis__gt=timezone.now(),
    ).select_related("user", "dokument", "genehmigt_von").order_by("gueltig_bis")

    abgelaufen = DokumentZugriffsschluessel.objects.exclude(
        status__in=[
            DokumentZugriffsschluessel.STATUS_OFFEN,
            DokumentZugriffsschluessel.STATUS_GENEHMIGT,
        ]
    ).select_related("user", "dokument", "genehmigt_von").order_by("-antrag_zeitpunkt")[:50]

    return render(request, "dms/zugriffsantraege.html", {
        "offene": offene,
        "aktive": aktive,
        "abgelaufen": abgelaufen,
    })


@login_required
def zugriff_genehmigen(request, schluessel_pk):
    """Staff genehmigt einen Zugriffsantrag und setzt das Ablaufdatum."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:zugriffsantraege")

    schluessel = get_object_or_404(
        DokumentZugriffsschluessel,
        pk=schluessel_pk,
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    )

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
    """Staff lehnt einen Zugriffsantrag ab."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:zugriffsantraege")

    schluessel = get_object_or_404(
        DokumentZugriffsschluessel,
        pk=schluessel_pk,
        status=DokumentZugriffsschluessel.STATUS_OFFEN,
    )

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
    """Staff widerruft einen aktiven Zugriffsschluessel vorzeitig."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:zugriffsantraege")

    schluessel = get_object_or_404(
        DokumentZugriffsschluessel,
        pk=schluessel_pk,
        status=DokumentZugriffsschluessel.STATUS_GENEHMIGT,
    )

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
