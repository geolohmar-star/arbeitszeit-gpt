"""
Django Views für Arbeitszeitverwaltung
"""
import io
from collections import defaultdict
from datetime import datetime, date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum, Case, When, IntegerField
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
# WICHTIG: Import für den Template-Filter-Workaround
from django.template.defaulttags import register

from .models import (
    Mitarbeiter,
    Arbeitszeitvereinbarung,
    Tagesarbeitszeit,
    ArbeitszeitHistorie,
    Zeiterfassung,
    Urlaubsanspruch,
)
from .forms import RegisterForm

# --- CUSTOM TEMPLATE FILTER (WORKAROUND) ---
@register.filter(name='mod')
def mod(value, arg):
    try:
        return int(value) % int(arg)
    except (ValueError, TypeError):
        return 0

# --- HELPER FUNKTIONEN ---

def _get_wochentag_sortierung():
    return Case(
        When(wochentag='montag', then=1),
        When(wochentag='dienstag', then=2),
        When(wochentag='mittwoch', then=3),
        When(wochentag='donnerstag', then=4),
        When(wochentag='freitag', then=5),
        When(wochentag='samstag', then=6),
        When(wochentag='sonntag', then=7),
        default=99,
        output_field=IntegerField(),
    )

def zeitwert_to_str(minuten):
    """Minuten in HH:MM umwandeln."""
    if minuten is None:
        return "0:00"
    stunden = minuten // 60
    rest_minuten = minuten % 60
    return f"{stunden}:{rest_minuten:02d}"

def get_zeitoptionen():
    zeitoptionen = [{'value': 0, 'label': 'Frei'}]
    for hour in range(2, 13):
        for minute in range(0, 60, 15):
            if hour == 12 and minute > 15:
                break
            value = hour * 60 + minute
            label = f"{hour:02d}:{minute:02d}"
            zeitoptionen.append({'value': value, 'label': label})
    return zeitoptionen

# --- VIEWS ---

def vereinbarung_detail(request, pk):
    vereinbarung = get_object_or_404(Arbeitszeitvereinbarung, pk=pk)

    # Arbeitszeiten laden und sortieren
    arbeitszeiten = vereinbarung.tagesarbeitszeiten.annotate(
        sort_order=_get_wochentag_sortierung()
    ).order_by('woche', 'sort_order')
    
    # Gruppieren
    temp_grouped = defaultdict(list)
    for ta in arbeitszeiten:
        ta.display_zeit = zeitwert_to_str(ta.zeitwert)
        temp_grouped[ta.woche].append(ta)

    # Struktur für Template bauen: { woche: { 'tage': [...], 'summe': 'HH:MM' } }
    wochen_daten = {}
    for woche, tage in temp_grouped.items():
        gesamt_minuten = sum(t.zeitwert for t in tage if t.zeitwert)
        wochen_daten[woche] = {
            'tage': tage,
            'summe': zeitwert_to_str(gesamt_minuten)
        }

    historie = ArbeitszeitHistorie.objects.filter(vereinbarung=vereinbarung).order_by('aenderung_am')

    context = {
        'vereinbarung': vereinbarung,
        'wochen_daten': wochen_daten, # Neuer Name für strukturierte Daten
        'historie': historie,
    }
    return render(request, 'arbeitszeit/vereinbarung_detail.html', context)


