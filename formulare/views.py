import uuid
from datetime import date as date_type, timedelta
from itertools import chain
from operator import attrgetter

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from arbeitszeit.models import (
    Arbeitszeitvereinbarung,
    Tagesarbeitszeit,
    Zeiterfassung,
    get_feiertagskalender,
)
from formulare.forms import AenderungZeiterfassungForm
from formulare.models import AenderungZeiterfassung, ZAGAntrag, ZAGStorno

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
    Zeigt sowohl AenderungZeiterfassung- als auch ZAGAntrag-Eintraege.
    """
    # Automatische Loeschung abgelaufener Eintraege (alle Nutzer, datenschutzkonform)
    loeschgrenze = _loeschgrenze_berechnen()
    AenderungZeiterfassung.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    ZAGAntrag.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()
    ZAGStorno.objects.filter(
        erstellt_am__date__lt=loeschgrenze
    ).delete()

    # Beide Antragstypen zusammenfuehren und nach Datum sortieren
    aenderungen = list(
        AenderungZeiterfassung.objects.filter(
            antragsteller__user=request.user
        )
    )
    for a in aenderungen:
        a.antrag_typ = "aenderung"

    zag_antraege = list(
        ZAGAntrag.objects.filter(
            antragsteller__user=request.user
        )
    )
    for z in zag_antraege:
        z.antrag_typ = "zag"

    zag_stornos = list(
        ZAGStorno.objects.filter(
            antragsteller__user=request.user
        )
    )
    for s in zag_stornos:
        s.antrag_typ = "zag_storno"

    alle_antraege = sorted(
        chain(aenderungen, zag_antraege, zag_stornos),
        key=attrgetter("erstellt_am"),
        reverse=True,
    )

    paginator = Paginator(alle_antraege, 10)
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


# ---------------------------------------------------------------------------
# Z-AG Antrag
# ---------------------------------------------------------------------------

def _soll_minuten_fuer_datum(mitarbeiter, datum):
    """Berechnet Soll-Minuten aus Vereinbarung fuer ein Datum.

    Gibt None zurueck wenn keine Vereinbarung vorhanden.
    """
    if datum.weekday() >= 5:
        # Wochenenden haben keine Soll-Zeit
        return 0

    vereinbarung = _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum)
    if not vereinbarung:
        return None

    wochentag_name = WOCHENTAG_MAP[datum.weekday()]

    if vereinbarung.arbeitszeit_typ == "individuell":
        tage = Tagesarbeitszeit.objects.filter(
            vereinbarung=vereinbarung,
            wochentag=wochentag_name,
        )
        if tage.exists():
            gesamt = sum(t.zeit_in_minuten for t in tage)
            return int(round(gesamt / tage.count()))
        return 0

    if vereinbarung.wochenstunden:
        return int(round(float(vereinbarung.wochenstunden) / 5 * 60))
    return None


def _erstelle_zag_eintraege(mitarbeiter, datum_von, datum_bis, bemerkung):
    """Erstellt Zeiterfassungs-Eintraege fuer einen Z-AG-Zeitraum.

    Wochenenden und Feiertage (standortabhaengig) werden uebersprungen.
    Gibt die Anzahl erstellter Eintraege zurueck.
    """
    cal = get_feiertagskalender(mitarbeiter.standort)
    aktuell = datum_von
    anzahl = 0
    while aktuell <= datum_bis:
        # Nur Werktage (Mo-Fr) und keine Feiertage
        if aktuell.weekday() < 5 and not cal.is_holiday(aktuell):
            soll_minuten = _soll_minuten_fuer_datum(mitarbeiter, aktuell)
            Zeiterfassung.objects.update_or_create(
                mitarbeiter=mitarbeiter,
                datum=aktuell,
                defaults={
                    "art": "z_ag",
                    "arbeitsbeginn": None,
                    "arbeitsende": None,
                    "pause_minuten": 0,
                    "arbeitszeit_minuten": 0,
                    "soll_minuten": soll_minuten,
                    "bemerkung": bemerkung,
                },
            )
            anzahl += 1
        aktuell += timedelta(days=1)
    return anzahl


@login_required
def zag_antrag(request):
    """Formular fuer Z-AG Antrag mit mehreren Datumsbereichen."""
    if request.method == "POST":
        # Zeilen aus POST sammeln
        von_datums = request.POST.getlist("zag_von_datum")
        bis_datums = request.POST.getlist("zag_bis_datum")

        zag_daten = []
        fehler = []

        for i in range(len(von_datums)):
            von_str = von_datums[i] if i < len(von_datums) else ""
            bis_str = bis_datums[i] if i < len(bis_datums) else ""

            if not von_str and not bis_str:
                # Leere Zeile ueberspringen
                continue

            if not von_str or not bis_str:
                fehler.append(
                    f"Zeile {i + 1}: Bitte beide Datumsfelder ausfullen."
                )
                continue

            try:
                von = date_type.fromisoformat(von_str)
                bis = date_type.fromisoformat(bis_str)
            except ValueError:
                fehler.append(f"Zeile {i + 1}: Ungultiges Datum.")
                continue

            if bis < von:
                fehler.append(
                    f"Zeile {i + 1}: Bis-Datum darf nicht vor Von-Datum liegen."
                )
                continue

            zag_daten.append({"von_datum": von_str, "bis_datum": bis_str})

        if not zag_daten and not fehler:
            fehler.append("Bitte mindestens eine Zeile ausfullen.")

        # Pflichtfelder Vertretung
        vertretung_name = request.POST.get("vertretung_name", "").strip()
        vertretung_telefon = request.POST.get("vertretung_telefon", "").strip()
        if not vertretung_name:
            fehler.append("Bitte die Vertretung (Name) angeben.")
        if not vertretung_telefon:
            fehler.append("Bitte die Telefonnummer der Vertretung angeben.")

        if fehler:
            # Zeilen mit row_id fuer Tage-Zaehler wiederherstellen
            zag_raws = [
                {
                    "von": von_datums[i] if i < len(von_datums) else "",
                    "bis": bis_datums[i] if i < len(bis_datums) else "",
                    "row_id": uuid.uuid4().hex[:8],
                }
                for i in range(max(len(von_datums), len(bis_datums)))
            ]
            fehler_kontext = {
                "fehler": fehler,
                "zag_raws": zag_raws,
                "vertretung_name": vertretung_name,
                "vertretung_telefon": vertretung_telefon,
            }
            if hasattr(request.user, "mitarbeiter"):
                fehler_kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
            return render(request, "formulare/zag_antrag.html", fehler_kontext)

        # Antrag speichern
        mitarbeiter = request.user.mitarbeiter
        antrag = ZAGAntrag.objects.create(
            antragsteller=mitarbeiter,
            zag_daten=zag_daten,
            vertretung_name=request.POST.get("vertretung_name", "").strip(),
            vertretung_telefon=request.POST.get("vertretung_telefon", "").strip(),
        )

        # Sofort Zeiterfassungs-Eintraege anlegen
        gesamt_tage = 0
        for zeile in zag_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            gesamt_tage += _erstelle_zag_eintraege(mitarbeiter, von, bis, "")

        return redirect("formulare:zag_erfolg", pk=antrag.pk)

    # Optionales Vorbefuellen des Von-Datums aus Query-Parameter
    first_von = request.GET.get("von", "")

    kontext = {
        "first_row_id": uuid.uuid4().hex[:8],
        "first_von": first_von,
    }
    if hasattr(request.user, "mitarbeiter"):
        kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
    return render(request, "formulare/zag_antrag.html", kontext)


@login_required
def zag_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen eines Z-AG-Antrags.

    Zeigt Betreffzeile mit Kopierfunktion, Datumsbereich(e) und PDF-Download.
    """
    antrag = get_object_or_404(
        ZAGAntrag,
        pk=pk,
        antragsteller__user=request.user,
    )
    kontext = {
        "antrag": antrag,
        "betreff": antrag.get_betreff(),
    }
    kontext.update(_zag_jahres_kontext(antrag.antragsteller))
    return render(request, "formulare/zag_erfolg.html", kontext)


