import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from hr.models import Abteilung, Bereich, HRMitarbeiter
from .models import Feier, FeierteilnahmeAnmeldung, FeierteilnahmeGutschrift

logger = logging.getLogger(__name__)


def _get_aktueller_hrma(request):
    """Gibt den HRMitarbeiter des eingeloggten Users zurueck oder None."""
    try:
        return HRMitarbeiter.objects.select_related("stelle").get(
            user=request.user
        )
    except HRMitarbeiter.DoesNotExist:
        return None


@login_required
def uebersicht(request):
    """Liste aller Veranstaltungen mit Filter."""
    qs = Feier.objects.select_related(
        "abteilung", "bereich", "verantwortlicher"
    )

    # Filter
    status_filter = request.GET.get("status", "")
    art_filter = request.GET.get("art", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if art_filter:
        qs = qs.filter(art=art_filter)

    context = {
        "feierlist": qs,
        "status_choices": Feier.STATUS_CHOICES,
        "art_choices": Feier.ART_CHOICES,
        "filter": {
            "status": status_filter,
            "art": art_filter,
        },
    }
    return render(request, "veranstaltungen/uebersicht.html", context)


@login_required
def detail(request, pk):
    """Detailansicht einer Veranstaltung mit Anmeldeliste."""
    feier = get_object_or_404(
        Feier.objects.select_related(
            "abteilung", "bereich", "verantwortlicher", "erstellt_von"
        ),
        pk=pk,
    )
    anmeldungen = feier.anmeldungen.select_related(
        "mitarbeiter", "mitarbeiter__stelle"
    ).order_by("ist_vorbereitungsteam", "mitarbeiter__nachname")

    # Pruefen ob eingeloggter User bereits angemeldet ist
    aktueller_hrma = _get_aktueller_hrma(request)
    bereits_angemeldet = False
    if aktueller_hrma:
        bereits_angemeldet = anmeldungen.filter(
            mitarbeiter=aktueller_hrma
        ).exists()

    context = {
        "feier": feier,
        "anmeldungen": anmeldungen,
        "aktueller_hrma": aktueller_hrma,
        "bereits_angemeldet": bereits_angemeldet,
    }
    return render(request, "veranstaltungen/detail.html", context)


@login_required
def anlegen(request):
    """Neue Veranstaltung anlegen."""
    aktueller_hrma = _get_aktueller_hrma(request)

    if request.method == "POST":
        titel = request.POST.get("titel", "").strip()
        art = request.POST.get("art", "sonstiges")
        datum = request.POST.get("datum")
        uhrzeit_von = request.POST.get("uhrzeit_von") or None
        uhrzeit_bis = request.POST.get("uhrzeit_bis") or None
        ort = request.POST.get("ort", "").strip()
        reichweite = request.POST.get("reichweite", "abteilung")
        anmeldeschluss = request.POST.get("anmeldeschluss") or None

        abteilung_pk = request.POST.get("abteilung") or None
        bereich_pk = request.POST.get("bereich") or None
        verantwortlicher_pk = request.POST.get("verantwortlicher") or None

        try:
            gutschrift_stunden = Decimal(
                request.POST.get("gutschrift_stunden", "0") or "0"
            )
            gutschrift_faktor = Decimal(
                request.POST.get("gutschrift_faktor", "1") or "1"
            )
            vorbereitung_stunden = Decimal(
                request.POST.get("vorbereitung_stunden", "0") or "0"
            )
            vorbereitung_faktor = Decimal(
                request.POST.get("vorbereitung_faktor", "1") or "1"
            )
        except Exception:
            gutschrift_stunden = Decimal("0")
            gutschrift_faktor = Decimal("1")
            vorbereitung_stunden = Decimal("0")
            vorbereitung_faktor = Decimal("1")

        if not titel or not datum:
            messages.error(request, "Titel und Datum sind Pflichtfelder.")
        else:
            feier = Feier.objects.create(
                titel=titel,
                art=art,
                datum=datum,
                uhrzeit_von=uhrzeit_von,
                uhrzeit_bis=uhrzeit_bis,
                ort=ort,
                reichweite=reichweite,
                anmeldeschluss=anmeldeschluss,
                abteilung_id=abteilung_pk,
                bereich_id=bereich_pk,
                verantwortlicher_id=verantwortlicher_pk,
                erstellt_von=aktueller_hrma,
                gutschrift_stunden=gutschrift_stunden,
                gutschrift_faktor=gutschrift_faktor,
                vorbereitung_stunden=vorbereitung_stunden,
                vorbereitung_faktor=vorbereitung_faktor,
                status="geplant",
            )
            messages.success(request, f"Veranstaltung \"{feier.titel}\" angelegt.")
            return redirect("veranstaltungen:detail", pk=feier.pk)

    context = {
        "abteilungen": Abteilung.objects.select_related("bereich").order_by(
            "bereich__name", "name"
        ),
        "bereiche": Bereich.objects.order_by("name"),
        "mitarbeiter_liste": HRMitarbeiter.objects.select_related(
            "stelle"
        ).order_by("nachname", "vorname"),
        "art_choices": Feier.ART_CHOICES,
        "reichweite_choices": Feier.REICHWEITE_CHOICES,
    }
    return render(request, "veranstaltungen/anlegen.html", context)


@login_required
def anmelden(request, pk):
    """HTMX-View: Selbst-Anmeldung oder Abmeldung zu einer Veranstaltung."""
    feier = get_object_or_404(Feier, pk=pk)
    aktueller_hrma = _get_aktueller_hrma(request)

    if not aktueller_hrma:
        if request.headers.get("HX-Request"):
            return render(
                request,
                "veranstaltungen/partials/_anmelde_fehler.html",
                {"fehler": "Kein HR-Mitarbeiter-Profil gefunden."},
            )
        messages.error(request, "Kein HR-Mitarbeiter-Profil gefunden.")
        return redirect("veranstaltungen:detail", pk=pk)

    if request.method == "POST":
        aktion = request.POST.get("aktion", "anmelden")
        if aktion == "abmelden":
            FeierteilnahmeAnmeldung.objects.filter(
                feier=feier, mitarbeiter=aktueller_hrma
            ).delete()
            bereits_angemeldet = False
        else:
            # Anmelden (idempotent)
            FeierteilnahmeAnmeldung.objects.get_or_create(
                feier=feier,
                mitarbeiter=aktueller_hrma,
                defaults={"ist_vorbereitungsteam": False},
            )
            bereits_angemeldet = True

        anmeldungen = feier.anmeldungen.select_related(
            "mitarbeiter", "mitarbeiter__stelle"
        ).order_by("ist_vorbereitungsteam", "mitarbeiter__nachname")

        if request.headers.get("HX-Request"):
            return render(
                request,
                "veranstaltungen/partials/_anmelde_bereich.html",
                {
                    "feier": feier,
                    "aktueller_hrma": aktueller_hrma,
                    "bereits_angemeldet": bereits_angemeldet,
                    "anmeldungen": anmeldungen,
                },
            )

    return redirect("veranstaltungen:detail", pk=pk)


@login_required
def bestaetigung_liste(request, pk):
    """Anwesenheitsliste bearbeiten: Teilnahme bestaetigen oder abwaehlen."""
    feier = get_object_or_404(Feier, pk=pk)
    aktueller_hrma = _get_aktueller_hrma(request)

    if request.method == "POST":
        # Alle bestaetigten IDs aus POST holen
        bestaetigte_ids = request.POST.getlist("bestaetigt")
        bestaetigte_ids = [int(i) for i in bestaetigte_ids if i.isdigit()]

        # Alle Anmeldungen der Feier aktualisieren
        for anmeldung in feier.anmeldungen.all():
            if anmeldung.pk in bestaetigte_ids:
                if not anmeldung.teilnahme_bestaetigt:
                    anmeldung.teilnahme_bestaetigt = True
                    anmeldung.bestaetigt_am = timezone.now()
                    anmeldung.bestaetigt_von = aktueller_hrma
                    anmeldung.save()
            else:
                if anmeldung.teilnahme_bestaetigt:
                    anmeldung.teilnahme_bestaetigt = False
                    anmeldung.bestaetigt_am = None
                    anmeldung.bestaetigt_von = None
                    anmeldung.save()

        messages.success(request, "Teilnahmen aktualisiert.")
        return redirect("veranstaltungen:bestaetigung_liste", pk=pk)

    anmeldungen = feier.anmeldungen.select_related(
        "mitarbeiter", "mitarbeiter__stelle", "bestaetigt_von"
    ).order_by("ist_vorbereitungsteam", "mitarbeiter__nachname")

    context = {
        "feier": feier,
        "anmeldungen": anmeldungen,
        "aktueller_hrma": aktueller_hrma,
    }
    return render(
        request, "veranstaltungen/bestaetigung_liste.html", context
    )


@login_required
def gutschrift_erstellen(request, pk):
    """Gutschrift-Sammeldokument anlegen und Status auf 'eingereicht' setzen."""
    feier = get_object_or_404(Feier, pk=pk)
    aktueller_hrma = _get_aktueller_hrma(request)

    # Vorhandenes Dokument laden oder neu anlegen
    gutschrift, _ = FeierteilnahmeGutschrift.objects.get_or_create(
        feier=feier,
        defaults={"erstellt_von": aktueller_hrma},
    )

    if request.method == "POST":
        bemerkung = request.POST.get("bemerkung", "").strip()
        gutschrift.bemerkung = bemerkung
        gutschrift.status = "eingereicht"
        gutschrift.eingereicht_am = timezone.now()
        gutschrift.save()

        # Feier-Status auf abgeschlossen setzen
        feier.status = "abgeschlossen"
        feier.save()

        messages.success(
            request, "Zeitgutschrift-Sammelliste eingereicht."
        )
        return redirect("veranstaltungen:gutschrift_pdf", pk=pk)

    teilnehmer = gutschrift.teilnehmer_bestaetigt()
    vorbereitungsteam = gutschrift.vorbereitungsteam_bestaetigt()

    context = {
        "feier": feier,
        "gutschrift": gutschrift,
        "teilnehmer": teilnehmer,
        "vorbereitungsteam": vorbereitungsteam,
        "aktueller_hrma": aktueller_hrma,
    }
    return render(
        request, "veranstaltungen/gutschrift_erstellen.html", context
    )


@login_required
def gutschrift_pdf(request, pk):
    """PDF-Ansicht der Gutschrift-Sammelliste (druckoptimiertes Template)."""
    feier = get_object_or_404(Feier, pk=pk)
    gutschrift = get_object_or_404(FeierteilnahmeGutschrift, feier=feier)

    teilnehmer = gutschrift.teilnehmer_bestaetigt()
    vorbereitungsteam = gutschrift.vorbereitungsteam_bestaetigt()

    context = {
        "feier": feier,
        "gutschrift": gutschrift,
        "teilnehmer": teilnehmer,
        "vorbereitungsteam": vorbereitungsteam,
        "jetzt": timezone.now(),
    }
    return render(request, "veranstaltungen/gutschrift_pdf.html", context)


@login_required
def status_aendern(request, pk):
    """HTMX-View: Status einer Veranstaltung schnell aendern."""
    feier = get_object_or_404(Feier, pk=pk)

    if request.method == "POST":
        neuer_status = request.POST.get("status")
        erlaubte_status = [s[0] for s in Feier.STATUS_CHOICES]
        if neuer_status in erlaubte_status:
            feier.status = neuer_status
            feier.save()

        if request.headers.get("HX-Request"):
            return render(
                request,
                "veranstaltungen/partials/_status_badge.html",
                {"feier": feier},
            )

    return redirect("veranstaltungen:detail", pk=pk)
