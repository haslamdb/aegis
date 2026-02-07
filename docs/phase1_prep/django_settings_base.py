# aegis_project/settings/base.py
"""
Django base settings for AEGIS project.
Shared across all environments (dev, staging, production).
"""

import os
from pathlib import Path
import environ

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Environment variables
env = environ.Env(
    DEBUG=(bool, False)
)
# Read .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# Application definition
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'corsheaders',
    'django_celery_beat',
    'auditlog',  # django-auditlog
    'csp',  # django-csp
    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.contrib.celery',
    'health_check.contrib.redis',
    'drf_spectacular',  # API documentation

    # AEGIS apps - Shared Services
    'apps.core.apps.CoreConfig',
    'apps.authentication.apps.AuthenticationConfig',
    'apps.alerts.apps.AlertsConfig',
    'apps.metrics.apps.MetricsConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.llm_tracking.apps.LlmTrackingConfig',

    # AEGIS apps - Clinical Modules
    'apps.hai_detection.apps.HaiDetectionConfig',
    'apps.dosing_verification.apps.DosingVerificationConfig',
    'apps.abx_approvals.apps.AbxApprovalsConfig',
    'apps.guideline_adherence.apps.GuidelineAdherenceConfig',
    'apps.drug_bug_mismatch.apps.DrugBugMismatchConfig',
    'apps.mdro_surveillance.apps.MdroSurveillanceConfig',
    'apps.surgical_prophylaxis.apps.SurgicalProphylaxisConfig',
    'apps.nhsn_reporting.apps.NhsnReportingConfig',
    'apps.outbreak_detection.apps.OutbreakDetectionConfig',
    'apps.action_analytics.apps.ActionAnalyticsConfig',

    # API
    'apps.api.apps.ApiConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.authentication.middleware.AuditMiddleware',  # HIPAA audit logging
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'csp.middleware.CSPMiddleware',  # Content Security Policy
    'auditlog.middleware.AuditlogMiddleware',  # django-auditlog
]

ROOT_URLCONF = 'aegis_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.aegis_context',  # Custom context
            ],
        },
    },
]

WSGI_APPLICATION = 'aegis_project.wsgi.application'

# Database
# This will be overridden in environment-specific settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', default='aegis'),
        'USER': env('DB_USER', default='aegis_user'),
        'PASSWORD': env('DB_PASSWORD', default=''),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': env.int('DB_CONN_MAX_AGE', default=600),  # Connection pooling
        'OPTIONS': {
            'sslmode': env('DB_SSLMODE', default='prefer'),
        },
    }
}

# Custom User Model
AUTH_USER_MODEL = 'authentication.User'

# Authentication Backends
AUTHENTICATION_BACKENDS = [
    'apps.authentication.backends.LDAPAuthBackend',
    'apps.authentication.backends.SAMLAuthBackend',
    'django.contrib.auth.backends.ModelBackend',  # Fallback
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 12,  # HIPAA recommendation
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'  # Cincinnati Children's timezone
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files (user uploads - if any)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.api.exceptions.custom_exception_handler',
}

# DRF Spectacular (API Documentation)
SPECTACULAR_SETTINGS = {
    'TITLE': 'AEGIS API',
    'DESCRIPTION': 'Antimicrobial Stewardship & Infection Prevention Platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/v1',
    'COMPONENT_SPLIT_REQUEST': True,
}

# Celery Configuration
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes max per task
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Restart worker after 1000 tasks

# Celery Beat Schedule (Periodic Tasks)
CELERY_BEAT_SCHEDULE = {
    'daily-metrics-snapshot': {
        'task': 'apps.metrics.tasks.generate_daily_snapshot',
        'schedule': 86400.0,  # Daily (24 hours)
    },
    'abx-approvals-auto-recheck': {
        'task': 'apps.abx_approvals.tasks.auto_recheck_approvals',
        'schedule': 28800.0,  # 3x daily (every 8 hours)
    },
    'hai-detection-scan': {
        'task': 'apps.hai_detection.tasks.run_detection_scan',
        'schedule': 3600.0,  # Hourly
    },
    'auto-accept-old-alerts': {
        'task': 'apps.alerts.tasks.auto_accept_old_alerts',
        'schedule': 86400.0,  # Daily
    },
}

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'aegis',
        'TIMEOUT': 300,  # 5 minutes default
    }
}

# Session Configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 900  # 15 minutes
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_NAME = 'aegis_session'

# Security Settings (base - enhanced in production)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# CORS Settings (restrictive by default)
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")  # TODO: Remove unsafe-inline in production
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'",)
CSP_CONNECT_SRC = ("'self'",)

# Email Configuration (for notifications)
EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='aegis@cchmc.org')

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': env('LOG_FILE', default='/var/log/aegis/django.log'),
            'maxBytes': 1024 * 1024 * 100,  # 100 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': env('AUDIT_LOG_FILE', default='/var/log/aegis/audit.log'),
            'maxBytes': 1024 * 1024 * 500,  # 500 MB
            'backupCount': 50,  # 7 years retention for HIPAA
            'formatter': 'json',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false'],
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.authentication.audit': {
            'handlers': ['audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# LDAP Configuration (Cincinnati Children's Active Directory)
# These will be populated from environment variables
LDAP_SERVER_URI = env('LDAP_SERVER_URI', default='ldap://ldap.cchmc.org')
LDAP_BIND_DN = env('LDAP_BIND_DN', default='')
LDAP_BIND_PASSWORD = env('LDAP_BIND_PASSWORD', default='')
LDAP_USER_SEARCH_BASE = env('LDAP_USER_SEARCH_BASE', default='ou=users,dc=cchmc,dc=org')
LDAP_GROUP_SEARCH_BASE = env('LDAP_GROUP_SEARCH_BASE', default='ou=groups,dc=cchmc,dc=org')

# SAML Configuration
SAML_ENABLED = env.bool('SAML_ENABLED', default=False)
SAML_METADATA_URL = env('SAML_METADATA_URL', default='')
SAML_ENTITY_ID = env('SAML_ENTITY_ID', default='https://aegis.cchmc.org/saml')

# AEGIS-Specific Settings
AEGIS_ALERT_AUTO_ACCEPT_DAYS = env.int('AEGIS_ALERT_AUTO_ACCEPT_DAYS', default=14)
AEGIS_SESSION_TIMEOUT_WARNING_MINUTES = env.int('AEGIS_SESSION_TIMEOUT_WARNING_MINUTES', default=2)

# LLM Configuration (for HAI extraction, guideline reviews)
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY', default='')
LLM_PROVIDER = env('LLM_PROVIDER', default='openai')  # 'openai' or 'anthropic'
LLM_MODEL = env('LLM_MODEL', default='gpt-4-turbo')

# FHIR Server Configuration
FHIR_SERVER_URL = env('FHIR_SERVER_URL', default='https://fhir.cchmc.org/fhir')
FHIR_AUTH_TOKEN = env('FHIR_AUTH_TOKEN', default='')

# Twilio Configuration (SMS notifications)
TWILIO_ACCOUNT_SID = env('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = env('TWILIO_AUTH_TOKEN', default='')
TWILIO_FROM_NUMBER = env('TWILIO_FROM_NUMBER', default='')

# Teams Webhook (notifications)
TEAMS_WEBHOOK_URL = env('TEAMS_WEBHOOK_URL', default='')
