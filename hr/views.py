import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    Abteilung,
    Bereich,
    HierarchieSnapshot,
    HRMitarbeiter,
    OrgEinheit,
    Stelle,
)

logger = logging.getLogger(__name__)


def _ist_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _suche_mitarbeiter(qs, suche):
    """Volltextsuche ueber HRMitarbeiter-Felder.

    Auf PostgreSQL: SearchVector mit Ranking (FTS).
    Fallback fuer SQLite: einfaches icontains.
    """
    from django.db import connection
    from django.db.models import Q

    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
        vector = SearchVector(
            "vorname", "nachname", "personalnummer", "email",
            config="simple",  # simple: kein Stemming - besser fuer Eigennamen
        )
        query = SearchQuery(suche, config="simple", search_type="plain")

        # FTS auf direkten Feldern
        qs_fts = qs.annotate(rank=SearchRank(vector, query)).filter(rank__gt=0)

        # Zusaetzlich: Stelle (kuerzel + bezeichnung) per icontains
        qs_stelle = qs.filter(
            Q(stelle__kuerzel__icontains=suche)
            | Q(stelle__bezeichnung__icontains=suche)
        )

        return (qs_fts | qs_stelle).distinct().order_by("-rank", "nachname")

    # Fallback fuer lokale SQLite-Entwicklung
    return qs.filter(
        Q(nachname__icontains=suche)
        | Q(vorname__icontains=suche)
        | Q(personalnummer__icontains=suche)
        | Q(email__icontains=suche)
        | Q(stelle__kuerzel__icontains=suche)
        | Q(stelle__bezeichnung__icontains=suche)
    ).distinct()


@login_required
@user_passes_test(_ist_staff)
def mitarbeiter_liste(request):
    """Listet alle HR-Mitarbeiter mit Such- und Filtermoeglichkeit.

    Unterstuetzt HTMX-Live-Suche: bei HX-Request wird nur die Tabelle zurueckgegeben.
    """
    qs = HRMitarbeiter.objects.select_related(
        "abteilung", "team", "bereich", "vorgesetzter", "stelle"
    )

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
        qs = _suche_mitarbeiter(qs, suche)
    else:
        qs = qs.order_by("nachname", "vorname")

    context = {
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
    }

    # HTMX-Request: nur Tabellen-Partial zurueckgeben
    if request.headers.get("HX-Request"):
        return render(request, "hr/partials/_mitarbeiter_tabelle.html", context)

    return render(request, "hr/liste.html", context)


@login_required
@user_passes_test(_ist_staff)
def organigramm(request):
    """Uebersichtsseite fuer alle Organigramm- und Builder-Optionen."""
    from formulare.models import TeamQueue

    # Statistiken
    orgeinheiten_count = OrgEinheit.objects.count()
    stellen_count = Stelle.objects.count()
    stellen_besetzt = Stelle.objects.filter(hrmitarbeiter__isnull=False).count()
    mitarbeiter_count = HRMitarbeiter.objects.count()
    teams_count = TeamQueue.objects.count()

    return render(request, "hr/organigramm_hub.html", {
        "orgeinheiten_count": orgeinheiten_count,
        "stellen_count": stellen_count,
        "stellen_besetzt": stellen_besetzt,
        "mitarbeiter_count": mitarbeiter_count,
        "teams_count": teams_count,
    })


