# AEGIS Django Migration: Architectural Analysis & Recommendations

**Prepared by:** Django Architect Agent
**Date:** 2026-02-07
**Status:** Phase 1 - Architecture Design

---

## Executive Summary

After analyzing the existing Flask codebase and the Django migration plan, I provide the following architectural recommendations for migrating AEGIS to Django. This analysis covers:

1. **Django Project Structure** - Optimal app organization for 10+ modules
2. **App Organization Strategy** - Clear boundaries and shared components
3. **Model Design Strategy** - Converting dataclasses to Django ORM
4. **Migration Sequence Priorities** - Risk-based migration order

---

## 1. Current Flask Architecture Analysis

### 1.1 Overall Structure

The AEGIS Flask application uses a **modular monolith** pattern:

```
aegis/
├── dashboard/              # Flask app (main UI)
│   ├── app.py             # App factory with 13 blueprints
│   ├── routes/            # 14 route files (one per module)
│   ├── templates/         # Jinja2 templates
│   └── services/          # Business logic
├── common/                # Shared components
│   ├── alert_store/       # SQLite-based alert persistence
│   ├── metrics_store/     # Activity tracking and analytics
│   ├── abx_approvals/     # Approval workflow
│   ├── dosing_verification/ # Dosing alert store
│   ├── channels/          # Notifications (email, Teams, SMS)
│   └── llm_tracking/      # LLM usage tracking
└── [10+ module directories]/ # Domain-specific logic
    ├── hai-detection/
    ├── dosing-verification/
    ├── guideline-adherence/
    ├── drug-bug-mismatch/
    └── ...
```

### 1.2 Key Architectural Patterns Observed

1. **Blueprint-based routing** - Each module is a Flask blueprint
2. **Dataclass models** - Using Python dataclasses with manual SQLite persistence
3. **Shared stores** - `AlertStore`, `MetricsStore`, `DoseAlertStore` are SQLite databases
4. **No authentication** - Currently no user auth (planned for Django)
5. **Manual ORM** - Custom SQL queries with row-to-dataclass converters
6. **Mixed concerns** - Routes handle both UI and API endpoints

### 1.3 Module Inventory (13 Modules)

| Module | Route Prefix | Complexity | Database Dependencies |
|--------|-------------|------------|---------------------|
| HAI Detection | `/hai-detection` | **High** | AlertStore, MetricsStore, custom SQLite |
| ABX Approvals | `/abx-approvals` | **High** | ApprovalStore, MetricsStore |
| Dosing Verification | `/dosing-verification` | **Medium** | DoseAlertStore, MetricsStore |
| Guideline Adherence | `/guideline-adherence` | **Medium** | AlertStore, MetricsStore |
| Drug-Bug Mismatch | `/drug-bug-mismatch` | **Low** | AlertStore |
| MDRO Surveillance | `/mdro-surveillance` | **Low** | AlertStore |
| Surgical Prophylaxis | `/surgical-prophylaxis` | **Medium** | AlertStore |
| ABX Indications | `/abx-indications` | **Medium** | AlertStore, LLM tracking |
| NHSN Reporting | `/nhsn-reporting` | **Medium** | Custom SQLite |
| Outbreak Detection | `/outbreak-detection` | **Low** | AlertStore |
| Action Analytics | `/action-analytics` | **Low** | MetricsStore (read-only) |
| ASP Metrics | `/asp-metrics` | **Medium** | MetricsStore |
| ASP Alerts (legacy) | `/asp-alerts` | **Low** | AlertStore |

---

## 2. Django Project Structure Recommendation

### 2.1 Proposed Directory Structure

