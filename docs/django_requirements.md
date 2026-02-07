# Django Requirements Files

This document outlines the Python dependencies for the AEGIS Django migration.

---

## Requirements Structure

```
requirements/
├── base.txt           # Core dependencies (all environments)
├── development.txt    # Development tools
├── production.txt     # Production optimizations
└── test.txt          # Testing dependencies
```

---

## base.txt - Core Dependencies

```txt
# Django core
Django==4.2.9
django-environ==0.11.2

# Database
psycopg2-binary==2.9.9

# REST API
djangorestframework==3.14.0
django-filter==23.5
djangorestframework-simplejwt==5.3.1
drf-spectacular==0.27.0  # API documentation (OpenAPI/Swagger)

# Authentication
django-auth-ldap==4.6.0
python3-saml==1.16.0
djangosaml2==1.7.0

# Security & HIPAA Compliance
django-auditlog==2.3.0
django-encrypted-model-fields==0.6.5
django-csp==3.8  # Content Security Policy
django-permissions-policy==4.18.0

# Background tasks
celery==5.3.4
redis==5.0.1
django-celery-beat==2.5.0  # Periodic tasks
django-celery-results==2.5.1

# Notifications
requests==2.31.0  # For Teams webhooks, external APIs
twilio==8.11.1  # SMS notifications

# FHIR Client (keep existing)
fhirclient==4.1.0

# LLM Integration
openai==1.7.0
anthropic==0.8.0

# Utilities
python-dateutil==2.8.2
pytz==2023.3.post1

# Monitoring & Logging
sentry-sdk==1.39.2

# CORS (for API)
django-cors-headers==4.3.1

# Health checks
django-health-check==3.18.1
```

---

## development.txt - Development Tools

```txt
-r base.txt

# Debugging
django-debug-toolbar==4.2.0
django-extensions==3.2.3
ipython==8.19.0

# Code quality
black==23.12.1
flake8==7.0.0
isort==5.13.2
pylint==3.0.3
mypy==1.8.0
django-stubs==4.2.7

# Testing
pytest==7.4.4
pytest-django==4.7.0
pytest-cov==4.1.0
factory-boy==3.3.0
faker==22.0.0

# Documentation
sphinx==7.2.6
sphinx-rtd-theme==2.0.0

# Database inspection
django-querycount==0.8.3  # Query profiling
```

---

## production.txt - Production Optimizations

```txt
-r base.txt

# WSGI server
gunicorn==21.2.0
gevent==23.9.1

# Static files
whitenoise==6.6.0  # Serve static files efficiently

# Caching
django-redis==5.4.0

# Performance monitoring
django-silk==5.0.4

# Database connection pooling
psycopg2==2.9.9  # Use binary for prod (not psycopg2-binary)

# Azure-specific (if deploying to Azure)
django-storages[azure]==1.14.2  # For Azure Blob Storage (media files)
```

---

## test.txt - Testing Dependencies

```txt
-r base.txt

# Testing frameworks
pytest==7.4.4
pytest-django==4.7.0
pytest-cov==4.1.0
pytest-xdist==3.5.0  # Parallel testing
pytest-mock==3.12.0

# Test data
factory-boy==3.3.0
faker==22.0.0

# Coverage reporting
coverage==7.4.0

# API testing
requests-mock==1.11.0
```

---

## Installation Instructions

### Development Environment

```bash
cd /home/david/projects/aegis/aegis_django

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements/development.txt

# Verify installation
python manage.py --version
```

### Production Environment

```bash
# On production server
pip install -r requirements/production.txt
```

### CI/CD Pipeline

```bash
# In GitHub Actions / GitLab CI
pip install -r requirements/test.txt
pytest
```

---

## Package Rationale

### Core Django Packages

**Django 4.2.9**
- LTS version (support until April 2026)
- Production-ready, stable
- Excellent security track record

**django-environ**
- Manage environment variables from `.env` files
- Clean separation of config from code (12-factor app)

**psycopg2-binary**
- PostgreSQL adapter for Django
- Binary distribution for easy installation (dev)
- Use `psycopg2` (compiled) for production

### REST API

**djangorestframework (DRF)**
- De facto standard for Django REST APIs
- Serializers, ViewSets, authentication, permissions
- Browsable API for development

**django-filter**
- Powerful filtering for DRF endpoints
- Example: `/api/alerts/?severity=critical&status=pending`

**djangorestframework-simplejwt**
- JWT token authentication for API
- Needed for mobile apps, third-party integrations

**drf-spectacular**
- OpenAPI 3.0 schema generation
- Automatic Swagger UI documentation
- Replaces deprecated `drf-yasg`

### Authentication

**django-auth-ldap**
- LDAP/Active Directory authentication
- Map AD groups → Django groups/roles
- Essential for Cincinnati Children's SSO

**python3-saml**
- SAML 2.0 support
- Single Sign-On for enterprise
- Handles SAML assertions, metadata

**djangosaml2**
- Django integration for python3-saml
- Provides views, middleware for SAML flow

### Security & HIPAA Compliance

**django-auditlog**
- Automatic audit trail for all model changes
- Tracks who, what, when for HIPAA compliance
- Can query historical changes

**django-encrypted-model-fields**
- Encrypt sensitive fields at rest
- Uses Fernet (symmetric encryption)
- Example: encrypt patient SSN, phone numbers

**django-csp**
- Content Security Policy headers
- Prevents XSS attacks
- Configurable per-view

**django-permissions-policy**
- Permissions-Policy headers (formerly Feature-Policy)
- Control browser features (camera, microphone, geolocation)

