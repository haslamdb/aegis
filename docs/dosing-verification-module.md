# Antimicrobial Dosing Verification & Alerting Module

**GitHub Issue:** #19
**Priority:** High
**Status:** Planning

---

## Overview

Real-time verification of antimicrobial dosing, interval, and route based on clinical indication, patient factors, and drug interactions. Generates tiered alerts when dosing is inappropriate for the clinical context. Integrates with the existing ABX Indications module (which extracts the indication) and the ASP Alerts workflow (for pharmacist review and resolution tracking).

### Design Philosophy

The ABX Indications module answers: **"Why is this patient on this antibiotic?"**
This module answers: **"Is the dose correct for that reason?"**

ABX Indications remains a passive monitoring/tracking module. This module is the active alerting layer that fires when the dose, interval, route, or duration doesn't match what the indication, age, weight, renal function, or co-medications require.

---

## Architecture

```
                         Data Sources (FHIR)
                    ┌──────────┬──────────┬──────────┐
                    │          │          │          │
              Medication   Lab Results  Patient     Clinical
              Requests     (SCr, GFR,   Demographics Notes
              (dose,       weight, etc) (age, weight)
               interval,
               route)
                    │          │          │          │
                    └──────────┴──────────┴──────────┘
                                    │
                                    ▼
                    ┌────────────────────────────┐
    ABX Indications │   Indication Extraction    │ (existing module)
    Module          │   LLM-based syndrome ID    │
                    └────────────────────────────┘
                                    │
                           indication + confidence
                                    │
                                    ▼
                    ┌────────────────────────────┐
    NEW MODULE      │   Dosing Rules Engine      │
                    │                            │
                    │  1. Indication-based rules  │
                    │  2. Renal adjustment rules  │
                    │  3. Weight-based rules      │
                    │  4. Age-based rules         │
                    │  5. Drug interaction rules  │
                    │  6. Route verification      │
                    │  7. Duration rules          │
                    └────────────────────────────┘
                          │              │
                    ┌─────┘              └─────┐
                    ▼                          ▼
          ┌──────────────┐          ┌──────────────────┐
          │ DoseAlert    │          │ MetricsStore     │
          │ Store        │          │ (activity log)   │
          │ (SQLite)     │          └──────────────────┘
          └──────────────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     Dashboard   Teams     Email
     (review)    (critical) (high)
```

---

## File Plan

### New Files

| File | Purpose |
|------|---------|
| **Backend** | |
| `dosing-verification/src/__init__.py` | Package init |
| `dosing-verification/src/models.py` | Dataclasses, enums (DoseAlert, DoseFlag, etc.) |
| `dosing-verification/src/rules_engine.py` | Core rules engine: evaluates dose against indication + patient factors |
| `dosing-verification/src/rules/` | Rule modules (one per category) |
| `dosing-verification/src/rules/__init__.py` | Rule registry |
| `dosing-verification/src/rules/indication_rules.py` | Indication-dependent dosing tables |
| `dosing-verification/src/rules/renal_rules.py` | Renal adjustment rules |
| `dosing-verification/src/rules/weight_rules.py` | Weight-based dosing (obesity, pediatric) |
| `dosing-verification/src/rules/age_rules.py` | Age-based dosing (neonatal, pediatric, adult) |
| `dosing-verification/src/rules/interaction_rules.py` | Drug-drug interaction checks |
| `dosing-verification/src/rules/route_rules.py` | Route verification (e.g., PO vancomycin for CDI) |
| `dosing-verification/src/rules/duration_rules.py` | Duration appropriateness |
| `dosing-verification/src/fhir_client.py` | FHIR data fetching (extends DrugBugFHIRClient pattern) |
| `dosing-verification/src/monitor.py` | Main orchestrator: poll orders → evaluate → alert |
| `dosing-verification/src/runner.py` | CLI entry point (--once, --continuous, --dry-run) |
| **Store** | |
| `common/dosing_verification/__init__.py` | Package init |
| `common/dosing_verification/models.py` | Store data models |
| `common/dosing_verification/store.py` | DoseAlertStore (SQLite) |
| `common/dosing_verification/schema.sql` | Database schema |
| **Dashboard** | |
| `dashboard/routes/dosing_verification.py` | Blueprint with routes + API + CSV export |
| `dashboard/templates/dosing_dashboard.html` | Active alerts list with filters |
| `dashboard/templates/dosing_alert_detail.html` | Alert detail with ASP review workflow |
| `dashboard/templates/dosing_history.html` | Resolved alerts with filters |
| `dashboard/templates/dosing_reports.html` | Analytics dashboard |
| `dashboard/templates/dosing_help.html` | Help/documentation page |

### Files to Modify

| File | Change |
|------|--------|
| `dashboard/app.py` | Register `dosing_verification_bp` blueprint |
| `dashboard/templates/base.html` | Add Dosing Verification nav section |
| `dashboard/templates/landing.html` | Add module card |
| `dashboard/templates/about.html` | Add module description |
| `common/alert_store/models.py` | Add `DOSING_ALERT` to AlertType enum |
| `common/metrics_store/models.py` | Add `DOSING_VERIFICATION` to ModuleSource enum |

---

## Data Model

### Enums

