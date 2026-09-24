import os
from pathlib import Path

import dj_database_url

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment file if present
ENV_PATH = BASE_DIR / '.env'
if ENV_PATH.exists():
    with ENV_PATH.open('r', encoding='utf-8') as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            os.environ.setdefault(key, value)

# SECURITY
default_debug = 'False' if os.getenv('RENDER') else 'True'
DEBUG = os.getenv('DEBUG', os.getenv('DJANGO_DEBUG', default_debug)).lower() in ('true', '1', 'yes', 'on')

configured_secret_key = os.getenv('SECRET_KEY') or os.getenv('DJANGO_SECRET_KEY')
if not configured_secret_key and not DEBUG:
    raise RuntimeError('SECRET_KEY must be configured when DEBUG is disabled.')
SECRET_KEY = configured_secret_key or 'development-only-secret-key'


def _normalize_host(host):
    host = host.strip()
    if not host:
        return ''
    return host.replace('https://', '').replace('http://', '')


def _normalize_origin(origin):
    origin = origin.strip()
    if not origin:
        return ''
    if origin.startswith('http://') or origin.startswith('https://'):
        return origin
    return f'https://{origin}'


allowed_hosts = os.getenv('ALLOWED_HOSTS') or os.getenv('DJANGO_ALLOWED_HOSTS')
render_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME') or os.getenv('RENDER_HOSTNAME')

# Allow all hosts for development/testing
if allowed_hosts:
    ALLOWED_HOSTS = [_normalize_host(host) for host in allowed_hosts.split(',') if host.strip()]
else:
    ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [_normalize_origin(origin) for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
if 'http://207.180.246.69:7038' not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append('http://207.180.246.69:7038')
if render_hostname:
    csrf_origin = f'https://{render_hostname}'
    if csrf_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(csrf_origin)

# ========================
# Installed apps
# ========================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',  # Token authentication

    'vehicles',
    'django_apscheduler',  # required for scheduler
]

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
}

# ========================
# Middleware
# ========================
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

ROOT_URLCONF = 'asset_management.urls'

# ========================
# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'vehicles.context_processors.user_roles',
            ],
        },
    },
]

WSGI_APPLICATION = 'asset_management.wsgi.application'

# ========================
# Database
# ========================
# Prefer PostgreSQL on the VPS / production environment. The app supports either
# a DATABASE_URL value or standard POSTGRES_* environment variables.
if os.getenv('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv('DATABASE_URL'),
            conn_max_age=600,
            ssl_require=False,
        )
    }
else:
    postgres_db = (
        os.getenv('POSTGRES_DB')
        or os.getenv('PGDATABASE')
        or os.getenv('DB_NAME')
    )
    postgres_user = (
        os.getenv('POSTGRES_USER')
        or os.getenv('PGUSER')
        or os.getenv('DB_USER')
    )
    postgres_password = (
        os.getenv('POSTGRES_PASSWORD')
        or os.getenv('PGPASSWORD')
        or os.getenv('DB_PASSWORD')
    )
    postgres_host = (
        os.getenv('POSTGRES_HOST')
        or os.getenv('PGHOST')
        or os.getenv('DB_HOST')
        or 'localhost'
    )
    postgres_port = (
        os.getenv('POSTGRES_PORT')
        or os.getenv('PGPORT')
        or os.getenv('DB_PORT')
        or '5432'
    )

    if postgres_db and postgres_user and postgres_password:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': postgres_db,
                'USER': postgres_user,
                'PASSWORD': postgres_password,
                'HOST': postgres_host,
                'PORT': postgres_port,
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }

# ========================
# Password validation
# ========================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# ========================
# Internationalization
# ========================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# ========================
# Login URL
# ========================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# ========================
# Static files
# ========================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ========================
# Default primary key
# ========================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ========================
# Gmail Email Configuration
# ========================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# Expiry alert email configuration
# NOTE: Recipients are now managed through Django Admin (Email Recipients section)
# The ALERT_EMAIL_FROM below is used as the sender address for outgoing notifications.
ALERT_EMAIL_FROM = DEFAULT_FROM_EMAIL

# ========================
# Application Settings
# ========================
# Pagination
VEHICLES_PER_PAGE = 25
EQUIPMENT_PER_PAGE = 20
MAINTENANCE_PER_PAGE = 30

# Expiry alerts
DEFAULT_ALERT_DAYS = 30
ALERT_DAYS_MIN = 1
ALERT_DAYS_MAX = 365

# File upload limits
FILE_UPLOAD_MAX_SIZE_MB = 10
FILE_UPLOAD_MAX_MEMORY_SIZE = FILE_UPLOAD_MAX_SIZE_MB * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = FILE_UPLOAD_MAX_SIZE_MB * 1024 * 1024  # 10 MB

# Session
SESSION_TIMEOUT_MANAGER = 1209600  # 2 weeks (seconds)
SESSION_TIMEOUT_USER = 0  # Close on browser close

# ========================
# Security Settings (Production)
# ========================
# HTTPS Security (set to True in production)
SECURE_SSL_REDIRECT = not DEBUG if os.getenv('DJANGO_SECURE_SSL_REDIRECT') is None else os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 'yes')
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False').lower() in ('true', '1', 'yes')
SECURE_HSTS_PRELOAD = os.getenv('DJANGO_SECURE_HSTS_PRELOAD', 'False').lower() in ('true', '1', 'yes')

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'http')

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Content Security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# Additional Security Headers
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