```
aegis_django/
├── manage.py
├── aegis_project/                 # Django project settings
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py               # Shared settings
│   │   ├── development.py        # Dev settings (SQLite, DEBUG=True)
│   │   ├── staging.py            # Staging settings
│   │   └── production.py         # Production settings (PostgreSQL, security)
│   ├── urls.py                   # Root URL configuration
│   ├── wsgi.py                   # WSGI entry point
│   └── asgi.py                   # ASGI for async (future websockets)
│
├── apps/                          # All Django apps
│   │
│   ├── core/                     # Shared core functionality
│   │   ├── models.py             # Base models (TimeStampedModel, etc.)
│   │   ├── managers.py           # Custom model managers
│   │   ├── mixins.py             # Model mixins
│   │   ├── utils.py              # Shared utilities
│   │   └── templatetags/         # Custom template tags
│   │
│   ├── authentication/           # SSO, user management, RBAC
│   │   ├── models.py             # User, Role, Permission
│   │   ├── backends.py           # LDAP/SAML auth backends
│   │   ├── middleware.py         # Session tracking, audit middleware
│   │   ├── views.py              # Login, logout, profile
│   │   └── decorators.py         # @role_required, @permission_required
│   │
│   ├── alerts/                   # Unified alert system
│   │   ├── models.py             # Alert, AlertAudit, AlertType enums
│   │   ├── managers.py           # AlertManager with query methods
│   │   ├── views.py              # Alert CRUD views
│   │   ├── serializers.py        # DRF serializers
│   │   └── tasks.py              # Celery tasks (auto-accept, cleanup)
│   │
│   ├── metrics/                  # Activity tracking & analytics
│   │   ├── models.py             # ProviderActivity, InterventionSession, etc.
│   │   ├── managers.py           # Analytics query methods
│   │   ├── views.py              # Metrics dashboards
│   │   ├── aggregator.py         # Daily snapshot generation
│   │   └── tasks.py              # Celery tasks (daily aggregation)
│   │
│   ├── notifications/            # Notification channels
│   │   ├── models.py             # NotificationLog, ReceiptTracker
│   │   ├── channels.py           # Email, Teams, SMS backends
│   │   ├── tasks.py              # Celery tasks (async notifications)
│   │   └── signals.py            # Alert signals → notifications
│   │
│   ├── llm_tracking/             # LLM usage tracking (HIPAA compliance)
│   │   ├── models.py             # LLMRequest, LLMExtraction
│   │   ├── views.py              # LLM audit dashboards
│   │   └── middleware.py         # Request/response logging
│   │
│   ├── hai_detection/            # HAI Detection module
│   │   ├── models.py             # CLABSICandidate, SSICandidate, etc.
│   │   ├── views.py              # Dashboard views
│   │   ├── api/                  # DRF API views
│   │   │   ├── views.py
│   │   │   └── serializers.py
│   │   ├── detectors/            # Detection logic (Python modules)
│   │   │   ├── clabsi.py
│   │   │   ├── ssi.py
│   │   │   └── ...
│   │   ├── templates/            # HAI-specific templates
│   │   └── tasks.py              # Celery tasks (hourly detection)
│   │
│   ├── dosing_verification/      # Antimicrobial dosing verification
│   │   ├── models.py             # DoseAlert, DoseFlag, DoseAssessment
│   │   ├── views.py              # Dashboard views
│   │   ├── api/
│   │   ├── rules_engine/         # Dosing rules (Python modules)
│   │   ├── fhir_client.py        # FHIR integration (keep as-is)
│   │   └── templates/
│   │
│   ├── abx_approvals/            # Antibiotic approvals workflow
│   │   ├── models.py             # ApprovalRequest, ApprovalAudit
│   │   ├── views.py
│   │   ├── api/
│   │   ├── recheck_scheduler.py  # Re-approval logic
│   │   ├── templates/
│   │   └── tasks.py              # Celery tasks (auto-recheck)
│   │
│   ├── guideline_adherence/      # Guideline bundle adherence
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── bundles/              # Bundle definitions (Python modules)
│   │   └── templates/
│   │
│   ├── drug_bug_mismatch/        # Culture-therapy mismatch
│   │   ├── models.py
│   │   ├── views.py
│   │   └── templates/
│   │
│   ├── mdro_surveillance/        # MDRO surveillance
│   │   ├── models.py
│   │   ├── views.py
│   │   └── templates/
│   │
│   ├── surgical_prophylaxis/     # Surgical prophylaxis compliance
│   │   ├── models.py
│   │   ├── views.py
│   │   └── templates/
│   │
│   ├── nhsn_reporting/           # NHSN AU/AR reporting
│   │   ├── models.py
│   │   ├── views.py
│   │   └── templates/
│   │
│   ├── outbreak_detection/       # Outbreak clustering
│   │   ├── models.py
│   │   ├── views.py
│   │   └── templates/
│   │
│   ├── action_analytics/         # ASP/IP action analytics
│   │   ├── views.py              # Read-only dashboards
│   │   └── templates/
│   │
│   └── api/                      # Unified REST API (DRF)
│       ├── urls.py               # API router
│       ├── views.py              # API root, documentation
│       ├── authentication.py     # API auth (token, OAuth2)
│       └── permissions.py        # API permission classes
│
├── templates/                     # Global templates
│   ├── base.html                 # Base template (header, nav, footer)
│   ├── partials/                 # Reusable components
│   └── errors/                   # Error pages (404, 500)
│
├── static/                        # Static files
│   ├── css/
│   ├── js/
│   └── img/
│
├── media/                         # User-uploaded files (if any)
│
├── requirements/
│   ├── base.txt                  # Core dependencies
│   ├── development.txt           # Dev dependencies
│   └── production.txt            # Production dependencies
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf                # Reverse proxy config
│
└── docs/
    ├── api/                       # API documentation
    └── deployment/                # Deployment guides
```

