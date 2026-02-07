# Phase 1 Implementation Checklist: Django Infrastructure Setup

**Duration:** Week 1-3
**Status:** Ready to begin
**Owner:** Django Architect + Team

---

## Week 1: Django Project Setup

### Day 1-2: Project Initialization

- [ ] Create Django project directory structure
  ```bash
  cd /home/david/projects/aegis
  mkdir aegis_django
  cd aegis_django
  django-admin startproject aegis_project .
  ```

- [ ] Set up virtual environment
  ```bash
  python3.11 -m venv venv
  source venv/bin/activate
  ```

- [ ] Install core dependencies
  ```bash
  pip install -r requirements/base.txt
  ```

- [ ] Initialize git (in aegis_django/)
  ```bash
  git init
  git add .
  git commit -m "Initial Django project setup"
  ```

- [ ] Create environment-based settings structure
  ```
  aegis_project/
  ├── settings/
  │   ├── __init__.py
  │   ├── base.py
  │   ├── development.py
  │   ├── staging.py
  │   └── production.py
  ```

### Day 3-4: Shared Apps Creation

- [ ] Create core app
  ```bash
  python manage.py startapp core apps/core
  ```

- [ ] Create authentication app
  ```bash
  python manage.py startapp authentication apps/authentication
  ```

- [ ] Create alerts app
  ```bash
  python manage.py startapp alerts apps/alerts
  ```

- [ ] Create metrics app
  ```bash
  python manage.py startapp metrics apps/metrics
  ```

- [ ] Create notifications app
  ```bash
  python manage.py startapp notifications apps/notifications
  ```

- [ ] Create llm_tracking app
  ```bash
  python manage.py startapp llm_tracking apps/llm_tracking
  ```

- [ ] Register all apps in `INSTALLED_APPS`

### Day 5: Database Setup

- [ ] Install PostgreSQL locally (for development)
  ```bash
  sudo apt install postgresql postgresql-contrib
  ```

- [ ] Create development database
  ```bash
  sudo -u postgres createdb aegis_dev
  sudo -u postgres createuser aegis_user
  sudo -u postgres psql -c "ALTER USER aegis_user WITH PASSWORD 'dev_password';"
  sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aegis_dev TO aegis_user;"
  ```

- [ ] Configure database settings in `settings/development.py`

- [ ] Test database connection
  ```bash
  python manage.py dbshell
  ```

---

## Week 2: Authentication & Security

### Day 1-2: User Model & RBAC

- [ ] Design User model (extend AbstractUser)
  - [ ] Add role field (choices: asp_pharmacist, infection_preventionist, physician, admin)
  - [ ] Add department field
  - [ ] Add employee_id field

- [ ] Create Role model (if using separate table)

- [ ] Create Permission model (module-level permissions)

- [ ] Create initial migrations
  ```bash
  python manage.py makemigrations
  python manage.py migrate
  ```

- [ ] Create superuser
  ```bash
  python manage.py createsuperuser
  ```

### Day 3-4: SSO Integration Preparation

- [ ] **Contact Cincinnati Children's IT**
  - [ ] Request SAML metadata XML
  - [ ] Request LDAP connection details:
    - LDAP server URL
    - Base DN structure
    - User DN format (e.g., `uid={username},ou=users,dc=cchmc,dc=org`)
    - Group DN format
  - [ ] Request test environment access
  - [ ] Request sample test credentials

- [ ] Install SSO packages
  ```bash
  pip install django-auth-ldap python3-saml djangosaml2
  ```

- [ ] Create LDAP auth backend
  - [ ] Implement `LDAPAuthBackend` in `apps/authentication/backends.py`
  - [ ] Map LDAP groups to Django roles

- [ ] Create SAML auth backend
  - [ ] Configure SAML settings
  - [ ] Create attribute mapping (username, email, groups)

- [ ] Create placeholder login page (for testing)

### Day 5: Audit Middleware

- [ ] Create `AuditMiddleware` in `apps/authentication/middleware.py`
  - [ ] Log all HTTP requests (method, path, user, IP, timestamp)
  - [ ] Log all data modifications (create, update, delete)
  - [ ] Write to dedicated audit log file (`/var/log/aegis/audit.log`)

- [ ] Configure logging in settings
  - [ ] Set up rotating file handlers
  - [ ] Configure audit log retention (7 years for HIPAA)

- [ ] Test audit logging
  - [ ] Create test request
  - [ ] Verify audit entry in log file

---

## Week 3: Core Models & Security Hardening

### Day 1-2: Core App Models

- [ ] Create `TimeStampedModel` abstract base class
  ```python
  class TimeStampedModel(models.Model):
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          abstract = True
  ```

- [ ] Create `SoftDeletableModel` mixin
  ```python
  class SoftDeletableModel(models.Model):
      deleted_at = models.DateTimeField(null=True, blank=True)

      class Meta:
          abstract = True
  ```

- [ ] Create custom managers
  - [ ] `ActiveManager` (exclude soft-deleted)
  - [ ] `SoftDeleteManager` (include soft-deleted)

### Day 3: Alerts App Models

- [ ] Create `AlertType` enum (TextChoices)
- [ ] Create `AlertStatus` enum (TextChoices)
- [ ] Create `ResolutionReason` enum (TextChoices)
- [ ] Create `AuditAction` enum (TextChoices)

- [ ] Create `Alert` model
  - [ ] All fields from Flask `StoredAlert`
  - [ ] ForeignKey to User for acknowledged_by, resolved_by
  - [ ] JSONField for content
  - [ ] Custom manager with filtering methods

- [ ] Create `AlertAudit` model
  - [ ] ForeignKey to Alert
  - [ ] ForeignKey to User for performed_by
  - [ ] Auto-created via signals

