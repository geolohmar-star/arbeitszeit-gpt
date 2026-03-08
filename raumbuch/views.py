import logging
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from config.kommunikation_utils import jitsi_link_generieren, matrix_raum_link

from .models import (
    Belegung,
    Bereich,
    Besuchsanmeldung,
    Gebaeude,
    Geschoss,
    Glasfaserverbindung,
    NetzwerkKomponente,
    RaumbuchLog,
    Raumbuchung,
    RaumArbeitsschutzDaten,
    RaumElektroDaten,
    RaumFacilityDaten,
    RaumInstallationDaten,
    RaumNetzwerkDaten,
    Raum,
    Reinigungsplan,
    ReinigungsQuittung,
    Schluessel,
    SchluesselAusgabe,
    Standort,
    Treppenhaus,
    Umzugsauftrag,
    ZutrittsProfil,
    ZutrittsToken,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interaktiver Gebaeudegrundriss
# ---------------------------------------------------------------------------

@login_required
def gebaeude_grundriss(request):
    """Interaktiver SVG-Grundriss mit Statusanzeigen."""
    import json

    # Navigationsstruktur fuer Sidebar
    struktur = []
    for gb in Gebaeude.objects.prefetch_related("geschosse").order_by("pk"):
        geschosse = []
        for gs in gb.geschosse.all().order_by("reihenfolge"):
            geschosse.append({
                "id": gs.pk,
                "bezeichnung": gs.bezeichnung,
                "kuerzel": gs.kuerzel,
            })
        struktur.append({
            "bezeichnung": gb.bezeichnung,
            "kuerzel": gb.kuerzel,
            "geschosse": geschosse,
        })

    # Ausgewaehltes Geschoss
    geschoss_id = request.GET.get("geschoss")
    geschoss = None
    raeume_data = []

    if geschoss_id:
        geschoss = get_object_or_404(Geschoss, pk=geschoss_id)
        raeume = Raum.objects.filter(
            geschoss=geschoss, ist_aktiv=True
        ).order_by("raumnummer")

        belegungen = {
            b.raum_id: b.mitarbeiter
            for b in Belegung.objects.filter(
                raum__in=raeume, bis__isnull=True
            ).select_related("mitarbeiter")
        }

        netzwerk = {
            n.raum_id: n
            for n in RaumNetzwerkDaten.objects.filter(raum__in=raeume)
        }

        for raum in raeume:
            ma = belegungen.get(raum.pk)
            nw = netzwerk.get(raum.pk)
            raeume_data.append({
                "id": raum.pk,
                "nummer": raum.raumnummer,
                "name": raum.raumname,
                "typ": raum.raumtyp,
                "flaeche": float(raum.flaeche_m2) if raum.flaeche_m2 else None,
                "kapazitaet": raum.kapazitaet,
                "belegt_von": str(ma) if ma else None,
                "hat_netzwerk": nw is not None,
                "hat_netzwerkplan": raum.raumtyp in {"serverraum", "it_verteiler", "druckerraum", "elektroverteilung"},
                "url": f"/raumbuch/raum/{raum.pk}/",
                "netzwerkplan_url": f"/raumbuch/raum/{raum.pk}/netzwerkplan/",
            })
    elif struktur and struktur[0]["geschosse"]:
        # Default: erstes Geschoss laden
        first_id = struktur[0]["geschosse"][0]["id"]
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(f"?geschoss={first_id}")

    return render(request, "raumbuch/gebaeude_grundriss.html", {
        "struktur_json": json.dumps(struktur, ensure_ascii=False),
        "raeume_json": json.dumps(raeume_data, ensure_ascii=False),
        "geschoss": geschoss,
        "geschoss_id": geschoss_id or "",
    })


@login_required
def gebaeude_status_api(request):
    """JSON-API: Buchungsstatus fuer alle Raeume eines Geschosses."""
    from django.http import JsonResponse

    geschoss_id = request.GET.get("geschoss")
    if not geschoss_id:
        return JsonResponse({"raeume": {}})

    jetzt = timezone.now()
    heute = timezone.localdate()

    raeume = Raum.objects.filter(geschoss_id=geschoss_id, ist_aktiv=True)

    buchungen_jetzt = set(
        Raumbuchung.objects.filter(
            raum__in=raeume,
            datum=heute,
            von__lte=jetzt.time(),
            bis__gte=jetzt.time(),
            status__in=["offen", "bestaetigt"],
        ).values_list("raum_id", flat=True)
    )

    naechste = {}
    for b in Raumbuchung.objects.filter(
        raum__in=raeume,
        datum=heute,
        von__gt=jetzt.time(),
        status__in=["offen", "bestaetigt"],
    ).order_by("von").select_related("buchender"):
        if b.raum_id not in naechste:
            name = b.buchender.get_full_name() or b.buchender.username if b.buchender else "?"
            naechste[b.raum_id] = f"{b.von.strftime('%H:%M')} {b.betreff or name}"

    result = {}
    for raum in raeume:
        result[str(raum.pk)] = {
            "buchung_aktiv": raum.pk in buchungen_jetzt,
            "naechste_buchung": naechste.get(raum.pk),
        }

    return JsonResponse({"raeume": result})


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _log(raum, aktion, beschreibung, user, model_name="", objekt_id=None):
    """Schreibt einen Eintrag in den Raumbuch-Audit-Trail."""
    RaumbuchLog.objects.create(
        raum=raum,
        aktion=aktion,
        beschreibung=beschreibung,
        geaendert_von=user,
        model_name=model_name,
        objekt_id=objekt_id,
    )


def _ist_facility_oder_staff(user):
    """True wenn der User Staff ist oder einem Facility-Team angehoert."""
    if user.is_staff:
        return True
    return user.facility_teams.exists()


def _ist_token_bearbeiter(user):
    """True fuer Staff, Facility-Team-Mitglieder und Security-Team-Mitglieder."""
    if user.is_staff or user.facility_teams.exists():
        return True
    from formulare.models import TeamQueue
    return TeamQueue.objects.filter(kuerzel="sec-token", mitglieder=user).exists()


# ---------------------------------------------------------------------------
# Gebaeudestruktur
# ---------------------------------------------------------------------------

@login_required
def gebaeude_struktur(request):
    """Accordion-Baum: Standort → Gebaeude → Geschoss → Raeume."""
    standorte = Standort.objects.prefetch_related(
        "gebaeude__geschosse__raeume"
    ).all()
    return render(
        request,
        "raumbuch/struktur.html",
        {"standorte": standorte},
    )


# ---------------------------------------------------------------------------
# Raum CRUD
# ---------------------------------------------------------------------------

@login_required
def raum_uebersicht(request):
    """Raumliste mit optionalen Filtern."""
    raeume = Raum.objects.select_related("geschoss__gebaeude__standort", "bereich").all()

    # Filter
    geschoss_id = request.GET.get("geschoss")
    raumtyp = request.GET.get("raumtyp")
    nutzung = request.GET.get("nutzung")
    leerstand = request.GET.get("leerstand")
    suche = request.GET.get("q", "").strip()

    if geschoss_id:
        raeume = raeume.filter(geschoss_id=geschoss_id)
    if raumtyp:
        raeume = raeume.filter(raumtyp=raumtyp)
    if nutzung:
        raeume = raeume.filter(nutzungsmodell=nutzung)
    if leerstand == "1":
        raeume = raeume.filter(ist_leer=True)
    if suche:
        raeume = raeume.filter(
            raumnummer__icontains=suche
        ) | raeume.filter(raumname__icontains=suche)

    from .models import RAUMTYP_CHOICES
    geschosse = Geschoss.objects.select_related("gebaeude").order_by(
        "gebaeude__kuerzel", "reihenfolge"
    )

    return render(
        request,
        "raumbuch/uebersicht.html",
        {
            "raeume": raeume,
            "geschosse": geschosse,
            "raumtyp_choices": RAUMTYP_CHOICES,
            "filter_geschoss": geschoss_id,
            "filter_raumtyp": raumtyp,
            "filter_nutzung": nutzung,
            "filter_leerstand": leerstand,
            "suche": suche,
        },
    )


@login_required
def raum_detail(request, pk):
    """Raum-Detail mit Bootstrap-Tabs fuer alle Datenschichten."""
    # select_related holt Datenschichten und Gebaeudestruktur in einem JOIN statt 6+ Queries
    raum = get_object_or_404(
        Raum.objects.select_related(
            "geschoss__gebaeude__standort",
            "bereich",
            "facility_daten",
            "elektro_daten",
            "netzwerk_daten",
            "installation_daten",
            "arbeitsschutz_daten",
        ),
        pk=pk,
    )

    # Datenschichten aus dem bereits geladenen Objekt lesen (kein weiterer DB-Hit)
    def _schicht(attr):
        try:
            return getattr(raum, attr)
        except Exception:
            return None

    facility_daten = _schicht("facility_daten")
    elektro_daten = _schicht("elektro_daten")
    netzwerk_daten = _schicht("netzwerk_daten")
    installation_daten = _schicht("installation_daten")
    arbeitsschutz_daten = _schicht("arbeitsschutz_daten")

    belegungen = Belegung.objects.filter(raum=raum).select_related("mitarbeiter")
    buchungen = Raumbuchung.objects.filter(raum=raum, datum__gte=date.today()).order_by("datum", "von")
    reinigungen = ReinigungsQuittung.objects.filter(raum=raum)[:10]
    schluessel = raum.schluessel.all()
    tokens = ZutrittsToken.objects.filter(
        profile__raeume=raum
    ).distinct().select_related("mitarbeiter")
    log_eintraege = RaumbuchLog.objects.filter(raum=raum)[:20]

    return render(
        request,
        "raumbuch/raum_detail.html",
        {
            "raum": raum,
            "facility_daten": facility_daten,
            "elektro_daten": elektro_daten,
            "netzwerk_daten": netzwerk_daten,
            "installation_daten": installation_daten,
            "arbeitsschutz_daten": arbeitsschutz_daten,
            "belegungen": belegungen,
            "buchungen": buchungen,
            "reinigungen": reinigungen,
            "schluessel": schluessel,
            "tokens": tokens,
            "log_eintraege": log_eintraege,
        },
    )


@login_required
def raum_erstellen(request):
    """Neuen Raum anlegen."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:uebersicht")

    geschosse = Geschoss.objects.select_related("gebaeude").order_by(
        "gebaeude__kuerzel", "reihenfolge"
    )
    bereiche = Bereich.objects.select_related("geschoss").all()
    from .models import RAUMTYP_CHOICES

    if request.method == "POST":
        geschoss_id = request.POST.get("geschoss")
        raumnummer = request.POST.get("raumnummer", "").strip()
        raumname = request.POST.get("raumname", "").strip()
        raumtyp = request.POST.get("raumtyp", "")
        nutzungsmodell = request.POST.get("nutzungsmodell", "statisch")
        kapazitaet = request.POST.get("kapazitaet") or None
        flaeche_m2 = request.POST.get("flaeche_m2") or None
        bereich_id = request.POST.get("bereich") or None
        ist_leer = request.POST.get("ist_leer") == "on"
        beschreibung = request.POST.get("beschreibung", "")

        fehler = []
        if not geschoss_id:
            fehler.append("Bitte ein Geschoss auswaehlen.")
        if not raumnummer:
            fehler.append("Raumnummer ist erforderlich.")
        if not raumtyp:
            fehler.append("Raumtyp ist erforderlich.")

        if not fehler:
            # Duplikat pruefen
            if Raum.objects.filter(geschoss_id=geschoss_id, raumnummer=raumnummer).exists():
                fehler.append("Diese Raumnummer existiert in diesem Geschoss bereits.")

        if fehler:
            for f in fehler:
                messages.error(request, f)
        else:
            raum = Raum.objects.create(
                geschoss_id=geschoss_id,
                raumnummer=raumnummer,
                raumname=raumname,
                raumtyp=raumtyp,
                nutzungsmodell=nutzungsmodell,
                kapazitaet=kapazitaet,
                flaeche_m2=flaeche_m2,
                bereich_id=bereich_id,
                ist_leer=ist_leer,
                beschreibung=beschreibung,
            )
            _log(raum, "erstellt", f"Raum {raumnummer} angelegt.", request.user, "Raum", raum.pk)
            messages.success(request, f"Raum {raumnummer} wurde angelegt.")
            return redirect("raumbuch:raum_detail", pk=raum.pk)

    return render(
        request,
        "raumbuch/raum_form.html",
        {
            "geschosse": geschosse,
            "bereiche": bereiche,
            "raumtyp_choices": RAUMTYP_CHOICES,
            "raum": None,
        },
    )


@login_required
def raum_bearbeiten(request, pk):
    """Raum-Stammdaten bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:raum_detail", pk=pk)

    raum = get_object_or_404(Raum, pk=pk)
    geschosse = Geschoss.objects.select_related("gebaeude").order_by(
        "gebaeude__kuerzel", "reihenfolge"
    )
    bereiche = Bereich.objects.select_related("geschoss").all()
    from .models import RAUMTYP_CHOICES

    if request.method == "POST":
        geschoss_id = request.POST.get("geschoss")
        raumnummer = request.POST.get("raumnummer", "").strip()
        raumname = request.POST.get("raumname", "").strip()
        raumtyp = request.POST.get("raumtyp", "")
        nutzungsmodell = request.POST.get("nutzungsmodell", "statisch")
        kapazitaet = request.POST.get("kapazitaet") or None
        flaeche_m2 = request.POST.get("flaeche_m2") or None
        bereich_id = request.POST.get("bereich") or None
        ist_leer = request.POST.get("ist_leer") == "on"
        ist_aktiv = request.POST.get("ist_aktiv") == "on"
        beschreibung = request.POST.get("beschreibung", "")

        # Duplikat nur pruefen wenn Nummer geaendert
        if (
            raumnummer != raum.raumnummer
            and Raum.objects.filter(geschoss_id=geschoss_id, raumnummer=raumnummer).exists()
        ):
            messages.error(request, "Diese Raumnummer existiert in diesem Geschoss bereits.")
        else:
            raum.geschoss_id = geschoss_id
            raum.raumnummer = raumnummer
            raum.raumname = raumname
            raum.raumtyp = raumtyp
            raum.nutzungsmodell = nutzungsmodell
            raum.kapazitaet = kapazitaet
            raum.flaeche_m2 = flaeche_m2
            raum.bereich_id = bereich_id
            raum.ist_leer = ist_leer
            raum.ist_aktiv = ist_aktiv
            raum.beschreibung = beschreibung
            raum.save()
            _log(raum, "geaendert", "Stammdaten aktualisiert.", request.user, "Raum", raum.pk)
            messages.success(request, "Raum wurde aktualisiert.")
            return redirect("raumbuch:raum_detail", pk=raum.pk)

    return render(
        request,
        "raumbuch/raum_form.html",
        {
            "raum": raum,
            "geschosse": geschosse,
            "bereiche": bereiche,
            "raumtyp_choices": RAUMTYP_CHOICES,
        },
    )


@login_required
def raum_loeschen(request, pk):
    """Raum deaktivieren (logisches Loeschen via ist_aktiv=False)."""
    if not request.user.is_staff:
        messages.error(request, "Nur Administratoren duerfen Raeume loeschen.")
        return redirect("raumbuch:raum_detail", pk=pk)

    raum = get_object_or_404(Raum, pk=pk)
    if request.method == "POST":
        raum.ist_aktiv = False
        raum.save()
        _log(raum, "deaktiviert", "Raum deaktiviert.", request.user, "Raum", raum.pk)
        messages.success(request, f"Raum {raum.raumnummer} wurde deaktiviert.")
        return redirect("raumbuch:uebersicht")

    return render(request, "raumbuch/raum_loeschen.html", {"raum": raum})


# ---------------------------------------------------------------------------
# Datenschicht-Views (gemeinsames Pattern: get_or_create + POST speichern)
# ---------------------------------------------------------------------------

def _datenschicht_view(request, pk, model_class, schicht_name, felder):
    """Generischer View fuer alle 5 Datenschichten."""
    raum = get_object_or_404(Raum, pk=pk)
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:raum_detail", pk=pk)

    obj, _ = model_class.objects.get_or_create(raum=raum)

    if request.method == "POST":
        for feld in felder:
            feldtyp = obj._meta.get_field(feld)
            val = request.POST.get(feld, "")
            if feldtyp.get_internal_type() == "BooleanField":
                setattr(obj, feld, val == "on")
            elif feldtyp.get_internal_type() in ("IntegerField",):
                setattr(obj, feld, int(val) if val else None)
            elif feldtyp.get_internal_type() in ("DecimalField",):
                setattr(obj, feld, val if val else None)
            elif feldtyp.get_internal_type() == "DateField":
                setattr(obj, feld, val if val else None)
            else:
                setattr(obj, feld, val)
        obj.save()
        _log(raum, f"{schicht_name} aktualisiert", "", request.user, model_class.__name__, obj.pk)
        messages.success(request, f"{schicht_name}-Daten gespeichert.")
        return redirect("raumbuch:raum_detail", pk=pk)

    # Felder als (name, wert, feldtyp_intern) Tupel aufbereiten
    felder_info = []
    for feld in felder:
        feldtyp = obj._meta.get_field(feld)
        felder_info.append({
            "name": feld,
            "wert": getattr(obj, feld),
            "typ": feldtyp.get_internal_type(),
        })

    return render(
        request,
        "raumbuch/schicht_form.html",
        {
            "raum": raum,
            "obj": obj,
            "schicht_name": schicht_name,
            "felder_info": felder_info,
        },
    )


@login_required
def raum_facility_daten(request, pk):
    felder = [
        "baujahr", "bodenbelag", "fenster_anzahl", "fenster_verdunkelbar",
        "flaeche_m2", "klima_typ", "letzte_renovierung", "lueftungsanlage",
        "moebelliste", "volumen_m3",
    ]
    return _datenschicht_view(request, pk, RaumFacilityDaten, "Facility", felder)


@login_required
def raum_elektro_daten(request, pk):
    felder = [
        "drehstrom", "notbeleuchtung", "sicherungsbezeichnungen",
        "stromkreise_beschreibung", "usv_gesichert",
    ]
    return _datenschicht_view(request, pk, RaumElektroDaten, "Elektro", felder)


@login_required
def raum_netzwerk_daten(request, pk):
    felder = [
        "ip_adressen", "lan_ports_anzahl", "lan_ports_beschreibung",
        "switch_name", "switch_port", "telefondosen", "wlan_abdeckung",
    ]
    return _datenschicht_view(request, pk, RaumNetzwerkDaten, "Netzwerk", felder)


@login_required
def raum_installation_daten(request, pk):
    felder = ["absperrhaehne", "brandschutzklappen", "glt_adressen"]
    return _datenschicht_view(request, pk, RaumInstallationDaten, "Installation", felder)


@login_required
def raum_arbeitsschutz_daten(request, pk):
    felder = [
        "aed_standort", "barrierefrei", "barrierefreiheit_details",
        "brandabschnitt", "erste_hilfe_kasten", "erste_hilfe_standort",
        "feuerloesch_naechste_pruefung", "feuerloesch_nummer", "feuerloesch_typ",
        "fluchtweg_beschreibung", "gefahrstoffe_beschreibung", "gefahrstoffe_vorhanden",
        "rauchmelder",
    ]
    return _datenschicht_view(request, pk, RaumArbeitsschutzDaten, "Arbeitsschutz", felder)


# ---------------------------------------------------------------------------
# Treppenhaus
# ---------------------------------------------------------------------------

@login_required
def treppenhaus_liste(request):
    """Alle Treppenhaeuser mit Zustand-Ampel."""
    treppenhaeuser = Treppenhaus.objects.select_related("gebaeude__standort").all()
    return render(request, "raumbuch/treppenhaus_liste.html", {"treppenhaeuser": treppenhaeuser})


@login_required
def treppenhaus_form(request, pk=None):
    """Treppenhaus anlegen oder bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:treppenhaus_liste")

    treppenhaus = get_object_or_404(Treppenhaus, pk=pk) if pk else None
    gebaeude_qs = Gebaeude.objects.select_related("standort").all()

    if request.method == "POST":
        daten = {
            "bezeichnung": request.POST.get("bezeichnung", ""),
            "gebaeude_id": request.POST.get("gebaeude"),
            "typ": request.POST.get("typ", "haupt"),
            "zustand": request.POST.get("zustand", "gut"),
            "lichte_breite_cm": request.POST.get("lichte_breite_cm") or None,
            "kapazitaet_personen": request.POST.get("kapazitaet_personen") or None,
            "verbindet_geschosse": request.POST.get("verbindet_geschosse", ""),
            "letzter_begehungstermin": request.POST.get("letzter_begehungstermin") or None,
            "naechste_pruefung": request.POST.get("naechste_pruefung") or None,
            "maengel": request.POST.get("maengel", ""),
        }
        if treppenhaus:
            for k, v in daten.items():
                setattr(treppenhaus, k, v)
            treppenhaus.save()
            messages.success(request, "Treppenhaus aktualisiert.")
        else:
            treppenhaus = Treppenhaus.objects.create(**daten)
            messages.success(request, "Treppenhaus angelegt.")
        return redirect("raumbuch:treppenhaus_liste")

    return render(
        request,
        "raumbuch/treppenhaus_form.html",
        {
            "treppenhaus": treppenhaus,
            "gebaeude_qs": gebaeude_qs,
            "typ_choices": Treppenhaus.TYP_CHOICES,
            "zustand_choices": Treppenhaus.ZUSTAND_CHOICES,
        },
    )


@login_required
def treppenhaus_loeschen(request, pk):
    """Treppenhaus loeschen (nur Staff)."""
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:treppenhaus_liste")

    treppenhaus = get_object_or_404(Treppenhaus, pk=pk)
    if request.method == "POST":
        treppenhaus.delete()
        messages.success(request, "Treppenhaus geloescht.")
        return redirect("raumbuch:treppenhaus_liste")

    return render(request, "raumbuch/treppenhaus_loeschen.html", {"treppenhaus": treppenhaus})


# ---------------------------------------------------------------------------
# Schluesselverwaltung
# ---------------------------------------------------------------------------

@login_required
def schluessel_liste(request):
    """Schluesselliste mit Ausgabe-Status."""
    schluessel_qs = Schluessel.objects.prefetch_related("raeume", "ausgaben").all()
    return render(request, "raumbuch/schluessel_liste.html", {"schluessel_qs": schluessel_qs})


@login_required
def schluessel_form(request, pk=None):
    """Schluessel anlegen oder bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:schluessel_liste")

    schluessel = get_object_or_404(Schluessel, pk=pk) if pk else None
    raeume_qs = Raum.objects.filter(ist_aktiv=True).select_related("geschoss__gebaeude")

    if request.method == "POST":
        schluesselnummer = request.POST.get("schluesselnummer", "").strip()
        bezeichnung = request.POST.get("bezeichnung", "").strip()
        schliessanlage = request.POST.get("schliessanlage", "")
        schliessanlage_typ = request.POST.get("schliessanlage_typ", "einzel")
        anzahl_kopien = int(request.POST.get("anzahl_kopien") or 1)
        raum_ids = request.POST.getlist("raeume")

        if not schluesselnummer or not bezeichnung:
            messages.error(request, "Schluesselnummer und Bezeichnung sind erforderlich.")
        else:
            if schluessel:
                schluessel.schluesselnummer = schluesselnummer
                schluessel.bezeichnung = bezeichnung
                schluessel.schliessanlage = schliessanlage
                schluessel.schliessanlage_typ = schliessanlage_typ
                schluessel.anzahl_kopien = anzahl_kopien
                schluessel.raeume.set(raum_ids)
                schluessel.save()
                messages.success(request, "Schluessel aktualisiert.")
            else:
                schluessel = Schluessel.objects.create(
                    schluesselnummer=schluesselnummer,
                    bezeichnung=bezeichnung,
                    schliessanlage=schliessanlage,
                    schliessanlage_typ=schliessanlage_typ,
                    anzahl_kopien=anzahl_kopien,
                )
                schluessel.raeume.set(raum_ids)
                messages.success(request, "Schluessel angelegt.")
            return redirect("raumbuch:schluessel_detail", pk=schluessel.pk)

    return render(
        request,
        "raumbuch/schluessel_form.html",
        {
            "schluessel": schluessel,
            "raeume_qs": raeume_qs,
            "anlage_typ_choices": Schluessel.ANLAGE_TYP,
        },
    )


@login_required
def schluessel_detail(request, pk):
    """Schluessel-Detail mit Ausgabe-Historie."""
    schluessel = get_object_or_404(Schluessel, pk=pk)
    ausgaben = schluessel.ausgaben.select_related("empfaenger", "ausgegeben_von").order_by(
        "-ausgabe_datum"
    )

    from hr.models import HRMitarbeiter
    mitarbeiter_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")

    return render(
        request,
        "raumbuch/schluessel_detail.html",
        {
            "schluessel": schluessel,
            "ausgaben": ausgaben,
            "mitarbeiter_qs": mitarbeiter_qs,
        },
    )


@login_required
def schluessel_ausgabe(request, pk):
    """Schluessel an Mitarbeiter ausgeben."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:schluessel_detail", pk=pk)

    schluessel = get_object_or_404(Schluessel, pk=pk)

    if request.method == "POST":
        empfaenger_id = request.POST.get("empfaenger")
        ausgabe_datum = request.POST.get("ausgabe_datum") or date.today()
        bemerkung = request.POST.get("bemerkung", "")

        if not empfaenger_id:
            messages.error(request, "Bitte einen Empfaenger auswaehlen.")
        else:
            SchluesselAusgabe.objects.create(
                schluessel=schluessel,
                empfaenger_id=empfaenger_id,
                ausgabe_datum=ausgabe_datum,
                ausgegeben_von=request.user,
                bemerkung=bemerkung,
            )
            messages.success(request, "Schluessel ausgegeben.")

    return redirect("raumbuch:schluessel_detail", pk=pk)


@login_required
def schluessel_rueckgabe(request, ausgabe_pk):
    """Schluessel-Rueckgabe erfassen."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:schluessel_liste")

    ausgabe = get_object_or_404(SchluesselAusgabe, pk=ausgabe_pk)

    if request.method == "POST":
        rueckgabe_datum = request.POST.get("rueckgabe_datum") or date.today()
        ausgabe.rueckgabe_datum = rueckgabe_datum
        ausgabe.save()
        messages.success(request, "Rueckgabe eingetragen.")

    return redirect("raumbuch:schluessel_detail", pk=ausgabe.schluessel_id)


