# aegis_project/settings/production.py
"""
Django production settings for AEGIS project.
Use for Cincinnati Children's production deployment.
"""

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Allowed hosts - Cincinnati Children's domains
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[
    'aegis.cchmc.org',
    'aegis-app.cchmc.org',
])

# Database - Azure PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),  # e.g., aegis-db.postgres.database.azure.com
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,  # Connection pooling
        'OPTIONS': {
            'sslmode': 'require',  # Required for Azure PostgreSQL
            'connect_timeout': 10,
        },
    }
}

# Security - HTTPS enforcement
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies - Secure
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'

# Additional security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Content Security Policy - Strict
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'",)
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)

# CORS - Restrictive (only allow specific origins)
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# Static files - Use WhiteNoise for serving
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Media files - Use Azure Blob Storage
if env.bool('USE_AZURE_STORAGE', default=True):
    DEFAULT_FILE_STORAGE = 'storages.backends.azure_storage.AzureStorage'
    AZURE_ACCOUNT_NAME = env('AZURE_STORAGE_ACCOUNT_NAME')
    AZURE_ACCOUNT_KEY = env('AZURE_STORAGE_ACCOUNT_KEY')
    AZURE_CONTAINER = env('AZURE_STORAGE_CONTAINER', default='media')
    AZURE_SSL = True

# Cache - Production Redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        },
        'KEY_PREFIX': 'aegis',
        'TIMEOUT': 300,
    }
}

# Session - Use Redis for sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Email - Production SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='aegis-noreply@cchmc.org')
SERVER_EMAIL = env('SERVER_EMAIL', default='aegis-errors@cchmc.org')

# Admins - Get error emails
ADMINS = env.list('ADMINS', default=[])
MANAGERS = ADMINS

# Logging - Production configuration
LOGGING['handlers']['file']['filename'] = env(
    'LOG_FILE',
    default='/var/log/aegis/django.log'
)
LOGGING['handlers']['audit_file']['filename'] = env(
    'AUDIT_LOG_FILE',
    default='/var/log/aegis/audit.log'
)

# Add Sentry for error tracking
if env('SENTRY_DSN', default=None):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=env('SENTRY_DSN'),
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        environment=env('SENTRY_ENVIRONMENT', default='production'),
        traces_sample_rate=env.float('SENTRY_TRACES_SAMPLE_RATE', default=0.1),
        send_default_pii=False,  # HIPAA compliance - don't send PII
    )

# Celery - Production configuration
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND')
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# REST Framework - Remove Browsable API in production
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# LDAP - Production Active Directory
LDAP_SERVER_URI = env('LDAP_SERVER_URI')
LDAP_BIND_DN = env('LDAP_BIND_DN')
LDAP_BIND_PASSWORD = env('LDAP_BIND_PASSWORD')
LDAP_USER_SEARCH_BASE = env('LDAP_USER_SEARCH_BASE')
LDAP_GROUP_SEARCH_BASE = env('LDAP_GROUP_SEARCH_BASE')

# SAML - Enable in production
SAML_ENABLED = env.bool('SAML_ENABLED', default=True)
SAML_METADATA_URL = env('SAML_METADATA_URL')
SAML_ENTITY_ID = env('SAML_ENTITY_ID', default='https://aegis.cchmc.org/saml')

# LLM - Production API keys
OPENAI_API_KEY = env('OPENAI_API_KEY')
ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY', default='')
LLM_PROVIDER = env('LLM_PROVIDER', default='openai')
LLM_MODEL = env('LLM_MODEL', default='gpt-4-turbo')

# FHIR - Production server
FHIR_SERVER_URL = env('FHIR_SERVER_URL')
FHIR_AUTH_TOKEN = env('FHIR_AUTH_TOKEN')

# Twilio - Production credentials
TWILIO_ACCOUNT_SID = env('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = env('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = env('TWILIO_FROM_NUMBER')

# Teams - Production webhook
TEAMS_WEBHOOK_URL = env('TEAMS_WEBHOOK_URL')

# Database backup configuration (for Azure PostgreSQL)
DATABASE_BACKUP_ENABLED = env.bool('DATABASE_BACKUP_ENABLED', default=True)
DATABASE_BACKUP_RETENTION_DAYS = env.int('DATABASE_BACKUP_RETENTION_DAYS', default=30)

# Performance optimization
CONN_MAX_AGE = 600
ATOMIC_REQUESTS = True  # Wrap each request in a transaction

# Template caching (production)
TEMPLATES[0]['OPTIONS']['loaders'] = [
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ]),
]

# Require strong passwords in production
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 14,  # Stronger than HIPAA minimum
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Azure-specific health checks
if env.bool('USE_AZURE_HEALTH_CHECKS', default=True):
    INSTALLED_APPS += [
        'health_check.contrib.psutil',  # Disk, memory usage
    ]

# Disable admin in production (use dedicated admin subdomain if needed)
if env.bool('DISABLE_ADMIN', default=False):
    INSTALLED_APPS.remove('django.contrib.admin')

print("=" * 70)
print("AEGIS Production Environment")
print("=" * 70)
print(f"Database Host: {DATABASES['default']['HOST']}")
print(f"Debug: {DEBUG}")
print(f"HTTPS Enforced: {SECURE_SSL_REDIRECT}")
print(f"SAML Enabled: {SAML_ENABLED}")
print(f"LLM Provider: {LLM_PROVIDER}")
print("=" * 70)
