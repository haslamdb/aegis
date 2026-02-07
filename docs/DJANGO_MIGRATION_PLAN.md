# AEGIS Flask to Django Migration Plan

**Goal:** Convert AEGIS from Flask to Django for enterprise healthcare deployment at Cincinnati Children's Hospital

**Why Django:**
- Built-in SSO integration (SAML, OAuth2, LDAP)
- Comprehensive audit logging middleware
- ORM with built-in security (SQL injection protection)
- Role-based access control (permissions system)
- CSRF protection by default
- Django admin for management
- Better enterprise deployment support
- HIPAA compliance features available

---

## Migration Strategy: **Incremental Module-by-Module**

**Approach:** Run Flask and Django side-by-side, migrating modules incrementally rather than big-bang cutover.

**Benefits:**
- Zero downtime
- Gradual testing and validation
- Rollback capability at each step
- Preserve working functionality
- Team can learn Django incrementally

---

## Phase 1: Infrastructure & Core Setup (Week 1-2)

### 1.1 Django Project Setup
- [ ] Create new `aegis-django/` directory alongside existing Flask app
- [ ] Initialize Django project: `django-admin startproject aegis_project`
- [ ] Configure settings for development/staging/production
- [ ] Set up PostgreSQL database (migrate from SQLite for production)
- [ ] Configure environment variables (`.env` file)
- [ ] Set up Django admin interface

