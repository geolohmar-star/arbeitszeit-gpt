# Django Arbeitszeitverwaltung - Dokumentation

## Übersicht

Dieses Django-System ermöglicht die vollständige Verwaltung von Arbeitszeiten pro Mitarbeiter, einschließlich:

- Arbeitszeitvereinbarungen (Weiterbewilligung, Verringerung, Erhöhung)
- Regelmäßige und individuelle Wochenverteilung
- Zeiterfassung
- Urlaubsverwaltung
- Genehmigungsworkflow für Vorgesetzte

## Installation

### 1. Projekt-Setup

```bash
# In Ihrer Django-App (z.B. 'arbeitszeit')
python manage.py makemigrations
python manage.py migrate
```

### 2. URLs einbinden

In Ihrer Hauptprojekt `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('arbeitszeit/', include('arbeitszeit.urls')),
]
```

### 3. Settings anpassen

In `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    'arbeitszeit',
]

# Optional: Login/Logout URLs
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/arbeitszeit/'
```

## Datenmodell

### Mitarbeiter
- Stammdaten (Name, Personalnummer, Abteilung, Standort)
- Verknüpfung mit Django User
- Automatische Ermittlung der aktuellen Vereinbarung

### Arbeitszeitvereinbarung
- **Antragsart**: Weiterbewilligung, Verringerung, Erhöhung
- **Typ**: Regelmäßig oder Individuelle Wochenverteilung
- **Regelmäßig**: Wochenstunden → automatische Berechnung der Tageszeit
- **Individuell**: Stundenangabe pro Wochentag → automatische Summenberechnung
- **Status**: Entwurf, Beantragt, Genehmigt, Aktiv, Beendet, Abgelehnt
- **Gültigkeit**: Ab-Datum, Bis-Datum (optional)
- **Telearbeit-Option**

### Tagesarbeitszeit
- Einzelne Stundenangaben für individuelle Wochenverteilung
- Format: Zeitwert (z.B. 830 = 8:30 Uhr)
- Automatische Formatierung

### Historie
- Vollständige Nachverfolgung aller Statusänderungen
- Wer, Wann, Was wurde geändert

### Zeiterfassung
- Tägliche Arbeitszeiterfassung
- Arbeitsbeginn, Arbeitsende, Pausen
- Automatische Berechnung der Arbeitszeit
- Unterscheidung: Büro, Homeoffice, Urlaub, Krank

### Urlaubsanspruch
- Berechnung basierend auf Arbeitszeit
- Vollzeit vs. Teilzeit-Anspruch
- Resturlaubsberechnung

## Workflow

### Mitarbeiter-Workflow

1. **Antrag erstellen**
   - Mitarbeiter füllt Formular aus (wie im HTML-Template)
   - Wählt Antragsart und Typ
   - System erstellt Vereinbarung mit Status "Beantragt"

2. **Status verfolgen**
   - Dashboard zeigt aktuelle Vereinbarung
   - Übersicht aller Anträge mit Status

3. **Zeiterfassung**
   - Täglich Arbeitszeiten erfassen
   - Übersicht mit Monatsstatistiken

### Vorgesetzten-Workflow

1. **Anträge prüfen**
   - Liste offener Anträge
   - Detailansicht mit allen Informationen

2. **Genehmigung**
   - Genehmigen → Status "Genehmigt"
   - Aktivieren → Status "Aktiv" (ab Gültigkeitsdatum)
   - Ablehnen → Status "Abgelehnt"

3. **Mitarbeiterübersicht**
   - Alle Mitarbeiter mit aktueller Vereinbarung
   - Filter nach Abteilung/Standort

## Views & URLs

### Mitarbeiter-URLs
```
/arbeitszeit/                           - Dashboard
/arbeitszeit/vereinbarung/neu/          - Neue Vereinbarung erstellen
/arbeitszeit/vereinbarung/<id>/         - Vereinbarung Details
/arbeitszeit/vereinbarungen/            - Alle Vereinbarungen
/arbeitszeit/zeiterfassung/neu/         - Zeit erfassen
/arbeitszeit/zeiterfassung/             - Zeiterfassungs-Übersicht
```

### Admin-URLs (nur für Vorgesetzte)
```
/arbeitszeit/admin/vereinbarungen/              - Offene Anträge
/arbeitszeit/admin/vereinbarung/<id>/genehmigen/ - Antrag genehmigen
/arbeitszeit/admin/mitarbeiter/                 - Mitarbeiterübersicht
```

## Django Admin Integration

Das System ist vollständig in Django Admin integriert:

- **Mitarbeiter**: Stammdatenverwaltung
- **Arbeitszeitvereinbarungen**: Mit Inline-Tageszeiten und Historie
- **Bulk-Aktionen**: Genehmigen, Aktivieren, Ablehnen
- **Filter & Suche**: Nach Status, Abteilung, Standort, Datum
- **Zeiterfassung**: Tägliche Zeiten verwalten
- **Urlaubsanspruch**: Jahresverwaltung

## Formular-Integration

