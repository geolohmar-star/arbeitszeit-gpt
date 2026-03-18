import functools
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

logger = logging.getLogger(__name__)

from .forms import ITSystemForm, StatusMeldungForm, StatusMeldungSchliessenForm, WartungForm
from .models import ITStatusMeldung, ITSystem, ITWartung


def _helpdesk_required(view_func):
    """Dekorator: nur fuer Mitglieder der Gruppe 'it_helpdesk' zugaenglich."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not (
            request.user.is_staff
            or request.user.groups.filter(name="it_helpdesk").exists()
        ):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Oeffentliche Views (alle eingeloggten Nutzer)
# ---------------------------------------------------------------------------

@login_required
def uebersicht(request):
    """Statusuebersicht aller aktiven IT-Systeme."""
    jetzt = timezone.now()
    systeme = (
        ITSystem.objects
        .filter(aktiv=True)
        .prefetch_related("meldungen", "wartungen")
    )

    prioritaet = {
        ITSystem.STATUS_GESTOERT: 3,
        ITSystem.STATUS_WARNUNG:  2,
        ITSystem.STATUS_WARTUNG:  1,
        ITSystem.STATUS_OK:       0,
    }
    gesamt_status = ITSystem.STATUS_OK
    for s in systeme:
        if prioritaet.get(s.status, 0) > prioritaet.get(gesamt_status, 0):
            gesamt_status = s.status

    gesamt_farbe = {
        ITSystem.STATUS_OK:       "success",
        ITSystem.STATUS_WARNUNG:  "warning",
        ITSystem.STATUS_GESTOERT: "danger",
        ITSystem.STATUS_WARTUNG:  "secondary",
    }.get(gesamt_status, "secondary")

    naechste_wartungen = (
        ITWartung.objects
        .filter(ende__gte=jetzt)
        .select_related("system")
        .order_by("start")[:5]
    )

    ist_helpdesk = (
        request.user.is_staff
        or request.user.groups.filter(name="it_helpdesk").exists()
    )

    return render(request, "it_status/uebersicht.html", {
        "systeme":            systeme,
        "gesamt_status":      gesamt_status,
        "gesamt_farbe":       gesamt_farbe,
        "naechste_wartungen": naechste_wartungen,
        "jetzt":              jetzt,
        "ist_helpdesk":       ist_helpdesk,
    })


@login_required
def system_detail(request, pk):
    """Detailseite eines IT-Systems mit allen Meldungen und Wartungen."""
    system   = get_object_or_404(ITSystem, pk=pk, aktiv=True)
    jetzt    = timezone.now()
    meldungen = system.meldungen.select_related("erstellt_von").order_by("-erstellt_am")[:20]
    wartungen = system.wartungen.filter(ende__gte=jetzt).order_by("start")

    ist_helpdesk = (
        request.user.is_staff
        or request.user.groups.filter(name="it_helpdesk").exists()
    )

    return render(request, "it_status/system_detail.html", {
        "system":       system,
        "meldungen":    meldungen,
        "wartungen":    wartungen,
        "jetzt":        jetzt,
        "ist_helpdesk": ist_helpdesk,
    })


# ---------------------------------------------------------------------------
# Helpdesk-Views (nur Gruppe it_helpdesk oder Staff)
# ---------------------------------------------------------------------------

@_helpdesk_required
def meldung_neu(request):
    """Neue Statusmeldung anlegen."""
    form = StatusMeldungForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        meldung = form.save(commit=False)
        meldung.erstellt_von = request.user
        meldung.save()
        # Systemstatus sofort aktualisieren
        meldung.system.status = meldung.status
        meldung.system.save(update_fields=["status"])
        # Workflow starten (Postbote: E-Mail + Matrix) – falls konfiguriert
        # Der generische Signal-Handler in workflow/signals.py uebernimmt das
        # automatisch sobald ein aktiver Trigger 'it_stoerung_gemeldet' existiert.
        messages.success(request, "Meldung gespeichert.")
        return redirect("it_status:uebersicht")

    return render(request, "it_status/meldung_form.html", {"form": form, "titel": "Neue Meldung"})


@_helpdesk_required
def meldung_schliessen(request, pk):
    """Meldung als geloest markieren und Systemstatus auf OK setzen."""
    meldung = get_object_or_404(ITStatusMeldung, pk=pk)
    form    = StatusMeldungSchliessenForm(request.POST or None, instance=meldung)
    if request.method == "POST" and form.is_valid():
        form.save()
        # Systemstatus auf OK zuruecksetzen wenn keine offenen Meldungen mehr
        offene = meldung.system.meldungen.filter(geloest_am__isnull=True).exists()
        if not offene:
            meldung.system.status = ITSystem.STATUS_OK
            meldung.system.save(update_fields=["status"])
        messages.success(request, "Meldung geschlossen.")
        return redirect("it_status:system_detail", pk=meldung.system.pk)

    return render(request, "it_status/meldung_schliessen.html", {
        "form":    form,
        "meldung": meldung,
    })


@_helpdesk_required
def wartung_neu(request):
    """Neues Wartungsfenster anlegen."""
    form = WartungForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        wartung = form.save(commit=False)
        wartung.erstellt_von = request.user
        wartung.save()
        messages.success(request, "Wartungsfenster gespeichert.")
        return redirect("it_status:uebersicht")

    return render(request, "it_status/wartung_form.html", {"form": form, "titel": "Neues Wartungsfenster"})


@_helpdesk_required
def wartung_loeschen(request, pk):
    """Wartungsfenster loeschen."""
    wartung = get_object_or_404(ITWartung, pk=pk)
    if request.method == "POST":
        system_pk = wartung.system.pk
        wartung.delete()
        messages.success(request, "Wartungsfenster geloescht.")
        return redirect("it_status:system_detail", pk=system_pk)

    return render(request, "it_status/wartung_loeschen.html", {"wartung": wartung})


@_helpdesk_required
def system_neu(request):
    """Neues IT-System anlegen."""
    form = ITSystemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "System gespeichert.")
        return redirect("it_status:uebersicht")
    return render(request, "it_status/system_form.html", {"form": form, "titel": "Neues System"})


@_helpdesk_required
def system_bearbeiten(request, pk):
    """Bestehendes IT-System bearbeiten."""
    system = get_object_or_404(ITSystem, pk=pk)
    form = ITSystemForm(request.POST or None, instance=system)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "System gespeichert.")
        return redirect("it_status:system_detail", pk=pk)
    return render(request, "it_status/system_form.html", {"form": form, "titel": system.bezeichnung, "system": system})


@_helpdesk_required
def system_loeschen(request, pk):
    """IT-System loeschen (nur wenn keine offenen Meldungen)."""
    system = get_object_or_404(ITSystem, pk=pk)
    if request.method == "POST":
        system.delete()
        messages.success(request, "System geloescht.")
        return redirect("it_status:uebersicht")
    return render(request, "it_status/system_loeschen.html", {"system": system})


@_helpdesk_required
def system_status_aendern(request, pk):
    """Status eines Systems direkt aendern (POST-only)."""
    system = get_object_or_404(ITSystem, pk=pk)
    if request.method == "POST":
        neuer_status = request.POST.get("status")
        if neuer_status in dict(ITSystem.STATUS_CHOICES):
            system.status = neuer_status
            system.save(update_fields=["status"])
            messages.success(request, f"Status fuer {system.bezeichnung} geaendert.")
    return redirect("it_status:system_detail", pk=pk)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

