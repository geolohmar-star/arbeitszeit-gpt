from django.urls import path
from . import views

app_name = 'schichtplan'

urlpatterns = [
    # Dashboard
    path('', views.planer_dashboard, name='dashboard'),
    
    # Schichtplan
    path('erstellen/', views.SchichtplanCreateView.as_view(), name='erstellen'),
    path('<int:pk>/', views.schichtplan_detail, name='detail'),
    
    # Excel-Import
    path('<int:pk>/import/', views.excel_import_view, name='excel_import'),
    path('import/analyse/', views.excel_analyse_view, name='excel_analyse'),
    
    # Mitarbeiter
    path('mitarbeiter/', views.mitarbeiter_uebersicht, name='mitarbeiter_uebersicht'),
    
    # Schichten
    path('<int:schichtplan_pk>/schicht-zuweisen/', views.schicht_zuweisen, name='schicht_zuweisen'),
    path('schicht/<int:pk>/loeschen/', views.schicht_loeschen, name='schicht_loeschen'),
    
    # ========================================================================
    # WUNSCH-SYSTEM
    # ========================================================================
    
    # Listenansicht aller Perioden (für Planer und MA)
    path(
        'wuensche/',
        views.wunsch_perioden_liste,
        name='wunschperioden_liste'
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
]