Das HTML-Formular aus `arbeitszeit_antrag_template.html` kann direkt verwendet werden:

1. **Template einbinden**:
   ```python
   # In views.py
   return render(request, 'arbeitszeit/vereinbarung_form.html', context)
   ```

2. **Formular verarbeiten**:
   - Die `vereinbarung_erstellen` View verarbeitet POST-Daten
   - Erstellt Vereinbarung und Tagesarbeitszeiten
   - Speichert in Datenbank

3. **JavaScript-Logik**:
   - Bereits im Template enthalten
   - Automatische Berechnungen
   - Show/Hide für Regelmäßig/Individuell

## Berechtigungen

### Mitarbeiter (normale User)
- Eigene Vereinbarungen erstellen und ansehen
- Eigene Zeiterfassung

### Vorgesetzte (is_staff=True)
- Alle Vereinbarungen sehen und genehmigen
- Mitarbeiterübersicht
- Zeiterfassungen aller Mitarbeiter

### Admin (is_superuser=True)
- Vollzugriff auf Django Admin
- Alle Funktionen

## Erweiterungsmöglichkeiten

### 1. Automatische Benachrichtigungen
```python
# In signals.py
from django.db.models.signals import post_save
from django.core.mail import send_mail

@receiver(post_save, sender=Arbeitszeitvereinbarung)
def notify_status_change(sender, instance, created, **kwargs):
    if instance.status == 'genehmigt':
        send_mail(
            'Ihre Arbeitszeitvereinbarung wurde genehmigt',
            f'Ihre Vereinbarung ab {instance.gueltig_ab} wurde genehmigt.',
            'noreply@firma.de',
            [instance.mitarbeiter.user.email],
        )
```

### 2. Kalenderintegration
```python
# Export zu iCal/Google Calendar
def export_arbeitszeiten_kalender(mitarbeiter):
    vereinbarung = mitarbeiter.get_aktuelle_vereinbarung()
    # Generiere .ics Datei mit Arbeitszeiten
```

### 3. Statistiken & Reports
```python
# In views.py
def jahresbericht(request, mitarbeiter_id, jahr):
    # Generiere PDF mit Jahresübersicht
    # - Alle Vereinbarungen
    # - Gesamte Arbeitszeit
    # - Urlaubsübersicht
```

### 4. API für mobile App
```python
# Mit Django REST Framework
from rest_framework import viewsets

class ArbeitszeitvereinbarungViewSet(viewsets.ModelViewSet):
    queryset = Arbeitszeitvereinbarung.objects.all()
    serializer_class = ArbeitszeitvereinbarungSerializer
    permission_classes = [IsAuthenticated]
```

### 5. Excel-Export
```python
import openpyxl

def export_zeiterfassung_excel(mitarbeiter, monat, jahr):
    # Erstelle Excel-Datei mit Monatsdaten
    workbook = openpyxl.Workbook()
    # ... Excel-Generierung
```

## Best Practices

### 1. Datenvalidierung
- Prüfe, dass Wochenstunden zwischen 2-48 liegen
- Validiere, dass gueltig_bis >= gueltig_ab
- Prüfe Überschneidungen bei Vereinbarungen

### 2. Status-Management
- Nur genehmigte Vereinbarungen können aktiviert werden
- Aktive Vereinbarungen können nicht mehr bearbeitet werden
- Historie bei jeder Statusänderung

### 3. Performance
- Select Related nutzen für Foreign Keys
- Prefetch Related für Many-to-Many
- Indizes auf häufig gefilterte Felder

### 4. Sicherheit
- @login_required für alle Views
- Prüfe Berechtigung (Mitarbeiter sieht nur eigene Daten)
- CSRF-Protection in Formularen

## Testbeispiele

```python
# tests.py
from django.test import TestCase
from django.contrib.auth.models import User
from .models import Mitarbeiter, Arbeitszeitvereinbarung

class ArbeitszeitvereinbarungTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user('testuser', 'test@test.de', 'password')
        self.mitarbeiter = Mitarbeiter.objects.create(
            user=user,
            personalnummer='12345',
            nachname='Mustermann',
            vorname='Max',
            abteilung='IT',
            standort='siegburg',
            eintrittsdatum='2020-01-01'
        )
    
    def test_vereinbarung_erstellen(self):
        vereinbarung = Arbeitszeitvereinbarung.objects.create(
            mitarbeiter=self.mitarbeiter,
            antragsart='weiterbewilligung',
            arbeitszeit_typ='regelmaessig',
            wochenstunden=38.5,
            gueltig_ab='2025-02-01',
            status='beantragt'
        )
        
        self.assertEqual(vereinbarung.tagesarbeitszeit, '7:42h')
    
    def test_aktuelle_vereinbarung(self):
        # Test get_aktuelle_vereinbarung Methode
        pass
```

## Support & Wartung

- Regelmäßige Backups der Datenbank
- Log-Dateien für Fehlersuche
- Monitoring der Genehmigungszeiten
- Jährliche Anpassung Urlaubsansprüche

## Lizenz

Dieses System ist für interne Verwendung konzipiert.