@login_required
def dashboard(request):
    user = request.user
    if hasattr(user, 'mitarbeiter'):
        rolle = user.mitarbeiter.rolle
        if rolle == 'sachbearbeiter':
            return redirect('arbeitszeit:admin_dashboard')
        if rolle == 'schichtplaner':
            return redirect('schichtplan:dashboard')
    
    mitarbeiter, created = Mitarbeiter.objects.get_or_create(
        user=user,
        defaults={
            'personalnummer': f'MA{user.id:04d}',
            'vorname': user.first_name or 'Vorname',
            'nachname': user.last_name or 'Nachname',
            'abteilung': 'Allgemein',
            'standort': 'siegburg',
            'eintrittsdatum': date.today(),
            'aktiv': True
        }
    )
    if created:
        messages.info(request, "Ihr Mitarbeiter-Profil wurde erstellt.")
    
    aktuelle_vereinbarung = mitarbeiter.get_aktuelle_vereinbarung()
    letzte_erfassungen = mitarbeiter.zeiterfassungen.all().order_by('-datum')[:10]
    
    aktuelles_jahr = timezone.now().year
    urlaubsanspruch = mitarbeiter.urlaubsansprueche.filter(jahr=aktuelles_jahr).first()
    
    alle_vereinbarungen = mitarbeiter.arbeitszeitvereinbarungen.all().order_by('-created_at')[:5]
    
    context = {
        'mitarbeiter': mitarbeiter,
        'aktuelle_vereinbarung': aktuelle_vereinbarung,
        'letzte_erfassungen': letzte_erfassungen,
        'urlaubsanspruch': urlaubsanspruch,
        'alle_vereinbarungen': alle_vereinbarungen,
        'user': user,
    }
    return render(request, 'arbeitszeit/dashboard.html', context)


@login_required
def vereinbarung_erstellen(request):
    try:
        mitarbeiter = request.user.mitarbeiter
    except Mitarbeiter.DoesNotExist:
        messages.error(request, "Kein Mitarbeiterprofil gefunden.")
        return redirect('arbeitszeit:dashboard')

    tage_list = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag']
    
    if request.method == 'POST':
        antragsart = request.POST.get('antragsart')
        arbeitszeit_typ = request.POST.get('arbeitszeit_typ')
        gueltig_ab = request.POST.get('gueltig_ab')
        gueltig_bis = request.POST.get('gueltig_bis') or None
        telearbeit = bool(request.POST.get('telearbeit'))

        vereinbarung = Arbeitszeitvereinbarung.objects.create(
            mitarbeiter=mitarbeiter,
            antragsart=antragsart,
            arbeitszeit_typ=arbeitszeit_typ,
            gueltig_ab=gueltig_ab,
            gueltig_bis=gueltig_bis,
            telearbeit=telearbeit,
            status='beantragt'
        )

        if arbeitszeit_typ == 'individuell':
            week = 1
            while True:
                found_in_week = False
                for tag in tage_list:
                    key = f'neuantrag_{tag}_{week}'
                    if key in request.POST:
                        found_in_week = True
                        zeitwert_str = request.POST.get(key)
                        if zeitwert_str:
                            try:
                                stunden, minuten = map(int, zeitwert_str.split(':'))
                                wert = stunden * 60 + minuten
                                Tagesarbeitszeit.objects.create(
                                    vereinbarung=vereinbarung,
                                    wochentag=tag,
                                    zeitwert=wert,
                                    woche=week
                                )
                            except ValueError:
                                continue
                
                if not found_in_week:
                    break
                week += 1
        else:
            try:
                wochenstunden = float(request.POST.get('wochenstunden', 0))
            except ValueError:
                wochenstunden = 0
            
            minuten_pro_tag = int((wochenstunden * 60) / 5)
            
            for tag in tage_list:
                Tagesarbeitszeit.objects.create(
                    vereinbarung=vereinbarung,
                    wochentag=tag,
                    zeitwert=minuten_pro_tag,
                    woche=1
                )

        messages.success(request, "Die Arbeitszeitvereinbarung wurde beantragt.")
        return redirect('arbeitszeit:dashboard')

    return render(request, 'arbeitszeit/vereinbarung_form.html', {'tage_list': tage_list})


