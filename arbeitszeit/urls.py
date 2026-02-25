
from django.urls import path
from . import views
from . import views_debug

app_name = 'arbeitszeit'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    
    # Vereinbarungen
    path('vereinbarung/neu/', views.vereinbarung_erstellen, name='vereinbarung_erstellen'),
    path('vereinbarung/<int:pk>/', views.vereinbarung_detail, name='vereinbarung_detail'),
    path('vereinbarungen/', views.vereinbarung_liste, name='vereinbarung_liste'),
    
    # Zeiterfassung
    path('zeiterfassung/neu/', views.zeiterfassung_erstellen, name='zeiterfassung_erstellen'),
    path('zeiterfassung/', views.zeiterfassung_uebersicht, name='zeiterfassung_uebersicht'),
    path('zeiterfassung/wochenbericht/', views.wochenbericht_pdf, name='wochenbericht_pdf'),
    path('zeiterfassung/wochenbericht-csv/', views.wochenbericht_csv, name='wochenbericht_csv'),
    path('zeiterfassung/monatsbericht/', views.monatsbericht_pdf, name='monatsbericht_pdf'),
    path('zeiterfassung/monatsbericht-csv/', views.monatsbericht_csv, name='monatsbericht_csv'),
    path('zeiterfassung/<int:pk>/loeschen/', views.zeiterfassung_loeschen, name='zeiterfassung_loeschen'),
    path('zeiterfassung/saldo/', views.saldo_korrektur, name='saldo_korrektur'),
    path('zeiterfassung/saldo/<int:pk>/loeschen/', views.saldo_korrektur_loeschen, name='saldo_korrektur_loeschen'),
    
    # Verwaltung
    path('verwaltung/', views.admin_dashboard, name='admin_dashboard'),
    path('verwaltung/vereinbarung/<int:pk>/genehmigen/', views.admin_vereinbarung_genehmigen, name='admin_vereinbarung_genehmigen'),
    path('verwaltung/vereinbarungen/', views.admin_vereinbarungen_genehmigen, name='admin_vereinbarungen'),
    path('verwaltung/vereinbarung/<int:pk>/loeschen/', views.admin_vereinbarung_loeschen, name='admin_vereinbarung_loeschen'),
    
    # Mitarbeiter
    path('verwaltung/mitarbeiter/', views.mitarbeiter_uebersicht, name='mitarbeiter_uebersicht'),
    path('verwaltung/mitarbeiter/<int:pk>/', views.mitarbeiter_detail, name='mitarbeiter_detail'),  # ← NEU!
    
    # Dokumente
    path('verwaltung/vereinbarung/<int:pk>/docx/', views.admin_vereinbarung_docx_export, name='admin_vereinbarung_docx'),
    path('verwaltung/vereinbarung/<int:pk>/pdf/', views.admin_vereinbarung_pdf_export, name='admin_vereinbarung_pdf'),

     # Soll-Stunden
    path(
        'soll-stunden/',
        views.soll_stunden_dashboard,
        name='soll_stunden_dashboard'
    ),
    path(
        'soll-stunden/berechnen/',
        views.soll_stunden_berechnen,
        name='soll_stunden_berechnen'
    ),
    path(
        'soll-stunden/jahresuebersicht/',
        views.soll_stunden_jahresuebersicht,
        name='soll_stunden_jahresuebersicht'
    ),
    path(
        'mitarbeiter/<int:pk>/soll-stunden/',
        views.mitarbeiter_soll_uebersicht,
        name='mitarbeiter_soll_uebersicht'
    ),

    # Debug (nur fuer Staff/Admin)
    path('debug/berechtigungen/', views_debug.debug_berechtigungen, name='debug_berechtigungen'),
]