### 2.2 Rationale for Structure

**Why this structure?**

1. **Apps are domain-focused** - Each AEGIS module gets its own Django app
2. **Clear separation of concerns** - Core, auth, alerts, metrics are shared services
3. **Scalable** - Easy to add new modules without restructuring
4. **DRF-first API** - Dedicated `api/` app for REST endpoints
5. **Template inheritance** - Global templates + app-specific templates
6. **Environment-based settings** - Easy to deploy to dev/staging/prod
7. **Celery-ready** - `tasks.py` in each app for background jobs

---

## 3. App Organization Strategy

### 3.1 Shared Apps (Foundation)

These apps provide infrastructure for all modules:

#### `apps/core/`
- **Purpose:** Shared utilities, base models, mixins
- **Models:** `TimeStampedModel`, `SoftDeletableModel`
- **Managers:** `SoftDeleteManager`, `ActiveManager`
- **Utils:** Date helpers, formatters, validators

#### `apps/authentication/`
- **Purpose:** User authentication, SSO, RBAC
- **Models:**
  - `User` (extends `AbstractUser`)
  - `Role` (ASP Pharmacist, Infection Preventionist, Physician, Admin)
  - `Permission` (module-level permissions)
  - `UserSession` (audit trail)
- **Backends:** `LDAPAuthBackend`, `SAMLAuthBackend`
- **Middleware:** `AuditMiddleware` (logs all requests for HIPAA)

#### `apps/alerts/`
- **Purpose:** Unified alert storage (replaces `common/alert_store`)
- **Models:**
  - `Alert` (main alert model)
  - `AlertAudit` (audit log)
  - `AlertType` (enum → Django `TextChoices`)
  - `AlertStatus` (enum → Django `TextChoices`)
  - `ResolutionReason` (enum → Django `TextChoices`)
- **Managers:** Custom queryset for filtering (active, by type, by severity)
- **Signals:** Auto-create audit entries on save

#### `apps/metrics/`
- **Purpose:** Activity tracking (replaces `common/metrics_store`)
- **Models:**
  - `ProviderActivity`
  - `InterventionSession`
  - `InterventionTarget`
  - `InterventionOutcome`
  - `DailySnapshot` (aggregated metrics)
- **Tasks:** Daily snapshot generation (Celery cron job)

#### `apps/notifications/`
- **Purpose:** Notification channels (email, Teams, SMS)
- **Models:** `NotificationLog`, `ReceiptTracker`
- **Channels:** `EmailChannel`, `TeamsChannel`, `SMSChannel`
- **Signals:** Listen to `Alert.post_save` → send notifications

