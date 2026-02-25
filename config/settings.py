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
    'arbeitszeit.apps.ArbeitszeitConfig',
    'schichtplan',
    'formulare.apps.FormulareConfig',
    'berechtigungen.apps.BerechtigungenConfig',
    'hr.apps.HrConfig',
    'workflow.apps.WorkflowConfig',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
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

# Email-Domain fuer stellenbasierte Adressen
STELLEN_EMAIL_DOMAIN = os.environ.get('STELLEN_EMAIL_DOMAIN', 'firma.de')

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