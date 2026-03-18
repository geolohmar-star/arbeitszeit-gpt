from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import JitsiRaum, MatrixRaum, SitzungsKalender, TeilnehmerTemplate


def _ist_staff(user):
    return user.is_staff


# ---------------------------------------------------------------------------
# Matrix-Raeume
# ---------------------------------------------------------------------------

@login_required
def raum_liste(request):
    """Uebersicht aller Matrix-Raeume."""
    raeume = MatrixRaum.objects.select_related("org_einheit", "teilnehmer_template")
    return render(request, "matrix_integration/raum_liste.html", {"raeume": raeume})


@login_required
@user_passes_test(_ist_staff)
def raum_anlegen(request):
    """Neuen Matrix-Raum anlegen."""
    templates = TeilnehmerTemplate.objects.all()
    from hr.models import OrgEinheit
    org_einheiten = OrgEinheit.objects.order_by("kuerzel")

    if request.method == "POST":
        raum = MatrixRaum.objects.create(
            name=request.POST.get("name", ""),
            typ=request.POST.get("typ", "manuell"),
            room_id=request.POST.get("room_id", ""),
            room_alias=request.POST.get("room_alias", ""),
            element_url=request.POST.get("element_url", ""),
            ping_typ=request.POST.get("ping_typ", ""),
            beschreibung=request.POST.get("beschreibung", ""),
            org_einheit_id=request.POST.get("org_einheit") or None,
            teilnehmer_template_id=request.POST.get("teilnehmer_template") or None,
        )
        return redirect("matrix_integration:raum_detail", pk=raum.pk)

    return render(request, "matrix_integration/raum_form.html", {
        "templates": templates,
        "org_einheiten": org_einheiten,
        "titel": "Neuen Matrix-Raum anlegen",
    })


@login_required
@user_passes_test(_ist_staff)
def raum_bearbeiten(request, pk):
    """Bestehenden Matrix-Raum bearbeiten."""
    raum = get_object_or_404(MatrixRaum, pk=pk)
    templates = TeilnehmerTemplate.objects.all()
    from hr.models import OrgEinheit
    org_einheiten = OrgEinheit.objects.order_by("kuerzel")

    if request.method == "POST":
        raum.name = request.POST.get("name", raum.name)
        raum.typ = request.POST.get("typ", raum.typ)
        raum.room_id = request.POST.get("room_id", "")
        raum.room_alias = request.POST.get("room_alias", "")
        raum.element_url = request.POST.get("element_url", "")
        raum.ping_typ = request.POST.get("ping_typ", "")
        raum.beschreibung = request.POST.get("beschreibung", "")
        raum.org_einheit_id = request.POST.get("org_einheit") or None
        raum.teilnehmer_template_id = request.POST.get("teilnehmer_template") or None
        raum.ist_aktiv = "ist_aktiv" in request.POST
        raum.save()
        return redirect("matrix_integration:raum_detail", pk=raum.pk)

    return render(request, "matrix_integration/raum_form.html", {
        "raum": raum,
        "templates": templates,
        "org_einheiten": org_einheiten,
        "titel": f"Raum bearbeiten: {raum.name}",
    })


@login_required
def raum_detail(request, pk):
    """Detail-Ansicht eines Matrix-Raums."""
    raum = get_object_or_404(MatrixRaum, pk=pk)
    return render(request, "matrix_integration/raum_detail.html", {"raum": raum})


@login_required
@user_passes_test(_ist_staff)
def raum_loeschen(request, pk):
    """Matrix-Raum loeschen."""
    raum = get_object_or_404(MatrixRaum, pk=pk)
    if request.method == "POST":
        raum.delete()
        return redirect("matrix_integration:raum_liste")
    return render(request, "matrix_integration/raum_loeschen.html", {"raum": raum})


# ---------------------------------------------------------------------------
# Teilnehmer-Templates
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(_ist_staff)
def template_liste(request):
    """Uebersicht aller Teilnehmer-Templates."""
    templates = TeilnehmerTemplate.objects.select_related("org_einheit").prefetch_related("mitglieder")
    return render(request, "matrix_integration/template_liste.html", {"templates": templates})


@login_required
@user_passes_test(_ist_staff)
def template_anlegen(request):
    """Neues Teilnehmer-Template anlegen."""
    from django.contrib.auth.models import User
    from hr.models import OrgEinheit
    org_einheiten = OrgEinheit.objects.order_by("kuerzel")
    alle_user = User.objects.filter(is_active=True).order_by("last_name", "first_name")

    if request.method == "POST":
        tmpl = TeilnehmerTemplate.objects.create(
            name=request.POST.get("name", ""),
            typ=request.POST.get("typ", "manuell"),
            beschreibung=request.POST.get("beschreibung", ""),
            org_einheit_id=request.POST.get("org_einheit") or None,
        )
        # Manuelle Mitglieder setzen
        mitglieder_ids = request.POST.getlist("mitglieder")
        if mitglieder_ids:
            tmpl.mitglieder.set(mitglieder_ids)
        return redirect("matrix_integration:template_liste")

    return render(request, "matrix_integration/template_form.html", {
        "org_einheiten": org_einheiten,
        "alle_user": alle_user,
        "titel": "Neues Teilnehmer-Template",
    })


