import os
from pathlib import Path

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
            os.environ.setdefault(key.strip(), value.strip())

# SECURITY
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    import warnings
    warnings.warn(
        'DJANGO_SECRET_KEY is not set. For production, set the DJANGO_SECRET_KEY '
        'environment variable to a secure random value.',
        UserWarning
    )
    # Keep a fallback for local development only.
    SECRET_KEY = 'CHANGE_THIS_IN_PRODUCTION_TO_A_SECURE_RANDOM_KEY'

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')
allowed_hosts = os.getenv('DJANGO_ALLOWED_HOSTS')
if allowed_hosts:
    ALLOWED_HOSTS = allowed_hosts.split(',')
else:
    ALLOWED_HOSTS = ['*']

# Warn if DEBUG is True
if DEBUG:
    import warnings
    warnings.warn(
        'DEBUG is set to True. This should be False in production.',
        UserWarning
    )

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
            ],
        },
    },
]

WSGI_APPLICATION = 'asset_management.wsgi.application'

# ========================
# Database
# ========================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'ATOMIC_REQUESTS': False,  # Avoid holding locks during entire request
        'CONN_MAX_AGE': 0,  # Close DB connections after each request to reduce contention
        'OPTIONS': {
            'timeout': 20,  # Wait up to 20 seconds for database lock
        }
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
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'topafgg@gmail.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', 'mbqn xqaw kozx roaj')
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
SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 'yes')
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False').lower() in ('true', '1', 'yes')
SECURE_HSTS_PRELOAD = os.getenv('DJANGO_SECURE_HSTS_PRELOAD', 'False').lower() in ('true', '1', 'yes')

# Cookie Security
SESSION_COOKIE_SECURE = os.getenv('DJANGO_SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
CSRF_COOKIE_SECURE = os.getenv('DJANGO_CSRF_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Content Security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# Additional Security Headers
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
