
from django.urls import path
from . import views

app_name = 'arbeitszeit'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Registrierung
    path('register/', views.register, name='register'),
    
    # Arbeitszeitvereinbarungen
    
    path('vereinbarung/neu/', views.vereinbarung_erstellen, name='vereinbarung_erstellen'),
    path('vereinbarung/<int:pk>/', views.vereinbarung_detail, name='vereinbarung_detail'),
    path('vereinbarungen/', views.vereinbarung_liste, name='vereinbarung_liste'),
    
    # Zeiterfassung
    path('zeiterfassung/neu/', views.zeiterfassung_erstellen, name='zeiterfassung_erstellen'),
    path('zeiterfassung/', views.zeiterfassung_uebersicht, name='zeiterfassung_uebersicht'),
    
    # Admin/Vorgesetzte
    path('verwaltung/', views.admin_dashboard, name='admin_dashboard'),  # NEU!
    path('verwaltung/vereinbarungen/', views.admin_vereinbarungen_genehmigen, name='admin_vereinbarungen'),
    path('verwaltung/vereinbarung/<int:pk>/genehmigen/', views.admin_vereinbarung_genehmigen, name='admin_vereinbarung_genehmigen'),
    path('verwaltung/vereinbarung/<int:pk>/loeschen/', views.admin_vereinbarung_loeschen, name='admin_vereinbarung_loeschen'),
    path('verwaltung/mitarbeiter/', views.mitarbeiter_uebersicht, name='mitarbeiter_uebersicht'),
    path('verwaltung/vereinbarung/<int:pk>/docx/', views.admin_vereinbarung_docx_export, name='admin_vereinbarung_docx'),
    path('verwaltung/vereinbarung/<int:pk>/pdf/', views.admin_vereinbarung_pdf_export, name='admin_vereinbarung_pdf'),
]