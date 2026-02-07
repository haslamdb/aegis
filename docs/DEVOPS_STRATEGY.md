# AEGIS Django Migration - DevOps Strategy

**Author:** DevOps Specialist
**Date:** 2026-02-07
**Purpose:** Docker, Celery, CI/CD, and deployment architecture for zero-downtime Flask → Django migration

---

## Executive Summary

This document outlines the DevOps infrastructure for AEGIS's gradual Flask-to-Django migration. The strategy enables:

- **Zero-downtime cutover** via Nginx path-based routing
- **Side-by-side operation** of Flask and Django during 6-month migration
- **Celery-based background tasks** for HAI detection, ABX approvals, metrics aggregation
- **CI/CD pipeline** with automated testing and deployment
- **Hospital-ready deployment** for Cincinnati Children's infrastructure
- **Production monitoring** with Sentry, health checks, and APM

**Key Design Principles:**
1. **Incremental migration** - Route traffic per module, rollback capability at each step
2. **Infrastructure as Code** - All configs in Git, reproducible environments
3. **PHI-safe** - All containers run on-premises, no external PHI egress
4. **Hospital compliance** - HIPAA audit logging, encryption, access controls

---

## 1. Docker Compose Setup for Development

### 1.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx (Reverse Proxy)               │
│              Routes by path: /dosing-verification → Django   │
│                          Everything else → Flask            │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │  Flask   │      │  Django  │      │  Static  │
  │  (8082)  │      │  (8000)  │      │  Files   │
  └────┬─────┘      └────┬─────┘      └──────────┘
       │                 │
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │   PostgreSQL    │    Shared database
       │     (5432)      │    (both apps during migration)
       └─────────────────┘
                │
       ┌────────┴────────┐
       ▼                 ▼
  ┌──────────┐      ┌──────────┐
  │  Redis   │      │  Celery  │
  │  (6379)  │◄─────│  Worker  │
  └──────────┘      └──────────┘
       ▲                 │
       └─────────────────┘
            (Task queue)
```

### 1.2 Docker Compose Configuration

**File:** `docker-compose.yml` (development environment)

```yaml
version: '3.8'

services:
  # PostgreSQL - Shared database for Flask and Django
  postgres:
    image: postgres:15-alpine
    container_name: aegis-postgres
    environment:
      POSTGRES_DB: aegis
      POSTGRES_USER: aegis_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aegis_user -d aegis"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - aegis_network

  # Redis - Celery broker and cache
  redis:
    image: redis:7-alpine
    container_name: aegis-redis
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - aegis_network

  # Flask - Legacy application (during migration)
  flask:
    build:
      context: .
      dockerfile: docker/Dockerfile.flask
    container_name: aegis-flask
    environment:
      - FLASK_APP=dashboard.app
      - FLASK_ENV=development
      - DATABASE_URL=postgresql://aegis_user:${POSTGRES_PASSWORD}@postgres:5432/aegis
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - ALERT_DB_PATH=/app/data/alerts.db
      - FHIR_BASE_URL=${FHIR_BASE_URL}
      - DASHBOARD_BASE_URL=http://localhost:8080
    volumes:
      - .:/app
      - flask_data:/app/data
      - static_files:/app/dashboard/static
    ports:
      - "8082:8082"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - aegis_network

  # Django - New application (gradual rollout)
  django:
    build:
      context: .
      dockerfile: docker/Dockerfile.django
    container_name: aegis-django
    environment:
      - DJANGO_SETTINGS_MODULE=aegis_project.settings.development
      - DATABASE_URL=postgresql://aegis_user:${POSTGRES_PASSWORD}@postgres:5432/aegis
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
      - SECRET_KEY=${DJANGO_SECRET_KEY}
      - DEBUG=1
      - ALLOWED_HOSTS=localhost,127.0.0.1,nginx
      - FHIR_BASE_URL=${FHIR_BASE_URL}
    volumes:
      - ./aegis-django:/app
      - django_static:/app/staticfiles
      - django_media:/app/media
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      sh -c "python manage.py migrate &&
             python manage.py collectstatic --noinput &&
             gunicorn aegis_project.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 60 --access-logfile - --error-logfile -"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - aegis_network

  # Celery Worker - Background tasks
  celery:
    build:
      context: .
      dockerfile: docker/Dockerfile.django
    container_name: aegis-celery
    environment:
      - DJANGO_SETTINGS_MODULE=aegis_project.settings.development
      - DATABASE_URL=postgresql://aegis_user:${POSTGRES_PASSWORD}@postgres:5432/aegis
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
      - SECRET_KEY=${DJANGO_SECRET_KEY}
    volumes:
      - ./aegis-django:/app
      - celery_logs:/var/log/celery
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      django:
        condition: service_healthy
    command: celery -A aegis_project worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
    restart: unless-stopped
    networks:
      - aegis_network

  # Celery Beat - Periodic task scheduler
  celery-beat:
    build:
      context: .
      dockerfile: docker/Dockerfile.django
    container_name: aegis-celery-beat
    environment:
      - DJANGO_SETTINGS_MODULE=aegis_project.settings.development
      - DATABASE_URL=postgresql://aegis_user:${POSTGRES_PASSWORD}@postgres:5432/aegis
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
      - SECRET_KEY=${DJANGO_SECRET_KEY}
    volumes:
      - ./aegis-django:/app
      - celery_beat_schedule:/app/celerybeat-schedule
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      django:
        condition: service_healthy
    command: celery -A aegis_project beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    restart: unless-stopped
    networks:
      - aegis_network

  # Flower - Celery monitoring UI
  flower:
    build:
      context: .
      dockerfile: docker/Dockerfile.django
    container_name: aegis-flower
    environment:
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
    ports:
      - "5555:5555"
    depends_on:
      - redis
      - celery
    command: celery -A aegis_project flower --port=5555 --basic_auth=${FLOWER_USER}:${FLOWER_PASSWORD}
    restart: unless-stopped
    networks:
      - aegis_network

  # Nginx - Reverse proxy with path-based routing
  nginx:
    image: nginx:1.25-alpine
    container_name: aegis-nginx
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./docker/nginx/conf.d:/etc/nginx/conf.d:ro
      - static_files:/usr/share/nginx/html/static/flask:ro
      - django_static:/usr/share/nginx/html/static/django:ro
      - ./docker/nginx/ssl:/etc/nginx/ssl:ro
    ports:
      - "8080:80"
      - "8443:443"
    depends_on:
      - flask
      - django
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - aegis_network

  # HAPI FHIR Server (development only)
  hapi-fhir:
    image: hapiproject/hapi:latest
    container_name: aegis-hapi-fhir
    ports:
      - "8081:8080"
    environment:
      - hapi.fhir.default_encoding=json
      - hapi.fhir.fhir_version=R4
      - hapi.fhir.allow_external_references=true
      - spring.datasource.url=jdbc:postgresql://postgres:5432/fhir
      - spring.datasource.username=aegis_user
      - spring.datasource.password=${POSTGRES_PASSWORD}
      - spring.jpa.hibernate.ddl-auto=update
    volumes:
      - hapi_data:/data/hapi
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/fhir/metadata"]
      interval: 30s
      timeout: 10s
      retries: 5
    restart: unless-stopped
    networks:
      - aegis_network

