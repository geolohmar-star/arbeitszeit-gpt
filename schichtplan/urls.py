from django.urls import path
from . import views

app_name = 'schichtplan'

urlpatterns = [
    # Dashboard
    path('', views.planer_dashboard, name='dashboard'),
    
    # Schichtplan
    path('erstellen/', views.SchichtplanCreateView.as_view(), name='erstellen'),
    path('<int:pk>/', views.schichtplan_detail, name='detail'),
    path('<int:pk>/zur-genehmigung/', views.schichtplan_zur_genehmigung, name='zur_genehmigung'),
    path('<int:pk>/veroeffentlichen/', views.schichtplan_veroeffentlichen, name='veroeffentlichen'),
    path('<int:pk>/uebersicht-detail/', views.schichtplan_uebersicht_detail, name='uebersicht_detail'),
    path('<int:pk>/rueckgaengig/', views.schichtplan_rueckgaengig, name='rueckgaengig'),
    path('<int:pk>/export-excel/', views.schichtplan_export_excel, name='export_excel'),
    
    # Excel-Import
    path('<int:pk>/import/', views.excel_import_view, name='excel_import'),
    path('import/analyse/', views.excel_analyse_view, name='excel_analyse'),
    
    # Mitarbeiter
    path('mitarbeiter/', views.mitarbeiter_uebersicht, name='mitarbeiter_uebersicht'),
    
    # Schichten
    path('<int:schichtplan_pk>/schicht-zuweisen/', views.schicht_zuweisen, name='schicht_zuweisen'),
    path('<int:schichtplan_pk>/schicht-anlegen/', views.schicht_anlegen, name='schicht_anlegen'),
    path('schicht/<int:pk>/loeschen/', views.schicht_loeschen, name='schicht_loeschen'),
    path('schicht/<int:pk>/bearbeiten/', views.schicht_bearbeiten, name='schicht_bearbeiten'),
    path('schicht/<int:pk>/tauschen/', views.schicht_tauschen, name='schicht_tauschen'),
    
    # ========================================================================
    # WUNSCH-SYSTEM
    # ========================================================================
    
    # Listenansicht aller Perioden (für Planer und MA)
    path(
        'wuensche/',
        views.wunsch_perioden_liste,
        name='wunschperioden_liste'
    ),
    # Redirect „aktueller Kalender“ → aktuelle/ nächste Wunschperiode oder Dashboard
    path(
        'wuensche/kalender-aktuell/',
        views.wunsch_kalender_aktuell,
        name='wunsch_kalender_aktuell'
    ),
    # Kalenderansicht einer Periode
    path(
        'wuensche/periode/<int:periode_id>/kalender/',
        views.wunsch_kalender,
        name='wunsch_kalender'
    ),
    
    # Wunsch eingeben / bearbeiten
    path(
        'wuensche/periode/<int:periode_id>/eingeben/',
        views.wunsch_eingeben,
        name='wunsch_eingeben'
    ),
    
    # Wunsch löschen
    path(
        'wuensche/<int:wunsch_id>/loeschen/',
        views.wunsch_loeschen,
        name='wunsch_loeschen'
    ),
    
    # NEUE PERIODE ERSTELLEN (Korrektur: Nur ein Pfad, passend zum Dashboard-Button)
    path(
    'wuensche/periode/neu/', 
    views.WunschPeriodeCreateView.as_view(), # Wir nutzen die Klasse!
    name='wunschperiode_erstellen'           # Der Name für den Dashboard-Button
    ),

    # ========================================================================
    # ADMIN / GENEHMIGUNGS-LOGIK
    # ========================================================================
    
    path(
        'wuensche/periode/<int:periode_id>/planer/',
        views.wuensche_schichtplaner_uebersicht,
        name='wuensche_schichtplaner_uebersicht'
    ),
    path(
        'wuensche/<int:wunsch_id>/genehmigen/',
        views.wunsch_genehmigen,
        name='wunsch_genehmigen'
    ),
    path(
        'wuensche/periode/<int:periode_id>/genehmigen/',
        views.wuensche_genehmigen,
        name='wuensche_genehmigen'
    ),
    path(
    'wuensche/', 
    views.wunsch_perioden_liste, 
    name='wunsch_perioden_liste'
),
    
    # Wunschperiode löschen
    path(
        'wuensche/periode/<int:periode_id>/loeschen/',
        views.wunschperiode_loeschen,
        name='wunschperiode_loeschen'
    ),
]