### 3.2 Module Apps (Domain Logic)

Each clinical module gets its own app:

**Pattern for module apps:**
```
apps/[module_name]/
├── models.py              # Domain models (extend alerts.Alert if needed)
├── views.py               # HTML dashboard views
├── api/
│   ├── views.py          # DRF ViewSets
│   ├── serializers.py    # DRF serializers
│   └── urls.py           # API routes
├── templates/
│   └── [module_name]/    # Module-specific templates
├── tasks.py              # Celery tasks (detection, notifications)
├── admin.py              # Django admin customization
├── urls.py               # URL routes
└── tests/
    ├── test_models.py
    ├── test_views.py
    └── test_api.py
```

### 3.3 Dependency Map

```
Core Dependencies:
core → (no dependencies)
authentication → core
alerts → core, authentication
metrics → core, authentication
notifications → core, alerts

Module Dependencies:
hai_detection → core, authentication, alerts, metrics, notifications
dosing_verification → core, authentication, alerts, metrics
abx_approvals → core, authentication, metrics, notifications
guideline_adherence → core, authentication, alerts, metrics
... (all other modules)
```

**Key principle:** Modules depend on shared apps, but **never on each other**. This prevents circular dependencies.

---

## 4. Model Design Strategy

### 4.1 Converting Dataclasses to Django Models

**Current pattern (Flask):**
```python
# common/alert_store/models.py
@dataclass
class StoredAlert:
    id: str
    alert_type: AlertType
    source_id: str
    status: AlertStatus
    # ... 20+ fields
    created_at: datetime = field(default_factory=datetime.now)
```

**Django pattern:**
```python
# apps/alerts/models.py
class Alert(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    alert_type = models.CharField(max_length=50, choices=AlertType.choices)
    source_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=AlertStatus.choices)

    # Patient info
    patient_id = models.CharField(max_length=255, null=True)
    patient_mrn = models.CharField(max_length=100, null=True, db_index=True)
    patient_name = models.CharField(max_length=255, null=True)

    # Alert content (JSON field for flexibility)
    title = models.CharField(max_length=500)
    summary = models.TextField()
    content = models.JSONField(default=dict)

    # Timestamps (inherited from TimeStampedModel)
    # created_at, updated_at

    # Status tracking
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(User, null=True, related_name='acknowledged_alerts', on_delete=models.SET_NULL)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, null=True, related_name='resolved_alerts', on_delete=models.SET_NULL)
    resolution_reason = models.CharField(max_length=50, choices=ResolutionReason.choices, null=True)

    # Snooze
    snoozed_until = models.DateTimeField(null=True, blank=True)

    # Notes
    notes = models.TextField(null=True, blank=True)

    objects = AlertManager()  # Custom manager

    class Meta:
        db_table = 'alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient_mrn', 'status']),
            models.Index(fields=['alert_type', 'status']),
            models.Index(fields=['created_at']),
        ]

    def is_snoozed(self):
        if self.status != AlertStatus.SNOOZED:
            return False
        if not self.snoozed_until:
            return False
        return timezone.now() < self.snoozed_until

    def is_actionable(self):
        if self.status == AlertStatus.RESOLVED:
            return False
        return not self.is_snoozed()

    def __str__(self):
        return f"{self.alert_type} - {self.patient_mrn}"
```

### 4.2 Enum Conversion Pattern

**Current (Flask):**
```python
class AlertType(Enum):
    BACTEREMIA = "bacteremia"
    BROAD_SPECTRUM_USAGE = "broad_spectrum_usage"
```

**Django pattern:**
```python
class AlertType(models.TextChoices):
    BACTEREMIA = "bacteremia", "Bacteremia"
    BROAD_SPECTRUM_USAGE = "broad_spectrum_usage", "Broad Spectrum Usage"
    DOSING_ALERT = "dosing_alert", "Dosing Alert"
    # ... all types
```

