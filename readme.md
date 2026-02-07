@"
# Arbeitszeit Tracking App

Django-basierte Arbeitszeit- und Schichtplan-Verwaltung mit Supabase PostgreSQL Backend.

## Features
- Arbeitszeiterfassung
- Schichtplanverwaltung
- Urlaubsverwaltung
- Benutzer-Authentifizierung

## Installation

1. Repository klonen:
``````
git clone https://github.com/DEIN-USERNAME/arbeitszeit-app.git
cd arbeitszeit-app
``````

2. Virtuelle Umgebung erstellen:
``````
python -m venv env
.\env\Scripts\Activate.ps1
``````

3. Dependencies installieren:
``````
pip install -r requirements.txt
``````

4. .env Datei erstellen:
``````
DATABASE_URL=your_database_url_here
DEBUG=True
DJANGO_SECRET_KEY=your_secret_key_here
``````

5. Migrationen ausführen:
``````
python manage.py migrate
``````

6. Superuser erstellen:
``````
python manage.py createsuperuser
``````

7. Server starten:
``````
python manage.py runserver
``````

## Tech Stack
- Django 5.x
- PostgreSQL (Supabase)
- WhiteNoise (Static Files)
- Workalendar (Feiertage)
"@ | Out-File -FilePath README.md -Encoding UTF8