@login_required
def vereinbarung_liste(request):
    try:
        mitarbeiter = request.user.mitarbeiter
    except Mitarbeiter.DoesNotExist:
        return redirect('arbeitszeit:dashboard')
    
    vereinbarungen = mitarbeiter.arbeitszeitvereinbarungen.all().order_by('-created_at')
    
    status_filter = request.GET.get('status')
    if status_filter:
        vereinbarungen = vereinbarungen.filter(status=status_filter)
    
    context = {
        'mitarbeiter': mitarbeiter,
        'vereinbarungen': vereinbarungen,
        'status_filter': status_filter,
    }
    return render(request, 'arbeitszeit/vereinbarung_liste.html', context)


@login_required
def zeiterfassung_erstellen(request):
    try:
        mitarbeiter = request.user.mitarbeiter
    except Mitarbeiter.DoesNotExist:
        return redirect('arbeitszeit:dashboard')
    
    datum = request.POST.get('datum', timezone.now().date())
    
    if request.method == 'POST':
        pause = request.POST.get('pause_minuten', '0')
        if not pause.isdigit():
            pause = 0
            
        Zeiterfassung.objects.update_or_create(
            mitarbeiter=mitarbeiter,
            datum=datum,
            defaults={
                'arbeitsbeginn': request.POST.get('arbeitsbeginn') or None,
                'arbeitsende': request.POST.get('arbeitsende') or None,
                'pause_minuten': int(pause),
                'art': request.POST.get('art', 'buero'),
                'bemerkung': request.POST.get('bemerkung', ''),
            }
        )
        messages.success(request, 'Zeiterfassung wurde gespeichert.')
        return redirect('arbeitszeit:zeiterfassung_uebersicht')
    
    erfassung = Zeiterfassung.objects.filter(mitarbeiter=mitarbeiter, datum=datum).first()
    
    context = {
        'mitarbeiter': mitarbeiter,
        'datum': datum,
        'erfassung': erfassung,
    }
    return render(request, 'arbeitszeit/zeiterfassung_form.html', context)


@login_required
def zeiterfassung_uebersicht(request):
    try:
        mitarbeiter = request.user.mitarbeiter
    except Mitarbeiter.DoesNotExist:
        return redirect('arbeitszeit:dashboard')
    
    jahr = int(request.GET.get('jahr', timezone.now().year))
    monat = int(request.GET.get('monat', timezone.now().month))
    
    erfassungen = mitarbeiter.zeiterfassungen.filter(
        datum__year=jahr,
        datum__month=monat
    ).order_by('datum')
    
    gesamt_minuten = erfassungen.aggregate(total=Sum('arbeitszeit_minuten'))['total'] or 0
    
    context = {
        'mitarbeiter': mitarbeiter,
        'erfassungen': erfassungen,
        'jahr': jahr,
        'monat': monat,
        'gesamt_arbeitszeit': zeitwert_to_str(gesamt_minuten) + "h",
    }
    return render(request, 'arbeitszeit/zeiterfassung_uebersicht.html', context)


# --- ADMIN VIEWS ---

@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, "Sie haben keine Berechtigung für diese Seite.")
        return redirect('arbeitszeit:dashboard')
    
    heute = timezone.now()
    monatsanfang = heute.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    stats = {
        'offene_antraege': Arbeitszeitvereinbarung.objects.filter(status='beantragt').count(),
        'gesamt_mitarbeiter': Mitarbeiter.objects.filter(aktiv=True).count(),
        'genehmigte_vereinbarungen': Arbeitszeitvereinbarung.objects.filter(
            status='genehmigt', genehmigt_am__gte=monatsanfang
        ).count(),
        'aktive_vereinbarungen': Arbeitszeitvereinbarung.objects.filter(status='aktiv').count(),
        'mitarbeiter_siegburg': Mitarbeiter.objects.filter(aktiv=True, standort='siegburg').count(),
        'mitarbeiter_bonn': Mitarbeiter.objects.filter(aktiv=True, standort='bonn').count(),
    }
    
    letzte_aktivitaeten = Arbeitszeitvereinbarung.objects.filter(
        created_at__gte=heute.date()
    ).select_related('mitarbeiter').order_by('-created_at')[:5]
    
    context = {**stats, 'letzte_aktivitaeten': letzte_aktivitaeten}
    return render(request, 'arbeitszeit/admin_dashboard.html', context)