### Background Tasks

**celery**
- Distributed task queue
- For async notifications, scheduled jobs
- Scalable (can add more workers)

**redis**
- Message broker for Celery
- Also used for caching

**django-celery-beat**
- Periodic task scheduler (cron replacement)
- Store schedules in database
- Example: Auto-recheck ABX approvals 3x daily

**django-celery-results**
- Store task results in database
- Query task status, results
- Useful for long-running tasks

### Notifications

**requests**
- For Teams webhooks, external API calls
- FHIR API calls

**twilio**
- SMS notifications
- Voice calls (if needed)

### LLM Integration

**openai**
- For GPT-4 (if using OpenAI)
- HAI extraction, guideline reviews

**anthropic**
- For Claude (if using Anthropic)
- Alternative to OpenAI

### Monitoring

**sentry-sdk**
- Error tracking and performance monitoring
- Automatic exception capture
- Production error alerts

**django-health-check**
- Health check endpoints for load balancer
- Example: `/health/` returns 200 if healthy
- Checks database, cache, Celery

### Development Tools

**django-debug-toolbar**
- SQL query profiling
- Template rendering analysis
- Cache usage inspection

**django-extensions**
- `shell_plus` - Enhanced shell with auto-imported models
- `show_urls` - List all URL patterns
- `runserver_plus` - Werkzeug debugger

**ipython**
- Better REPL for Django shell
- Auto-completion, syntax highlighting

### Code Quality

**black**
- Opinionated code formatter
- Consistent style across team
- `black .` to format all files

**flake8**
- Linting (PEP 8 compliance)
- Catches common errors

**isort**
- Sort imports automatically
- Groups: stdlib, third-party, local

**mypy**
- Static type checking
- Catch type errors before runtime

**django-stubs**
- Type stubs for Django
- Enables mypy to understand Django ORM

### Testing

**pytest-django**
- Better than Django's built-in TestCase
- Fixtures, parametrization
- Parallel testing

**factory-boy**
- Test data factories
- Example: `AlertFactory.create()` creates test alert
- Cleaner than manual object creation

**faker**
- Generate realistic fake data
- Names, addresses, emails, etc.

### Production

**gunicorn**
- WSGI HTTP server
- Production-ready
- Replaces Django's `runserver`

**whitenoise**
- Serve static files efficiently
- No need for separate static file server

**django-redis**
- Redis cache backend
- Session storage in Redis

**django-silk**
- Live profiling and inspection
- SQL query analysis in production (use carefully)

---

## Security Considerations

### HIPAA Compliance

The following packages help meet HIPAA requirements:

1. **django-auditlog** - Audit trail (required)
2. **django-encrypted-model-fields** - Data encryption (required)
3. **django-csp** - Prevent XSS (best practice)
4. **sentry-sdk** - Error monitoring without exposing PHI

### Production Security Checklist

```bash
# Run Django security check
python manage.py check --deploy

# Expected: No critical warnings
```

### Dependency Scanning

```bash
# Install safety
pip install safety

# Check for known vulnerabilities
safety check -r requirements/production.txt
```

---

## Version Pinning Strategy

**Why pin versions?**
- Reproducible builds
- Avoid breaking changes from automatic upgrades
- Easier debugging (know exact versions in production)

**When to upgrade?**
- Security patches: Immediately
- Bug fixes: Review changelog, test, then upgrade
- New features: Quarterly review, upgrade if beneficial

**How to upgrade:**
```bash
# Update all packages to latest
pip install --upgrade -r requirements/base.txt

# Regenerate requirements with exact versions
pip freeze > requirements/base.txt

# Test thoroughly before deploying
pytest
```

---

## Azure-Specific Dependencies

If deploying to Azure, add:

```txt
# Azure PostgreSQL
django-postgres-extensions==0.10.0  # Azure-specific features

# Azure Blob Storage (for media files)
django-storages[azure]==1.14.2
azure-storage-blob==12.19.0

# Azure Key Vault (for secrets)
azure-keyvault-secrets==4.7.0
azure-identity==1.15.0

# Azure Application Insights (monitoring)
opencensus-ext-azure==1.1.13
opencensus-ext-django==0.8.0
```

---

## Installation Order

When setting up a new environment, install in this order:

```bash
# 1. System dependencies (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3.11 python3.11-venv postgresql-client libpq-dev

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip setuptools wheel

# 4. Install requirements
pip install -r requirements/development.txt  # or production.txt

# 5. Verify
python -c "import django; print(django.VERSION)"
```

---

## Common Issues

### Issue: `psycopg2` installation fails

**Solution:**
```bash
# Install PostgreSQL development headers
sudo apt install -y libpq-dev python3-dev

# Retry
pip install psycopg2-binary
```

### Issue: `python3-saml` installation fails

**Solution:**
```bash
# Install libxml2 and libxmlsec1
sudo apt install -y libxml2-dev libxmlsec1-dev libxmlsec1-openssl pkg-config

# Retry
pip install python3-saml
```

### Issue: Conflicting dependencies

**Solution:**
```bash
# Use pip-tools to resolve conflicts
pip install pip-tools
pip-compile requirements/base.in  # Create .in files first
```

---

## Next Steps

1. Create `requirements/` directory in Django project
2. Copy these files into `requirements/`
3. Test installation in clean virtual environment
4. Add `requirements/` to `.gitignore` (keep in repo)
5. Document any custom packages added later

---

**Last Updated:** 2026-02-07
**Maintained By:** Django Architect
