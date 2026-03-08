import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Loeschprotokoll

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """DSGVO-Uebersicht: Zertifikat, Auskunftsrecht, Loeschprotokolle (nur Staff)."""
    from arbeitszeit.models import Mitarbeiter

    mitarbeiter = None
    try:
        mitarbeiter = request.user.mitarbeiter
    except Exception:
        pass

    protokolle = None
    if request.user.is_staff:
        protokolle = Loeschprotokoll.objects.all()[:50]

    return render(request, "datenschutz/dashboard.html", {
        "mitarbeiter": mitarbeiter,
        "protokolle": protokolle,
    })


@login_required
def auskunft_pdf(request):
    """DSGVO Art. 15 – Selbstauskunft: alle ueber den User gespeicherten Daten als PDF."""
    from weasyprint import HTML
    from django.template.loader import render_to_string

    user = request.user
    kontext = _sammle_auskunftsdaten(user)
    kontext["auskunft_datum"] = timezone.now()

    html_str = render_to_string("datenschutz/auskunft_pdf.html", kontext)
    pdf = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()

    dateiname = f"DSGVO_Auskunft_{user.username}_{timezone.now().date()}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response


@login_required
def loeschprotokoll_detail(request, pk):
    """Detail-Ansicht eines Loeschprotokolls (nur Staff)."""
    if not request.user.is_staff:
        messages.error(request, "Nur fuer Administratoren.")
        return render(request, "datenschutz/dashboard.html", {})

    protokoll = get_object_or_404(Loeschprotokoll, pk=pk)
    return render(request, "datenschutz/loeschprotokoll_detail.html", {
        "protokoll": protokoll,
    })


@login_required
def loeschprotokoll_pdf_download(request, pk):
    """Gespeichertes Loeschprotokoll-PDF herunterladen (nur Staff)."""
    if not request.user.is_staff:
        messages.error(request, "Nur fuer Administratoren.")
        return HttpResponse(status=403)

    protokoll = get_object_or_404(Loeschprotokoll, pk=pk)
    if not protokoll.protokoll_pdf:
        messages.error(request, "Kein PDF gespeichert.")
        return HttpResponse(status=404)

    response = HttpResponse(bytes(protokoll.protokoll_pdf), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="Loeschprotokoll_{protokoll.pk}_{protokoll.personalnummer}.pdf"'
    )
    return response


# ---------------------------------------------------------------------------
# Datensammlung fuer Auskunft
# ---------------------------------------------------------------------------