@login_required
def zag_pdf(request, pk):
    """Gibt den Z-AG-Antrag als PDF-Download zurueck."""
    from weasyprint import HTML

    antrag = get_object_or_404(
        ZAGAntrag,
        pk=pk,
        antragsteller__user=request.user,
    )

    # Arbeitstage pro Zeitraum berechnen
    mitarbeiter = antrag.antragsteller
    zag_daten_mit_tagen = []
    gesamt_tage = 0
    for zeile in (antrag.zag_daten or []):
        try:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            tage = _zaehle_zag_tage(mitarbeiter, von, bis)
        except (KeyError, ValueError, TypeError):
            von = None
            bis = None
            tage = None
        zag_daten_mit_tagen.append({
            "von_datum": von,
            "bis_datum": bis,
            "tage": tage,
        })
        if tage:
            gesamt_tage += tage

    html_string = render_to_string(
        "formulare/pdf/zag_pdf.html",
        {
            "antrag": antrag,
            "betreff": antrag.get_betreff(),
            "zag_daten_mit_tagen": zag_daten_mit_tagen,
            "gesamt_tage": gesamt_tage,
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()

    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response


def _zag_jahres_kontext(mitarbeiter):
    """Berechnet Z-AG-Tage des laufenden Jahres fuer den Kontext."""
    jahr = date_type.today().year
    z_ag_tage_jahr = Zeiterfassung.objects.filter(
        mitarbeiter=mitarbeiter,
        datum__year=jahr,
        art="z_ag",
    ).count()
    return {"z_ag_tage_jahr": z_ag_tage_jahr, "z_ag_jahr": jahr}


def _zaehle_zag_tage(mitarbeiter, datum_von, datum_bis):
    """Zaehlt Arbeitstage im Zeitraum exklusive Wochenenden, Feiertage
    und (bei individueller Vereinbarung) vertragsfreier Wochentage.
    """
    cal = get_feiertagskalender(mitarbeiter.standort)

    # Vereinbarung zum Startdatum (wird fuer gesamten Zeitraum genutzt)
    vereinbarung = _vereinbarung_fuer_mitarbeiter(mitarbeiter, datum_von)

    # Freie Wochentage aus individueller Vereinbarung ermitteln
    freie_wochentage = set()
    if vereinbarung and vereinbarung.arbeitszeit_typ == "individuell":
        for wt_num in range(5):  # Mo-Fr
            wt_name = WOCHENTAG_MAP[wt_num]
            tage_vb = Tagesarbeitszeit.objects.filter(
                vereinbarung=vereinbarung,
                wochentag=wt_name,
            )
            if not tage_vb.exists() or all(t.zeitwert == 0 for t in tage_vb):
                freie_wochentage.add(wt_num)

    aktuell = datum_von
    anzahl = 0
    while aktuell <= datum_bis:
        if (
            aktuell.weekday() < 5
            and not cal.is_holiday(aktuell)
            and aktuell.weekday() not in freie_wochentage
        ):
            anzahl += 1
        aktuell += timedelta(days=1)
    return anzahl


@login_required
def zag_tage_zaehlen(request):
    """HTMX-View - berechnet Arbeitstage fuer einen Z-AG-Zeitraum.

    Beruecksichtigt Wochenenden, standortabhaengige Feiertage und
    freie Wochentage aus individueller Arbeitszeitvereinbarung.
    """
    # HTMX-View - gibt nur Partial zurueck
    von_str = request.GET.get("zag_von_datum", "")
    bis_str = request.GET.get("zag_bis_datum", "")
    tage_anzahl = None

    if von_str and bis_str and hasattr(request.user, "mitarbeiter"):
        try:
            von = date_type.fromisoformat(von_str)
            bis = date_type.fromisoformat(bis_str)
            if bis >= von:
                tage_anzahl = _zaehle_zag_tage(
                    request.user.mitarbeiter, von, bis
                )
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_zag_tage.html",
        {"tage_anzahl": tage_anzahl},
    )


@login_required
def neue_zag_zeile(request):
    """HTMX-View - gibt eine neue leere Z-AG-Zeile als Partial zurueck.

    Wird per HTMX aufgerufen wenn der Nutzer auf '+' klickt.
    """
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_zag_zeile.html",
        {"row_id": row_id},
    )