# ---------------------------------------------------------------------------
# Zutrittskontrolle
# ---------------------------------------------------------------------------

@login_required
def token_liste(request):
    """Zutrittstoken-Liste mit Ablauf-Warnung."""
    tokens = ZutrittsToken.objects.select_related("mitarbeiter").prefetch_related("profile").exclude(status="beantragt")
    heute = date.today()

    # Beantragte Token nur fuer Security-Team, Facility-Team und Staff sichtbar
    beantragte = None
    if _ist_token_bearbeiter(request.user):
        beantragte = ZutrittsToken.objects.select_related("mitarbeiter").prefetch_related("profile").filter(status="beantragt")

    return render(request, "raumbuch/token_liste.html", {
        "tokens": tokens,
        "beantragte": beantragte,
        "heute": heute,
        "ist_token_bearbeiter": _ist_token_bearbeiter(request.user),
    })


@login_required
def token_anfrage(request):
    """Fuehrungskraefte (AL/BL/GF) koennen fuer ihre Mitarbeiter Token beantragen.

    Der Token wird mit status='beantragt' und badge_id='AUSSTEHEND' angelegt.
    Facility bearbeitet den Antrag und traegt die Badge-ID nach.
    """
    from hr.models import HRMitarbeiter

    # Zugriff: AL, BL, GF oder Staff
    try:
        rolle = request.user.hr_mitarbeiter.rolle
        ist_berechtigt = rolle in ("gf", "bereichsleiter", "abteilungsleiter")
    except AttributeError:
        ist_berechtigt = False

    if not (request.user.is_staff or ist_berechtigt):
        messages.error(request, "Keine Berechtigung fuer Token-Antraege.")
        return redirect("raumbuch:uebersicht")

    # Nur direkte Berichte oder (bei Staff) alle aktiven Mitarbeiter
    if request.user.is_staff:
        mitarbeiter_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")
    else:
        mitarbeiter_qs = request.user.hr_mitarbeiter.direkte_berichte.filter(
            user__is_active=True
        ).order_by("nachname", "vorname")

    profile_qs = ZutrittsProfil.objects.all().order_by("bezeichnung")

    if request.method == "POST":
        mitarbeiter_id = request.POST.get("mitarbeiter")
        profil_ids = request.POST.getlist("profile")
        gueltig_bis = request.POST.get("gueltig_bis") or None
        bemerkung = request.POST.get("bemerkung", "").strip()

        if not mitarbeiter_id:
            messages.error(request, "Bitte einen Mitarbeiter auswaehlen.")
        else:
            try:
                mitarbeiter = mitarbeiter_qs.get(pk=mitarbeiter_id)
            except HRMitarbeiter.DoesNotExist:
                messages.error(request, "Ungueltige Auswahl.")
                return redirect("raumbuch:token_anfrage")

            token = ZutrittsToken.objects.create(
                mitarbeiter=mitarbeiter,
                badge_id="AUSSTEHEND",
                status="beantragt",
                ausgestellt_am=date.today(),
                gueltig_bis=gueltig_bis or None,
                bemerkung=f"Beantragt von {request.user.get_full_name() or request.user.username}"
                          + (f": {bemerkung}" if bemerkung else ""),
            )
            if profil_ids:
                token.profile.set(ZutrittsProfil.objects.filter(pk__in=profil_ids))

            messages.success(
                request,
                f"Token-Antrag fuer {mitarbeiter} wurde eingereicht. "
                "Facility wird den Badge zuweisen.",
            )
            return redirect("raumbuch:token_anfrage")

    return render(request, "raumbuch/token_anfrage.html", {
        "mitarbeiter_qs": mitarbeiter_qs,
        "profile_qs": profile_qs,
    })