**Benefits:**
- Built-in database constraints
- Automatic validation
- Admin UI integration
- Human-readable labels

### 4.3 Foreign Key Strategy

**Replace string references with ForeignKeys:**

```python
# Old (Flask): acknowledged_by: str | None = None
# New (Django):
acknowledged_by = models.ForeignKey(
    User,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name='acknowledged_alerts'
)
```

**Benefits:**
- Database referential integrity
- Automatic joins
- `.select_related()` for performance
- Admin UI autocomplete

### 4.4 JSON Field Usage

Use `JSONField` for flexible, non-relational data:

```python
# Alert content (varies by type)
content = models.JSONField(default=dict)

# Clinical context (medications, cultures, etc.)
clinical_context = models.JSONField(default=dict)

# Metrics breakdowns
by_location = models.JSONField(default=dict)
by_service = models.JSONField(default=dict)
```

**When to use JSONField:**
- Variable structure (alert content differs by type)
- Aggregated data (metrics breakdowns)
- Non-queryable metadata

**When NOT to use JSONField:**
- Data you need to query/filter (use proper columns)
- Data with relationships (use ForeignKey)
- Large binary data (use FileField)

### 4.5 Audit Log Pattern

**Current (Flask):**
```python
@dataclass
class AlertAuditEntry:
    id: int
    alert_id: str
    action: AuditAction
    performed_by: str | None
    performed_at: datetime
    details: str | None = None
```

**Django pattern:**
```python
class AlertAudit(models.Model):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='audit_log')
    action = models.CharField(max_length=50, choices=AuditAction.choices)
    performed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    performed_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'alert_audit'
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['alert', 'performed_at']),
        ]
```

**Signal-based auto-logging:**
```python
# apps/alerts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Alert)
def create_audit_entry(sender, instance, created, **kwargs):
    action = AuditAction.CREATED if created else AuditAction.UPDATED
    AlertAudit.objects.create(
        alert=instance,
        action=action,
        performed_by=get_current_user(),  # from middleware
    )
```

---

## 5. Migration Sequence Priorities

### 5.1 Recommended Migration Order (Revised)

Based on **dependencies** and **risk**, I recommend this order:

#### **Phase 1: Foundation (Week 1-3)**
1. ✅ Django project setup
2. ✅ `apps/core/` - Base models, utilities
3. ✅ `apps/authentication/` - User model, SSO, RBAC
4. ✅ PostgreSQL setup, migrations
5. ✅ Security hardening (HTTPS, CSRF, headers)
6. ✅ Audit middleware

#### **Phase 2: Shared Services (Week 4-5)**
1. ✅ `apps/alerts/` - Unified alert system
   - Migrate `common/alert_store` → Django ORM
   - Convert all enums to `TextChoices`
   - Set up signal-based audit logging
2. ✅ `apps/metrics/` - Activity tracking
   - Migrate `common/metrics_store` → Django ORM
   - Set up daily snapshot Celery task
3. ✅ `apps/notifications/` - Notification channels
   - Migrate `common/channels` → Django app
   - Set up signal-based notifications

#### **Phase 3: Low-Risk Modules (Week 6-8)**

**Priority 1: Action Analytics** (Week 6)
- **Why first:** Read-only, no critical workflows
- **Migration:**
  - Create `apps/action_analytics/`
  - Views consume `apps/metrics/` (already migrated)
  - Convert templates to Django templates (minimal changes)
  - No models needed (reads from `metrics`)
- **Risk:** ⭐ Very Low
- **Route:** `/action-analytics/` → Django

**Priority 2: MDRO Surveillance** (Week 7)
- **Why next:** Simple FHIR-based detection, few dependencies
- **Migration:**
  - Create `apps/mdro_surveillance/`
  - Models: `MDROCase`, `MDRODetection`
  - FHIR client (keep as-is, wrap in Django)
  - Dashboard views + templates
- **Risk:** ⭐⭐ Low
- **Route:** `/mdro-surveillance/` → Django