def _sammle_auskunftsdaten(user):
    """Sammelt alle personenbezogenen Daten eines Users fuer die DSGVO-Auskunft."""
    daten = {"user": user, "kategorien": []}

    # Stammdaten
    try:
        ma = user.mitarbeiter
        daten["mitarbeiter"] = ma
        daten["kategorien"].append({
            "titel": "Stammdaten",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
            "speicherfrist": "10 Jahre nach Austritt (§ 147 AO)",
            "felder": [
                ("Vorname", ma.vorname),
                ("Nachname", ma.nachname),
                ("Personalnummer", ma.personalnummer),
                ("Abteilung", ma.abteilung),
                ("Eintrittsdatum", ma.eintrittsdatum),
                ("Austrittsdatum", ma.austritt_datum if hasattr(ma, "austritt_datum") else "–"),
                ("Rolle", ma.get_rolle_display()),
                ("Aktiv", "Ja" if ma.aktiv else "Nein"),
            ],
        })
    except Exception:
        pass

    # Zeiterfassung
    try:
        from arbeitszeit.models import Zeiterfassung
        ze = Zeiterfassung.objects.filter(mitarbeiter=user.mitarbeiter)
        daten["kategorien"].append({
            "titel": "Zeiterfassung",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. c DSGVO (rechtliche Verpflichtung)",
            "speicherfrist": "10 Jahre nach Austritt (§ 147 AO)",
            "anzahl": ze.count(),
            "zeitraum": _zeitraum(ze, "datum"),
        })
    except Exception:
        pass

    # Arbeitszeitvereinbarungen
    try:
        from arbeitszeit.models import Arbeitszeitvereinbarung
        av = Arbeitszeitvereinbarung.objects.filter(mitarbeiter=user.mitarbeiter)
        daten["kategorien"].append({
            "titel": "Arbeitszeitvereinbarungen",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
            "speicherfrist": "10 Jahre nach Austritt (§ 147 AO)",
            "anzahl": av.count(),
            "zeitraum": _zeitraum(av, "gueltig_ab"),
        })
    except Exception:
        pass

    # ZAG-Antraege
    try:
        from formulare.models import ZAGAntrag
        zag = ZAGAntrag.objects.filter(mitarbeiter=user.mitarbeiter)
        daten["kategorien"].append({
            "titel": "Z-AG-Antraege (Zusatzarbeit)",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
            "speicherfrist": "3 Jahre (§ 195 BGB)",
            "anzahl": zag.count(),
            "zeitraum": _zeitraum(zag, "erstellt_am"),
        })
    except Exception:
        pass

    # Zeitgutschriften
    try:
        from formulare.models import Zeitgutschrift
        zg = Zeitgutschrift.objects.filter(mitarbeiter=user.mitarbeiter)
        daten["kategorien"].append({
            "titel": "Zeitgutschriften",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
            "speicherfrist": "3 Jahre (§ 195 BGB)",
            "anzahl": zg.count(),
            "zeitraum": _zeitraum(zg, "erstellt_am"),
        })
    except Exception:
        pass

    # Dienstreisen
    try:
        from formulare.models import Dienstreiseantrag
        dr = Dienstreiseantrag.objects.filter(mitarbeiter=user.mitarbeiter)
        daten["kategorien"].append({
            "titel": "Dienstreiseantraege",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
            "speicherfrist": "10 Jahre nach Austritt (§ 147 AO, Reisekosten)",
            "anzahl": dr.count(),
            "zeitraum": _zeitraum(dr, "erstellt_am"),
        })
    except Exception:
        pass

    # Signatur-Zertifikate
    try:
        from signatur.models import MitarbeiterZertifikat, SignaturProtokoll
        zert = MitarbeiterZertifikat.objects.filter(user=user)
        prot = SignaturProtokoll.objects.filter(unterzeichner=user)
        daten["kategorien"].append({
            "titel": "Digitale Signaturen & Zertifikate",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. c DSGVO / eIDAS",
            "speicherfrist": "10 Jahre (eIDAS Art. 40)",
            "anzahl": zert.count() + prot.count(),
            "details": f"{zert.count()} Zertifikat(e), {prot.count()} Signatur-Protokoll(e)",
        })
    except Exception:
        pass

    # Raumbuchungen
    try:
        from raumbuch.models import Raumbuchung
        rb = Raumbuchung.objects.filter(gebucht_von=user)
        daten["kategorien"].append({
            "titel": "Raumbuchungen",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO",
            "speicherfrist": "2 Jahre (DSGVO Art. 5)",
            "anzahl": rb.count(),
            "zeitraum": _zeitraum(rb, "beginn"),
        })
    except Exception:
        pass

    # Workflow-Tasks
    try:
        from workflow.models import WorkflowTask
        wt = WorkflowTask.objects.filter(zugewiesen_an=user)
        daten["kategorien"].append({
            "titel": "Workflow-Aufgaben",
            "rechtsgrundlage": "Art. 6 Abs. 1 lit. b DSGVO",
            "speicherfrist": "3 Jahre (§ 195 BGB)",
            "anzahl": wt.count(),
        })
    except Exception:
        pass

    return daten


def _zeitraum(queryset, datumsfeld):
    """Gibt 'TT.MM.JJJJ – TT.MM.JJJJ' zurueck oder '–' bei leerer Menge."""
    from django.db.models import Min, Max
    agg = queryset.aggregate(von=Min(datumsfeld), bis=Max(datumsfeld))
    if not agg["von"]:
        return "–"
    von = agg["von"]
    bis = agg["bis"]
    # date oder datetime
    von_str = von.date().strftime("%d.%m.%Y") if hasattr(von, "date") else str(von)
    bis_str = bis.date().strftime("%d.%m.%Y") if hasattr(bis, "date") else str(bis)
    return f"{von_str} – {bis_str}"