- [ ] Set up signals for auto-audit
  ```python
  @receiver(post_save, sender=Alert)
  def create_audit_entry(sender, instance, created, **kwargs):
      # Create audit entry
  ```

- [ ] Run migrations
  ```bash
  python manage.py makemigrations alerts
  python manage.py migrate alerts
  ```

### Day 4: Metrics App Models

- [ ] Create enums (ActivityType, ModuleSource, etc.)

- [ ] Create `ProviderActivity` model

- [ ] Create `InterventionSession` model

- [ ] Create `InterventionTarget` model

- [ ] Create `InterventionOutcome` model

- [ ] Create `DailySnapshot` model

- [ ] Create `ProviderSession` model

- [ ] Run migrations
  ```bash
  python manage.py makemigrations metrics
  python manage.py migrate metrics
  ```

### Day 5: Security Hardening

- [ ] Enable HTTPS enforcement
  ```python
  SECURE_SSL_REDIRECT = True
  SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
  ```

- [ ] Configure HSTS headers
  ```python
  SECURE_HSTS_SECONDS = 31536000
  SECURE_HSTS_INCLUDE_SUBDOMAINS = True
  SECURE_HSTS_PRELOAD = True
  ```

- [ ] Configure secure cookies
  ```python
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  SESSION_COOKIE_HTTPONLY = True
  CSRF_COOKIE_HTTPONLY = True
  SESSION_COOKIE_SAMESITE = 'Strict'
  CSRF_COOKIE_SAMESITE = 'Strict'
  ```

- [ ] Configure security headers
  ```python
  SECURE_BROWSER_XSS_FILTER = True
  SECURE_CONTENT_TYPE_NOSNIFF = True
  X_FRAME_OPTIONS = 'DENY'
  ```

- [ ] Set up Content Security Policy (CSP)
  ```bash
  pip install django-csp
  ```

- [ ] Configure session timeout (15 minutes)
  ```python
  SESSION_COOKIE_AGE = 900
  SESSION_SAVE_EVERY_REQUEST = True
  ```

- [ ] Run security checklist
  ```bash
  python manage.py check --deploy
  ```

---

## Week 3 (continued): Testing & Documentation

### Testing

- [ ] Create test database
  ```python
  # settings/test.py
  DATABASES = {
      'default': {
          'ENGINE': 'django.db.backends.postgresql',
          'NAME': 'aegis_test',
          # ...
      }
  }
  ```

- [ ] Write model tests
  - [ ] Test Alert model creation
  - [ ] Test Alert audit logging
  - [ ] Test user authentication
  - [ ] Test role-based permissions

- [ ] Run tests
  ```bash
  python manage.py test
  ```

### Documentation

- [ ] Document database schema (ER diagram)
- [ ] Document authentication flow
- [ ] Document role/permission mapping
- [ ] Create developer setup guide
- [ ] Create SSO integration guide for Cincinnati Children's IT

---

## Phase 1 Completion Criteria

Before moving to Phase 2, verify:

✅ **Django Project**
- [ ] Django 4.2+ running successfully
- [ ] All shared apps created and registered
- [ ] Database migrations applied without errors

✅ **Database**
- [ ] PostgreSQL connected and working
- [ ] All core models migrated
- [ ] Test data can be created via Django admin

✅ **Authentication**
- [ ] User model created and working
- [ ] Django admin accessible with superuser
- [ ] LDAP/SAML backends configured (even if not fully tested yet)
- [ ] Role-based permissions defined

✅ **Security**
- [ ] HTTPS enforcement configured
- [ ] Secure cookies configured
- [ ] Audit middleware logging all requests
- [ ] `python manage.py check --deploy` passes with no critical warnings

✅ **Models**
- [ ] Alert model fully migrated from Flask dataclass
- [ ] Metrics models fully migrated
- [ ] Signal-based audit logging working

✅ **Tests**
- [ ] All model tests passing
- [ ] Authentication tests passing
- [ ] Test coverage > 80% for core/auth/alerts/metrics apps

✅ **Documentation**
- [ ] Architecture document complete
- [ ] Developer setup guide written
- [ ] Database schema documented

---

## Dependencies for Next Phase

**Phase 2 requires:**
- ✅ PostgreSQL database fully operational
- ✅ User authentication working (even if just local, SSO can be finalized later)
- ✅ Alert and Metrics models migrated and tested
- ✅ Security hardening complete

**Blockers:**
- [ ] Cincinnati Children's IT response on SSO (can proceed with local auth for now)
- [ ] Security specialist review (can proceed with standard Django security)
- [ ] DevOps specialist review (can proceed with local development setup)

---

## Risk Mitigation

**Risk: SSO integration delayed by Cincinnati Children's IT**
- **Mitigation:** Use Django's built-in auth for development, integrate SSO later

**Risk: PostgreSQL connection issues**
- **Mitigation:** Test with local PostgreSQL first, document Azure-specific settings separately

**Risk: Model migration bugs**
- **Mitigation:** Extensive testing with sample data from Flask SQLite databases

**Risk: Security configuration errors**
- **Mitigation:** Use `python manage.py check --deploy` frequently, review Django security docs

---

## Next Steps After Phase 1

Once Phase 1 is complete:

1. **Phase 2:** Convert remaining shared models (notifications, llm_tracking)
2. **Data Migration:** Create scripts to migrate data from Flask SQLite → Django PostgreSQL
3. **Module Migration:** Begin with Action Analytics (Week 6)

---

**Status:** Ready to begin
**Estimated Duration:** 3 weeks (15 working days)
**Team:** Django Architect + Security Specialist + DevOps Specialist
