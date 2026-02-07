# AEGIS Harmonization Audit Report

**Date:** 2026-02-06
**Scope:** UI consistency, backend patterns, interaction tracking, LLM override tracking across all AEGIS modules

---

## Table of Contents

1. [Overview](#overview)
2. [Frontend UI Harmonization](#1-frontend-ui-harmonization)
3. [Backend Harmonization](#2-backend-harmonization)
4. [User Interaction & Alert Tracking](#3-user-interaction--alert-tracking)
5. [LLM Extraction Accept/Override Tracking](#4-llm-extraction-acceptoverride-tracking)
6. [Prioritized Action Items](#prioritized-action-items)

---

## Overview

This audit analyzed all 12+ AEGIS modules, ~80 dashboard templates, 14 route files, and the `common/` shared library to identify inconsistencies in UI, backend patterns, interaction tracking, and LLM override tracking. The goal is to harmonize appearance and functionality across all modules and ensure comprehensive tracking of user interactions with alerts, notifications, and LLM-based recommendations.

### Modules Analyzed

| Module | Route File | Blueprint Prefix | Templates |
|--------|-----------|------------------|-----------|
| HAI Detection | `routes/hai.py` | `/hai-detection/` | `hai_*.html` |
| Drug-Bug Mismatch | `routes/drug_bug.py` | `/drug-bug-mismatch/` | `drug_bug_*.html` |
| ABX Indications | `routes/abx_indications.py` | `/abx-indications/` | `abx_indications_*.html` |
| Guideline Adherence | `routes/guideline_adherence.py` | `/guideline-adherence/` | `guideline_adherence_*.html` |
| MDRO Surveillance | `routes/mdro_surveillance.py` | `/mdro-surveillance/` | `mdro_*.html` |
| Outbreak Detection | `routes/outbreak_detection.py` | `/outbreak-detection/` | `outbreak_*.html` |
| Surgical Prophylaxis | `routes/surgical_prophylaxis.py` | `/surgical-prophylaxis/` | `surgical_prophylaxis_*.html` |
| ASP Metrics | `routes/asp_metrics.py` | `/asp-metrics/` | `asp_metrics_*.html` |
| ABX Approvals | `routes/abx_approvals.py` | `/abx-approvals/` | (uses shared templates) |
| NHSN Reporting | `routes/au_ar.py` | `/nhsn-reporting/` | `au_ar_*.html`, `nhsn_*.html` |
| ASP Alerts | `routes/views.py` | `/asp-alerts/` | `alerts_*.html`, `alert_detail.html` |
| Dashboards Index | `routes/dashboards.py` | `/dashboards/` | `dashboards_index.html` |

### Shared Infrastructure

| Component | Location | Purpose |
|-----------|----------|---------|
| Alert Store | `common/alert_store/` | Persistent alert lifecycle management (SQLite) |
| Metrics Store | `common/metrics_store/` | Unified activity tracking, daily snapshots, intervention tracking |
| ABX Approvals | `common/abx_approvals/` | Antibiotic approval request tracking |
| Notification Channels | `common/channels/` | Email, SMS, Teams notification delivery |
| Allergy Recommendations | `common/allergy_recommendations/` | Allergy-based antibiotic recommendations |
| LLM Architecture Doc | `common/AEGIS_LLM_EXTRACTION_ARCHITECTURE.md` | Design for unified LLM extraction layer |

---

## 1. Frontend UI Harmonization

### What's Working Well

- All templates extend `base.html` consistently
- Shared CSS in `static/style.css` with consistent teal/cyan color palette
- Consistent navbar pattern with per-module navigation links and active-state highlighting
- Flash message system in `base.html` handles common actions (acknowledged, snoozed, resolved, note_added)
- Relative time formatting (`timeAgo()`) and auto-refresh are shared via `base.html` JavaScript
- Disclaimer banner and footer are consistent across all pages

### Inconsistencies Found

#### 1.1 Navigation Depth Varies Across Modules

Some modules have rich sub-navigation while others are minimal:

| Module | Sub-Navigation Links |
|--------|---------------------|
| HAI Detection | Dashboard, History, Reports, Main, Help |
| ASP Alerts | Active Alerts, History, Reports, Main, Help |
| NHSN Reporting | Dashboard, AU Detail, AR Detail, HAI Detail, Denominators, Submission, Main, Help |
| ASP Metrics | Dashboard, Workload, Targets, Trends, Interventions, Main |
| ABX Approvals | Dashboard, New Request, History, Reports, Main, Help |
| MDRO Surveillance | Dashboard, Cases, Analytics, Main, Help |
| Outbreak Detection | Dashboard, Clusters, Alerts, Main, Help |
| **ABX Indications** | **Main, Help only** |
| **Drug-Bug Mismatch** | **Main, Help only** |
| **Surgical Prophylaxis** | **Main, Help only** |
| **Guideline Adherence** | **Main, Help only** |

**Recommendation:** Add consistent sub-navigation to all modules. At minimum: Dashboard, Active/Pending, History, Main, Help.

#### 1.2 Dashboard Card/Panel Layouts Differ

Each module uses slightly different structures for summary statistics cards on its dashboard page. Card sizing, icon usage, metric labeling, and grid layouts vary.

**Recommendation:** Create a shared `_stat_card.html` Jinja partial with standardized card layout:
```html
{% macro stat_card(title, value, subtitle, color, icon) %}
<div class="stat-card stat-card--{{ color }}">
    <div class="stat-card__value">{{ value }}</div>
    <div class="stat-card__title">{{ title }}</div>
    {% if subtitle %}<div class="stat-card__subtitle">{{ subtitle }}</div>{% endif %}
</div>
{% endmacro %}
```

#### 1.3 Data Table Patterns Inconsistent

- Some modules use clickable rows to navigate to detail pages; others use explicit action buttons in a table column
- Pagination implementation varies (some modules have it, some don't)
- Column ordering is inconsistent (some lead with patient name, others with date or severity)
- Sort controls differ across modules

**Recommendation:** Standardize data tables with consistent column ordering: Patient | Date/Time | Severity | Status | Actions. Use clickable rows for navigation + action buttons for status changes.

#### 1.4 Detail Page Layouts Vary

- HAI and MDRO use a two-column layout (patient context on left, alert details and actions on right)
- ABX Indications and Drug-Bug use single-column layouts
- Guideline Adherence uses tabbed sections
- Some detail pages have audit trail sections; others don't

**Recommendation:** Adopt two-column layout consistently: left column = patient demographics + context; right column = alert/case details + action buttons + audit trail.

#### 1.5 Status Badge Colors

Most modules use the shared CSS classes for severity badges (`badge-critical`, `badge-warning`, `badge-info`) but Outbreak Detection uses custom styles for cluster status (active, monitoring, resolved).

**Recommendation:** Consolidate all status and severity badges to shared CSS classes. Define a standard palette:
- Critical/Active: red
- Warning/Monitoring: amber
- Info/Pending: blue
- Success/Resolved: green
- Neutral/Snoozed: gray

#### 1.6 Empty State Handling

Some modules show plain "No data" text when lists are empty; others show styled empty-state cards with icons and explanatory text.

**Recommendation:** Create shared `_empty_state.html` partial with consistent styling.

#### 1.7 Help Page Structure

All modules have help pages but content depth and organization vary widely. Some have detailed workflow explanations; others are minimal.

**Recommendation:** Create a standardized help template with sections: Overview, Alert Types, User Actions, Workflow, FAQ.

### Frontend Priority Recommendation

Create a `templates/_components/` directory with shared Jinja macros/partials:
- `_stat_card.html`
- `_data_table.html`
- `_action_buttons.html`
- `_empty_state.html`
- `_status_badge.html`
- `_audit_trail.html`

---

## 2. Backend Harmonization

### What's Working Well

- Consistent Flask Blueprint pattern across all modules
- Hyphenated URL prefixes (`/hai-detection/`, `/drug-bug-mismatch/`, etc.)
- Shared `AlertStore` used by ASP Alerts, Drug-Bug, HAI, Outbreak for alert lifecycle
- Shared `MetricsStore` exists for unified activity tracking
- Shared notification channels (`common/channels/`) for email, SMS, Teams

### Inconsistencies Found

#### 2.1 MetricsStore Adoption is Partial

Only some modules log user activities to the unified `MetricsStore`:

| Module | Logs to MetricsStore? | Mechanism |
|--------|----------------------|-----------|
| ASP Alerts | Yes | Via `alert_store/store.py` `_log_asp_activity()` |
| HAI Detection | Yes | Via `hai_src/db.py` |
| Guideline Adherence | Yes | Via `guideline_src/episode_db.py` |
| ABX Indications | Yes | Via `antimicrobial-usage-alerts/au_alerts_src/indication_db.py` |
| ABX Approvals | Yes | Via `common/abx_approvals/store.py` |
| **Drug-Bug Mismatch** | **No** | Uses AlertStore but no MetricsStore integration |
| **MDRO Surveillance** | **No** | Has own db.py, no MetricsStore calls |
| **Outbreak Detection** | **No** | Has own db.py, no MetricsStore calls |
| **Surgical Prophylaxis** | **No** | Has own database.py, no MetricsStore calls |
| **NHSN Reporting** | **No** | No activity logging |

**Recommendation:** Add `MetricsStore.log_activity()` calls to all module interaction handlers, especially Drug-Bug, MDRO, Outbreak, and Surgical Prophylaxis.

#### 2.2 ModuleSource Enum is Incomplete

The `ModuleSource` enum in `common/metrics_store/models.py` currently includes:

```python
class ModuleSource(Enum):
    HAI = "hai"
    ASP_ALERTS = "asp_alerts"
    GUIDELINE_ADHERENCE = "guideline_adherence"
    ABX_INDICATIONS = "abx_indications"
    DRUG_BUG = "drug_bug"
    SURGICAL_PROPHYLAXIS = "surgical_prophylaxis"
    ABX_APPROVALS = "abx_approvals"
```

**Missing:** `MDRO_SURVEILLANCE`, `OUTBREAK_DETECTION`, `NHSN_REPORTING`

**Recommendation:** Add the missing values to the enum.

#### 2.3 Data Access Patterns Differ

Each module uses a different approach to data access:

| Module | Data Access Pattern |
|--------|-------------------|
| HAI Detection | Own `hai_src/db.py` with SQLite |
| Guideline Adherence | Own `guideline_src/episode_db.py` and `adherence_db.py` |
| ABX Indications | Own `indication_db.py` in `antimicrobial-usage-alerts/` |
| Drug-Bug Mismatch | Direct `AlertStore` access from route file |
| MDRO Surveillance | Own `mdro_src/db.py` |
| Outbreak Detection | Own `outbreak_src/db.py` |
| Surgical Prophylaxis | Own `src/database.py` |
| ABX Approvals | `common/abx_approvals/store.py` |

**Recommendation:** Create consistent module-level service classes that wrap DB access and always log to `MetricsStore`. This doesn't require changing the DB layer, just adding a service facade.

#### 2.4 Error Handling Varies

- HAI, MDRO, Outbreak, Surgical Prophylaxis, ABX Indications have dedicated `*_not_found.html` templates for 404s
- Some routes redirect on error; others return error templates
- API endpoints return JSON errors inconsistently (some with status codes, some without)

**Recommendation:** Standardize: detail pages return module-specific 404 templates; API endpoints return consistent JSON envelope: `{"success": bool, "data": ..., "error": ...}`.

#### 2.5 API Route Organization

- `routes/api.py` handles generic alert CRUD (acknowledge, snooze, resolve, update status)
- Module-specific API endpoints are defined inline in each module's route file
- No API versioning or consistent JSON response format

**Recommendation:** Consider creating a shared `api_response()` helper function for consistent JSON responses.

---

## 3. User Interaction & Alert Tracking

### Current State (Well-Built Foundation)

#### AlertStore (`common/alert_store/`)

The `AlertStore` tracks a solid alert lifecycle:

**AlertStatus** (lifecycle states):
```
PENDING -> SENT -> ACKNOWLEDGED -> SNOOZED -> RESOLVED
```

**AuditAction** (tracked actions):
```
CREATED, SENT, ACKNOWLEDGED, SNOOZED, RESOLVED, REOPENED, NOTE_ADDED
```

**ResolutionReason** (10 options for how alerts are closed):
```
ACKNOWLEDGED            - Just acknowledged, no action needed
MESSAGED_TEAM           - Messaged the care team
DISCUSSED_WITH_TEAM     - Discussed with care team
APPROVED                - Therapy approved as appropriate
SUGGESTED_ALTERNATIVE   - Recommended alternative therapy
THERAPY_CHANGED         - Therapy was changed
THERAPY_STOPPED         - Therapy was discontinued
PATIENT_DISCHARGED      - Patient discharged
AUTO_ACCEPTED           - Auto-accepted after timeout
OTHER                   - Other reason (see notes)
```

Features:
- Full audit trail with timestamps and user attribution
- Duplicate detection via `check_if_alerted()`
- Auto-accept for old unreviewed alerts
- Comprehensive analytics: alerts by day, severity, status, resolution reason breakdown, response time metrics, day-of-week distribution

#### MetricsStore (`common/metrics_store/`)

**ActivityType** (provider actions tracked):
```
REVIEW, ACKNOWLEDGMENT, RESOLUTION, INTERVENTION, EDUCATION, OVERRIDE
```

**DailySnapshot** fields:
- Alert metrics: created, resolved, acknowledged, avg time to ack/resolve
- HAI metrics: candidates created/reviewed, confirmed, override count
- Bundle metrics: episodes active, alerts created, adherence rate
- ABX indication metrics: reviews, appropriate/inappropriate counts and rate
- Human activity: total reviews, unique reviewers, total interventions
- Breakdowns: by location, by service

**Intervention tracking:** Sessions, targets, outcomes with pre/post comparison and sustained improvement tracking.

### Gaps Identified

#### 3.1 Interaction Tracking Not Unified Across All Modules

| Gap | Current State | Recommendation |
|-----|--------------|----------------|
| Drug-Bug does not log to MetricsStore | Alerts tracked in AlertStore but user interactions (acknowledge, resolve) are not logged as provider activities | Add `MetricsStore.log_activity()` calls to Drug-Bug route handlers |
| MDRO does not log to MetricsStore | Has own `db.py` for case tracking but no unified activity logging | Add MetricsStore integration to MDRO review/classification handlers |
| Outbreak does not log to MetricsStore | Has own `db.py` for cluster tracking but no unified activity logging | Add MetricsStore integration to Outbreak alert/cluster handlers |
| Surgical Prophylaxis does not log to MetricsStore | Has own `database.py` but no unified activity logging | Add MetricsStore integration to Surgical Prophylaxis handlers |
| NHSN Reporting has no activity logging | Submission and review actions are not tracked | Add MetricsStore integration for NHSN submission/review workflows |

#### 3.2 Missing Interaction Types

The current `AuditAction` enum captures core actions but misses several important interaction types:

| Missing Action | Description | Value |
|---------------|-------------|-------|
| **Viewed** | User opened the detail page for an alert/case | `viewed` |
| **Escalated** | Escalated to attending/senior physician | `escalated` |
| **Forwarded** | Forwarded to a colleague | `forwarded` |
| **Deferred** | Deferred to next shift | `deferred` |
| **Commented** | Added a clinical comment (distinct from general notes) | `commented` |

**Recommended additions to `AuditAction`:**
```python
class AuditAction(Enum):
    # ... existing values ...
    VIEWED = "viewed"
    ESCALATED = "escalated"
    FORWARDED = "forwarded"
    DEFERRED = "deferred"
    COMMENTED = "commented"
```

#### 3.3 Missing Resolution Reasons

The current `ResolutionReason` enum is strong but could be expanded:

| Missing Reason | Description | Value |
|---------------|-------------|-------|
| Escalated to Attending | Escalated to attending physician for decision | `escalated_to_attending` |
| Deferred to Next Shift | Passed to next shift for follow-up | `deferred_to_next_shift` |
| Culture Pending | Waiting for culture results before acting | `culture_pending` |
| No Action Needed | Alert reviewed, determined no action required | `no_action_needed` |

**Recommended additions to `ResolutionReason`:**
```python
class ResolutionReason(Enum):
    # ... existing values ...
    ESCALATED_TO_ATTENDING = "escalated_to_attending"
    DEFERRED_TO_NEXT_SHIFT = "deferred_to_next_shift"
    CULTURE_PENDING = "culture_pending"
    NO_ACTION_NEEDED = "no_action_needed"
```

#### 3.4 Notification Channel Tracking

The `common/channels/` implementations (email, SMS, Teams) send notifications but do not track whether the notification was read or clicked.

**Recommendation:** Add delivery receipt tracking to notification channels:
- Email: track open/click via tracking pixel or link redirect
- Teams: track message read receipts via Teams API
- SMS: track delivery status via SMS provider callbacks

#### 3.5 Session-Level Metrics

There is no tracking of user sessions:
- How many alerts a user reviews per session
- Session duration
- Alert-to-action time per user per session

**Recommendation:** Add lightweight session tracking to `MetricsStore`:
```python
class UserSession:
    session_id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None
    alerts_reviewed: int
    actions_taken: int
    modules_accessed: list[str]
```

#### 3.6 DailySnapshot Missing Module Metrics

The `DailySnapshot` has dedicated fields for HAI, Bundle (Guideline), and ABX Indication metrics, but nothing for:
- Drug-Bug Mismatch (alerts created, resolved, therapy changed rate)
- MDRO Surveillance (cases identified, reviewed, confirmed)
- Outbreak Detection (clusters active, alerts triggered, investigations)
- Surgical Prophylaxis (cases evaluated, compliant rate, timing metrics)

**Recommendation:** Add the following fields to `DailySnapshot`:
```python
# Drug-Bug metrics
drug_bug_alerts_created: int = 0
drug_bug_alerts_resolved: int = 0
drug_bug_therapy_changed_count: int = 0

# MDRO metrics
mdro_cases_identified: int = 0
mdro_cases_reviewed: int = 0
mdro_confirmed: int = 0

# Outbreak metrics
outbreak_clusters_active: int = 0
outbreak_alerts_triggered: int = 0

# Surgical Prophylaxis metrics
surgical_prophylaxis_cases: int = 0
surgical_prophylaxis_compliant: int = 0
surgical_prophylaxis_compliance_rate: float | None = None
```

---

## 4. LLM Extraction Accept/Override Tracking

### Current State

#### ABX Indications (Most Mature)

The ABX Indications module has excellent LLM tracking via `abx-indications/training_collector.py`:

**Extraction logging (`ABXExtractionRecord`):**
- Every LLM extraction is recorded with: candidate_id, antibiotic, input notes, extracted syndrome, syndrome confidence (definite/probable/unclear), therapy intent, supporting evidence, evidence quotes, red flags, guideline matching, model used, extraction time

**Human review decisions:**
- `syndrome_decision`: `confirm_syndrome` | `correct_syndrome` | `no_indication` | `viral_illness`
- `agent_decision`: `agent_appropriate` | `agent_acceptable` | `agent_inappropriate`
- Agent notes for context

**Training data pipeline:**
- Corrections are saved and can be exported for fine-tuning via `export_training_data()`
- Stats track review rate, correction rate, syndrome distribution, agent decision distribution
- Monthly JSONL files for storage

#### Guideline Adherence (Partial)

- LLM extracts clinical appearance from notes (e.g., febrile infant well-appearing vs ill-appearing)
- Users can confirm or override with structured override reasons
- Override reason categories defined in `GUIDELINE_OVERRIDE_REASONS` and `OVERRIDE_REASONS` dicts
- Training data collection mirrors the ABX pattern via `guideline_src/episode_db.py`

#### HAI Detection (Partial)

- Users can override the automated HAI classification (confirm/exclude a candidate)
- Override reasons are captured with both a structured category (`override_reason_category`) and free-text (`override_reason`)
- Logged to MetricsStore as `ActivityType.OVERRIDE`

#### Other Modules

- Surgical Prophylaxis, MDRO, and Outbreak currently use rule-based logic, not LLM extraction
- The `AEGIS_LLM_EXTRACTION_ARCHITECTURE.md` design document plans for unified LLM extraction across all modules (recommended architecture: Option 3, Unified Extraction Layer)

### Gaps Identified

#### 4.1 No Unified LLM Tracking Schema

Each module that uses LLM extraction has its own tracking mechanism:
- ABX: `ABXTrainingCollector` with `ABXExtractionRecord`
- Guideline: episode_db with its own schema
- HAI: hai_src/db with its own schema

There is no shared interface for logging LLM accept/override decisions.

**Recommendation:** Create `common/llm_tracking/` with a unified `LLMDecisionTracker` class that all modules can use.

#### 4.2 Override Reason Taxonomy Varies

| Module | Override Categories |
|--------|-------------------|
| ABX Indications | confirm_syndrome, correct_syndrome, no_indication, viral_illness |
| Guideline Adherence | Structured dict of medical reasons (module-specific) |
| HAI Detection | Category-based with free-text |

**Recommendation:** Create a unified override reason taxonomy (see section 4.5 below).

#### 4.3 Missing LLM Tracking in Planned Modules

Surgical Prophylaxis, MDRO, and Outbreak currently don't have LLM-based extraction, but the architecture document plans for it. The tracking interface should be designed now so it's ready when LLM extraction is added to these modules.

#### 4.4 No Cross-Module LLM Performance Dashboard

Each module tracks its own LLM accuracy (ABX has `abx_indications_analytics.html` and `model_training.html`; Guideline has `guideline_adherence_training_stats.html`) but there is no unified view of LLM acceptance rates across all modules.

**Recommendation:** Add an LLM Performance section to the ASP Metrics dashboard showing:
- Overall acceptance rate by module
- Override rate trends over time
- Most common override reasons
- Confidence calibration (does "definite" confidence correlate with higher acceptance?)

#### 4.5 Recommended Unified Override Reason Taxonomy

```python
class LLMOverrideReason(Enum):
    """Unified reasons for overriding LLM-based recommendations across all modules."""

    # Clinical judgment
    CLINICAL_CONTEXT_DIFFERS = "clinical_context_differs"
    # LLM missed relevant clinical context visible to the reviewer

    ADDITIONAL_INFO_AVAILABLE = "additional_info_available"
    # Reviewer has access to information not in the notes the LLM reviewed

    PATIENT_SPECIFIC_FACTORS = "patient_specific_factors"
    # Unique patient considerations (allergies, comorbidities, preferences)

    # LLM extraction errors
    INCORRECT_EXTRACTION = "incorrect_extraction"
    # LLM extracted wrong data from the note

    MISSING_DATA = "missing_data"
    # LLM missed important data present in the note

    OUTDATED_INFORMATION = "outdated_information"
    # LLM used information that has since been superseded

    # Guideline/protocol
    LOCAL_PROTOCOL_DIFFERS = "local_protocol_differs"
    # Local CCHMC guidelines differ from what the LLM recommended

    SPECIALIST_RECOMMENDATION = "specialist_recommendation"
    # ID or other specialist recommendation overrides LLM

    # Administrative
    DUPLICATE_ALERT = "duplicate_alert"
    # Already addressed elsewhere

    DOCUMENTATION_LAG = "documentation_lag"
    # Notes not yet updated to reflect current status

    OTHER = "other"
    # Free-text reason required
```

#### 4.6 Recommended Unified LLM Decision Record Schema

```python
@dataclass
class LLMDecisionRecord:
    """Unified tracking record for LLM accept/override decisions."""

    # Identifiers
    decision_id: str                    # Unique ID for this decision
    module: ModuleSource                # Which module (abx_indications, guideline_adherence, etc.)
    entity_id: str                      # Module-specific entity (candidate_id, episode_id, case_id)
    patient_mrn: str | None = None

    # LLM extraction details
    model_used: str = ""                # Model name/version
    extraction_confidence: str = ""     # definite, probable, unclear
    extraction_result: dict = field(default_factory=dict)   # Module-specific extraction data
    extraction_time_ms: int = 0         # Extraction latency

    # Human decision
    decision: str = ""                  # accept, override, partial_accept
    decision_by: str = ""               # Reviewer identifier
    decision_at: datetime = field(default_factory=datetime.now)

    # Override details (populated when decision != "accept")
    override_reason: LLMOverrideReason | None = None
    override_reason_text: str | None = None     # Free text for "other" reason
    corrected_result: dict | None = None        # What the human changed it to

    # Quality metrics
    time_to_decision_seconds: int | None = None  # How long the reviewer took

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
```

#### 4.7 Confidence Calibration Not Tracked

Confidence levels (definite/probable/unclear) are recorded in the ABX Indications module but there is no analysis of whether confidence correlates with actual acceptance rates. This is important for understanding whether the LLM's self-assessed confidence is well-calibrated.

**Recommendation:** Add confidence calibration analysis to training stats: for each confidence level, compute the acceptance rate. If "definite" extractions are overridden 30% of the time, the confidence scoring needs adjustment.

#### 4.8 No Time-Series LLM Accuracy Tracking

Current stats show point-in-time accuracy but not trends. There is no way to see if the LLM is improving or degrading over time.

**Recommendation:** Add weekly/monthly LLM accuracy snapshots to `DailySnapshot`:
```python
# LLM performance metrics
llm_extractions_total: int = 0
llm_extractions_accepted: int = 0
llm_extractions_overridden: int = 0
llm_acceptance_rate: float | None = None
```

---

## Prioritized Action Items

### High Priority (Improve Data Quality Now)

- [x] **H1.** Add `MetricsStore.log_activity()` calls to Drug-Bug, MDRO, Outbreak, and Surgical Prophylaxis route handlers so all user interactions are tracked in the unified store
- [x] **H2.** Add missing `ModuleSource` enum values: `MDRO_SURVEILLANCE`, `OUTBREAK_DETECTION`, `NHSN_REPORTING`
- [x] **H3.** Add `VIEWED` audit action to track page-view engagement across all module detail pages
- [x] **H4.** Expand `DailySnapshot` to include metrics for Drug-Bug, MDRO, Outbreak, and Surgical Prophylaxis modules

### Medium Priority (Harmonize UX)

- [ ] **M1.** Create shared template partials (`templates/_components/`) for stat cards, data tables, action buttons, empty states, status badges, audit trails
- [ ] **M2.** Standardize sub-navigation across all modules to include at minimum: Dashboard, Active/Pending, History, Main, Help
- [ ] **M3.** Standardize detail page layouts to two-column format (patient context left, details + actions right)
- [ ] **M4.** Create unified JSON response envelope for all API endpoints: `{"success": bool, "data": ..., "error": ...}`
- [x] **M5.** Add missing `ResolutionReason` values: `escalated_to_attending`, `deferred_to_next_shift`, `culture_pending`, `no_action_needed`
- [x] **M6.** Add missing `AuditAction` values: `viewed`, `escalated`, `forwarded`, `deferred`, `commented`

### Lower Priority (LLM Tracking Enhancements)

- [ ] **L1.** Create `common/llm_tracking/` with unified `LLMDecisionTracker` and `LLMDecisionRecord` schema
- [ ] **L2.** Implement unified `LLMOverrideReason` taxonomy across ABX Indications, Guideline Adherence, and HAI Detection
- [ ] **L3.** Add LLM accuracy trend fields to `DailySnapshot` (`llm_extractions_total`, `llm_acceptance_rate`, etc.)
- [ ] **L4.** Add cross-module LLM performance view to ASP Metrics dashboard
- [ ] **L5.** Implement confidence calibration analysis (acceptance rate by confidence level)
- [ ] **L6.** Add session-level tracking (alerts reviewed per session, session duration)
- [ ] **L7.** Add notification delivery receipt tracking to `common/channels/`

---

## Files Referenced

### Common Library
- `common/alert_store/models.py` - AlertType, AlertStatus, AuditAction, ResolutionReason, StoredAlert
- `common/alert_store/store.py` - AlertStore with lifecycle management and analytics
- `common/metrics_store/models.py` - ActivityType, ModuleSource, DailySnapshot, InterventionTarget, etc.
- `common/metrics_store/store.py` - MetricsStore with activity logging and reporting
- `common/metrics_store/aggregator.py` - Metrics aggregation
- `common/metrics_store/reports.py` - Report generation
- `common/abx_approvals/models.py` - ABX approval models
- `common/abx_approvals/store.py` - ABX approval tracking
- `common/AEGIS_LLM_EXTRACTION_ARCHITECTURE.md` - LLM extraction architecture design

### Dashboard
- `dashboard/templates/base.html` - Base template (navbar, flash messages, footer, JS)
- `dashboard/static/style.css` - Shared stylesheet
- `dashboard/routes/*.py` - All route files (14 total)
- `dashboard/services/fhir.py` - FHIR service layer
- `dashboard/services/user.py` - User service

### LLM Extraction
- `abx-indications/indication_extractor.py` - LLM extraction for antibiotic indications
- `abx-indications/training_collector.py` - Training data collection from user feedback
- `abx-indications/indication_taxonomy.py` - Indication taxonomy
- `guideline-adherence/guideline_src/episode_monitor.py` - Episode-level guideline monitoring
- `guideline-adherence/guideline_src/episode_db.py` - Episode database with LLM review tracking
