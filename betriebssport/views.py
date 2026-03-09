import calendar
import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from hr.models import HRMitarbeiter
from raumbuch.models import Standort

from .models import (
    BetriebssportGutschrift,
    Sporteinheit,
    Sportgruppe,
    SportgruppeMitglied,
    Sportteilnahme,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _get_hrma(request):
    """Gibt den HRMitarbeiter des eingeloggten Users zurueck oder None."""
    try:
        return HRMitarbeiter.objects.select_related("stelle").get(user=request.user)
    except HRMitarbeiter.DoesNotExist:
        return None


def _ist_verantwortlicher(gruppe, hrma):
    """True wenn hrma der Verantwortliche oder Staff ist."""
    if hrma is None:
        return False
    return gruppe.verantwortlicher_id == hrma.pk


def _erster_des_monats(jahr, monat):
    """Gibt den ersten Tag des Monats als date-Objekt zurueck."""
    return date(jahr, monat, 1)


def _baue_matrix(gruppe, einheiten, hrma):
    """Baut die Datenstruktur fuer die Anwesenheitsmatrix.

    Gibt zurueck:
      mitglieder  – QuerySet aller Mitglieder (geordnet)
      matrix      – Liste von Dicts:
                    {einheit, zeilen: [{mitarbeiter, anwesend, eigene_zeile}]}
      summen      – Dict mitarbeiter_pk -> Anzahl Anwesenheiten
    """
    mitglieder = list(
        gruppe.mitglieder.select_related("stelle", "abteilung")
        .order_by("nachname", "vorname")
    )

    # Alle Teilnahmen fuer diese Einheiten in einem DB-Call laden
    alle_teilnahmen = set(
        Sportteilnahme.objects.filter(einheit__in=einheiten)
        .values_list("einheit_id", "mitarbeiter_id")
    )

    matrix = []
    summen = {ma.pk: 0 for ma in mitglieder}

    for einheit in einheiten:
        zeilen = []
        for ma in mitglieder:
            anwesend = (einheit.pk, ma.pk) in alle_teilnahmen
            if anwesend:
                summen[ma.pk] += 1
            zeilen.append({
                "mitarbeiter": ma,
                "anwesend": anwesend,
                "eigene_zeile": hrma is not None and ma.pk == hrma.pk,
            })
        matrix.append({"einheit": einheit, "zeilen": zeilen})

    return mitglieder, matrix, summen


def _starte_workflow(gutschrift, user):
    """Startet den Betriebssport-Workflow."""
    from workflow.models import WorkflowTemplate, WorkflowInstance
    from workflow.services import WorkflowEngine
    from django.contrib.contenttypes.models import ContentType

    template = WorkflowTemplate.objects.filter(
        trigger_event="betriebssport_gutschrift_eingereicht",
        ist_aktiv=True,
    ).first()
    if not template:
        logger.debug("Kein aktives Betriebssport-Workflow-Template gefunden.")
        return

    ct = ContentType.objects.get_for_model(gutschrift)
    if WorkflowInstance.objects.filter(
        template=template,
        content_type=ct,
        object_id=gutschrift.pk,
        status__in=["laufend", "wartend"],
    ).exists():
        return

    try:
        WorkflowEngine().start_workflow(template, gutschrift, user)
        logger.info("Betriebssport-Workflow gestartet fuer pk=%s", gutschrift.pk)
    except Exception as exc:
        logger.error("Fehler beim Starten des Betriebssport-Workflows: %s", exc)


def _auto_signiere(gutschrift, request):
    """PDF erzeugen und sofort signieren."""
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        from signatur.services import signiere_pdf

        ctx = _gutschrift_pdf_context(gutschrift)
        html_string = render_to_string(
            "betriebssport/pdf/gutschrift_pdf.html",
            ctx,
            request=request,
        )
        pdf = HTML(
            string=html_string,
            base_url=request.build_absolute_uri(),
        ).write_pdf()

        user = gutschrift.erstellt_von.user if gutschrift.erstellt_von else request.user
        dateiname = f"BS-{gutschrift.pk}_{gutschrift.gruppe.name}_{gutschrift.monat:%Y-%m}.pdf".replace(" ", "_")
        signiere_pdf(
            pdf,
            user,
            dokument_name=dateiname,
            content_type="betriebssportgutschrift",
            object_id=gutschrift.pk,
        )
        logger.info("Auto-Signatur OK: BetriebssportGutschrift pk=%s", gutschrift.pk)
    except Exception as exc:
        logger.warning(
            "Auto-Signatur fehlgeschlagen: BetriebssportGutschrift pk=%s – %s",
            gutschrift.pk,
            exc,
        )


def _gutschrift_pdf_context(gutschrift):
    """Baut den Template-Kontext fuer das PDF."""
    gruppe = gutschrift.gruppe
    einheiten = list(gutschrift.einheiten.order_by("datum"))

    mitglieder = list(
        gruppe.mitglieder.select_related("abteilung")
        .order_by("nachname", "vorname")
    )

    alle_teilnahmen = set(
        Sportteilnahme.objects.filter(einheit__in=einheiten)
        .values_list("einheit_id", "mitarbeiter_id")
    )

    # Teilnehmerliste mit Einzelstunden und Gesamt
    teilnehmer_daten = []
    gesamt_stunden = 0
    for ma in mitglieder:
        anzahl = sum(
            1 for e in einheiten
            if (e.pk, ma.pk) in alle_teilnahmen and e.status == "stattgefunden"
        )
        stunden = gruppe.gutschrift_stunden * anzahl
        gesamt_stunden += stunden
        if anzahl > 0:
            teilnehmer_daten.append({
                "mitarbeiter": ma,
                "anzahl_einheiten": anzahl,
                "stunden": stunden,
            })

    # Workflow-Tasks laden
    workflow_tasks = []
    try:
        from workflow.models import WorkflowInstance, WorkflowTask
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(gutschrift)
        instanz = WorkflowInstance.objects.filter(
            content_type=ct, object_id=gutschrift.pk
        ).order_by("-gestartet_am").first()
        if instanz:
            workflow_tasks = list(
                WorkflowTask.objects.filter(instance=instanz)
                .select_related("step", "bearbeitet_von", "claimed_von")
                .order_by("step__reihenfolge")
            )
    except Exception:
        pass

    return {
        "gutschrift": gutschrift,
        "gruppe": gruppe,
        "einheiten": einheiten,
        "teilnehmer_daten": teilnehmer_daten,
        "gesamt_stunden": gesamt_stunden,
        "workflow_tasks": workflow_tasks,
        "jetzt": timezone.now(),
    }


def _monat_navigation(monat):
    """Gibt vorherigen und naechsten Monat als date-Objekte zurueck."""
    if monat.month == 1:
        vormonat = date(monat.year - 1, 12, 1)
    else:
        vormonat = date(monat.year, monat.month - 1, 1)
    if monat.month == 12:
        naechster = date(monat.year + 1, 1, 1)
    else:
        naechster = date(monat.year, monat.month + 1, 1)
    return vormonat, naechster


# ---------------------------------------------------------------------------
# Views: Sportgruppen
# ---------------------------------------------------------------------------

@login_required
def uebersicht(request):
    """Alle aktiven Sportgruppen anzeigen."""
    hrma = _get_hrma(request)

    gruppen = Sportgruppe.objects.select_related(
        "verantwortlicher", "standort"
    ).filter(status="aktiv")

    # Mitgliedschaft des eingeloggten Nutzers vorberechnen
    meine_pks = set()
    if hrma:
        meine_pks = set(
            SportgruppeMitglied.objects.filter(mitarbeiter=hrma)
            .values_list("gruppe_id", flat=True)
        )

    gruppen_liste = []
    for g in gruppen:
        gruppen_liste.append({
            "gruppe": g,
            "ist_mitglied": g.pk in meine_pks,
            "mitglieder_anzahl": g.mitglieder.count(),
        })

    context = {
        "gruppen_liste": gruppen_liste,
        "hrma": hrma,
    }
    return render(request, "betriebssport/uebersicht.html", context)


@login_required
def gruppe_detail(request, pk):
    """Detailansicht mit Matrix fuer den aktuellen Monat."""
    gruppe = get_object_or_404(
        Sportgruppe.objects.select_related("verantwortlicher", "standort"),
        pk=pk,
    )
    hrma = _get_hrma(request)
    ist_verantwortlicher = _ist_verantwortlicher(gruppe, hrma) or request.user.is_staff

    # Monat aus GET-Parameter lesen (Standard: aktueller Monat)
    heute = timezone.localdate()
    try:
        monat_str = request.GET.get("monat", "")
        if monat_str:
            teile = monat_str.split("-")
            monat = _erster_des_monats(int(teile[0]), int(teile[1]))
        else:
            monat = _erster_des_monats(heute.year, heute.month)
    except (ValueError, IndexError):
        monat = _erster_des_monats(heute.year, heute.month)

    # Letzter Tag des Monats
    letzter_tag = calendar.monthrange(monat.year, monat.month)[1]
    monat_ende = date(monat.year, monat.month, letzter_tag)

    einheiten = list(
        gruppe.einheiten.filter(datum__gte=monat, datum__lte=monat_ende)
        .order_by("datum")
    )

    mitglieder, matrix, summen = _baue_matrix(gruppe, einheiten, hrma)

    # Mitgliedschaft des eingeloggten Nutzers
    ist_mitglied = False
    if hrma:
        ist_mitglied = SportgruppeMitglied.objects.filter(
            gruppe=gruppe, mitarbeiter=hrma
        ).exists()

    # Gutschrift fuer diesen Monat (falls vorhanden)
    gutschrift = BetriebssportGutschrift.objects.filter(
        gruppe=gruppe, monat=monat
    ).first()

    vormonat, naechster_monat = _monat_navigation(monat)

    context = {
        "gruppe": gruppe,
        "hrma": hrma,
        "ist_mitglied": ist_mitglied,
        "ist_verantwortlicher": ist_verantwortlicher,
        "monat": monat,
        "vormonat": vormonat,
        "naechster_monat": naechster_monat,
        "einheiten": einheiten,
        "mitglieder": mitglieder,
        "matrix": matrix,
        "summen": summen,
        "gutschrift": gutschrift,
        "heute": heute,
    }
    return render(request, "betriebssport/gruppe_detail.html", context)


@login_required
def gruppe_anlegen(request):
    """Neue Sportgruppe anlegen (Staff oder jeder mit HR-Profil)."""
    hrma = _get_hrma(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        sportart = request.POST.get("sportart", "sonstiges")
        wochentag = request.POST.get("wochentag", "0")
        uhrzeit_von = request.POST.get("uhrzeit_von") or None
        uhrzeit_bis = request.POST.get("uhrzeit_bis") or None
        ort = request.POST.get("ort_beschreibung", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        standort_pk = request.POST.get("standort") or None

        if not name:
            messages.error(request, "Name ist ein Pflichtfeld.")
        elif hrma is None:
            messages.error(request, "Kein HR-Profil gefunden.")
        else:
            gruppe = Sportgruppe.objects.create(
                name=name,
                sportart=sportart,
                wochentag=int(wochentag),
                uhrzeit_von=uhrzeit_von,
                uhrzeit_bis=uhrzeit_bis,
                ort_beschreibung=ort,
                beschreibung=beschreibung,
                standort_id=standort_pk,
                verantwortlicher=hrma,
                status="aktiv",
            )
            # Verantwortlicher tritt automatisch bei
            SportgruppeMitglied.objects.get_or_create(
                gruppe=gruppe, mitarbeiter=hrma
            )
            messages.success(request, f"Sportgruppe \"{gruppe}\" angelegt.")
            return redirect("betriebssport:gruppe_detail", pk=gruppe.pk)

    context = {
        "sportart_choices": Sportgruppe.SPORTART_CHOICES,
        "wochentag_choices": Sportgruppe.WOCHENTAG_CHOICES,
        "standorte": Standort.objects.order_by("name"),
    }
    return render(request, "betriebssport/gruppe_anlegen.html", context)


@login_required
def gruppe_bearbeiten(request, pk):
    """Sportgruppe bearbeiten – nur Verantwortlicher oder Staff."""
    from decimal import Decimal as _Dec
    gruppe = get_object_or_404(Sportgruppe, pk=pk)
    hrma = _get_hrma(request)

    if not (_ist_verantwortlicher(gruppe, hrma) or request.user.is_staff):
        messages.error(request, "Nur der Verantwortliche darf die Gruppe bearbeiten.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    if request.method == "POST":
        gruppe.name = request.POST.get("name", gruppe.name).strip()
        gruppe.sportart = request.POST.get("sportart", gruppe.sportart)
        gruppe.wochentag = int(request.POST.get("wochentag", gruppe.wochentag))
        gruppe.uhrzeit_von = request.POST.get("uhrzeit_von") or None
        gruppe.uhrzeit_bis = request.POST.get("uhrzeit_bis") or None
        gruppe.ort_beschreibung = request.POST.get("ort_beschreibung", "").strip()
        gruppe.beschreibung = request.POST.get("beschreibung", "").strip()
        gruppe.status = request.POST.get("status", gruppe.status)
        standort_pk = request.POST.get("standort") or None
        gruppe.standort_id = standort_pk
        try:
            gruppe.gutschrift_stunden = _Dec(
                request.POST.get("gutschrift_stunden", "1") or "1"
            )
        except Exception:
            pass
        gruppe.save()
        messages.success(request, "Gruppe gespeichert.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    context = {
        "gruppe": gruppe,
        "sportart_choices": Sportgruppe.SPORTART_CHOICES,
        "wochentag_choices": Sportgruppe.WOCHENTAG_CHOICES,
        "status_choices": Sportgruppe.STATUS_CHOICES,
        "standorte": Standort.objects.order_by("name"),
    }
    return render(request, "betriebssport/gruppe_bearbeiten.html", context)


# ---------------------------------------------------------------------------
# Views: Mitgliedschaft (HTMX)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def beitreten_toggle(request, pk):
    """HTMX: Gruppe beitreten oder verlassen."""
    gruppe = get_object_or_404(Sportgruppe, pk=pk)
    hrma = _get_hrma(request)

    if hrma is None:
        return HttpResponse("Kein HR-Profil.", status=400)

    mitglied, erstellt = SportgruppeMitglied.objects.get_or_create(
        gruppe=gruppe, mitarbeiter=hrma
    )
    if not erstellt:
        mitglied.delete()
        ist_mitglied = False
    else:
        ist_mitglied = True

    return render(
        request,
        "betriebssport/partials/_beitreten_btn.html",
        {"gruppe": gruppe, "ist_mitglied": ist_mitglied},
    )


# ---------------------------------------------------------------------------
# Views: Einheiten
# ---------------------------------------------------------------------------

@login_required
@require_POST
def einheit_anlegen(request, pk):
    """Verantwortlicher legt eine neue Trainingseinheit an."""
    gruppe = get_object_or_404(Sportgruppe, pk=pk)
    hrma = _get_hrma(request)

    if not (_ist_verantwortlicher(gruppe, hrma) or request.user.is_staff):
        messages.error(request, "Nur der Verantwortliche darf Einheiten anlegen.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    datum = request.POST.get("datum")
    if not datum:
        messages.error(request, "Datum ist Pflichtfeld.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    einheit, erstellt = Sporteinheit.objects.get_or_create(
        gruppe=gruppe,
        datum=datum,
        defaults={"erstellt_von": hrma, "status": "stattgefunden"},
    )
    if erstellt:
        messages.success(request, f"Einheit am {einheit.datum} angelegt.")
    else:
        messages.warning(request, f"Einheit am {einheit.datum} existiert bereits.")

    from django.urls import reverse
    monat_str = f"{einheit.datum.year}-{einheit.datum.month:02d}"
    url = reverse("betriebssport:gruppe_detail", kwargs={"pk": pk})
    return redirect(f"{url}?monat={monat_str}")


@login_required
@require_POST
def einheit_ausgefallen(request, pk, einheit_pk):
    """Verantwortlicher markiert eine Einheit als ausgefallen."""
    gruppe = get_object_or_404(Sportgruppe, pk=pk)
    einheit = get_object_or_404(Sporteinheit, pk=einheit_pk, gruppe=gruppe)
    hrma = _get_hrma(request)

    if not (_ist_verantwortlicher(gruppe, hrma) or request.user.is_staff):
        messages.error(request, "Keine Berechtigung.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    if einheit.status == "ausgefallen":
        einheit.status = "stattgefunden"
        meldung = f"Einheit am {einheit.datum} wieder als stattgefunden markiert."
    else:
        einheit.status = "ausgefallen"
        meldung = f"Einheit am {einheit.datum} als ausgefallen markiert."
    einheit.save()
    messages.success(request, meldung)

    monat_str = f"{einheit.datum.year}-{einheit.datum.month:02d}"
    from django.urls import reverse
    url = reverse("betriebssport:gruppe_detail", kwargs={"pk": pk})
    return redirect(f"{url}?monat={monat_str}")


# ---------------------------------------------------------------------------
# Views: Teilnahme-Toggle (HTMX)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def teilnahme_toggle(request, pk, einheit_pk):
    """HTMX: Eigene Teilnahme an einer Einheit an/abhaken."""
    gruppe = get_object_or_404(Sportgruppe, pk=pk)
    einheit = get_object_or_404(
        Sporteinheit, pk=einheit_pk, gruppe=gruppe
    )
    hrma = _get_hrma(request)

    if hrma is None:
        return HttpResponse("Kein HR-Profil.", status=400)

    # Verantwortlicher darf fuer beliebige Mitarbeiter togglen
    ziel_pk = request.POST.get("mitarbeiter_pk")
    ist_verantwortlicher = _ist_verantwortlicher(gruppe, hrma) or request.user.is_staff
    if ziel_pk and ist_verantwortlicher:
        try:
            ziel_ma = HRMitarbeiter.objects.get(pk=int(ziel_pk))
        except (HRMitarbeiter.DoesNotExist, ValueError):
            ziel_ma = hrma
    else:
        ziel_ma = hrma

    if einheit.status == "ausgefallen":
        return HttpResponse("Ausgefallen.", status=400)

    teilnahme, erstellt = Sportteilnahme.objects.get_or_create(
        einheit=einheit, mitarbeiter=ziel_ma
    )
    if not erstellt:
        teilnahme.delete()
        anwesend = False
    else:
        anwesend = True

    return render(
        request,
        "betriebssport/partials/_teilnahme_zelle.html",
        {
            "einheit": einheit,
            "gruppe": gruppe,
            "mitarbeiter": ziel_ma,
            "anwesend": anwesend,
            "eigene_zeile": ziel_ma.pk == hrma.pk,
            "ist_verantwortlicher": ist_verantwortlicher,
        },
    )


# ---------------------------------------------------------------------------
# Views: Gutschrift
# ---------------------------------------------------------------------------

@login_required
def gutschrift_monat(request, pk, monat_str):
    """Monatliche Gutschrift anlegen / ansehen."""
    gruppe = get_object_or_404(
        Sportgruppe.objects.select_related("verantwortlicher"), pk=pk
    )
    hrma = _get_hrma(request)
    ist_verantwortlicher = _ist_verantwortlicher(gruppe, hrma) or request.user.is_staff

    if not ist_verantwortlicher:
        messages.error(request, "Nur der Verantwortliche kann Gutschriften erstellen.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    try:
        teile = monat_str.split("-")
        monat = _erster_des_monats(int(teile[0]), int(teile[1]))
    except (ValueError, IndexError):
        messages.error(request, "Ungueltige Monatsangabe.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    letzter_tag = calendar.monthrange(monat.year, monat.month)[1]
    monat_ende = date(monat.year, monat.month, letzter_tag)

    einheiten = list(
        gruppe.einheiten.filter(datum__gte=monat, datum__lte=monat_ende)
        .order_by("datum")
    )

    # Gutschrift anlegen falls noch nicht vorhanden
    gutschrift, _ = BetriebssportGutschrift.objects.get_or_create(
        gruppe=gruppe,
        monat=monat,
        defaults={"erstellt_von": hrma},
    )
    gutschrift.einheiten.set(einheiten)

    if request.method == "POST" and gutschrift.status == "entwurf":
        bemerkung = request.POST.get("bemerkung", "").strip()
        gutschrift.bemerkung = bemerkung
        gutschrift.status = "eingereicht"
        gutschrift.eingereicht_am = timezone.now()
        gutschrift.save()

        _starte_workflow(gutschrift, request.user)
        _auto_signiere(gutschrift, request)

        messages.success(request, "Betriebssport-Gutschrift eingereicht.")
        return redirect(
            "betriebssport:gutschrift_download",
            pk=pk,
            monat_str=monat_str,
        )

    # Vorschau-Daten aufbereiten
    mitglieder = list(
        gruppe.mitglieder.select_related("abteilung").order_by("nachname", "vorname")
    )
    alle_teilnahmen = set(
        Sportteilnahme.objects.filter(einheit__in=einheiten)
        .values_list("einheit_id", "mitarbeiter_id")
    )

    vorschau = []
    gesamt_stunden = 0
    for ma in mitglieder:
        anzahl = sum(
            1 for e in einheiten
            if (e.pk, ma.pk) in alle_teilnahmen and e.status == "stattgefunden"
        )
        stunden = gruppe.gutschrift_stunden * anzahl
        gesamt_stunden += stunden
        if anzahl > 0:
            vorschau.append({
                "mitarbeiter": ma,
                "anzahl": anzahl,
                "stunden": stunden,
            })

    context = {
        "gruppe": gruppe,
        "gutschrift": gutschrift,
        "monat": monat,
        "einheiten": einheiten,
        "vorschau": vorschau,
        "gesamt_stunden": gesamt_stunden,
        "hrma": hrma,
    }
    return render(request, "betriebssport/gutschrift_monat.html", context)


@login_required
def gutschrift_download(request, pk, monat_str):
    """Signiertes PDF der Betriebssport-Gutschrift herunterladen."""
    gruppe = get_object_or_404(Sportgruppe, pk=pk)

    try:
        teile = monat_str.split("-")
        monat = _erster_des_monats(int(teile[0]), int(teile[1]))
    except (ValueError, IndexError):
        messages.error(request, "Ungueltige Monatsangabe.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    gutschrift = get_object_or_404(
        BetriebssportGutschrift, gruppe=gruppe, monat=monat
    )
    dateiname = (
        f"BS-{gutschrift.pk}_{gruppe.name}_{monat:%Y-%m}.pdf".replace(" ", "_")
    )

    # Vorhandene Signatur suchen
    try:
        from signatur.models import SignaturJob
        job = (
            SignaturJob.objects.filter(
                content_type="betriebssportgutschrift",
                object_id=gutschrift.pk,
                status="completed",
            )
            .select_related("protokoll")
            .order_by("-erstellt_am")
            .first()
        )
        if job and hasattr(job, "protokoll") and job.protokoll and job.protokoll.signiertes_pdf:
            pdf_bytes = bytes(job.protokoll.signiertes_pdf)
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
            return response
    except Exception as exc:
        logger.warning("SignaturJob-Lookup fehlgeschlagen: %s", exc)

    # Fallback: WeasyPrint frisch erzeugen
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string

        ctx = _gutschrift_pdf_context(gutschrift)
        html_string = render_to_string(
            "betriebssport/pdf/gutschrift_pdf.html",
            ctx,
            request=request,
        )
        pdf_bytes = HTML(
            string=html_string,
            base_url=request.build_absolute_uri(),
        ).write_pdf()
    except Exception as exc:
        logger.error("WeasyPrint-Fehler: %s", exc)
        messages.error(request, "PDF konnte nicht erzeugt werden.")
        return redirect("betriebssport:gruppe_detail", pk=pk)

    # Signatur-Versuch
    try:
        from signatur.services import signiere_pdf
        user = gutschrift.erstellt_von.user if gutschrift.erstellt_von else request.user
        pdf_bytes = signiere_pdf(
            pdf_bytes,
            user,
            dokument_name=dateiname,
            content_type="betriebssportgutschrift",
            object_id=gutschrift.pk,
        )
    except Exception as exc:
        logger.warning("Signatur fehlgeschlagen, PDF unsigniert: %s", exc)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
    return response