# ---------------------------------------------------------------------------
# Z-AG Storno
# ---------------------------------------------------------------------------

def _storniere_zag_eintraege(mitarbeiter, datum_von, datum_bis):
    """Loescht Z-AG-Zeiterfassungs-Eintraege im Zeitraum.

    Gibt die Anzahl tatsaechlich geloeschter Eintraege zurueck.
    """
    deleted, _ = Zeiterfassung.objects.filter(
        mitarbeiter=mitarbeiter,
        art="z_ag",
        datum__gte=datum_von,
        datum__lte=datum_bis,
    ).delete()
    return deleted


@login_required
def zag_storno_tage_zaehlen(request):
    """HTMX-View - zeigt vorhandene Z-AG-Tage im gewaehlten Zeitraum.

    Berechnet wie viele Zeiterfassungs-Eintraege mit art='z_ag'
    tatsaechlich vorhanden sind und storniert wuerden.
    """
    # HTMX-View - gibt nur Partial zurueck
    von_str = request.GET.get("storno_von_datum", "")
    bis_str = request.GET.get("storno_bis_datum", "")
    tage_anzahl = None

    if von_str and bis_str and hasattr(request.user, "mitarbeiter"):
        try:
            von = date_type.fromisoformat(von_str)
            bis = date_type.fromisoformat(bis_str)
            if bis >= von:
                tage_anzahl = Zeiterfassung.objects.filter(
                    mitarbeiter=request.user.mitarbeiter,
                    art="z_ag",
                    datum__gte=von,
                    datum__lte=bis,
                ).count()
        except (ValueError, AttributeError):
            pass

    return render(
        request,
        "formulare/partials/_zag_storno_tage.html",
        {"tage_anzahl": tage_anzahl},
    )


