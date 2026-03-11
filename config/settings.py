from pathlib import Path
import os
from dotenv import load_dotenv
import sys

load_dotenv()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError(
        "Umgebungsvariable DJANGO_SECRET_KEY muss gesetzt sein. "
        "Fuer lokale Entwicklung bitte in .env eintragen."
    )

# DEBUG: Default False – muss explizit auf 'True' gesetzt werden
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# ALLOWED_HOSTS
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'host.docker.internal',
    '.onrender.com',
    'arbeitszeit-gpt.up.railway.app',
    '.railway.app',
    '.up.railway.app',
]

CSRF_TRUSTED_ORIGINS = [
    'https://*.onrender.com',
    'https://arbeitszeit-gpt.up.railway.app',
    'https://*.railway.app',
    'https://*.up.railway.app',
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'guardian',
    'axes',
    'arbeitszeit.apps.ArbeitszeitConfig',
    'schichtplan',
    'formulare.apps.FormulareConfig',
    'berechtigungen.apps.BerechtigungenConfig',
    'hr.apps.HrConfig',
    'workflow.apps.WorkflowConfig',
    'veranstaltungen.apps.VeranstaltungenConfig',
    'facility.apps.FacilityConfig',
    'raumbuch.apps.RaumbuchConfig',
    'signatur.apps.SignaturConfig',
    'datenschutz.apps.DatenschutzConfig',
    'dokumente.apps.DokumenteConfig',
    'bewerbung.apps.BewerbungConfig',
    'stellenportal.apps.StellenportalConfig',
    'betriebssport.apps.BetriebssportConfig',
    'django.contrib.postgres',
    'dms.apps.DmsConfig',
]

# Verschluesselung fuer sensible Dokumente (Fernet AES-128)
# Schluessel generieren: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DOKUMENT_VERSCHLUESSEL_KEY = os.environ.get("DOKUMENT_VERSCHLUESSEL_KEY", "")

# ---------------------------------------------------------------------------
# Signatur-System
# ---------------------------------------------------------------------------
SIGNATUR_BACKEND = os.environ.get("SIGNATUR_BACKEND", "intern")

# ---------------------------------------------------------------------------
# DMS – Dokumentenmanagementsystem
# ---------------------------------------------------------------------------
# AES-256-GCM Schluessel fuer sensible Dokumente (Klasse 2)
# Generieren: python -c "import os; print(os.urandom(32).hex())"
DMS_VERSCHLUESSEL_KEY = os.environ.get("DMS_VERSCHLUESSEL_KEY", "")

# Paperless-ngx Integration (optional)
PAPERLESS_URL = os.environ.get("PAPERLESS_URL", "")
PAPERLESS_TOKEN = os.environ.get("PAPERLESS_TOKEN", "")
SIGNATUR_SIGN_ME_URL = os.environ.get("SIGNATUR_SIGN_ME_URL", "https://api.sign-me.de")
SIGNATUR_SIGN_ME_KEY = os.environ.get("SIGNATUR_SIGN_ME_KEY", "")
SIGNATUR_SIGN_ME_TIMEOUT = 30

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    # Erbt von ModelBackend + verwaltet PBKDF2-Signatur-Schluessel beim Login
    'signatur.auth_backend.SignaturAuthBackend',
    'guardian.backends.ObjectPermissionBackend',
]

# Guardian: Anonymer User bekommt keine Rechte
ANONYMOUS_USER_NAME = None

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
    # Stellt PBKDF2-Signatur-Schluessel aus Session im Thread-Local bereit
    'signatur.middleware.SignaturKeyMiddleware',
    'config.middleware.CSPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'schichtplan' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'arbeitszeit.context_processors.schichtplan_zugang',
                'arbeitszeit.context_processors.genehmiger_rolle',
                'arbeitszeit.context_processors.workflow_tasks_anzahl',
                'arbeitszeit.context_processors.team_stapel_anzahl',
                'arbeitszeit.context_processors.prozessverantwortlicher',
                'arbeitszeit.context_processors.personalgewinnung_kontext',
                'arbeitszeit.context_processors.dms_badge_kontext',
                'arbeitszeit.context_processors.hilfe_kontext',
                'arbeitszeit.context_processors.cmd_items',
                'facility.context_processors.facility_context',
                'stellenportal.context_processors.stellenportal_context',
                'veranstaltungen.context_processors.veranstaltungen_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database - AUTOMATISCH lokal=SQLite, Render/Supabase=PostgreSQL
if os.environ.get('DATABASE_URL'):
    # Production/Supabase: PostgreSQL mit Connection Pooling
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Development: SQLite lokal
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 20,
            },
        }
    }
    
    # WAL-Mode für SQLite aktivieren
    def activate_wal_mode():
        import sqlite3
        db_path = BASE_DIR / 'db.sqlite3'
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.close()
    
    try:
        activate_wal_mode()
    except Exception:
        pass

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'de-de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True
DEFAULT_CHARSET = 'utf-8'
FILE_CHARSET = 'utf-8'

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login/Logout URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Messages
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.ERROR: 'error',
    messages.SUCCESS: 'success',
}

if sys.version_info[0] >= 3:
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
    except:
        pass

# ---------------------------------------------------------------------------
# Virusscanner (ClamAV via Netzwerk)
# Leer lassen solange kein Scanner-Server vorhanden ist.
# Die App laeuft ohne Scanner – Uploads werden dann ohne Pruefung zugelassen.
# ---------------------------------------------------------------------------
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "")          # z.B. "192.168.1.50"
CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT", 3310))   # clamd Standard-Port
CLAMAV_TIMEOUT = int(os.environ.get("CLAMAV_TIMEOUT", 15))
# True = Upload ablehnen wenn Scanner nicht erreichbar (sicherer aber strenger)
CLAMAV_BLOCKIERE_BEI_FEHLER = os.environ.get("CLAMAV_BLOCKIERE_BEI_FEHLER", "False") == "True"