**Priority 3: Outbreak Detection** (Week 8)
- **Why next:** Self-contained clustering algorithm
- **Migration:**
  - Create `apps/outbreak_detection/`
  - Models: `OutbreakCluster`, `ClusterCase`
  - Clustering logic (keep as Python module)
  - Dashboard views
- **Risk:** ⭐⭐ Low
- **Route:** `/outbreak-detection/` → Django

#### **Phase 4: Medium-Risk Modules (Week 9-12)**

**Priority 4: Dosing Verification** (Week 9)
- **Why:** Newest module, cleanest code, good test case
- **Migration:**
  - Create `apps/dosing_verification/`
  - Models: `DoseAlert`, `DoseFlag`, `DoseAssessment`
  - Rules engine (keep as Python modules)
  - FHIR client (keep as-is)
  - DRF API endpoints
  - Dashboard views (5 pages)
- **Risk:** ⭐⭐⭐ Medium
- **Route:** `/dosing-verification/` → Django

**Priority 5: Drug-Bug Mismatch** (Week 10)
- **Migration:**
  - Create `apps/drug_bug_mismatch/`
  - Models: `DrugBugAlert`
  - FHIR client + matching logic
  - Dashboard
- **Risk:** ⭐⭐⭐ Medium
- **Route:** `/drug-bug-mismatch/` → Django

**Priority 6: Surgical Prophylaxis** (Week 11)
- **Migration:**
  - Create `apps/surgical_prophylaxis/`
  - Models: `SurgicalCase`, `ProphylaxisEvaluation`
  - Compliance checker
  - Dashboard
- **Risk:** ⭐⭐⭐ Medium
- **Route:** `/surgical-prophylaxis/` → Django

**Priority 7: Guideline Adherence** (Week 12)
- **Migration:**
  - Create `apps/guideline_adherence/`
  - Models: `GuidelineCheck`, `Bundle`, `BundleElement`
  - LLM review workflow (keep logic, wrap in Django)
  - 7 guideline bundles (Python modules)
  - Dashboard views
- **Risk:** ⭐⭐⭐⭐ Medium-High (LLM complexity)
- **Route:** `/guideline-adherence/` → Django

#### **Phase 5: High-Risk Modules (Week 13-16)**

**Priority 8: HAI Detection** (Week 13-14) - **CRITICAL**
- **Why later:** Most complex, 5 HAI types, critical for infection control
- **Migration:**
  - Create `apps/hai_detection/`
  - Models for 5 HAI types:
    - `CLABSICandidate`, `SSICandidate`, `CAUTICandidate`, `VAECandidate`, `CDICandidate`
  - 5 detection algorithms (Python modules)
  - FHIR clients (devices, cultures, ventilators)
  - LLM extraction (keep as-is)
  - 5+ dashboard views
  - Validation framework
- **Risk:** ⭐⭐⭐⭐⭐ Very High
- **Testing:** Extensive testing required (most critical module)
- **Route:** `/hai-detection/` → Django

**Priority 9: ABX Approvals** (Week 15-16) - **CRITICAL**
- **Why last:** Active clinical workflow, can't break
- **Migration:**
  - Create `apps/abx_approvals/`
  - Models: `ApprovalRequest`, `ApprovalAudit`
  - Approval workflow logic
  - Auto-recheck scheduler (Celery periodic task)
  - Email notifications (Django signals)
  - Dashboard (pharmacy queue)
  - Re-approval chain logic
- **Risk:** ⭐⭐⭐⭐⭐ Very High
- **Testing:** Test re-approval chain thoroughly
- **Route:** `/abx-approvals/` → Django

**Priority 10: NHSN Reporting** (Week 17)
- **Migration:**
  - Create `apps/nhsn_reporting/`
  - Models: `AntimicrobialUsage`, `AntimicrobialResistance`
  - CSV export logic
  - Dashboard
- **Risk:** ⭐⭐⭐ Medium
- **Route:** `/nhsn-reporting/` → Django

