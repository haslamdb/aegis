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

## Phase 1: Infrastructure & Core Setup ✅ COMPLETE

### 1.1 Django Project Setup ✅
- [x] Create new `aegis-django/` directory alongside existing Flask app
- [x] Initialize Django project: `django-admin startproject aegis_project`
- [x] Configure settings for development/staging/production
- [x] Set up SQLite database (development); PostgreSQL planned for production
- [x] Configure environment variables (python-decouple)
- [x] Set up Django admin interface

### 1.2 Authentication & Authorization ✅
- [x] SAML SSO backend (`SAMLAuthBackend`)
- [x] LDAP fallback backend (`LDAPAuthBackend`)
- [x] Custom User model extending AbstractUser with 4-role RBAC
- [x] Roles defined: asp_pharmacist, infection_preventionist, physician, admin
- [x] Permission decorators: `physician_or_higher_required`, `role_required`, etc.
- [x] Session management (15-min HIPAA timeout, secure cookies)
- [x] Login/logout views and templates wired at `/auth/login/`, `/auth/logout/`

### 1.3 Security Configuration ✅
- [x] HTTPS enforcement configured (production settings)
- [x] CSRF protection enabled (default)
- [x] Secure cookie settings configured
- [x] CSP headers (note: still uses `unsafe-inline`, TODO: nonce-based)
- [x] X-Frame-Options DENY, X-Content-Type-Options nosniff
- [x] SQL injection protection via ORM
- [ ] Rate limiting for API endpoints (deferred to Phase 5)

### 1.4 Audit Logging ✅
- [x] Custom AuditMiddleware logs all authenticated requests
- [x] Authentication events logged (login, logout, failed attempts)
- [x] Data modification logging functions available
- [x] AlertAudit model for alert action tracking
- [x] Log retention configured (500 MB x 50 files for HIPAA)
- [ ] SIEM export (deferred to Phase 8)

### 1.5 Database Setup (partial)
- [x] SQLite for development
- [ ] PostgreSQL for production (deferred to Phase 7)
- [ ] Connection pooling, encryption at rest, backups, replication

### 1.6 Code Audit ✅ (2026-02-07)
- [x] Full audit of foundation code — 10 bugs found and fixed
- [x] Security: missing auth decorators on API endpoints
- [x] Bugs: timezone-naive datetime, unsafe int parsing, thread-local leak
- [x] HIPAA: SoftDeletableModel.delete() now tracks deleted_by
- [x] Foundation certified solid for building additional modules

---

## Phase 2: Core Shared Components ✅ COMPLETE

### 2.1 Convert Common Models ✅
1. **User & Authentication Models** ✅ — Custom User with RBAC, UserSession, Permission, RolePermission
2. **Alert Store** ✅ — Unified Alert model with AlertType (25+ types), AlertStatus, AlertSeverity, AlertAudit
3. **Metrics Store** ✅ — ProviderActivity, DailySnapshot
4. **Notifications** ✅ — NotificationLog with multi-channel support (email, Teams, SMS)
5. **Core Base Models** ✅ — TimeStampedModel, UUIDModel, SoftDeletableModel, PatientRelatedModel

### 2.2 Django Apps Structure ✅
Apps created: `core`, `authentication`, `alerts`, `metrics`, `notifications`, `action_analytics`, `asp_alerts`

### 2.3 Django REST Framework ✅
- [x] DRF installed and configured (SessionAuth + TokenAuth)
- [x] API permissions configured (IsAuthenticated default)
- [x] drf-spectacular configured for API docs
- [ ] Serializers and ViewSets (will be created per-module as needed)

---

## Phase 3: Migrate Modules (Week 5-12)

**Strategy:** Migrate one module at a time, running both Flask and Django simultaneously using Nginx routing.

### Migration Order (Lowest Risk → Highest Risk):

#### 3.1 Action Analytics ✅ COMPLETE (audited & fixed)
- [x] Created Django app: `apps/action_analytics/`
- [x] ActionAnalyzer class with 6 analytics methods
- [x] 4 dashboard views + 4 JSON API endpoints
- [x] 4 HTML templates
- [x] Audited: fixed timezone, auth, deprecated ORM, input validation

#### 3.1b ASP Alerts ✅ COMPLETE
- [x] Created Django app: `apps/asp_alerts/`
- [x] 7 ASP alert types, coverage rules ported from Flask
- [x] Views: active alerts, detail, history, reports, 4 API actions
- [x] Templates: stats cards, susceptibility panels, two-column detail layout
- [x] Demo data command with 8 clinical scenarios
- [x] Full audit logging on all alert actions

#### 3.2 Dosing Verification ✅ COMPLETE
- [x] Created Django app: `apps/dosing/`
- [x] 9 clinical rule modules ported (allergy, age, renal, weight, route, indication, interaction, duration, extended infusion)
- [x] DosingRulesEngine orchestrator
- [x] FHIR client adapted for Django settings
- [x] Views: dashboard, detail, history, reports, help + 4 API endpoints
- [x] Templates: 6 files with blue theme
- [x] Management commands: create_demo_dosing, monitor_dosing
- [x] Route `/dosing/` to Django