```python
class DoseFlagType(str, Enum):
    """Category of dosing issue detected."""
    SUBTHERAPEUTIC_DOSE = "subtherapeutic_dose"       # Dose too low for indication
    SUPRATHERAPEUTIC_DOSE = "supratherapeutic_dose"   # Dose too high
    WRONG_INTERVAL = "wrong_interval"                  # Interval doesn't match indication
    WRONG_ROUTE = "wrong_route"                        # Route inappropriate (IV vanc for CDI)
    NO_RENAL_ADJUSTMENT = "no_renal_adjustment"        # Renal impairment, no dose reduction
    EXCESSIVE_RENAL_ADJUSTMENT = "excessive_renal_adj" # Over-reduced for renal function
    WEIGHT_DOSE_MISMATCH = "weight_dose_mismatch"     # Dose not weight-appropriate
    AGE_DOSE_MISMATCH = "age_dose_mismatch"           # Dose not age-appropriate
    MAX_DOSE_EXCEEDED = "max_dose_exceeded"            # Exceeds absolute max
    DRUG_INTERACTION = "drug_interaction"              # Significant DDI
    DURATION_EXCESSIVE = "duration_excessive"          # Duration longer than guideline
    DURATION_INSUFFICIENT = "duration_insufficient"    # Duration shorter than guideline
    CONTRAINDICATED = "contraindicated"                # Drug contraindicated in this context
    EXTENDED_INFUSION_CANDIDATE = "extended_infusion"  # Would benefit from extended infusion


class DoseAlertSeverity(str, Enum):
    """Alert severity determines notification channel."""
    CRITICAL = "critical"   # Real-time Teams + Email (wrong route, contraindicated, dangerous DDI)
    HIGH = "high"           # Email + dashboard (subtherapeutic for severe infection, no renal adj)
    MODERATE = "moderate"   # Dashboard only (duration optimization, extended infusion candidate)


class DoseAlertStatus(str, Enum):
    """Alert lifecycle status."""
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class DoseResolution(str, Enum):
    """How the alert was resolved."""
    DOSE_ADJUSTED = "dose_adjusted"
    INTERVAL_ADJUSTED = "interval_adjusted"
    ROUTE_CHANGED = "route_changed"
    THERAPY_CHANGED = "therapy_changed"
    THERAPY_STOPPED = "therapy_stopped"
    DISCUSSED_WITH_TEAM = "discussed_with_team"
    CLINICAL_JUSTIFICATION = "clinical_justification"  # Dose intentional, documented reason
    MESSAGED_TEAM = "messaged_team"
    ESCALATED_TO_ATTENDING = "escalated_to_attending"
    NO_ACTION_NEEDED = "no_action_needed"
    AUTO_ACCEPTED = "auto_accepted"
    OTHER = "other"

    @classmethod
    def display_name(cls, value):
        return {
            cls.DOSE_ADJUSTED: "Dose Adjusted",
            cls.INTERVAL_ADJUSTED: "Interval Adjusted",
            cls.ROUTE_CHANGED: "Route Changed",
            cls.THERAPY_CHANGED: "Therapy Changed",
            cls.THERAPY_STOPPED: "Therapy Stopped",
            cls.DISCUSSED_WITH_TEAM: "Discussed with Team",
            cls.CLINICAL_JUSTIFICATION: "Clinical Justification",
            cls.MESSAGED_TEAM: "Messaged Team",
            cls.ESCALATED_TO_ATTENDING: "Escalated to Attending",
            cls.NO_ACTION_NEEDED: "No Action Needed",
            cls.AUTO_ACCEPTED: "Auto-Accepted",
            cls.OTHER: "Other",
        }.get(value, value)

    @classmethod
    def all_options(cls):
        return [(r.value, cls.display_name(r)) for r in cls if r != cls.AUTO_ACCEPTED]
```

### Core Dataclasses

```python
@dataclass
class DoseFlag:
    """A single dosing issue found by the rules engine."""
    flag_type: DoseFlagType
    severity: DoseAlertSeverity
    drug: str
    message: str                    # Human-readable description
    expected: str                   # What the dose should be (e.g., "100 mg/kg/day divided q12h")
    actual: str                     # What was ordered (e.g., "50 mg/kg/day q24h")
    rule_source: str                # Which guideline/rule triggered this (e.g., "IDSA Meningitis 2024")
    indication: str                 # The clinical indication driving this rule
    details: dict | None = None     # Additional context (renal function, weight, interaction drugs)

    def to_dict(self) -> dict: ...


@dataclass
class DoseAssessment:
    """Complete assessment of a patient's antimicrobial dosing."""
    assessment_id: str
    patient_id: str
    patient_mrn: str
    patient_name: str
    encounter_id: str | None

    # Patient factors used in evaluation
    age_years: float | None
    weight_kg: float | None
    height_cm: float | None
    scr: float | None               # Serum creatinine
    gfr: float | None               # Estimated GFR
    is_on_dialysis: bool
    gestational_age_weeks: int | None  # For neonates

    # What was evaluated
    medications_evaluated: list[dict]  # [{drug, dose, interval, route, order_id, start_date}]
    indication: str | None             # From ABX Indications module
    indication_confidence: float | None
    indication_source: str | None      # "llm", "taxonomy", "icd10"

    # Results
    flags: list[DoseFlag]
    max_severity: DoseAlertSeverity | None  # Highest severity across all flags
    assessed_at: str                         # ISO datetime
    assessed_by: str                         # "dosing_engine_v1"

    # Co-medications (for DDI checking)
    co_medications: list[dict]  # [{drug, class}] - non-antimicrobial meds relevant to DDIs

    def to_dict(self) -> dict: ...
    def to_alert_content(self) -> dict: ...  # For AlertStore


@dataclass
class DoseAlertRecord:
    """Persisted dose alert in the store."""
    id: str
    assessment_id: str
    patient_id: str
    patient_mrn: str
    patient_name: str
    encounter_id: str | None

    # Alert content
    drug: str                        # Primary drug with issue
    indication: str | None
    flag_type: str                   # DoseFlagType value
    severity: str                    # DoseAlertSeverity value
    message: str                     # Human-readable summary
    expected_dose: str
    actual_dose: str
    rule_source: str

    # Clinical context (JSON)
    patient_factors: str             # JSON: age, weight, renal, etc.
    assessment_details: str          # JSON: full DoseFlag details

    # Status tracking
    status: str                      # DoseAlertStatus value
    created_at: str
    sent_at: str | None
    acknowledged_at: str | None
    acknowledged_by: str | None
    resolved_at: str | None
    resolved_by: str | None
    resolution: str | None           # DoseResolution value
    resolution_notes: str | None
    notes: str | None

    @classmethod
    def from_row(cls, row) -> "DoseAlertRecord": ...
    def to_dict(self) -> dict: ...
```

### SQLite Schema

```sql
-- common/dosing_verification/schema.sql

CREATE TABLE IF NOT EXISTS dose_alerts (
    id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    patient_id TEXT,
    patient_mrn TEXT,
    patient_name TEXT,
    encounter_id TEXT,

    -- Alert content
    drug TEXT NOT NULL,
    indication TEXT,
    flag_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'moderate',
    message TEXT NOT NULL,
    expected_dose TEXT,
    actual_dose TEXT,
    rule_source TEXT,

    -- Clinical context (JSON blobs)
    patient_factors TEXT,        -- JSON: {age, weight, scr, gfr, dialysis, gest_age}
    assessment_details TEXT,     -- JSON: full assessment with all flags

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at TEXT,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    resolved_at TEXT,
    resolved_by TEXT,
    resolution TEXT,
    resolution_notes TEXT,
    notes TEXT,

    -- Deduplication: one active alert per drug per patient per flag type
    UNIQUE(patient_mrn, drug, flag_type, status)
);

CREATE INDEX IF NOT EXISTS idx_dose_alerts_status ON dose_alerts(status);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_severity ON dose_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_patient ON dose_alerts(patient_mrn);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_drug ON dose_alerts(drug);
CREATE INDEX IF NOT EXISTS idx_dose_alerts_created ON dose_alerts(created_at);

CREATE TABLE IF NOT EXISTS dose_alert_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    action TEXT NOT NULL,
    performed_by TEXT,
    performed_at TEXT NOT NULL DEFAULT (datetime('now')),
    details TEXT,
    FOREIGN KEY (alert_id) REFERENCES dose_alerts(id)
);

CREATE INDEX IF NOT EXISTS idx_dose_audit_alert ON dose_alert_audit(alert_id);
```

---

## DoseAlertStore

Follows the established AbxApprovalStore / AlertStore pattern.

