from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render

from .models import Bereich, Abteilung, HRMitarbeiter


def _ist_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(_ist_staff)
def mitarbeiter_liste(request):
    """Listet alle HR-Mitarbeiter mit Such- und Filtermoeglichkeit."""
    qs = HRMitarbeiter.objects.select_related(
        "abteilung", "team", "bereich", "vorgesetzter"
    )

    # Einfache Filter
    bereich_id = request.GET.get("bereich")
    abteilung_id = request.GET.get("abteilung")
    rolle = request.GET.get("rolle")
    suche = request.GET.get("q", "").strip()

    if bereich_id:
        qs = qs.filter(bereich_id=bereich_id)
    if abteilung_id:
        qs = qs.filter(abteilung_id=abteilung_id)
    if rolle:
        qs = qs.filter(rolle=rolle)
    if suche:
        qs = qs.filter(nachname__icontains=suche) | qs.filter(vorname__icontains=suche)

    return render(request, "hr/liste.html", {
        "mitarbeiter": qs,
        "bereiche": Bereich.objects.all(),
        "abteilungen": Abteilung.objects.select_related("bereich").all(),
        "rollen": HRMitarbeiter.ROLLE_CHOICES,
        "filter": {
            "bereich": bereich_id,
            "abteilung": abteilung_id,
            "rolle": rolle,
            "q": suche,
        },
    })


@login_required
@user_passes_test(_ist_staff)
def organigramm(request):
    """Zeigt die Organisationshierarchie."""
    bereiche = Bereich.objects.prefetch_related(
        "abteilungen__teams",
        "abteilungen__mitarbeiter",
        "mitarbeiter",
    ).all()

    return render(request, "hr/organigramm.html", {
        "bereiche": bereiche,
    })


@login_required
@user_passes_test(_ist_staff)
def mitarbeiter_detail(request, pk):
    """Zeigt Details eines HR-Mitarbeiters inkl. Stellvertreter."""
    ma = get_object_or_404(
        HRMitarbeiter.objects.select_related(
            "bereich", "abteilung", "team", "vorgesetzter", "stellvertretung_fuer"
        ),
        pk=pk,
    )
    direkte_berichte = ma.direkte_berichte.select_related("abteilung", "team")
    stellvertreter = ma.stellvertreter.select_related("abteilung")

    return render(request, "hr/detail.html", {
        "ma": ma,
        "direkte_berichte": direkte_berichte,
        "stellvertreter": stellvertreter,
    })