#### 3.3 MDRO Surveillance ✅ COMPLETE
- [x] Created Django app: `apps/mdro/`
- [x] MDRO detection and case management
- [x] Dashboard views and templates
- [x] Route `/mdro-surveillance/` to Django

#### 3.4 Drug-Bug Mismatch ✅ COMPLETE
- [x] Created Django app: `apps/drug_bug/`
- [x] Business logic ported: matcher, antibiotic_map, data_models
- [x] FHIR client adapted for Django settings
- [x] Views: dashboard, history, help + API endpoints
- [x] Management commands: create_demo_mismatches, monitor_drug_bug
- [x] Route `/drug-bug/` to Django

#### 3.5 Guideline Adherence ✅ COMPLETE
- [x] Created Django app: `apps/guideline_adherence/`
- [x] 5 custom models: BundleEpisode, ElementResult, EpisodeAssessment, EpisodeReview, MonitorState
- [x] 9 guideline bundles (sepsis, CAP, febrile infant, HSV, C.diff, febrile neutropenia, surgical prophylaxis, UTI, SSTI)
- [x] 3 monitoring modes: trigger, episode, adherence
- [x] 7 element checkers + tiered NLP (7B + 70B LLM)
- [x] 70 tests passing
- [x] Route `/guideline-adherence/` to Django

#### 3.6 Surgical Prophylaxis ✅ COMPLETE
- [x] Created Django app: `apps/surgical_prophylaxis/`
- [x] 9 custom models: SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication, ComplianceMetric, SurgicalJourney, PatientLocation, PreOpCheck, AlertEscalation
- [x] 7-element ASHP bundle evaluation + real-time HL7 ADT monitoring
- [x] 66 tests passing
- [x] Route `/surgical-prophylaxis/` to Django

#### 3.7 HAI Detection ✅ COMPLETE
- [x] Created Django app: `apps/hai_detection/` (76 Python files)
- [x] 4 custom Django models: HAICandidate, HAIClassification, HAIReview, LLMAuditLog
- [x] 61 business logic files copied to `logic/` with import path fixes:
  - 5 candidate detectors (CLABSI, SSI, VAE, CAUTI, CDI)
  - 5 classifiers + schemas (LLM extraction + rules architecture)
  - 5 NHSN rules engines + schemas
  - 6 LLM extractors + triage extractor + training collector
  - Note retriever, chunker, deduplicator
  - LLM backends (Ollama, vLLM) + factory
  - Data sources (FHIR, Clarity, mock) + factory
- [x] 6 prompt templates for LLM extraction
- [x] Services layer: HAIDetectionService (Django ORM adapter for monitor.py)
- [x] Views: dashboard, candidate detail, history, reports, help + 5 API endpoints
- [x] 6 templates with red/maroon IP theme
- [x] Management commands: monitor_hai (detection pipeline), create_demo_hai (20+ scenarios)
- [x] HAI_DETECTION settings dict in base.py
- [x] Route `/hai-detection/` to Django

#### 3.8 Antimicrobial Usage Alerts ✅ COMPLETE
- [x] Created Django app: `apps/antimicrobial_usage/`
- [x] No custom models — uses Alert model with BROAD_SPECTRUM_USAGE type
- [x] BroadSpectrumMonitorService with FHIR client, dedup via JSONField
- [x] 7 tests passing
- [x] Route `/antimicrobial-usage/` to Django

#### 3.9 ABX Indications ✅ COMPLETE
- [x] Created Django app: `apps/abx_indications/`
- [x] 3 custom models: IndicationCandidate, IndicationReview, IndicationLLMAuditLog
- [x] LLM extraction via Ollama, CCHMC guidelines engine (57 diseases)
- [x] 64 tests passing
- [x] Route `/abx-indications/` to Django

#### 3.10 Outbreak Detection ✅ COMPLETE
- [x] Created Django app: `apps/outbreak_detection/`
- [x] 2 custom models: OutbreakCluster, ClusterCase
- [x] ORM data sources replacing SQLite queries
- [x] Route `/outbreak-detection/` to Django

#### 3.11 NHSN Reporting ✅ COMPLETE
- [x] Created Django app: `apps/nhsn_reporting/`
- [x] 11 custom models: NHSNEvent, DenominatorDaily, DenominatorMonthly, AUMonthlySummary, AUAntimicrobialUsage, AUPatientLevel, ARQuarterlySummary, ARIsolate, ARSusceptibility, ARPhenotypeSummary, SubmissionAudit
- [x] AU/AR data extraction from Clarity (DOT/DDD, isolates, phenotypes)
- [x] HL7 CDA R2 document generation for HAI event submission
- [x] DIRECT protocol client for NHSN submission via HISP
- [x] CSV export for all data types
- [x] 104 tests passing
- [x] Route `/nhsn-reporting/` to Django

**Phase 3 COMPLETE — All 12 modules migrated to Django.**

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