@login_required
def neue_zag_storno_zeile(request):
    """HTMX-View - gibt eine neue leere Storno-Zeile als Partial zurueck."""
    # HTMX-View - gibt nur Partial zurueck
    row_id = uuid.uuid4().hex[:8]
    return render(
        request,
        "formulare/partials/_zag_storno_zeile.html",
        {"row_id": row_id},
    )


@login_required
def zag_storno(request):
    """Formular fuer Z-AG Stornierung mit mehreren Datumsbereichen."""
    if request.method == "POST":
        von_datums = request.POST.getlist("storno_von_datum")
        bis_datums = request.POST.getlist("storno_bis_datum")

        storno_daten = []
        fehler = []

        for i in range(len(von_datums)):
            von_str = von_datums[i] if i < len(von_datums) else ""
            bis_str = bis_datums[i] if i < len(bis_datums) else ""

            if not von_str and not bis_str:
                continue

            if not von_str or not bis_str:
                fehler.append(
                    f"Zeile {i + 1}: Bitte beide Datumsfelder ausfullen."
                )
                continue

            try:
                von = date_type.fromisoformat(von_str)
                bis = date_type.fromisoformat(bis_str)
            except ValueError:
                fehler.append(f"Zeile {i + 1}: Ungultiges Datum.")
                continue

            if bis < von:
                fehler.append(
                    f"Zeile {i + 1}: Bis-Datum darf nicht vor Von-Datum liegen."
                )
                continue

            storno_daten.append({"von_datum": von_str, "bis_datum": bis_str})

        if not storno_daten and not fehler:
            fehler.append("Bitte mindestens eine Zeile ausfullen.")

        if fehler:
            storno_raws = [
                {
                    "von": von_datums[i] if i < len(von_datums) else "",
                    "bis": bis_datums[i] if i < len(bis_datums) else "",
                    "row_id": uuid.uuid4().hex[:8],
                }
                for i in range(max(len(von_datums), len(bis_datums)))
            ]
            fehler_kontext = {
                "fehler": fehler,
                "storno_raws": storno_raws,
            }
            if hasattr(request.user, "mitarbeiter"):
                fehler_kontext.update(_zag_jahres_kontext(request.user.mitarbeiter))
            return render(request, "formulare/zag_storno.html", fehler_kontext)

        # Storno-Antrag speichern
        mitarbeiter = request.user.mitarbeiter
        antrag = ZAGStorno.objects.create(
            antragsteller=mitarbeiter,
            storno_daten=storno_daten,
        )

        # Sofort Zeiterfassungs-Eintraege loeschen
        for zeile in storno_daten:
            von = date_type.fromisoformat(zeile["von_datum"])
            bis = date_type.fromisoformat(zeile["bis_datum"])
            _storniere_zag_eintraege(mitarbeiter, von, bis)

        return redirect("formulare:zag_storno_erfolg", pk=antrag.pk)

    kontext = {"first_row_id": uuid.uuid4().hex[:8]}
    if hasattr(request.user, "mitarbeiter"):
        mitarbeiter = request.user.mitarbeiter
        kontext.update(_zag_jahres_kontext(mitarbeiter))
        # Zukuenftige Z-AG-Eintraege des laufenden Jahres zur Orientierung
        heute = date_type.today()
        kontext["zag_zukunft"] = (
            Zeiterfassung.objects
            .filter(
                mitarbeiter=mitarbeiter,
                art="z_ag",
                datum__gte=heute,
                datum__year=heute.year,
            )
            .order_by("datum")
        )
    return render(request, "formulare/zag_storno.html", kontext)


@login_required
def zag_storno_erfolg(request, pk):
    """Erfolgsseite nach dem Einreichen einer Z-AG Stornierung."""
    antrag = get_object_or_404(
        ZAGStorno,
        pk=pk,
        antragsteller__user=request.user,
    )
    kontext = {
        "antrag": antrag,
        "betreff": antrag.get_betreff(),
    }
    kontext.update(_zag_jahres_kontext(antrag.antragsteller))
    return render(request, "formulare/zag_storno_erfolg.html", kontext)


@login_required
def zag_storno_pdf(request, pk):
    """Gibt die Z-AG Stornierung als PDF-Download zurueck."""
    from weasyprint import HTML

    antrag = get_object_or_404(
        ZAGStorno,
        pk=pk,
        antragsteller__user=request.user,
    )
    html_string = render_to_string(
        "formulare/pdf/zag_storno_pdf.html",
        {
            "antrag": antrag,
            "betreff": antrag.get_betreff(),
        },
        request=request,
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri(),
    ).write_pdf()

    dateiname = antrag.get_betreff().replace(" ", "_") + ".pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response