@login_required
def admin_vereinbarungen_genehmigen(request):
    if not request.user.is_staff:
        return redirect('arbeitszeit:dashboard')
    
    offene_antraege = Arbeitszeitvereinbarung.objects.filter(
        status='beantragt'
    ).select_related('mitarbeiter').order_by('-created_at')
    
    alle_vereinbarungen = Arbeitszeitvereinbarung.objects.select_related(
        'mitarbeiter'
    ).order_by('-created_at')
    
    context = {
        'offene_antraege': offene_antraege,
        'alle_vereinbarungen': alle_vereinbarungen,
    }
    return render(request, 'arbeitszeit/admin_vereinbarungen.html', context)


@login_required
def admin_vereinbarung_genehmigen(request, pk):
    """Einzelne Vereinbarung genehmigen (Detailansicht für Admin)"""
    if not request.user.is_staff:
        return redirect('arbeitszeit:dashboard')
    
    vereinbarung = get_object_or_404(Arbeitszeitvereinbarung, pk=pk)
    
    if request.method == 'POST':
        aktion = request.POST.get('aktion')
        bemerkung = request.POST.get('bemerkung', '')
        alter_status = vereinbarung.status
        
        if aktion == 'genehmigen':
            vereinbarung.status = 'genehmigt'
            vereinbarung.genehmigt_von = request.user
            vereinbarung.genehmigt_am = timezone.now()
            messages.success(request, 'Vereinbarung wurde genehmigt.')
        elif aktion == 'aktivieren':
            vereinbarung.status = 'aktiv'
            messages.success(request, 'Vereinbarung wurde aktiviert.')
        elif aktion == 'ablehnen':
            vereinbarung.status = 'abgelehnt'
            messages.warning(request, 'Vereinbarung wurde abgelehnt.')
        
        vereinbarung.save()
        
        ArbeitszeitHistorie.objects.create(
            vereinbarung=vereinbarung,
            aenderung_durch=request.user,
            alter_status=alter_status,
            neuer_status=vereinbarung.status,
            bemerkung=bemerkung
        )
        return redirect('arbeitszeit:admin_vereinbarungen')
    
    # Sortierung mittels Helper
    tagesarbeitszeiten = vereinbarung.tagesarbeitszeiten.annotate(
        sort_order=_get_wochentag_sortierung()
    ).order_by('woche', 'sort_order')
    
    temp_grouped = defaultdict(list)
    for tag in tagesarbeitszeiten:
        tag.display_zeit = zeitwert_to_str(tag.zeitwert)
        temp_grouped[tag.woche].append(tag)
    
    # Auch hier: Strukturierte Daten mit Summe
    wochen_daten = {}
    for woche, tage in temp_grouped.items():
        gesamt_minuten = sum(t.zeitwert for t in tage if t.zeitwert)
        wochen_daten[woche] = {
            'tage': tage,
            'summe': zeitwert_to_str(gesamt_minuten)
        }
    
    context = {
        'vereinbarung': vereinbarung,
        'wochen_daten': wochen_daten,
        'zeitoptionen': get_zeitoptionen(),
    }
    return render(request, 'arbeitszeit/admin_vereinbarung_detail.html', context)