@login_required
def token_form(request, pk=None):
    """Zutrittstoken anlegen oder bearbeiten."""
    if not _ist_token_bearbeiter(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:token_liste")

    token = get_object_or_404(ZutrittsToken, pk=pk) if pk else None
    from hr.models import HRMitarbeiter
    mitarbeiter_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")
    profile_qs = ZutrittsProfil.objects.all()

    if request.method == "POST":
        mitarbeiter_id = request.POST.get("mitarbeiter")
        badge_id = request.POST.get("badge_id", "").strip()
        status = request.POST.get("status", "aktiv")
        ausgestellt_am = request.POST.get("ausgestellt_am") or date.today()
        gueltig_bis = request.POST.get("gueltig_bis") or None
        ablauf_warnung_tage = int(request.POST.get("ablauf_warnung_tage") or 30)
        profil_ids = request.POST.getlist("profile")
        bemerkung = request.POST.get("bemerkung", "")

        if not badge_id or not mitarbeiter_id:
            messages.error(request, "Badge-ID und Mitarbeiter sind Pflichtfelder.")
        else:
            if token:
                token.mitarbeiter_id = mitarbeiter_id
                token.badge_id = badge_id
                token.status = status
                token.ausgestellt_am = ausgestellt_am
                token.gueltig_bis = gueltig_bis
                token.ablauf_warnung_tage = ablauf_warnung_tage
                token.bemerkung = bemerkung
                token.profile.set(profil_ids)
                token.save()
                messages.success(request, "Token aktualisiert.")
            else:
                token = ZutrittsToken.objects.create(
                    mitarbeiter_id=mitarbeiter_id,
                    badge_id=badge_id,
                    status=status,
                    ausgestellt_am=ausgestellt_am,
                    gueltig_bis=gueltig_bis,
                    ablauf_warnung_tage=ablauf_warnung_tage,
                    bemerkung=bemerkung,
                )
                token.profile.set(profil_ids)
                messages.success(request, "Token angelegt.")
            return redirect("raumbuch:token_liste")

    return render(
        request,
        "raumbuch/token_form.html",
        {
            "token": token,
            "mitarbeiter_qs": mitarbeiter_qs,
            "profile_qs": profile_qs,
            "status_choices": ZutrittsToken.STATUS_CHOICES,
        },
    )


@login_required
def token_sperren(request, pk):
    """Token auf 'gesperrt' setzen."""
    if not _ist_token_bearbeiter(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:token_liste")

    token = get_object_or_404(ZutrittsToken, pk=pk)
    if request.method == "POST":
        token.status = "gesperrt"
        token.save()
        messages.success(request, f"Token {token.badge_id} wurde gesperrt.")

    return redirect("raumbuch:token_liste")


@login_required
def zutrittsprofil_liste(request):
    """Alle Zutrittsprofile."""
    profile = ZutrittsProfil.objects.prefetch_related("raeume").all()
    return render(request, "raumbuch/profil_liste.html", {"profile": profile})


@login_required
def zutrittsprofil_form(request, pk=None):
    """Zutrittsprofil anlegen oder bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:profil_liste")

    profil = get_object_or_404(ZutrittsProfil, pk=pk) if pk else None
    raeume_qs = Raum.objects.filter(ist_aktiv=True).select_related("geschoss__gebaeude")

    if request.method == "POST":
        bezeichnung = request.POST.get("bezeichnung", "").strip()
        beschreibung = request.POST.get("beschreibung", "")
        raum_ids = request.POST.getlist("raeume")

        if not bezeichnung:
            messages.error(request, "Bezeichnung ist erforderlich.")
        else:
            if profil:
                profil.bezeichnung = bezeichnung
                profil.beschreibung = beschreibung
                profil.raeume.set(raum_ids)
                profil.save()
                messages.success(request, "Profil aktualisiert.")
            else:
                profil = ZutrittsProfil.objects.create(
                    bezeichnung=bezeichnung, beschreibung=beschreibung
                )
                profil.raeume.set(raum_ids)
                messages.success(request, "Profil angelegt.")
            return redirect("raumbuch:profil_liste")

    return render(
        request,
        "raumbuch/profil_form.html",
        {"profil": profil, "raeume_qs": raeume_qs},
    )


# ---------------------------------------------------------------------------
# Belegung
# ---------------------------------------------------------------------------

@login_required
def belegungsplan(request):
    """Belegungsplan: Geschoss-Tabs mit aktueller Belegung."""
    geschosse = Geschoss.objects.select_related("gebaeude").prefetch_related(
        "raeume__belegungen__mitarbeiter"
    ).order_by("gebaeude__kuerzel", "reihenfolge")
    heute = date.today()
    return render(
        request,
        "raumbuch/belegungsplan.html",
        {"geschosse": geschosse, "heute": heute},
    )


@login_required
def belegung_form(request, pk=None):
    """Belegung anlegen oder bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:belegungsplan")

    belegung = get_object_or_404(Belegung, pk=pk) if pk else None
    from hr.models import HRMitarbeiter
    mitarbeiter_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")
    raeume_qs = Raum.objects.filter(ist_aktiv=True).select_related("geschoss__gebaeude")

    if request.method == "POST":
        raum_id = request.POST.get("raum")
        mitarbeiter_id = request.POST.get("mitarbeiter")
        von = request.POST.get("von")
        bis = request.POST.get("bis") or None
        notiz = request.POST.get("notiz", "")

        if not raum_id or not mitarbeiter_id or not von:
            messages.error(request, "Raum, Mitarbeiter und Von-Datum sind Pflichtfelder.")
        else:
            if belegung:
                belegung.raum_id = raum_id
                belegung.mitarbeiter_id = mitarbeiter_id
                belegung.von = von
                belegung.bis = bis
                belegung.notiz = notiz
                belegung.save()
                messages.success(request, "Belegung aktualisiert.")
            else:
                belegung = Belegung.objects.create(
                    raum_id=raum_id,
                    mitarbeiter_id=mitarbeiter_id,
                    von=von,
                    bis=bis,
                    notiz=notiz,
                )
                raum = belegung.raum
                _log(raum, "Belegung eingetragen", str(belegung), request.user, "Belegung", belegung.pk)
                messages.success(request, "Belegung eingetragen.")
            return redirect("raumbuch:belegungsplan")

    return render(
        request,
        "raumbuch/belegung_form.html",
        {"belegung": belegung, "mitarbeiter_qs": mitarbeiter_qs, "raeume_qs": raeume_qs},
    )


@login_required
def belegung_loeschen(request, pk):
    """Belegung entfernen."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:belegungsplan")

    belegung = get_object_or_404(Belegung, pk=pk)
    if request.method == "POST":
        raum = belegung.raum
        _log(raum, "Belegung geloescht", str(belegung), request.user, "Belegung", belegung.pk)
        belegung.delete()
        messages.success(request, "Belegung entfernt.")
    return redirect("raumbuch:belegungsplan")


# ---------------------------------------------------------------------------
# Reinigung
# ---------------------------------------------------------------------------

@login_required
def reinigung_uebersicht(request):
    """Reinigungsplan-Uebersicht mit Faelligkeit-Ampel."""
    plaene = Reinigungsplan.objects.select_related("raum__geschoss__gebaeude").all()
    return render(request, "raumbuch/reinigung_uebersicht.html", {"plaene": plaene})


@login_required
def reinigungsplan_form(request, raum_pk):
    """Reinigungsplan fuer einen Raum anlegen/bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:reinigung")

    raum = get_object_or_404(Raum, pk=raum_pk)
    plan, _ = Reinigungsplan.objects.get_or_create(raum=raum)

    if request.method == "POST":
        plan.intervall = request.POST.get("intervall", "taeglich")
        plan.zustaendig = request.POST.get("zustaendig", "")
        plan.methode = request.POST.get("methode", "")
        letzte = request.POST.get("letzte_reinigung")
        plan.letzte_reinigung = letzte if letzte else None
        plan.save()
        _log(raum, "Reinigungsplan aktualisiert", "", request.user, "Reinigungsplan", plan.pk)
        messages.success(request, "Reinigungsplan gespeichert.")
        return redirect("raumbuch:reinigung")

    return render(
        request,
        "raumbuch/reinigungsplan_form.html",
        {
            "raum": raum,
            "plan": plan,
            "intervall_choices": Reinigungsplan.INTERVALL_CHOICES,
        },
    )


@login_required
def reinigung_quittieren(request, raum_pk):
    """Reinigungsquittung erfassen und letzte_reinigung aktualisieren."""
    raum = get_object_or_404(Raum, pk=raum_pk)

    if request.method == "POST":
        name = request.POST.get("quittiert_durch_name", "").strip()
        bemerkung = request.POST.get("bemerkung", "")
        if not name:
            messages.error(request, "Name fuer die Quittung ist erforderlich.")
        else:
            ReinigungsQuittung.objects.create(
                raum=raum, quittiert_durch_name=name, bemerkung=bemerkung
            )
            # Letzte Reinigung am Plan aktualisieren
            plan, _ = Reinigungsplan.objects.get_or_create(raum=raum)
            plan.letzte_reinigung = date.today()
            plan.save()
            _log(raum, "Reinigung quittiert", f"Durch: {name}", request.user, "ReinigungsQuittung")
            messages.success(request, "Reinigung quittiert.")

    return redirect("raumbuch:reinigung")


# ---------------------------------------------------------------------------
# Besuchsanmeldung
# ---------------------------------------------------------------------------

@login_required
def besuch_liste(request):
    """Heutige und kommende Besuche."""
    heute = date.today()
    besuche_heute = Besuchsanmeldung.objects.filter(datum=heute).select_related(
        "gastgeber", "zielraum"
    )
    besuche_kommend = Besuchsanmeldung.objects.filter(datum__gt=heute).order_by("datum", "von").select_related(
        "gastgeber", "zielraum"
    )[:20]
    besuche_vergangen = Besuchsanmeldung.objects.filter(datum__lt=heute).order_by("-datum").select_related(
        "gastgeber", "zielraum"
    )[:20]
    return render(
        request,
        "raumbuch/besuch_liste.html",
        {
            "besuche_heute": besuche_heute,
            "besuche_kommend": besuche_kommend,
            "besuche_vergangen": besuche_vergangen,
            "heute": heute,
        },
    )


@login_required
def besuch_anmelden(request):
    """Besuch anmelden."""
    from hr.models import HRMitarbeiter
    gastgeber_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")
    raeume_qs = Raum.objects.filter(ist_aktiv=True).select_related("geschoss__gebaeude")

    if request.method == "POST":
        vorname = request.POST.get("besucher_vorname", "").strip()
        nachname = request.POST.get("besucher_nachname", "").strip()
        firma = request.POST.get("besucher_firma", "")
        gastgeber_id = request.POST.get("gastgeber")
        datum = request.POST.get("datum") or date.today()
        von = request.POST.get("von") or None
        bis = request.POST.get("bis") or None
        zielraum_id = request.POST.get("zielraum") or None
        zweck = request.POST.get("zweck", "")

        if not vorname or not nachname or not gastgeber_id:
            messages.error(request, "Vorname, Nachname und Gastgeber sind Pflichtfelder.")
        else:
            besuch = Besuchsanmeldung.objects.create(
                besucher_vorname=vorname,
                besucher_nachname=nachname,
                besucher_firma=firma,
                gastgeber_id=gastgeber_id,
                datum=datum,
                von=von,
                bis=bis,
                zielraum_id=zielraum_id,
                zweck=zweck,
                erstellt_von=request.user,
            )
            messages.success(request, f"Besuch von {vorname} {nachname} angemeldet.")
            return redirect("raumbuch:besuch_liste")

    return render(
        request,
        "raumbuch/besuch_form.html",
        {"gastgeber_qs": gastgeber_qs, "raeume_qs": raeume_qs, "besuch": None},
    )


@login_required
def besuch_bearbeiten(request, pk):
    """Besuchsanmeldung bearbeiten."""
    besuch = get_object_or_404(Besuchsanmeldung, pk=pk)
    from hr.models import HRMitarbeiter
    gastgeber_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")
    raeume_qs = Raum.objects.filter(ist_aktiv=True).select_related("geschoss__gebaeude")

    if request.method == "POST":
        besuch.besucher_vorname = request.POST.get("besucher_vorname", "").strip()
        besuch.besucher_nachname = request.POST.get("besucher_nachname", "").strip()
        besuch.besucher_firma = request.POST.get("besucher_firma", "")
        besuch.gastgeber_id = request.POST.get("gastgeber")
        besuch.datum = request.POST.get("datum") or date.today()
        besuch.von = request.POST.get("von") or None
        besuch.bis = request.POST.get("bis") or None
        besuch.zielraum_id = request.POST.get("zielraum") or None
        besuch.zweck = request.POST.get("zweck", "")
        besuch.status = request.POST.get("status", besuch.status)
        besuch.save()
        messages.success(request, "Besuch aktualisiert.")
        return redirect("raumbuch:besuch_liste")

    return render(
        request,
        "raumbuch/besuch_form.html",
        {
            "besuch": besuch,
            "gastgeber_qs": gastgeber_qs,
            "raeume_qs": raeume_qs,
            "status_choices": Besuchsanmeldung.STATUS_CHOICES,
        },
    )


# ---------------------------------------------------------------------------
# Buchungssystem
# ---------------------------------------------------------------------------

@login_required
def buchung_kalender(request):
    """Uebersicht buchbarer Raeume und aktuelle Buchungen."""
    buchbare_raeume = Raum.objects.filter(
        nutzungsmodell="dynamisch", ist_aktiv=True
    ).select_related("geschoss__gebaeude")
    datum_param = request.GET.get("datum")
    if datum_param:
        try:
            from datetime import datetime
            aktuelles_datum = datetime.strptime(datum_param, "%Y-%m-%d").date()
        except ValueError:
            aktuelles_datum = date.today()
    else:
        aktuelles_datum = date.today()

    buchungen = Raumbuchung.objects.filter(
        datum=aktuelles_datum, status__in=["offen", "bestaetigt"]
    ).select_related("raum", "buchender").order_by("von")

    return render(
        request,
        "raumbuch/buchung_kalender.html",
        {
            "buchbare_raeume": buchbare_raeume,
            "aktuelles_datum": aktuelles_datum,
            "buchungen": buchungen,
        },
    )


@login_required
def buchung_erstellen(request, raum_pk=None):
    """Buchung erstellen mit Konfliktpruefung."""
    buchbare_raeume = Raum.objects.filter(
        nutzungsmodell="dynamisch", ist_aktiv=True
    ).select_related("geschoss__gebaeude")

    vorausgewaehlter_raum = get_object_or_404(Raum, pk=raum_pk) if raum_pk else None

    konflikt = None

    if request.method == "POST":
        raum_id = request.POST.get("raum")
        datum = request.POST.get("datum")
        von = request.POST.get("von")
        bis = request.POST.get("bis")
        betreff = request.POST.get("betreff", "")
        teilnehmerzahl = request.POST.get("teilnehmerzahl") or None

        if not raum_id or not datum or not von or not bis:
            messages.error(request, "Raum, Datum, Von und Bis sind Pflichtfelder.")
        else:
            # Konfliktpruefung
            konflikt_qs = Raumbuchung.objects.filter(
                raum_id=raum_id,
                datum=datum,
                status__in=["offen", "bestaetigt"],
            ).exclude(
                # Keine Ueberschneidung wenn neue Buchung vor oder nach bestehender liegt
                bis__lte=von
            ).exclude(
                von__gte=bis
            )
            if konflikt_qs.exists():
                konflikt = konflikt_qs.first()
                messages.error(
                    request,
                    f"Zeitkonflikt mit Buchung {konflikt.buchungs_nr} ({konflikt.von}–{konflikt.bis}).",
                )
            else:
                buchungs_nr = Raumbuchung.generiere_buchungsnummer()
                # Raum-Objekt laden fuer Jitsi-Link-Generierung
                raum = get_object_or_404(Raum, pk=raum_id)
                raumname_slug = (
                    f"{raum.raumnummer}-{raum.raumname}"
                    if raum.raumname
                    else raum.raumnummer
                )
                jitsi_url = jitsi_link_generieren(raumname_slug, datum, buchungs_nr)
                buchung = Raumbuchung.objects.create(
                    raum_id=raum_id,
                    datum=datum,
                    von=von,
                    bis=bis,
                    betreff=betreff,
                    teilnehmerzahl=teilnehmerzahl,
                    buchender=request.user,
                    buchungs_nr=buchungs_nr,
                    jitsi_link=jitsi_url,
                    status="offen",
                )
                _log(raum, "Buchung erstellt", buchungs_nr, request.user, "Raumbuchung", buchung.pk)
                messages.success(request, f"Buchung {buchungs_nr} angelegt.")
                return redirect("raumbuch:buchung_detail", pk=buchung.pk)

    return render(
        request,
        "raumbuch/buchung_form.html",
        {
            "buchbare_raeume": buchbare_raeume,
            "vorausgewaehlter_raum": vorausgewaehlter_raum,
            "konflikt": konflikt,
            "heute": date.today(),
        },
    )


@login_required
def buchung_detail(request, pk):
    """Buchungsdetail mit Jitsi- und Matrix-Links."""
    buchung = get_object_or_404(Raumbuchung, pk=pk)
    matrix_link = matrix_raum_link(
        f"{buchung.raum.raumnummer}-{buchung.raum.raumname}"
        if buchung.raum.raumname
        else buchung.raum.raumnummer
    )
    return render(
        request,
        "raumbuch/buchung_detail.html",
        {"buchung": buchung, "matrix_link": matrix_link},
    )


@login_required
def buchung_stornieren(request, pk):
    """Buchung stornieren."""
    buchung = get_object_or_404(Raumbuchung, pk=pk)

    # Nur Ersteller oder Staff darf stornieren
    if request.user != buchung.buchender and not request.user.is_staff:
        messages.error(request, "Nur der Buchende oder ein Administrator darf stornieren.")
        return redirect("raumbuch:buchung_detail", pk=pk)

    if request.method == "POST":
        buchung.status = "storniert"
        buchung.save()
        _log(buchung.raum, "Buchung storniert", buchung.buchungs_nr, request.user, "Raumbuchung", buchung.pk)
        messages.success(request, f"Buchung {buchung.buchungs_nr} storniert.")
        return redirect("raumbuch:buchung_kalender")

    return render(request, "raumbuch/buchung_stornieren.html", {"buchung": buchung})


# ---------------------------------------------------------------------------
# Umzugsauftraege
# ---------------------------------------------------------------------------

@login_required
def umzug_liste(request):
    """Offene und erledigte Umzugsauftraege."""
    offen = Umzugsauftrag.objects.filter(
        status__in=["offen", "in_bearbeitung"]
    ).select_related("mitarbeiter", "von_raum", "nach_raum", "beauftragt_von").order_by("datum_geplant")
    erledigt = Umzugsauftrag.objects.filter(
        status__in=["erledigt", "storniert"]
    ).select_related("mitarbeiter", "von_raum", "nach_raum").order_by("-datum_geplant")[:20]
    return render(
        request,
        "raumbuch/umzug_liste.html",
        {"offen": offen, "erledigt": erledigt},
    )


@login_required
def umzug_form(request, pk=None):
    """Umzugsauftrag anlegen oder bearbeiten."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:umzug_liste")

    umzug = get_object_or_404(Umzugsauftrag, pk=pk) if pk else None
    from hr.models import HRMitarbeiter
    mitarbeiter_qs = HRMitarbeiter.objects.filter(user__is_active=True).order_by("nachname", "vorname")
    raeume_qs = Raum.objects.filter(ist_aktiv=True).select_related("geschoss__gebaeude")

    if request.method == "POST":
        datum_geplant = request.POST.get("datum_geplant")
        mitarbeiter_id = request.POST.get("mitarbeiter") or None
        von_raum_id = request.POST.get("von_raum") or None
        nach_raum_id = request.POST.get("nach_raum") or None
        notiz = request.POST.get("notiz", "")

        if not datum_geplant:
            messages.error(request, "Geplantes Datum ist erforderlich.")
        else:
            if umzug:
                umzug.datum_geplant = datum_geplant
                umzug.mitarbeiter_id = mitarbeiter_id
                umzug.von_raum_id = von_raum_id
                umzug.nach_raum_id = nach_raum_id
                umzug.notiz = notiz
                umzug.save()
                messages.success(request, "Umzugsauftrag aktualisiert.")
            else:
                umzug = Umzugsauftrag.objects.create(
                    datum_geplant=datum_geplant,
                    mitarbeiter_id=mitarbeiter_id,
                    von_raum_id=von_raum_id,
                    nach_raum_id=nach_raum_id,
                    notiz=notiz,
                    beauftragt_von=request.user,
                )
                messages.success(request, "Umzugsauftrag angelegt.")
            return redirect("raumbuch:umzug_liste")

    return render(
        request,
        "raumbuch/umzug_form.html",
        {"umzug": umzug, "mitarbeiter_qs": mitarbeiter_qs, "raeume_qs": raeume_qs},
    )


@login_required
def umzug_erledigen(request, pk):
    """Umzugsauftrag als erledigt markieren."""
    if not _ist_facility_oder_staff(request.user):
        messages.error(request, "Keine Berechtigung.")
        return redirect("raumbuch:umzug_liste")

    umzug = get_object_or_404(Umzugsauftrag, pk=pk)
    if request.method == "POST":
        umzug.status = "erledigt"
        umzug.save()

        # Belegung automatisch aktualisieren wenn MA und Raeume gesetzt
        if umzug.mitarbeiter and umzug.von_raum and umzug.nach_raum:
            # Alte Belegung beenden
            Belegung.objects.filter(
                mitarbeiter=umzug.mitarbeiter,
                raum=umzug.von_raum,
                bis__isnull=True,
            ).update(bis=date.today())
            # Neue Belegung anlegen
            Belegung.objects.create(
                mitarbeiter=umzug.mitarbeiter,
                raum=umzug.nach_raum,
                von=date.today(),
            )

        messages.success(request, "Umzug als erledigt markiert.")

    return redirect("raumbuch:umzug_liste")


# ---------------------------------------------------------------------------
# Audit-Trail
# ---------------------------------------------------------------------------

@login_required
def raum_log(request, pk):
    """Audit-Log fuer einen einzelnen Raum."""
    raum = get_object_or_404(Raum, pk=pk)
    log_eintraege = RaumbuchLog.objects.filter(raum=raum).select_related("geaendert_von")
    return render(
        request,
        "raumbuch/log_liste.html",
        {"raum": raum, "log_eintraege": log_eintraege},
    )


@login_required
def gesamtlog(request):
    """Vollstaendiger Audit-Trail (nur Staff)."""
    if not request.user.is_staff:
        messages.error(request, "Nur Administratoren haben Zugriff auf den Gesamtlog.")
        return redirect("raumbuch:uebersicht")

    log_eintraege = RaumbuchLog.objects.select_related("raum", "geaendert_von").all()[:200]
    return render(
        request,
        "raumbuch/log_liste.html",
        {"raum": None, "log_eintraege": log_eintraege},
    )


# ---------------------------------------------------------------------------
# Netzwerkplan – IT-Raum Detail mit Rack-Visualisierung
# ---------------------------------------------------------------------------

@login_required
def raum_netzwerkplan(request, pk):
    """Netzwerkplan eines IT-Raums: 19-Zoll Rack-SVG, Komponenten, Glasfaser."""
    raum = get_object_or_404(Raum, pk=pk)

    # Nur IT-Raeume freischalten
    it_typen = {"serverraum", "it_verteiler", "druckerraum", "elektroverteilung"}
    if raum.raumtyp not in it_typen and not request.user.is_staff:
        messages.error(request, "Kein Netzwerkplan fuer diesen Raumtyp verfuegbar.")
        return redirect("raumbuch:raum_detail", pk=pk)

    komponenten = raum.netzwerk_komponenten.all().order_by("-rack_einheit_start")

    # Hoechste belegte Rack-Einheit ermitteln (fuer SVG-Groesse)
    max_he = 42
    for k in komponenten:
        if k.rack_einheit_start:
            max_he = max(max_he, k.rack_einheit_start)

    # Glasfaserverbindungen die diesen Raum betreffen
    glasfaser = Glasfaserverbindung.objects.filter(
        von_raum=raum
    ).exclude(nach_raum=raum).select_related("nach_raum")

    # Verbundene Raeume: alle Bueros die ueber diesen Switch laufen
    try:
        netz = raum.netzwerk_daten
        switch_name = netz.switch_name or raum.raumnummer
    except RaumNetzwerkDaten.DoesNotExist:
        switch_name = raum.raumnummer

    # Alle Raeume die auf Komponenten in diesem Raum verweisen
    verbundene_raeume = (
        RaumNetzwerkDaten.objects.filter(switch_name__in=[k.bezeichnung for k in komponenten])
        .select_related("raum__geschoss")
        .order_by("raum__geschoss__reihenfolge", "raum__raumnummer")
    )

    # Gesamtport-Statistik
    gesamt_ports = sum(k.ports_gesamt or 0 for k in komponenten)
    belegte_ports = sum(k.ports_belegt or 0 for k in komponenten)

    return render(request, "raumbuch/netzwerkplan.html", {
        "raum": raum,
        "komponenten": komponenten,
        "max_he": max_he,
        "glasfaser": glasfaser,
        "verbundene_raeume": verbundene_raeume,
        "gesamt_ports": gesamt_ports,
        "belegte_ports": belegte_ports,
    })
