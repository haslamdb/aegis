"""
AEGIS Django - Base Settings

Shared settings for all environments (development, staging, production).
"""

import os
from pathlib import Path
from decouple import config

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security
SECRET_KEY = config('SECRET_KEY', default='django-insecure-CHANGE-THIS-IN-PRODUCTION')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# Application definition
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'corsheaders',
    'auditlog',
    'django_celery_beat',
    'drf_spectacular',

    # AEGIS apps (shared)
    'apps.core',
    'apps.authentication',  # ✅ Phase 1.3 - Authentication & SSO
    'apps.alerts',  # ✅ Phase 1.4 - Unified alert system
    'apps.metrics',  # ✅ Phase 1.4 - Activity tracking
    'apps.notifications',  # ✅ Phase 1.4 - Multi-channel notifications
    # 'apps.llm_tracking',  # TO BE CREATED - Future

    # AEGIS apps (modules)
    'apps.action_analytics',  # ✅ Phase 2 - First migrated module!
    'apps.asp_alerts',  # ✅ Phase 2 - ASP Alerts Dashboard
    'apps.mdro',  # ✅ Phase 3 - MDRO Surveillance
    'apps.drug_bug',  # ✅ Phase 3 - Drug-Bug Mismatch
    'apps.dosing',  # ✅ Phase 3 - Dosing Verification
    'apps.hai_detection',  # ✅ Phase 3 - HAI Detection
    'apps.outbreak_detection',  # ✅ Phase 3 - Outbreak Detection
    'apps.antimicrobial_usage',  # ✅ Phase 3 - Antimicrobial Usage Alerts
    'apps.abx_indications',  # ✅ Phase 3 - ABX Indication Monitoring
    'apps.surgical_prophylaxis',  # ✅ Phase 3 - Surgical Prophylaxis
    'apps.guideline_adherence',  # ✅ Phase 3 - Guideline Adherence
    'apps.nhsn_reporting',  # ✅ Phase 3 - NHSN Reporting (final module)

    # API
    # 'apps.api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.authentication.middleware.AuditMiddleware',  # ✅ HIPAA audit logging
    'apps.authentication.middleware.SessionTrackingMiddleware',  # ✅ User session tracking
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'auditlog.middleware.AuditlogMiddleware',  # django-auditlog
]

ROOT_URLCONF = 'aegis_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'aegis_project.wsgi.application'

# Database
# Overridden in development.py and production.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Authentication
AUTH_USER_MODEL = 'authentication.User'  # ✅ Custom User model with RBAC
AUTHENTICATION_BACKENDS = [
    'apps.authentication.backends.SAMLAuthBackend',  # ✅ SAML SSO (primary)
    'apps.authentication.backends.LDAPAuthBackend',  # ✅ LDAP (fallback)
    'django.contrib.auth.backends.ModelBackend',  # Local password (fallback)
]

