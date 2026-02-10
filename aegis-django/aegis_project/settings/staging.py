"""
AEGIS Django - Staging Settings

Staging deployment at staging.aegis-asp.com.
Extends production settings with staging-specific overrides.
"""

from .production import *

# Staging-specific overrides
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='staging.aegis-asp.com',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# Database - local PostgreSQL (no SSL required for localhost)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='aegis_django'),
        'USER': config('DB_USER', default='aegis'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,
    }
}

# Redis - local instance
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Static files
STATIC_ROOT = '/var/www/aegis-django/static/'
MEDIA_ROOT = '/var/www/aegis-django/media/'

# Logging - staging-specific paths
LOGGING['handlers']['file']['filename'] = '/var/log/aegis/django.log'
LOGGING['handlers']['audit_file']['filename'] = '/var/log/aegis/audit.log'
LOGGING['loggers']['django']['level'] = 'INFO'
LOGGING['loggers']['apps']['level'] = 'INFO'

# CORS - allow staging origin
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='https://staging.aegis-asp.com',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# Sentry - use staging environment tag
# (inherited from production.py, just override the environment)

# Nginx handles TLS termination — don't redirect at Django level
SECURE_SSL_REDIRECT = False

# Disable HSTS preload for staging (don't want staging in preload lists)
SECURE_HSTS_PRELOAD = False
SECURE_HSTS_SECONDS = 3600  # 1 hour for staging