@login_required
def mitarbeiter_uebersicht(request):
    is_schichtplaner = hasattr(request.user, 'mitarbeiter') and request.user.mitarbeiter.rolle == 'schichtplaner'
    
    if not (request.user.is_staff or is_schichtplaner):
        messages.error(request, "Keine Berechtigung.")
        return redirect('arbeitszeit:dashboard')
    
    mitarbeiter_liste = Mitarbeiter.objects.filter(aktiv=True)
    
    if not request.user.is_staff and is_schichtplaner:
        eigene_abteilung = request.user.mitarbeiter.abteilung
        mitarbeiter_liste = mitarbeiter_liste.filter(abteilung=eigene_abteilung)
    
    abteilung_filter = request.GET.get('abteilung')
    standort_filter = request.GET.get('standort')
    
    if abteilung_filter and request.user.is_staff:
        mitarbeiter_liste = mitarbeiter_liste.filter(abteilung=abteilung_filter)
    
    if standort_filter:
        mitarbeiter_liste = mitarbeiter_liste.filter(standort=standort_filter)

    context = {
        'mitarbeiter_liste': mitarbeiter_liste,
        'abteilung_filter': abteilung_filter,
        'standort_filter': standort_filter,
        'anzahl_siegburg': mitarbeiter_liste.filter(standort='siegburg').count(),
        'anzahl_bonn': mitarbeiter_liste.filter(standort='bonn').count(),
    }
    return render(request, 'arbeitszeit/mitarbeiter_uebersicht.html', context)


def register(request):
    if request.user.is_authenticated:
        return redirect('arbeitszeit:dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password1'],
                    first_name=form.cleaned_data['vorname'],
                    last_name=form.cleaned_data['nachname'],
                )
                
                Mitarbeiter.objects.create(
                    user=user,
                    personalnummer=form.cleaned_data['personalnummer'],
                    vorname=form.cleaned_data['vorname'],
                    nachname=form.cleaned_data['nachname'],
                    abteilung=form.cleaned_data['abteilung'],
                    standort=form.cleaned_data['standort'],
                    eintrittsdatum=form.cleaned_data['eintrittsdatum'],
                    aktiv=True
                )
                
                login(request, user)
                messages.success(request, 'Registrierung erfolgreich! Willkommen!')
                return redirect('arbeitszeit:dashboard')
                
            except Exception as e:
                messages.error(request, f'Ein Fehler ist aufgetreten: {str(e)}')
        else:
            messages.error(request, 'Bitte korrigieren Sie die Fehler im Formular.')
    else:
        form = RegisterForm()

    return render(request, 'arbeitszeit/register.html', {'form': form})


@login_required
def admin_vereinbarung_loeschen(request, pk):
    if not request.user.is_staff:
        messages.error(request, "Keine Berechtigung.")
        return redirect('arbeitszeit:dashboard')
    
    vereinbarung = get_object_or_404(Arbeitszeitvereinbarung, pk=pk)
    
    if request.method == 'POST':
        name = vereinbarung.mitarbeiter.vollname
        art = vereinbarung.get_antragsart_display()
        vereinbarung.delete()
        messages.success(request, f'Vereinbarung von {name} ({art}) wurde gelöscht.')
    
    return redirect('arbeitszeit:admin_vereinbarungen')