# Email-Domain fuer stellenbasierte Adressen
STELLEN_EMAIL_DOMAIN = os.environ.get('STELLEN_EMAIL_DOMAIN', 'firma.de')

# E-Mail-Versand (intern via Mailpit, spaeter Stalwart)
# Lokal: Mailpit laeuft als Docker-Container auf Port 1025
# Produktion: EMAIL_HOST/PORT per .env ueberschreiben → kein Code-Aenderung noetig
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '1025'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'False') == 'True'
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'prima@prima.intern')

# Workflow-Einstellungen
# Schwellwert fuer GF-Freigabe bei Dienstreisen (in EUR)
DIENSTREISE_GF_FREIGABE_SCHWELLE = 1000

# HTTPS-Sicherheitseinstellungen (nur in Produktion aktiv, d.h. wenn DEBUG=False)
if not DEBUG:
    # Railway/Render terminiert SSL am Load Balancer – kein SSL-Redirect noetig.
    # Stattdessen X-Forwarded-Proto-Header vertrauen damit Django weiss,
    # dass die Verbindung zum Client verschluesselt ist.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000  # 1 Jahr
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# BSI IT-Grundschutz: Session-Sicherheit (ORP.4)
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 28800          # 8 Stunden Sitzungslaenge
SESSION_SAVE_EVERY_REQUEST = True   # Timer bei Aktivitaet zuruecksetzen
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Tab schliessen = abgemeldet

# ---------------------------------------------------------------------------
# BSI IT-Grundschutz: Brute-Force-Schutz (APP.3.1) via django-axes
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 5              # 5 Fehlversuche bis zur Sperre
AXES_COOLOFF_TIME = 1               # 1 Stunde Sperrzeit
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_RESET_ON_SUCCESS = True        # Zaehler nach Erfolg zuruecksetzen
AXES_LOCKOUT_TEMPLATE = "fehler/429.html"
AXES_VERBOSE = False

# ---------------------------------------------------------------------------
# BSI IT-Grundschutz: Logging (OPS.1.1.5)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "prima": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "konsole": {
            "class": "logging.StreamHandler",
            "formatter": "prima",
        },
    },
    "loggers": {
        "django.security": {
            "handlers": ["konsole"],
            "level": "WARNING",
            "propagate": False,
        },
        "axes": {
            "handlers": ["konsole"],
            "level": "WARNING",
            "propagate": False,
        },
        "bewerbung":  {"handlers": ["konsole"], "level": "INFO", "propagate": False},
        "dokumente":  {"handlers": ["konsole"], "level": "INFO", "propagate": False},
        "workflow":   {"handlers": ["konsole"], "level": "INFO", "propagate": False},
        "facility":   {"handlers": ["konsole"], "level": "INFO", "propagate": False},
        "signatur":   {"handlers": ["konsole"], "level": "INFO", "propagate": False},
        "datenschutz":{"handlers": ["konsole"], "level": "INFO", "propagate": False},
        "config.kommunikation_utils": {"handlers": ["konsole"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Kommunikationsintegration: Jitsi Meet + Matrix/Element
# ---------------------------------------------------------------------------
# Alle Werte kommen aus Umgebungsvariablen – leer = Integration deaktiviert.
# Lokal: in .env eintragen. Railway: in den Service-Variablen setzen.

# BentoPDF: URL des selbst betriebenen BentoPDF-Servers (ohne abschliessendes /)
# Beispiel: BENTOPDF_URL=https://pdf.georg-klein.com
BENTOPDF_URL = os.environ.get("BENTOPDF_URL", "")

# OnlyOffice: URL des selbst betriebenen Document Servers (ohne abschliessendes /)
# Beispiel: ONLYOFFICE_URL=https://office.georg-klein.com
ONLYOFFICE_URL = os.environ.get("ONLYOFFICE_URL", "")
# JWT-Secret muss mit dem JWT_SECRET im OnlyOffice docker-compose.yml uebereinstimmen
ONLYOFFICE_JWT_SECRET = os.environ.get("ONLYOFFICE_JWT_SECRET", "")
# Basis-URL unter der PRIMA vom OnlyOffice-Container erreichbar ist
# Lokal: host.docker.internal:8000 (Docker Desktop Windows/Mac)
# Produktion: oeffentliche PRIMA-URL
PRIMA_BASE_URL = os.environ.get("PRIMA_BASE_URL", "http://host.docker.internal:8000")

# Jitsi Meet: Basis-URL des eigenen Jitsi-Servers (ohne abschliessendes /)
# Beispiel: JITSI_BASE_URL=https://meet.intranet.firma.de
JITSI_BASE_URL = os.environ.get("JITSI_BASE_URL", "")

# Matrix/Element: Homeserver-URL + Bot-Token (Zugangstoken eines Bot-Accounts)
# Beispiel: MATRIX_HOMESERVER_URL=https://matrix.intranet.firma.de
MATRIX_HOMESERVER_URL = os.environ.get("MATRIX_HOMESERVER_URL", "")
MATRIX_BOT_TOKEN = os.environ.get("MATRIX_BOT_TOKEN", "")

# Matrix-Raum-ID des Facility-Teams (fuer automatische Stoermeldungs-Pings)
# Format: !raumid:server  – im Element-Client unter Raumeinstellungen abrufbar
MATRIX_FACILITY_ROOM_ID = os.environ.get("MATRIX_FACILITY_ROOM_ID", "")