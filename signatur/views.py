import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import MitarbeiterZertifikat, SignaturJob, SignaturProtokoll

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    """Signatur-Cockpit: Zertifikat-Status + letzte Signaturen."""
    zertifikat = MitarbeiterZertifikat.objects.filter(
        user=request.user, status="aktiv"
    ).first()

    meine_signaturen = SignaturProtokoll.objects.filter(
        unterzeichner=request.user
    ).select_related("job")[:20]

    return render(request, "signatur/dashboard.html", {
        "zertifikat": zertifikat,
        "meine_signaturen": meine_signaturen,
    })


# ---------------------------------------------------------------------------
# Signatur-Protokoll-Detail
# ---------------------------------------------------------------------------

@login_required
def protokoll_detail(request, pk):
    """Details einer einzelnen Signatur."""
    protokoll = get_object_or_404(SignaturProtokoll, pk=pk)
    # Nur eigene Signaturen oder Staff
    if protokoll.unterzeichner != request.user and not request.user.is_staff:
        messages.error(request, "Kein Zugriff auf dieses Protokoll.")
        return redirect("signatur:dashboard")
    return render(request, "signatur/protokoll_detail.html", {
        "protokoll": protokoll,
    })


# ---------------------------------------------------------------------------
# Signiertes PDF herunterladen
# ---------------------------------------------------------------------------

@login_required
def pdf_download(request, pk):
    """Signiertes PDF aus dem Protokoll herunterladen."""
    protokoll = get_object_or_404(SignaturProtokoll, pk=pk)
    if protokoll.unterzeichner != request.user and not request.user.is_staff:
        messages.error(request, "Kein Zugriff.")
        return redirect("signatur:dashboard")

    if not protokoll.signiertes_pdf:
        messages.error(request, "Kein PDF gespeichert.")
        return redirect("signatur:protokoll_detail", pk=pk)

    dateiname = protokoll.job.dokument_name.replace(" ", "_") + "_signiert.pdf"
    response = HttpResponse(bytes(protokoll.signiertes_pdf), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response


# ---------------------------------------------------------------------------
# Zertifikat-Verwaltung (nur Staff)
# ---------------------------------------------------------------------------

@login_required
def zertifikat_liste(request):
    """Uebersicht aller Mitarbeiter-Zertifikate (nur Staff)."""
    if not request.user.is_staff:
        messages.error(request, "Nur Administratoren.")
        return redirect("signatur:dashboard")

    zertifikate = MitarbeiterZertifikat.objects.select_related("user").order_by(
        "status", "gueltig_bis"
    )
    return render(request, "signatur/zertifikat_liste.html", {
        "zertifikate": zertifikate,
    })


@login_required
def zertifikat_sperren(request, pk):
    """Zertifikat sperren (nur Staff)."""
    if not request.user.is_staff:
        messages.error(request, "Nur Administratoren.")
        return redirect("signatur:dashboard")

    zert = get_object_or_404(MitarbeiterZertifikat, pk=pk)
    if request.method == "POST":
        zert.status = "gesperrt"
        zert.save()
        messages.success(request, f"Zertifikat von {zert.user.get_full_name()} gesperrt.")
    return redirect("signatur:zertifikat_liste")


# ---------------------------------------------------------------------------
# Dokumentation als PDF
# ---------------------------------------------------------------------------

@login_required
def dokumentation_pdf(request):
    """Gibt die Systemdokumentation als PDF zurueck (WeasyPrint)."""
    from django.conf import settings
    from django.template.loader import render_to_string
    from weasyprint import HTML

    backend_name = getattr(settings, "SIGNATUR_BACKEND", "intern")
    gateway_url = getattr(settings, "SIGNATUR_SIGN_ME_URL", "nicht konfiguriert")

    html_string = render_to_string("signatur/doku_pdf.html", {
        "backend_name": backend_name,
        "gateway_url": gateway_url,
        "request": request,
    })

    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="Signatur_Systemdokumentation.pdf"'
    return response
