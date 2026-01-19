# AEGIS Implementation Plan

## Comprehensive Specification for Additional HAI Types and AU/AR Reporting

**Version:** 1.0  
**Target System:** AEGIS (Automated Evaluation and Guidance for Infection Surveillance)  
**Implementation Tool:** Claude CLI

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Overview](#2-current-architecture-overview)
3. [Phase 1: Infrastructure Enhancements](#3-phase-1-infrastructure-enhancements)
4. [Phase 2: CAUTI Detection Module](#4-phase-2-cauti-detection-module)
5. [Phase 3: VAE Detection Module](#5-phase-3-vae-detection-module)
6. [Phase 4: SSI Detection Module](#6-phase-4-ssi-detection-module)
7. [Phase 5: Antibiotic Usage (AU) Reporting](#7-phase-5-antibiotic-usage-au-reporting)
8. [Phase 6: Antimicrobial Resistance (AR) Reporting](#8-phase-6-antimicrobial-resistance-ar-reporting)
9. [Phase 7: Dashboard Enhancements](#9-phase-7-dashboard-enhancements)
10. [Implementation Checklist](#10-implementation-checklist)
11. [Testing Strategy](#11-testing-strategy)

---

## 1. Executive Summary

### Scope

This document provides implementation specifications for expanding AEGIS to include:

1. **Additional HAI Types:**
   - CAUTI (Catheter-Associated Urinary Tract Infection)
   - VAE (Ventilator-Associated Events)
   - SSI (Surgical Site Infection)

2. **NHSN Reporting Modules:**
   - AU (Antibiotic Usage) - Monthly reporting of antimicrobial consumption
   - AR (Antimicrobial Resistance) - Quarterly reporting of resistance patterns

### Architecture Principle

Maintain the proven CLABSI architecture: **LLM extracts FACTS, rules engine applies LOGIC**

```
Data Sources → Rule-Based Screening → LLM Extraction → Rules Engine → IP Review → NHSN Submission
```

### Priority Order

1. **High Priority:** CAUTI (similar architecture to CLABSI, shared infrastructure)
2. **High Priority:** AU Reporting (CMS requirement, monthly cadence)
3. **Medium Priority:** VAE (more complex criteria, ventilator-specific)
4. **Medium Priority:** AR Reporting (builds on AU data)
5. **Lower Priority:** SSI (requires surgical procedure tracking, complex timing)

---

## 2. Current Architecture Overview

### Existing CLABSI Pipeline

```
nhsn-reporting/src/
├── candidates/
│   └── clabsi.py              # Rule-based screening
├── extraction/
│   └── clabsi_extractor.py    # LLM fact extraction
├── rules/
│   ├── schemas.py             # ClinicalExtraction dataclass
│   ├── nhsn_criteria.py       # Reference data
│   └── clabsi_engine.py       # NHSN decision tree
├── classifiers/
│   └── clabsi_classifier_v2.py # Orchestration
└── data/
    ├── fhir_source.py         # FHIR queries
    ├── clarity_source.py      # Clarity SQL
    └── denominator.py         # Device days
```

### Key Abstractions to Reuse

1. **BaseCandidateDetector** - Abstract base for rule-based screening
2. **BaseHAIClassifier** - Abstract base for classification orchestration
3. **BaseLLMClient** - Ollama/Claude abstraction
4. **NHSNDatabase** - SQLite operations (extend schema)
5. **IP Review Workflow** - Dashboard integration

---

## 3. Phase 1: Infrastructure Enhancements

### 3.1 Database Schema Extensions

**File:** `nhsn-reporting/schema.sql`

Add tables for new HAI types and AU/AR reporting:

```sql
-- ============================================================
-- CAUTI Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS cauti_candidates (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    mrn TEXT,
    patient_name TEXT,
    urine_culture_id TEXT NOT NULL,
    urine_culture_date TEXT NOT NULL,
    organism TEXT NOT NULL,
    cfu_count INTEGER,  -- Colony forming units (≥100,000 threshold)
    catheter_device_id TEXT,
    catheter_type TEXT,  -- Indwelling, condom, suprapubic
    catheter_start_date TEXT,
    catheter_end_date TEXT,
    catheter_days INTEGER,
    location TEXT,
    detected_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, classified, reviewed, submitted
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS cauti_classifications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    classification TEXT NOT NULL,  -- CAUTI, ASYMPTOMATIC_BACTERIURIA, NOT_ELIGIBLE, SECONDARY
    confidence REAL,
    reasoning TEXT,
    extracted_data TEXT,  -- JSON: symptoms, alternate sources
    rule_trace TEXT,      -- JSON: which rules fired
    classified_at TEXT NOT NULL,
    llm_model TEXT,
    prompt_version TEXT,
    FOREIGN KEY (candidate_id) REFERENCES cauti_candidates(id)
);

CREATE TABLE IF NOT EXISTS cauti_reviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    classification_id TEXT,
    reviewer TEXT,
    decision TEXT NOT NULL,  -- confirmed, not_cauti, needs_more_info
    override_reason TEXT,
    notes TEXT,
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES cauti_candidates(id),
    FOREIGN KEY (classification_id) REFERENCES cauti_classifications(id)
);

-- ============================================================
-- VAE Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS vae_candidates (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    mrn TEXT,
    patient_name TEXT,
    ventilator_start_date TEXT NOT NULL,
    ventilator_end_date TEXT,
    baseline_peep REAL,
    baseline_fio2 REAL,
    event_date TEXT NOT NULL,  -- Date of deterioration
    event_type TEXT,  -- VAC, IVAC, PVAP
    location TEXT,
    detected_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS vae_daily_assessments (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    assessment_date TEXT NOT NULL,
    peep REAL,
    fio2 REAL,
    temperature REAL,
    wbc_count REAL,
    new_antibiotic INTEGER,  -- Boolean: started new antimicrobial
    purulent_secretions INTEGER,  -- Boolean
    positive_culture INTEGER,  -- Boolean
    FOREIGN KEY (candidate_id) REFERENCES vae_candidates(id)
);

CREATE TABLE IF NOT EXISTS vae_classifications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    classification TEXT NOT NULL,  -- VAC, IVAC, PVAP, NOT_VAE
    confidence REAL,
    reasoning TEXT,
    extracted_data TEXT,
    rule_trace TEXT,
    classified_at TEXT NOT NULL,
    llm_model TEXT,
    prompt_version TEXT,
    FOREIGN KEY (candidate_id) REFERENCES vae_candidates(id)
);

CREATE TABLE IF NOT EXISTS vae_reviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    classification_id TEXT,
    reviewer TEXT,
    decision TEXT NOT NULL,
    override_reason TEXT,
    notes TEXT,
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES vae_candidates(id)
);

-- ============================================================
-- SSI Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS ssi_procedures (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    mrn TEXT,
    procedure_code TEXT NOT NULL,  -- ICD-10-PCS or CPT
    procedure_category TEXT NOT NULL,  -- NHSN procedure category (COLO, HYST, etc.)
    procedure_date TEXT NOT NULL,
    surgeon_id TEXT,
    asa_score INTEGER,  -- ASA physical status
    wound_class TEXT,  -- Clean, Clean-contaminated, Contaminated, Dirty
    duration_minutes INTEGER,
    endoscopic INTEGER,  -- Boolean
    emergency INTEGER,  -- Boolean
    implant INTEGER,  -- Boolean: prosthetic device placed
    location TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS ssi_candidates (
    id TEXT PRIMARY KEY,
    procedure_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    encounter_id TEXT,  -- May be different encounter for post-discharge SSI
    mrn TEXT,
    patient_name TEXT,
    infection_date TEXT NOT NULL,
    days_post_op INTEGER,
    ssi_level TEXT,  -- Superficial, Deep, Organ/Space
    culture_id TEXT,
    organism TEXT,
    location TEXT,
    detected_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (procedure_id) REFERENCES ssi_procedures(id),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS ssi_classifications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    classification TEXT NOT NULL,  -- SUPERFICIAL_SSI, DEEP_SSI, ORGAN_SPACE_SSI, NOT_SSI
    confidence REAL,
    reasoning TEXT,
    extracted_data TEXT,
    rule_trace TEXT,
    classified_at TEXT NOT NULL,
    llm_model TEXT,
    prompt_version TEXT,
    FOREIGN KEY (candidate_id) REFERENCES ssi_candidates(id)
);

CREATE TABLE IF NOT EXISTS ssi_reviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    classification_id TEXT,
    reviewer TEXT,
    decision TEXT NOT NULL,
    override_reason TEXT,
    notes TEXT,
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES ssi_candidates(id)
);

-- ============================================================
-- Antibiotic Usage (AU) Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS au_monthly_summary (
    id TEXT PRIMARY KEY,
    reporting_month TEXT NOT NULL,  -- YYYY-MM format
    location TEXT NOT NULL,  -- NHSN location code
    location_type TEXT,  -- ICU, Ward, NICU, etc.
    patient_days INTEGER NOT NULL,
    admissions INTEGER,
    created_at TEXT NOT NULL,
    submitted_at TEXT,
    UNIQUE(reporting_month, location)
);

CREATE TABLE IF NOT EXISTS au_antimicrobial_usage (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL,
    antimicrobial_code TEXT NOT NULL,  -- NHSN antimicrobial code
    antimicrobial_name TEXT NOT NULL,
    route TEXT NOT NULL,  -- IV, PO, IM
    days_of_therapy INTEGER NOT NULL,  -- DOT
    defined_daily_doses REAL,  -- DDD (optional)
    doses_administered INTEGER,
    FOREIGN KEY (summary_id) REFERENCES au_monthly_summary(id)
);

CREATE TABLE IF NOT EXISTS au_patient_level (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    mrn TEXT,
    antimicrobial_code TEXT NOT NULL,
    antimicrobial_name TEXT NOT NULL,
    route TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    total_doses INTEGER,
    location TEXT,
    indication TEXT,  -- Optional: documented indication
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

-- ============================================================
-- Antimicrobial Resistance (AR) Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS ar_quarterly_summary (
    id TEXT PRIMARY KEY,
    reporting_quarter TEXT NOT NULL,  -- YYYY-Q# format
    location TEXT NOT NULL,
    location_type TEXT,
    created_at TEXT NOT NULL,
    submitted_at TEXT,
    UNIQUE(reporting_quarter, location)
);

CREATE TABLE IF NOT EXISTS ar_isolates (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    mrn TEXT,
    specimen_date TEXT NOT NULL,
    specimen_type TEXT NOT NULL,  -- Blood, Urine, Respiratory, etc.
    organism_code TEXT NOT NULL,
    organism_name TEXT NOT NULL,
    location TEXT,
    is_duplicate INTEGER DEFAULT 0,  -- First isolate per patient per quarter
    FOREIGN KEY (summary_id) REFERENCES ar_quarterly_summary(id)
);

CREATE TABLE IF NOT EXISTS ar_susceptibilities (
    id TEXT PRIMARY KEY,
    isolate_id TEXT NOT NULL,
    antimicrobial_code TEXT NOT NULL,
    antimicrobial_name TEXT NOT NULL,
    interpretation TEXT NOT NULL,  -- S, I, R, NS (non-susceptible)
    mic_value TEXT,  -- MIC if available
    disk_zone INTEGER,  -- Disk diffusion zone if available
    testing_method TEXT,  -- MIC, Disk, Vitek, etc.
    FOREIGN KEY (isolate_id) REFERENCES ar_isolates(id)
);

CREATE TABLE IF NOT EXISTS ar_phenotype_summary (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL,
    organism_code TEXT NOT NULL,
    organism_name TEXT NOT NULL,
    phenotype TEXT NOT NULL,  -- MRSA, VRE, ESBL, CRE, etc.
    isolate_count INTEGER NOT NULL,
    percent_resistant REAL,
    FOREIGN KEY (summary_id) REFERENCES ar_quarterly_summary(id)
);

-- ============================================================
-- Denominator Tables (Shared)
-- ============================================================

CREATE TABLE IF NOT EXISTS denominators_daily (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    location TEXT NOT NULL,
    location_type TEXT,
    patient_days INTEGER DEFAULT 0,
    central_line_days INTEGER DEFAULT 0,
    urinary_catheter_days INTEGER DEFAULT 0,
    ventilator_days INTEGER DEFAULT 0,
    admissions INTEGER DEFAULT 0,
    UNIQUE(date, location)
);

CREATE TABLE IF NOT EXISTS denominators_monthly (
    id TEXT PRIMARY KEY,
    month TEXT NOT NULL,  -- YYYY-MM
    location TEXT NOT NULL,
    location_type TEXT,
    patient_days INTEGER DEFAULT 0,
    central_line_days INTEGER DEFAULT 0,
    urinary_catheter_days INTEGER DEFAULT 0,
    ventilator_days INTEGER DEFAULT 0,
    admissions INTEGER DEFAULT 0,
    procedures INTEGER DEFAULT 0,
    UNIQUE(month, location)
);
```

### 3.2 Shared Models

**File:** `nhsn-reporting/src/models.py`

Extend with new dataclasses:

```python
"""
Domain models for NHSN HAI reporting.

Add these to the existing models.py file.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum


# ============================================================
# Enums for HAI Types
# ============================================================

class HAIType(Enum):
    CLABSI = "clabsi"
    CAUTI = "cauti"
    VAE = "vae"
    SSI = "ssi"


class CAUTIClassification(Enum):
    CAUTI = "CAUTI"
    ASYMPTOMATIC_BACTERIURIA = "ASYMPTOMATIC_BACTERIURIA"
    SECONDARY_UTI = "SECONDARY_UTI"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class VAEClassification(Enum):
    VAC = "VAC"  # Ventilator-Associated Condition
    IVAC = "IVAC"  # Infection-related VAC
    PVAP = "PVAP"  # Possible VAP
    NOT_VAE = "NOT_VAE"


class SSIClassification(Enum):
    SUPERFICIAL_INCISIONAL = "SUPERFICIAL_INCISIONAL"
    DEEP_INCISIONAL = "DEEP_INCISIONAL"
    ORGAN_SPACE = "ORGAN_SPACE"
    NOT_SSI = "NOT_SSI"


# ============================================================
# CAUTI Models
# ============================================================

@dataclass
class CAUTICandidate:
    """Candidate for CAUTI evaluation."""
    id: str
    patient_id: str
    encounter_id: str
    mrn: Optional[str]
    patient_name: Optional[str]
    urine_culture_id: str
    urine_culture_date: datetime
    organism: str
    cfu_count: Optional[int]  # Colony forming units
    catheter_device_id: Optional[str]
    catheter_type: Optional[str]  # Indwelling, condom, suprapubic
    catheter_start_date: Optional[datetime]
    catheter_end_date: Optional[datetime]
    catheter_days: Optional[int]
    location: Optional[str]
    detected_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"


@dataclass
class CAUTIExtraction:
    """LLM-extracted clinical facts for CAUTI classification."""
    # Urinary symptoms (at least 1 required for CAUTI)
    fever: bool = False  # >38.0°C
    suprapubic_tenderness: bool = False
    costovertebral_angle_pain: bool = False
    urinary_urgency: bool = False
    urinary_frequency: bool = False
    dysuria: bool = False
    
    # Alternate explanations
    alternate_uti_source: bool = False  # Pyelonephritis from other cause
    recent_urologic_procedure: bool = False
    
    # Catheter assessment
    catheter_documented: bool = False
    catheter_days_documented: Optional[int] = None
    catheter_removed_before_culture: bool = False
    
    # Documentation quality
    documentation_quality: str = "adequate"
    evidence_sources: List[str] = field(default_factory=list)


# ============================================================
# VAE Models
# ============================================================

@dataclass
class VAECandidate:
    """Candidate for VAE evaluation."""
    id: str
    patient_id: str
    encounter_id: str
    mrn: Optional[str]
    patient_name: Optional[str]
    ventilator_start_date: datetime
    ventilator_end_date: Optional[datetime]
    baseline_peep: Optional[float]
    baseline_fio2: Optional[float]
    event_date: datetime  # Date of deterioration
    event_type: Optional[str]
    location: Optional[str]
    detected_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"


@dataclass
class VAEDailyAssessment:
    """Daily ventilator parameters for VAE detection."""
    date: date
    peep: Optional[float]
    fio2: Optional[float]
    temperature: Optional[float]
    wbc_count: Optional[float]
    new_antibiotic: bool = False
    purulent_secretions: bool = False
    positive_culture: bool = False


@dataclass
class VAEExtraction:
    """LLM-extracted clinical facts for VAE classification."""
    # VAC criteria (oxygenation deterioration after stability)
    sustained_peep_increase: bool = False  # ≥3 cmH2O increase for ≥2 days
    sustained_fio2_increase: bool = False  # ≥20 point increase for ≥2 days
    baseline_period_stable: bool = False  # 2+ days of stable/improving settings
    
    # IVAC criteria (infection-related)
    temperature_abnormal: bool = False  # >38°C or <36°C
    wbc_abnormal: bool = False  # >12,000 or <4,000
    new_antimicrobial_started: bool = False  # ≥4 days of new agent
    
    # PVAP criteria (possible pneumonia)
    purulent_secretions: bool = False
    positive_respiratory_culture: bool = False
    positive_lung_histopathology: bool = False
    positive_legionella_test: bool = False
    positive_respiratory_virus: bool = False
    
    # Documentation
    ventilator_days: Optional[int] = None
    documentation_quality: str = "adequate"
    evidence_sources: List[str] = field(default_factory=list)


# ============================================================
# SSI Models
# ============================================================

@dataclass
class SSIProcedure:
    """Surgical procedure being monitored for SSI."""
    id: str
    patient_id: str
    encounter_id: str
    mrn: Optional[str]
    procedure_code: str  # ICD-10-PCS or CPT
    procedure_category: str  # NHSN category (COLO, HYST, CRAN, etc.)
    procedure_date: datetime
    surgeon_id: Optional[str]
    asa_score: Optional[int]  # ASA physical status 1-5
    wound_class: Optional[str]  # Clean, Clean-contaminated, Contaminated, Dirty
    duration_minutes: Optional[int]
    endoscopic: bool = False
    emergency: bool = False
    implant: bool = False  # Prosthetic device placed
    location: Optional[str] = None


@dataclass
class SSICandidate:
    """Candidate for SSI evaluation."""
    id: str
    procedure_id: str
    patient_id: str
    encounter_id: Optional[str]  # May be different encounter for post-discharge
    mrn: Optional[str]
    patient_name: Optional[str]
    infection_date: datetime
    days_post_op: int
    ssi_level: Optional[str]  # Superficial, Deep, Organ/Space
    culture_id: Optional[str]
    organism: Optional[str]
    location: Optional[str]
    detected_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"


@dataclass
class SSIExtraction:
    """LLM-extracted clinical facts for SSI classification."""
    # Superficial incisional criteria
    purulent_drainage_superficial: bool = False
    wound_opened_by_surgeon: bool = False
    pain_or_tenderness: bool = False
    localized_swelling: bool = False
    erythema: bool = False
    heat: bool = False
    superficial_culture_positive: bool = False
    
    # Deep incisional criteria
    purulent_drainage_deep: bool = False
    deep_incision_dehiscence: bool = False
    abscess_at_deep_incision: bool = False
    
    # Organ/space criteria
    purulent_drainage_from_drain: bool = False
    organ_space_culture_positive: bool = False
    abscess_identified: bool = False
    
    # General
    fever: bool = False  # >38°C
    diagnosed_by_surgeon: bool = False
    reoperation_required: bool = False
    
    # Documentation
    documentation_quality: str = "adequate"
    evidence_sources: List[str] = field(default_factory=list)


# ============================================================
# AU/AR Models
# ============================================================

@dataclass
class AntimicrobialAdministration:
    """Single antimicrobial administration record."""
    patient_id: str
    encounter_id: str
    mrn: Optional[str]
    antimicrobial_code: str
    antimicrobial_name: str
    route: str  # IV, PO, IM
    dose: Optional[str]
    administration_datetime: datetime
    location: str
    indication: Optional[str] = None


@dataclass
class AUMonthlySummary:
    """Monthly antibiotic usage summary for NHSN AU reporting."""
    id: str
    reporting_month: str  # YYYY-MM
    location: str
    location_type: str
    patient_days: int
    admissions: int
    antimicrobial_usage: List['AntimicrobialUsage'] = field(default_factory=list)


@dataclass
class AntimicrobialUsage:
    """Usage data for a single antimicrobial in a location/month."""
    antimicrobial_code: str
    antimicrobial_name: str
    route: str
    days_of_therapy: int  # DOT
    defined_daily_doses: Optional[float] = None  # DDD
    doses_administered: Optional[int] = None


@dataclass
class ARQuarterlySummary:
    """Quarterly antimicrobial resistance summary for NHSN AR reporting."""
    id: str
    reporting_quarter: str  # YYYY-Q#
    location: str
    location_type: str
    isolates: List['ARIsolate'] = field(default_factory=list)
    phenotype_summaries: List['ARPhenotypeSummary'] = field(default_factory=list)


@dataclass
class ARIsolate:
    """Single isolate for AR reporting."""
    id: str
    patient_id: str
    encounter_id: str
    mrn: Optional[str]
    specimen_date: datetime
    specimen_type: str
    organism_code: str
    organism_name: str
    location: str
    susceptibilities: List['Susceptibility'] = field(default_factory=list)
    is_first_isolate: bool = True  # First per patient per quarter


@dataclass
class Susceptibility:
    """Susceptibility result for an isolate."""
    antimicrobial_code: str
    antimicrobial_name: str
    interpretation: str  # S, I, R, NS
    mic_value: Optional[str] = None
    disk_zone: Optional[int] = None
    testing_method: Optional[str] = None


@dataclass
class ARPhenotypeSummary:
    """Summary of resistance phenotype (e.g., MRSA, VRE, CRE)."""
    organism_code: str
    organism_name: str
    phenotype: str  # MRSA, VRE, ESBL, CRE, etc.
    isolate_count: int
    percent_resistant: float
```

### 3.3 Abstract Base Classes

**File:** `nhsn-reporting/src/candidates/base.py`

```python
"""
Abstract base classes for HAI candidate detection.

Extend BaseCandidateDetector for each HAI type.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..models import HAIType


class BaseCandidateDetector(ABC):
    """Abstract base for rule-based HAI candidate screening."""
    
    def __init__(self, data_source, config: Optional[Dict[str, Any]] = None):
        """
        Initialize detector.
        
        Args:
            data_source: FHIR or Clarity data source
            config: Optional configuration overrides
        """
        self.data_source = data_source
        self.config = config or {}
    
    @property
    @abstractmethod
    def hai_type(self) -> HAIType:
        """Return the HAI type this detector handles."""
        pass
    
    @property
    @abstractmethod
    def min_device_days(self) -> int:
        """Minimum device days for eligibility."""
        pass
    
    @property
    @abstractmethod
    def surveillance_window_days(self) -> int:
        """Days after device removal to still consider device-associated."""
        pass
    
    @abstractmethod
    def detect_candidates(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Any]:
        """
        Detect HAI candidates in the specified date range.
        
        Args:
            start_date: Start of detection window
            end_date: End of detection window
            
        Returns:
            List of HAI candidate objects
        """
        pass
    
    @abstractmethod
    def validate_device_eligibility(
        self,
        device_start: datetime,
        device_end: Optional[datetime],
        event_date: datetime
    ) -> bool:
        """
        Check if device meets timing criteria for HAI eligibility.
        
        Args:
            device_start: When device was placed
            device_end: When device was removed (None if still in place)
            event_date: Date of potential HAI event
            
        Returns:
            True if device timing meets criteria
        """
        pass
    
    def calculate_device_days(
        self,
        device_start: datetime,
        device_end: Optional[datetime],
        as_of_date: Optional[datetime] = None
    ) -> int:
        """
        Calculate device days.
        
        Args:
            device_start: When device was placed
            device_end: When device was removed
            as_of_date: Calculate as of this date (default: now)
            
        Returns:
            Number of device days
        """
        if as_of_date is None:
            as_of_date = datetime.now()
        
        end = device_end or as_of_date
        delta = (end.date() - device_start.date()).days
        return max(0, delta)
```

### 3.4 Configuration Updates

**File:** `nhsn-reporting/.env.template`

Add configuration for new modules:

```env
# ============================================================
# Existing CLABSI Configuration
# ============================================================
NOTE_SOURCE=fhir
FHIR_BASE_URL=http://localhost:8081/fhir
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:70b
MIN_DEVICE_DAYS=2
POLL_INTERVAL=300

# ============================================================
# CAUTI Configuration
# ============================================================
CAUTI_ENABLED=true
CAUTI_MIN_CATHETER_DAYS=2
CAUTI_CFU_THRESHOLD=100000
CAUTI_SURVEILLANCE_WINDOW=1  # Days after catheter removal

# ============================================================
# VAE Configuration
# ============================================================
VAE_ENABLED=true
VAE_MIN_VENT_DAYS=3  # Must be on vent ≥3 days before VAE
VAE_BASELINE_PERIOD_DAYS=2  # Stable/improving period required
VAE_DETERIORATION_DAYS=2  # Days of worsening required

# ============================================================
# SSI Configuration
# ============================================================
SSI_ENABLED=true
SSI_SUPERFICIAL_WINDOW_DAYS=30  # Superficial/Deep
SSI_IMPLANT_WINDOW_DAYS=90  # With implant: 90 days for deep/organ-space

# ============================================================
# AU Reporting Configuration
# ============================================================
AU_ENABLED=true
AU_CLARITY_CONNECTION_STRING=  # Clarity database connection
AU_REPORTING_LOCATIONS=  # Comma-separated NHSN location codes

# ============================================================
# AR Reporting Configuration
# ============================================================
AR_ENABLED=true
AR_REPORTING_LOCATIONS=  # Comma-separated NHSN location codes
AR_FIRST_ISOLATE_WINDOW_DAYS=14  # Deduplication window

# ============================================================
# NHSN Submission
# ============================================================
NHSN_FACILITY_ID=
NHSN_FACILITY_NAME=
NHSN_DIRECT_ADDRESS=
NHSN_SENDER_DIRECT_ADDRESS=
```

---

## 4. Phase 2: CAUTI Detection Module

### 4.1 CAUTI Candidate Detector

**File:** `nhsn-reporting/src/candidates/cauti.py`

```python
"""
CAUTI (Catheter-Associated Urinary Tract Infection) candidate detection.

NHSN CAUTI Criteria:
1. Indwelling urinary catheter in place for >2 calendar days on date of event
2. Positive urine culture (≥10^5 CFU/mL) with no more than 2 species
3. At least one of: fever (>38.0°C), suprapubic tenderness, CVA pain/tenderness,
   urinary urgency, frequency, or dysuria
4. No alternate source for the UTI symptoms
"""

from typing import List, Optional
from datetime import datetime, timedelta
import logging

from .base import BaseCandidateDetector
from ..models import HAIType, CAUTICandidate
from ..config import Config

logger = logging.getLogger(__name__)


class CAUTICandidateDetector(BaseCandidateDetector):
    """Detects potential CAUTI candidates from urine culture data."""
    
    @property
    def hai_type(self) -> HAIType:
        return HAIType.CAUTI
    
    @property
    def min_device_days(self) -> int:
        return self.config.get('min_catheter_days', Config.CAUTI_MIN_CATHETER_DAYS)
    
    @property
    def surveillance_window_days(self) -> int:
        return self.config.get('surveillance_window', Config.CAUTI_SURVEILLANCE_WINDOW)
    
    @property
    def cfu_threshold(self) -> int:
        return self.config.get('cfu_threshold', Config.CAUTI_CFU_THRESHOLD)
    
    def detect_candidates(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[CAUTICandidate]:
        """
        Detect CAUTI candidates from positive urine cultures.
        
        Steps:
        1. Query positive urine cultures in date range
        2. Filter for significant bacteriuria (≥10^5 CFU/mL)
        3. Check for indwelling urinary catheter
        4. Validate catheter was in place ≥2 days
        5. Return eligible candidates
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=1)
        if end_date is None:
            end_date = datetime.now()
        
        candidates = []
        
        # Step 1: Get positive urine cultures
        urine_cultures = self.data_source.get_urine_cultures(
            start_date=start_date,
            end_date=end_date,
            positive_only=True
        )
        
        logger.info(f"Found {len(urine_cultures)} positive urine cultures")
        
        for culture in urine_cultures:
            # Step 2: Check CFU threshold
            if not self._meets_cfu_threshold(culture):
                logger.debug(f"Culture {culture.id} below CFU threshold")
                continue
            
            # Step 3: Check for catheter
            catheter = self.data_source.get_urinary_catheter(
                patient_id=culture.patient_id,
                as_of_date=culture.collection_date
            )
            
            if not catheter:
                logger.debug(f"No catheter found for patient {culture.patient_id}")
                continue
            
            # Step 4: Validate catheter timing
            if not self.validate_device_eligibility(
                device_start=catheter.start_date,
                device_end=catheter.end_date,
                event_date=culture.collection_date
            ):
                logger.debug(f"Catheter timing not eligible for {culture.patient_id}")
                continue
            
            # Step 5: Create candidate
            catheter_days = self.calculate_device_days(
                catheter.start_date,
                catheter.end_date,
                culture.collection_date
            )
            
            candidate = CAUTICandidate(
                id=f"cauti-{culture.id}",
                patient_id=culture.patient_id,
                encounter_id=culture.encounter_id,
                mrn=culture.mrn,
                patient_name=culture.patient_name,
                urine_culture_id=culture.id,
                urine_culture_date=culture.collection_date,
                organism=culture.organism,
                cfu_count=culture.cfu_count,
                catheter_device_id=catheter.id,
                catheter_type=catheter.type,
                catheter_start_date=catheter.start_date,
                catheter_end_date=catheter.end_date,
                catheter_days=catheter_days,
                location=culture.location
            )
            
            candidates.append(candidate)
            logger.info(f"CAUTI candidate detected: {candidate.id}")
        
        return candidates
    
    def _meets_cfu_threshold(self, culture) -> bool:
        """Check if culture meets CFU threshold (≥10^5)."""
        if culture.cfu_count is None:
            # If CFU not specified, assume significant if reported as positive
            return True
        return culture.cfu_count >= self.cfu_threshold
    
    def validate_device_eligibility(
        self,
        device_start: datetime,
        device_end: Optional[datetime],
        event_date: datetime
    ) -> bool:
        """
        NHSN CAUTI device eligibility:
        - Catheter in place for >2 calendar days on date of event
        - Event occurs while catheter in place OR within 1 day of removal
        """
        device_days = self.calculate_device_days(device_start, device_end, event_date)
        
        if device_days < self.min_device_days:
            return False
        
        # Check if event within surveillance window
        if device_end:
            days_after_removal = (event_date.date() - device_end.date()).days
            if days_after_removal > self.surveillance_window_days:
                return False
        
        return True
```

### 4.2 CAUTI Extraction Prompt

**File:** `nhsn-reporting/prompts/cauti_extraction_v1.txt`

```text
You are a clinical data extraction assistant. Your task is to extract specific clinical facts from medical documentation to support CAUTI (Catheter-Associated Urinary Tract Infection) classification.

IMPORTANT: You are extracting FACTS, not making a classification decision. Answer only based on what is explicitly documented.

## Patient Information
- Patient: {patient_name} (MRN: {mrn})
- Urine Culture Date: {culture_date}
- Organism: {organism}
- Colony Count: {cfu_count} CFU/mL
- Catheter Type: {catheter_type}
- Catheter Days: {catheter_days}

## Clinical Notes
{clinical_notes}

## Extraction Questions

Answer each question with "yes", "no", or "not documented". Provide the source note type and date for each "yes" answer.

### Urinary Symptoms (within 24 hours of culture)
1. Fever documented (>38.0°C or "febrile")?
2. Suprapubic tenderness documented?
3. Costovertebral angle (CVA) pain or tenderness documented?
4. Urinary urgency documented?
5. Urinary frequency documented?
6. Dysuria documented?

### Alternate Explanations
7. Is there documentation of another source for UTI symptoms (e.g., pyelonephritis from ureteral obstruction)?
8. Was a urologic procedure performed within 48 hours of culture?

### Catheter Assessment
9. Is indwelling urinary catheter explicitly documented as present at time of culture?
10. How many days was catheter documented as in place before culture?
11. Was catheter removed BEFORE urine culture was collected?

### Documentation Quality
12. Rate the overall documentation quality for CAUTI assessment:
    - poor: Missing critical information
    - limited: Some relevant notes but incomplete
    - adequate: Sufficient for assessment
    - detailed: Comprehensive documentation

## Response Format

Respond with a JSON object:
```json
{
  "fever": "yes|no|not documented",
  "fever_source": "note type, date",
  "suprapubic_tenderness": "yes|no|not documented",
  "suprapubic_tenderness_source": "",
  "cva_pain": "yes|no|not documented",
  "cva_pain_source": "",
  "urinary_urgency": "yes|no|not documented",
  "urinary_urgency_source": "",
  "urinary_frequency": "yes|no|not documented",
  "urinary_frequency_source": "",
  "dysuria": "yes|no|not documented",
  "dysuria_source": "",
  "alternate_uti_source": "yes|no|not documented",
  "alternate_uti_source_details": "",
  "recent_urologic_procedure": "yes|no|not documented",
  "recent_urologic_procedure_details": "",
  "catheter_documented": "yes|no",
  "catheter_days_documented": "number or null",
  "catheter_removed_before_culture": "yes|no|not documented",
  "documentation_quality": "poor|limited|adequate|detailed"
}
```
```

### 4.3 CAUTI Rules Engine

**File:** `nhsn-reporting/src/rules/cauti_engine.py`

```python
"""
NHSN CAUTI Rules Engine.

Applies deterministic NHSN criteria to extracted clinical facts.

NHSN CAUTI Definition (simplified):
1. Indwelling catheter >2 days at time of event
2. Positive urine culture ≥10^5 CFU/mL with ≤2 organisms
3. At least ONE of:
   - Fever (>38.0°C)
   - Suprapubic tenderness
   - CVA pain/tenderness
   - Urinary urgency/frequency/dysuria
4. No alternate source for symptoms
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum

from ..models import CAUTICandidate, CAUTIExtraction, CAUTIClassification


@dataclass
class CAUTIRuleResult:
    """Result of CAUTI rules evaluation."""
    classification: CAUTIClassification
    confidence: float
    reasoning: str
    rule_trace: List[str]


class CAUTIRulesEngine:
    """Deterministic NHSN CAUTI classification engine."""
    
    # NHSN-defined CFU threshold
    CFU_THRESHOLD = 100000
    MIN_CATHETER_DAYS = 2
    
    # Organisms that require special handling
    CONTAMINANT_ORGANISMS = {
        'lactobacillus',
        'corynebacterium',
        'coagulase-negative staphylococcus',
    }
    
    def evaluate(
        self,
        candidate: CAUTICandidate,
        extraction: CAUTIExtraction
    ) -> CAUTIRuleResult:
        """
        Apply NHSN CAUTI decision tree.
        
        Decision Order:
        1. Check basic eligibility (catheter days, CFU count)
        2. Check for urinary symptoms (at least 1 required)
        3. Check for alternate explanations
        4. If all criteria met → CAUTI
        """
        rule_trace = []
        
        # Rule 1: Basic eligibility
        eligible, reason = self._check_eligibility(candidate, extraction)
        rule_trace.append(f"Eligibility check: {reason}")
        
        if not eligible:
            return CAUTIRuleResult(
                classification=CAUTIClassification.NOT_ELIGIBLE,
                confidence=0.95,
                reasoning=reason,
                rule_trace=rule_trace
            )
        
        # Rule 2: Urinary symptoms
        has_symptoms, symptom_reason = self._check_urinary_symptoms(extraction)
        rule_trace.append(f"Symptom check: {symptom_reason}")
        
        if not has_symptoms:
            return CAUTIRuleResult(
                classification=CAUTIClassification.ASYMPTOMATIC_BACTERIURIA,
                confidence=0.90,
                reasoning="Positive culture without documented urinary symptoms = asymptomatic bacteriuria",
                rule_trace=rule_trace
            )
        
        # Rule 3: Alternate explanations
        has_alternate, alternate_reason = self._check_alternate_sources(extraction)
        rule_trace.append(f"Alternate source check: {alternate_reason}")
        
        if has_alternate:
            return CAUTIRuleResult(
                classification=CAUTIClassification.SECONDARY_UTI,
                confidence=0.85,
                reasoning=f"UTI secondary to alternate source: {alternate_reason}",
                rule_trace=rule_trace
            )
        
        # Rule 4: All criteria met → CAUTI
        confidence = self._calculate_confidence(extraction)
        rule_trace.append(f"CAUTI criteria met. Confidence: {confidence:.2f}")
        
        return CAUTIRuleResult(
            classification=CAUTIClassification.CAUTI,
            confidence=confidence,
            reasoning="Meets NHSN CAUTI criteria: catheter ≥2 days + positive culture + urinary symptoms + no alternate source",
            rule_trace=rule_trace
        )
    
    def _check_eligibility(
        self,
        candidate: CAUTICandidate,
        extraction: CAUTIExtraction
    ) -> Tuple[bool, str]:
        """Check basic CAUTI eligibility criteria."""
        # Check catheter days
        if candidate.catheter_days is not None:
            if candidate.catheter_days < self.MIN_CATHETER_DAYS:
                return False, f"Catheter only {candidate.catheter_days} days (need ≥{self.MIN_CATHETER_DAYS})"
        elif extraction.catheter_days_documented:
            if extraction.catheter_days_documented < self.MIN_CATHETER_DAYS:
                return False, f"Documented catheter days ({extraction.catheter_days_documented}) < {self.MIN_CATHETER_DAYS}"
        
        # Check catheter removed before culture
        if extraction.catheter_removed_before_culture:
            return False, "Catheter removed before urine culture collected"
        
        # Check CFU count
        if candidate.cfu_count and candidate.cfu_count < self.CFU_THRESHOLD:
            return False, f"CFU count ({candidate.cfu_count:,}) below threshold ({self.CFU_THRESHOLD:,})"
        
        return True, "Basic eligibility criteria met"
    
    def _check_urinary_symptoms(
        self,
        extraction: CAUTIExtraction
    ) -> Tuple[bool, str]:
        """Check for at least one urinary symptom."""
        symptoms = []
        
        if extraction.fever:
            symptoms.append("fever")
        if extraction.suprapubic_tenderness:
            symptoms.append("suprapubic tenderness")
        if extraction.costovertebral_angle_pain:
            symptoms.append("CVA pain/tenderness")
        if extraction.urinary_urgency:
            symptoms.append("urinary urgency")
        if extraction.urinary_frequency:
            symptoms.append("urinary frequency")
        if extraction.dysuria:
            symptoms.append("dysuria")
        
        if symptoms:
            return True, f"Documented symptoms: {', '.join(symptoms)}"
        else:
            return False, "No urinary symptoms documented"
    
    def _check_alternate_sources(
        self,
        extraction: CAUTIExtraction
    ) -> Tuple[bool, str]:
        """Check for alternate explanations for UTI."""
        if extraction.alternate_uti_source:
            return True, "Alternate UTI source documented"
        if extraction.recent_urologic_procedure:
            return True, "Recent urologic procedure documented"
        
        return False, "No alternate sources identified"
    
    def _calculate_confidence(self, extraction: CAUTIExtraction) -> float:
        """Calculate confidence based on documentation quality."""
        base_confidence = 0.85
        
        quality_adjustments = {
            'poor': -0.15,
            'limited': -0.05,
            'adequate': 0.0,
            'detailed': 0.10
        }
        
        adjustment = quality_adjustments.get(extraction.documentation_quality, 0.0)
        return min(0.99, max(0.50, base_confidence + adjustment))
```

### 4.4 CAUTI Classifier (Orchestration)

**File:** `nhsn-reporting/src/classifiers/cauti_classifier.py`

```python
"""
CAUTI Classifier - Orchestrates extraction and rules engine.

Pipeline:
1. Retrieve clinical notes for candidate
2. Run LLM extraction to get structured facts
3. Apply NHSN rules engine
4. Return classification with full audit trail
"""

from typing import Optional, Dict, Any
from datetime import datetime
import logging
import json

from .base import BaseHAIClassifier
from ..models import CAUTICandidate, CAUTIExtraction, CAUTIClassification
from ..extraction.cauti_extractor import CAUTIExtractor
from ..rules.cauti_engine import CAUTIRulesEngine, CAUTIRuleResult
from ..notes.retriever import NoteRetriever
from ..llm.factory import LLMFactory
from ..db import NHSNDatabase

logger = logging.getLogger(__name__)


class CAUTIClassifier(BaseHAIClassifier):
    """CAUTI classification using extraction + rules architecture."""
    
    def __init__(
        self,
        llm_client=None,
        note_retriever=None,
        db: Optional[NHSNDatabase] = None
    ):
        self.llm_client = llm_client or LLMFactory.create()
        self.note_retriever = note_retriever or NoteRetriever()
        self.db = db or NHSNDatabase()
        
        self.extractor = CAUTIExtractor(self.llm_client)
        self.rules_engine = CAUTIRulesEngine()
    
    def classify(
        self,
        candidate: CAUTICandidate,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify a CAUTI candidate.
        
        Returns dict with:
        - classification: CAUTIClassification enum value
        - confidence: float 0-1
        - reasoning: human-readable explanation
        - extraction: extracted clinical facts
        - rule_trace: list of rules evaluated
        """
        logger.info(f"Classifying CAUTI candidate: {candidate.id}")
        
        # Step 1: Get clinical notes if not provided
        if notes is None:
            notes = self.note_retriever.get_notes_for_event(
                patient_id=candidate.patient_id,
                event_date=candidate.urine_culture_date,
                note_types=['progress', 'nursing', 'consult'],
                window_days=3
            )
        
        if not notes:
            logger.warning(f"No clinical notes found for {candidate.id}")
            return self._create_result(
                classification=CAUTIClassification.NOT_ELIGIBLE,
                confidence=0.5,
                reasoning="Insufficient documentation - no clinical notes found",
                extraction=None,
                rule_trace=["No notes available for review"]
            )
        
        # Step 2: LLM extraction
        extraction = self.extractor.extract(candidate, notes)
        
        # Step 3: Apply rules engine
        result = self.rules_engine.evaluate(candidate, extraction)
        
        # Step 4: Store classification
        classification_record = self._store_classification(
            candidate, extraction, result
        )
        
        return self._create_result(
            classification=result.classification,
            confidence=result.confidence,
            reasoning=result.reasoning,
            extraction=extraction,
            rule_trace=result.rule_trace,
            classification_id=classification_record.id
        )
    
    def _create_result(
        self,
        classification: CAUTIClassification,
        confidence: float,
        reasoning: str,
        extraction: Optional[CAUTIExtraction],
        rule_trace: list,
        classification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create standardized result dictionary."""
        return {
            'classification': classification.value,
            'confidence': confidence,
            'reasoning': reasoning,
            'extraction': extraction.__dict__ if extraction else None,
            'rule_trace': rule_trace,
            'classification_id': classification_id,
            'classified_at': datetime.now().isoformat()
        }
    
    def _store_classification(
        self,
        candidate: CAUTICandidate,
        extraction: CAUTIExtraction,
        result: CAUTIRuleResult
    ):
        """Store classification in database."""
        return self.db.store_cauti_classification(
            candidate_id=candidate.id,
            classification=result.classification.value,
            confidence=result.confidence,
            reasoning=result.reasoning,
            extracted_data=json.dumps(extraction.__dict__),
            rule_trace=json.dumps(result.rule_trace)
        )
```

---

## 5. Phase 3: VAE Detection Module

### 5.1 VAE Overview

VAE (Ventilator-Associated Events) is a more complex HAI with a tiered definition:

```
                    ┌─────────────────┐
                    │       VAC       │  Ventilator-Associated Condition
                    │  (Oxygenation   │  - ≥2 days stable/improving
                    │   worsening)    │  - Then ≥2 days worsening PEEP/FiO2
                    └────────┬────────┘
                             │
                      meets IVAC criteria?
                             │
                    ┌────────▼────────┐
                    │      IVAC       │  Infection-related VAC
                    │  (VAC + fever/  │  - Temperature >38°C or <36°C
                    │   WBC + new     │  - WBC >12k or <4k
                    │   antibiotic)   │  - Started new antimicrobial ≥4 days
                    └────────┬────────┘
                             │
                      meets PVAP criteria?
                             │
                    ┌────────▼────────┐
                    │      PVAP       │  Possible VAP
                    │  (IVAC +        │  - Purulent secretions, OR
                    │   respiratory   │  - Positive quantitative culture, OR
                    │   evidence)     │  - Lung histopathology, OR
                    └─────────────────┘  - Positive Legionella/viral test
```

### 5.2 VAE Candidate Detector

**File:** `nhsn-reporting/src/candidates/vae.py`

```python
"""
VAE (Ventilator-Associated Event) candidate detection.

NHSN VAE Detection Algorithm:
1. Patient on mechanical ventilation ≥3 calendar days
2. Period of stability or improvement (≥2 days) on ventilator
3. Followed by worsening oxygenation:
   - Increase in daily minimum PEEP ≥3 cm H2O for ≥2 days, OR
   - Increase in daily minimum FiO2 ≥20 points for ≥2 days
"""

from typing import List, Optional, Dict
from datetime import datetime, timedelta, date
from dataclasses import dataclass
import logging

from .base import BaseCandidateDetector
from ..models import HAIType, VAECandidate, VAEDailyAssessment
from ..config import Config

logger = logging.getLogger(__name__)


@dataclass
class VentilatorDay:
    """Single day of ventilator data."""
    date: date
    min_peep: Optional[float]
    min_fio2: Optional[float]
    

class VAECandidateDetector(BaseCandidateDetector):
    """Detects VAE candidates from ventilator data."""
    
    @property
    def hai_type(self) -> HAIType:
        return HAIType.VAE
    
    @property
    def min_device_days(self) -> int:
        """Minimum ventilator days before VAE can occur."""
        return self.config.get('min_vent_days', 3)
    
    @property
    def surveillance_window_days(self) -> int:
        return 0  # VAE only while on ventilator
    
    @property
    def baseline_period_days(self) -> int:
        """Days of stable/improving settings required."""
        return self.config.get('baseline_period_days', 2)
    
    @property
    def deterioration_days(self) -> int:
        """Days of worsening required to trigger VAE."""
        return self.config.get('deterioration_days', 2)
    
    @property
    def peep_threshold(self) -> float:
        """PEEP increase threshold (cm H2O)."""
        return 3.0
    
    @property
    def fio2_threshold(self) -> float:
        """FiO2 increase threshold (percentage points)."""
        return 20.0
    
    def detect_candidates(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[VAECandidate]:
        """
        Detect VAE candidates by analyzing ventilator trends.
        
        Steps:
        1. Get all mechanically ventilated patients
        2. For each, get daily PEEP/FiO2 values
        3. Apply VAE detection algorithm
        4. Return candidates meeting VAC criteria
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()
        
        candidates = []
        
        # Get ventilated patients
        vent_episodes = self.data_source.get_ventilator_episodes(
            start_date=start_date,
            end_date=end_date,
            min_duration_days=self.min_device_days
        )
        
        logger.info(f"Found {len(vent_episodes)} ventilator episodes ≥{self.min_device_days} days")
        
        for episode in vent_episodes:
            # Get daily assessments
            daily_data = self.data_source.get_ventilator_daily_values(
                patient_id=episode.patient_id,
                encounter_id=episode.encounter_id,
                start_date=episode.start_date,
                end_date=episode.end_date or end_date
            )
            
            if len(daily_data) < self.min_device_days:
                continue
            
            # Apply VAE detection algorithm
            vae_events = self._detect_vae_events(episode, daily_data)
            
            for event_date in vae_events:
                candidate = VAECandidate(
                    id=f"vae-{episode.patient_id}-{event_date.isoformat()}",
                    patient_id=episode.patient_id,
                    encounter_id=episode.encounter_id,
                    mrn=episode.mrn,
                    patient_name=episode.patient_name,
                    ventilator_start_date=episode.start_date,
                    ventilator_end_date=episode.end_date,
                    baseline_peep=self._get_baseline_peep(daily_data, event_date),
                    baseline_fio2=self._get_baseline_fio2(daily_data, event_date),
                    event_date=datetime.combine(event_date, datetime.min.time()),
                    location=episode.location
                )
                candidates.append(candidate)
                logger.info(f"VAE candidate detected: {candidate.id}")
        
        return candidates
    
    def _detect_vae_events(
        self,
        episode,
        daily_data: List[VentilatorDay]
    ) -> List[date]:
        """
        Apply NHSN VAE detection algorithm.
        
        For each day after baseline period:
        1. Check if prior 2 days were stable/improving
        2. Check if current + next day show sustained worsening
        """
        events = []
        
        # Need at least baseline + deterioration days
        min_days = self.baseline_period_days + self.deterioration_days
        if len(daily_data) < min_days:
            return events
        
        # Sort by date
        daily_data = sorted(daily_data, key=lambda x: x.date)
        
        for i in range(self.baseline_period_days, len(daily_data) - 1):
            current_day = daily_data[i]
            
            # Check baseline period (prior 2 days stable or improving)
            baseline_days = daily_data[i - self.baseline_period_days:i]
            if not self._is_baseline_stable(baseline_days):
                continue
            
            # Check for deterioration (current + next day worsening)
            deterioration_days = daily_data[i:i + self.deterioration_days]
            if len(deterioration_days) < self.deterioration_days:
                continue
            
            baseline_peep = self._get_baseline_metric(baseline_days, 'peep')
            baseline_fio2 = self._get_baseline_metric(baseline_days, 'fio2')
            
            if self._is_peep_deterioration(deterioration_days, baseline_peep) or \
               self._is_fio2_deterioration(deterioration_days, baseline_fio2):
                events.append(current_day.date)
        
        return events
    
    def _is_baseline_stable(self, days: List[VentilatorDay]) -> bool:
        """Check if baseline period shows stable or improving settings."""
        if len(days) < 2:
            return False
        
        # Simplified: check that settings didn't increase
        for i in range(1, len(days)):
            if days[i].min_peep and days[i-1].min_peep:
                if days[i].min_peep > days[i-1].min_peep:
                    return False
            if days[i].min_fio2 and days[i-1].min_fio2:
                if days[i].min_fio2 > days[i-1].min_fio2:
                    return False
        
        return True
    
    def _is_peep_deterioration(
        self,
        days: List[VentilatorDay],
        baseline_peep: float
    ) -> bool:
        """Check if PEEP increased ≥3 cm H2O for ≥2 days."""
        if baseline_peep is None:
            return False
        
        elevated_days = 0
        for day in days:
            if day.min_peep and (day.min_peep - baseline_peep) >= self.peep_threshold:
                elevated_days += 1
        
        return elevated_days >= self.deterioration_days
    
    def _is_fio2_deterioration(
        self,
        days: List[VentilatorDay],
        baseline_fio2: float
    ) -> bool:
        """Check if FiO2 increased ≥20 points for ≥2 days."""
        if baseline_fio2 is None:
            return False
        
        elevated_days = 0
        for day in days:
            if day.min_fio2 and (day.min_fio2 - baseline_fio2) >= self.fio2_threshold:
                elevated_days += 1
        
        return elevated_days >= self.deterioration_days
    
    def _get_baseline_metric(
        self,
        days: List[VentilatorDay],
        metric: str
    ) -> Optional[float]:
        """Get baseline value for PEEP or FiO2."""
        values = []
        for day in days:
            val = getattr(day, f'min_{metric}', None)
            if val is not None:
                values.append(val)
        return min(values) if values else None
    
    def _get_baseline_peep(
        self,
        daily_data: List[VentilatorDay],
        event_date: date
    ) -> Optional[float]:
        """Get baseline PEEP before event."""
        baseline_days = [
            d for d in daily_data
            if d.date < event_date
        ][-self.baseline_period_days:]
        return self._get_baseline_metric(baseline_days, 'peep')
    
    def _get_baseline_fio2(
        self,
        daily_data: List[VentilatorDay],
        event_date: date
    ) -> Optional[float]:
        """Get baseline FiO2 before event."""
        baseline_days = [
            d for d in daily_data
            if d.date < event_date
        ][-self.baseline_period_days:]
        return self._get_baseline_metric(baseline_days, 'fio2')
    
    def validate_device_eligibility(
        self,
        device_start: datetime,
        device_end: Optional[datetime],
        event_date: datetime
    ) -> bool:
        """VAE only while on ventilator."""
        vent_days = self.calculate_device_days(device_start, device_end, event_date)
        
        if vent_days < self.min_device_days:
            return False
        
        # Must still be on ventilator
        if device_end and event_date > device_end:
            return False
        
        return True
```

### 5.3 VAE Rules Engine

**File:** `nhsn-reporting/src/rules/vae_engine.py`

```python
"""
NHSN VAE Rules Engine.

Applies tiered VAE classification:
VAC → IVAC → PVAP
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple

from ..models import VAECandidate, VAEExtraction, VAEClassification


@dataclass
class VAERuleResult:
    """Result of VAE rules evaluation."""
    classification: VAEClassification
    confidence: float
    reasoning: str
    rule_trace: List[str]


class VAERulesEngine:
    """Deterministic NHSN VAE classification engine."""
    
    def evaluate(
        self,
        candidate: VAECandidate,
        extraction: VAEExtraction
    ) -> VAERuleResult:
        """
        Apply NHSN VAE decision tree.
        
        Order:
        1. Confirm VAC criteria (oxygenation worsening)
        2. Check IVAC criteria (infection markers + antimicrobial)
        3. Check PVAP criteria (respiratory evidence)
        """
        rule_trace = []
        
        # Rule 1: VAC criteria (must be met for any VAE)
        is_vac, vac_reason = self._check_vac_criteria(candidate, extraction)
        rule_trace.append(f"VAC check: {vac_reason}")
        
        if not is_vac:
            return VAERuleResult(
                classification=VAEClassification.NOT_VAE,
                confidence=0.90,
                reasoning=vac_reason,
                rule_trace=rule_trace
            )
        
        # Rule 2: IVAC criteria
        is_ivac, ivac_reason = self._check_ivac_criteria(extraction)
        rule_trace.append(f"IVAC check: {ivac_reason}")
        
        if not is_ivac:
            return VAERuleResult(
                classification=VAEClassification.VAC,
                confidence=0.85,
                reasoning="Meets VAC criteria (oxygenation worsening) but not IVAC (no infection markers)",
                rule_trace=rule_trace
            )
        
        # Rule 3: PVAP criteria
        is_pvap, pvap_reason = self._check_pvap_criteria(extraction)
        rule_trace.append(f"PVAP check: {pvap_reason}")
        
        if is_pvap:
            return VAERuleResult(
                classification=VAEClassification.PVAP,
                confidence=0.80,
                reasoning="Meets PVAP criteria (IVAC + respiratory evidence)",
                rule_trace=rule_trace
            )
        
        return VAERuleResult(
            classification=VAEClassification.IVAC,
            confidence=0.85,
            reasoning="Meets IVAC criteria (VAC + infection markers + new antimicrobial)",
            rule_trace=rule_trace
        )
    
    def _check_vac_criteria(
        self,
        candidate: VAECandidate,
        extraction: VAEExtraction
    ) -> Tuple[bool, str]:
        """
        VAC requires:
        - ≥2 days stable/improving ventilator settings
        - Followed by ≥2 days of sustained worsening
        """
        if not extraction.baseline_period_stable:
            return False, "No documented stable baseline period"
        
        if extraction.sustained_peep_increase:
            return True, f"PEEP increased ≥3 cm H2O for ≥2 days"
        
        if extraction.sustained_fio2_increase:
            return True, f"FiO2 increased ≥20 points for ≥2 days"
        
        return False, "No sustained oxygenation worsening documented"
    
    def _check_ivac_criteria(
        self,
        extraction: VAEExtraction
    ) -> Tuple[bool, str]:
        """
        IVAC requires VAC PLUS:
        - Temperature >38°C or <36°C, AND
        - WBC >12,000 or <4,000, AND
        - New antimicrobial started and continued ≥4 days
        """
        if not extraction.temperature_abnormal:
            return False, "No abnormal temperature documented"
        
        if not extraction.wbc_abnormal:
            return False, "No abnormal WBC documented"
        
        if not extraction.new_antimicrobial_started:
            return False, "No new antimicrobial documented for ≥4 days"
        
        return True, "Temperature + WBC abnormal + new antimicrobial ≥4 days"
    
    def _check_pvap_criteria(
        self,
        extraction: VAEExtraction
    ) -> Tuple[bool, str]:
        """
        PVAP requires IVAC PLUS one of:
        - Purulent respiratory secretions + organism, OR
        - Positive lung histopathology, OR
        - Positive diagnostic test (Legionella, respiratory virus)
        """
        if extraction.purulent_secretions and extraction.positive_respiratory_culture:
            return True, "Purulent secretions + positive respiratory culture"
        
        if extraction.positive_lung_histopathology:
            return True, "Positive lung histopathology"
        
        if extraction.positive_legionella_test:
            return True, "Positive Legionella test"
        
        if extraction.positive_respiratory_virus:
            return True, "Positive respiratory virus test"
        
        return False, "No PVAP criteria met"
```

---

## 6. Phase 4: SSI Detection Module

### 6.1 SSI Overview

SSI (Surgical Site Infection) is the most complex HAI type due to:
- Requires tracking of surgical procedures
- Different surveillance windows (30 vs 90 days)
- Three levels: Superficial, Deep, Organ/Space
- Procedure-specific NHSN categories (COLO, HYST, CABG, etc.)

```
┌──────────────────────────────────────────────────────────────┐
│                    SSI Surveillance Windows                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Procedure Date         30 days                90 days       │
│       │                    │                      │          │
│       ├────────────────────┤                      │          │
│       │  Superficial SSI   │                      │          │
│       │                    │                      │          │
│       ├────────────────────┼──────────────────────┤          │
│       │  Deep SSI          │  (with implant only) │          │
│       │                    │                      │          │
│       ├────────────────────┼──────────────────────┤          │
│       │  Organ/Space SSI   │  (with implant only) │          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 SSI Candidate Detector

**File:** `nhsn-reporting/src/candidates/ssi.py`

```python
"""
SSI (Surgical Site Infection) candidate detection.

NHSN SSI Criteria:
1. Patient had NHSN operative procedure
2. Infection occurs within surveillance window:
   - 30 days for superficial/deep without implant
   - 90 days for deep/organ-space with implant
3. Infection involves incision or organ/space
"""

from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from .base import BaseCandidateDetector
from ..models import HAIType, SSICandidate, SSIProcedure
from ..config import Config

logger = logging.getLogger(__name__)


# NHSN procedure categories with surveillance windows
NHSN_PROCEDURES = {
    # Category: (CPT/ICD codes, implant_extends_window)
    'COLO': (['44140', '44141', '44143', '44144'], True),
    'HYST': (['58150', '58152', '58180', '58200'], True),
    'CABG': (['33510', '33511', '33512', '33513'], True),
    'CRAN': (['61304', '61305', '61312', '61313'], True),
    'FUSN': (['22551', '22552', '22554', '22558'], True),
    'HTP': (['27130', '27132'], True),
    'KPRO': (['27447', '27446'], True),
    'APPY': (['44950', '44955', '44960'], False),
    'CHOL': (['47562', '47563', '47564'], False),
}


class SSICandidateDetector(BaseCandidateDetector):
    """Detects SSI candidates from surgical procedures and subsequent infections."""
    
    @property
    def hai_type(self) -> HAIType:
        return HAIType.SSI
    
    @property
    def min_device_days(self) -> int:
        return 0  # Not device-based
    
    @property
    def surveillance_window_days(self) -> int:
        return 30  # Base window, extended for implants
    
    @property
    def implant_window_days(self) -> int:
        return 90
    
    def detect_candidates(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[SSICandidate]:
        """
        Detect SSI candidates.
        
        Steps:
        1. Get NHSN surgical procedures in lookback window
        2. For each procedure, check for infection events
        3. Validate timing within surveillance window
        4. Return eligible candidates
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            # Look back far enough to capture procedures within surveillance window
            start_date = end_date - timedelta(days=self.implant_window_days + 30)
        
        candidates = []
        
        # Step 1: Get surgical procedures
        procedures = self._get_nhsn_procedures(start_date, end_date)
        logger.info(f"Found {len(procedures)} NHSN procedures")
        
        for procedure in procedures:
            # Step 2: Check for infection events
            infections = self._find_infection_events(procedure, end_date)
            
            for infection in infections:
                # Step 3: Validate surveillance window
                days_post_op = (infection['date'].date() - procedure.procedure_date.date()).days
                
                if not self._within_surveillance_window(procedure, days_post_op):
                    continue
                
                # Step 4: Create candidate
                candidate = SSICandidate(
                    id=f"ssi-{procedure.id}-{infection['id']}",
                    procedure_id=procedure.id,
                    patient_id=procedure.patient_id,
                    encounter_id=infection.get('encounter_id'),
                    mrn=procedure.mrn,
                    patient_name=infection.get('patient_name'),
                    infection_date=infection['date'],
                    days_post_op=days_post_op,
                    ssi_level=infection.get('level'),
                    culture_id=infection.get('culture_id'),
                    organism=infection.get('organism'),
                    location=procedure.location
                )
                candidates.append(candidate)
                logger.info(f"SSI candidate detected: {candidate.id}")
        
        return candidates
    
    def _get_nhsn_procedures(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[SSIProcedure]:
        """Get surgical procedures that match NHSN categories."""
        all_procedures = self.data_source.get_surgical_procedures(
            start_date=start_date,
            end_date=end_date
        )
        
        nhsn_procedures = []
        for proc in all_procedures:
            category = self._map_to_nhsn_category(proc.procedure_code)
            if category:
                proc.procedure_category = category
                nhsn_procedures.append(proc)
        
        return nhsn_procedures
    
    def _map_to_nhsn_category(self, procedure_code: str) -> Optional[str]:
        """Map procedure code to NHSN category."""
        for category, (codes, _) in NHSN_PROCEDURES.items():
            if procedure_code in codes:
                return category
        return None
    
    def _find_infection_events(
        self,
        procedure: SSIProcedure,
        end_date: datetime
    ) -> List[Dict]:
        """Find potential infection events for a procedure."""
        # Determine surveillance window
        window_days = self.implant_window_days if procedure.implant else self.surveillance_window_days
        window_end = min(
            procedure.procedure_date + timedelta(days=window_days),
            end_date
        )
        
        infections = []
        
        # Check for wound cultures
        cultures = self.data_source.get_wound_cultures(
            patient_id=procedure.patient_id,
            start_date=procedure.procedure_date,
            end_date=window_end
        )
        
        for culture in cultures:
            infections.append({
                'id': culture.id,
                'date': culture.collection_date,
                'type': 'culture',
                'culture_id': culture.id,
                'organism': culture.organism,
                'encounter_id': culture.encounter_id,
                'patient_name': culture.patient_name
            })
        
        # Check for wound-related diagnoses/procedures
        diagnoses = self.data_source.get_wound_diagnoses(
            patient_id=procedure.patient_id,
            start_date=procedure.procedure_date,
            end_date=window_end
        )
        
        for dx in diagnoses:
            infections.append({
                'id': dx.id,
                'date': dx.date,
                'type': 'diagnosis',
                'level': self._infer_ssi_level(dx.code),
                'encounter_id': dx.encounter_id,
                'patient_name': dx.patient_name
            })
        
        return infections
    
    def _within_surveillance_window(
        self,
        procedure: SSIProcedure,
        days_post_op: int
    ) -> bool:
        """Check if infection is within NHSN surveillance window."""
        if days_post_op < 0:
            return False
        
        # Deep/organ-space with implant: 90 days
        if procedure.implant:
            category_info = NHSN_PROCEDURES.get(procedure.procedure_category)
            if category_info and category_info[1]:  # implant_extends_window
                return days_post_op <= self.implant_window_days
        
        # All others: 30 days
        return days_post_op <= self.surveillance_window_days
    
    def _infer_ssi_level(self, diagnosis_code: str) -> Optional[str]:
        """Infer SSI level from diagnosis code."""
        # Simplified mapping - would need full ICD-10 mapping in production
        if 'superficial' in diagnosis_code.lower():
            return 'Superficial'
        elif 'deep' in diagnosis_code.lower():
            return 'Deep'
        elif 'organ' in diagnosis_code.lower() or 'space' in diagnosis_code.lower():
            return 'Organ/Space'
        return None
    
    def validate_device_eligibility(
        self,
        device_start: datetime,
        device_end: Optional[datetime],
        event_date: datetime
    ) -> bool:
        """SSI not device-based, uses procedure timing instead."""
        # This method required by base class but SSI uses procedure timing
        return True
```

---

## 7. Phase 5: Antibiotic Usage (AU) Reporting

### 7.1 AU Overview

NHSN Antibiotic Use (AU) reporting tracks antimicrobial consumption at the facility level. Required monthly for CMS reporting.

**Key Metrics:**
- **Days of Therapy (DOT):** Number of days a patient received an antimicrobial
- **Standardized Antimicrobial Administration Ratio (SAAR):** Observed DOT / Predicted DOT

```
                    Monthly AU Reporting Flow
                    
    Clarity/FHIR Data           Aggregation            NHSN Submission
    ─────────────────           ───────────            ───────────────
    
    MAR_ADMIN_INFO     ───▶    DOT by Drug    ───▶    AU Monthly
    (administrations)          by Location            CSV/CDA
                               by Route
                               
    PAT_ENC_HSP        ───▶    Patient Days   ───▶    Denominator
    (census)                   by Location            Data
```

### 7.2 AU Data Extractor

**File:** `nhsn-reporting/src/au/extractor.py`

```python
"""
Antibiotic Usage (AU) data extraction from Clarity and FHIR.

Extracts:
- Antimicrobial administrations (DOT, doses)
- Patient days by location
- Maps to NHSN antimicrobial codes
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import logging

from ..models import AntimicrobialAdministration, AUMonthlySummary, AntimicrobialUsage
from ..data.clarity_source import ClarityDataSource
from ..data.fhir_source import FHIRDataSource

logger = logging.getLogger(__name__)


# NHSN Antimicrobial Code Mapping
NHSN_ANTIMICROBIAL_CODES = {
    # Beta-lactams
    'ampicillin': 'AMP',
    'amoxicillin': 'AMX',
    'amoxicillin/clavulanate': 'AMC',
    'ampicillin/sulbactam': 'SAM',
    'piperacillin/tazobactam': 'TZP',
    'cefazolin': 'CFZ',
    'ceftriaxone': 'CRO',
    'ceftazidime': 'CAZ',
    'cefepime': 'FEP',
    'ceftazidime/avibactam': 'CZA',
    'meropenem': 'MEM',
    'ertapenem': 'ETP',
    'imipenem/cilastatin': 'IPM',
    
    # Glycopeptides
    'vancomycin': 'VAN',
    'daptomycin': 'DAP',
    'linezolid': 'LZD',
    
    # Aminoglycosides
    'gentamicin': 'GEN',
    'tobramycin': 'TOB',
    'amikacin': 'AMK',
    
    # Fluoroquinolones
    'ciprofloxacin': 'CIP',
    'levofloxacin': 'LVX',
    'moxifloxacin': 'MXF',
    
    # Macrolides
    'azithromycin': 'AZM',
    'erythromycin': 'ERY',
    
    # Antifungals
    'fluconazole': 'FLU',
    'micafungin': 'MFG',
    'caspofungin': 'CAS',
    'amphotericin B': 'AMB',
    
    # Other
    'metronidazole': 'MTZ',
    'trimethoprim/sulfamethoxazole': 'SXT',
    'clindamycin': 'CLI',
    'doxycycline': 'DOX',
}


@dataclass
class LocationPatientDays:
    """Patient days for a location/month."""
    location: str
    location_type: str
    month: str
    patient_days: int
    admissions: int


class AUDataExtractor:
    """Extracts antibiotic usage data for NHSN AU reporting."""
    
    def __init__(
        self,
        clarity_source: Optional[ClarityDataSource] = None,
        fhir_source: Optional[FHIRDataSource] = None
    ):
        self.clarity = clarity_source
        self.fhir = fhir_source
    
    def extract_monthly_usage(
        self,
        month: str,  # YYYY-MM format
        locations: Optional[List[str]] = None
    ) -> List[AUMonthlySummary]:
        """
        Extract AU data for a given month.
        
        Returns AUMonthlySummary for each location with:
        - Patient days
        - DOT by antimicrobial
        """
        # Parse month
        year, month_num = map(int, month.split('-'))
        start_date = date(year, month_num, 1)
        if month_num == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month_num + 1, 1) - timedelta(days=1)
        
        summaries = []
        
        # Get patient days by location
        patient_days_by_location = self._get_patient_days(
            start_date, end_date, locations
        )
        
        # Get administrations
        administrations = self._get_administrations(
            start_date, end_date, locations
        )
        
        # Aggregate by location
        for loc, loc_data in patient_days_by_location.items():
            # Calculate DOT by antimicrobial
            loc_administrations = [
                a for a in administrations if a.location == loc
            ]
            usage = self._calculate_dot(loc_administrations, start_date, end_date)
            
            summary = AUMonthlySummary(
                id=f"au-{month}-{loc}",
                reporting_month=month,
                location=loc,
                location_type=loc_data.location_type,
                patient_days=loc_data.patient_days,
                admissions=loc_data.admissions,
                antimicrobial_usage=usage
            )
            summaries.append(summary)
        
        return summaries
    
    def _get_patient_days(
        self,
        start_date: date,
        end_date: date,
        locations: Optional[List[str]]
    ) -> Dict[str, LocationPatientDays]:
        """Get patient days by location from Clarity."""
        if self.clarity:
            return self.clarity.get_patient_days_by_location(
                start_date, end_date, locations
            )
        elif self.fhir:
            return self.fhir.get_patient_days_by_location(
                start_date, end_date, locations
            )
        else:
            raise ValueError("No data source configured")
    
    def _get_administrations(
        self,
        start_date: date,
        end_date: date,
        locations: Optional[List[str]]
    ) -> List[AntimicrobialAdministration]:
        """Get antimicrobial administrations from Clarity MAR."""
        if self.clarity:
            return self.clarity.get_antimicrobial_administrations(
                start_date, end_date, locations
            )
        elif self.fhir:
            return self.fhir.get_antimicrobial_administrations(
                start_date, end_date, locations
            )
        else:
            raise ValueError("No data source configured")
    
    def _calculate_dot(
        self,
        administrations: List[AntimicrobialAdministration],
        start_date: date,
        end_date: date
    ) -> List[AntimicrobialUsage]:
        """
        Calculate Days of Therapy (DOT) from administrations.
        
        DOT = Number of days a patient received a specific antimicrobial
        (regardless of # doses per day)
        """
        # Group by patient + drug + route + date
        dot_tracker: Dict[Tuple[str, str, str], set] = {}  # (drug, route) -> set of (patient, date)
        dose_counter: Dict[Tuple[str, str], int] = {}  # (drug, route) -> count
        
        for admin in administrations:
            # Map to NHSN code
            nhsn_code = self._map_to_nhsn_code(admin.antimicrobial_name)
            if not nhsn_code:
                continue
            
            key = (nhsn_code, admin.route)
            admin_date = admin.administration_datetime.date()
            
            # Track unique patient-days for DOT
            if key not in dot_tracker:
                dot_tracker[key] = set()
            dot_tracker[key].add((admin.patient_id, admin_date))
            
            # Count doses
            if key not in dose_counter:
                dose_counter[key] = 0
            dose_counter[key] += 1
        
        # Convert to AntimicrobialUsage objects
        usage_list = []
        for (nhsn_code, route), patient_dates in dot_tracker.items():
            usage = AntimicrobialUsage(
                antimicrobial_code=nhsn_code,
                antimicrobial_name=self._get_drug_name(nhsn_code),
                route=route,
                days_of_therapy=len(patient_dates),  # Unique patient-days
                doses_administered=dose_counter.get((nhsn_code, route), 0)
            )
            usage_list.append(usage)
        
        return sorted(usage_list, key=lambda x: x.days_of_therapy, reverse=True)
    
    def _map_to_nhsn_code(self, drug_name: str) -> Optional[str]:
        """Map drug name to NHSN antimicrobial code."""
        drug_lower = drug_name.lower()
        for name, code in NHSN_ANTIMICROBIAL_CODES.items():
            if name in drug_lower:
                return code
        return None
    
    def _get_drug_name(self, nhsn_code: str) -> str:
        """Get drug name from NHSN code."""
        for name, code in NHSN_ANTIMICROBIAL_CODES.items():
            if code == nhsn_code:
                return name.title()
        return nhsn_code
```

### 7.3 Clarity SQL Queries for AU

**File:** `nhsn-reporting/src/data/clarity_au_queries.py`

```python
"""
Clarity SQL queries for Antibiotic Usage (AU) data extraction.
"""

# Get antimicrobial administrations from MAR
GET_ANTIMICROBIAL_ADMINISTRATIONS = """
SELECT
    mar.MAR_ENC_CSN AS encounter_id,
    pat.PAT_ID AS patient_id,
    pat.PAT_MRN_ID AS mrn,
    om.NAME AS antimicrobial_name,
    mar.ROUTE_C AS route_code,
    zc_route.NAME AS route,
    mar.TAKEN_TIME AS administration_datetime,
    mar.SIG AS dose,
    dep.DEPARTMENT_NAME AS location,
    zc_loc.NAME AS location_type
FROM
    MAR_ADMIN_INFO mar
    INNER JOIN PATIENT pat ON mar.PAT_ID = pat.PAT_ID
    INNER JOIN ORDER_MED om ON mar.ORDER_MED_ID = om.ORDER_MED_ID
    LEFT JOIN ZC_ADMIN_ROUTE zc_route ON mar.ROUTE_C = zc_route.ADMIN_ROUTE_C
    INNER JOIN PAT_ENC_HSP peh ON mar.MAR_ENC_CSN = peh.PAT_ENC_CSN_ID
    INNER JOIN CLARITY_DEP dep ON peh.DEPARTMENT_ID = dep.DEPARTMENT_ID
    LEFT JOIN ZC_ACUITY_LEVEL zc_loc ON dep.ACUITY_LEVEL_C = zc_loc.ACUITY_LEVEL_C
WHERE
    mar.TAKEN_TIME >= :start_date
    AND mar.TAKEN_TIME <= :end_date
    AND mar.MAR_ACTION_C IN (1, 6)  -- Given, New Bag
    AND om.PHARM_CLASS_C IN (
        SELECT PHARM_CLASS_C FROM ZC_PHARM_CLASS 
        WHERE NAME LIKE '%antibiotic%' OR NAME LIKE '%antifungal%' OR NAME LIKE '%antimicrobial%'
    )
    {location_filter}
ORDER BY
    mar.TAKEN_TIME
"""

# Get patient days by location
GET_PATIENT_DAYS_BY_LOCATION = """
SELECT
    dep.DEPARTMENT_NAME AS location,
    zc_loc.NAME AS location_type,
    COUNT(DISTINCT CONCAT(peh.PAT_ID, '-', CAST(census_date.calendar_date AS VARCHAR))) AS patient_days,
    COUNT(DISTINCT CASE 
        WHEN CAST(peh.HOSP_ADMSN_TIME AS DATE) = census_date.calendar_date 
        THEN peh.PAT_ENC_CSN_ID 
    END) AS admissions
FROM
    PAT_ENC_HSP peh
    INNER JOIN CLARITY_DEP dep ON peh.DEPARTMENT_ID = dep.DEPARTMENT_ID
    LEFT JOIN ZC_ACUITY_LEVEL zc_loc ON dep.ACUITY_LEVEL_C = zc_loc.ACUITY_LEVEL_C
    CROSS JOIN (
        SELECT DATEADD(DAY, number, :start_date) AS calendar_date
        FROM master.dbo.spt_values
        WHERE type = 'P' AND number <= DATEDIFF(DAY, :start_date, :end_date)
    ) census_date
WHERE
    census_date.calendar_date >= CAST(peh.HOSP_ADMSN_TIME AS DATE)
    AND census_date.calendar_date < COALESCE(CAST(peh.HOSP_DISCH_TIME AS DATE), :end_date + 1)
    AND census_date.calendar_date >= :start_date
    AND census_date.calendar_date <= :end_date
    {location_filter}
GROUP BY
    dep.DEPARTMENT_NAME,
    zc_loc.NAME
ORDER BY
    dep.DEPARTMENT_NAME
"""

# Get NHSN location mapping
GET_NHSN_LOCATION_MAPPING = """
SELECT
    dep.DEPARTMENT_NAME AS clarity_location,
    nhsn_map.NHSN_LOCATION_CODE AS nhsn_code,
    nhsn_map.NHSN_LOCATION_TYPE AS nhsn_type
FROM
    CLARITY_DEP dep
    LEFT JOIN NHSN_LOCATION_MAPPING nhsn_map ON dep.DEPARTMENT_ID = nhsn_map.DEPARTMENT_ID
WHERE
    nhsn_map.ACTIVE_YN = 'Y'
"""
```

---

## 8. Phase 6: Antimicrobial Resistance (AR) Reporting

### 8.1 AR Overview

NHSN Antimicrobial Resistance (AR) reporting tracks resistance patterns at the facility level. Required quarterly.

**Key Components:**
- **Isolate-level data:** Organism + susceptibility results
- **First-isolate rule:** Only first isolate per patient per rolling 14-day window
- **Phenotype aggregation:** MRSA, VRE, ESBL, CRE percentages

### 8.2 AR Data Extractor

**File:** `nhsn-reporting/src/ar/extractor.py`

```python
"""
Antimicrobial Resistance (AR) data extraction for NHSN reporting.

Extracts:
- Culture isolates with susceptibility results
- Applies first-isolate rule (deduplication)
- Calculates resistance phenotype summaries
"""

from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import logging

from ..models import (
    ARQuarterlySummary, ARIsolate, Susceptibility, ARPhenotypeSummary
)
from ..data.clarity_source import ClarityDataSource

logger = logging.getLogger(__name__)


# NHSN Phenotype Definitions
PHENOTYPE_DEFINITIONS = {
    'MRSA': {
        'organism': 'Staphylococcus aureus',
        'resistance_criteria': [
            {'drug': 'oxacillin', 'interpretation': 'R'},
            {'drug': 'cefoxitin', 'interpretation': 'R'},
        ]
    },
    'VRE': {
        'organism': 'Enterococcus faecium|Enterococcus faecalis',
        'resistance_criteria': [
            {'drug': 'vancomycin', 'interpretation': 'R'},
        ]
    },
    'ESBL': {
        'organism': 'Escherichia coli|Klebsiella pneumoniae|Klebsiella oxytoca',
        'resistance_criteria': [
            {'drug': 'ceftriaxone', 'interpretation': 'R'},
            {'drug': 'ceftazidime', 'interpretation': 'R'},
        ]
    },
    'CRE': {
        'organism': 'Enterobacter|Escherichia coli|Klebsiella|Citrobacter|Serratia',
        'resistance_criteria': [
            {'drug': 'meropenem', 'interpretation': 'R'},
            {'drug': 'imipenem', 'interpretation': 'R'},
            {'drug': 'ertapenem', 'interpretation': 'R'},
        ]
    },
    'CRPA': {
        'organism': 'Pseudomonas aeruginosa',
        'resistance_criteria': [
            {'drug': 'meropenem', 'interpretation': 'R'},
            {'drug': 'imipenem', 'interpretation': 'R'},
            {'drug': 'ceftazidime', 'interpretation': 'R'},
            {'drug': 'piperacillin/tazobactam', 'interpretation': 'R'},
        ]
    },
    'CRAB': {
        'organism': 'Acinetobacter baumannii',
        'resistance_criteria': [
            {'drug': 'meropenem', 'interpretation': 'R'},
            {'drug': 'imipenem', 'interpretation': 'R'},
        ]
    },
}


class ARDataExtractor:
    """Extracts antimicrobial resistance data for NHSN AR reporting."""
    
    def __init__(
        self,
        clarity_source: Optional[ClarityDataSource] = None,
        first_isolate_window_days: int = 14
    ):
        self.clarity = clarity_source
        self.first_isolate_window = first_isolate_window_days
    
    def extract_quarterly_data(
        self,
        quarter: str,  # YYYY-Q# format
        locations: Optional[List[str]] = None
    ) -> List[ARQuarterlySummary]:
        """
        Extract AR data for a given quarter.
        
        Returns ARQuarterlySummary for each location with:
        - Isolates (deduplicated per first-isolate rule)
        - Phenotype summaries (MRSA, VRE, etc.)
        """
        # Parse quarter
        year, q_num = quarter.split('-Q')
        year = int(year)
        q_num = int(q_num)
        
        quarter_dates = {
            1: (date(year, 1, 1), date(year, 3, 31)),
            2: (date(year, 4, 1), date(year, 6, 30)),
            3: (date(year, 7, 1), date(year, 9, 30)),
            4: (date(year, 10, 1), date(year, 12, 31)),
        }
        start_date, end_date = quarter_dates[q_num]
        
        summaries = []
        
        # Get all isolates with susceptibilities
        raw_isolates = self._get_isolates_with_susceptibilities(
            start_date, end_date, locations
        )
        logger.info(f"Found {len(raw_isolates)} total isolates")
        
        # Apply first-isolate rule
        first_isolates = self._apply_first_isolate_rule(raw_isolates)
        logger.info(f"After first-isolate rule: {len(first_isolates)} isolates")
        
        # Group by location
        isolates_by_location: Dict[str, List[ARIsolate]] = {}
        for isolate in first_isolates:
            if isolate.location not in isolates_by_location:
                isolates_by_location[isolate.location] = []
            isolates_by_location[isolate.location].append(isolate)
        
        # Create summaries
        for location, isolates in isolates_by_location.items():
            phenotype_summaries = self._calculate_phenotype_summaries(isolates)
            
            summary = ARQuarterlySummary(
                id=f"ar-{quarter}-{location}",
                reporting_quarter=quarter,
                location=location,
                location_type=isolates[0].location_type if isolates else None,
                isolates=isolates,
                phenotype_summaries=phenotype_summaries
            )
            summaries.append(summary)
        
        return summaries
    
    def _get_isolates_with_susceptibilities(
        self,
        start_date: date,
        end_date: date,
        locations: Optional[List[str]]
    ) -> List[ARIsolate]:
        """Get culture isolates with susceptibility data."""
        if self.clarity:
            return self.clarity.get_isolates_with_susceptibilities(
                start_date, end_date, locations
            )
        else:
            raise ValueError("Clarity data source required for AR reporting")
    
    def _apply_first_isolate_rule(
        self,
        isolates: List[ARIsolate]
    ) -> List[ARIsolate]:
        """
        Apply NHSN first-isolate deduplication rule.
        
        For each patient + organism combination, only count the first
        isolate within a rolling window (typically 14 days).
        """
        # Sort by date
        sorted_isolates = sorted(isolates, key=lambda x: x.specimen_date)
        
        # Track seen patient+organism combinations
        seen: Dict[str, datetime] = {}  # (patient_id, organism) -> last_date
        first_isolates = []
        
        for isolate in sorted_isolates:
            key = (isolate.patient_id, isolate.organism_code)
            
            if key in seen:
                last_date = seen[key]
                days_since = (isolate.specimen_date - last_date).days
                
                if days_since < self.first_isolate_window:
                    # Within window, mark as duplicate
                    isolate.is_first_isolate = False
                    continue
            
            # First isolate or outside window
            isolate.is_first_isolate = True
            seen[key] = isolate.specimen_date
            first_isolates.append(isolate)
        
        return first_isolates
    
    def _calculate_phenotype_summaries(
        self,
        isolates: List[ARIsolate]
    ) -> List[ARPhenotypeSummary]:
        """Calculate resistance phenotype summaries."""
        summaries = []
        
        for phenotype_name, definition in PHENOTYPE_DEFINITIONS.items():
            # Filter isolates matching organism pattern
            import re
            organism_pattern = re.compile(definition['organism'], re.IGNORECASE)
            matching_isolates = [
                i for i in isolates
                if organism_pattern.search(i.organism_name)
            ]
            
            if not matching_isolates:
                continue
            
            # Count resistant isolates
            resistant_count = 0
            for isolate in matching_isolates:
                if self._is_resistant(isolate, definition['resistance_criteria']):
                    resistant_count += 1
            
            summary = ARPhenotypeSummary(
                organism_code=definition['organism'].split('|')[0],
                organism_name=definition['organism'].split('|')[0],
                phenotype=phenotype_name,
                isolate_count=len(matching_isolates),
                percent_resistant=(resistant_count / len(matching_isolates)) * 100
            )
            summaries.append(summary)
        
        return summaries
    
    def _is_resistant(
        self,
        isolate: ARIsolate,
        criteria: List[Dict]
    ) -> bool:
        """Check if isolate meets resistance criteria."""
        for criterion in criteria:
            for susc in isolate.susceptibilities:
                if (criterion['drug'].lower() in susc.antimicrobial_name.lower() and
                    susc.interpretation == criterion['interpretation']):
                    return True
        return False
```

---

## 9. Phase 7: Dashboard Enhancements

### 9.1 Dashboard Route Updates

**File:** `dashboard/routes/nhsn.py`

Add routes for new HAI types and AU/AR reporting:

```python
"""
NHSN Dashboard Routes - Extended for CAUTI, VAE, SSI, AU, AR
"""

from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, date

nhsn_bp = Blueprint('nhsn', __name__, url_prefix='/nhsn')


# ============================================================
# Overview and Stats
# ============================================================

@nhsn_bp.route('/')
def overview():
    """NHSN module overview with stats for all HAI types."""
    stats = {
        'clabsi': get_clabsi_stats(),
        'cauti': get_cauti_stats(),
        'vae': get_vae_stats(),
        'ssi': get_ssi_stats(),
    }
    return render_template('nhsn/overview.html', stats=stats)


@nhsn_bp.route('/stats')
def stats_api():
    """API endpoint for dashboard stats."""
    return jsonify({
        'clabsi': get_clabsi_stats(),
        'cauti': get_cauti_stats(),
        'vae': get_vae_stats(),
        'ssi': get_ssi_stats(),
        'au': get_au_stats(),
        'ar': get_ar_stats(),
    })


# ============================================================
# CAUTI Routes
# ============================================================

@nhsn_bp.route('/cauti')
def cauti_dashboard():
    """CAUTI surveillance dashboard."""
    return render_template('nhsn/cauti/dashboard.html')


@nhsn_bp.route('/cauti/candidates')
def cauti_candidates():
    """List CAUTI candidates."""
    candidates = db.get_cauti_candidates(status='pending')
    return render_template('nhsn/cauti/candidates.html', candidates=candidates)


@nhsn_bp.route('/cauti/reviews')
def cauti_reviews():
    """CAUTI IP review queue."""
    pending = db.get_cauti_candidates(status='classified')
    return render_template('nhsn/cauti/reviews.html', pending=pending)


@nhsn_bp.route('/cauti/review/<candidate_id>', methods=['GET', 'POST'])
def cauti_review(candidate_id):
    """Single CAUTI review page."""
    if request.method == 'POST':
        decision = request.form.get('decision')
        notes = request.form.get('notes')
        db.submit_cauti_review(
            candidate_id=candidate_id,
            decision=decision,
            reviewer=request.form.get('reviewer'),
            notes=notes
        )
        return redirect(url_for('nhsn.cauti_reviews'))
    
    candidate = db.get_cauti_candidate(candidate_id)
    classification = db.get_cauti_classification(candidate_id)
    return render_template(
        'nhsn/cauti/review.html',
        candidate=candidate,
        classification=classification
    )


# ============================================================
# VAE Routes
# ============================================================

@nhsn_bp.route('/vae')
def vae_dashboard():
    """VAE surveillance dashboard."""
    return render_template('nhsn/vae/dashboard.html')


@nhsn_bp.route('/vae/candidates')
def vae_candidates():
    """List VAE candidates."""
    candidates = db.get_vae_candidates(status='pending')
    return render_template('nhsn/vae/candidates.html', candidates=candidates)


@nhsn_bp.route('/vae/reviews')
def vae_reviews():
    """VAE IP review queue."""
    pending = db.get_vae_candidates(status='classified')
    return render_template('nhsn/vae/reviews.html', pending=pending)


# ============================================================
# SSI Routes
# ============================================================

@nhsn_bp.route('/ssi')
def ssi_dashboard():
    """SSI surveillance dashboard."""
    return render_template('nhsn/ssi/dashboard.html')


@nhsn_bp.route('/ssi/procedures')
def ssi_procedures():
    """List monitored surgical procedures."""
    procedures = db.get_ssi_procedures()
    return render_template('nhsn/ssi/procedures.html', procedures=procedures)


@nhsn_bp.route('/ssi/candidates')
def ssi_candidates():
    """List SSI candidates."""
    candidates = db.get_ssi_candidates(status='pending')
    return render_template('nhsn/ssi/candidates.html', candidates=candidates)


# ============================================================
# AU/AR Reporting Routes
# ============================================================

@nhsn_bp.route('/au')
def au_dashboard():
    """Antibiotic Usage reporting dashboard."""
    # Get recent months' data
    summaries = db.get_au_summaries(months=6)
    return render_template('nhsn/au/dashboard.html', summaries=summaries)


@nhsn_bp.route('/au/generate', methods=['POST'])
def au_generate():
    """Generate AU report for a month."""
    month = request.form.get('month')  # YYYY-MM
    locations = request.form.getlist('locations')
    
    from nhsn_reporting.src.au.extractor import AUDataExtractor
    extractor = AUDataExtractor()
    summaries = extractor.extract_monthly_usage(month, locations)
    
    # Store in database
    for summary in summaries:
        db.store_au_summary(summary)
    
    return redirect(url_for('nhsn.au_dashboard'))


@nhsn_bp.route('/au/export/<month>')
def au_export(month):
    """Export AU data for NHSN submission."""
    summaries = db.get_au_summaries_for_month(month)
    
    # Generate CSV
    csv_data = generate_au_csv(summaries)
    
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=AU_{month}.csv'}
    )


@nhsn_bp.route('/ar')
def ar_dashboard():
    """Antimicrobial Resistance reporting dashboard."""
    summaries = db.get_ar_summaries(quarters=4)
    return render_template('nhsn/ar/dashboard.html', summaries=summaries)


@nhsn_bp.route('/ar/generate', methods=['POST'])
def ar_generate():
    """Generate AR report for a quarter."""
    quarter = request.form.get('quarter')  # YYYY-Q#
    locations = request.form.getlist('locations')
    
    from nhsn_reporting.src.ar.extractor import ARDataExtractor
    extractor = ARDataExtractor()
    summaries = extractor.extract_quarterly_data(quarter, locations)
    
    for summary in summaries:
        db.store_ar_summary(summary)
    
    return redirect(url_for('nhsn.ar_dashboard'))


# ============================================================
# Combined Submission
# ============================================================

@nhsn_bp.route('/submission')
def submission():
    """NHSN submission page for all modules."""
    return render_template('nhsn/submission.html',
        hai_pending=db.get_pending_hai_submissions(),
        au_pending=db.get_pending_au_submissions(),
        ar_pending=db.get_pending_ar_submissions()
    )


@nhsn_bp.route('/submission/export', methods=['POST'])
def submission_export():
    """Export data for NHSN submission."""
    module = request.form.get('module')
    period = request.form.get('period')
    format_type = request.form.get('format', 'csv')
    
    # Route to appropriate exporter
    if module == 'hai':
        return export_hai_data(period, format_type)
    elif module == 'au':
        return export_au_data(period, format_type)
    elif module == 'ar':
        return export_ar_data(period, format_type)
```

### 9.2 Dashboard Templates Structure

```
dashboard/templates/nhsn/
├── overview.html           # Combined overview
├── submission.html         # Unified submission page
│
├── clabsi/                 # Existing CLABSI templates
│   ├── dashboard.html
│   ├── candidates.html
│   ├── reviews.html
│   └── review.html
│
├── cauti/                  # NEW: CAUTI templates
│   ├── dashboard.html
│   ├── candidates.html
│   ├── reviews.html
│   └── review.html
│
├── vae/                    # NEW: VAE templates
│   ├── dashboard.html
│   ├── candidates.html
│   ├── reviews.html
│   └── review.html
│
├── ssi/                    # NEW: SSI templates
│   ├── dashboard.html
│   ├── procedures.html
│   ├── candidates.html
│   ├── reviews.html
│   └── review.html
│
├── au/                     # NEW: Antibiotic Usage
│   ├── dashboard.html
│   ├── generate.html
│   └── report.html
│
└── ar/                     # NEW: Antimicrobial Resistance
    ├── dashboard.html
    ├── generate.html
    └── report.html
```

---

## 10. Implementation Checklist

### Phase 1: Infrastructure (Week 1-2)
- [ ] Extend database schema with new tables
- [ ] Add new models to `models.py`
- [ ] Update `config.py` with new settings
- [ ] Create abstract base classes if not present
- [ ] Set up test fixtures

### Phase 2: CAUTI Module (Week 3-4)
- [ ] Implement `CAUTICandidateDetector`
- [ ] Create CAUTI extraction prompt
- [ ] Implement `CAUTIExtractor`
- [ ] Implement `CAUTIRulesEngine`
- [ ] Implement `CAUTIClassifier`
- [ ] Add FHIR queries for urinary catheters
- [ ] Add Clarity queries for urinary catheters
- [ ] Create dashboard templates
- [ ] Write unit tests
- [ ] Create demo data generator

### Phase 3: VAE Module (Week 5-6)
- [ ] Implement `VAECandidateDetector`
- [ ] Create VAE extraction prompt
- [ ] Implement `VAEExtractor`
- [ ] Implement `VAERulesEngine`
- [ ] Implement `VAEClassifier`
- [ ] Add FHIR queries for ventilator data
- [ ] Add Clarity queries for ventilator flowsheets
- [ ] Create dashboard templates
- [ ] Write unit tests
- [ ] Create demo data generator

### Phase 4: SSI Module (Week 7-8)
- [ ] Define NHSN procedure code mappings
- [ ] Implement `SSICandidateDetector`
- [ ] Create SSI extraction prompt
- [ ] Implement `SSIExtractor`
- [ ] Implement `SSIRulesEngine`
- [ ] Implement `SSIClassifier`
- [ ] Add FHIR queries for procedures
- [ ] Add Clarity queries for surgical data
- [ ] Create dashboard templates
- [ ] Write unit tests
- [ ] Create demo data generator

### Phase 5: AU Reporting (Week 9-10)
- [ ] Implement `AUDataExtractor`
- [ ] Add Clarity MAR queries
- [ ] Create NHSN antimicrobial code mapping
- [ ] Implement DOT calculation
- [ ] Implement DDD calculation (optional)
- [ ] Create AU dashboard
- [ ] Implement CSV export
- [ ] Implement CDA generation for AU
- [ ] Write unit tests

### Phase 6: AR Reporting (Week 11-12)
- [ ] Implement `ARDataExtractor`
- [ ] Add Clarity culture/susceptibility queries
- [ ] Implement first-isolate deduplication
- [ ] Implement phenotype calculations
- [ ] Create AR dashboard
- [ ] Implement CSV export
- [ ] Implement CDA generation for AR
- [ ] Write unit tests

### Phase 7: Integration & Testing (Week 13-14)
- [ ] Unified submission page
- [ ] DIRECT protocol testing for new modules
- [ ] End-to-end testing with Synthea data
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] User acceptance testing

---

## 11. Testing Strategy

### Unit Tests

Each module should have unit tests for:
- Candidate detection logic
- Rules engine decision tree
- LLM extraction parsing
- Database operations
- CSV/CDA generation

Example test structure:
```
tests/
├── test_cauti_detector.py
├── test_cauti_rules.py
├── test_vae_detector.py
├── test_vae_rules.py
├── test_ssi_detector.py
├── test_ssi_rules.py
├── test_au_extractor.py
├── test_ar_extractor.py
└── fixtures/
    ├── cauti_test_cases.json
    ├── vae_test_cases.json
    └── ssi_test_cases.json
```

### Integration Tests

- FHIR data source integration
- Clarity data source integration
- LLM extraction accuracy
- Dashboard API endpoints
- NHSN export format validation

### Demo Data Generation

Extend Synthea modules or create scripts for:
- CAUTI scenarios (catheter + UTI combinations)
- VAE scenarios (ventilator worsening patterns)
- SSI scenarios (procedure + post-op infection)
- AU data (varied antimicrobial orders)
- AR data (resistant isolates)

---

## Appendix A: NHSN Reference Links

- [NHSN Patient Safety Manual](https://www.cdc.gov/nhsn/psc/index.html)
- [CLABSI Protocol](https://www.cdc.gov/nhsn/pdfs/pscmanual/4psc_clabscurrent.pdf)
- [CAUTI Protocol](https://www.cdc.gov/nhsn/pdfs/pscmanual/7psccauticurrent.pdf)
- [VAE Protocol](https://www.cdc.gov/nhsn/pdfs/pscmanual/10-vae_final.pdf)
- [SSI Protocol](https://www.cdc.gov/nhsn/pdfs/pscmanual/9pscssicurrent.pdf)
- [AU Module Protocol](https://www.cdc.gov/nhsn/pdfs/pscmanual/11pscauocurrent.pdf)
- [AR Module Protocol](https://www.cdc.gov/nhsn/pdfs/pscmanual/11pscauocurrent.pdf)

---

## Appendix B: Claude CLI Usage

To implement each phase, use Claude CLI with targeted prompts:

```bash
# Phase 1: Infrastructure
claude "Read AEGIS_IMPLEMENTATION_PLAN.md Phase 1. Implement the database schema extensions in nhsn-reporting/schema.sql"

# Phase 2: CAUTI
claude "Read AEGIS_IMPLEMENTATION_PLAN.md Phase 2. Implement the CAUTI candidate detector following the pattern in clabsi.py"

# Phase 3: VAE
claude "Read AEGIS_IMPLEMENTATION_PLAN.md Phase 3. Implement the VAE module including daily assessment tracking"

# And so on...
```

For incremental development:
```bash
# Start with detector
claude "Implement CAUTICandidateDetector based on the specification in AEGIS_IMPLEMENTATION_PLAN.md section 4.2"

# Then rules engine
claude "Implement CAUTIRulesEngine based on the specification in AEGIS_IMPLEMENTATION_PLAN.md section 4.3"

# Then classifier
claude "Implement CAUTIClassifier that orchestrates extraction and rules, based on section 4.4"
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: Claude (Anthropic)
