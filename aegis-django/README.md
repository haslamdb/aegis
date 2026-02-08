# AEGIS Django

Django migration of the AEGIS Flask application for enterprise deployment at Cincinnati Children's Hospital.

## Project Status

**Current Phase:** Phase 1 - Infrastructure & Core Setup (In Progress)

**Django Version:** 5.1.5 (latest stable)
**Python Version:** 3.12

## What's Been Completed

### Phase 1.1 - Django Project Setup ✅
- [x] Created Django project structure with split settings (base, development, production)
- [x] Installed Django 5.1.5 with all core dependencies
- [x] Set up environment-based configuration (.env files)
- [x] Created requirements files (base, development, production)
- [x] Configured logging (django.log + audit.log for HIPAA compliance)
- [x] Set up security settings (HSTS, CSP, secure cookies, session timeout)
- [x] Configured REST Framework with token authentication
- [x] Set up Celery for background tasks
- [x] Configured django-auditlog for HIPAA audit trails
- [x] Initial database migrations completed

### Phase 1.2 - Core Shared App ✅
- [x] Created `apps/core/` with base models and utilities
- [x] Base models: `TimeStampedModel`, `UUIDModel`, `SoftDeletableModel`, `PatientRelatedModel`
- [x] Custom managers: `SoftDeletableManager`, `ActiveManager`, `TimeRangeManager`
- [x] Utility functions: age calculations, MRN formatting, date helpers
- [x] Registered core app in Django settings

### Phase 1.3 - Authentication & SSO ✅
- [x] Created `apps/authentication/` with custom User model
- [x] 4-role RBAC system: ASP Pharmacist, Infection Preventionist, Physician, Admin
- [x] SSO integration: SAML 2.0 and LDAP backends with AD group mapping
- [x] HIPAA audit middleware: Logs all requests, sessions, and data access
- [x] User session tracking: Login/logout tracking, IP address, user agent
- [x] Permission system: Decorators and mixins for view protection
- [x] Security features: Account lockout (5 failed attempts), failed login tracking
- [x] Django admin interface: User management with role badges and status indicators
- [x] Database migrations: Applied successfully with custom User model

### Phase 1.4 - Shared Services ✅
- [x] Created `apps/alerts/` - Unified alert system for all AEGIS modules
- [x] Alert model: 27 alert types, 5 severity levels, 7 status states, UUID primary key
- [x] AlertAudit model: HIPAA-compliant audit trail with signal-based logging
- [x] Alert manager: 7 custom query methods (active, actionable, by_type, etc.)
- [x] Created `apps/metrics/` - Activity tracking and analytics
- [x] ProviderActivity model: Tracks all ASP/IP actions with user, module, duration
- [x] DailySnapshot model: Aggregated metrics ready for Celery tasks
- [x] Created `apps/notifications/` - Multi-channel notification system
- [x] NotificationLog model: Email, Teams, SMS delivery tracking
- [x] Django admin: Colored badges for alert types, severity, and status
- [x] Database migrations: 3 new apps with 5 models, proper indexes and foreign keys

## Project Structure

```
aegis-django/
├── aegis_project/              # Django project
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py            # Shared settings
│   │   ├── development.py     # Dev settings (SQLite, DEBUG=True)
│   │   └── production.py      # Production settings (PostgreSQL, HIPAA security)
│   ├── urls.py
│   └── wsgi.py
├── apps/                       # Django apps
│   └── core/                  # ✅ Core base models & utilities
│       ├── models.py          # TimeStampedModel, UUIDModel, etc.
│       ├── managers.py        # Custom model managers
│       └── utils.py           # Helper functions
├── requirements/
│   ├── base.txt              # Django 5.1.5 + core deps
│   ├── development.txt       # Debug toolbar, testing
│   └── production.txt        # Gunicorn, Sentry, WhiteNoise
├── logs/                      # Application logs
├── static/                    # Static files (CSS, JS, images)
├── templates/                 # Global templates
├── media/                     # User-uploaded files
├── .env                       # Environment variables
└── manage.py
```

## Key Technologies

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | Django | 5.1.5 |
| API | Django REST Framework | 3.15.2 |
| Database | PostgreSQL (prod) / SQLite (dev) | 16+ / 3 |
| Task Queue | Celery | 5.4.0 |
| Cache/Broker | Redis | 5.2.1 |
| Audit Logging | django-auditlog | 3.0.0 |
| API Docs | drf-spectacular | 0.28.0 |

## Getting Started

### 1. Setup Virtual Environment

```bash
cd aegis-django
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements/development.txt
```

### 3. Environment Configuration

