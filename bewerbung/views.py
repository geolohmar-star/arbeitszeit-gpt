import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BewerbungDokumentForm, BewerbungForm, HREinstellungForm
from .models import Bewerbung, BewerbungDokument, EinladungsCode
from .services import erstelle_absage_docx, erstelle_zusage_docx, lehne_ab, stelle_ein

logger = logging.getLogger(__name__)

SESSION_CODE_KEY = "bewerbung_einladungscode"


def _nur_hr(user):
    """Prueft ob der User HR-Rechte hat."""
    return user.is_staff or user.has_perm("hr.hr_view_stammdaten")


# ── Bewerber-Seite (kein Login noetig) ──────────────────────────────────────

def code_eingabe(request):
    """Einstiegsseite: Bewerber gibt seinen Einladungscode ein."""
    fehler = None

    if request.method == "POST":
        code_roh = request.POST.get("code", "").strip().upper()
        try:
            einladung = EinladungsCode.objects.get(code=code_roh)
        except EinladungsCode.DoesNotExist:
            fehler = "Ungültiger Code. Bitte wenden Sie sich an die Personalabteilung."
        else:
            if einladung.status == EinladungsCode.STATUS_VERWENDET:
                fehler = "Dieser Code wurde bereits verwendet."
            elif einladung.status != EinladungsCode.STATUS_VERFUEGBAR and \
                    einladung.status != EinladungsCode.STATUS_AUSGEGEBEN:
                fehler = "Dieser Code ist nicht mehr gueltig."
            else:
                # Code in Session merken, weiterleiten
                request.session[SESSION_CODE_KEY] = einladung.code
                return redirect("bewerbung:erfassen")

    return render(request, "bewerbung/code_eingabe.html", {"fehler": fehler})


def bewerbung_erfassen(request):
    """Bewerber fuellt am Intranet-PC den Bogen aus. Einladungscode erforderlich."""
    code_str = request.session.get(SESSION_CODE_KEY)
    if not code_str:
        return redirect("bewerbung:code_eingabe")

    try:
        einladung = EinladungsCode.objects.get(
            code=code_str,
            status__in=[EinladungsCode.STATUS_VERFUEGBAR, EinladungsCode.STATUS_AUSGEGEBEN],
        )
    except EinladungsCode.DoesNotExist:
        # Code ungueltig oder schon verwendet
        del request.session[SESSION_CODE_KEY]
        return redirect("bewerbung:code_eingabe")

    if request.method == "POST":
        form = BewerbungForm(request.POST)
        if form.is_valid():
            bewerbung = form.save(commit=False)
            bewerbung.einladungscode = einladung
            bewerbung.save()
            # Code als verwendet markieren
            einladung.status = EinladungsCode.STATUS_VERWENDET
            einladung.save()
            # Session bereinigen
            del request.session[SESSION_CODE_KEY]
            return redirect("bewerbung:erfassen_dokumente", pk=bewerbung.pk)
    else:
        form = BewerbungForm()

    return render(request, "bewerbung/erfassen.html", {"form": form})


