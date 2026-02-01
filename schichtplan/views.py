# schichtplan/views.py - ANGEPASST für MA1-MA15 mit Präferenzen
"""
Views für das Schichtplan-Modul
ANGEPASST: Filtert nur Mitarbeiter mit Kennung MA1-MA15
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.views.generic.edit import CreateView
from django.urls import reverse_lazy
from django.db import transaction

from datetime import timedelta
from calendar import day_name
import tempfile

# Models
from arbeitszeit.models import Mitarbeiter
from .models import Schichtplan, Schicht, Schichttyp, SchichtwunschPeriode

# Forms
from .forms import ExcelImportForm, SchichtplanForm, SchichtForm

# Services
from .services import SchichtplanGenerator

# Utils
try:
    from .utils.excel_import import SchichtplanImporter
except ImportError:
    try:
        from .utils.xls_importer import SchichtplanImporter
    except ImportError:
        SchichtplanImporter = None


# ============================================================================
# HELPER FUNKTIONEN
# ============================================================================

def ist_schichtplaner(user):
    """Prüft, ob der User Schichtplaner-Rechte hat"""
    if user.is_staff or user.is_superuser:
        return True
    
    if hasattr(user, 'mitarbeiter'):
        return user.mitarbeiter.rolle == 'schichtplaner'
    
    return False


def get_planbare_mitarbeiter():
    """
    Gibt nur Mitarbeiter zurück, die für Schichtplanung relevant sind.
    
    Kriterien:
    - Aktiv = True
    - Kennung = MA1 bis MA15
    - Verfügbarkeit != 'dauerkrank'
    """
    gueltige_kennungen = [f'MA{i}' for i in range(1, 16)]  # MA1 bis MA15
    
    return Mitarbeiter.objects.filter(
        aktiv=True,
        schichtplan_kennung__in=gueltige_kennungen
    ).exclude(
        verfuegbarkeit='dauerkrank'
    ).select_related('user')


# ============================================================================
# CLASS-BASED VIEW: Schichtplan erstellen
# ============================================================================

class SchichtplanCreateView(CreateView):
    """
    Erstellt einen neuen Schichtplan.
    Verwendet nur Mitarbeiter mit Kennung MA1-MA15.
    """
    
    model = Schichtplan
    form_class = SchichtplanForm
    template_name = 'schichtplan/schichtplan_erstellen.html'
    success_url = reverse_lazy('schichtplan:dashboard')

    def dispatch(self, request, *args, **kwargs):
        """Berechtigungsprüfung"""
        if not ist_schichtplaner(request.user):
            messages.error(request, "❌ Keine Berechtigung für diese Aktion.")
            return redirect('arbeitszeit:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """Speichern + Optional KI-Generierung"""
        
        ki_aktiviert = form.cleaned_data.get('vorschlag_generieren', False)
        
        try:
            with transaction.atomic():
                # 1. Schichtplan speichern
                self.object = form.save(commit=False)
                
                if hasattr(self.object, 'erstellt_von'):
                    self.object.erstellt_von = self.request.user
                
                self.object.save()
                
                print(f"✅ Schichtplan '{self.object.name}' (ID={self.object.pk}) gespeichert")
                
                # 2. KI-Generierung (falls aktiviert)
                if ki_aktiviert:
                    self._generate_with_ai()
                else:
                    messages.success(
                        self.request,
                        f"✅ Plan '{self.object.name}' wurde leer angelegt."
                    )
            
            return redirect(self.get_success_url())
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            messages.error(
                self.request,
                f"❌ Fehler beim Erstellen des Plans: {str(e)}"
            )
            return self.form_invalid(form)

    def _generate_with_ai(self):
        """
        KI-Generierung mit gefilterter Mitarbeiter-Liste (MA1-MA15).
        Berücksichtigt alle Präferenzen aus dem Mitarbeiter-Model.
        """
        
        print(f"🤖 KI-Generierung für Plan '{self.object.name}' (ID={self.object.pk}) gestartet...")
        
        # ====================================================================
        # MITARBEITER LADEN: NUR MA1-MA15
        # ====================================================================
        
        planbare_mitarbeiter = get_planbare_mitarbeiter()
        
        if not planbare_mitarbeiter.exists():
            messages.warning(
                self.request,
                "⚠️ Keine planbaren Mitarbeiter gefunden!\n"
                "Prüfe, ob Mitarbeiter:\n"
                "- Aktiv sind\n"
                "- Kennung MA1-MA15 haben\n"
                "- Nicht dauerkrank sind"
            )
            return
        
        print(f"   ✓ {planbare_mitarbeiter.count()} planbare Mitarbeiter (MA1-MA15) gefunden:")
        for ma in planbare_mitarbeiter:
            print(f"      - {ma.schichtplan_kennung}: {ma.vollname}")
            print(f"        Verfügbarkeit: {ma.get_verfuegbarkeit_display()}")
            print(f"        Tag: {ma.kann_tagschicht}, Nacht: {ma.kann_nachtschicht}")
            if ma.nachtschicht_nur_wochenende:
                print(f"        → Nachtschicht nur Wochenende!")
            if ma.nur_zusatzdienste_wochentags:
                print(f"        → Wochentags nur Zusatzdienste!")
        
        # ====================================================================
        # VALIDIERUNG: Schichttypen T und N vorhanden?
        # ====================================================================
        
        required_types = ['T', 'N']
        existing_types = list(
            Schichttyp.objects.filter(
                kuerzel__in=required_types
            ).values_list('kuerzel', flat=True)
        )
        
        if len(existing_types) != len(required_types):
            missing = set(required_types) - set(existing_types)
            raise Exception(
                f"Schichttypen fehlen: {', '.join(missing)}. "
                f"Bitte erstelle diese im Admin-Bereich."
            )
        
        print(f"   ✓ Schichttypen T und N vorhanden")
        
        # ====================================================================
        # GENERATOR STARTEN
        # ====================================================================
        
        try:
            generator = SchichtplanGenerator(planbare_mitarbeiter)
            generator.generiere_vorschlag(self.object)
            
            schichten_anzahl = self.object.schichten.count()
            
            messages.success(
                self.request,
                f"✅ Plan '{self.object.name}' wurde erfolgreich erstellt! "
                f"🚀 {schichten_anzahl} Schichten für {planbare_mitarbeiter.count()} "
                f"Mitarbeiter (MA1-MA15) automatisch generiert."
            )
            
            print(f"✅ Erfolgreich {schichten_anzahl} Schichten generiert für Plan ID={self.object.pk}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            raise Exception(
                f"Die KI-Generierung schlug fehl: {str(e)}. "
                f"Überprüfe die Konsole für Details."
            )


# ============================================================================
# REST DER VIEWS (unverändert)
# ============================================================================

@login_required
def excel_import_view(request, pk):
    """Importiert Excel-Datei in einen bestehenden Schichtplan"""
    schichtplan = get_object_or_404(Schichtplan, pk=pk)

    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung.")
        return redirect('schichtplan:dashboard')

    if request.method == 'POST':
        form = ExcelImportForm(request.POST, request.FILES)

        if form.is_valid():
            excel_file = request.FILES['excel_file']

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                for chunk in excel_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            try:
                if SchichtplanImporter is None:
                    raise Exception("Excel-Importer nicht verfügbar!")
                
                importer = SchichtplanImporter()
                importer.import_excel_mit_zuordnung(tmp_path, schichtplan)

                messages.success(request, "✅ Excel-Datei erfolgreich importiert!")
                return redirect('schichtplan:detail', pk=schichtplan.pk)

            except Exception as e:
                messages.error(request, f"❌ Fehler beim Import: {str(e)}")

    else:
        form = ExcelImportForm()

    return render(request, 'schichtplan/excel_import.html', {
        'form': form,
        'schichtplan': schichtplan
    })


@login_required
def excel_analyse_view(request):
    """Analysiert Excel-Datei vor dem Import"""
    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung.")
        return redirect('arbeitszeit:dashboard')
    
    if request.method == 'POST':
        form = ExcelImportForm(request.POST, request.FILES)
        
        if form.is_valid():
            stats = {
                'info': 'Analyse-Funktion noch nicht implementiert'
            }
            
            return render(request, 'schichtplan/excel_analyse.html', {
                'stats': stats,
                'form': form,
            })
    else:
        form = ExcelImportForm()
    
    return render(request, 'schichtplan/excel_analyse.html', {
        'form': form,
    })


@login_required
def planer_dashboard(request):
    """Dashboard für Schichtplaner"""
    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung für diese Seite.")
        return redirect('arbeitszeit:dashboard')
    
    schichtplaene = Schichtplan.objects.all().order_by('-start_datum')
    
    aktive_plaene = schichtplaene.filter(status='veroeffentlicht').count()
    entwuerfe = schichtplaene.filter(status='entwurf').count()
    
    # Zeige nur planbare Mitarbeiter in den Statistiken
    planbare_ma = get_planbare_mitarbeiter()
    
    context = {
        'schichtplaene': schichtplaene,
        'aktive_plaene': aktive_plaene,
        'entwuerfe': entwuerfe,
        'mitarbeiter_gesamt': planbare_ma.count(),
        'mitarbeiter_zugeordnet': planbare_ma.exclude(schichtplan_kennung='').count(),
    }
    
    return render(request, 'schichtplan/planer_dashboard.html', context)


@login_required
def mitarbeiter_uebersicht(request):
    """Mitarbeiter-Übersicht für Schichtplaner"""
    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung.")
        return redirect('arbeitszeit:dashboard')
    
    # Zeige nur planbare Mitarbeiter
    mitarbeiter = get_planbare_mitarbeiter()
    
    stats = {
        'gesamt': mitarbeiter.count(),
        'zugeordnet': mitarbeiter.exclude(schichtplan_kennung='').count(),
        'nicht_zugeordnet': mitarbeiter.filter(schichtplan_kennung='').count(),
        'dauerkrank': Mitarbeiter.objects.filter(
            aktiv=True,
            verfuegbarkeit='dauerkrank'
        ).count(),
    }
    
    context = {
        'mitarbeiter': mitarbeiter,
        'mitarbeiter_liste': mitarbeiter,
        'stats': stats,
        'anzahl_siegburg': mitarbeiter.filter(standort='siegburg').count(),
        'anzahl_bonn': mitarbeiter.filter(standort='bonn').count(),
    }
    
    return render(request, 'arbeitszeit/mitarbeiter_uebersicht.html', context)


@login_required
def schichtplan_detail(request, pk):
    """Detail-Ansicht eines Schichtplans"""
    schichtplan = get_object_or_404(Schichtplan, pk=pk)

    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung.")
        return redirect('arbeitszeit:dashboard')

    # Alle Schichten des Plans
    schichten = schichtplan.schichten.select_related(
        'mitarbeiter', 'schichttyp'
    ).order_by('datum', 'schichttyp__start_zeit')

    # Mitarbeiter-Zuordnung (Mapping von schichtplan_kennung zu vollname)
    mitarbeiter_mapping = {ma.schichtplan_kennung: ma.vollname for ma in Mitarbeiter.objects.all()}

    kalender_daten = {}
    current_date = schichtplan.start_datum

    # Bereite die Kalender-Daten vor
    while current_date <= schichtplan.ende_datum:
        tag_schichten = schichten.filter(datum=current_date)
        kalender_daten[current_date] = {
            'datum': current_date,
            'wochentag': day_name[current_date.weekday()],
            'schichten': tag_schichten,
            'ist_wochenende': current_date.weekday() >= 5,
        }
        current_date += timedelta(days=1)

    # Mitarbeiter-Statistik
    mitarbeiter_stats = Mitarbeiter.objects.filter(
        schichten__schichtplan=schichtplan
    ).annotate(
        anzahl_schichten=Count('schichten')
    ).order_by('-anzahl_schichten')

    # Übergib das Mapping zu den Mitarbeiternamen an das Template
    context = {
        'schichtplan': schichtplan,
        'kalender_daten': kalender_daten,
        'mitarbeiter_stats': mitarbeiter_stats,
        'schichttypen': Schichttyp.objects.filter(aktiv=True),
        'mitarbeiter_mapping': mitarbeiter_mapping,  # Das Mapping hier hinzufügen
    }

    return render(request, 'schichtplan/schichtplan_detail.html', context)



@login_required
def schicht_zuweisen(request, schichtplan_pk):
    """Schicht manuell zuweisen"""
    schichtplan = get_object_or_404(Schichtplan, pk=schichtplan_pk)
    
    if not ist_schichtplaner(request.user):
        return JsonResponse({'error': 'Keine Berechtigung'}, status=403)
    
    if request.method == 'POST':
        form = SchichtForm(request.POST)
        
        if form.is_valid():
            schicht = form.save(commit=False)
            schicht.schichtplan = schichtplan
            
            try:
                schicht.save()
                messages.success(request, "✅ Schicht erfolgreich zugewiesen!")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'schicht_id': schicht.pk,
                    })
                
                return redirect('schichtplan:detail', pk=schichtplan.pk)
                
            except Exception as e:
                messages.error(request, f"❌ Fehler beim Speichern: {e}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': str(e)}, status=400)
        
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': form.errors}, status=400)
    
    else:
        form = SchichtForm()
    
    context = {
        'schichtplan': schichtplan,
        'form': form,
    }
    
    return render(request, 'schichtplan/schicht_zuweisen.html', context)


@login_required
def schicht_loeschen(request, pk):
    """Schicht löschen"""
    schicht = get_object_or_404(Schicht, pk=pk)
    
    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung.")
        return redirect('schichtplan:dashboard')
    
    schichtplan_pk = schicht.schichtplan.pk
    
    if request.method == 'POST':
        schicht.delete()
        messages.success(request, "✅ Schicht wurde gelöscht.")
        return redirect('schichtplan:detail', pk=schichtplan_pk)
    
    context = {
        'schicht': schicht,
    }
    
    return render(request, 'schichtplan/schicht_loeschen_confirm.html', context)


@login_required
def wuensche_genehmigen(request, periode_id):
    """Schichtplaner genehmigt Wünsche"""
    if not ist_schichtplaner(request.user):
        messages.error(request, "❌ Keine Berechtigung.")
        return redirect('schichtplan:dashboard')
    
    periode = get_object_or_404(SchichtwunschPeriode, pk=periode_id)
    
    context = {
        'periode': periode,
    }
    
    return render(request, 'schichtplan/wuensche_genehmigen.html', context)