Copy `.env.example` to `.env` and update with your settings:

```bash
cp .env.example .env
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Run Development Server

```bash
python manage.py runserver
```

Visit: http://localhost:8000/admin

## Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Django Settings
DJANGO_SETTINGS_MODULE=aegis_project.settings.development
SECRET_KEY=your-secret-key
DEBUG=True

# Database (Production)
DB_NAME=aegis
DB_USER=aegis_user
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

# Celery/Redis
CELERY_BROKER_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/1

# Security
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

## Security Features (HIPAA Compliance)

✅ **Implemented:**
- HTTPS enforcement (HSTS, SSL redirect)
- Secure session cookies (15-minute timeout, HttpOnly)
- CSRF protection (enabled by default)
- Security headers (X-Frame-Options, X-Content-Type-Options)
- Content Security Policy (CSP)
- Audit logging (django-auditlog) with 7-year retention
- SQL injection protection (Django ORM)
- Password validation (complexity requirements)

🔜 **Planned (Phase 1.3-1.5):**
- SSO integration (SAML + LDAP)
- Role-based access control (4 roles)
- MFA validation via SAML
- Rate limiting and brute-force protection
- Vulnerability scanning
- PostgreSQL encryption at rest (Azure TDE)

## Next Steps (Phase 1 Remaining)

### Phase 1.3 - Authentication & SSO ✅ COMPLETE (Week 2)
- [x] Create authentication app
- [x] Implement custom User model with RBAC (4 roles)
- [x] Configure SAML + LDAP authentication backends
- [x] Set up permission decorators and mixins
- [x] Create audit middleware for HIPAA logging
- [x] Implement user session tracking
- [x] Map AD groups to Django roles
- [x] Create superuser and test authentication

### Phase 1.4 - Shared Services ✅ COMPLETE (Week 3)
- [x] Create alerts app (unified alert system)
- [x] Create metrics app (activity tracking)
- [x] Create notifications app (email, Teams, SMS)
- [x] Alert model: 27 alert types, 5 severity levels, UUID primary key
- [x] Metrics models: ProviderActivity, DailySnapshot
- [x] Notifications model: NotificationLog with multi-channel support
- [x] Django admin interfaces with colored badges
- [x] Signal-based audit logging for all alert actions
- [x] Database migrations applied successfully

### Phase 1.5 - Database Setup (Week 4)
- [ ] Set up PostgreSQL for staging/production
- [ ] Configure Azure Database for PostgreSQL with TDE
- [ ] Set up Azure Key Vault for encryption keys
- [ ] Configure connection pooling
- [ ] Set up automated backups
- [ ] Test database encryption

## Testing

```bash
# Run tests
python manage.py test

# Run with coverage
pytest --cov=apps

# Check code quality
flake8 apps/
black apps/
isort apps/
mypy apps/
```

## Docker (Coming in Phase 7)

Docker Compose setup will include:
- Django app container
- PostgreSQL container
- Redis container (Celery broker)
- Celery worker container
- Nginx container (reverse proxy)

## Migration Strategy

**Zero-Downtime Approach:**
1. Run Flask and Django side-by-side
2. Migrate modules one at a time using Nginx path-based routing
3. Route traffic: `/dosing-verification/` → Django, everything else → Flask
4. Gradual cutover with rollback capability at each step
5. Final cutover only after all modules migrated and tested

**Migration Order (Phases 3-4):**
1. Action Analytics (read-only, lowest risk)
2. MDRO Surveillance
3. Outbreak Detection
4. Dosing Verification
5. Drug-Bug Mismatch
6. Surgical Prophylaxis
7. Guideline Adherence
8. HAI Detection (complex, critical)
9. ABX Approvals (critical active workflow, migrate last)
10. NHSN Reporting

## Documentation

- **Django Migration Plan:** `/home/david/projects/aegis/docs/DJANGO_MIGRATION_PLAN.md`
- **Architecture Design:** `/home/david/projects/aegis/docs/django_architecture_detailed.md`
- **Security Architecture:** `/home/david/projects/aegis/docs/django_security_architecture.md`
- **Phase 1 Prep:** `/home/david/projects/aegis/docs/phase1_prep/`

## Team Coordination

This migration is being developed with AI agent collaboration:
- **Django Architect:** Overall architecture and model design
- **Security Specialist:** SSO, HIPAA compliance, audit logging
- **DevOps Specialist:** Docker, CI/CD, Azure deployment

## License

Internal use only - Cincinnati Children's Hospital

---

**Last Updated:** 2026-02-07
**Phase:** 1 (Infrastructure & Core Setup)
**Status:** In Progress
