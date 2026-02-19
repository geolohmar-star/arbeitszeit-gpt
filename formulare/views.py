import uuid
from datetime import date as date_type, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from arbeitszeit.models import Arbeitszeitvereinbarung, Tagesarbeitszeit
from formulare.forms import AenderungZeiterfassungForm
from formulare.models import AenderungZeiterfassung

WOCHENTAG_MAP = {
    0: "montag",
    1: "dienstag",
    2: "mittwoch",
    3: "donnerstag",
    4: "freitag",
    5: "samstag",
    6: "sonntag",
}


@login_required
def dashboard(request):
    """Dashboard fuer die Formulare-App.

    Zeigt eine Uebersicht aller verfuegbaren Antragsformulare.
    """
    context = {}

    # HTMX-Request: nur Partial zurueckgeben
    if request.headers.get("HX-Request"):
        return render(
            request,
            "formulare/partials/_dashboard.html",
            context,
        )

    return render(request, "formulare/dashboard.html", context)


def _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum):
    """Gibt die aktive Arbeitszeitvereinbarung zum Datum zurueck oder None."""
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


@login_required
def meine_antraege(request):
    """Liste aller eigenen Antraege, neueste zuerst, mit Paginierung.

    Loescht automatisch Eintraege die aelter als 2 Jahre minus 1 Tag sind.
    """
    # Automatische Loeschung abgelaufener Eintraege (alle Nutzer, datenschutzkonform)
    loeschgrenze = _loeschgrenze_berechnen()
    AenderungZeiterfassung.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()

    antraege = AenderungZeiterfassung.objects.filter(
        antragsteller__user=request.user
    ).order_by("-erstellt_am")

    paginator = Paginator(antraege, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "formulare/meine_antraege.html",
        {
            "page_obj": page_obj,
            "loeschgrenze": loeschgrenze,
        },
    )


@login_required
def aenderung_zeiterfassung(request):
    """Formular fuer manuelle Aenderungen der Zeiterfassung."""
    form = AenderungZeiterfassungForm(request.POST or None)

    # Tagestausch nur bei individueller Vereinbarung erlaubt
    tausch_erlaubt = False
    if hasattr(request.user, "mitarbeiter"):
        vereinbarung = _vereinbarung_fuer_mitarbeiter(
            request.user.mitarbeiter,
            date_type.today(),
        )
        tausch_erlaubt = bool(
            vereinbarung
            and vereinbarung.arbeitszeit_typ == "individuell"
        )

    if request.method == "POST":
        if form.is_valid():
            antrag = form.save(commit=False)
            antrag.antragsteller = request.user.mitarbeiter

            # Zeitzeilen-Array-Daten aus POST sammeln und als JSON speichern
            tages_datums = request.POST.getlist("tages_datum")
            kommen_zeits = request.POST.getlist("kommen_zeit")
            pause_gehen_zeits = request.POST.getlist("pause_gehen_zeit")
            pause_kommen_zeits = request.POST.getlist("pause_kommen_zeit")
            gehen_zeits = request.POST.getlist("gehen_zeit")
            zeiten_daten = []
            for i in range(len(tages_datums)):
                zeile = {
                    "datum": tages_datums[i] if i < len(tages_datums) else "",
                    "kommen": kommen_zeits[i] if i < len(kommen_zeits) else "",
                    "pause_gehen": pause_gehen_zeits[i] if i < len(pause_gehen_zeits) else "",
                    "pause_kommen": pause_kommen_zeits[i] if i < len(pause_kommen_zeits) else "",
                    "gehen": gehen_zeits[i] if i < len(gehen_zeits) else "",
                }
                if any(zeile.values()):
                    zeiten_daten.append(zeile)
            antrag.zeiten_daten = zeiten_daten or None

            # Tauschzeilen-Array-Daten aus POST sammeln und als JSON speichern
            von_datums = request.POST.getlist("tausch_von_datum")
            zu_datums = request.POST.getlist("tausch_zu_datum")
            tausch_daten = []
            for i in range(len(von_datums)):
                zeile = {
                    "von_datum": von_datums[i] if i < len(von_datums) else "",
                    "zu_datum": zu_datums[i] if i < len(zu_datums) else "",
                }
                if any(zeile.values()):
                    tausch_daten.append(zeile)
            antrag.tausch_daten = tausch_daten or None

            antrag.save()
            return redirect("formulare:aenderung_erfolg", pk=antrag.pk)

        # HTMX-POST mit Fehler: Formular-Partial zurueckgeben
        if request.headers.get("HX-Request"):
            art = request.POST.get("art", "")
            return render(
                request,
                "formulare/partials/_aenderung_felder.html",
                {"form": form, "art": art},
            )

    return render(
        request,
        "formulare/aenderung_zeiterfassung.html",
        {"form": form, "tausch_erlaubt": tausch_erlaubt},
    )