```python
class DoseAlertStore:
    """SQLite-backed store for dosing verification alerts."""

    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.expanduser("~/.aegis/dose_alerts.db")
        self._init_db()

    # --- CRUD ---
    def save_alert(self, record: DoseAlertRecord) -> DoseAlertRecord
    def get_alert(self, alert_id: str) -> DoseAlertRecord | None
    def check_if_alerted(self, patient_mrn: str, drug: str, flag_type: str) -> bool

    # --- Status transitions ---
    def mark_sent(self, alert_id: str) -> None
    def acknowledge(self, alert_id: str, by: str) -> None
    def resolve(self, alert_id: str, by: str, resolution: str, notes: str = "") -> None
    def add_note(self, alert_id: str, by: str, note: str) -> None

    # --- Queries ---
    def list_active(self, severity=None, flag_type=None, drug=None, mrn=None) -> list[DoseAlertRecord]
    def list_resolved(self, days_back=30, resolution=None, severity=None) -> list[DoseAlertRecord]
    def list_by_patient(self, patient_mrn: str) -> list[DoseAlertRecord]

    # --- Analytics ---
    def get_stats(self) -> dict          # Counts by status, severity, flag_type
    def get_analytics(self, days=30) -> dict  # Resolution rates, response times, top drugs, top flags

    # --- Maintenance ---
    def auto_accept_old(self, hours=72) -> int
    def cleanup_old_resolved(self, days=90) -> int

    # --- Audit ---
    def get_audit_log(self, alert_id: str) -> list[dict]

    # --- Internal ---
    def _log_activity(self, alert_id, action, by, patient_mrn, details=None)
        # Fire-and-forget to MetricsStore with ModuleSource.DOSING_VERIFICATION
```

---

## Rules Engine

### Design

The rules engine is modular. Each rule module registers functions that take a standardized patient context and return a list of `DoseFlag` objects. Rules are evaluated in priority order and can be enabled/disabled via configuration.

```python
# dosing-verification/src/rules_engine.py

class DosingRulesEngine:
    """Evaluates antimicrobial orders against clinical rules."""

    def __init__(self, config=None):
        self.rules = [
            ContraindicationRules(),    # Check first: contraindicated scenarios
            RouteRules(),               # Wrong route (e.g., IV vancomycin for CDI)
            IndicationDoseRules(),      # Indication-specific dosing
            RenalAdjustmentRules(),     # Renal dose adjustments
            WeightBasedRules(),         # Weight-appropriate dosing
            AgeBasedRules(),            # Age-appropriate dosing (neonatal/peds)
            DrugInteractionRules(),     # Drug-drug interactions
            DurationRules(),            # Duration appropriateness
            ExtendedInfusionRules(),    # Extended infusion candidates
        ]

    def evaluate(self, context: PatientContext) -> DoseAssessment:
        """Run all rules against patient context, return assessment with flags."""
        flags = []
        for rule_module in self.rules:
            flags.extend(rule_module.evaluate(context))
        # Deduplicate, sort by severity, build assessment
        ...

@dataclass
class PatientContext:
    """All data needed for dosing evaluation, assembled from FHIR."""
    patient_id: str
    patient_mrn: str
    patient_name: str
    encounter_id: str | None

    # Demographics
    age_years: float | None
    weight_kg: float | None
    height_cm: float | None
    gestational_age_weeks: int | None  # Neonates only
    bsa: float | None                   # Body surface area (calculated)

    # Renal
    scr: float | None
    gfr: float | None
    crcl: float | None                  # Cockcroft-Gault CrCl
    is_on_dialysis: bool
    dialysis_type: str | None           # HD, CRRT, PD

    # Current antimicrobials
    antimicrobials: list[MedicationOrder]  # dose, interval, route, start_date, order_id

    # Indication (from ABX Indications module)
    indication: str | None
    indication_confidence: float | None
    indication_source: str | None

    # Co-medications (for DDI)
    co_medications: list[MedicationOrder]

    # Allergies
    allergies: list[dict]  # [{substance, severity, reaction}]


@dataclass
class MedicationOrder:
    """A single medication order from FHIR."""
    drug_name: str
    dose_value: float
    dose_unit: str          # mg, mg/kg, g
    interval: str           # q6h, q8h, q12h, q24h, etc.
    route: str              # IV, PO, IM, IT
    frequency_hours: int    # Normalized: q8h → 8
    daily_dose: float       # Calculated total daily dose
    daily_dose_per_kg: float | None  # If weight available
    start_date: str
    order_id: str
    infusion_duration_minutes: int | None  # For extended infusion checks
    rxnorm_code: str | None
```

### Rule Module Interface

Each rule module implements:

```python
class BaseRuleModule:
    """Base class for rule modules."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Return list of dosing flags for this patient context."""
        raise NotImplementedError
```

### Indication-Based Dosing Rules

The core clinical rules organized by syndrome. Each entry defines the expected dosing for a drug-indication pair. The engine compares the actual order against these expectations.