def bewerbung_dokumente(request, pk):
    """Schritt 2: Dokumente zur Bewerbung hochladen."""
    bewerbung = get_object_or_404(Bewerbung, pk=pk, status=Bewerbung.STATUS_EINGEGANGEN)

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
                    messages.error(
                        request,
                        f"Datei abgelehnt: Bedrohung gefunden ({scan.bedrohung}).",
                    )
                    return render(request, "bewerbung/dokumente.html", {
                        "bewerbung": bewerbung,
                        "form": form,
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
                    "bewerbung": bewerbung,
                    "form": form,
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


# ── HR-Bereich (Login + HR-Recht) ───────────────────────────────────────────

@login_required
def hr_liste(request):
    """HR-Uebersicht aller Bewerbungen."""
    if not _nur_hr(request.user):
        raise Http404

    status_filter = request.GET.get("status", "")
    bewerbungen = Bewerbung.objects.select_related(
        "bearbeitet_von", "angestrebte_stelle", "einladungscode"
    )
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

    bewerbung = get_object_or_404(
        Bewerbung.objects.select_related("bearbeitet_von", "angestrebte_stelle", "einladungscode"),
        pk=pk,
    )

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
def hr_status_weiter(request, pk):
    """Bewerbungsstatus einen Schritt vorwaerts schalten."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)

    if request.method == "POST":
        naechster = bewerbung.naechster_status
        if naechster:
            bewerbung.status = naechster
            bewerbung.bearbeitet_von = request.user
            bewerbung.save()
            messages.success(
                request,
                f"Status geaendert: {bewerbung.get_status_display()}",
            )
        else:
            messages.warning(request, "Kein weiterer Status moeglich.")

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
                "Bewerbungsdaten wurden DSGVO-konform geloescht.",
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
def hr_zusage_docx(request, pk):
    """Zusage-Brief als DOCX herunterladen."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)

    docx_bytes = erstelle_zusage_docx(bewerbung)
    name_safe = f"{bewerbung.nachname}_{bewerbung.vorname}".replace(" ", "_")
    response = HttpResponse(
        docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="Zusage_{name_safe}.docx"'
    return response


@login_required
def hr_absage_docx(request, pk):
    """Absage-Brief als DOCX herunterladen."""
    if not _nur_hr(request.user):
        raise Http404

    bewerbung = get_object_or_404(Bewerbung, pk=pk)

    docx_bytes = erstelle_absage_docx(bewerbung)
    name_safe = f"{bewerbung.nachname}_{bewerbung.vorname}".replace(" ", "_")
    response = HttpResponse(
        docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="Absage_{name_safe}.docx"'
    return response


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


@login_required
def hr_einladungscodes(request):
    """HR-Uebersicht der Einladungscodes – ausgeben und verwalten."""
    if not _nur_hr(request.user):
        raise Http404

    if request.method == "POST":
        code_pk = request.POST.get("code_pk")
        aktion = request.POST.get("aktion")
        try:
            code = EinladungsCode.objects.get(pk=code_pk)
        except EinladungsCode.DoesNotExist:
            messages.error(request, "Code nicht gefunden.")
            return redirect("bewerbung:hr_einladungscodes")

        if aktion == "ausgeben" and code.status == EinladungsCode.STATUS_VERFUEGBAR:
            name = request.POST.get("ausgegeben_an_name", "").strip()
            telefon = request.POST.get("ausgegeben_an_telefon", "").strip()
            code.status = EinladungsCode.STATUS_AUSGEGEBEN
            code.ausgegeben_an_name = name
            code.ausgegeben_an_telefon = telefon
            code.ausgegeben_von = request.user
            code.ausgegeben_am = timezone.now()
            code.save()
            messages.success(request, f"Code {code.code} als ausgegeben markiert.")
        elif aktion == "zurueck" and code.status == EinladungsCode.STATUS_AUSGEGEBEN:
            code.status = EinladungsCode.STATUS_VERFUEGBAR
            code.ausgegeben_an_name = ""
            code.ausgegeben_an_telefon = ""
            code.ausgegeben_von = None
            code.ausgegeben_am = None
            code.save()
            messages.success(request, f"Code {code.code} wieder freigegeben.")

        return redirect("bewerbung:hr_einladungscodes")

    # Anzeige
    status_filter = request.GET.get("status", "")
    codes = EinladungsCode.objects.select_related("ausgegeben_von")
    if status_filter:
        codes = codes.filter(status=status_filter)

    anzahl = {
        "verfuegbar": EinladungsCode.objects.filter(status=EinladungsCode.STATUS_VERFUEGBAR).count(),
        "ausgegeben": EinladungsCode.objects.filter(status=EinladungsCode.STATUS_AUSGEGEBEN).count(),
        "verwendet": EinladungsCode.objects.filter(status=EinladungsCode.STATUS_VERWENDET).count(),
    }

    return render(request, "bewerbung/hr_einladungscodes.html", {
        "codes": codes,
        "status_filter": status_filter,
        "status_choices": EinladungsCode.STATUS_CHOICES,
        "anzahl": anzahl,
    })
