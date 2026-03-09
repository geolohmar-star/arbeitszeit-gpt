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


# ---------------------------------------------------------------------------
# PDF-Signaturpruefung
# ---------------------------------------------------------------------------

@login_required
def signatur_pruefen(request):
    """PDF hochladen und digitale Signatur pruefen."""
    signaturen = []
    fehler = None
    dateiname = None

    if request.method == "POST":
        hochgeladen = request.FILES.get("pdf_datei")
        if not hochgeladen:
            fehler = "Keine Datei hochgeladen."
        elif not hochgeladen.name.lower().endswith(".pdf"):
            fehler = "Nur PDF-Dateien sind zulaessig."
        elif hochgeladen.size > 20 * 1024 * 1024:
            fehler = "Datei zu gross (max. 20 MB)."
        else:
            dateiname = hochgeladen.name
            try:
                import io
                from pyhanko.sign.validation import validate_pdf_signature
                from pyhanko.pdf_utils.reader import PdfFileReader

                pdf_bytes = hochgeladen.read()
                reader = PdfFileReader(io.BytesIO(pdf_bytes))
                eingebettete = list(reader.embedded_signatures)

                if not eingebettete:
                    fehler = "Keine digitalen Signaturen in dieser Datei gefunden."
                else:
                    for sig in eingebettete:
                        try:
                            status = validate_pdf_signature(sig)
                            unveraendert = (
                                status.coverage is not None
                                and str(status.coverage) in (
                                    "ModificationLevel.LTA_UPDATES",
                                    "ModificationLevel.FORM_FILLING",
                                )
                            ) or getattr(status, "intact", True)
                        except Exception:
                            unveraendert = None

                        cert = getattr(sig, "signer_cert", None)
                        unterzeichner = "Unbekannt"
                        aussteller = "Unbekannt"
                        seriennummer = "–"

                        if cert:
                            try:
                                unterzeichner = cert.subject.human_friendly
                            except Exception:
                                unterzeichner = str(cert.subject)
                            try:
                                aussteller = cert.issuer.human_friendly
                            except Exception:
                                aussteller = str(cert.issuer)
                            try:
                                seriennummer = hex(cert.serial_number)
                            except Exception:
                                pass

                        zeitstempel = getattr(sig, "self_reported_timestamp", None)

                        signaturen.append({
                            "unterzeichner": unterzeichner,
                            "aussteller": aussteller,
                            "seriennummer": seriennummer,
                            "zeitstempel": zeitstempel,
                            "unveraendert": unveraendert,
                        })
            except Exception as exc:
                logger.warning("Signaturpruefung fehlgeschlagen: %s", exc)
                fehler = f"Pruefung fehlgeschlagen: {exc}"

    return render(request, "signatur/signatur_pruefen.html", {
        "signaturen": signaturen,
        "fehler": fehler,
        "dateiname": dateiname,
    })


# ---------------------------------------------------------------------------
# CA-Importanleitung als signiertes PDF
# ---------------------------------------------------------------------------

@login_required
def ca_anleitung_pdf(request):
    """Gibt die Root-CA-Importanleitung fuer IT-Admins als signiertes PDF zurueck."""
    if not request.user.is_staff:
        messages.error(request, "Nur fuer Administratoren.")
        return redirect("signatur:dashboard")

    from django.template.loader import render_to_string
    from weasyprint import HTML
    from .services import signiere_pdf
    from .models import RootCA

    root_ca = RootCA.objects.first()

    html_string = render_to_string("signatur/ca_anleitung_pdf.html", {
        "root_ca": root_ca,
        "request": request,
    })
    pdf_bytes = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    try:
        pdf_bytes = signiere_pdf(
            pdf_bytes,
            request.user,
            dokument_name="CA-Importanleitung Gruppenrichtlinie",
            sichtbar=True,
        )
    except Exception as exc:
        logger.warning(
            "CA-Anleitung ohne Signatur (kein Zertifikat fuer %s): %s",
            request.user.username, exc,
        )

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="CA_Importanleitung.pdf"'
    return response


# ---------------------------------------------------------------------------
# Root-CA-Zertifikat als .cer herunterladen (fuer GPO-Import)
# ---------------------------------------------------------------------------

@login_required
def ca_zertifikat_download(request):
    """Root-CA-Zertifikat als DER-Datei (.cer) fuer Windows GPO-Import."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from .models import RootCA
    from cryptography.x509 import load_pem_x509_certificate
    from cryptography.hazmat.primitives.serialization import Encoding

    root_ca = RootCA.objects.first()
    if not root_ca:
        from django.http import Http404
        raise Http404("Keine Root-CA konfiguriert.")

    cert = load_pem_x509_certificate(root_ca.zertifikat_pem.encode())
    der_bytes = cert.public_bytes(Encoding.DER)

    response = HttpResponse(der_bytes, content_type="application/x-x509-ca-cert")
    response["Content-Disposition"] = 'attachment; filename="ca_root.cer"'
    return response
