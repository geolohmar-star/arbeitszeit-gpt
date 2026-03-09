"""DMS-Views: Dokumentenliste, Upload, Download, Suche."""
import logging
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models as db_models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DokumentSucheForm, DokumentUploadForm
from .models import Dokument, ZugriffsProtokoll
from .services import lade_dokument, speichere_dokument

logger = logging.getLogger(__name__)


def _protokolliere(request, dokument, aktion="download"):
    """Schreibt einen ZugriffsProtokoll-Eintrag."""
    ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip:
        ip = ip.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    ZugriffsProtokoll.objects.create(
        dokument=dokument,
        user=request.user if request.user.is_authenticated else None,
        aktion=aktion,
        ip_adresse=ip,
    )


@login_required
def dokument_liste(request):
    """Listet alle fuer den User sichtbaren Dokumente mit Suche."""
    form = DokumentSucheForm(request.GET or None)
    qs = Dokument.objects.select_related("kategorie").prefetch_related("tags")

    # Sensible Dokumente nur fuer Staff sichtbar
    if not request.user.is_staff:
        qs = qs.filter(klasse="offen")

    if form.is_valid():
        q = form.cleaned_data.get("q")
        klasse = form.cleaned_data.get("klasse")
        kategorie = form.cleaned_data.get("kategorie")
        tag = form.cleaned_data.get("tag")

        if q:
            # Einfache Textsuche auf Titel + Beschreibung (sqlite-kompatibel)
            # Auf PostgreSQL wird der GIN-Suchvektor bevorzugt
            from django.db.backends.signals import connection_created
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
                # SQLite-Fallback: einfaches icontains
                qs = qs.filter(
                    db_models.Q(titel__icontains=q) | db_models.Q(beschreibung__icontains=q)
                )
        if klasse:
            qs = qs.filter(klasse=klasse)
        if kategorie:
            qs = qs.filter(kategorie=kategorie)
        if tag:
            qs = qs.filter(tags=tag)

    paginator = Paginator(qs, 25)
    seite = paginator.get_page(request.GET.get("page"))

    return render(request, "dms/dokument_liste.html", {
        "form": form,
        "seite": seite,
        "titel": "Dokumente",
    })


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

        # Inhalt je nach Klasse verschluesseln oder roh speichern
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


@login_required
def dokument_download(request, pk):
    """Laedt das Dokument herunter – entschluesselt falls noetig."""
    dok = get_object_or_404(Dokument, pk=pk)

    # Sensible Dokumente nur fuer Staff
    if dok.klasse == "sensibel" and not request.user.is_staff:
        messages.error(request, "Sie haben keine Berechtigung dieses Dokument herunterzuladen.")
        return redirect("dms:liste")

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
    """Zeigt das Dokument inline im Browser (PDF, Bilder)."""
    dok = get_object_or_404(Dokument, pk=pk)

    if dok.klasse == "sensibel" and not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

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

    if dok.klasse == "sensibel" and not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("dms:liste")

    zugriffe = dok.zugriffe.select_related("user").order_by("-zeitpunkt")[:20]

    return render(request, "dms/dokument_detail.html", {
        "dok": dok,
        "zugriffe": zugriffe,
    })
