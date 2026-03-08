import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BewerbungDokumentForm, BewerbungForm, HREinstellungForm
from .models import Bewerbung, BewerbungDokument
from .services import lehne_ab, stelle_ein

logger = logging.getLogger(__name__)


def _nur_hr(user):
    """Prueft ob der User HR-Rechte hat."""
    return user.is_staff or user.has_perm("hr.hr_view_stammdaten")


# ── Bewerber-Seite (kein Login noetig) ─────────────────────────────────────

def bewerbung_erfassen(request):
    """Bewerber fuellt am Intranet-PC den Bogen aus. Kein Login noetig."""
    if request.method == "POST":
        form = BewerbungForm(request.POST)
        if form.is_valid():
            bewerbung = form.save()
            return redirect("bewerbung:erfassen_dokumente", pk=bewerbung.pk)
    else:
        form = BewerbungForm()
    return render(request, "bewerbung/erfassen.html", {"form": form})


def bewerbung_dokumente(request, pk):
    """Schritt 2: Dokumente zur Bewerbung hochladen."""
    bewerbung = get_object_or_404(Bewerbung, pk=pk, status=Bewerbung.STATUS_NEU)

    if request.method == "POST":
        if "fertig" in request.POST:
            return redirect("bewerbung:danke")

        form = BewerbungDokumentForm(request.POST, request.FILES)
        if form.is_valid():
            datei = form.cleaned_data["datei"]
            try:
                from utils.virusscanner import scan_datei
                scan = scan_datei(datei)
                if not scan.sauber:
                    messages.error(request, f"Datei abgelehnt: Bedrohung gefunden ({scan.bedrohung}).")
                    return render(request, "bewerbung/dokumente.html", {
                        "bewerbung": bewerbung, "form": form,
                        "vorhandene": bewerbung.dokumente.all(),
                    })
            except Exception as exc:
                logger.warning("Virenscanner-Fehler: %s", exc)

            inhalt_roh = datei.read()
            try:
                from dokumente.services import verschluessel_dokument
                inhalt_verschluesselt = verschluessel_dokument(inhalt_roh)
            except ValueError as exc:
                messages.error(request, f"Verschluesselung nicht moeglich: {exc}")
                return render(request, "bewerbung/dokumente.html", {
                    "bewerbung": bewerbung, "form": form,
                    "vorhandene": bewerbung.dokumente.all(),
                })

            BewerbungDokument.objects.create(
                bewerbung=bewerbung,
                typ=form.cleaned_data["typ"],
                dateiname=datei.name,
                dateityp=datei.content_type,
                inhalt_verschluesselt=inhalt_verschluesselt,
                groesse_bytes=datei.size,
            )
            messages.success(request, f"'{datei.name}' hochgeladen.")
            return redirect("bewerbung:erfassen_dokumente", pk=pk)
    else:
        form = BewerbungDokumentForm()

    return render(request, "bewerbung/dokumente.html", {
        "bewerbung": bewerbung,
        "form": form,
        "vorhandene": bewerbung.dokumente.all(),
    })


def bewerbung_danke(request):
    """Abschlussseite nach erfolgreicher Bewerbungserfassung."""
    return render(request, "bewerbung/danke.html")


# ── HR-Bereich (Login + HR-Recht) ──────────────────────────────────────────

@login_required
def hr_liste(request):
    """HR-Uebersicht aller Bewerbungen."""
    if not _nur_hr(request.user):
        raise Http404

    status_filter = request.GET.get("status", "")
    bewerbungen = Bewerbung.objects.all()
    if status_filter:
        bewerbungen = bewerbungen.filter(status=status_filter)

    return render(request, "bewerbung/hr_liste.html", {
        "bewerbungen": bewerbungen,
        "status_filter": status_filter,
        "status_choices": Bewerbung.STATUS_CHOICES,
    })


@login_required
def hr_detail(request, pk):
    """HR-Detailansicht einer Bewerbung."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)

    if request.method == "POST" and "pruefung" in request.POST:
        bewerbung.status = Bewerbung.STATUS_PRUEFUNG
        bewerbung.bearbeitet_von = request.user
        bewerbung.save()
        messages.success(request, "Bewerbung in Pruefung gesetzt.")
        return redirect("bewerbung:hr_detail", pk=pk)

    return render(request, "bewerbung/hr_detail.html", {
        "bewerbung": bewerbung,
        "hr_form": HREinstellungForm(instance=bewerbung),
        "dokumente": bewerbung.dokumente.all(),
    })


@login_required
def hr_detail_speichern(request, pk):
    """Speichert HR-Felder (Stelle, Eintrittsdatum, Notiz)."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)
    form = HREinstellungForm(request.POST, instance=bewerbung)
    if form.is_valid():
        b = form.save(commit=False)
        b.bearbeitet_von = request.user
        b.save()
        messages.success(request, "HR-Angaben gespeichert.")
    else:
        messages.error(request, "Bitte Eingaben pruefen.")
    return redirect("bewerbung:hr_detail", pk=pk)


@login_required
def hr_einstellen(request, pk):
    """Stellt den Bewerber ein – loescht Bewerbung, legt HRMitarbeiter an."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)

    if request.method == "POST":
        try:
            hr_ma = stelle_ein(bewerbung, erstellt_von=request.user)
            messages.success(
                request,
                f"{hr_ma.vollname} wurde eingestellt (Personalnummer: {hr_ma.personalnummer}). "
                f"Bewerbungsdaten wurden DSGVO-konform geloescht.",
            )
            return redirect("hr:detail", pk=hr_ma.pk)
        except Exception as exc:
            logger.exception("Einstellung fehlgeschlagen fuer Bewerbung pk=%s: %s", pk, exc)
            messages.error(request, f"Fehler bei der Einstellung: {exc}")
            return redirect("bewerbung:hr_detail", pk=pk)

    return render(request, "bewerbung/hr_einstellen.html", {"bewerbung": bewerbung})


@login_required
def hr_ablehnen(request, pk):
    """Lehnt Bewerbung ab – DSGVO Hard-Delete aller Daten."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)

    if request.method == "POST":
        name = bewerbung.vollname
        lehne_ab(bewerbung, abgelehnt_von=request.user)
        messages.success(
            request,
            f"Bewerbung von {name} abgelehnt. Alle Daten wurden DSGVO-konform geloescht.",
        )
        return redirect("bewerbung:hr_liste")

    return render(request, "bewerbung/hr_ablehnen.html", {"bewerbung": bewerbung})


@login_required
def hr_dokument_download(request, pk, dok_pk):
    """Entschluesselter Download eines Bewerbungsdokuments (nur HR)."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)
    dok = get_object_or_404(BewerbungDokument, pk=dok_pk, bewerbung=bewerbung)

    from cryptography.fernet import InvalidToken
    from dokumente.services import entschluessel_dokument
    try:
        inhalt = entschluessel_dokument(dok.inhalt_verschluesselt)
    except (InvalidToken, ValueError):
        messages.error(request, "Dokument konnte nicht entschlueselt werden.")
        return redirect("bewerbung:hr_detail", pk=pk)

    response = HttpResponse(inhalt, content_type=dok.dateityp)
    response["Content-Disposition"] = f'attachment; filename="{dok.dateiname}"'
    return response