```python
# dosing-verification/src/rules/indication_rules.py

INDICATION_DOSE_RULES = {

    # === CNS Infections ===
    "meningitis": {
        "ceftriaxone": {
            "pediatric": {"dose_mg_kg_day": 100, "interval": "q12h", "max_daily_mg": 4000},
            "adult": {"dose_mg": 2000, "interval": "q12h"},
            "severity": "critical",
            "source": "IDSA Meningitis Guidelines 2024",
        },
        "meropenem": {
            "pediatric": {"dose_mg_kg_day": 120, "interval": "q8h", "max_daily_mg": 6000},
            "adult": {"dose_mg": 2000, "interval": "q8h"},
            "severity": "critical",
            "source": "IDSA Meningitis Guidelines",
        },
        "ampicillin": {
            "pediatric": {"dose_mg_kg_day": 300, "interval": "q6h", "max_daily_mg": 12000},
            "adult": {"dose_mg": 2000, "interval": "q4h"},
            "severity": "critical",
            "source": "IDSA Meningitis Guidelines",
        },
        "vancomycin": {
            "pediatric": {"dose_mg_kg_day": 60, "interval": "q6h", "trough_target": "15-20"},
            "adult": {"auc_mic_target": "400-600", "trough_target": "15-20"},
            "severity": "critical",
            "source": "IDSA/ASHP Vancomycin Guidelines 2020",
        },
        "metronidazole": {
            "pediatric": {"dose_mg_kg_day": 30, "interval": "q6h", "loading_mg_kg": 15},
            "adult": {"dose_mg": 500, "interval": "q6-8h", "loading_mg": 1000},
            "severity": "high",
            "source": "IDSA Brain Abscess Guidelines",
        },
    },

    "encephalitis": {
        "acyclovir": {
            "pediatric": {"dose_mg_kg": 20, "interval": "q8h"},
            "adult": {"dose_mg_kg": 10, "interval": "q8h"},
            "severity": "critical",
            "source": "IDSA Encephalitis Guidelines",
            "note": "HSV encephalitis requires 2x standard mucocutaneous dose",
        },
    },

    "brain_abscess": {
        "metronidazole": {
            "pediatric": {"dose_mg_kg_day": 30, "interval": "q6h", "loading_mg_kg": 15},
            "severity": "high",
            "source": "IDSA CNS Infection Guidelines",
        },
        "ceftriaxone": {
            "pediatric": {"dose_mg_kg_day": 100, "interval": "q12h", "max_daily_mg": 4000},
            "severity": "high",
            "source": "IDSA CNS Infection Guidelines",
        },
    },

    # === Endocarditis ===
    "endocarditis": {
        "gentamicin": {
            "pediatric": {"dose_mg_kg": 1, "interval": "q8h"},
            "adult": {"dose_mg_kg": 1, "interval": "q8h"},
            "severity": "critical",
            "source": "AHA Endocarditis Guidelines 2015",
            "note": "Synergy dosing (NOT extended-interval). 1 mg/kg q8h, not 5-7 mg/kg q24h",
            "flag_if_extended_interval": True,
        },
        "ampicillin": {
            "pediatric": {"dose_mg_kg_day": 300, "interval": "q4-6h"},
            "adult": {"dose_mg": 2000, "interval": "q4h", "daily_max_mg": 12000},
            "severity": "high",
            "source": "AHA Endocarditis Guidelines",
        },
        "daptomycin": {
            "adult": {"dose_mg_kg": 8, "interval": "q24h", "range_mg_kg": [8, 10]},
            "severity": "high",
            "source": "IDSA MRSA Guidelines (endocarditis dose: 8-10 mg/kg, NOT 4-6)",
        },
        "ceftriaxone": {
            "pediatric": {"dose_mg_kg_day": 100, "interval": "q12-24h"},
            "adult": {"dose_mg": 2000, "interval": "q12-24h"},
            "severity": "high",
            "source": "AHA Endocarditis Guidelines (enterococcal endocarditis combo)",
        },
    },

    # === C. difficile ===
    "c_difficile": {
        "vancomycin": {
            "pediatric": {"dose_mg_kg": 10, "interval": "q6h", "route": "PO", "max_dose_mg": 125},
            "adult": {"dose_mg": 125, "interval": "q6h", "route": "PO"},
            "adult_severe": {"dose_mg": 500, "interval": "q6h", "route": "PO"},
            "severity": "critical",
            "source": "IDSA/SHEA CDI Guidelines 2021",
            "note": "MUST be PO or rectal. IV vancomycin does NOT reach colon.",
            "route_critical": True,
        },
        "fidaxomicin": {
            "adult": {"dose_mg": 200, "interval": "q12h", "route": "PO", "duration_days": 10},
            "severity": "moderate",
            "source": "IDSA/SHEA CDI Guidelines 2021",
        },
        "metronidazole": {
            "note": "No longer first-line per IDSA 2021. Flag if used alone.",
            "severity": "moderate",
            "source": "IDSA/SHEA CDI Guidelines 2021",
        },
    },

    # === Invasive Fungal ===
    "candidemia": {
        "fluconazole": {
            "pediatric": {"dose_mg_kg_day": 12, "loading_mg_kg": 25, "interval": "q24h"},
            "adult": {"dose_mg": 800, "loading_mg": 800, "maintenance_mg": 400, "interval": "q24h"},
            "severity": "high",
            "source": "IDSA Candidiasis Guidelines 2016",
            "note": "Loading dose 12 mg/kg (max 800 mg) day 1, then 6-12 mg/kg/day",
        },
        "micafungin": {
            "pediatric": {"dose_mg_kg": 2, "interval": "q24h"},
            "adult": {"dose_mg": 100, "interval": "q24h"},
            "severity": "moderate",
            "source": "IDSA Candidiasis Guidelines",
        },
    },

    "invasive_aspergillosis": {
        "voriconazole": {
            "pediatric": {"dose_mg_kg": 9, "interval": "q12h", "loading_mg_kg": 9},
            "adult": {"dose_mg_kg": 4, "interval": "q12h", "loading_mg_kg": 6},
            "severity": "high",
            "source": "IDSA Aspergillosis Guidelines 2016",
            "note": "TDM required: target trough 1.0-5.5 mcg/mL",
            "tdm_required": True,
        },
    },

    # === Osteomyelitis ===
    "osteomyelitis": {
        "cefazolin": {
            "pediatric": {"dose_mg_kg_day": 100, "interval": "q8h", "max_daily_mg": 6000},
            "adult": {"dose_mg": 2000, "interval": "q8h"},
            "severity": "moderate",
            "source": "IDSA Osteomyelitis Guidelines",
            "note": "Higher dose than standard (25 mg/kg). Duration 4-6 weeks.",
        },
        "vancomycin": {
            "note": "Target AUC/MIC 400-600 for MRSA osteomyelitis",
            "severity": "moderate",
            "source": "IDSA MRSA Guidelines",
        },
    },

    # === Bacteremia (non-endocarditis) ===
    "bacteremia": {
        "daptomycin": {
            "adult": {"dose_mg_kg": 6, "interval": "q24h", "range_mg_kg": [6, 10]},
            "severity": "high",
            "source": "IDSA MRSA Guidelines (bacteremia: >= 6 mg/kg, consider 8-10)",
            "note": "Higher than skin/soft tissue dose (4 mg/kg)",
        },
    },

    # === Necrotizing Fasciitis ===
    "necrotizing_fasciitis": {
        "clindamycin": {
            "pediatric": {"dose_mg_kg_day": 40, "interval": "q8h", "max_daily_mg": 2700},
            "adult": {"dose_mg": 900, "interval": "q8h"},
            "severity": "high",
            "source": "IDSA Skin/Soft Tissue Guidelines 2014",
            "note": "Added for toxin suppression regardless of susceptibility",
        },
    },

    # === Pneumonia ===
    "pneumonia": {
        "piperacillin_tazobactam": {
            "adult": {"dose_mg": 4500, "interval": "q6h"},
            "severity": "moderate",
            "source": "ATS/IDSA HAP/VAP Guidelines 2016",
            "note": "Consider extended infusion (4h) for critically ill",
            "extended_infusion_candidate": True,
        },
        "meropenem": {
            "adult": {"dose_mg": 1000, "interval": "q8h"},
            "severity": "moderate",
            "source": "ATS/IDSA HAP/VAP Guidelines",
            "note": "Consider extended infusion (3h) for critically ill",
            "extended_infusion_candidate": True,
        },
    },

    # === UTI ===
    "uti": {
        "nitrofurantoin": {
            "route": "PO",
            "severity": "critical",
            "source": "IDSA UTI Guidelines",
            "note": "PO only. Not appropriate for pyelonephritis or bacteremia (no serum levels).",
            "contraindicated_if": ["bacteremia", "pyelonephritis"],
        },
    },
}
```

### Renal Adjustment Rules