### 5.2 Parallel Work Opportunities

Some modules can be migrated in parallel:

**Week 6-8 (Parallel):**
- Team A: Action Analytics
- Team B: MDRO Surveillance
- Team C: Outbreak Detection

**Week 9-12 (Parallel):**
- Team A: Dosing Verification
- Team B: Drug-Bug Mismatch
- Team C: Surgical Prophylaxis + Guideline Adherence

---

## 6. Database Design Recommendations

### 6.1 PostgreSQL Schema

```sql
-- Core tables (apps/alerts)
CREATE TABLE alerts (
    id UUID PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    patient_id VARCHAR(255),
    patient_mrn VARCHAR(100),
    patient_name VARCHAR(255),
    title VARCHAR(500) NOT NULL,
    summary TEXT,
    content JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    resolved_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    resolution_reason VARCHAR(50),
    snoozed_until TIMESTAMP,
    notes TEXT
);

CREATE INDEX idx_alerts_patient_mrn_status ON alerts(patient_mrn, status);
CREATE INDEX idx_alerts_type_status ON alerts(alert_type, status);
CREATE INDEX idx_alerts_created_at ON alerts(created_at DESC);

-- Audit table
CREATE TABLE alert_audit (
    id SERIAL PRIMARY KEY,
    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    performed_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    performed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    details TEXT
);

CREATE INDEX idx_alert_audit_alert_time ON alert_audit(alert_id, performed_at DESC);
```

### 6.2 Migration from SQLite to PostgreSQL

**Data migration strategy:**

1. **Export from SQLite:**
   ```bash
   python manage.py dumpdata alerts --output=alerts.json
   ```

2. **Load into PostgreSQL:**
   ```bash
   python manage.py loaddata alerts.json
   ```

3. **Validate:**
   ```python
   # Compare counts
   sqlite_count = get_sqlite_alert_count()
   postgres_count = Alert.objects.count()
   assert sqlite_count == postgres_count

   # Spot-check records
   for alert_id in sample_ids:
       sqlite_alert = get_from_sqlite(alert_id)
       postgres_alert = Alert.objects.get(id=alert_id)
       assert sqlite_alert == postgres_alert
   ```

### 6.3 Performance Optimization

**Indexing strategy:**
- Index foreign keys (user IDs, alert IDs)
- Composite indexes for common queries (`patient_mrn + status`)
- Indexes on datetime fields for time-based filtering

**Query optimization:**
- Use `.select_related()` for ForeignKeys
- Use `.prefetch_related()` for reverse FKs
- Use `.only()` / `.defer()` for large JSONFields
- Implement pagination (Django Paginator)

---

## 7. Django Settings Architecture

### 7.1 Settings Structure

```python
# aegis_project/settings/base.py
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
    'django_celery_beat',

    # AEGIS apps (shared)
    'apps.core',
    'apps.authentication',
    'apps.alerts',
    'apps.metrics',
    'apps.notifications',
    'apps.llm_tracking',

    # AEGIS apps (modules)
    'apps.hai_detection',
    'apps.dosing_verification',
    'apps.abx_approvals',
    'apps.guideline_adherence',
    'apps.drug_bug_mismatch',
    'apps.mdro_surveillance',
    'apps.surgical_prophylaxis',
    'apps.nhsn_reporting',
    'apps.outbreak_detection',
    'apps.action_analytics',

    # API
    'apps.api',
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
]

# Authentication
AUTH_USER_MODEL = 'authentication.User'
AUTHENTICATION_BACKENDS = [
    'apps.authentication.backends.LDAPAuthBackend',
    'apps.authentication.backends.SAMLAuthBackend',
    'django.contrib.auth.backends.ModelBackend',  # Fallback
]

# HIPAA Security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Session timeout (15 minutes)
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
}

# Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'America/New_York'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/aegis/django.log',
            'maxBytes': 1024 * 1024 * 100,  # 100 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/aegis/audit.log',
            'maxBytes': 1024 * 1024 * 500,  # 500 MB
            'backupCount': 50,  # Keep 50 files (25 GB total)
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'apps.authentication.audit': {
            'handlers': ['audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

```python
# aegis_project/settings/production.py
from .base import *

