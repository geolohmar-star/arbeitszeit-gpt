from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Permission
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from guardian.shortcuts import assign_perm, remove_perm, get_users_with_perms

from arbeitszeit.models import Mitarbeiter
from .models import BerechtigungsProtokoll


# Verfuegbare Objekt-Permissions fuer Mitarbeiter
# (codename, lesbare Bezeichnung)
VERFUEGBARE_PERMISSIONS = [
    ("view_zeiterfassung", "Zeiterfassung einsehen"),
    ("genehmigen_antraege", "Antraege genehmigen/ablehnen"),
    ("view_stammdaten", "Stammdaten einsehen"),
    ("view_mitarbeiter", "Mitarbeiterdetails sehen"),
    ("change_mitarbeiter", "Mitarbeiterdaten bearbeiten"),
]


def _ist_berechtigungsadmin(user):
    """Prueft ob der User die Berechtigungsverwaltung nutzen darf."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(_ist_berechtigungsadmin)
def uebersicht(request):
    """Listet alle Mitarbeiter mit einem Ueberblick ihrer Berechtigten."""
    mitarbeiter_liste = Mitarbeiter.objects.select_related("user").order_by(
        "nachname", "vorname"
    )

    # Fuer jeden Mitarbeiter: wer hat Rechte?
    mitarbeiter_mit_berechtigten = []
    for ma in mitarbeiter_liste:
        berechtigte = get_users_with_perms(
            ma, attach_perms=False, with_group_users=False
        )
        mitarbeiter_mit_berechtigten.append({
            "mitarbeiter": ma,
            "anzahl_berechtigte": berechtigte.count(),
        })

    return render(request, "berechtigungen/uebersicht.html", {
        "mitarbeiter_liste": mitarbeiter_mit_berechtigten,
    })


@login_required
@user_passes_test(_ist_berechtigungsadmin)
def mitarbeiter_detail(request, pk):
    """Zeigt und verwaltet die Berechtigungen fuer einen Mitarbeiter."""
    mitarbeiter = get_object_or_404(Mitarbeiter, pk=pk)

    # Alle User mit ihren Permissions auf diesem Objekt
    users_mit_perms = get_users_with_perms(
        mitarbeiter,
        attach_perms=True,
        with_group_users=False,
    )

    # Alle User ohne Mitarbeiter selbst fuer das Vergabe-Formular
    alle_user = User.objects.filter(is_active=True).exclude(
        pk=mitarbeiter.user_id
    ).order_by("last_name", "first_name")

    return render(request, "berechtigungen/detail.html", {
        "mitarbeiter": mitarbeiter,
        "users_mit_perms": users_mit_perms,
        "alle_user": alle_user,
        "verfuegbare_permissions": VERFUEGBARE_PERMISSIONS,
    })


@login_required
@user_passes_test(_ist_berechtigungsadmin)
def permission_vergeben(request, pk):
    """Vergibt eine Objekt-Permission auf einen Mitarbeiter an einen User."""
    if request.method != "POST":
        return redirect("berechtigungen:detail", pk=pk)

    mitarbeiter = get_object_or_404(Mitarbeiter, pk=pk)
    user_id = request.POST.get("user_id")
    perm_codename = request.POST.get("permission")
    bemerkung = request.POST.get("bemerkung", "")

    # Validierung
    erlaubte_codenames = [p[0] for p in VERFUEGBARE_PERMISSIONS]
    if perm_codename not in erlaubte_codenames:
        messages.error(request, "Unbekannte Berechtigung.")
        return redirect("berechtigungen:detail", pk=pk)

    try:
        ziel_user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        messages.error(request, "Nutzer nicht gefunden.")
        return redirect("berechtigungen:detail", pk=pk)

    # Berechtigung via guardian zuweisen
    assign_perm(perm_codename, ziel_user, mitarbeiter)

    # Protokoll schreiben
    BerechtigungsProtokoll.objects.create(
        aktion="vergeben",
        permission_codename=perm_codename,
        ziel_mitarbeiter=mitarbeiter,
        berechtigter_user=ziel_user,
        durchgefuehrt_von=request.user,
        bemerkung=bemerkung,
    )

    perm_label = dict(VERFUEGBARE_PERMISSIONS).get(perm_codename, perm_codename)
    messages.success(
        request,
        f"Berechtigung '{perm_label}' wurde an "
        f"{ziel_user.get_full_name() or ziel_user.username} vergeben.",
    )
    return redirect("berechtigungen:detail", pk=pk)


@login_required
@user_passes_test(_ist_berechtigungsadmin)
def permission_entziehen(request, pk):
    """Entzieht eine Objekt-Permission auf einen Mitarbeiter von einem User."""
    if request.method != "POST":
        return redirect("berechtigungen:detail", pk=pk)

    mitarbeiter = get_object_or_404(Mitarbeiter, pk=pk)
    user_id = request.POST.get("user_id")
    perm_codename = request.POST.get("permission")

    try:
        ziel_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, "Nutzer nicht gefunden.")
        return redirect("berechtigungen:detail", pk=pk)

    # Berechtigung entziehen
    remove_perm(perm_codename, ziel_user, mitarbeiter)

    # Protokoll schreiben
    BerechtigungsProtokoll.objects.create(
        aktion="entzogen",
        permission_codename=perm_codename,
        ziel_mitarbeiter=mitarbeiter,
        berechtigter_user=ziel_user,
        durchgefuehrt_von=request.user,
    )

    perm_label = dict(VERFUEGBARE_PERMISSIONS).get(perm_codename, perm_codename)
    messages.success(
        request,
        f"Berechtigung '{perm_label}' wurde von "
        f"{ziel_user.get_full_name() or ziel_user.username} entzogen.",
    )
    return redirect("berechtigungen:detail", pk=pk)


@login_required
@user_passes_test(_ist_berechtigungsadmin)
def protokoll(request):
    """Zeigt den vollstaendigen Audit-Trail aller Berechtigungsaenderungen."""
    # Optionale Filter
    ma_filter = request.GET.get("mitarbeiter")
    aktion_filter = request.GET.get("aktion")

    eintraege = BerechtigungsProtokoll.objects.select_related(
        "ziel_mitarbeiter",
        "berechtigter_user",
        "durchgefuehrt_von",
    )

    if ma_filter:
        eintraege = eintraege.filter(ziel_mitarbeiter_id=ma_filter)
    if aktion_filter in ("vergeben", "entzogen"):
        eintraege = eintraege.filter(aktion=aktion_filter)

    mitarbeiter_liste = Mitarbeiter.objects.order_by("nachname", "vorname")

    return render(request, "berechtigungen/protokoll.html", {
        "eintraege": eintraege[:200],
        "mitarbeiter_liste": mitarbeiter_liste,
        "ma_filter": ma_filter,
        "aktion_filter": aktion_filter,
        "verfuegbare_permissions": VERFUEGBARE_PERMISSIONS,
    })