@login_required
def admin_vereinbarung_docx_export(request, pk):
    """Generiert ein DOCX-Dokument mit Wochen-Gruppierung."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        messages.error(request, "Das Modul 'python-docx' ist nicht installiert.")
        return redirect('arbeitszeit:admin_vereinbarung_genehmigen', pk=pk)

    if not request.user.is_staff:
        return redirect('arbeitszeit:dashboard')
    
    vereinbarung = get_object_or_404(Arbeitszeitvereinbarung, pk=pk)
    
    # 1. Laden und Sortieren
    tagesarbeitszeiten = vereinbarung.tagesarbeitszeiten.annotate(
        sort_order=_get_wochentag_sortierung()
    ).order_by('woche', 'sort_order')
    
    # 2. Gruppieren nach Wochen
    from collections import defaultdict
    wochen_daten = defaultdict(list)
    for tag in tagesarbeitszeiten:
        wochen_daten[tag.woche].append(tag)
    
    # --- DOKUMENT START ---
    doc = Document()
    
    # Layout
    section = doc.sections[0]
    section.page_height = Inches(11.69) # A4
    section.page_width = Inches(8.27)
    section.top_margin = Inches(1)
    
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(11)
    
    # Kopfbereich (Leerzeilen)
    for _ in range(4): doc.add_paragraph()
    
    # Betreff
    betreff_suffix = {
        'weiterbewilligung': ' - Weiterbewilligung',
        'verringerung': ' - Verringerung',
        'erhoehung': ' - Erhöhung',
        'beendigung': ' - Beendigung'
    }.get(vereinbarung.antragsart, '')
    
    p = doc.add_paragraph()
    run = p.add_run(f'Betreff: Flexible Arbeitszeit{betreff_suffix}')
    run.bold = True
    run.font.size = Pt(12)
    
    doc.add_paragraph()
    
    # Stammdaten kurz auflisten
    doc.add_paragraph(f"Mitarbeiter: {vereinbarung.mitarbeiter.vollname}")
    doc.add_paragraph(f"Antragsart: {vereinbarung.get_antragsart_display()}")
    
    gueltig_bis = vereinbarung.gueltig_bis.strftime('%d.%m.%Y') if vereinbarung.gueltig_bis else 'unbefristet'
    doc.add_paragraph(f'Gültig: {vereinbarung.gueltig_ab.strftime("%d.%m.%Y")} bis {gueltig_bis}')
    
    doc.add_paragraph('\nSehr geehrte Damen und Herren,\n')
    doc.add_paragraph('hiermit wird die folgende Arbeitszeitvereinbarung getroffen:\n')
    
    # --- WOCHENVERTEILUNG GENERIEREN ---
    if wochen_daten:
        p = doc.add_paragraph()
        p.add_run('Wochenverteilung:').bold = True
        
        # Schleife über die Wochen (Woche 1, Woche 2, etc.)
        for woche in sorted(wochen_daten.keys()):
            tage = wochen_daten[woche]
            
            # Überschrift für die Woche
            p = doc.add_paragraph()
            run = p.add_run(f"Woche {woche}")
            run.bold = True
            run.font.color.rgb = RGBColor(26, 77, 46) # Dunkelgrün
            
            # Tabelle erstellen
            table = doc.add_table(rows=1, cols=2)
            table.style = 'Table Grid'
            
            # Header Zeile
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'Wochentag'
            hdr_cells[1].text = 'Arbeitszeit'
            
            # Header Styling (Grüner Hintergrund)
            for cell in hdr_cells:
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:fill'), '1a4d2e')
                cell._element.get_or_add_tcPr().append(shading_elm)
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.color.rgb = RGBColor(255, 255, 255)
                        run.bold = True
            
            hdr_cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            
            # Datenzeilen
            wochen_summe = 0
            for tag in tage:
                row_cells = table.add_row().cells
                row_cells[0].text = tag.get_wochentag_display()
                row_cells[1].text = zeitwert_to_str(tag.zeitwert) + " h"
                row_cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                
                if tag.zeitwert:
                    wochen_summe += tag.zeitwert

            # Summenzeile pro Woche hinzufügen
            row_cells = table.add_row().cells
            row_cells[0].text = "Summe"
            row_cells[1].text = zeitwert_to_str(wochen_summe) + " h"
            
            # Summenzeile fett machen & Hintergrund grau
            for cell in row_cells:
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:fill'), 'F0F0F0') # Hellgrau
                cell._element.get_or_add_tcPr().append(shading_elm)
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
            row_cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

            doc.add_paragraph() # Abstand zur nächsten Woche
            
    # --- ENDE DOKUMENT ---

    doc.add_paragraph(f'Diese Vereinbarung gilt vom {vereinbarung.gueltig_ab.strftime("%d.%m.%Y")} bis {gueltig_bis}.')
    doc.add_paragraph('\nMit freundlichen Grüßen\n\n\n_______________________________\nUnterschrift')
    
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    
    response = HttpResponse(
        file_stream.read(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    filename = f"Arbeitszeit_{vereinbarung.mitarbeiter.nachname}_{vereinbarung.pk}.docx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def admin_vereinbarung_pdf_export(request, pk):
    try:
        from weasyprint import HTML
    except ImportError:
        messages.error(request, "Das Modul 'weasyprint' ist nicht installiert.")
        return redirect('arbeitszeit:admin_vereinbarung_genehmigen', pk=pk)

    if not request.user.is_staff:
        return redirect('arbeitszeit:dashboard')
    
    vereinbarung = get_object_or_404(Arbeitszeitvereinbarung, pk=pk)
    
    # Daten laden und sortieren
    tagesarbeitszeiten = vereinbarung.tagesarbeitszeiten.annotate(
        sort_order=_get_wochentag_sortierung()
    ).order_by('woche', 'sort_order')
    
    # DATEN GRUPPIEREN (Wichtig für die "Kästen" pro Woche)
    from collections import defaultdict
    temp_grouped = defaultdict(list)
    
    for tag in tagesarbeitszeiten:
        # Zeit für Anzeige vorbereiten
        tag.display_zeit = zeitwert_to_str(tag.zeitwert)
        temp_grouped[tag.woche].append(tag)
    
    # Strukturierte Daten mit Summen erstellen
    wochen_daten = {}
    # sorted(temp_grouped.keys()) sorgt dafür, dass Woche 1 vor Woche 2 kommt
    for woche in sorted(temp_grouped.keys()):
        tage = temp_grouped[woche]
        gesamt_minuten = sum(t.zeitwert for t in tage if t.zeitwert)
        wochen_daten[woche] = {
            'tage': tage,
            'summe': zeitwert_to_str(gesamt_minuten)
        }
    
    context = {
        'vereinbarung': vereinbarung,
        'wochen_daten': wochen_daten,  # Das ist neu für das PDF
    }
    
    html_string = render_to_string('arbeitszeit/pdf_vereinbarung.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf = html.write_pdf()
    
    response = HttpResponse(pdf, content_type='application/pdf')
    filename = f"Arbeitszeit_{vereinbarung.mitarbeiter.nachname}_{vereinbarung.pk}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def mitarbeiter_detail(request, pk):
    mitarbeiter = get_object_or_404(Mitarbeiter, pk=pk)
    
    is_schichtplaner = hasattr(request.user, 'mitarbeiter') and request.user.mitarbeiter.rolle == 'schichtplaner'
    if not (request.user.is_staff or is_schichtplaner):
        messages.error(request, "Keine Berechtigung.")
        return redirect('arbeitszeit:dashboard')
    
    if request.method == 'POST':
        mitarbeiter.schichtplan_kennung = request.POST.get('schichtplan_kennung', '')
        mitarbeiter.kann_tagschicht = 'kann_tagschicht' in request.POST
        mitarbeiter.kann_nachtschicht = 'kann_nachtschicht' in request.POST
        mitarbeiter.nachtschicht_nur_wochenende = 'nachtschicht_nur_wochenende' in request.POST
        mitarbeiter.nur_zusatzdienste_wochentags = 'nur_zusatzdienste_wochentags' in request.POST
        mitarbeiter.verfuegbarkeit = request.POST.get('verfuegbarkeit', 'voll')
        mitarbeiter.schichtplan_einschraenkungen = request.POST.get('schichtplan_einschraenkungen', '')
        
        try:
            mitarbeiter.max_wochenenden_pro_monat = int(request.POST.get('max_wochenenden_pro_monat', 4))
        except ValueError:
            mitarbeiter.max_wochenenden_pro_monat = 4
        
        mitarbeiter.save()
        messages.success(request, f"Mitarbeiter {mitarbeiter.vollname} aktualisiert!")
        return redirect('schichtplan:mitarbeiter_uebersicht')
    
    return render(request, 'arbeitszeit/mitarbeiter_detail.html', {'mitarbeiter': mitarbeiter})