@login_required
@user_passes_test(_ist_staff)
def organigramm_karten(request):
    """Zeigt die Organisationshierarchie als Karten basierend auf OrgEinheiten und Stellen."""
    # Lade nur Root-OrgEinheiten (ohne uebergeordnete)
    # Untereinheiten und Stellen werden im Template rekursiv gerendert
    root_orgeinheiten = OrgEinheit.objects.filter(
        uebergeordnet__isnull=True
    ).prefetch_related(
        'untereinheiten',
        'stellen__hrmitarbeiter',
        'stellen__untergeordnete_stellen'
    ).order_by('kuerzel')

    return render(request, "hr/organigramm.html", {
        "root_orgeinheiten": root_orgeinheiten,
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


# ============================================================================
# STELLEN-MANAGEMENT
# ============================================================================


@login_required
@user_passes_test(_ist_staff)
def stellen_uebersicht(request):
    """Feature 1: Liste aller Stellen mit Hierarchie und Filter."""
    qs = Stelle.objects.select_related(
        "org_einheit", "uebergeordnete_stelle", "delegiert_an"
    ).prefetch_related("hrmitarbeiter")

    # Filter nach OrgEinheit
    org_filter = request.GET.get("org")
    if org_filter:
        qs = qs.filter(org_einheit__kuerzel=org_filter)

    # Filter nach Besetzt/Unbesetzt
    besetzt_filter = request.GET.get("besetzt")
    if besetzt_filter == "ja":
        qs = qs.filter(hrmitarbeiter__isnull=False)
    elif besetzt_filter == "nein":
        qs = qs.filter(hrmitarbeiter__isnull=True)

    # Hierarchisch sortieren: erst nach org_einheit, dann kuerzel
    stellen = qs.order_by("org_einheit__kuerzel", "kuerzel")

    return render(request, "hr/stellen_uebersicht.html", {
        "stellen": stellen,
        "org_einheiten": OrgEinheit.objects.all(),
        "filter": {
            "org": org_filter,
            "besetzt": besetzt_filter,
        },
    })


@login_required
@user_passes_test(_ist_staff)
def stelle_bearbeiten(request, pk=None):
    """Feature 2: Stelle anlegen oder bearbeiten."""
    stelle = get_object_or_404(Stelle, pk=pk) if pk else None

    if request.method == "POST":
        # Felder aus POST holen
        kuerzel = request.POST.get("kuerzel", "").strip()
        bezeichnung = request.POST.get("bezeichnung", "").strip()
        org_einheit_id = request.POST.get("org_einheit")
        uebergeordnete_stelle_id = request.POST.get("uebergeordnete_stelle") or None
        delegiert_an_id = request.POST.get("delegiert_an") or None
        max_urlaubstage = request.POST.get("max_urlaubstage_genehmigung") or 0
        eskalation_tage = request.POST.get("eskalation_nach_tagen") or 3

        # Validierung
        if not kuerzel or not bezeichnung or not org_einheit_id:
            messages.error(request, "Kuerzel, Bezeichnung und OrgEinheit sind Pflichtfelder.")
        else:
            # Speichern
            if stelle:
                stelle.kuerzel = kuerzel
                stelle.bezeichnung = bezeichnung
                stelle.org_einheit_id = org_einheit_id
                stelle.uebergeordnete_stelle_id = uebergeordnete_stelle_id
                stelle.delegiert_an_id = delegiert_an_id
                stelle.max_urlaubstage_genehmigung = int(max_urlaubstage)
                stelle.eskalation_nach_tagen = int(eskalation_tage)
                stelle.save()
                messages.success(request, f"Stelle {kuerzel} aktualisiert.")
            else:
                stelle = Stelle.objects.create(
                    kuerzel=kuerzel,
                    bezeichnung=bezeichnung,
                    org_einheit_id=org_einheit_id,
                    uebergeordnete_stelle_id=uebergeordnete_stelle_id,
                    delegiert_an_id=delegiert_an_id,
                    max_urlaubstage_genehmigung=int(max_urlaubstage),
                    eskalation_nach_tagen=int(eskalation_tage),
                )
                messages.success(request, f"Stelle {kuerzel} angelegt.")
            return redirect("hr:stellen_uebersicht")

    # Andere Stellen für uebergeordnete_stelle und delegiert_an
    andere_stellen = Stelle.objects.exclude(pk=pk) if pk else Stelle.objects.all()

    return render(request, "hr/stelle_bearbeiten.html", {
        "stelle": stelle,
        "org_einheiten": OrgEinheit.objects.all(),
        "andere_stellen": andere_stellen.select_related("org_einheit"),
    })


@login_required
@user_passes_test(_ist_staff)
def mitarbeiter_stelle_zuweisen(request, pk):
    """Feature 3: Stelle einem HRMitarbeiter zuweisen."""
    hrm = get_object_or_404(HRMitarbeiter, pk=pk)

    if request.method == "POST":
        stelle_id = request.POST.get("stelle") or None
        if stelle_id:
            stelle = get_object_or_404(Stelle, pk=stelle_id)
            # Pruefen ob Stelle schon besetzt
            if stelle.ist_besetzt and stelle.hrmitarbeiter != hrm:
                messages.warning(
                    request,
                    f"Stelle {stelle.kuerzel} ist bereits durch "
                    f"{stelle.hrmitarbeiter.vollname} besetzt."
                )
            else:
                hrm.stelle = stelle
                hrm.save(update_fields=["stelle"])
                messages.success(
                    request,
                    f"{hrm.vollname} wurde Stelle {stelle.kuerzel} zugewiesen."
                )
        else:
            # Stelle entfernen
            hrm.stelle = None
            hrm.save(update_fields=["stelle"])
            messages.success(request, f"{hrm.vollname}: Stelle entfernt.")
        return redirect("hr:detail", pk=hrm.pk)

    # Verfuegbare Stellen (unbesetzt oder die aktuelle Stelle des Mitarbeiters)
    alle_stellen = Stelle.objects.select_related("org_einheit", "hrmitarbeiter")

    return render(request, "hr/mitarbeiter_stelle_zuweisen.html", {
        "hrm": hrm,
        "alle_stellen": alle_stellen,
    })


@login_required
@user_passes_test(_ist_staff)
def stelle_quick_zuweisen(request, pk):
    """HTMX-View: Schnellzuweisung eines Mitarbeiters zu einer Stelle direkt im Organigramm.

    GET  -> gibt das Zuweis-Formular als Partial zurueck
    POST -> speichert Zuweisung und gibt aktualisiertes Badge + leeres Formular zurueck
    """
    stelle = get_object_or_404(Stelle, pk=pk)

    if request.method == "POST":
        hrm_id = request.POST.get("hrm_id") or None

        if hrm_id:
            hrm = get_object_or_404(HRMitarbeiter, pk=hrm_id)
            # Alte Zuweisung loesen falls die Stelle schon besetzt ist
            if stelle.ist_besetzt and stelle.hrmitarbeiter != hrm:
                alter_inhaber = stelle.hrmitarbeiter
                alter_inhaber.stelle = None
                alter_inhaber.save(update_fields=["stelle"])
            hrm.stelle = stelle
            hrm.save(update_fields=["stelle"])
        else:
            # Mitarbeiter von Stelle entfernen
            if stelle.ist_besetzt:
                inhaber = stelle.hrmitarbeiter
                inhaber.stelle = None
                inhaber.save(update_fields=["stelle"])

        # Stelle neu laden damit ist_besetzt aktuell ist
        stelle.refresh_from_db()

        return render(request, "hr/partials/_stelle_quick_zuweisen.html", {
            "stelle": stelle,
            "alle_hrm": HRMitarbeiter.objects.select_related("stelle").order_by("nachname", "vorname"),
            "gespeichert": True,
        })

    # GET ?reset=1 -> nur Trigger-Button zurueckgeben (Abbrechen)
    if request.GET.get("reset"):
        return render(request, "hr/partials/_stelle_zuweis_trigger.html", {"stelle": stelle})

    # GET: Formular anzeigen
    alle_hrm = HRMitarbeiter.objects.select_related("stelle").order_by("nachname", "vorname")
    return render(request, "hr/partials/_stelle_quick_zuweisen.html", {
        "stelle": stelle,
        "alle_hrm": alle_hrm,
        "gespeichert": False,
    })


@login_required
@user_passes_test(_ist_staff)
def stellen_organigramm(request):
    """Feature 4: Visuelle Hierarchie basierend auf OrgEinheiten."""
    import json

    def orgeinheit_to_dict(orgeinheit):
        """Konvertiert eine OrgEinheit in D3 Tree Format."""
        data = {
            "id": f"org_{orgeinheit.pk}",
            "name": orgeinheit.kuerzel,
            "title": orgeinheit.bezeichnung,
            "className": "node-orgeinheit",
            "extra": {
                "typ": "orgeinheit",
                "stellen_count": orgeinheit.stellen.count(),
                "ist_reserviert": orgeinheit.ist_reserviert,
            },
        }

        # Sammle Kinder: Untergeordnete OrgEinheiten + Root-Stellen
        children = []

        # 1. Untergeordnete OrgEinheiten
        for untereinheit in orgeinheit.untereinheiten.all():
            children.append(orgeinheit_to_dict(untereinheit))

        # 2. Root-Stellen dieser OrgEinheit (ohne uebergeordnete_stelle)
        root_stellen = orgeinheit.stellen.filter(uebergeordnete_stelle__isnull=True)
        for stelle in root_stellen:
            children.append(stelle_to_dict(stelle))

        if children:
            data["children"] = children

        return data

    def stelle_to_dict(stelle):
        """Konvertiert eine Stelle in D3 Tree Format."""
        data = {
            "id": f"stelle_{stelle.pk}",
            "name": stelle.kuerzel,
            "title": stelle.bezeichnung,
            "className": f"node-{stelle.kuerzel[:2].lower()}",
            "extra": {
                "typ": "stelle",
                "org": stelle.org_einheit.kuerzel,
                "email": stelle.email,
                "besetzt": stelle.ist_besetzt,
                "inhaber": stelle.aktueller_inhaber.vollname if stelle.ist_besetzt else "Unbesetzt",
                "inhaber_url": f"/hr/{stelle.aktueller_inhaber.pk}/" if stelle.ist_besetzt else None,
                "edit_url": f"/hr/stellen/{stelle.pk}/bearbeiten/",
            },
        }

        # Delegation/Vertretung
        if stelle.delegiert_an:
            data["extra"]["delegiert_an"] = stelle.delegiert_an.kuerzel
        if stelle.vertreten_durch:
            data["extra"]["vertreten_durch"] = stelle.vertreten_durch.kuerzel

        # Rekursiv untergeordnete Stellen hinzufuegen
        untergeordnete = stelle.untergeordnete_stellen.select_related(
            "org_einheit"
        ).prefetch_related("untergeordnete_stellen")

        if untergeordnete.exists():
            data["children"] = [stelle_to_dict(kind) for kind in untergeordnete]

        return data

    # Root-OrgEinheiten (ohne uebergeordnete)
    root_orgeinheiten = OrgEinheit.objects.filter(
        uebergeordnet__isnull=True
    ).prefetch_related(
        'untereinheiten',
        'stellen__untergeordnete_stellen'
    ).order_by('kuerzel')

    # Konvertiere zu D3 Tree Format
    orgchart_data = []
    for orgeinheit in root_orgeinheiten:
        orgchart_data.append(orgeinheit_to_dict(orgeinheit))

    return render(
        request,
        "hr/stellen_organigramm.html",
        {
            "orgchart_data_json": json.dumps(orgchart_data, ensure_ascii=False),
        },
    )


@login_required
@user_passes_test(_ist_staff)
def delegation_verwalten(request):
    """Feature 5: Delegation und Vertretung verwalten."""
    if request.method == "POST":
        stelle_id = request.POST.get("stelle_id")
        aktion = request.POST.get("aktion")

        if not stelle_id:
            messages.error(request, "Keine Stelle ausgewaehlt.")
            return redirect("hr:delegation_verwalten")

        stelle = get_object_or_404(Stelle, pk=stelle_id)

        if aktion == "delegation_setzen":
            delegiert_an_id = request.POST.get("delegiert_an")
            if delegiert_an_id:
                stelle.delegiert_an_id = delegiert_an_id
                stelle.save(update_fields=["delegiert_an"])
                messages.success(
                    request,
                    f"Delegation fuer {stelle.kuerzel} gesetzt."
                )
            else:
                messages.error(request, "Keine Ziel-Stelle ausgewaehlt.")

        elif aktion == "delegation_entfernen":
            stelle.delegiert_an = None
            stelle.save(update_fields=["delegiert_an"])
            messages.success(request, f"Delegation fuer {stelle.kuerzel} entfernt.")

        elif aktion == "vertretung_setzen":
            vertreten_durch_id = request.POST.get("vertreten_durch")
            von = request.POST.get("vertretung_von")
            bis = request.POST.get("vertretung_bis")

            if vertreten_durch_id and von and bis:
                stelle.vertreten_durch_id = vertreten_durch_id
                stelle.vertretung_von = von
                stelle.vertretung_bis = bis
                stelle.save(update_fields=[
                    "vertreten_durch", "vertretung_von", "vertretung_bis"
                ])
                messages.success(
                    request,
                    f"Vertretung fuer {stelle.kuerzel} gesetzt ({von} bis {bis})."
                )
            else:
                messages.error(request, "Alle Felder muessen ausgefuellt sein.")

        elif aktion == "vertretung_entfernen":
            stelle.vertreten_durch = None
            stelle.vertretung_von = None
            stelle.vertretung_bis = None
            stelle.save(update_fields=[
                "vertreten_durch", "vertretung_von", "vertretung_bis"
            ])
            messages.success(request, f"Vertretung fuer {stelle.kuerzel} entfernt.")

        return redirect("hr:delegation_verwalten")

    # Alle Stellen mit aktuellen Delegations-/Vertretungsinformationen
    stellen = Stelle.objects.select_related(
        "org_einheit", "delegiert_an", "vertreten_durch"
    ).order_by("org_einheit__kuerzel", "kuerzel")

    return render(request, "hr/delegation_verwalten.html", {
        "stellen": stellen,
    })


# === Company Builder Views ===

@login_required
@user_passes_test(_ist_staff)
def company_builder(request):
    """Visueller Company Builder mit Drag & Drop."""
    from django.db.models import Count

    # Nur Root-OrgEinheiten laden (ohne uebergeordnete Einheit)
    # Untereinheiten werden im Template rekursiv gerendert
    orgeinheiten = OrgEinheit.objects.filter(
        uebergeordnet__isnull=True
    ).prefetch_related('stellen', 'untereinheiten').order_by('kuerzel')

    stellen = Stelle.objects.select_related('org_einheit').order_by('kuerzel')
    mitarbeiter = HRMitarbeiter.objects.filter(stelle__isnull=False).count()

    return render(request, 'hr/company_builder.html', {
        'orgeinheiten': orgeinheiten,
        'stellen': stellen,
        'mitarbeiter': mitarbeiter,
    })


@login_required
@user_passes_test(_ist_staff)
def company_builder_preview(request):
    """Organigramm-Preview Seite fuer Company Builder."""
    return render(request, 'hr/company_builder_preview.html')


@login_required
@user_passes_test(_ist_staff)
def company_builder_neue_orgeinheit(request):
    """HTMX: Form fuer neue OrgEinheit."""
    if request.method == 'POST':
        kuerzel = request.POST.get('kuerzel')
        bezeichnung = request.POST.get('bezeichnung')
        
        if kuerzel and bezeichnung:
            orgeinheit = OrgEinheit.objects.create(
                kuerzel=kuerzel.upper(),
                bezeichnung=bezeichnung
            )
            messages.success(request, f'OrgEinheit {kuerzel} erstellt!')
            
            # Reload Builder Canvas
            orgeinheiten = OrgEinheit.objects.prefetch_related('stellen').order_by('kuerzel')
            return render(request, 'hr/partials/_builder_canvas.html', {
                'orgeinheiten': orgeinheiten
            })
    
    return render(request, 'hr/partials/_form_orgeinheit.html')


@login_required
@user_passes_test(_ist_staff)
def company_builder_neue_stelle(request):
    """HTMX: Form fuer neue Stelle."""
    orgeinheit_id = request.GET.get('orgeinheit_id')
    
    if request.method == 'POST':
        kuerzel = request.POST.get('kuerzel')
        bezeichnung = request.POST.get('bezeichnung')
        orgeinheit_id = request.POST.get('orgeinheit_id')
        
        if kuerzel and bezeichnung and orgeinheit_id:
            orgeinheit = OrgEinheit.objects.get(id=orgeinheit_id)
            stelle = Stelle.objects.create(
                kuerzel=kuerzel.lower(),
                bezeichnung=bezeichnung,
                org_einheit=orgeinheit
            )
            messages.success(request, f'Stelle {kuerzel} erstellt!')
            
            # Reload OrgEinheit
            return render(request, 'hr/partials/_builder_orgeinheit.html', {
                'orgeinheit': orgeinheit
            })
    
    orgeinheiten = OrgEinheit.objects.order_by('kuerzel')
    return render(request, 'hr/partials/_form_stelle.html', {
        'orgeinheiten': orgeinheiten,
        'orgeinheit_id': orgeinheit_id
    })


@login_required
@user_passes_test(_ist_staff)
def company_builder_neuer_mitarbeiter(request):
    """HTMX: Form fuer neuen HRMitarbeiter."""
    if request.method == 'POST':
        vorname = request.POST.get('vorname')
        nachname = request.POST.get('nachname')
        email = request.POST.get('email', '')
        rolle = request.POST.get('rolle', 'mitarbeiter')
        stelle_id = request.POST.get('stelle_id')

        if vorname and nachname:
            try:
                # Erstelle HRMitarbeiter (Personalnummer wird automatisch vergeben)
                mitarbeiter_data = {
                    'vorname': vorname,
                    'nachname': nachname,
                    'email': email,
                    'rolle': rolle,
                }

                # Stelle zuweisen falls angegeben
                if stelle_id:
                    stelle = Stelle.objects.get(id=stelle_id)
                    mitarbeiter_data['stelle'] = stelle

                mitarbeiter = HRMitarbeiter.objects.create(**mitarbeiter_data)
                messages.success(request, f'Mitarbeiter {vorname} {nachname} erstellt!')

                # Reload Builder Canvas
                orgeinheiten = OrgEinheit.objects.prefetch_related('stellen').order_by('kuerzel')
                return render(request, 'hr/partials/_builder_canvas.html', {
                    'orgeinheiten': orgeinheiten
                })
            except Exception as e:
                messages.error(request, f'Fehler beim Erstellen: {str(e)}')

    # GET Request: Formular anzeigen
    stellen = Stelle.objects.select_related('org_einheit').order_by('kuerzel')
    return render(request, 'hr/partials/_form_mitarbeiter.html', {
        'stellen': stellen,
        'rolle_choices': HRMitarbeiter.ROLLE_CHOICES
    })


@login_required
@user_passes_test(_ist_staff)
def company_builder_hierarchie_update(request):
    """HTMX: Update Hierarchie nach Drag & Drop.

    Erwartet JSON-Struktur:
    {
        "orgeinheiten": [
            {"id": "1", "parent_id": null, "stellen": [...]},
            {"id": "2", "parent_id": "1", "stellen": [...]}
        ],
        "stellen": [
            {"id": "10", "parent_stelle_id": null, "org_einheit_id": "1"},
            {"id": "11", "parent_stelle_id": "10", "org_einheit_id": "1"}
        ]
    }
    """
    import json
    from django.db import transaction
    from django.http import JsonResponse

    if request.method == 'POST':
        structure_json = request.POST.get('structure')
        if not structure_json:
            return JsonResponse({'status': 'error', 'message': 'Keine Struktur ubergeben'})

        try:
            data = json.loads(structure_json)

            with transaction.atomic():
                # 1. OrgEinheiten aktualisieren
                for org_data in data.get('orgeinheiten', []):
                    org_id = org_data.get('id')
                    parent_id = org_data.get('parent_id')

                    try:
                        org = OrgEinheit.objects.get(pk=org_id)
                        if parent_id:
                            org.uebergeordnet = OrgEinheit.objects.get(pk=parent_id)
                        else:
                            org.uebergeordnet = None
                        org.save(update_fields=['uebergeordnet'])
                    except OrgEinheit.DoesNotExist:
                        continue

                # 2. Stellen aktualisieren
                for stelle_data in data.get('stellen', []):
                    stelle_id = stelle_data.get('id')
                    parent_stelle_id = stelle_data.get('parent_stelle_id')
                    org_einheit_id = stelle_data.get('org_einheit_id')

                    try:
                        stelle = Stelle.objects.get(pk=stelle_id)

                        # OrgEinheit setzen
                        if org_einheit_id:
                            stelle.org_einheit = OrgEinheit.objects.get(pk=org_einheit_id)

                        # Uebergeordnete Stelle setzen
                        if parent_stelle_id:
                            stelle.uebergeordnete_stelle = Stelle.objects.get(pk=parent_stelle_id)
                        else:
                            stelle.uebergeordnete_stelle = None

                        stelle.save(update_fields=['org_einheit', 'uebergeordnete_stelle'])
                    except (Stelle.DoesNotExist, OrgEinheit.DoesNotExist):
                        continue

            logger.info('Hierarchie aktualisiert: %d OrgEinheiten, %d Stellen',
                       len(data.get('orgeinheiten', [])),
                       len(data.get('stellen', [])))

            return JsonResponse({'status': 'success', 'message': 'Hierarchie gespeichert'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Ungueltige JSON-Struktur'})
        except Exception as e:
            logger.error('Fehler beim Hierarchie-Update: %s', str(e))
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Nur POST erlaubt'})


@login_required
@user_passes_test(_ist_staff)
def company_builder_organigramm(request):
    """API: Liefert Organigramm-Daten als JSON basierend auf OrgEinheiten."""
    import json
    from django.http import JsonResponse

    def build_tree(orgeinheit=None):
        """Rekursiv Baum aus OrgEinheiten aufbauen."""
        if orgeinheit is None:
            # Root-Ebene: OrgEinheiten ohne Uebergeordnete
            root_orgs = OrgEinheit.objects.filter(
                uebergeordnet__isnull=True
            ).order_by('kuerzel')

            return {
                'name': 'Unternehmen',
                'children': [build_tree(org) for org in root_orgs]
            }

        # Untergeordnete OrgEinheiten
        untereinheiten = OrgEinheit.objects.filter(
            uebergeordnet=orgeinheit
        ).order_by('kuerzel')

        node = {
            'name': f"{orgeinheit.kuerzel}",
            'children': [build_tree(kind) for kind in untereinheiten] if untereinheiten.exists() else []
        }

        return node

    tree_data = build_tree()
    return JsonResponse(tree_data)


@login_required
@user_passes_test(_ist_staff)
def snapshot_create(request):
    """Erstellt einen Snapshot der aktuellen Hierarchie."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Nur POST erlaubt'})

    try:
        # Sammle aktuelle Hierarchie-Daten
        snapshot_data = {
            'orgeinheiten': [],
            'stellen': []
        }

        # Alle OrgEinheiten
        for org in OrgEinheit.objects.all():
            snapshot_data['orgeinheiten'].append({
                'id': org.id,
                'kuerzel': org.kuerzel,
                'bezeichnung': org.bezeichnung,
                'uebergeordnet_id': org.uebergeordnet_id,
                'ist_reserviert': org.ist_reserviert,
            })

        # Alle Stellen
        for stelle in Stelle.objects.all():
            snapshot_data['stellen'].append({
                'id': stelle.id,
                'kuerzel': stelle.kuerzel,
                'bezeichnung': stelle.bezeichnung,
                'org_einheit_id': stelle.org_einheit_id,
                'uebergeordnete_stelle_id': stelle.uebergeordnete_stelle_id,
                'delegiert_an_id': stelle.delegiert_an_id,
                'vertreten_durch_id': stelle.vertreten_durch_id,
                'vertretung_von': str(stelle.vertretung_von) if stelle.vertretung_von else None,
                'vertretung_bis': str(stelle.vertretung_bis) if stelle.vertretung_bis else None,
                'max_urlaubstage_genehmigung': stelle.max_urlaubstage_genehmigung,
                'eskalation_nach_tagen': stelle.eskalation_nach_tagen,
            })

        # Snapshot speichern
        snapshot = HierarchieSnapshot.objects.create(
            created_by=request.user,
            snapshot_data=snapshot_data
        )

        # Alte Snapshots loeschen (nur letzte 10 behalten)
        old_snapshots = HierarchieSnapshot.objects.all()[10:]
        for old in old_snapshots:
            old.delete()

        logger.info('Snapshot #%d erstellt von %s', snapshot.id, request.user.username)

        return JsonResponse({
            'status': 'success',
            'snapshot_id': snapshot.id,
            'message': 'Snapshot erstellt'
        })

    except Exception as e:
        logger.error('Fehler beim Snapshot-Erstellen: %s', str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required
@user_passes_test(_ist_staff)
def snapshot_restore(request):
    """Stellt den letzten Snapshot wieder her."""
    import json
    from django.http import JsonResponse
    from django.db import transaction

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Nur POST erlaubt'})

    try:
        # Letzten Snapshot holen
        snapshot = HierarchieSnapshot.objects.first()
        if not snapshot:
            return JsonResponse({'status': 'error', 'message': 'Kein Snapshot vorhanden'})

        data = snapshot.snapshot_data

        with transaction.atomic():
            # 1. Alle OrgEinheiten wiederherstellen
            for org_data in data.get('orgeinheiten', []):
                try:
                    org = OrgEinheit.objects.get(pk=org_data['id'])
                    org.kuerzel = org_data['kuerzel']
                    org.bezeichnung = org_data['bezeichnung']
                    org.uebergeordnet_id = org_data.get('uebergeordnet_id')
                    org.ist_reserviert = org_data.get('ist_reserviert', False)
                    org.save()
                except OrgEinheit.DoesNotExist:
                    # OrgEinheit existiert nicht mehr, ueberspringe
                    continue

            # 2. Alle Stellen wiederherstellen
            for stelle_data in data.get('stellen', []):
                try:
                    stelle = Stelle.objects.get(pk=stelle_data['id'])
                    stelle.kuerzel = stelle_data['kuerzel']
                    stelle.bezeichnung = stelle_data['bezeichnung']
                    stelle.org_einheit_id = stelle_data.get('org_einheit_id')
                    stelle.uebergeordnete_stelle_id = stelle_data.get('uebergeordnete_stelle_id')
                    stelle.delegiert_an_id = stelle_data.get('delegiert_an_id')
                    stelle.vertreten_durch_id = stelle_data.get('vertreten_durch_id')
                    stelle.vertretung_von = stelle_data.get('vertretung_von')
                    stelle.vertretung_bis = stelle_data.get('vertretung_bis')
                    stelle.max_urlaubstage_genehmigung = stelle_data.get('max_urlaubstage_genehmigung', 0)
                    stelle.eskalation_nach_tagen = stelle_data.get('eskalation_nach_tagen', 3)
                    stelle.save()
                except Stelle.DoesNotExist:
                    # Stelle existiert nicht mehr, ueberspringe
                    continue

        # Snapshot nach erfolgreicher Wiederherstellung loeschen
        snapshot.delete()

        logger.info('Snapshot #%d wiederhergestellt von %s', snapshot.id, request.user.username)

        return JsonResponse({
            'status': 'success',
            'message': 'Hierarchie wiederhergestellt'
        })

    except Exception as e:
        logger.error('Fehler beim Snapshot-Wiederherstellen: %s', str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required
@user_passes_test(lambda u: u.is_staff)
def company_builder_delete_orgeinheit(request, pk):
    """Loescht eine OrgEinheit nach Bestaetigung."""
    from django.http import JsonResponse
    from django.db import transaction

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Nur POST erlaubt'})

    try:
        orgeinheit = get_object_or_404(OrgEinheit, pk=pk)

        # Pruefe ob reserviert
        if orgeinheit.ist_reserviert:
            return JsonResponse({
                'status': 'error',
                'message': f'OrgEinheit "{orgeinheit.kuerzel}" ist reserviert und kann nicht geloescht werden.'
            })

        # Pruefe ob noch Stellen zugeordnet sind
        stellen_count = orgeinheit.stellen.count()
        if stellen_count > 0:
            return JsonResponse({
                'status': 'error',
                'message': f'OrgEinheit "{orgeinheit.kuerzel}" hat noch {stellen_count} Stelle(n) und kann nicht geloescht werden.'
            })

        # Pruefe ob noch untergeordnete OrgEinheiten existieren
        untereinheiten_count = orgeinheit.untereinheiten.count()
        if untereinheiten_count > 0:
            return JsonResponse({
                'status': 'error',
                'message': f'OrgEinheit "{orgeinheit.kuerzel}" hat noch {untereinheiten_count} untergeordnete Einheit(en) und kann nicht geloescht werden.'
            })

        # Alles OK, loesche
        kuerzel = orgeinheit.kuerzel
        with transaction.atomic():
            orgeinheit.delete()

        logger.info('OrgEinheit "%s" (ID %d) geloescht von %s', kuerzel, pk, request.user.username)

        return JsonResponse({
            'status': 'success',
            'message': f'OrgEinheit "{kuerzel}" wurde geloescht.'
        })

    except Exception as e:
        logger.error('Fehler beim Loeschen von OrgEinheit %d: %s', pk, str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required
@user_passes_test(lambda u: u.is_staff)
def company_builder_delete_stelle(request, pk):
    """Loescht eine Stelle nach Bestaetigung."""
    from django.http import JsonResponse
    from django.db import transaction

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Nur POST erlaubt'})

    try:
        stelle = get_object_or_404(Stelle, pk=pk)

        # Pruefe ob Stelle besetzt ist
        if stelle.ist_besetzt:
            return JsonResponse({
                'status': 'error',
                'message': f'Stelle "{stelle.kuerzel}" ist besetzt von {stelle.aktueller_inhaber.vollname} und kann nicht geloescht werden.'
            })

        # Pruefe ob noch untergeordnete Stellen existieren
        untergeordnete_count = stelle.untergeordnete_stellen.count()
        if untergeordnete_count > 0:
            return JsonResponse({
                'status': 'error',
                'message': f'Stelle "{stelle.kuerzel}" hat noch {untergeordnete_count} untergeordnete Stelle(n) und kann nicht geloescht werden.'
            })

        # Alles OK, loesche
        kuerzel = stelle.kuerzel
        with transaction.atomic():
            stelle.delete()

        logger.info('Stelle "%s" (ID %d) geloescht von %s', kuerzel, pk, request.user.username)

        return JsonResponse({
            'status': 'success',
            'message': f'Stelle "{kuerzel}" wurde geloescht.'
        })

    except Exception as e:
        logger.error('Fehler beim Loeschen von Stelle %d: %s', pk, str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============================================================================
# ORG-CHART EDITOR (Neuer grafischer Editor)
# ============================================================================


@login_required
@user_passes_test(_ist_staff)
def orgchart_editor(request):
    """Neuer grafischer Org-Chart Editor."""
    return render(request, "hr/orgchart_editor.html")


@login_required
@user_passes_test(_ist_staff)
def orgchart_editor_data(request):
    """API: Liefert Org-Chart Daten als JSON."""
    import json
    from django.http import JsonResponse

    def build_tree(orgeinheit):
        data = {
            "id": orgeinheit.id,
            "type": "orgeinheit",
            "kuerzel": orgeinheit.kuerzel,
            "name": orgeinheit.kuerzel,
            "title": orgeinheit.bezeichnung,
            "bezeichnung": orgeinheit.bezeichnung,
            "children": []
        }

        # Untergeordnete OrgEinheiten
        for unter in orgeinheit.untereinheiten.all():
            data["children"].append(build_tree(unter))

        # Root-Stellen dieser OrgEinheit
        for stelle in orgeinheit.stellen.filter(uebergeordnete_stelle__isnull=True):
            data["children"].append(build_stelle_tree(stelle))

        return data

    def build_stelle_tree(stelle):
        data = {
            "id": stelle.id,
            "type": "stelle",
            "kuerzel": stelle.kuerzel,
            "name": stelle.kuerzel,
            "title": stelle.bezeichnung,
            "bezeichnung": stelle.bezeichnung,
            "email": stelle.email,
            "inhaber": stelle.aktueller_inhaber.vollname if stelle.ist_besetzt else None,
            "children": []
        }

        # Untergeordnete Stellen
        for unter in stelle.untergeordnete_stellen.all():
            data["children"].append(build_stelle_tree(unter))

        return data

    # Root-OrgEinheiten
    root_orgs = OrgEinheit.objects.filter(uebergeordnet__isnull=True).order_by('kuerzel')
    tree_data = [build_tree(org) for org in root_orgs]

    return JsonResponse(tree_data, safe=False)


@login_required
@user_passes_test(_ist_staff)
def orgchart_editor_edit(request, typ, pk):
    """API: Element bearbeiten."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        kuerzel = data.get('kuerzel')
        bezeichnung = data.get('bezeichnung')

        if typ == 'orgeinheit':
            obj = get_object_or_404(OrgEinheit, pk=pk)
        else:
            obj = get_object_or_404(Stelle, pk=pk)

        obj.kuerzel = kuerzel
        obj.bezeichnung = bezeichnung
        obj.save()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def orgchart_editor_add(request):
    """API: Element hinzufuegen."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        typ = data.get('type')
        kuerzel = data.get('kuerzel')
        bezeichnung = data.get('bezeichnung')
        parent_type = data.get('parent_type')
        parent_id = data.get('parent_id')

        if typ == 'orgeinheit':
            # OrgEinheit erstellen
            parent_org = None
            if parent_type == 'orgeinheit' and parent_id:
                parent_org = OrgEinheit.objects.get(pk=parent_id)

            OrgEinheit.objects.create(
                kuerzel=kuerzel,
                bezeichnung=bezeichnung,
                uebergeordnet=parent_org
            )
        else:
            # Stelle erstellen
            if parent_type == 'orgeinheit' and parent_id:
                org_einheit = OrgEinheit.objects.get(pk=parent_id)
                Stelle.objects.create(
                    kuerzel=kuerzel,
                    bezeichnung=bezeichnung,
                    org_einheit=org_einheit
                )
            elif parent_type == 'stelle' and parent_id:
                parent_stelle = Stelle.objects.get(pk=parent_id)
                Stelle.objects.create(
                    kuerzel=kuerzel,
                    bezeichnung=bezeichnung,
                    org_einheit=parent_stelle.org_einheit,
                    uebergeordnete_stelle=parent_stelle
                )
            else:
                return JsonResponse({'error': 'Stellen brauchen eine OrgEinheit'}, status=400)

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def orgchart_editor_delete(request, typ, pk):
    """API: Element loeschen."""
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        if typ == 'orgeinheit':
            obj = get_object_or_404(OrgEinheit, pk=pk)
            if obj.ist_reserviert:
                return JsonResponse({'error': 'Reservierte OrgEinheit'}, status=400)
            if obj.stellen.exists():
                return JsonResponse({'error': 'OrgEinheit hat noch Stellen'}, status=400)
            if obj.untereinheiten.exists():
                return JsonResponse({'error': 'OrgEinheit hat noch Untereinheiten'}, status=400)
        else:
            obj = get_object_or_404(Stelle, pk=pk)
            if obj.ist_besetzt:
                return JsonResponse({'error': 'Stelle ist besetzt'}, status=400)
            if obj.untergeordnete_stellen.exists():
                return JsonResponse({'error': 'Stelle hat noch untergeordnete Stellen'}, status=400)

        obj.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ============================================================================
# EINFACHER STRUKTUR-EDITOR (Tabellen-basiert)
# ============================================================================


@login_required
@user_passes_test(_ist_staff)
def struktur_editor(request):
    """Einfacher tabellarischer Struktur-Editor."""
    orgeinheiten = OrgEinheit.objects.all().order_by('kuerzel')
    stellen = Stelle.objects.select_related('org_einheit', 'uebergeordnete_stelle', 'hrmitarbeiter').order_by('kuerzel')

    return render(request, 'hr/struktur_editor.html', {
        'orgeinheiten': orgeinheiten,
        'stellen': stellen,
    })


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_org_parent(request, pk):
    """OrgEinheit Hierarchie aendern."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        parent_id = data.get('parent_id')

        org = get_object_or_404(OrgEinheit, pk=pk)
        org.uebergeordnet_id = parent_id
        org.save(update_fields=['uebergeordnet'])

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_stelle_org(request, pk):
    """Stelle OrgEinheit aendern."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        org_id = data.get('org_id')

        stelle = get_object_or_404(Stelle, pk=pk)
        stelle.org_einheit_id = org_id
        stelle.save(update_fields=['org_einheit'])

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_stelle_parent(request, pk):
    """Stelle Hierarchie aendern."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        parent_id = data.get('parent_id')

        stelle = get_object_or_404(Stelle, pk=pk)
        stelle.uebergeordnete_stelle_id = parent_id
        stelle.save(update_fields=['uebergeordnete_stelle'])

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_org_add(request):
    """OrgEinheit hinzufuegen."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        OrgEinheit.objects.create(
            kuerzel=data['kuerzel'],
            bezeichnung=data['bezeichnung']
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_stelle_add(request):
    """Stelle hinzufuegen."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        # Erste OrgEinheit als default
        erste_org = OrgEinheit.objects.first()
        Stelle.objects.create(
            kuerzel=data['kuerzel'],
            bezeichnung=data['bezeichnung'],
            org_einheit=erste_org
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_org_edit(request, pk):
    """OrgEinheit bearbeiten."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        org = get_object_or_404(OrgEinheit, pk=pk)
        org.kuerzel = data['kuerzel']
        org.bezeichnung = data['bezeichnung']
        org.save()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_stelle_edit(request, pk):
    """Stelle bearbeiten."""
    import json
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        stelle = get_object_or_404(Stelle, pk=pk)
        stelle.kuerzel = data['kuerzel']
        stelle.bezeichnung = data['bezeichnung']
        stelle.save()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_org_delete(request, pk):
    """OrgEinheit loeschen."""
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        org = get_object_or_404(OrgEinheit, pk=pk)
        if org.ist_reserviert:
            return JsonResponse({'status': 'error', 'message': 'Reserviert'}, status=400)
        if org.stellen.exists():
            return JsonResponse({'status': 'error', 'message': 'Hat noch Stellen'}, status=400)
        org.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def struktur_editor_stelle_delete(request, pk):
    """Stelle loeschen."""
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        stelle = get_object_or_404(Stelle, pk=pk)
        if stelle.ist_besetzt:
            return JsonResponse({'status': 'error', 'message': 'Stelle ist besetzt'}, status=400)
        stelle.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ============================================================================
# NETZWERK-EDITOR (Visueller Graph mit Schere & Andocken)
# ============================================================================


@login_required
@user_passes_test(_ist_staff)
def netzwerk_editor(request):
    """Visueller Netzwerk-Editor mit Bubbles."""
    return render(request, 'hr/netzwerk_editor.html')


@login_required
@user_passes_test(_ist_staff)
def netzwerk_editor_data(request):
    """API: Liefert Netzwerk-Daten."""
    from django.http import JsonResponse

    nodes = []
    edges = []

    # OrgEinheiten als Nodes
    for org in OrgEinheit.objects.select_related('uebergeordnet', 'leitende_stelle'):
        nodes.append({
            'id': org.id,
            'type': 'orgeinheit',
            'label': org.kuerzel,
            'title': org.bezeichnung
        })
        # Verbindung zur uebergeordneten OrgEinheit
        if org.uebergeordnet:
            edges.append({
                'id': f'org_{org.id}_to_{org.uebergeordnet.id}',
                'from': f'orgeinheit_{org.uebergeordnet.id}',
                'to': f'orgeinheit_{org.id}'
            })
        # Verbindung zur leitenden Stelle (Bereichsleiter -> OrgEinheit)
        if org.leitende_stelle:
            edges.append({
                'id': f'stelle_{org.leitende_stelle.id}_to_org_{org.id}',
                'from': f'stelle_{org.leitende_stelle.id}',
                'to': f'orgeinheit_{org.id}'
            })

    # Stellen als Nodes
    for stelle in Stelle.objects.select_related('org_einheit', 'uebergeordnete_stelle'):
        inhaber = f' ({stelle.aktueller_inhaber.vollname})' if stelle.ist_besetzt else ''
        nodes.append({
            'id': stelle.id,
            'type': 'stelle',
            'kategorie': stelle.kategorie,
            'label': stelle.kuerzel,
            'title': f'{stelle.bezeichnung}{inhaber}'
        })
        # Verbindung zur OrgEinheit (wenn Root-Stelle in dieser OrgEinheit)
        if not stelle.uebergeordnete_stelle:
            edges.append({
                'id': f'org_{stelle.org_einheit.id}_to_stelle_{stelle.id}',
                'from': f'orgeinheit_{stelle.org_einheit.id}',
                'to': f'stelle_{stelle.id}'
            })
        # Verbindung zur uebergeordneten Stelle
        else:
            edges.append({
                'id': f'stelle_{stelle.id}_to_{stelle.uebergeordnete_stelle.id}',
                'from': f'stelle_{stelle.uebergeordnete_stelle.id}',
                'to': f'stelle_{stelle.id}'
            })

    return JsonResponse({
        'nodes': nodes,
        'edges': edges
    })


@login_required
@user_passes_test(_ist_staff)
def netzwerk_editor_save(request):
    """API: Speichert Netzwerk-Aenderungen."""
    import json
    from django.http import JsonResponse
    from django.db import transaction
    from django.core.exceptions import ValidationError

    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)

    try:
        data = json.loads(request.body)
        nodes_data = data.get('nodes', [])
        edges_data = data.get('edges', [])

        with transaction.atomic():
            # Schritt 1: Erstelle/Aktualisiere alle Nodes
            # Mapping: temp_id -> echte DB-ID
            id_mapping = {}
            created_count = 0
            updated_count = 0

            for node in nodes_data:
                node_id = node['id']
                node_type = node.get('type') or node.get('data', {}).get('type')
                kategorie = node.get('kategorie') or node.get('data', {}).get('kategorie', 'fachkraft')
                kuerzel = node['label']
                bezeichnung = node['title']

                # Validierung
                if not kuerzel or not kuerzel.strip():
                    return JsonResponse({'error': f'Kuerzel darf nicht leer sein'}, status=400)
                if not bezeichnung or not bezeichnung.strip():
                    return JsonResponse({'error': f'Bezeichnung darf nicht leer sein'}, status=400)

                if node_id.startswith('temp_'):
                    # Neue Node erstellen
                    if node_type == 'orgeinheit':
                        # Pruefe ob Kuerzel schon existiert
                        if OrgEinheit.objects.filter(kuerzel=kuerzel).exists():
                            return JsonResponse({'error': f'OrgEinheit mit Kuerzel "{kuerzel}" existiert bereits'}, status=400)
                        obj = OrgEinheit.objects.create(
                            kuerzel=kuerzel,
                            bezeichnung=bezeichnung
                        )
                        id_mapping[node_id] = f'orgeinheit_{obj.id}'
                        created_count += 1
                    elif node_type == 'stelle':
                        # Pruefe ob Kuerzel schon existiert
                        if Stelle.objects.filter(kuerzel=kuerzel).exists():
                            return JsonResponse({'error': f'Stelle mit Kuerzel "{kuerzel}" existiert bereits'}, status=400)
                        # Neue Stelle braucht zwingend eine OrgEinheit
                        # Wir nehmen die erste OrgEinheit als Default
                        default_org = OrgEinheit.objects.first()
                        if not default_org:
                            return JsonResponse({'error': 'Keine OrgEinheit vorhanden - erstelle zuerst eine OrgEinheit'}, status=400)
                        obj = Stelle.objects.create(
                            kuerzel=kuerzel,
                            bezeichnung=bezeichnung,
                            kategorie=kategorie,
                            org_einheit=default_org
                        )
                        id_mapping[node_id] = f'stelle_{obj.id}'
                        created_count += 1
                else:
                    # Bestehende Node aktualisieren
                    if node_id.startswith('orgeinheit_'):
                        pk = int(node_id.split('_')[1])
                        # Pruefe ob Kuerzel-Aenderung zu Konflikt fuehrt
                        existing = OrgEinheit.objects.filter(kuerzel=kuerzel).exclude(pk=pk)
                        if existing.exists():
                            return JsonResponse({'error': f'OrgEinheit mit Kuerzel "{kuerzel}" existiert bereits'}, status=400)
                        OrgEinheit.objects.filter(pk=pk).update(
                            kuerzel=kuerzel,
                            bezeichnung=bezeichnung
                        )
                        id_mapping[node_id] = node_id
                        updated_count += 1
                    elif node_id.startswith('stelle_'):
                        pk = int(node_id.split('_')[1])
                        # Pruefe ob Kuerzel-Aenderung zu Konflikt fuehrt
                        existing = Stelle.objects.filter(kuerzel=kuerzel).exclude(pk=pk)
                        if existing.exists():
                            return JsonResponse({'error': f'Stelle mit Kuerzel "{kuerzel}" existiert bereits'}, status=400)
                        Stelle.objects.filter(pk=pk).update(
                            kuerzel=kuerzel,
                            bezeichnung=bezeichnung,
                            kategorie=kategorie
                        )
                        id_mapping[node_id] = node_id
                        updated_count += 1

            # Schritt 2: Aktualisiere Parent-Beziehungen basierend auf Edges
            # WICHTIG: Alle Parents auf NULL setzen - Nodes ohne Edges werden Root-Nodes
            OrgEinheit.objects.all().update(uebergeordnet=None, leitende_stelle=None)
            Stelle.objects.all().update(uebergeordnete_stelle=None)

            edges_count = 0
            for edge in edges_data:
                from_id = id_mapping.get(edge['from'], edge['from'])
                to_id = id_mapping.get(edge['to'], edge['to'])

                # Edge bedeutet: from -> to, also to ist Kind von from
                if to_id.startswith('orgeinheit_'):
                    child_pk = int(to_id.split('_')[1])
                    if from_id.startswith('orgeinheit_'):
                        # OrgEinheit -> OrgEinheit: Hierarchie
                        parent_pk = int(from_id.split('_')[1])
                        # Pruefe auf Zirkelreferenz (vereinfacht)
                        if child_pk == parent_pk:
                            return JsonResponse({'error': 'Zirkelreferenz: OrgEinheit kann nicht ihr eigener Parent sein'}, status=400)
                        OrgEinheit.objects.filter(pk=child_pk).update(
                            uebergeordnet_id=parent_pk
                        )
                        edges_count += 1
                    elif from_id.startswith('stelle_'):
                        # Stelle -> OrgEinheit: Bereichsleiter leitet OrgEinheit
                        stelle_pk = int(from_id.split('_')[1])
                        OrgEinheit.objects.filter(pk=child_pk).update(
                            leitende_stelle_id=stelle_pk
                        )
                        edges_count += 1
                elif to_id.startswith('stelle_'):
                    child_pk = int(to_id.split('_')[1])
                    if from_id.startswith('stelle_'):
                        # Stelle -> Stelle: Hierarchie
                        parent_pk = int(from_id.split('_')[1])
                        # Pruefe auf Zirkelreferenz (vereinfacht)
                        if child_pk == parent_pk:
                            return JsonResponse({'error': 'Zirkelreferenz: Stelle kann nicht ihr eigener Parent sein'}, status=400)
                        Stelle.objects.filter(pk=child_pk).update(
                            uebergeordnete_stelle_id=parent_pk
                        )
                        edges_count += 1
                    elif from_id.startswith('orgeinheit_'):
                        # OrgEinheit -> Stelle: Stelle gehoert zu OrgEinheit
                        org_pk = int(from_id.split('_')[1])
                        Stelle.objects.filter(pk=child_pk).update(
                            org_einheit_id=org_pk
                        )
                        edges_count += 1

        message = f'Struktur gespeichert! ({created_count} erstellt, {updated_count} aktualisiert, {edges_count} Verbindungen)'
        return JsonResponse({'status': 'success', 'message': message})
    except ValidationError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Fehler: {str(e)}'}, status=400)


@login_required
@user_passes_test(_ist_staff)
def tree_editor(request):
    """Tree Editor mit D3.js"""
    return render(request, 'hr/tree_editor.html')


@login_required
@user_passes_test(_ist_staff)
def tree_editor_data(request):
    """API: Liefert Baumdaten fuer Tree Editor"""
    from django.http import JsonResponse

    def org_to_tree(org, visited=None):
        """Konvertiert OrgEinheit zu Tree-Format"""
        if visited is None:
            visited = set()

        # Vermeide Zyklen
        org_key = f'org_{org.id}'
        if org_key in visited:
            return None
        visited.add(org_key)

        node = {
            'id': org_key,
            'name': f'{org.kuerzel} - {org.bezeichnung}',
            'type': 'orgeinheit',
            'db_id': org.id,
            'children': []
        }

        # Stellen in dieser OrgEinheit (Root-Stellen)
        for stelle in org.stellen.filter(uebergeordnete_stelle__isnull=True).order_by('kuerzel'):
            child = stelle_to_tree(stelle, visited)
            if child:
                node['children'].append(child)

        # Untereinheiten
        for child_org in org.untereinheiten.order_by('kuerzel'):
            child = org_to_tree(child_org, visited)
            if child:
                node['children'].append(child)

        return node

    def stelle_to_tree(stelle, visited=None):
        """Konvertiert Stelle zu Tree-Format"""
        if visited is None:
            visited = set()

        # Vermeide Zyklen
        stelle_key = f'stelle_{stelle.id}'
        if stelle_key in visited:
            return None
        visited.add(stelle_key)

        node = {
            'id': stelle_key,
            'name': f'{stelle.kuerzel} - {stelle.bezeichnung}',
            'type': 'stelle',
            'kategorie': stelle.kategorie,
            'db_id': stelle.id,
            'children': []
        }

        # Untergeordnete Stellen
        for child_stelle in stelle.untergeordnete_stellen.order_by('kuerzel'):
            child = stelle_to_tree(child_stelle, visited)
            if child:
                node['children'].append(child)

        return node

    # Root finden
    root_org = OrgEinheit.objects.filter(uebergeordnet__isnull=True).first()
    if not root_org:
        return JsonResponse({'error': 'Keine Root-OrgEinheit gefunden'}, status=404)

    tree_data = org_to_tree(root_org)
    return JsonResponse(tree_data)


@login_required
@user_passes_test(_ist_staff)
def tree_editor_save(request):
    """API: Speichert Tree-Aenderungen"""
    import json
    from django.http import JsonResponse
    from django.db import transaction
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Nur POST'}, status=400)
    
    try:
        data = json.loads(request.body)
        
        with transaction.atomic():
            # TODO: Implementiere Save-Logik
            # Das ist komplex weil die gesamte Baumstruktur neu aufgebaut werden muss
            return JsonResponse({
                'status': 'success',
                'message': 'Save noch nicht implementiert - Vorschau'
            })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(_ist_staff)
def orgchart_kasten(request):
    """OrgChart mit Kaesten"""
    return render(request, 'hr/orgchart_kasten.html')


@login_required
@user_passes_test(_ist_staff)
def orgchart_kasten_data(request):
    """API: Liefert Daten fuer OrgChart.js Kaesten"""
    from django.http import JsonResponse
    
    nodes = []
    node_id = 1
    
    # 1. Geschaeftsfuehrung
    gf_org = OrgEinheit.objects.filter(kuerzel='GF').first()
    if gf_org:
        gf_stellen = gf_org.stellen.filter(uebergeordnete_stelle__isnull=True)
        stellen_html = '<div class="box-stellen">'
        for stelle in gf_stellen:
            kategorie_class = f'stelle-kategorie-{stelle.kategorie}'
            icon = '👔' if stelle.kategorie == 'leitung' else '👤'
            stellen_html += f'<div class="stelle-item {kategorie_class}">'
            stellen_html += f'<span class="stelle-icon">{icon}</span>'
            stellen_html += f'<span>{stelle.kuerzel} - {stelle.bezeichnung}</span>'
            stellen_html += '</div>'
        stellen_html += '</div>'
        
        gf_node = {
            'id': node_id,
            'titel': f'<div class="box-title">📋 {gf_org.bezeichnung}</div>',
            'stellen_html': stellen_html,
            'tags': ['geschaeftsfuehrung']
        }
        nodes.append(gf_node)
        gf_node_id = node_id
        node_id += 1
    
    # 2. Bereiche (VW, PT, VM)
    bereiche = OrgEinheit.objects.filter(uebergeordnet=gf_org).order_by('kuerzel')
    for bereich in bereiche:
        bereich_stellen = bereich.stellen.filter(uebergeordnete_stelle__isnull=True)
        stellen_html = '<div class="box-stellen">'
        for stelle in bereich_stellen:
            kategorie_class = f'stelle-kategorie-{stelle.kategorie}'
            icon = '👔' if stelle.kategorie == 'leitung' else ('📎' if stelle.kategorie == 'stab' else '👤')
            stellen_html += f'<div class="stelle-item {kategorie_class}">'
            stellen_html += f'<span class="stelle-icon">{icon}</span>'
            stellen_html += f'<span>{stelle.kuerzel}</span>'
            stellen_html += '</div>'
        stellen_html += '</div>'
        
        bereich_node = {
            'id': node_id,
            'pid': gf_node_id,
            'titel': f'<div class="box-title">📦 BEREICH: {bereich.bezeichnung}</div>',
            'stellen_html': stellen_html,
            'tags': ['bereich']
        }
        nodes.append(bereich_node)
        bereich_node_id = node_id
        node_id += 1
        
        # 3. Abteilungen unter diesem Bereich
        abteilungen = bereich.untereinheiten.order_by('kuerzel')
        for abteilung in abteilungen:
            abt_stellen = abteilung.stellen.filter(uebergeordnete_stelle__isnull=True)
            stellen_html = '<div class="box-stellen">'
            for stelle in abt_stellen:
                kategorie_class = f'stelle-kategorie-{stelle.kategorie}'
                icon = '👔' if stelle.kategorie == 'leitung' else '👤'
                inhaber = f' ({stelle.aktueller_inhaber.vollname})' if stelle.ist_besetzt else ''
                stellen_html += f'<div class="stelle-item {kategorie_class}">'
                stellen_html += f'<span class="stelle-icon">{icon}</span>'
                stellen_html += f'<span>{stelle.kuerzel}{inhaber}</span>'
                stellen_html += '</div>'
            stellen_html += '</div>'
            
            abt_node = {
                'id': node_id,
                'pid': bereich_node_id,
                'titel': f'<div class="box-title">🏢 {abteilung.bezeichnung}</div>',
                'stellen_html': stellen_html,
                'tags': ['abteilung']
            }
            nodes.append(abt_node)
            node_id += 1
    
    return JsonResponse(nodes, safe=False)


@login_required
@user_passes_test(_ist_staff)
def kasten_organigramm(request):
    """Einfaches Kasten-Organigramm mit HTML/CSS"""

    # Geschaeftsfuehrung
    gf_org = OrgEinheit.objects.filter(kuerzel='GF').first()
    gf_stellen = gf_org.stellen.filter(uebergeordnete_stelle__isnull=True) if gf_org else []

    # Bereiche mit Abteilungen
    bereiche_data = []
    if gf_org:
        bereiche = OrgEinheit.objects.filter(uebergeordnet=gf_org).order_by('kuerzel')
        for bereich in bereiche:
            bereich_stellen = bereich.stellen.filter(uebergeordnete_stelle__isnull=True)
            abteilungen = bereich.untereinheiten.order_by('kuerzel')

            abteilungen_data = []
            for abt in abteilungen:
                abt_stellen = abt.stellen.filter(uebergeordnete_stelle__isnull=True)

                # Teams unter Abteilung
                teams = abt.untereinheiten.order_by('kuerzel')
                teams_data = []
                for team in teams:
                    team_stellen = team.stellen.filter(uebergeordnete_stelle__isnull=True)
                    teams_data.append({
                        'kuerzel': team.kuerzel,
                        'bezeichnung': team.bezeichnung,
                        'stellen': team_stellen
                    })

                abteilungen_data.append({
                    'kuerzel': abt.kuerzel,
                    'bezeichnung': abt.bezeichnung,
                    'stellen': abt_stellen,
                    'teams': teams_data
                })

            bereiche_data.append({
                'kuerzel': bereich.kuerzel,
                'bezeichnung': bereich.bezeichnung,
                'stellen': bereich_stellen,
                'abteilungen': abteilungen_data
            })

    return render(request, 'hr/kasten_organigramm.html', {
        'gf_stellen': gf_stellen,
        'bereiche': bereiche_data
    })


@login_required
@user_passes_test(_ist_staff)
def kasten_bereich_form(request):
    """HTMX: Formular zum Anlegen eines neuen Bereichs"""
    if request.method == 'POST':
        kuerzel = request.POST.get('kuerzel', '').strip().upper()
        bezeichnung = request.POST.get('bezeichnung', '').strip()

        if not kuerzel or not bezeichnung:
            return render(request, 'hr/partials/kasten_bereich_form.html', {
                'error': 'Bitte Kuerzel und Bezeichnung eingeben'
            })

        # Pruefe ob Kuerzel schon existiert
        if OrgEinheit.objects.filter(kuerzel=kuerzel).exists():
            return render(request, 'hr/partials/kasten_bereich_form.html', {
                'error': f'Kuerzel "{kuerzel}" existiert bereits'
            })

        # GF als Parent
        gf_org = OrgEinheit.objects.filter(kuerzel='GF').first()
        if not gf_org:
            return render(request, 'hr/partials/kasten_bereich_form.html', {
                'error': 'GF OrgEinheit nicht gefunden'
            })

        # Erstelle Bereich
        OrgEinheit.objects.create(
            kuerzel=kuerzel,
            bezeichnung=bezeichnung,
            uebergeordnet=gf_org
        )

        logger.info(f'Neuer Bereich erstellt: {kuerzel} - {bezeichnung}')

        # Erfolg: Seite neu laden
        from django.http import HttpResponse
        return HttpResponse('<script>location.reload()</script>')

    return render(request, 'hr/partials/kasten_bereich_form.html')


@login_required
@user_passes_test(_ist_staff)
def kasten_abteilung_form(request):
    """HTMX: Formular zum Anlegen einer neuen Abteilung"""
    bereich_kuerzel = request.GET.get('bereich_kuerzel')

    if request.method == 'POST':
        kuerzel = request.POST.get('kuerzel', '').strip().upper()
        bezeichnung = request.POST.get('bezeichnung', '').strip()
        bereich_kuerzel = request.POST.get('bereich_kuerzel', '')

        if not kuerzel or not bezeichnung or not bereich_kuerzel:
            return render(request, 'hr/partials/kasten_abteilung_form.html', {
                'bereich_kuerzel': bereich_kuerzel,
                'error': 'Bitte alle Felder ausfuellen'
            })

        # Pruefe ob Kuerzel schon existiert
        if OrgEinheit.objects.filter(kuerzel=kuerzel).exists():
            return render(request, 'hr/partials/kasten_abteilung_form.html', {
                'bereich_kuerzel': bereich_kuerzel,
                'error': f'Kuerzel "{kuerzel}" existiert bereits'
            })

        # Bereich finden
        bereich = OrgEinheit.objects.filter(kuerzel=bereich_kuerzel).first()
        if not bereich:
            return render(request, 'hr/partials/kasten_abteilung_form.html', {
                'bereich_kuerzel': bereich_kuerzel,
                'error': f'Bereich "{bereich_kuerzel}" nicht gefunden'
            })

        # Erstelle Abteilung
        OrgEinheit.objects.create(
            kuerzel=kuerzel,
            bezeichnung=bezeichnung,
            uebergeordnet=bereich
        )

        logger.info(f'Neue Abteilung erstellt: {kuerzel} - {bezeichnung} unter {bereich_kuerzel}')

        # Erfolg: Seite neu laden
        from django.http import HttpResponse
        return HttpResponse('<script>location.reload()</script>')

    return render(request, 'hr/partials/kasten_abteilung_form.html', {
        'bereich_kuerzel': bereich_kuerzel
    })


@login_required
@user_passes_test(_ist_staff)
def kasten_stelle_form(request):
    """HTMX: Formular zum Anlegen einer neuen Stelle"""
    org_kuerzel = request.GET.get('org_kuerzel')

    if request.method == 'POST':
        kuerzel = request.POST.get('kuerzel', '').strip().lower()
        bezeichnung = request.POST.get('bezeichnung', '').strip()
        kategorie = request.POST.get('kategorie', 'fachkraft')
        org_kuerzel = request.POST.get('org_kuerzel', '')

        if not kuerzel or not bezeichnung or not org_kuerzel:
            return render(request, 'hr/partials/kasten_stelle_form.html', {
                'org_kuerzel': org_kuerzel,
                'error': 'Bitte alle Felder ausfuellen'
            })

        # Pruefe ob Kuerzel schon existiert
        if Stelle.objects.filter(kuerzel=kuerzel).exists():
            return render(request, 'hr/partials/kasten_stelle_form.html', {
                'org_kuerzel': org_kuerzel,
                'error': f'Kuerzel "{kuerzel}" existiert bereits'
            })

        # OrgEinheit finden
        org = OrgEinheit.objects.filter(kuerzel=org_kuerzel).first()
        if not org:
            return render(request, 'hr/partials/kasten_stelle_form.html', {
                'org_kuerzel': org_kuerzel,
                'error': f'OrgEinheit "{org_kuerzel}" nicht gefunden'
            })

        # Erstelle Stelle
        Stelle.objects.create(
            kuerzel=kuerzel,
            bezeichnung=bezeichnung,
            kategorie=kategorie,
            org_einheit=org
        )

        logger.info(f'Neue Stelle erstellt: {kuerzel} - {bezeichnung} in {org_kuerzel}')

        # Erfolg: Seite neu laden
        from django.http import HttpResponse
        return HttpResponse('<script>location.reload()</script>')

    return render(request, 'hr/partials/kasten_stelle_form.html', {
        'org_kuerzel': org_kuerzel
    })


@login_required
@user_passes_test(_ist_staff)
def kasten_team_form(request):
    """HTMX: Formular zum Anlegen eines neuen Teams"""
    abteilung_kuerzel = request.GET.get('abteilung_kuerzel')

    if request.method == 'POST':
        kuerzel = request.POST.get('kuerzel', '').strip().upper()
        bezeichnung = request.POST.get('bezeichnung', '').strip()
        abteilung_kuerzel = request.POST.get('abteilung_kuerzel', '')

        if not kuerzel or not bezeichnung or not abteilung_kuerzel:
            return render(request, 'hr/partials/kasten_team_form.html', {
                'abteilung_kuerzel': abteilung_kuerzel,
                'error': 'Bitte alle Felder ausfuellen'
            })

        # Pruefe ob Kuerzel schon existiert
        if OrgEinheit.objects.filter(kuerzel=kuerzel).exists():
            return render(request, 'hr/partials/kasten_team_form.html', {
                'abteilung_kuerzel': abteilung_kuerzel,
                'error': f'Kuerzel "{kuerzel}" existiert bereits'
            })

        # Abteilung finden
        abteilung = OrgEinheit.objects.filter(kuerzel=abteilung_kuerzel).first()
        if not abteilung:
            return render(request, 'hr/partials/kasten_team_form.html', {
                'abteilung_kuerzel': abteilung_kuerzel,
                'error': f'Abteilung "{abteilung_kuerzel}" nicht gefunden'
            })

        # Erstelle Team
        OrgEinheit.objects.create(
            kuerzel=kuerzel,
            bezeichnung=bezeichnung,
            uebergeordnet=abteilung
        )

        logger.info(f'Neues Team erstellt: {kuerzel} - {bezeichnung} unter {abteilung_kuerzel}')

        # Erfolg: Seite neu laden
        from django.http import HttpResponse
        return HttpResponse('<script>location.reload()</script>')

    return render(request, 'hr/partials/kasten_team_form.html', {
        'abteilung_kuerzel': abteilung_kuerzel
    })


@login_required
@user_passes_test(_ist_staff)
def kasten_stelle_edit(request, pk):
    """HTMX: Formular zum Bearbeiten einer Stelle"""
    stelle = get_object_or_404(Stelle, pk=pk)

    if request.method == 'POST':
        bezeichnung = request.POST.get('bezeichnung', '').strip()
        kategorie = request.POST.get('kategorie', 'fachkraft')

        if not bezeichnung:
            return render(request, 'hr/partials/kasten_stelle_edit.html', {
                'stelle': stelle,
                'error': 'Bitte Bezeichnung eingeben'
            })

        # Update Stelle
        stelle.bezeichnung = bezeichnung
        stelle.kategorie = kategorie
        stelle.save()

        logger.info(f'Stelle aktualisiert: {stelle.kuerzel}')

        # Erfolg: Seite neu laden
        from django.http import HttpResponse
        return HttpResponse('<script>location.reload()</script>')

    return render(request, 'hr/partials/kasten_stelle_edit.html', {
        'stelle': stelle
    })


@login_required
@user_passes_test(_ist_staff)
def kasten_detail(request, kuerzel):
    """Detail-Ansicht fuer eine OrgEinheit mit allen Stellen und Untereinheiten"""
    org = get_object_or_404(OrgEinheit, kuerzel=kuerzel)

    # Alle Stellen dieser OrgEinheit (inklusive untergeordneter Stellen)
    alle_stellen = org.stellen.all().order_by('kategorie', 'kuerzel')

    # Root-Stellen (ohne Parent)
    root_stellen = org.stellen.filter(uebergeordnete_stelle__isnull=True).order_by('kategorie', 'kuerzel')

    # Direkte Untereinheiten
    untereinheiten = org.untereinheiten.all().order_by('kuerzel')

    # Uebergeordnete OrgEinheit
    parent = org.uebergeordnet

    # Hierarchie-Pfad (Breadcrumb)
    pfad = []
    current = org
    while current:
        pfad.insert(0, current)
        current = current.uebergeordnet

    return render(request, 'hr/kasten_detail.html', {
        'org': org,
        'alle_stellen': alle_stellen,
        'root_stellen': root_stellen,
        'untereinheiten': untereinheiten,
        'parent': parent,
        'pfad': pfad
    })