```python
# dosing-verification/src/rules/renal_rules.py

RENAL_ADJUSTMENTS = {
    "vancomycin": {
        "method": "auc_based",  # AUC-based dosing, renal adjustment inherent
        "flag_if_no_level": True,
        "dialysis": {"dose_mg_kg": 25, "frequency": "per_level", "note": "Dose after HD, check levels"},
    },
    "meropenem": {
        "normal": {"dose_mg_kg": 20, "interval_h": 8},
        "gfr_26_50": {"dose_mg_kg": 20, "interval_h": 12},
        "gfr_10_25": {"dose_mg_kg": 10, "interval_h": 12},
        "gfr_lt_10": {"dose_mg_kg": 10, "interval_h": 24},
        "crrt": {"dose_mg_kg": 20, "interval_h": 8, "note": "Full dose on CRRT"},
    },
    "cefepime": {
        "normal": {"dose_mg": 2000, "interval_h": 8},
        "gfr_30_60": {"dose_mg": 2000, "interval_h": 12},
        "gfr_11_29": {"dose_mg": 1000, "interval_h": 12},
        "gfr_lt_11": {"dose_mg": 1000, "interval_h": 24},
        "note": "Neurotoxicity risk if not adjusted for renal function",
        "severity_if_not_adjusted": "critical",
    },
    "acyclovir": {
        "normal": {"interval_h": 8},
        "gfr_25_50": {"interval_h": 12},
        "gfr_10_25": {"interval_h": 24},
        "gfr_lt_10": {"dose_reduction": 0.5, "interval_h": 24},
    },
    "fluconazole": {
        "gfr_lt_50": {"dose_reduction": 0.5},
        "note": "50% dose reduction if CrCl < 50 (non-loading doses)",
    },
    "piperacillin_tazobactam": {
        "normal": {"dose_mg": 4500, "interval_h": 6},
        "gfr_20_40": {"dose_mg": 3375, "interval_h": 6},
        "gfr_lt_20": {"dose_mg": 2250, "interval_h": 6},
        "hd": {"dose_mg": 2250, "interval_h": 6, "note": "Extra dose after HD"},
    },
    "ciprofloxacin": {
        "gfr_lt_30": {"dose_reduction": 0.5},
    },
    "levofloxacin": {
        "gfr_20_49": {"dose_mg": 250, "interval_h": 24, "note": "After initial dose of 500mg"},
        "gfr_lt_20": {"dose_mg": 250, "interval_h": 48},
    },
    "gentamicin": {
        "method": "level_based",
        "flag_if_no_level": True,
        "extended_interval_cutoffs": {
            "gfr_gt_60": {"interval_h": 24},
            "gfr_40_60": {"interval_h": 36},
            "gfr_20_40": {"interval_h": 48},
            "gfr_lt_20": {"note": "Traditional dosing, check levels"},
        },
    },
    "tobramycin": {
        "method": "level_based",
        "flag_if_no_level": True,
        # Same as gentamicin
    },
}
```

### Drug-Drug Interaction Rules

```python
# dosing-verification/src/rules/interaction_rules.py

DRUG_INTERACTIONS = [
    {
        "antimicrobial": "linezolid",
        "interacting_classes": ["SSRI", "SNRI", "TCA", "MAOI", "tramadol", "meperidine", "buspirone"],
        "interacting_drugs": ["sertraline", "fluoxetine", "paroxetine", "citalopram", "escitalopram",
                              "venlafaxine", "duloxetine", "amitriptyline", "nortriptyline",
                              "tramadol", "meperidine", "buspirone", "fentanyl", "methadone"],
        "severity": "critical",
        "risk": "Serotonin syndrome",
        "recommendation": "Use alternative (vancomycin, daptomycin) or discontinue serotonergic agent if possible",
        "source": "FDA Black Box Warning",
    },
    {
        "antimicrobial": "metronidazole",
        "interacting_drugs": ["warfarin"],
        "severity": "high",
        "risk": "Potentiated anticoagulation (2-3x INR increase)",
        "recommendation": "Monitor INR closely, consider 25-50% warfarin dose reduction",
        "source": "Clinical pharmacology",
    },
    {
        "antimicrobial": "voriconazole",
        "interacting_drugs": ["sirolimus"],
        "severity": "critical",
        "risk": "Contraindicated combination. Sirolimus levels increase 10-fold",
        "recommendation": "Contraindicated. Switch antifungal or hold sirolimus",
        "source": "Voriconazole prescribing information",
    },
    {
        "antimicrobial": "voriconazole",
        "interacting_drugs": ["tacrolimus", "cyclosporine"],
        "severity": "high",
        "risk": "Calcineurin inhibitor levels increase 2-3x",
        "recommendation": "Reduce tacrolimus/cyclosporine by 50-66%, monitor levels closely",
        "source": "IDSA Aspergillosis Guidelines",
    },
    {
        "antimicrobial": "rifampin",
        "interacting_classes": ["calcineurin_inhibitor", "azole_antifungal", "anticoagulant",
                                "anticonvulsant", "protease_inhibitor", "hormonal_contraceptive"],
        "interacting_drugs": ["tacrolimus", "cyclosporine", "voriconazole", "itraconazole",
                              "posaconazole", "warfarin", "methadone", "phenytoin",
                              "carbamazepine", "dexamethasone", "midazolam"],
        "severity": "critical",
        "risk": "CYP3A4/2C9 induction reduces levels of interacting drugs by 50-90%",
        "recommendation": "Avoid combination if possible. If essential, increase interacting drug dose and monitor levels",
        "source": "Clinical pharmacology",
    },
    {
        "antimicrobial": "fluoroquinolone",
        "antimicrobial_drugs": ["ciprofloxacin", "levofloxacin", "moxifloxacin"],
        "interacting_classes": ["QT_prolonging"],
        "interacting_drugs": ["amiodarone", "sotalol", "dronedarone", "haloperidol",
                              "ondansetron", "methadone"],
        "severity": "high",
        "risk": "Additive QT prolongation, risk of torsades de pointes",
        "recommendation": "Obtain baseline ECG, monitor QTc, consider alternative antimicrobial",
        "source": "CredibleMeds QT drug list",
    },
    {
        "antimicrobial": "trimethoprim_sulfamethoxazole",
        "interacting_drugs": ["methotrexate"],
        "severity": "critical",
        "risk": "Increased methotrexate toxicity (pancytopenia)",
        "recommendation": "Avoid combination. If essential, monitor CBC and methotrexate levels",
        "source": "Clinical pharmacology",
    },
    {
        "antimicrobial": "trimethoprim_sulfamethoxazole",
        "interacting_drugs": ["warfarin"],
        "severity": "high",
        "risk": "Potentiated anticoagulation via CYP2C9 inhibition",
        "recommendation": "Monitor INR closely within 3-5 days of starting TMP-SMX",
        "source": "Clinical pharmacology",
    },
    {
        "antimicrobial": "daptomycin",
        "interacting_classes": ["statin"],
        "interacting_drugs": ["atorvastatin", "simvastatin", "rosuvastatin", "pravastatin"],
        "severity": "moderate",
        "risk": "Additive myotoxicity (elevated CK)",
        "recommendation": "Consider holding statin during daptomycin therapy, monitor CK weekly",
        "source": "Daptomycin prescribing information",
    },
]
```