# Login/Logout URLs
LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/auth/login/'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'  # Cincinnati Children's timezone
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files (user uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# HIPAA Security Settings
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Session timeout (15 minutes for HIPAA compliance)
SESSION_COOKIE_AGE = 900
SESSION_SAVE_EVERY_REQUEST = True

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# DRF Spectacular (API documentation)
SPECTACULAR_SETTINGS = {
    'TITLE': 'AEGIS API',
    'DESCRIPTION': 'Antimicrobial Stewardship & Infection Prevention Platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# CORS (for frontend development)
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://localhost:8080',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# Logging
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
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 1024 * 1024 * 100,  # 100 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'audit.log',
            'maxBytes': 1024 * 1024 * 500,  # 500 MB
            'backupCount': 50,  # Keep 50 files (25 GB total for HIPAA)
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps.authentication.audit': {
            'handlers': ['audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# HAI Detection Configuration
HAI_DETECTION = {
    'LLM_BACKEND': 'ollama',
    'OLLAMA_BASE_URL': config('HAI_OLLAMA_URL', default='http://localhost:11434'),
    'OLLAMA_MODEL': config('HAI_OLLAMA_MODEL', default='llama3.3:70b'),
    'TRIAGE_MODEL': config('HAI_TRIAGE_MODEL', default='llama3.2:8b'),
    'VLLM_BASE_URL': config('HAI_VLLM_URL', default='http://localhost:8000'),
    'VLLM_MODEL': config('HAI_VLLM_MODEL', default='meta-llama/Llama-3.3-70B-Instruct'),
    'FHIR_BASE_URL': config('HAI_FHIR_URL', default='http://localhost:8081/fhir'),
    'LOOKBACK_HOURS': 24,
    'POLL_INTERVAL': 300,
    'AUTO_CLASSIFY_THRESHOLD': 0.85,
    'IP_REVIEW_THRESHOLD': 0.60,
}

# Outbreak Detection Configuration
OUTBREAK_DETECTION = {
    'CLUSTER_WINDOW_DAYS': 14,
    'MIN_CLUSTER_SIZE': 2,
    'POLL_INTERVAL_MINUTES': 30,
}

# Antimicrobial Usage Alerts Configuration
ANTIMICROBIAL_USAGE = {
    'ALERT_THRESHOLD_HOURS': 72,
    'MONITORED_MEDICATIONS': {
        '29561': 'Meropenem',
        '11124': 'Vancomycin',
    },
    'POLL_INTERVAL_SECONDS': 300,
}

# ABX Indication Monitoring Configuration
ABX_INDICATIONS = {
    'LLM_MODEL': config('ABX_IND_LLM_MODEL', default='qwen2.5:7b'),
    'OLLAMA_BASE_URL': config('ABX_IND_OLLAMA_URL', default='http://localhost:11434'),
    'FHIR_BASE_URL': config('ABX_IND_FHIR_URL', default='http://localhost:8081/fhir'),
    'LOOKBACK_HOURS': 24,
    'AUTO_ACCEPT_HOURS': 48,
    'POLL_INTERVAL_SECONDS': 300,
    'MONITORED_MEDICATIONS': {
        '29561': 'Meropenem',
        '3356': 'Ceftriaxone',
        '2180': 'Cefepime',
        '18631': 'Piperacillin-Tazobactam',
        '11124': 'Vancomycin',
        '1665005': 'Ceftazidime-Avibactam',
        '82122': 'Levofloxacin',
        '2551': 'Ciprofloxacin',
        '190376': 'Linezolid',
        '1664986': 'Daptomycin',
        '1596450': 'Tedizolid',
        '325642': 'Micafungin',
        '121243': 'Caspofungin',
        '283742': 'Voriconazole',
        '1720673': 'Isavuconazonium',
        '644': 'Amphotericin B Lipid Complex',
        '2059746': 'Meropenem-Vaborbactam',
        '1535224': 'Ceftolozane-Tazobactam',
        '1597608': 'Ertapenem',
        '1723476': 'Imipenem-Cilastatin-Relebactam',
        '1807508': 'Aztreonam-Avibactam',
    },
}

# Surgical Prophylaxis Configuration
SURGICAL_PROPHYLAXIS = {
    'FHIR_BASE_URL': config('SP_FHIR_URL', default='http://localhost:8081/fhir'),
    'HL7_ENABLED': config('SP_HL7_ENABLED', default='false', cast=bool),
    'HL7_HOST': config('SP_HL7_HOST', default='0.0.0.0'),
    'HL7_PORT': config('SP_HL7_PORT', default=2575, cast=int),
    'FHIR_SCHEDULE_POLL_INTERVAL': 15,
    'FHIR_PROPHYLAXIS_POLL_INTERVAL': 5,
    'FHIR_LOOKAHEAD_HOURS': 48,
    'POLL_INTERVAL_SECONDS': 300,
    'ALERT_T24_ENABLED': True,
    'ALERT_T2_ENABLED': True,
    'ALERT_T60_ENABLED': True,
    'ALERT_T0_ENABLED': True,
    'EPIC_CHAT_ENABLED': False,
    'TEAMS_ENABLED': False,
}

# Guideline Adherence Configuration
GUIDELINE_ADHERENCE = {
    'FHIR_BASE_URL': config('GA_FHIR_URL', default='http://localhost:8081/fhir'),
    'LLM_BACKEND': 'ollama',
    'OLLAMA_BASE_URL': config('GA_OLLAMA_URL', default='http://localhost:11434'),
    'FULL_MODEL': config('GA_FULL_MODEL', default='llama3.3:70b'),
    'TRIAGE_MODEL': config('GA_TRIAGE_MODEL', default='qwen2.5:7b'),
    'CHECK_INTERVAL_MINUTES': 15,
    'POLL_INTERVAL_SECONDS': 300,
    'ENABLED_BUNDLES': [
        'sepsis_peds_2024', 'cap_peds_2024', 'febrile_infant_2024',
        'neonatal_hsv_2024', 'cdiff_testing_2024', 'fn_peds_2024',
        'uti_peds_2024', 'ssti_peds_2024',
    ],
}

# NHSN Reporting Configuration
NHSN_REPORTING = {
    'CLARITY_CONNECTION_STRING': config('NHSN_CLARITY_URL', default=None),
    'MOCK_CLARITY_DB_PATH': config('NHSN_MOCK_CLARITY_DB', default=None),
    'FHIR_BASE_URL': config('NHSN_FHIR_URL', default='http://localhost:8081/fhir'),
    'NHSN_FACILITY_ID': config('NHSN_FACILITY_ID', default=None),
    'NHSN_FACILITY_NAME': config('NHSN_FACILITY_NAME', default="Cincinnati Children's Hospital"),
    'AU_LOCATION_TYPES': config('NHSN_AU_LOCATION_TYPES', default='ICU,Ward,NICU,BMT', cast=lambda v: [s.strip() for s in v.split(',')]),
    'AU_INCLUDE_ORAL': config('NHSN_AU_INCLUDE_ORAL', default=True, cast=bool),
    'AR_SPECIMEN_TYPES': config('NHSN_AR_SPECIMEN_TYPES', default='Blood,Urine,Respiratory,CSF', cast=lambda v: [s.strip() for s in v.split(',')]),
    'AR_FIRST_ISOLATE_ONLY': config('NHSN_AR_FIRST_ISOLATE_ONLY', default=True, cast=bool),
    'DIRECT_HISP_SERVER': config('NHSN_HISP_SMTP_SERVER', default=None),
    'DIRECT_HISP_PORT': config('NHSN_HISP_SMTP_PORT', default=587, cast=int),
    'DIRECT_HISP_USERNAME': config('NHSN_HISP_USERNAME', default=None),
    'DIRECT_HISP_PASSWORD': config('NHSN_HISP_PASSWORD', default=None),
    'DIRECT_SENDER_ADDRESS': config('NHSN_SENDER_DIRECT', default=None),
    'DIRECT_NHSN_ADDRESS': config('NHSN_DIRECT_ADDRESS', default=None),
}