@login_required
def aenderung_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen eines Aenderungsantrags.

    Zeigt Betreffzeile mit Kopierfunktion, Antragsdetails und PDF-Download.
    """
    antrag = get_object_or_404(
        AenderungZeiterfassung,
        pk=pk,
        antragsteller__user=request.user,
    )
    vereinbarung = _vereinbarung_fuer_mitarbeiter(
        antrag.antragsteller,
        antrag.erstellt_am.date(),
    )

    # Fuer jeden Tausch-Eintrag die Sollzeit des Von-Datums aufschlagen
    tausch_mit_soll = []
    if antrag.tausch_daten:
        for zeile in antrag.tausch_daten:
            von_datum_str = zeile.get("von_datum", "")
            soll_text = ""
            if von_datum_str:
                try:
                    von_datum = date_type.fromisoformat(von_datum_str)
                    vb = _vereinbarung_fuer_mitarbeiter(
                        antrag.antragsteller, von_datum
                    )
                    if vb:
                        taz = (
                            Tagesarbeitszeit.objects
                            .filter(
                                vereinbarung=vb,
                                wochentag=WOCHENTAG_MAP[von_datum.weekday()],
                            )
                            .order_by("woche")
                            .first()
                        )
                        if taz:
                            soll_text = taz.formatierte_zeit()
                except (ValueError, AttributeError):
                    pass
            tausch_mit_soll.append({
                "von_datum": von_datum_str,
                "zu_datum": zeile.get("zu_datum", ""),
                "soll": soll_text,
            })

    return render(
        request,
        "formulare/aenderung_erfolg.html",
        {
            "antrag": antrag,
            "vereinbarung": vereinbarung,
            "betreff": antrag.get_betreff(),
            "tausch_mit_soll": tausch_mit_soll,
        },
    )


@login_required
def aenderung_pdf(request, pk):
    """Gibt den Aenderungsantrag als PDF-Download zurueck."""
    from weasyprint import HTML

    antrag = get_object_or_404(
        AenderungZeiterfassung,
        pk=pk,
        antragsteller__user=request.user,
    )
    vereinbarung = _vereinbarung_fuer_mitarbeiter(
        antrag.antragsteller,
        antrag.erstellt_am.date(),
    )

    html_string = render_to_string(
        "formulare/pdf/aenderung_zeiterfassung_pdf.html",
        {
            "antrag": antrag,
            "vereinbarung": vereinbarung,
            "betreff": antrag.get_betreff(),
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()

    # Dateiname wie Betreffzeile, Leerzeichen durch Unterstrich ersetzen
    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response


@login_required
def soll_fuer_datum(request):
    """HTMX-View - gibt Soll-Arbeitszeit fuer das gewaehlte Datum zurueck.

    Liest die aktive individuelle Vereinbarung des Mitarbeiters aus und
    zeigt die Sollzeit fuer den Wochentag des gewaehlten Datums.
    """
    # HTMX-View - gibt nur Partial zurueck
    datum_str = request.GET.get("tausch_von_datum", "")
    soll_text = ""

    if datum_str and hasattr(request.user, "mitarbeiter"):
        try:
            datum = date_type.fromisoformat(datum_str)
            wochentag = WOCHENTAG_MAP[datum.weekday()]

            vereinbarung = _vereinbarung_fuer_mitarbeiter(
                request.user.mitarbeiter, datum
            )

            if vereinbarung:
                taz = (
                    Tagesarbeitszeit.objects
                    .filter(
                        vereinbarung=vereinbarung,
                        wochentag=wochentag,
                    )
                    .order_by("woche")
                    .first()
                )
                if taz:
                    soll_text = taz.formatierte_zeit()

        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_soll_anzeige.html",
        {"soll_text": soll_text},
    )


@login_required
def neue_tauschzeile(request):
    """HTMX-View - gibt eine neue leere Tauschzeile als Partial zurueck.

    Jede Zeile bekommt eine eindeutige row_id fuer die HTMX-Kollisionsmeldung.
    """
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_tauschzeile.html",
        {"row_id": row_id},
    )


@login_required
def tausch_validierung(request):
    """HTMX-View - prueft ob der neue Tag laut Vereinbarung frei ist.

    Gibt eine Kollisionsmeldung zurueck wenn der neue Tag ein Arbeitstag ist.
    """
    # HTMX-View - gibt nur Partial zurueck
    datum_str = request.GET.get("tausch_zu_datum", "")
    row_id = request.GET.get("row_id", "")
    kollision = False
    datum_gueltig = False

    if datum_str and hasattr(request.user, "mitarbeiter"):
        try:
            datum = date_type.fromisoformat(datum_str)
            wochentag = WOCHENTAG_MAP[datum.weekday()]

            # Aktive Vereinbarung des Mitarbeiters zum gewaehlten Datum suchen
            vereinbarung = (
                Arbeitszeitvereinbarung.objects
                .filter(
                    mitarbeiter=request.user.mitarbeiter,
                    gueltig_ab__lte=datum,
                )
                .order_by("-gueltig_ab")
                .first()
            )

            if vereinbarung:
                taz = (
                    Tagesarbeitszeit.objects
                    .filter(
                        vereinbarung=vereinbarung,
                        wochentag=wochentag,
                    )
                    .first()
                )
                # Zeitwert > 0 bedeutet Arbeitstag -> Kollision
                if taz and taz.zeitwert > 0:
                    kollision = True
                else:
                    datum_gueltig = True

        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_tausch_kollision.html",
        {
            "kollision": kollision,
            "datum_gueltig": datum_gueltig,
            "row_id": row_id,
        },
    )


@login_required
def samstag_felder(request):
    """HTMX-View - gibt Samstags-Unterfelder basierend auf gewaehlter Art zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer eine Samstags-Option auswaehlt.
    """
    # HTMX-View - gibt nur Partial zurueck
    samstag_art = request.GET.get("samstag_art", "")
    form = AenderungZeiterfassungForm()
    return render(
        request,
        "formulare/partials/_samstag_felder.html",
        {"form": form, "samstag_art": samstag_art},
    )


@login_required
def neue_zeitzeile(request):
    """HTMX-View - gibt eine neue leere Zeitzeile als Partial zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer auf '+' klickt.
    """
    # HTMX-View - gibt nur Partial zurueck
    return render(request, "formulare/partials/_zeitzeile.html")


@login_required
def aenderung_felder(request):
    """HTMX-View - gibt Felder-Partial basierend auf gewaehlter Art zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer eine Art-Option auswaehlt.
    """
    # HTMX-View - gibt nur Partial zurueck
    art = request.GET.get("art", "")
    form = AenderungZeiterfassungForm()
    return render(
        request,
        "formulare/partials/_aenderung_felder.html",
        {"form": form, "art": art},
    )