### Contraindication / Route Rules

```python
# dosing-verification/src/rules/route_rules.py

ROUTE_RULES = [
    {
        "drug": "vancomycin",
        "indication": "c_difficile",
        "required_route": "PO",
        "forbidden_route": "IV",
        "severity": "critical",
        "message": "IV vancomycin does NOT reach the colon. C. difficile requires PO or rectal vancomycin.",
        "source": "IDSA/SHEA CDI Guidelines 2021",
    },
    {
        "drug": "nitrofurantoin",
        "contraindicated_indications": ["bacteremia", "pyelonephritis", "sepsis"],
        "severity": "critical",
        "message": "Nitrofurantoin achieves therapeutic levels only in urine. Not appropriate for systemic infections.",
        "source": "IDSA UTI Guidelines",
    },
    {
        "drug": "daptomycin",
        "contraindicated_indications": ["pneumonia"],
        "severity": "critical",
        "message": "Daptomycin is inactivated by pulmonary surfactant. Not effective for pneumonia.",
        "source": "Daptomycin prescribing information",
    },
    {
        "drug": "tigecycline",
        "contraindicated_indications": ["bacteremia"],
        "severity": "high",
        "message": "Tigecycline has poor serum levels. Not appropriate as sole agent for bacteremia.",
        "source": "FDA warning 2010, IDSA guidance",
    },
    {
        "drug": "ceftriaxone",
        "age_contraindication": {"max_days": 28, "condition": "hyperbilirubinemia"},
        "severity": "critical",
        "message": "Ceftriaxone contraindicated in neonates with hyperbilirubinemia (displaces bilirubin from albumin).",
        "source": "AAP/Pediatric guidelines",
    },
]
```

---

## FHIR Data Requirements

The monitor needs to fetch these data points per patient from FHIR:

| Data | FHIR Resource | Fields |
|------|--------------|--------|
| **Active medications** | MedicationRequest | medication, dosage (dose, frequency, route), status=active |
| **Weight** | Observation (vital-signs, 29463-7) | valueQuantity |
| **Height** | Observation (vital-signs, 8302-2) | valueQuantity |
| **Age** | Patient | birthDate |
| **Serum creatinine** | Observation (2160-0) | valueQuantity |
| **eGFR** | Observation (33914-3) | valueQuantity |
| **Allergies** | AllergyIntolerance | code, reaction.severity, criticality |
| **Co-medications** | MedicationRequest (status=active) | medication (all, not just antimicrobials) |
| **Dialysis status** | Procedure or Condition | code (HD/CRRT/PD procedure codes) |

The `DosingFHIRClient` extends the `DrugBugFHIRClient` pattern with additional methods:

```python
class DosingFHIRClient(DrugBugFHIRClient):
    """Extended FHIR client for dosing verification data."""

    def get_patient_weight(self, patient_id: str) -> float | None
    def get_patient_height(self, patient_id: str) -> float | None
    def get_serum_creatinine(self, patient_id: str) -> float | None
    def get_egfr(self, patient_id: str) -> float | None
    def get_all_active_medications(self, patient_id: str) -> list[MedicationOrder]
    def get_dialysis_status(self, patient_id: str) -> dict | None

    def build_patient_context(self, patient_id: str, indication: str = None) -> PatientContext:
        """Assemble complete PatientContext from FHIR for rules engine."""
        ...
```

---

## Monitor / Runner

```python
# dosing-verification/src/monitor.py

class DosingMonitor:
    """Main orchestrator: finds orders, evaluates dosing, generates alerts."""

    def __init__(self, config=None):
        self.fhir_client = DosingFHIRClient(config)
        self.rules_engine = DosingRulesEngine(config)
        self.store = DoseAlertStore()
        self.alert_store = AlertStore()  # For ASP alert integration
        self.email = EmailChannel(config)
        self.teams = TeamsWebhookChannel(config)

    def run_once(self):
        """Single pass: evaluate all active antimicrobial orders."""
        patients = self._get_patients_with_active_antimicrobials()
        for patient_id in patients:
            self._evaluate_patient(patient_id)

    def _evaluate_patient(self, patient_id: str):
        """Build context, run rules, generate alerts if needed."""
        # 1. Build PatientContext from FHIR
        context = self.fhir_client.build_patient_context(patient_id)

        # 2. Enrich with indication from ABX Indications module
        context.indication = self._get_indication(context.patient_mrn)

        # 3. Run rules engine
        assessment = self.rules_engine.evaluate(context)

        # 4. For each flag, check if already alerted, save new alerts
        for flag in assessment.flags:
            if not self.store.check_if_alerted(context.patient_mrn, flag.drug, flag.flag_type):
                alert = self._create_alert(context, flag, assessment)
                self.store.save_alert(alert)
                self._send_notifications(alert, flag)

    def _send_notifications(self, alert: DoseAlertRecord, flag: DoseFlag):
        """Send notifications based on severity tier."""
        if flag.severity == DoseAlertSeverity.CRITICAL:
            self._send_teams(alert, flag)
            self._send_email(alert, flag)
            self.store.mark_sent(alert.id)
        elif flag.severity == DoseAlertSeverity.HIGH:
            self._send_email(alert, flag)
            self.store.mark_sent(alert.id)
        # MODERATE: dashboard only, no notification
```

### Runner (CLI)

```python
# dosing-verification/src/runner.py

"""CLI entry point for dosing verification monitor.

Usage:
    python -m src.runner --once          # Single pass
    python -m src.runner --continuous     # Run every 15 minutes
    python -m src.runner --dry-run       # Evaluate but don't save/alert
    python -m src.runner --patient MRN   # Evaluate single patient
"""
```

---

## Dashboard Routes

Blueprint: `dosing_verification_bp` at `/dosing-verification`

### Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/` | redirect → `/active` | |
| `/active` | `dosing_dashboard.html` | Active dose alerts with filters |
| `/alert/<alert_id>` | `dosing_alert_detail.html` | Detail page with ASP review workflow |
| `/history` | `dosing_history.html` | Resolved alerts with filters |
| `/reports` | `dosing_reports.html` | Analytics dashboard |
| `/help` | `dosing_help.html` | Help/documentation |

### API Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/api/stats` | GET | Alert counts by status/severity |
| `/api/alerts` | GET | Active alerts (JSON) |
| `/api/<alert_id>/acknowledge` | POST | Acknowledge alert |
| `/api/<alert_id>/resolve` | POST | Resolve with reason |
| `/api/<alert_id>/note` | POST | Add note |

### CSV Export

| Route | Description |
|-------|-------------|
| `/export/active.csv` | Active alerts export |
| `/export/history.csv` | Resolved alerts export |

### Route Pattern

