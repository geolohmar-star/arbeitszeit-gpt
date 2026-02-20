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
def stellen_organigramm(request):
    """Feature 4: Visuelle Hierarchie der Stellen."""
    import json

    def stelle_to_dict(stelle):
        """Konvertiert eine Stelle in OrgChart.js Format."""
        data = {
            "id": str(stelle.pk),
            "name": stelle.kuerzel,
            "title": stelle.bezeichnung,
            "className": f"rolle-{stelle.kuerzel[:2]}",
            "extra": {
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

        # Rekursiv Kinder hinzufuegen
        kinder = stelle.untergeordnete_stellen.select_related(
            "org_einheit"
        ).prefetch_related("untergeordnete_stellen")

        if kinder.exists():
            data["children"] = [stelle_to_dict(kind) for kind in kinder]

        return data

    # Top-Level Stellen
    top_stellen = Stelle.objects.filter(
        uebergeordnete_stelle__isnull=True
    ).select_related("org_einheit").prefetch_related("untergeordnete_stellen")

    # Alle Stellen fuer Fallback
    alle_stellen = Stelle.objects.select_related(
        "org_einheit", "uebergeordnete_stelle"
    ).prefetch_related("untergeordnete_stellen")

    # Konvertiere zu OrgChart.js Format
    orgchart_data = []
    for stelle in top_stellen:
        orgchart_data.append(stelle_to_dict(stelle))

    return render(
        request,
        "hr/stellen_organigramm.html",
        {
            "top_stellen": top_stellen,
            "alle_stellen": alle_stellen,
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
    
    orgeinheiten = OrgEinheit.objects.prefetch_related('stellen').order_by('kuerzel')
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
    """API: Liefert Organigramm-Daten als JSON."""
    import json
    from django.http import JsonResponse
    
    def build_tree(stelle=None):
        """Rekursiv Baum aufbauen."""
        if stelle is None:
            # Root: GF-Stellen
            root_stellen = Stelle.objects.filter(
                uebergeordnete_stelle__isnull=True
            ).order_by('kuerzel')
            
            return {
                'name': 'Unternehmen',
                'children': [build_tree(s) for s in root_stellen]
            }
        
        # Kinder dieser Stelle
        kinder = Stelle.objects.filter(
            uebergeordnete_stelle=stelle
        ).order_by('kuerzel')
        
        node = {
            'name': f"{stelle.kuerzel}",
            'children': [build_tree(kind) for kind in kinder] if kinder.exists() else []
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
