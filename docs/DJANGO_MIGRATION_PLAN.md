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

## Phase 4: Background Tasks & Scheduling

**Goal:** Replace cron jobs and `--continuous` management commands with a proper task queue for reliability, monitoring, and scalability.

### 4.1 Set Up Celery + Redis

- [ ] Install Celery 5.x + Redis (broker + result backend)
- [ ] Add `aegis_project/celery.py` with autodiscover
- [ ] Add `CELERY_*` settings to `settings/base.py` (broker URL, result backend, serializer, timezone)
- [ ] Create `tasks.py` in each module that has a `--continuous` management command

### 4.2 Convert Management Commands to Celery Tasks

Each module's `--continuous` polling loop becomes a periodic Celery task:

| Module | Current Command | Celery Task | Schedule |
|--------|----------------|-------------|----------|
| HAI Detection | `monitor_hai --continuous` | `hai_detection.tasks.scan_for_candidates` | Every 15 min |
| HAI Detection | `monitor_hai --classify` | `hai_detection.tasks.classify_pending` | Every 30 min |
| Drug-Bug Mismatch | `monitor_drug_bug --continuous` | `drug_bug.tasks.check_mismatches` | Every 15 min |
| Dosing Verification | `monitor_dosing --continuous` | `dosing.tasks.evaluate_active_orders` | Every 15 min |
| Antimicrobial Usage | `monitor_usage --continuous` | `antimicrobial_usage.tasks.check_durations` | Every 30 min |
| ABX Indications | `monitor_indications --continuous` | `abx_indications.tasks.check_new_orders` | Every 15 min |
| ABX Indications | `monitor_indications --auto-accept` | `abx_indications.tasks.auto_accept_old` | Daily 6 AM |
| Surgical Prophylaxis | `monitor_prophylaxis --continuous` | `surgical_prophylaxis.tasks.evaluate_cases` | Every 15 min |
| Guideline Adherence | `monitor_guidelines --all` | `guideline_adherence.tasks.run_all_monitors` | Every 15 min |
| Outbreak Detection | `detect_outbreaks --continuous` | `outbreak_detection.tasks.detect_clusters` | Every 60 min |
| NHSN Reporting | `nhsn_extract --all` | `nhsn_reporting.tasks.monthly_extract` | 1st of month |
| Metrics | (manual) | `metrics.tasks.aggregate_daily_snapshot` | Daily midnight |
| Alerts | (manual) | `alerts.tasks.auto_resolve_stale` | Daily 6 AM |

### 4.3 Celery Beat Configuration

- [ ] Use `django-celery-beat` for database-backed schedule (admin-editable)
- [ ] Configure schedule in Django admin (not hardcoded)
- [ ] Add `PeriodicTask` entries for all tasks above
- [ ] Configure retry policy: max 3 retries with exponential backoff
- [ ] Configure task routing: `default` queue for most, `llm` queue for HAI/ABX/Guideline tasks (GPU-bound)
- [ ] Dead letter queue for tasks that exceed retry limit → create Alert with type `SYSTEM_ERROR`

### 4.4 HL7 ADT Listener (Surgical Prophylaxis)