```python
# dashboard/routes/dosing_verification.py

dosing_verification_bp = Blueprint(
    "dosing_verification", __name__, url_prefix="/dosing-verification"
)

@dosing_verification_bp.route("/")
def index():
    return redirect(url_for("dosing_verification.active"))

@dosing_verification_bp.route("/active")
def active():
    """List active dosing alerts with filters."""
    severity = request.args.get("severity", "")
    flag_type = request.args.get("flag_type", "")
    drug = request.args.get("drug", "")

    store = DoseAlertStore()
    alerts = store.list_active(severity=severity or None, flag_type=flag_type or None, drug=drug or None)
    stats = store.get_stats()

    return render_template("dosing_dashboard.html",
        alerts=alerts,
        stats=stats,
        current_severity=severity,
        current_flag_type=flag_type,
        current_drug=drug,
        severity_options=[(s.value, s.value.title()) for s in DoseAlertSeverity],
        flag_type_options=[(f.value, f.value.replace("_", " ").title()) for f in DoseFlagType],
    )

@dosing_verification_bp.route("/alert/<alert_id>")
def alert_detail(alert_id):
    """Alert detail with full clinical context and ASP review."""
    store = DoseAlertStore()
    alert = store.get_alert(alert_id)
    if not alert:
        abort(404)

    audit_log = store.get_audit_log(alert_id)
    patient_factors = json.loads(alert.patient_factors) if alert.patient_factors else {}
    assessment = json.loads(alert.assessment_details) if alert.assessment_details else {}

    # Log view activity
    try:
        MetricsStore().log_activity(
            provider_id=get_current_user().get("id", "unknown"),
            activity_type=ActivityType.REVIEW,
            module=ModuleSource.DOSING_VERIFICATION,
            entity_id=alert_id,
            entity_type="dose_alert",
            action_taken="viewed",
            patient_mrn=alert.patient_mrn,
        )
    except Exception:
        pass

    return render_template("dosing_alert_detail.html",
        alert=alert,
        patient_factors=patient_factors,
        assessment=assessment,
        audit_log=audit_log,
        resolution_options=DoseResolution.all_options(),
    )
```

---

## Template Structure

### dosing_dashboard.html (Active Alerts)

Uses harmonized components: `stat_card_row`, `stat_card`, `filter_bar`, `filter_select`, `data_table`.

```
┌─────────────────────────────────────────────────────────┐
│ Dosing Verification                     [History] [Reports] │
├─────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │ Active   │ │ Critical │ │ High     │ │ Resolved │   │
│ │ 12       │ │ 3        │ │ 5        │ │ Today: 4 │   │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│                                                         │
│ Filters: [Severity ▼] [Flag Type ▼] [Drug ▼]          │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Severity │ Patient │ Drug │ Issue │ Expected │ Time │ │
│ │──────────│─────────│──────│───────│──────────│──────│ │
│ │ CRITICAL │ MRN123  │ Vanc │ Wrong │ PO 125mg │ 2m  │ │
│ │          │ J. Doe  │      │ Route │ q6h      │ ago │ │
│ │ HIGH     │ MRN456  │ Mero │ No    │ 10mg/kg  │ 15m │ │
│ │          │ S. Smith│      │ Renal │ q12h     │ ago │ │
│ │          │         │      │ Adj.  │          │     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### dosing_alert_detail.html (Review Page)

Uses harmonized components: `detail_page`, `detail_sidebar`, `detail_main`, `detail_sidebar_section`, `detail_main_section`, `detail_field`, `detail_field_badge`, `detail_status_bar`, `detail_action_bar`, `detail_timeline`.

```
┌─────────────────────────────────────────────────────────┐
│ Dosing Alert: DA-ABC123                    [Back to List] │
├─────────────────────────────────────────────────────────┤
│ [CRITICAL] [PENDING] [Subtherapeutic Dose]              │
├────────────────────────┬────────────────────────────────┤
│ Patient Information    │ Dosing Issue                    │
│ ─────────────────────  │ ──────────────────────          │
│ Patient MRN: 12345     │ Drug: Ceftriaxone               │
│ Name: John Doe         │ Indication: Meningitis          │
│ Age: 4.2 years         │                                 │
│ Weight: 18.5 kg        │ Current Order:                  │
│                        │   50 mg/kg/day q24h IV          │
│ Renal Function         │                                 │
│ ─────────────────────  │ Expected for Meningitis:        │
│ SCr: 0.4 mg/dL         │   100 mg/kg/day divided q12h IV│
│ eGFR: > 90             │                                 │
│ Dialysis: No           │ Rule Source:                    │
│                        │   IDSA Meningitis Guidelines    │
│ Current Antimicrobials │                                 │
│ ─────────────────────  │ Note: BBB penetration requires  │
│ Ceftriaxone 450mg q24h │ higher serum levels. Standard   │
│ Vancomycin 270mg q6h   │ dose is subtherapeutic for CNS. │
│                        │                                 │
│ Co-Medications         │ ────────────────────────────────│
│ ─────────────────────  │ All Flags in Assessment         │
│ Levetiracetam          │ ──────────────────────          │
│ Dexamethasone          │ ✗ Ceftriaxone: Subtherapeutic  │
│                        │   (CRITICAL)                    │
│ Allergies              │ ✓ Vancomycin: Meningitis dose   │
│ ─────────────────────  │   appropriate (60 mg/kg/day)    │
│ None documented        │                                 │
│                        │ ────────────────────────────────│
│                        │ Audit Log                       │
│                        │ ──────────────────────          │
│                        │ 14:32 - Alert created           │
│                        │ 14:32 - Teams notification sent │
│                        │ 14:32 - Email sent              │
├────────────────────────┴────────────────────────────────┤
│ [Acknowledge] [Resolve ▼] [Add Note]                    │
│                                                         │
│ Resolution: [Dose Adjusted        ▼]                    │
│ Notes: [________________________________]               │
│        [Submit Resolution]                              │
└─────────────────────────────────────────────────────────┘
```

### dosing_reports.html (Analytics)

Uses harmonized components: `stat_card_row`, `filter_days`, `data_table`.

- Stat cards: Total alerts, Resolution rate, Avg response time, Most common flag
- Alert volume by severity (30-day trend)
- Top flagged drugs table
- Top flag types table
- Resolution breakdown
- Acceptance rate (% where dose was actually changed)

---

## Integration Points

### 1. ABX Indications Module → Dosing Verification

The Dosing Verification monitor queries the ABX Indications database for the extracted indication:

```python
def _get_indication(self, patient_mrn: str) -> str | None:
    """Get most recent indication extraction for this patient."""
    from au_alerts_src.indication_db import IndicationDatabase
    ind_db = IndicationDatabase()
    candidates = ind_db.get_candidates_by_mrn(patient_mrn, status="accepted", limit=1)
    if candidates:
        return candidates[0].primary_indication
    return None
```

If no indication is available, the engine still evaluates renal, weight, age, and DDI rules (which don't require an indication). Indication-specific rules are skipped with a note that indication was not available.

### 2. Dosing Verification → AlertStore (ASP Alerts)

Critical and high severity dose alerts are also saved to the main AlertStore with type `DOSING_ALERT`, making them visible in the ASP Alerts queue alongside bacteremia and drug-bug alerts:

```python
from common.alert_store import AlertStore, AlertType