@login_required
@user_passes_test(_ist_staff)
def template_loeschen(request, pk):
    """Teilnehmer-Template loeschen."""
    tmpl = get_object_or_404(TeilnehmerTemplate, pk=pk)
    if request.method == "POST":
        tmpl.delete()
        return redirect("matrix_integration:template_liste")
    return render(request, "matrix_integration/template_loeschen.html", {"tmpl": tmpl})


@login_required
@user_passes_test(_ist_staff)
def template_bearbeiten(request, pk):
    """Bestehendes Teilnehmer-Template bearbeiten."""
    from django.contrib.auth.models import User
    from hr.models import OrgEinheit
    tmpl = get_object_or_404(TeilnehmerTemplate, pk=pk)
    org_einheiten = OrgEinheit.objects.order_by("kuerzel")
    alle_user = User.objects.filter(is_active=True).order_by("last_name", "first_name")

    if request.method == "POST":
        tmpl.name = request.POST.get("name", tmpl.name)
        tmpl.typ = request.POST.get("typ", tmpl.typ)
        tmpl.beschreibung = request.POST.get("beschreibung", "")
        tmpl.org_einheit_id = request.POST.get("org_einheit") or None
        tmpl.save()
        mitglieder_ids = request.POST.getlist("mitglieder")
        tmpl.mitglieder.set(mitglieder_ids)
        return redirect("matrix_integration:template_liste")

    return render(request, "matrix_integration/template_form.html", {
        "tmpl": tmpl,
        "org_einheiten": org_einheiten,
        "alle_user": alle_user,
        "titel": f"Template bearbeiten: {tmpl.name}",
    })


# ---------------------------------------------------------------------------
# Sitzungs-Kalender
# ---------------------------------------------------------------------------

@login_required
def sitzung_liste(request):
    """Uebersicht aller Sitzungen."""
    sitzungen = SitzungsKalender.objects.select_related("matrix_raum", "teilnehmer_template")
    return render(request, "matrix_integration/sitzung_liste.html", {"sitzungen": sitzungen})


@login_required
@user_passes_test(_ist_staff)
def sitzung_anlegen(request):
    """Neue Sitzung anlegen."""
    raeume = MatrixRaum.objects.filter(ist_aktiv=True)
    templates = TeilnehmerTemplate.objects.all()

    if request.method == "POST":
        sitzung = SitzungsKalender.objects.create(
            name=request.POST.get("name", ""),
            beschreibung=request.POST.get("beschreibung", ""),
            matrix_raum_id=request.POST.get("matrix_raum"),
            teilnehmer_template_id=request.POST.get("teilnehmer_template") or None,
            von=request.POST.get("von"),
            bis=request.POST.get("bis"),
            start_datum=request.POST.get("start_datum"),
            ende_datum=request.POST.get("ende_datum") or None,
            ist_wiederkehrend="ist_wiederkehrend" in request.POST,
            wochentag=request.POST.get("wochentag") or None,
            erinnerung_minuten=request.POST.get("erinnerung_minuten", 15),
        )
        return redirect("matrix_integration:sitzung_liste")

    return render(request, "matrix_integration/sitzung_form.html", {
        "raeume": raeume,
        "templates": templates,
        "titel": "Neue Sitzung anlegen",
    })


@login_required
@user_passes_test(_ist_staff)
def sitzung_bearbeiten(request, pk):
    """Bestehende Sitzung bearbeiten."""
    sitzung = get_object_or_404(SitzungsKalender, pk=pk)
    raeume = MatrixRaum.objects.filter(ist_aktiv=True)
    templates = TeilnehmerTemplate.objects.all()

    if request.method == "POST":
        sitzung.name = request.POST.get("name", sitzung.name)
        sitzung.beschreibung = request.POST.get("beschreibung", "")
        sitzung.matrix_raum_id = request.POST.get("matrix_raum")
        sitzung.teilnehmer_template_id = request.POST.get("teilnehmer_template") or None
        sitzung.von = request.POST.get("von")
        sitzung.bis = request.POST.get("bis")
        sitzung.start_datum = request.POST.get("start_datum")
        sitzung.ende_datum = request.POST.get("ende_datum") or None
        sitzung.ist_wiederkehrend = "ist_wiederkehrend" in request.POST
        sitzung.wochentag = request.POST.get("wochentag") or None
        sitzung.erinnerung_minuten = request.POST.get("erinnerung_minuten", 15)
        sitzung.ist_aktiv = "ist_aktiv" in request.POST
        sitzung.save()
        return redirect("matrix_integration:sitzung_liste")

    return render(request, "matrix_integration/sitzung_form.html", {
        "sitzung": sitzung,
        "raeume": raeume,
        "templates": templates,
        "titel": f"Sitzung bearbeiten: {sitzung.name}",
    })


# ---------------------------------------------------------------------------
# Synapse API – Raum erstellen (AJAX)
# ---------------------------------------------------------------------------

