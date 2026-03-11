import logging

from cryptography.fernet import InvalidToken
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DokumentHochladenForm
from .models import DokumentZugriff, SensiblesDokument
from .services import entschluessel_dokument, verschluessel_dokument


def _get_client_ip(request):
    """Liest die echte Client-IP auch hinter einem Reverse-Proxy."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

logger = logging.getLogger(__name__)


@login_required
def dokument_liste(request):
    """Zeigt die Dokument-Uebersicht.

    Staff sieht alle Dokumente (optional gefiltert nach User).
    Normale User sehen nur ihre eigenen.
    """
    filter_user = None
    alle_user = None

    if request.user.is_staff:
        alle_user = User.objects.filter(is_active=True).order_by("last_name", "first_name")
        user_id = request.GET.get("user")
        if user_id:
            try:
                filter_user = User.objects.get(pk=user_id)
                dokumente = SensiblesDokument.objects.select_related(
                    "user", "hochgeladen_von"
                ).filter(user=filter_user)
            except User.DoesNotExist:
                dokumente = SensiblesDokument.objects.select_related(
                    "user", "hochgeladen_von"
                ).all()
        else:
            dokumente = SensiblesDokument.objects.select_related(
                "user", "hochgeladen_von"
            ).all()
    else:
        dokumente = SensiblesDokument.objects.filter(user=request.user)

    # Zugriffszaehler direkt ans Queryset annotieren
    from django.db.models import Count
    dokumente = dokumente.annotate(zugriff_anzahl=Count("zugriffe"))

    return render(request, "dokumente/liste.html", {
        "dokumente": dokumente,
        "alle_user": alle_user,
        "filter_user": filter_user,
    })


@login_required
def dokument_hochladen(request):
    """Laedt ein Dokument hoch und speichert es verschluesselt."""
    if request.method == "POST":
        form = DokumentHochladenForm(
            request.POST, request.FILES, is_staff=request.user.is_staff
        )
        if form.is_valid():
            datei = form.cleaned_data["datei"]

            # Virenscanner vor dem Speichern
            try:
                from utils.virusscanner import scan_datei
                scan = scan_datei(datei)
                if not scan.sauber:
                    messages.error(
                        request,
                        f"Datei abgelehnt: Virenscanner hat eine Bedrohung gefunden ({scan.bedrohung}).",
                    )
                    return render(request, "dokumente/hochladen.html", {"form": form})
            except Exception as exc:
                logger.warning("Virenscanner-Fehler beim Dokument-Upload: %s", exc)

            inhalt_roh = datei.read()

            try:
                inhalt_verschluesselt = verschluessel_dokument(inhalt_roh)
            except ValueError as exc:
                messages.error(request, f"Verschluesselung nicht moeglich: {exc}")
                return render(request, "dokumente/hochladen.html", {"form": form})

            # Ziel-User: Staff kann fuer andere hochladen, normale User nur fuer sich selbst
            if request.user.is_staff and form.cleaned_data.get("ziel_user"):
                ziel_user = form.cleaned_data["ziel_user"]
            else:
                ziel_user = request.user

            SensiblesDokument.objects.create(
                user=ziel_user,
                hochgeladen_von=request.user,
                kategorie=form.cleaned_data["kategorie"],
                dateiname=datei.name,
                dateityp=datei.content_type,
                inhalt_verschluesselt=inhalt_verschluesselt,
                groesse_bytes=datei.size,
                beschreibung=form.cleaned_data.get("beschreibung", ""),
                gueltig_bis=form.cleaned_data.get("gueltig_bis"),
            )
            logger.info(
                "Dokument hochgeladen: '%s' (Kat: %s) fuer User '%s' von '%s'",
                datei.name,
                form.cleaned_data["kategorie"],
                ziel_user.username,
                request.user.username,
            )
            messages.success(
                request,
                f"'{datei.name}' wurde verschluesselt gespeichert.",
            )
            next_url = request.POST.get("next", "")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect("dokumente:liste")
    else:
        # Vorauswahl via GET-Parameter (z.B. vom HR-Stammdaten-Link)
        initial = {}
        if request.user.is_staff:
            fuer_user_pk = request.GET.get("fuer_user")
            if fuer_user_pk:
                try:
                    initial["ziel_user"] = User.objects.get(pk=fuer_user_pk)
                except User.DoesNotExist:
                    pass
        form = DokumentHochladenForm(is_staff=request.user.is_staff, initial=initial)

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    return render(request, "dokumente/hochladen.html", {"form": form, "next_url": next_url})


@login_required
def dokument_download(request, pk):
    """Entschluesselt ein Dokument und liefert es als Download-Response."""
    dokument = get_object_or_404(SensiblesDokument, pk=pk)

    # Zugriffskontrolle: nur Owner oder Staff
    if not request.user.is_staff and dokument.user != request.user:
        raise Http404

    try:
        inhalt = entschluessel_dokument(dokument.inhalt_verschluesselt)
    except (InvalidToken, ValueError) as exc:
        logger.error(
            "Download-Entschluesselung fehlgeschlagen (Dokument pk=%s): %s", pk, exc
        )
        messages.error(request, "Das Dokument konnte nicht entschluesselt werden.")
        return redirect("dokumente:liste")

    # Zugriff protokollieren (unveraenderlicher Audit-Trail)
    DokumentZugriff.objects.create(
        dokument=dokument,
        user=request.user,
        ip_adresse=_get_client_ip(request),
    )
    logger.info(
        "Dokument-Download: '%s' (pk=%s) von User '%s'",
        dokument.dateiname,
        pk,
        request.user.username,
    )
    response = HttpResponse(inhalt, content_type=dokument.dateityp)
    response["Content-Disposition"] = (
        f'attachment; filename="{dokument.dateiname}"'
    )
    response["Content-Length"] = len(inhalt)
    return response


@login_required
def dokument_loeschen(request, pk):
    """Loescht ein Dokument nach Bestaetigung via POST."""
    dokument = get_object_or_404(SensiblesDokument, pk=pk)

    # Zugriffskontrolle: nur Owner oder Staff
    if not request.user.is_staff and dokument.user != request.user:
        raise Http404

    if request.method == "POST":
        name = dokument.dateiname
        dokument.delete()
        logger.info(
            "Dokument geloescht: '%s' (pk=%s) von User '%s'",
            name,
            pk,
            request.user.username,
        )
        messages.success(request, f"'{name}' wurde geloescht.")
        return redirect("dokumente:liste")

    return render(request, "dokumente/loeschen.html", {"dokument": dokument})


@login_required
def zugriffs_log(request):
    """Zeigt das vollstaendige Zugriffsprotokoll (nur Staff).

    Normale User sehen nur Zugriffe auf ihre eigenen Dokumente.
    """
    if request.user.is_staff:
        zugriffe = DokumentZugriff.objects.select_related(
            "dokument", "dokument__user", "user"
        ).all()[:500]
    else:
        zugriffe = DokumentZugriff.objects.select_related(
            "dokument", "user"
        ).filter(dokument__user=request.user)[:200]

    return render(request, "dokumente/zugriffs_log.html", {"zugriffe": zugriffe})