alert_store = AlertStore()
alert_store.save_alert(
    alert_type=AlertType.DOSING_ALERT,
    source_id=f"dose-{assessment_id}-{flag.flag_type}",
    severity="critical",
    patient_id=context.patient_id,
    patient_mrn=context.patient_mrn,
    patient_name=context.patient_name,
    title=f"Dosing Alert: {flag.drug} - {flag.message}",
    summary=f"{flag.drug}: {flag.actual} → {flag.expected}",
    content=flag.to_dict(),
)
```

This means dose alerts appear in both:
- The dedicated Dosing Verification dashboard (with full dosing context)
- The ASP Alerts active queue (for pharmacists who review all alert types together)

### 3. MetricsStore Activity Logging

All actions logged with `ModuleSource.DOSING_VERIFICATION`:

```python
MetricsStore().log_activity(
    provider_id=user_id,
    activity_type=ActivityType.REVIEW,      # or ACKNOWLEDGMENT, RESOLUTION, etc.
    module=ModuleSource.DOSING_VERIFICATION,
    entity_id=alert_id,
    entity_type="dose_alert",
    action_taken="resolved",
    outcome=resolution,
    patient_mrn=patient_mrn,
    location_code=location,
)
```

### 4. Notification Channels

```python
# Critical: Teams + Email
teams.send(TeamsMessage(
    title="DOSING ALERT: Ceftriaxone - Subtherapeutic for Meningitis",
    text="Patient MRN 12345 - Current: 50 mg/kg/day q24h, Expected: 100 mg/kg/day q12h",
    facts={"Drug": "Ceftriaxone", "Issue": "Subtherapeutic", "Indication": "Meningitis"},
    actions=build_teams_actions(alert_id, base_url),
))

# High: Email only
email.send(EmailMessage(
    to=asp_team_email,
    subject=f"[AEGIS] Dosing Alert - {drug} - {patient_name}",
    html=render_dosing_email(alert),
))
```

---

## Phased Implementation

### Phase 1: Core Engine + Store + Dashboard (MVP)

**Goal:** End-to-end dosing evaluation with dashboard review workflow.

1. **Data model** — `common/dosing_verification/` (models.py, store.py, schema.sql)
2. **Rules engine skeleton** — `dosing-verification/src/rules_engine.py` with `PatientContext` and `BaseRuleModule`
3. **Indication rules** — Meningitis, endocarditis, CDI, candidemia (highest clinical impact)
4. **Route rules** — IV vancomycin for CDI, nitrofurantoin for bacteremia, daptomycin for pneumonia
5. **DoseAlertStore** — CRUD, status transitions, audit log
6. **Dashboard routes** — Active list, detail page with review workflow, history
7. **Templates** — Using harmonized components (detail_layout, stat_cards, filters, data_tables, status_badges, action_buttons)
8. **App integration** — Register blueprint, add nav, add landing card, add about entry
9. **Demo data** — Script to generate sample dose alerts for testing

### Phase 2: Patient Factor Rules + FHIR Integration

**Goal:** Renal, weight, and age-based dosing checks with live FHIR data.

1. **Renal adjustment rules** — Full table for 15+ antimicrobials
2. **Weight-based rules** — Obesity dosing, pediatric weight calculations, max dose caps
3. **Age-based rules** — Neonatal vs pediatric vs adult dosing tables
4. **FHIR client** — DosingFHIRClient with weight, height, SCr, eGFR, dialysis status fetching
5. **Monitor** — `DosingMonitor.run_once()` with FHIR data assembly
6. **Runner CLI** — `--once`, `--continuous`, `--dry-run`, `--patient`

### Phase 3: DDI + Notifications + Analytics

**Goal:** Drug interaction detection, real-time alerting, and operational analytics.

1. **Drug interaction rules** — Full DDI table (linezolid, rifampin, voriconazole, FQs, etc.)
2. **Duration rules** — Flag short/long courses based on indication
3. **Extended infusion rules** — Identify candidates for pip-tazo, meropenem extended infusion
4. **Teams + Email notifications** — Tiered by severity
5. **ASP Alert integration** — Critical/high flags pushed to AlertStore for ASP queue visibility
6. **Analytics dashboard** — Reports page with resolution rates, top drugs, top flags, trends
7. **CSV export** — Active and history exports for committee presentations
8. **ABX Indications integration** — Pull indication from indication database automatically
9. **Help page** — Documentation with rule sources and clinical references

### Phase 4: Advanced Features

**Goal:** Refinement and edge cases.

1. **TDM integration** — Flag when vancomycin/aminoglycoside levels are due but not ordered
2. **Allergy cross-reactivity** — Penicillin allergy → cephalosporin safety assessment
3. **CRRT dosing** — Specialized rules for continuous renal replacement therapy
4. **Auto-acceptance** — Auto-accept moderate alerts after configurable timeout
5. **Cron scheduling** — Periodic re-evaluation (new labs may change renal status)
6. **Validation framework** — Gold standard cases for rules engine accuracy testing

---

## Testing Strategy

### Unit Tests

- Rules engine: Each rule module tested independently with mock `PatientContext`
- Store: CRUD operations, status transitions, analytics queries
- FHIR client: Mock FHIR responses for data parsing

### Integration Tests

- End-to-end: Mock FHIR server → Monitor → Rules → Store → Dashboard render
- Notification: Mock Teams/Email channels verify correct routing by severity

### Clinical Validation Cases

Build gold standard test cases for each rule category:

| Category | Example Test Case | Expected Flag |
|----------|------------------|---------------|
| CNS dosing | Meningitis + ceftriaxone 50 mg/kg q24h | SUBTHERAPEUTIC_DOSE (critical) |
| Route | CDI + IV vancomycin | WRONG_ROUTE (critical) |
| Renal | CrCl 20 + full-dose meropenem | NO_RENAL_ADJUSTMENT (high) |
| DDI | Linezolid + sertraline | DRUG_INTERACTION (critical) |
| Peds | Neonate + ceftriaxone + elevated bilirubin | CONTRAINDICATED (critical) |
| Duration | UTI + 14 days ciprofloxacin | DURATION_EXCESSIVE (moderate) |

---

## Configuration

```ini
# .env for dosing-verification module

FHIR_BASE_URL=http://localhost:8080/fhir
DOSE_ALERT_DB_PATH=~/.aegis/dose_alerts.db
ALERT_DB_PATH=~/.aegis/alerts.db

# Notification channels
SMTP_SERVER=smtp.example.com
SMTP_FROM=aegis@example.com
ASP_TEAM_EMAIL=asp-team@example.com
TEAMS_WEBHOOK_URL=https://...

# Monitor settings
MONITOR_INTERVAL_MINUTES=15
DRY_RUN=false
AUTO_ACCEPT_HOURS=72

# Dashboard
DASHBOARD_BASE_URL=https://aegis-asp.com
```