### 1.2 Authentication & Authorization
- [ ] Install `django-auth-ldap` for Cincinnati Children's LDAP/AD
- [ ] Configure SAML SSO using `djangosaml2` or `python3-saml`
- [ ] Set up User model (extend Django's AbstractUser if needed)
- [ ] Define roles and permissions:
  - `asp_pharmacist` - Full access to ASP modules
  - `infection_preventionist` - HAI detection, outbreak surveillance
  - `physician` - Read-only access, can add notes
  - `admin` - Full system administration
- [ ] Implement permission decorators for views
- [ ] Configure session management (timeout, secure cookies)

### 1.3 Security Configuration
- [ ] Enable HTTPS enforcement (`SECURE_SSL_REDIRECT = True`)
- [ ] Configure HSTS headers
- [ ] Set up CSRF protection (enabled by default)
- [ ] Configure secure cookie settings:
  ```python
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  SESSION_COOKIE_HTTPONLY = True
  CSRF_COOKIE_HTTPONLY = True
  ```
- [ ] Set up Content Security Policy (CSP) headers
- [ ] Configure X-Frame-Options, X-Content-Type-Options
- [ ] Enable SQL injection protection (ORM handles this)
- [ ] Set up rate limiting for API endpoints

### 1.4 Audit Logging
- [ ] Install `django-auditlog` or custom audit middleware
- [ ] Log all data access (who, what, when)
- [ ] Log authentication events (login, logout, failed attempts)
- [ ] Log all data modifications (create, update, delete)
- [ ] Log administrative actions
- [ ] Configure log retention policy (7 years for HIPAA)
- [ ] Set up log export to SIEM if required

### 1.5 Database Setup
- [ ] Install PostgreSQL (production-grade, HIPAA-compliant)
- [ ] Configure connection pooling
- [ ] Enable encryption at rest (PostgreSQL TDE or LUKS)
- [ ] Set up automated backups
- [ ] Configure replication for high availability
- [ ] Create database users with minimal privileges

---

## Phase 2: Core Shared Components (Week 3-4)

### 2.1 Convert Common Models
Priority order (most shared → least shared):

1. **User & Authentication Models**
   - Migrate Flask-Login to Django auth
   - User profiles with roles
   - Session management

2. **Alert Store** (`common/alert_store/`)
   - Convert SQLite schema to Django models
   - `Alert`, `AlertType`, `AlertStatus` models
   - Preserve existing data migration script

3. **Metrics Store** (`common/metrics_store/`)
   - `ProviderActivity`, `ProviderSession`, `MetricsDailySnapshot` models
   - Time-series data handling

4. **Dosing Verification** (`common/dosing_verification/`)
   - `DoseAlert`, `DoseFlag`, `DoseAssessment` models
   - Enums → Django Choices

5. **ABX Approvals** (`common/abx_approvals/`)
   - `ApprovalRequest`, `ApprovalDecision` models

6. **Channels** (`common/channels/`)
   - Keep as-is (email, Teams, SMS) - Django-agnostic
   - Or migrate to Django signals/tasks (Celery)

### 2.2 Create Django Apps Structure
```
aegis_project/
├── manage.py
├── aegis_project/           # Project settings
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   ├── staging.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── authentication/      # SSO, LDAP, user management
│   ├── core/               # Shared models, utilities
│   ├── hai_detection/      # HAI module
│   ├── drug_bug/           # Drug-bug mismatch
│   ├── mdro/              # MDRO surveillance
│   ├── guideline_adherence/
│   ├── surgical_prophylaxis/
│   ├── abx_usage/
│   ├── abx_approvals/
│   ├── nhsn_reporting/
│   ├── outbreak/
│   ├── dosing_verification/
│   ├── action_analytics/
│   └── api/               # DRF API endpoints
├── templates/             # Django templates
├── static/               # Static files (CSS, JS)
└── requirements.txt
```

### 2.3 Set Up Django REST Framework (DRF)
- [ ] Install `djangorestframework`
- [ ] Configure API authentication (token-based, OAuth2)
- [ ] Set up serializers for all models
- [ ] Create ViewSets for CRUD operations
- [ ] Configure API permissions
- [ ] Set up API documentation (drf-spectacular/Swagger)
- [ ] Rate limiting for API endpoints

---

## Phase 3: Migrate Modules (Week 5-12)

**Strategy:** Migrate one module at a time, running both Flask and Django simultaneously using Nginx routing.

### Migration Order (Lowest Risk → Highest Risk):

#### 3.1 Action Analytics (Week 5)
**Why first:** Read-only, no critical workflows, good test case

- [ ] Create Django app: `apps/action_analytics/`
- [ ] Convert models: `ActionAnalyzer` → Django models/queries
- [ ] Convert views: Flask routes → Django class-based views (CBVs)
- [ ] Convert templates: Jinja2 → Django templates (minimal changes)
- [ ] Migrate CSV export endpoints
- [ ] Test all 6 dashboard pages
- [ ] Route `/action-analytics/` to Django, keep rest in Flask

#### 3.2 Dosing Verification (Week 6)
**Why second:** Newest module, cleanest code, API-first

- [ ] Create Django app: `apps/dosing_verification/`
- [ ] Convert models:
  - `DoseAlert`, `DoseFlag`, `DoseAssessment`
  - Enums → Django `TextChoices`
- [ ] Convert rules engine (keep Python logic, wrap in Django)
- [ ] Convert FHIR client (Django-agnostic, minimal changes)
- [ ] Convert views: API endpoints → DRF ViewSets
- [ ] Convert templates: 5 dashboard pages
- [ ] Migrate notifications (Django signals or Celery tasks)
- [ ] Test all 12 rule modules
- [ ] Route `/dosing-verification/` to Django

#### 3.3 MDRO Surveillance (Week 7)
**Why third:** Simple FHIR-based module, no complex state

- [ ] Create Django app: `apps/mdro/`
- [ ] Convert models: `MDROCase`, `MDRODetection`
- [ ] Convert FHIR detection logic
- [ ] Convert dashboard views
- [ ] Route `/mdro/` to Django

#### 3.4 Drug-Bug Mismatch (Week 8)
- [ ] Create Django app: `apps/drug_bug/`
- [ ] Convert models: `DrugBugAlert`
- [ ] Convert FHIR client + matching logic
- [ ] Convert dashboard
- [ ] Route `/drug-bug-mismatch/` to Django

#### 3.5 Guideline Adherence (Week 9)
- [ ] Create Django app: `apps/guideline_adherence/`
- [ ] Convert models: `GuidelineCheck`, `Bundle`
- [ ] Convert LLM review workflow
- [ ] Convert 7 bundles (febrile infant, CAP, etc.)
- [ ] Route `/guideline-adherence/` to Django

#### 3.6 Surgical Prophylaxis (Week 10)
- [ ] Create Django app: `apps/surgical_prophylaxis/`
- [ ] Convert models: `SurgicalCase`, `ProphylaxisEvaluation`
- [ ] Convert compliance checker
- [ ] Convert dashboard
- [ ] Route `/surgical-prophylaxis/` to Django

#### 3.7 HAI Detection (Week 11) - **CRITICAL**
**Why later:** Most complex, critical infection control workflows

- [ ] Create Django app: `apps/hai_detection/`
- [ ] Convert models for all 5 HAI types:
  - CLABSI, SSI, CAUTI, VAE, CDI
- [ ] Convert detection algorithms (5 detectors)
- [ ] Convert FHIR clients (device tracking, cultures, ventilators)
- [ ] Convert LLM extraction (keep as-is, wrap in Django)
- [ ] Convert dashboards (5 HAI type dashboards)
- [ ] Migrate validation framework
- [ ] Test extensively (most critical module)
- [ ] Route `/hai-detection/` to Django

#### 3.8 ABX Approvals (Week 12) - **CRITICAL**
**Why last:** Active clinical workflow, can't break

- [ ] Create Django app: `apps/abx_approvals/`
- [ ] Convert models:
  - `ApprovalRequest`, `ApprovalDecision`, `ReapprovalChain`
- [ ] Convert approval workflow logic
- [ ] Convert auto-recheck scheduler (Django Celery tasks)
- [ ] Convert email notifications (Django signals)
- [ ] Convert dashboard (pharmacy queue)
- [ ] Test re-approval chain logic
- [ ] Route `/abx-approvals/` to Django

#### 3.9 NHSN Reporting (Week 13)
- [ ] Create Django app: `apps/nhsn_reporting/`
- [ ] Convert AU/AR models
- [ ] Convert CSV export logic
- [ ] Route `/nhsn-reporting/` to Django

#### 3.10 Outbreak Detection (Week 14)
- [ ] Create Django app: `apps/outbreak/`
- [ ] Convert clustering algorithm
- [ ] Convert outbreak tracking
- [ ] Route `/outbreak-detection/` to Django

---

## Phase 4: Background Tasks & Scheduling (Week 15)

### 4.1 Set Up Celery
- [ ] Install Celery + Redis/RabbitMQ
- [ ] Configure Celery workers
- [ ] Convert cron jobs to Celery periodic tasks:
  - ABX approvals auto-recheck (3x daily)
  - HAI detection scan (hourly)
  - Metrics aggregation (daily)
  - Auto-accept old alerts (daily)

### 4.2 Configure Django-Q or Celery Beat
- [ ] Periodic task scheduling
- [ ] Task monitoring and retry logic
- [ ] Dead letter queue for failed tasks

---

## Phase 5: API & Mobile Support (Week 16)

### 5.1 Unified API
- [ ] Consolidate all module APIs under `/api/v1/`
- [ ] DRF routers for consistent endpoints
- [ ] API versioning strategy
- [ ] Rate limiting per user role
- [ ] API documentation (Swagger UI)

### 5.2 API Authentication
- [ ] Token-based auth for mobile apps
- [ ] OAuth2 for third-party integrations
- [ ] API key management

---

## Phase 6: Testing & Quality Assurance (Week 17-18)

### 6.1 Automated Testing
- [ ] Unit tests for all models (Django TestCase)
- [ ] Integration tests for all modules
- [ ] API tests (DRF test client)
- [ ] Security tests (OWASP, penetration testing)
- [ ] Performance tests (load testing)
- [ ] HIPAA compliance audit

### 6.2 Data Migration Testing
- [ ] Migrate production data from SQLite to PostgreSQL
- [ ] Verify data integrity (checksums, counts)
- [ ] Test rollback procedures

### 6.3 User Acceptance Testing
- [ ] Pharmacists test ABX approvals workflow
- [ ] Infection preventionists test HAI detection
- [ ] Physicians test read-only access
- [ ] Admin tests user management

---

## Phase 7: Deployment & Infrastructure (Week 19-20)

### 7.1 Containerization (Docker)
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["gunicorn", "aegis_project.wsgi:application"]
```

**Docker Compose:**
- Django app container
- PostgreSQL container
- Redis container (Celery)
- Nginx container (reverse proxy)
- Celery worker container

### 7.2 Infrastructure as Code (Optional)
- [ ] Terraform or Ansible for provisioning
- [ ] Kubernetes manifests if deploying to K8s

### 7.3 CI/CD Pipeline
- [ ] GitHub Actions or GitLab CI
- [ ] Automated testing on PR
- [ ] Automated deployment to staging
- [ ] Manual approval for production

### 7.4 Monitoring & Logging
- [ ] Set up Sentry for error tracking
- [ ] Configure logging (syslog, CloudWatch, Splunk)
- [ ] APM monitoring (New Relic, Datadog)
- [ ] Health check endpoints
- [ ] Uptime monitoring

---

## Phase 8: Cincinnati Children's IT Requirements (Week 21-22)

### 8.1 SSO Integration
- [ ] Integrate with Cincinnati Children's SSO (SAML/LDAP)
- [ ] Test with hospital credentials
- [ ] Configure group-based role mapping
- [ ] Set up MFA if required

### 8.2 Security Hardening
- [ ] Vulnerability scan (Nessus, OpenVAS)
- [ ] Penetration testing
- [ ] HIPAA compliance review
- [ ] Security audit documentation
- [ ] Incident response plan

### 8.3 Network & Firewall Configuration
- [ ] Deploy within hospital network
- [ ] Configure firewall rules
- [ ] Set up VPN access if needed
- [ ] Network segmentation (DMZ if public-facing)

### 8.4 Compliance Documentation
- [ ] Security architecture diagram
- [ ] Data flow diagrams
- [ ] Risk assessment (HIPAA Security Rule)
- [ ] Business associate agreements (BAA) if using cloud
- [ ] Disaster recovery plan

---

## Phase 9: Cutover & Decommission Flask (Week 23)

### 9.1 Final Data Migration
- [ ] Freeze Flask app (read-only mode)
- [ ] Final data sync to Django/PostgreSQL
- [ ] Verify all data migrated
- [ ] Update Nginx to route 100% traffic to Django

### 9.2 Decommission Flask
- [ ] Archive Flask codebase
- [ ] Remove Flask app from servers
- [ ] Clean up old databases
- [ ] Update documentation

### 9.3 Post-Launch Monitoring
- [ ] Monitor for 2 weeks
- [ ] Address any issues
- [ ] Gather user feedback
- [ ] Performance tuning

---

## Rollback Strategy

At each phase:
1. Keep Flask app running
2. Route traffic via Nginx based on URL path
3. If Django module has issues, route back to Flask
4. Fix Django module, re-deploy, re-route

**Nginx routing example:**
```nginx
location /dosing-verification/ {
    proxy_pass http://django:8000;  # Route to Django
}

location / {
    proxy_pass http://flask:8082;   # Everything else to Flask
}
```

---

## Risk Mitigation

**Highest Risks:**
1. **Data loss during migration** → Automated backups, checksums, dry runs
2. **Breaking ABX approvals workflow** → Migrate last, extensive testing
3. **SSO integration issues** → Early integration testing with IT
4. **Performance degradation** → Load testing, query optimization
5. **Security vulnerabilities** → Automated scanning, security review

---

## Success Metrics

- [ ] Zero downtime during migration
- [ ] 100% data integrity (no lost records)
- [ ] SSO working for all users
- [ ] All audit logs captured
- [ ] Performance ≥ Flask (page load < 2s)
- [ ] Zero security vulnerabilities (critical/high)
- [ ] Cincinnati Children's IT approval

---

## Timeline Summary

| Phase | Duration | Milestone |
|-------|----------|-----------|
| 1. Infrastructure Setup | Week 1-2 | Django running, auth working |
| 2. Core Models | Week 3-4 | All shared models in Django |
| 3. Module Migration | Week 5-14 | All 10 modules migrated |
| 4. Background Tasks | Week 15 | Celery running |
| 5. API Consolidation | Week 16 | Unified API |
| 6. Testing | Week 17-18 | All tests passing |
| 7. Deployment | Week 19-20 | Containerized, deployed |
| 8. IT Requirements | Week 21-22 | SSO, security audit |
| 9. Cutover | Week 23 | Flask decommissioned |

**Total:** ~6 months for complete migration

---

## Team Structure Recommendation

**Team Lead/Architect** - Overall coordination, Django architecture
**Backend Developer 1** - Core models, authentication, database
**Backend Developer 2** - Module migration, business logic
**Frontend Developer** - Template conversion, UI/UX
**DevOps Engineer** - Docker, CI/CD, deployment
**Security Engineer** - SSO, audit logging, compliance (can be consultant)
**QA Engineer** - Testing, validation (can be part-time)

Or leverage **AI agents** for different components (see next section).

---

## Using AI Agent Team for Migration

Create specialized agents for:
1. **Django Architect** - Sets up project structure, models
2. **Migration Specialist** - Converts Flask routes to Django views
3. **Security Specialist** - Implements auth, audit, encryption
4. **Testing Specialist** - Writes tests, validates functionality
5. **DevOps Specialist** - Handles Docker, deployment

This can accelerate the timeline significantly.