volumes:
  postgres_data:
  redis_data:
  flask_data:
  static_files:
  django_static:
  django_media:
  celery_logs:
  celery_beat_schedule:
  hapi_data:

networks:
  aegis_network:
    driver: bridge
```

### 1.3 Environment Variables

**File:** `.env` (DO NOT commit to Git)

```bash
# PostgreSQL
POSTGRES_PASSWORD=your_secure_password_here

# Redis
REDIS_PASSWORD=your_redis_password_here

# Django
DJANGO_SECRET_KEY=your_django_secret_key_here_min_50_chars

# Flower (Celery monitoring)
FLOWER_USER=admin
FLOWER_PASSWORD=your_flower_password_here

# FHIR
FHIR_BASE_URL=http://hapi-fhir:8080/fhir

# Cincinnati Children's LDAP (production only)
LDAP_SERVER=ldap://ldap.cchmc.org
LDAP_BIND_DN=CN=aegis_service,OU=ServiceAccounts,DC=cchmc,DC=org
LDAP_BIND_PASSWORD=your_ldap_password_here
LDAP_USER_BASE=OU=Users,DC=cchmc,DC=org

# Sentry (production monitoring)
SENTRY_DSN=https://your_sentry_dsn_here
```

---

## 2. Nginx Routing Strategy for Gradual Cutover

### 2.1 Path-Based Routing Architecture

Nginx acts as a **smart router** that directs traffic to Flask or Django based on URL path. This enables:

- **Module-by-module migration** - Route `/dosing-verification/` to Django, keep `/asp-alerts/` in Flask
- **Instant rollback** - Change one line in nginx.conf to route back to Flask if issues arise
- **Independent scaling** - Flask and Django scale separately based on load
- **Gradual testing** - Production traffic hits new Django modules while Flask remains stable

### 2.2 Nginx Configuration

**File:** `docker/nginx/conf.d/aegis.conf`

```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=aegis_general:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=aegis_api:10m rate=5r/s;

# Upstream servers
upstream flask_backend {
    server flask:8082 max_fails=3 fail_timeout=30s;
}

upstream django_backend {
    server django:8000 max_fails=3 fail_timeout=30s;
}