@require_POST
@login_required
@user_passes_test(_ist_staff)
def synapse_raum_erstellen(request):
    """Erstellt einen neuen Raum auf dem Synapse-Server und gibt room_id + alias zurueck.

    POST-Parameter: name (Raumname), alias (optional, wird als room_alias_name verwendet)
    Antwort: JSON {room_id, room_alias} oder {fehler: ...}
    """
    from matrix_integration.synapse_service import erstelle_raum

    name = request.POST.get("name", "").strip()
    alias = request.POST.get("alias", "").strip()

    if not name:
        return JsonResponse({"fehler": "Name ist erforderlich."}, status=400)

    ergebnis = erstelle_raum(name=name, alias=alias or None)
    if not ergebnis:
        return JsonResponse(
            {"fehler": "Raum konnte nicht erstellt werden. Ist MATRIX_BOT_TOKEN konfiguriert?"},
            status=500,
        )

    # Den anfragenden User sofort einladen
    from matrix_integration.synapse_service import _matrix_user_id, einladen_in_raum
    matrix_id = _matrix_user_id(request.user.username)
    if matrix_id:
        einladen_in_raum(ergebnis["room_id"], matrix_id)

    return JsonResponse(ergebnis)


# ---------------------------------------------------------------------------
# Jitsi-Raeume
# ---------------------------------------------------------------------------

@login_required
def jitsi_liste(request):
    """Uebersicht aller Jitsi-Raeume."""
    raeume = JitsiRaum.objects.select_related("org_einheit")
    return render(request, "matrix_integration/jitsi_liste.html", {"raeume": raeume})


@login_required
@user_passes_test(_ist_staff)
def jitsi_anlegen(request):
    """Neuen Jitsi-Raum anlegen."""
    from hr.models import OrgEinheit
    org_einheiten = OrgEinheit.objects.order_by("kuerzel")

    if request.method == "POST":
        JitsiRaum.objects.create(
            name=request.POST.get("name", ""),
            raum_slug=request.POST.get("raum_slug", ""),
            beschreibung=request.POST.get("beschreibung", ""),
            org_einheit_id=request.POST.get("org_einheit") or None,
        )
        return redirect("matrix_integration:jitsi_liste")

    return render(request, "matrix_integration/jitsi_form.html", {
        "org_einheiten": org_einheiten,
        "titel": "Neuen Jitsi-Raum anlegen",
    })


@login_required
@user_passes_test(_ist_staff)
def jitsi_bearbeiten(request, pk):
    """Bestehenden Jitsi-Raum bearbeiten."""
    from hr.models import OrgEinheit
    raum = get_object_or_404(JitsiRaum, pk=pk)
    org_einheiten = OrgEinheit.objects.order_by("kuerzel")

    if request.method == "POST":
        raum.name = request.POST.get("name", raum.name)
        raum.raum_slug = request.POST.get("raum_slug", raum.raum_slug)
        raum.beschreibung = request.POST.get("beschreibung", "")
        raum.org_einheit_id = request.POST.get("org_einheit") or None
        raum.ist_aktiv = "ist_aktiv" in request.POST
        raum.save()
        return redirect("matrix_integration:jitsi_liste")

    return render(request, "matrix_integration/jitsi_form.html", {
        "raum": raum,
        "org_einheiten": org_einheiten,
        "titel": f"Jitsi-Raum bearbeiten: {raum.name}",
    })


@login_required
@user_passes_test(_ist_staff)
def jitsi_loeschen(request, pk):
    """Jitsi-Raum loeschen."""
    raum = get_object_or_404(JitsiRaum, pk=pk)
    if request.method == "POST":
        raum.delete()
        return redirect("matrix_integration:jitsi_liste")
    return render(request, "matrix_integration/jitsi_loeschen.html", {"raum": raum})


# ---------------------------------------------------------------------------
# Self-Service: Matrix-Passwort zuruecksetzen
# ---------------------------------------------------------------------------

@require_POST
@login_required
def matrix_passwort_reset_self(request):
    """Setzt das Matrix-Passwort des eingeloggten Users auf das Standardpasswort zurueck.

    Erreichbar fuer alle eingeloggten User (kein Staff erforderlich).
    Nach Abschluss Weiterleitung zur Matrix-Raum-Uebersicht.
    """
    from django.contrib import messages

    from matrix_integration.management.commands.matrix_passwort_setzen import (
        STANDARD_PASSWORT,
    )
    from matrix_integration.synapse_service import setze_matrix_passwort

    ok = setze_matrix_passwort(request.user.username, STANDARD_PASSWORT)
    if ok:
        messages.success(
            request,
            f"Dein Matrix-Passwort wurde auf '{STANDARD_PASSWORT}' zurueckgesetzt. "
            "Du kannst dich damit jetzt in Element anmelden.",
        )
    else:
        messages.error(
            request,
            "Matrix-Passwort konnte nicht zurueckgesetzt werden. "
            "Bitte Administrator kontaktieren.",
        )
    return redirect("matrix_integration:raum_liste")