- [ ] Keep `run_realtime_prophylaxis` as a systemd service (not Celery — it's a long-running TCP server)
- [ ] Add health check endpoint that Celery Beat pings every 5 min
- [ ] Auto-restart via systemd `Restart=always`
- [ ] Create `surgical_prophylaxis.tasks.check_hl7_listener_health` periodic task

### 4.5 Monitoring & Alerting

- [ ] Flower dashboard for Celery monitoring (or django-celery-results admin)
- [ ] Alert if task queue depth > 100 (backlog warning)
- [ ] Alert if task failure rate > 10% in any 1-hour window
- [ ] Log all task executions with duration, result, and error details

---

## Phase 5: Unified API & Integration

**Goal:** Consolidate 12 module APIs into a versioned, documented REST API. Enable Epic FHIR integration and future mobile/third-party access.

### 5.1 API Consolidation

Current state: Each module has its own `/api/` endpoints (e.g., `/hai-detection/api/stats/`, `/dosing/api/stats/`). These work but are inconsistent in naming, response format, and error handling.

- [ ] Create `apps/api/` app with versioned URL namespace: `/api/v1/`
- [ ] DRF DefaultRouter with ViewSets for each module:
  ```
  /api/v1/alerts/              — AlertViewSet (list, retrieve, acknowledge, resolve)
  /api/v1/hai/candidates/      — HAICandidateViewSet (list, retrieve, review)
  /api/v1/hai/classifications/  — HAIClassificationViewSet (list)
  /api/v1/dosing/assessments/  — DosingAssessmentViewSet (list, retrieve)
  /api/v1/drug-bug/mismatches/ — MismatchViewSet (list, retrieve)
  /api/v1/indications/         — IndicationViewSet (list, retrieve, review)
  /api/v1/prophylaxis/cases/   — SurgicalCaseViewSet (list, retrieve)
  /api/v1/guidelines/episodes/ — BundleEpisodeViewSet (list, retrieve, review)
  /api/v1/outbreaks/clusters/  — OutbreakClusterViewSet (list, retrieve)
  /api/v1/nhsn/events/         — NHSNEventViewSet (list, retrieve, submit)
  /api/v1/nhsn/au/             — AUViewSet (list, export)
  /api/v1/nhsn/ar/             — ARViewSet (list, export)
  /api/v1/usage/               — UsageAlertViewSet (list, retrieve)
  /api/v1/metrics/             — MetricsViewSet (overview, by-module)
  ```
- [ ] Consistent response envelope: `{"status": "ok", "data": {...}, "count": N}`
- [ ] Consistent error format: `{"status": "error", "code": "NOT_FOUND", "message": "..."}`
- [ ] Pagination: `LimitOffsetPagination` (default 50, max 200)
- [ ] Filtering: `django-filter` for date ranges, status, severity, module-specific fields

### 5.2 Serializers

- [ ] Create DRF serializers for all 40+ models across 12 modules
- [ ] Nested serializers for related objects (e.g., `AlertSerializer` includes `audit_log`)
- [ ] Read-only serializers for list views (performance)
- [ ] Write serializers for review/action endpoints
- [ ] Validate PHI fields are excluded from public-facing responses

### 5.3 API Authentication & Security

- [ ] Session auth (existing — for browser-based access)
- [ ] Token auth via DRF `TokenAuthentication` (for scripts, Celery, internal services)
- [ ] Rate limiting: `django-ratelimit` or DRF throttling
  - Anonymous: 0 (no anonymous access)
  - Authenticated: 100/min for reads, 30/min for writes
  - Admin: 500/min
- [ ] API key management for future third-party integrations (Epic CDS Hooks)
- [ ] CORS configuration for future frontend separation

### 5.4 API Documentation

- [ ] drf-spectacular (already installed) → generate OpenAPI 3.0 schema
- [ ] Swagger UI at `/api/docs/`
- [ ] ReDoc at `/api/redoc/`
- [ ] Export schema for Epic integration team review

### 5.5 Epic FHIR Integration Layer

- [ ] Create `apps/integrations/epic/` for shared Epic FHIR client
- [ ] Centralize OAuth2 client credentials flow (currently duplicated across 6 modules)
- [ ] FHIR Subscription support for real-time notifications (R4 topic-based)
- [ ] SMART on FHIR launch context for future EHR-embedded views
- [ ] Epic CDS Hooks endpoint (`/api/v1/cds-hooks/`) for medication-order-select, order-sign

---

## Phase 6: Testing & Quality Assurance

**Goal:** Comprehensive test coverage, integration testing, and clinical validation before production deployment.

### 6.1 Current Test Coverage

Tests already written per module:

| Module | Tests | Status |
|--------|-------|--------|
| Drug-Bug Mismatch | 7 | Passing |
| Antimicrobial Usage | 7 | Passing |
| ABX Indications | 64 | Passing |
| Surgical Prophylaxis | 66 | Passing |
| Guideline Adherence | 70 | Passing |
| NHSN Reporting | 104 | Passing |
| **Total** | **318** | **All passing** |

### 6.2 Fill Test Gaps

- [ ] Foundation tests: `apps/core/` models (TimeStampedModel, UUIDModel, SoftDeletableModel)
- [ ] Authentication tests: User model, roles, decorators, session management, SAML/LDAP backends
- [ ] Alert model tests: CRUD, status transitions, audit log creation, JSONField queries
- [ ] Metrics tests: ProviderActivity, DailySnapshot aggregation
- [ ] Notification tests: NotificationLog creation, multi-channel dispatch
- [ ] Action Analytics tests: ActionAnalyzer methods, API endpoints
- [ ] ASP Alerts tests: coverage rules, alert type filtering, demo data
- [ ] MDRO tests: case management, detection logic
- [ ] HAI Detection tests: candidate detection, LLM mocking, classification pipeline
- [ ] Outbreak Detection tests: cluster algorithm, ORM data sources
- [ ] Dosing tests: each of 9 rule modules individually, rules engine orchestration
- [ ] **Target: 800+ tests total, >90% line coverage on business logic**

### 6.3 Integration Tests

- [ ] End-to-end FHIR polling → alert creation → IP review → resolution for each module
- [ ] Cross-module: HAI Detection → NHSN Event creation → CDA generation → DIRECT submission
- [ ] Cross-module: MDRO case creation → Outbreak Detection cluster formation
- [ ] Celery task execution (use `CELERY_ALWAYS_EAGER=True` for tests)
- [ ] Template rendering with realistic context data (all 50+ templates)

### 6.4 LLM Validation (Clinical Accuracy)

Uses existing validation framework (`validation/validation_runner.py`):

- [ ] Collect 25 gold standard CLABSI cases from CCHMC records
- [ ] Collect 30 indication extraction cases from CCHMC pharmacy reviews
- [ ] Run validation against gold standards, measure precision/recall/F1
- [ ] Tune LLM prompts based on validation results
- [ ] Target: >90% sensitivity, >85% specificity for HAI classification
- [ ] Target: >85% accuracy for indication extraction

### 6.5 Security Testing

- [ ] OWASP ZAP scan against all endpoints
- [ ] SQL injection testing (ORM should prevent, but verify raw queries in Clarity extractors)
- [ ] XSS testing on all template input fields
- [ ] CSRF verification on all POST endpoints
- [ ] Authentication bypass testing (decorator coverage audit)
- [ ] PHI exposure audit (ensure no PHI in logs, error messages, API responses without auth)

### 6.6 Performance Testing

- [ ] Load test with realistic data volumes:
  - 500 active patients, 2,000 active medication orders
  - 50 concurrent users (10 pharmacists, 5 IPs, 30 physicians, 5 admins)
  - 12 modules polling simultaneously
- [ ] Database query optimization (identify N+1 queries, add `select_related`/`prefetch_related`)
- [ ] Page load targets: dashboard < 2s, detail views < 1s, API < 500ms
- [ ] LLM latency targets: HAI classification < 30s, indication extraction < 15s

### 6.7 User Acceptance Testing

- [ ] ASP Pharmacists: full approval workflow (new order → review → decision → re-approval chain)
- [ ] Infection Preventionists: HAI candidate review, outbreak dashboard, NHSN submission
- [ ] Physicians: read-only dashboard access, alert visibility
- [ ] Admin: user management, role assignment, system configuration
- [ ] Create UAT checklist document with pass/fail criteria per role

---

## Phase 7: Deployment & Infrastructure

**Goal:** Production-grade containerized deployment with PostgreSQL, monitoring, and CI/CD.

### 7.1 PostgreSQL Migration

- [ ] Install PostgreSQL 16 on production server (or use CCHMC-provided instance)
- [ ] Configure `settings/production.py` with PostgreSQL connection (DATABASE_URL via python-decouple)
- [ ] Run `python manage.py migrate` against PostgreSQL
- [ ] Import existing SQLite data: `python manage.py dumpdata | python manage.py loaddata` (or custom migration script)
- [ ] Verify data integrity: compare record counts, spot-check key records
- [ ] Configure connection pooling via `django-db-connection-pool` or pgBouncer
- [ ] Set up nightly backups (pg_dump) and WAL archiving for point-in-time recovery
- [ ] Enable SSL for database connections

### 7.2 Docker Containerization

Docker Compose services:

```yaml
services:
  web:          # Django + Gunicorn (4 workers)
  celery:       # Celery worker (default queue)
  celery-llm:   # Celery worker (llm queue, GPU-capable host)
  celery-beat:  # Celery Beat scheduler
  hl7-listener: # Surgical prophylaxis HL7 ADT TCP listener
  redis:        # Celery broker + cache
  postgres:     # PostgreSQL 16
  nginx:        # Reverse proxy + static files + TLS termination
  ollama:       # LLM server (llama3.3:70b, qwen2.5:7b)
```

- [ ] Write `Dockerfile` (Python 3.11-slim, multi-stage build, non-root user)
- [ ] Write `docker-compose.yml` with all services above
- [ ] Write `docker-compose.prod.yml` override (production secrets, volumes, restart policies)
- [ ] Configure health checks for all containers
- [ ] Static files: `collectstatic` in build, served by Nginx
- [ ] Media files: volume mount for any uploaded documents
- [ ] Environment variables: `.env` file (not committed), documented in `.env.example`

### 7.3 TLS & Reverse Proxy

- [ ] Nginx config: TLS 1.2+, HSTS, OCSP stapling
- [ ] Let's Encrypt certificate for `aegis-asp.com` (or CCHMC-provided cert)
- [ ] Proxy headers: `X-Forwarded-For`, `X-Forwarded-Proto` for Django `SECURE_PROXY_SSL_HEADER`
- [ ] Rate limiting at Nginx level (backup to application-level)
- [ ] Static file caching headers (1 year for hashed assets)

### 7.4 CI/CD Pipeline

GitHub Actions workflows:

- [ ] **`test.yml`** — On PR: run `python manage.py test` against SQLite, lint with ruff, type-check with mypy
- [ ] **`deploy-staging.yml`** — On merge to `develop`: build Docker image, push to registry, deploy to staging
- [ ] **`deploy-prod.yml`** — On merge to `main`: build, push, deploy with manual approval gate
- [ ] Container registry: GitHub Container Registry (ghcr.io) or CCHMC-provided registry
- [ ] Deployment target: `docker compose pull && docker compose up -d` via SSH or Watchtower

### 7.5 Monitoring & Observability

- [ ] **Error tracking:** Sentry (self-hosted or cloud) — capture unhandled exceptions, slow queries
- [ ] **Application logging:** Structured JSON logs → syslog or ELK stack
  - Audit logs: separate file, 500MB x 50 rotations (HIPAA requirement — already configured)
  - Application logs: stdout for Docker, captured by logging driver
- [ ] **Health checks:** `/health/` endpoint (database, Redis, Celery, Ollama connectivity)
- [ ] **Uptime monitoring:** UptimeRobot or Healthchecks.io for `/health/` endpoint
- [ ] **Metrics:** Prometheus + Grafana (optional) — request latency, task queue depth, error rate
- [ ] **Alerting:** PagerDuty or email for critical failures (database down, task queue stalled, LLM unavailable)

---

## Phase 8: CCHMC IT Integration

**Goal:** Meet Cincinnati Children's Hospital IT security requirements for production deployment on hospital infrastructure.

### 8.1 SSO Integration

AEGIS already has SAML and LDAP backends written (`apps/authentication/backends.py`). This phase connects them to CCHMC's actual identity provider.

- [ ] Submit Epic FHIR API access request to CCHMC IS (already drafted in `docs/integration-requirements.md`)
- [ ] Obtain SAML metadata from CCHMC Identity Provider (likely ADFS or Azure AD)
- [ ] Configure `python3-saml` with CCHMC-specific:
  - Entity ID, SSO URL, SLO URL
  - X.509 certificate for signature validation
  - Attribute mapping: `sAMAccountName` → username, `mail` → email, `memberOf` → roles
- [ ] Role mapping from AD groups:
  - `CCHMC-ASP-Pharmacists` → `asp_pharmacist`
  - `CCHMC-Infection-Prevention` → `infection_preventionist`
  - `CCHMC-Physicians-ID` → `physician`
  - `CCHMC-AEGIS-Admins` → `admin`
- [ ] Test SSO flow: login → attribute mapping → role assignment → session creation
- [ ] LDAP fallback configuration: `ldaps://ldap.cchmc.org:636` with service account
- [ ] MFA: CCHMC likely handles MFA at the IdP level (Duo); verify no AEGIS-side changes needed

### 8.2 Network & Firewall

- [ ] Deploy on CCHMC internal network (not public internet for production)
- [ ] Firewall rules:
  - Inbound: HTTPS (443) from CCHMC network only
  - Outbound: FHIR server (Epic), Clarity DB, NHSN DIRECT (port 587), Ollama LLM server
  - Inbound: HL7 ADT (port 2575) from Epic Interface Engine
- [ ] DNS: `aegis.cchmc.org` (internal) — coordinate with CCHMC networking
- [ ] SSL certificate: CCHMC-issued certificate (not Let's Encrypt for internal)
- [ ] VPN access for remote administration (if allowed by CCHMC policy)

### 8.3 Epic Integration Requirements

From `docs/integration-requirements.md`:

- [ ] Epic FHIR R4 API access (read-only for: Patient, Observation, MedicationRequest, MedicationAdministration, Condition, Procedure, DocumentReference, Encounter, Appointment)
- [ ] Epic client credentials (non-user OAuth2 — backend service)
- [ ] Clarity read-only access (reporting database — for NHSN denominators, AU/AR extraction)
- [ ] HL7 ADT feed from Epic Interface Engine (TCP/MLLP on port 2575)
- [ ] NHSN DIRECT address registration with CDC (HISP setup)

### 8.4 Security Hardening

- [ ] Vulnerability scan: CCHMC likely uses Qualys or Nessus — schedule scan
- [ ] Penetration test: coordinate with CCHMC InfoSec team (or approved vendor)
- [ ] Code review: remove all `DEBUG=True` paths, verify `ALLOWED_HOSTS`, verify `SECRET_KEY` is production-grade
- [ ] CSP: replace `unsafe-inline` with nonce-based CSP (TODO from Phase 1)
- [ ] Database encryption at rest (PostgreSQL TDE or filesystem-level)
- [ ] PHI handling audit: verify all PHI access is logged, no PHI in error logs or Sentry

### 8.5 HIPAA Compliance Documentation

CCHMC IT will require these documents before production approval:

- [ ] **Security Architecture Diagram** — network topology, data flows, encryption points
- [ ] **Data Flow Diagram** — PHI data lifecycle: FHIR → AEGIS → review → NHSN
- [ ] **Risk Assessment** (HIPAA Security Rule §164.308(a)(1)) — threats, vulnerabilities, mitigations
- [ ] **Access Control Policy** — role definitions, minimum necessary access, session management
- [ ] **Audit Control Policy** — what's logged, retention period (7 years for HIPAA), review process
- [ ] **Disaster Recovery Plan** — RTO/RPO targets, backup procedures, failover
- [ ] **Incident Response Plan** — PHI breach notification procedures, containment steps
- [ ] **Business Associate Agreements** — if using any cloud services (Sentry, monitoring)

### 8.6 Training & Documentation

- [ ] User guide for ASP pharmacists (approval workflow, alert management)
- [ ] User guide for Infection Preventionists (HAI review, NHSN submission, outbreak monitoring)
- [ ] Admin guide (user management, system configuration, troubleshooting)
- [ ] Clinical decision support documentation (what each alert type means, expected actions)
- [ ] On-call runbook (common issues, restart procedures, escalation contacts)

---

## Phase 9: Cutover & Flask Decommission

**Goal:** Complete transition from Flask to Django with zero data loss and minimal disruption.

### 9.1 Pre-Cutover Checklist

- [ ] All Phase 4-8 items complete
- [ ] All tests passing (800+ target)
- [ ] CCHMC IT security approval obtained
- [ ] SSO tested with real CCHMC credentials
- [ ] Epic FHIR integration tested with production endpoints (read-only)
- [ ] LLM validation results acceptable (>90% sensitivity for HAI)
- [ ] User acceptance testing signed off by all 4 roles
- [ ] Monitoring and alerting verified functional
- [ ] Disaster recovery tested (backup restore, failover)
- [ ] Communication plan: notify all users of cutover date and expected downtime

### 9.2 Cutover Execution

1. **T-1 week:** Final round of testing on staging with production-like data
2. **T-1 day:** Notify all users of planned maintenance window
3. **T-0 (maintenance window, e.g., Saturday 2 AM):**
   - Set Flask app to read-only mode
   - Final data export from Flask SQLite databases
   - Import into Django PostgreSQL (verify counts match)
   - Update DNS / Nginx to route all traffic to Django
   - Verify SSO login works
   - Verify all 12 module dashboards load correctly
   - Verify Celery tasks are running (check Flower)
   - Verify HL7 ADT listener is receiving messages
4. **T+1 hour:** Send "cutover complete" notification to users
5. **T+1 day:** Monitor for issues, check error rates in Sentry

### 9.3 Rollback Plan

If critical issues are found within the first 48 hours:

1. Revert DNS / Nginx to Flask
2. Flask app is still running (read-only) — switch back to read-write
3. Any data entered in Django during the window needs manual reconciliation
4. Fix the issue in Django, re-test, schedule new cutover window

### 9.4 Post-Cutover

- [ ] Monitor for 2 weeks (daily error review, weekly performance review)
- [ ] Collect user feedback (survey or informal check-ins)
- [ ] Performance tuning based on real production load
- [ ] Archive Flask codebase (tag `flask-final`, keep repository intact)
- [ ] Remove Flask from server (after 30-day grace period)
- [ ] Clean up old SQLite databases (after verifying all data migrated)
- [ ] Update all documentation to reflect Django-only architecture
- [ ] Close out migration tracking issues in GitHub Project Tracker

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

| Phase | Status | Milestone |
|-------|--------|-----------|
| 1. Infrastructure Setup | ✅ COMPLETE | Django running, auth working, audit logging |
| 2. Core Models | ✅ COMPLETE | All shared models, DRF configured |
| 3. Module Migration | ✅ COMPLETE | All 12 modules migrated (318 tests passing) |
| 4. Background Tasks | TODO | Celery + Redis, 13 periodic tasks, HL7 listener service |
| 5. Unified API | TODO | `/api/v1/` consolidation, Epic FHIR integration layer |
| 6. Testing & QA | TODO | 800+ tests, LLM validation, security scan, UAT |
| 7. Deployment | TODO | PostgreSQL, Docker Compose, CI/CD, monitoring |
| 8. CCHMC IT | TODO | SSO, Epic access, security audit, HIPAA docs |
| 9. Cutover | TODO | Data migration, DNS switch, Flask decommission |

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