# HTTP server (development)
server {
    listen 80;
    server_name localhost;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/aegis-access.log;
    error_log /var/log/nginx/aegis-error.log;

    # Max upload size
    client_max_body_size 10M;

    # Timeouts
    proxy_connect_timeout 60;
    proxy_send_timeout 60;
    proxy_read_timeout 60;

    # Health check endpoint (nginx itself)
    location /health {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }

    # Static files (served directly by nginx)
    location /static/flask/ {
        alias /usr/share/nginx/html/static/flask/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /static/django/ {
        alias /usr/share/nginx/html/static/django/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Deny sensitive files
    location ~ /\. {
        deny all;
    }
    location ~ \.(env|git|py|pyc|db|sql|sqlite)$ {
        deny all;
    }

    ###########################################
    # MIGRATION ROUTING - DJANGO MODULES
    ###########################################
    # As each module is migrated to Django, add its route here
    # When ready to cutover, route traffic to django_backend
    # If issues arise, change proxy_pass back to flask_backend

    # Module 1: Dosing Verification (migrated to Django)
    location /dosing-verification/ {
        limit_req zone=aegis_general burst=20 nodelay;
        proxy_pass http://django_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Module 2: Action Analytics (migrated to Django)
    location /action-analytics/ {
        limit_req zone=aegis_general burst=20 nodelay;
        proxy_pass http://django_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Module 3: MDRO Surveillance (next to migrate)
    # Uncomment when ready to cutover:
    # location /mdro-surveillance/ {
    #     limit_req zone=aegis_general burst=20 nodelay;
    #     proxy_pass http://django_backend;
    #     proxy_set_header Host $host;
    #     proxy_set_header X-Real-IP $remote_addr;
    #     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    #     proxy_set_header X-Forwarded-Proto $scheme;
    #     proxy_redirect off;
    # }

    # Add more Django modules here as they're migrated...

    ###########################################
    # DJANGO API ENDPOINTS
    ###########################################
    location /api/ {
        limit_req zone=aegis_api burst=10 nodelay;
        proxy_pass http://django_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Django admin interface
    location /admin/ {
        limit_req zone=aegis_api burst=10 nodelay;
        proxy_pass http://django_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    ###########################################
    # FLASK - ALL OTHER ROUTES
    ###########################################
    # Default: route everything else to Flask
    # As modules migrate to Django, they'll be caught by
    # the location blocks above before reaching this default
    location / {
        limit_req zone=aegis_general burst=20 nodelay;
        proxy_pass http://flask_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

### 2.3 Migration Workflow

**Step-by-step process for migrating a module:**

1. **Develop Django module** in `aegis-django/apps/module_name/`
2. **Test locally** by temporarily routing to Django in nginx.conf
3. **Deploy to staging** and run full test suite
4. **Update nginx.conf** in production to route module to Django
5. **Reload nginx** (`docker-compose exec nginx nginx -s reload` or `sudo systemctl reload nginx`)
6. **Monitor metrics** (error rates, response times, user feedback)
7. **Rollback if needed** by changing `proxy_pass http://django_backend` → `proxy_pass http://flask_backend`

**Example: Rolling back Dosing Verification module**

```bash
# Edit nginx config
vim docker/nginx/conf.d/aegis.conf

# Change:
# location /dosing-verification/ {
#     proxy_pass http://django_backend;  # ← Change this
# }
# To:
# location /dosing-verification/ {
#     proxy_pass http://flask_backend;  # ← Back to Flask
# }

# Reload nginx (zero downtime)
docker-compose exec nginx nginx -s reload

# Or in production:
sudo systemctl reload nginx
```

---

## 3. Celery Task Architecture

### 3.1 Background Jobs in AEGIS

AEGIS has several workloads that benefit from Celery's asynchronous execution:

| Task | Frequency | Execution Time | Priority |
|------|-----------|----------------|----------|
| **HAI Detection Scan** | Hourly | ~5-10 min | High |
| **ABX Approvals Auto-Recheck** | 3x daily (6am, 12pm, 6pm) | ~2-5 min | High |
| **Metrics Aggregation** | Daily (midnight) | ~10-15 min | Medium |
| **Auto-Accept Old Alerts** | Daily (1am) | ~1 min | Medium |
| **NHSN AU/AR Calculation** | Weekly (Sundays) | ~30-60 min | Low |
| **Drug-Bug Mismatch Scan** | Every 2 hours | ~3-5 min | Medium |
| **LLM Batch Processing** | On-demand | Variable | Low |

### 3.2 Celery Configuration

**File:** `aegis-django/aegis_project/celery.py`

```python
"""Celery configuration for AEGIS."""

import os
from celery import Celery
from celery.schedules import crontab

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aegis_project.settings')

# Create Celery app
app = Celery('aegis')

# Load config from Django settings (namespace 'CELERY')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Periodic task schedule
app.conf.beat_schedule = {
    # HAI Detection - Hourly scan for new HAI candidates
    'hai-detection-scan': {
        'task': 'apps.hai_detection.tasks.run_hai_detection_scan',
        'schedule': crontab(minute=0),  # Every hour on the hour
        'options': {'queue': 'high_priority'},
    },

    # ABX Approvals - Auto re-check expiring approvals
    'abx-approvals-recheck-morning': {
        'task': 'apps.abx_approvals.tasks.check_expiring_approvals',
        'schedule': crontab(hour=6, minute=0),  # 6:00 AM
        'options': {'queue': 'high_priority'},
    },
    'abx-approvals-recheck-noon': {
        'task': 'apps.abx_approvals.tasks.check_expiring_approvals',
        'schedule': crontab(hour=12, minute=0),  # 12:00 PM
        'options': {'queue': 'high_priority'},
    },
    'abx-approvals-recheck-evening': {
        'task': 'apps.abx_approvals.tasks.check_expiring_approvals',
        'schedule': crontab(hour=18, minute=0),  # 6:00 PM
        'options': {'queue': 'high_priority'},
    },

    # Metrics - Daily aggregation
    'metrics-daily-snapshot': {
        'task': 'apps.core.tasks.create_daily_metrics_snapshot',
        'schedule': crontab(hour=0, minute=0),  # Midnight
        'options': {'queue': 'default'},
    },

    # Alerts - Auto-accept stale alerts
    'alerts-auto-accept': {
        'task': 'apps.core.tasks.auto_accept_old_alerts',
        'schedule': crontab(hour=1, minute=0),  # 1:00 AM
        'options': {'queue': 'default'},
    },

    # Drug-Bug Mismatch - Scan every 2 hours
    'drug-bug-mismatch-scan': {
        'task': 'apps.drug_bug.tasks.run_drug_bug_scan',
        'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
        'options': {'queue': 'default'},
    },

    # MDRO Surveillance - Daily scan
    'mdro-surveillance-scan': {
        'task': 'apps.mdro.tasks.run_mdro_scan',
        'schedule': crontab(hour=2, minute=0),  # 2:00 AM
        'options': {'queue': 'default'},
    },

    # NHSN Reporting - Weekly AU/AR calculations
    'nhsn-au-ar-calculation': {
        'task': 'apps.nhsn_reporting.tasks.calculate_au_ar_weekly',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Sundays at 3:00 AM
        'options': {'queue': 'low_priority'},
    },

    # Guideline Adherence - Hourly bundle checks
    'guideline-adherence-scan': {
        'task': 'apps.guideline_adherence.tasks.check_bundle_compliance',
        'schedule': crontab(minute=30),  # Every hour at :30
        'options': {'queue': 'default'},
    },
}

# Task routing - send tasks to specific queues based on priority
app.conf.task_routes = {
    'apps.hai_detection.*': {'queue': 'high_priority'},
    'apps.abx_approvals.*': {'queue': 'high_priority'},
    'apps.drug_bug.*': {'queue': 'default'},
    'apps.mdro.*': {'queue': 'default'},
    'apps.nhsn_reporting.*': {'queue': 'low_priority'},
    'apps.guideline_adherence.*': {'queue': 'default'},
    'apps.dosing_verification.*': {'queue': 'high_priority'},
}

# Celery configuration
app.conf.update(
    # Result backend (store task results)
    result_backend='redis://redis:6379/2',
    result_expires=86400,  # 24 hours

    # Task execution settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/New_York',
    enable_utc=True,

    # Task acks late (ensure task completion before ack)
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Task time limits
    task_soft_time_limit=600,  # 10 minutes
    task_time_limit=900,  # 15 minutes (hard limit)

    # Task retries
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Worker settings
    worker_max_tasks_per_child=100,  # Prevent memory leaks
    worker_disable_rate_limits=False,
)


@app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery is working."""
    print(f'Request: {self.request!r}')
```

### 3.3 Example Task: HAI Detection

**File:** `aegis-django/apps/hai_detection/tasks.py`

```python
"""Celery tasks for HAI detection."""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta

from .candidates.clabsi import CLABSIDetector
from .candidates.ssi import SSIDetector
from .candidates.cauti import CAUTIDetector
from .candidates.vae import VAEDetector
from .candidates.cdi import CDIDetector
from .models import HAICandidate, HAIScanLog

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name='apps.hai_detection.tasks.run_hai_detection_scan',
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def run_hai_detection_scan(self):
    """
    Hourly scan for new HAI candidates across all 5 HAI types.

    This task:
    1. Runs detection algorithms for CLABSI, SSI, CAUTI, VAE, CDI
    2. Creates HAICandidate records for review
    3. Sends alerts to Infection Prevention team
    4. Logs scan results for monitoring
    """
    logger.info("Starting HAI detection scan...")
    scan_start = timezone.now()

    try:
        # Scan window: last 2 hours (overlap for safety)
        window_start = timezone.now() - timedelta(hours=2)
        window_end = timezone.now()

        results = {
            'clabsi': 0,
            'ssi': 0,
            'cauti': 0,
            'vae': 0,
            'cdi': 0,
        }

        # CLABSI Detection
        logger.info("Running CLABSI detection...")
        clabsi_detector = CLABSIDetector()
        clabsi_candidates = clabsi_detector.detect(window_start, window_end)
        results['clabsi'] = len(clabsi_candidates)

        # SSI Detection
        logger.info("Running SSI detection...")
        ssi_detector = SSIDetector()
        ssi_candidates = ssi_detector.detect(window_start, window_end)
        results['ssi'] = len(ssi_candidates)

        # CAUTI Detection
        logger.info("Running CAUTI detection...")
        cauti_detector = CAUTIDetector()
        cauti_candidates = cauti_detector.detect(window_start, window_end)
        results['cauti'] = len(cauti_candidates)

        # VAE Detection
        logger.info("Running VAE detection...")
        vae_detector = VAEDetector()
        vae_candidates = vae_detector.detect(window_start, window_end)
        results['vae'] = len(vae_candidates)

        # CDI Detection
        logger.info("Running CDI detection...")
        cdi_detector = CDIDetector()
        cdi_candidates = cdi_detector.detect(window_start, window_end)
        results['cdi'] = len(cdi_candidates)

        # Log scan results
        scan_duration = (timezone.now() - scan_start).total_seconds()
        total_candidates = sum(results.values())

        HAIScanLog.objects.create(
            scan_time=scan_start,
            window_start=window_start,
            window_end=window_end,
            duration_seconds=scan_duration,
            clabsi_count=results['clabsi'],
            ssi_count=results['ssi'],
            cauti_count=results['cauti'],
            vae_count=results['vae'],
            cdi_count=results['cdi'],
            total_count=total_candidates,
            status='success',
        )

        logger.info(
            f"HAI detection scan complete. "
            f"Found {total_candidates} candidates in {scan_duration:.1f}s. "
            f"CLABSI={results['clabsi']}, SSI={results['ssi']}, "
            f"CAUTI={results['cauti']}, VAE={results['vae']}, CDI={results['cdi']}"
        )

        return results

    except Exception as exc:
        logger.error(f"HAI detection scan failed: {exc}", exc_info=True)

        # Log failure
        HAIScanLog.objects.create(
            scan_time=scan_start,
            window_start=window_start,
            window_end=window_end,
            duration_seconds=(timezone.now() - scan_start).total_seconds(),
            status='failed',
            error_message=str(exc),
        )

        # Retry task
        raise self.retry(exc=exc)
```

### 3.4 Celery Worker Deployment

**Development:**
```bash
# Start all services including Celery
docker-compose up -d

# View Celery logs
docker-compose logs -f celery celery-beat

# Monitor tasks in Flower
open http://localhost:5555
```

**Production (systemd services):**

**File:** `/etc/systemd/system/aegis-celery-worker.service`

```ini
[Unit]
Description=AEGIS Celery Worker
After=network.target postgresql.service redis.service

[Service]
Type=forking
User=aegis
Group=aegis
WorkingDirectory=/opt/aegis/aegis-django
Environment="PATH=/opt/aegis/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=aegis_project.settings.production"
ExecStart=/opt/aegis/venv/bin/celery multi start worker1 \
    -A aegis_project \
    --pidfile=/var/run/celery/%n.pid \
    --logfile=/var/log/celery/%n%I.log \
    --loglevel=INFO \
    --concurrency=4 \
    --max-tasks-per-child=100
ExecStop=/opt/aegis/venv/bin/celery multi stopwait worker1 \
    --pidfile=/var/run/celery/%n.pid
ExecReload=/opt/aegis/venv/bin/celery multi restart worker1 \
    -A aegis_project \
    --pidfile=/var/run/celery/%n.pid \
    --logfile=/var/log/celery/%n%I.log \
    --loglevel=INFO
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 4. CI/CD Pipeline (GitHub Actions)

### 4.1 Pipeline Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Developer pushes code to feature branch                │
└────────────────┬────────────────────────────────────────┘
                 ▼
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions: Automated Tests                        │
│  - Linting (flake8, black, isort)                       │
│  - Unit tests (pytest)                                  │
│  - Integration tests (Django TestCase)                  │
│  - Security scan (bandit, safety)                       │
│  - Docker build test                                    │
└────────────────┬────────────────────────────────────────┘
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Pull Request: Code review + status checks              │
└────────────────┬────────────────────────────────────────┘
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Merge to main: Deploy to Staging                       │
│  - Build Docker images                                  │
│  - Push to registry                                     │
│  - Update staging containers                            │
│  - Run smoke tests                                      │
└────────────────┬────────────────────────────────────────┘
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Manual approval: Deploy to Production                  │
│  - Update production containers                         │
│  - Run health checks                                    │
│  - Monitor metrics                                      │
└─────────────────────────────────────────────────────────┘
```

### 4.2 GitHub Actions Workflow

**File:** `.github/workflows/ci-cd.yml`

```yaml
name: AEGIS CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  DOCKER_REGISTRY: ghcr.io
  DOCKER_IMAGE_PREFIX: haslamdb/aegis

jobs:
  # Job 1: Linting and code quality
  lint:
    name: Lint and Format Check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install flake8 black isort mypy

      - name: Run flake8
        run: |
          flake8 aegis-django/ --max-line-length=100 --exclude=migrations

      - name: Check black formatting
        run: |
          black --check aegis-django/

      - name: Check import sorting
        run: |
          isort --check-only aegis-django/

      - name: Type checking with mypy
        run: |
          mypy aegis-django/ --ignore-missing-imports

  # Job 2: Security scanning
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install bandit safety

      - name: Run bandit (security linter)
        run: |
          bandit -r aegis-django/ -x */tests/*,*/migrations/*

      - name: Check dependencies for vulnerabilities
        run: |
          pip install -r aegis-django/requirements.txt
          safety check --json

      - name: Scan for secrets
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD

  # Job 3: Unit and integration tests
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: aegis_test
          POSTGRES_USER: aegis_test
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r aegis-django/requirements.txt
          pip install -r aegis-django/requirements-dev.txt

      - name: Run Django migrations
        env:
          DATABASE_URL: postgresql://aegis_test:test_password@localhost:5432/aegis_test
          DJANGO_SETTINGS_MODULE: aegis_project.settings.testing
        run: |
          cd aegis-django
          python manage.py migrate --noinput

      - name: Run unit tests
        env:
          DATABASE_URL: postgresql://aegis_test:test_password@localhost:5432/aegis_test
          DJANGO_SETTINGS_MODULE: aegis_project.settings.testing
          REDIS_URL: redis://localhost:6379/0
        run: |
          cd aegis-django
          pytest apps/ \
            --cov=apps \
            --cov-report=xml \
            --cov-report=term-missing \
            --junitxml=test-results.xml \
            -v

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./aegis-django/coverage.xml
          flags: unittests
          name: codecov-umbrella

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: aegis-django/test-results.xml

  # Job 4: Build Docker images
  build:
    name: Build Docker Images
    runs-on: ubuntu-latest
    needs: [lint, security, test]
    if: github.event_name == 'push'
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.DOCKER_REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.DOCKER_REGISTRY }}/${{ env.DOCKER_IMAGE_PREFIX }}-django
          tags: |
            type=ref,event=branch
            type=sha,prefix={{branch}}-
            type=semver,pattern={{version}}

      - name: Build and push Django image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.django
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push Flask image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.flask
          push: true
          tags: ${{ env.DOCKER_REGISTRY }}/${{ env.DOCKER_IMAGE_PREFIX }}-flask:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # Job 5: Deploy to staging (auto)
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: [build]
    if: github.ref == 'refs/heads/develop' && github.event_name == 'push'
    environment:
      name: staging
      url: https://aegis-staging.cchmc.org
    steps:
      - name: Deploy to staging server
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: ${{ secrets.STAGING_USER }}
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/aegis
            docker-compose pull
            docker-compose up -d --no-deps django celery
            docker-compose exec -T django python manage.py migrate --noinput
            docker-compose exec -T django python manage.py collectstatic --noinput

      - name: Run smoke tests
        run: |
          curl -f https://aegis-staging.cchmc.org/health/ || exit 1
          curl -f https://aegis-staging.cchmc.org/api/health/ || exit 1

      - name: Notify Slack
        if: always()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Staging deployment ${{ job.status }}'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}

  # Job 6: Deploy to production (manual approval)
  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: [build]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment:
      name: production
      url: https://aegis-asp.com
    steps:
      - name: Deploy to production server
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/aegis
            docker-compose pull
            docker-compose up -d --no-deps django celery
            docker-compose exec -T django python manage.py migrate --noinput
            docker-compose exec -T django python manage.py collectstatic --noinput

      - name: Health check
        run: |
          curl -f https://aegis-asp.com/health/ || exit 1
          curl -f https://aegis-asp.com/api/health/ || exit 1

      - name: Notify Slack
        if: always()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Production deployment ${{ job.status }}'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}

      - name: Create Sentry release
        uses: getsentry/action-release@v1
        env:
          SENTRY_AUTH_TOKEN: ${{ secrets.SENTRY_AUTH_TOKEN }}
          SENTRY_ORG: cincinnati-childrens
          SENTRY_PROJECT: aegis
        with:
          environment: production
          version: ${{ github.sha }}
```

---

## 5. Monitoring and Alerting Strategy

### 5.1 Monitoring Stack

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| **Sentry** | Error tracking and crash reporting | Django + Celery integration |
| **APM (New Relic/Datadog)** | Performance monitoring, slow queries | Django middleware |
| **Prometheus + Grafana** | Metrics (requests/sec, latency, DB connections) | Exporters + dashboards |
| **Health Checks** | Uptime monitoring | `/health/` endpoints |
| **Log Aggregation** | Centralized logging (ELK or Splunk) | Docker log drivers |

### 5.2 Sentry Configuration

**File:** `aegis-django/aegis_project/settings/production.py`

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

sentry_sdk.init(
    dsn=os.environ.get('SENTRY_DSN'),
    integrations=[
        DjangoIntegration(),
        CeleryIntegration(),
        RedisIntegration(),
    ],
    environment='production',
    release=os.environ.get('GIT_COMMIT', 'unknown'),

    # Send 100% of errors
    traces_sample_rate=0.1,  # 10% of transactions for performance monitoring

    # Filter sensitive data
    send_default_pii=False,
    before_send=remove_phi_from_sentry,
)


def remove_phi_from_sentry(event, hint):
    """Remove PHI from Sentry events before sending."""
    # Redact sensitive fields
    if 'request' in event:
        if 'data' in event['request']:
            event['request']['data'] = '[REDACTED]'
        if 'cookies' in event['request']:
            event['request']['cookies'] = {}

    # Redact patient identifiers in breadcrumbs
    if 'breadcrumbs' in event:
        for crumb in event['breadcrumbs']:
            if 'data' in crumb:
                crumb['data'] = '[REDACTED]'

    return event
```

### 5.3 Health Check Endpoints

**File:** `aegis-django/apps/core/views.py`

```python
"""Health check endpoints for monitoring."""

from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
import redis


def health_check(request):
    """
    Simple health check endpoint.
    Returns 200 if application is healthy, 503 otherwise.
    """
    return JsonResponse({
        'status': 'ok',
        'timestamp': timezone.now().isoformat(),
    })


def health_check_detailed(request):
    """
    Detailed health check with database, cache, and Celery status.
    For internal monitoring (not exposed publicly).
    """
    checks = {
        'django': True,
        'database': False,
        'cache': False,
        'celery': False,
    }

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks['database'] = True
    except Exception as e:
        checks['database_error'] = str(e)

    # Cache check
    try:
        cache.set('health_check', 'ok', 1)
        checks['cache'] = cache.get('health_check') == 'ok'
    except Exception as e:
        checks['cache_error'] = str(e)

    # Celery check (inspect active workers)
    try:
        from aegis_project.celery import app
        inspect = app.control.inspect()
        active_workers = inspect.active()
        checks['celery'] = bool(active_workers)
        checks['celery_workers'] = len(active_workers) if active_workers else 0
    except Exception as e:
        checks['celery_error'] = str(e)

    status_code = 200 if all(
        [checks['django'], checks['database'], checks['cache'], checks['celery']]
    ) else 503

    return JsonResponse(checks, status=status_code)
```

### 5.4 Grafana Dashboards

**Key Metrics to Monitor:**

1. **Application Health**
   - Request rate (req/sec)
   - Error rate (%)
   - Response time (p50, p95, p99)
   - 5xx errors

2. **Database Performance**
   - Active connections
   - Query execution time
   - Slow queries (> 1s)
   - Connection pool saturation

3. **Celery Performance**
   - Task queue length
   - Task execution time
   - Failed tasks
   - Worker availability

4. **Infrastructure**
   - CPU usage
   - Memory usage
   - Disk I/O
   - Network throughput

### 5.5 Alerting Rules

| Alert | Threshold | Severity | Action |
|-------|-----------|----------|--------|
| **High error rate** | > 5% for 5 min | Critical | Page on-call |
| **API latency** | p95 > 2s for 10 min | Warning | Investigate |
| **Celery queue backup** | > 100 tasks for 15 min | Warning | Scale workers |
| **Database connections** | > 80% of max | Warning | Check for leaks |
| **Disk space** | < 10% free | Critical | Expand storage |
| **Health check failure** | 3 consecutive failures | Critical | Restart service |

---

## 6. Production Deployment Architecture

### 6.1 Cincinnati Children's Hospital Infrastructure

**Deployment Model:** On-premises virtual machines within CCHMC's DMZ

```
┌─────────────────────────────────────────────────────────────────┐
│                CCHMC Hospital Network                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   DMZ (AEGIS Servers)                      │  │
│  │  ┌───────────────┐   ┌───────────────┐   ┌─────────────┐ │  │
│  │  │  Load Balancer│   │  Web Server 1 │   │ Web Server 2│ │  │
│  │  │   (HAProxy)   │──▶│ Nginx + Django│   │Nginx + Django│ │  │
│  │  └───────────────┘   └───────┬───────┘   └──────┬──────┘ │  │
│  │                               │                   │        │  │
│  │  ┌───────────────────────────┼───────────────────┘        │  │
│  │  │                           ▼                             │  │
│  │  │  ┌───────────────┐   ┌───────────────┐                │  │
│  │  │  │ App Server 1  │   │ App Server 2  │                │  │
│  │  │  │ Django + Celery│   │Django + Celery│               │  │
│  │  │  └───────┬───────┘   └───────┬───────┘                │  │
│  │  │          │                     │                        │  │
│  │  │          └──────────┬──────────┘                        │  │
│  │  │                     ▼                                   │  │
│  │  │          ┌────────────────────┐                         │  │
│  │  │          │   PostgreSQL       │                         │  │
│  │  │          │   (Primary + Standby)                        │  │
│  │  │          └────────────────────┘                         │  │
│  │  │                     ▲                                   │  │
│  │  │          ┌──────────┴──────────┐                        │  │
│  │  │          │      Redis          │                        │  │
│  │  │          │  (Sentinel cluster) │                        │  │
│  │  │          └─────────────────────┘                        │  │
│  └──┼────────────────────────────────────────────────────────┘  │
│     │                                                            │
│     │  ┌─────────────────────────────────────────────────────┐  │
│     │  │            Internal Network                         │  │
│     └─▶│  ┌──────────────┐   ┌──────────────┐               │  │
│        │  │  Epic FHIR   │   │  Clarity DB  │               │  │
│        │  │   Server     │   │   (Read-only)│               │  │
│        │  └──────────────┘   └──────────────┘               │  │
│        │  ┌──────────────┐   ┌──────────────┐               │  │
│        │  │ LDAP/Active  │   │  SAML SSO    │               │  │
│        │  │  Directory   │   │   Provider   │               │  │
│        │  └──────────────┘   └──────────────┘               │  │
│        └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Server Specifications (Recommended)

| Server Type | Count | Specs | Purpose |
|-------------|-------|-------|---------|
| **Web Servers** | 2 | 4 vCPU, 8GB RAM, 100GB SSD | Nginx + Django (web tier) |
| **App Servers** | 2 | 8 vCPU, 16GB RAM, 200GB SSD | Django + Celery workers |
| **Database** | 2 | 8 vCPU, 32GB RAM, 500GB SSD | PostgreSQL (primary + standby) |
| **Redis** | 3 | 2 vCPU, 4GB RAM, 50GB SSD | Redis Sentinel cluster |
| **Load Balancer** | 2 | 2 vCPU, 4GB RAM, 50GB SSD | HAProxy (active/passive) |

### 6.3 Docker Compose for Production

**File:** `docker-compose.prod.yml`

```yaml
version: '3.8'

services:
  django:
    image: ${DOCKER_REGISTRY}/aegis-django:${VERSION}
    deploy:
      replicas: 4
      restart_policy:
        condition: on-failure
        max_attempts: 3
    environment:
      - DJANGO_SETTINGS_MODULE=aegis_project.settings.production
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - CELERY_BROKER_URL=${CELERY_BROKER_URL}
      - SECRET_KEY=${DJANGO_SECRET_KEY}
      - ALLOWED_HOSTS=${ALLOWED_HOSTS}
      - SENTRY_DSN=${SENTRY_DSN}
    volumes:
      - django_static:/app/staticfiles:ro
      - django_media:/app/media
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://splunk.cchmc.org:514"
        tag: "aegis-django"
    networks:
      - aegis_network

  celery:
    image: ${DOCKER_REGISTRY}/aegis-django:${VERSION}
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure
    environment:
      - DJANGO_SETTINGS_MODULE=aegis_project.settings.production
      - DATABASE_URL=${DATABASE_URL}
      - CELERY_BROKER_URL=${CELERY_BROKER_URL}
    command: celery -A aegis_project worker --loglevel=info --concurrency=8
    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://splunk.cchmc.org:514"
        tag: "aegis-celery"
    networks:
      - aegis_network

  nginx:
    image: nginx:1.25-alpine
    volumes:
      - ./docker/nginx/prod.conf:/etc/nginx/nginx.conf:ro
      - django_static:/usr/share/nginx/html/static:ro
      - /etc/ssl/certs/aegis.crt:/etc/nginx/ssl/cert.pem:ro
      - /etc/ssl/private/aegis.key:/etc/nginx/ssl/key.pem:ro
    ports:
      - "443:443"
    depends_on:
      - django
    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://splunk.cchmc.org:514"
        tag: "aegis-nginx"
    networks:
      - aegis_network

volumes:
  django_static:
  django_media:

networks:
  aegis_network:
    external: true
```

---

## 7. Database Migration Strategy

### 7.1 Shared Database During Transition

During the migration, **Flask and Django will share the same PostgreSQL database**. This eliminates the need for data synchronization between two databases.

**Strategy:**
1. **Phase 1:** Flask uses existing SQLite + PostgreSQL (for new modules)
2. **Phase 2:** Migrate all Flask data to PostgreSQL
3. **Phase 3:** Django apps access same PostgreSQL tables (via Django ORM)
4. **Phase 4:** After full migration, decommission Flask

### 7.2 Database Schema Compatibility

**File:** `scripts/migrate_sqlite_to_postgres.py`

```python
"""
Migrate AEGIS SQLite databases to PostgreSQL.
Preserves all existing data and maintains compatibility.
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values

def migrate_alerts_db(sqlite_path, postgres_dsn):
    """Migrate alert_store SQLite to PostgreSQL."""
    # Connect to databases
    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = psycopg2.connect(postgres_dsn)

    # ... migration logic ...
```

### 7.3 PostgreSQL Setup

**File:** `scripts/init_postgres.sql`

```sql
-- Create AEGIS database and user
CREATE USER aegis_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE aegis OWNER aegis_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aegis TO aegis_user;

-- Enable extensions
\c aegis
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Full-text search
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- Advanced indexing

-- Create schemas
CREATE SCHEMA IF NOT EXISTS flask;  -- Legacy Flask tables
CREATE SCHEMA IF NOT EXISTS django;  -- New Django tables
GRANT ALL ON SCHEMA flask TO aegis_user;
GRANT ALL ON SCHEMA django TO aegis_user;
```

---

## 8. Rollback and Disaster Recovery

### 8.1 Rollback Procedures

**Scenario 1: Django module has critical bug**

```bash
# Option A: Route traffic back to Flask (instant)
sudo vim /etc/nginx/conf.d/aegis.conf
# Change proxy_pass for affected module from django to flask
sudo systemctl reload nginx

# Option B: Deploy previous Docker image
cd /opt/aegis
docker-compose pull aegis-django:previous-sha
docker-compose up -d django
```

**Scenario 2: Database migration breaks application**

```bash
# Rollback Django migration
docker-compose exec django python manage.py migrate app_name previous_migration

# Restore database from backup (if needed)
psql aegis < /backups/aegis_$(date -d "1 hour ago" +%Y%m%d_%H%M).sql
```

### 8.2 Backup Strategy

**PostgreSQL Backups:**
```bash
# Daily full backup (via cron at 2:00 AM)
0 2 * * * pg_dump -U aegis_user -h localhost aegis | gzip > /backups/aegis_$(date +\%Y\%m\%d_\%H\%M).sql.gz

# Retain: 7 daily, 4 weekly, 12 monthly
```

**Redis Backups:**
- Redis AOF (append-only file) enabled
- Daily RDB snapshot to disk

**Docker Image Backups:**
- All images tagged with Git SHA
- Retain last 10 versions in registry

---

## 9. Security Hardening

### 9.1 Docker Security

**Best Practices:**
- ✅ Run containers as non-root user
- ✅ Use minimal base images (Alpine)
- ✅ Scan images for vulnerabilities (Trivy)
- ✅ Use Docker secrets for sensitive data
- ✅ Enable AppArmor/SELinux profiles
- ✅ Limit container resources (CPU/memory)

### 9.2 Network Security

**Firewall Rules:**
```bash
# Allow only necessary ports
iptables -A INPUT -p tcp --dport 443 -j ACCEPT  # HTTPS
iptables -A INPUT -p tcp --dport 22 -j ACCEPT   # SSH (from jump host only)
iptables -A INPUT -j DROP  # Block all other inbound

# Internal network only for database
iptables -A INPUT -p tcp --dport 5432 -s 10.x.x.0/24 -j ACCEPT
```

### 9.3 HIPAA Compliance Checklist

- [ ] Encryption at rest (PostgreSQL TDE or LUKS)
- [ ] Encryption in transit (TLS 1.2+)
- [ ] Access logging (all authentication events)
- [ ] Audit logging (all PHI access)
- [ ] Role-based access control (Django permissions)
- [ ] Session timeout (15 minutes idle)
- [ ] Strong password policy (AD-enforced)
- [ ] Multi-factor authentication (via SSO)
- [ ] Automated backup with encryption
- [ ] Disaster recovery plan (documented)
- [ ] Security incident response plan
- [ ] Regular vulnerability scanning
- [ ] Penetration testing (annual)

---

## 10. Next Steps & Recommendations

### 10.1 Immediate Actions (Week 1-2)

1. **Set up development environment**
   - Create `docker-compose.yml` based on Section 1.2
   - Test local Flask + Django side-by-side deployment
   - Verify Nginx routing works correctly

2. **Configure CI/CD pipeline**
   - Set up GitHub Actions workflow (Section 4.2)
   - Add required secrets to GitHub repository
   - Test automated builds and deployments

3. **Provision staging infrastructure**
   - Request VMs from CCHMC IT
   - Install Docker and Docker Compose
   - Set up PostgreSQL and Redis

### 10.2 Migration Readiness Checklist

Before migrating first module:
- [ ] Docker Compose development environment working
- [ ] CI/CD pipeline passing all tests
- [ ] Nginx routing tested with mock Django app
- [ ] Celery workers processing test tasks
- [ ] Health checks returning 200 OK
- [ ] Sentry receiving test errors
- [ ] Database backups automated
- [ ] Rollback procedure documented and tested

### 10.3 Team Coordination

**DevOps Specialist responsibilities during migration:**
- Monitor deployments and infrastructure health
- Update Nginx routing as modules are migrated
- Manage Celery task scheduling
- Respond to production incidents
- Maintain CI/CD pipeline
- Coordinate with CCHMC IT for network/firewall changes

---

## Appendix: Useful Commands

### Docker Compose
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f django celery

# Restart service
docker-compose restart django

# Scale workers
docker-compose up -d --scale celery=4

# Run Django command
docker-compose exec django python manage.py migrate

# Access Django shell
docker-compose exec django python manage.py shell
```

### Nginx
```bash
# Test configuration
docker-compose exec nginx nginx -t

# Reload configuration (zero downtime)
docker-compose exec nginx nginx -s reload

# View error log
docker-compose exec nginx tail -f /var/log/nginx/error.log
```

### Celery
```bash
# Inspect active tasks
docker-compose exec celery celery -A aegis_project inspect active

# Purge all tasks from queue
docker-compose exec celery celery -A aegis_project purge

# View scheduled tasks
docker-compose exec celery celery -A aegis_project inspect scheduled
```

### PostgreSQL
```bash
# Access psql
docker-compose exec postgres psql -U aegis_user -d aegis

# Manual backup
docker-compose exec postgres pg_dump -U aegis_user aegis > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U aegis_user aegis < backup.sql
```

---

**End of DevOps Strategy Document**

**Questions or feedback:** Coordinate with Django Architect and Security Specialist for implementation details.