DEBUG = False
ALLOWED_HOSTS = ['aegis.cchmc.org', 'aegis-staging.cchmc.org']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'aegis'),
        'USER': os.environ.get('DB_USER', 'aegis_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # Connection pooling
    }
}

# Security
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files (use WhiteNoise or S3)
STATIC_ROOT = '/var/www/aegis/static/'
MEDIA_ROOT = '/var/www/aegis/media/'
```

---

## 8. Key Recommendations

### 8.1 Immediate Next Steps

1. **Create Django project skeleton** (Week 1)
   ```bash
   django-admin startproject aegis_project
   cd aegis_project
   python -m venv venv
   source venv/bin/activate
   pip install django djangorestframework psycopg2-binary celery redis
   ```

2. **Set up shared apps** (Week 1-2)
   ```bash
   python manage.py startapp core apps/core
   python manage.py startapp authentication apps/authentication
   python manage.py startapp alerts apps/alerts
   python manage.py startapp metrics apps/metrics
   ```

3. **Configure PostgreSQL** (Week 2)
   - Install PostgreSQL 15+
   - Create `aegis` database
   - Configure connection pooling (pgbouncer)
   - Enable encryption at rest

4. **Implement SSO** (Week 2-3)
   - Install `django-auth-ldap`
   - Configure LDAP backend for Cincinnati Children's AD
   - Test with hospital credentials
   - Implement role-based permissions

### 8.2 Critical Success Factors

1. **Zero downtime migration** - Run Flask and Django side-by-side
2. **Comprehensive testing** - Test each module before migrating next
3. **Data integrity** - Automated checksums and validation
4. **Security first** - HIPAA compliance from day 1
5. **Incremental rollout** - One module at a time, easy rollback

### 8.3 Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss during migration | ⭐⭐⭐⭐⭐ Critical | Automated backups, dry runs, checksums |
| Breaking ABX approvals | ⭐⭐⭐⭐⭐ Critical | Migrate last, extensive testing, parallel run |
| SSO integration issues | ⭐⭐⭐⭐ High | Early testing with IT, fallback auth |
| Performance degradation | ⭐⭐⭐ Medium | Load testing, query optimization, caching |
| Security vulnerabilities | ⭐⭐⭐⭐ High | Security audit, penetration testing |

---

## 9. Timeline Summary

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 1. Foundation | Week 1-3 | Django running, auth working, PostgreSQL |
| 2. Shared Services | Week 4-5 | Alerts, Metrics, Notifications in Django |
| 3. Low-Risk Modules | Week 6-8 | Action Analytics, MDRO, Outbreak |
| 4. Medium-Risk Modules | Week 9-12 | Dosing, Drug-Bug, Surgical, Guideline |
| 5. High-Risk Modules | Week 13-17 | HAI Detection, ABX Approvals, NHSN |
| 6. Celery & Background Tasks | Week 18 | Celery workers, periodic tasks |
| 7. API Consolidation | Week 19 | Unified DRF API, documentation |
| 8. Testing & QA | Week 20-21 | Load testing, security audit |
| 9. Deployment | Week 22 | Docker, CI/CD, production deploy |
| 10. Cutover | Week 23 | Final data sync, Flask decommission |

**Total:** ~6 months

---

## 10. Conclusion

The migration from Flask to Django is **achievable** with the recommended architecture:

✅ **Modular app structure** - Clear boundaries, scalable
✅ **Shared services pattern** - DRY, consistent
✅ **Risk-based migration order** - Low-risk first, critical modules last
✅ **Zero downtime strategy** - Nginx routing, gradual cutover
✅ **Django best practices** - ORM, migrations, DRF, Celery

**Next:** Await team lead approval to begin Phase 1 implementation.

---

**Prepared by:** Django Architect Agent
**Status:** Ready for review
**Questions?** Available for clarification
