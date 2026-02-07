# aegis_project/settings/development.py
"""
Django development settings for AEGIS project.
Use for local development only.
"""

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Database - Use local PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', default='aegis_dev'),
        'USER': env('DB_USER', default='aegis_user'),
        'PASSWORD': env('DB_PASSWORD', default='dev_password'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 0,  # No connection pooling in dev
    }
}

# Development-specific apps
INSTALLED_APPS += [
    'debug_toolbar',
    'django_extensions',
]

# Development middleware
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

# Django Debug Toolbar
INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
}

# Email - Console backend for development (prints to console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging - More verbose in development
LOGGING['handlers']['console']['level'] = 'DEBUG'
LOGGING['loggers']['apps']['level'] = 'DEBUG'
LOGGING['loggers']['django']['level'] = 'DEBUG'

# Use local file for logs (not /var/log)
LOGGING['handlers']['file']['filename'] = str(BASE_DIR / 'logs' / 'django.log')
LOGGING['handlers']['audit_file']['filename'] = str(BASE_DIR / 'logs' / 'audit.log')

# Create logs directory if it doesn't exist
import os
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# CORS - Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True

# Security - Relaxed for local development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# CSP - Relaxed for development
CSP_DEFAULT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")

# Celery - Eager mode for development (runs tasks synchronously)
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_EAGER', default=True)
CELERY_TASK_EAGER_PROPAGATES = True

# Cache - Use local memory cache for development
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'aegis-dev-cache',
    }
}

# Session - Use database backend for development (easier debugging)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Static files - No need for collectstatic in dev
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Django Extensions - Shell Plus auto-import models
SHELL_PLUS_IMPORTS = [
    'from datetime import datetime, timedelta',
    'from django.utils import timezone',
]

# Development-specific AEGIS settings
AEGIS_ALERT_AUTO_ACCEPT_DAYS = 1  # Faster for testing

# LLM - Use smaller models for development
LLM_MODEL = env('LLM_MODEL', default='gpt-3.5-turbo')  # Cheaper for dev

# FHIR - Use test server
FHIR_SERVER_URL = env('FHIR_SERVER_URL', default='https://fhir-test.cchmc.org/fhir')

# Print settings on startup
print("=" * 70)
print("AEGIS Development Environment")
print("=" * 70)
print(f"Database: {DATABASES['default']['NAME']}")
print(f"Debug: {DEBUG}")
print(f"Celery Eager Mode: {CELERY_TASK_ALWAYS_EAGER}")
print(f"LLM Model: {LLM_MODEL}")
print("=" * 70)
