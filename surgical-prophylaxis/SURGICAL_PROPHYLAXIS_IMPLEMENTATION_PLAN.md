# AEGIS Surgical Antimicrobial Prophylaxis Module

## Implementation Plan

### Document Version
- **Version**: 1.0
- **Date**: January 2025
- **Author**: AEGIS Development Team
- **Status**: Planning

---

## Executive Summary

This document outlines the implementation plan for a standalone Surgical Antimicrobial Prophylaxis (SAP) module within AEGIS. The module will:

1. **Phase 1**: Monitor adherence to surgical prophylaxis guidelines (retrospective)
2. **Phase 2**: Provide real-time alerting when patients go to OR without appropriate prophylaxis orders (prospective)

The module addresses Joint Commission requirements (MM.09.01.01) and SCIP/CMS quality measures while reducing surgical site infections (SSIs) through evidence-based prophylaxis optimization.

---

## Table of Contents

1. [Background and Rationale](#1-background-and-rationale)
2. [Scope and Objectives](#2-scope-and-objectives)
3. [Evidence Base and Guidelines](#3-evidence-base-and-guidelines)
4. [Data Requirements](#4-data-requirements)
5. [Phase 1: Adherence Monitoring](#5-phase-1-adherence-monitoring)
6. [Phase 2: Real-Time Alerting](#6-phase-2-real-time-alerting)
7. [Technical Architecture](#7-technical-architecture)
8. [Dashboard Specifications](#8-dashboard-specifications)
9. [Integration Points](#9-integration-points)
10. [Implementation Timeline](#10-implementation-timeline)
11. [Success Metrics](#11-success-metrics)
12. [Risks and Mitigations](#12-risks-and-mitigations)
13. [NSQIP Reporting Integration](#13-nsqip-reporting-integration)
14. [Local CCHMC Guidelines](#14-local-cchmc-guidelines)
15. [Appendices](#15-appendices)

---

## 1. Background and Rationale

### 1.1 Clinical Problem

Surgical site infections (SSIs) are among the most common healthcare-associated infections, affecting 2-5% of surgical patients. Appropriate antimicrobial prophylaxis can reduce SSI rates by 50% or more, but adherence to evidence-based guidelines remains suboptimal:

| Metric | Typical Performance | Target |
|--------|---------------------|--------|
| Correct antibiotic selection | 70-85% | >95% |
| Timing within 60 min of incision | 75-90% | >95% |
| Discontinuation within 24h | 50-70% | >95% |
| Weight-based dosing | Variable | >95% |

### 1.2 Regulatory Requirements

- **Joint Commission MM.09.01.01**: Requires monitoring adherence to evidence-based guidelines
- **CMS SCIP Measures**: Prophylaxis timing and selection are publicly reported
- **Leapfrog Group**: SSI rates factor into hospital safety grades

### 1.3 Current State at Cincinnati Children's

- Surgical prophylaxis guidelines exist but adherence is not systematically tracked
- No automated alerting for missing prophylaxis orders
- Manual chart review for quality reporting is labor-intensive
- Prolonged prophylaxis (>24h) is common and contributes to antibiotic overuse

### 1.4 Opportunity

Automated monitoring and alerting can:
- Reduce SSI rates through improved prophylaxis compliance
- Decrease unnecessary antibiotic use (shorter duration)
- Free ASP pharmacists from manual surveillance
- Provide real-time decision support to surgical teams
- Generate automated quality reports for leadership and JC

---

## 2. Scope and Objectives

### 2.1 In Scope

| Category | Included |
|----------|----------|
| **Patient Population** | All surgical patients at CCHMC main campus |
| **Procedures** | All procedures in main OR, ambulatory surgery, cardiac OR, transplant |
| **Prophylaxis Elements** | Indication, agent selection, timing, dosing, duration |
| **Monitoring** | Retrospective adherence tracking, prospective alerting |
| **Reporting** | Dashboards, automated reports, drill-down capability |

### 2.2 Out of Scope (Initial Release)

- Interventional radiology procedures
- Bedside procedures (central line insertion, chest tube, etc.)
- Dental procedures
- Outpatient/clinic procedures
- Antibiotic allergy cross-reactivity logic (Phase 2+)

### 2.3 Objectives

| Objective | Metric | Target | Timeline |
|-----------|--------|--------|----------|
| Track prophylaxis adherence | Bundle compliance rate | Baseline → 90% | 6 months |
| Reduce prolonged prophylaxis | Duration >24h rate | Baseline → <10% | 6 months |
| Enable real-time alerting | Alert system live | Functional | 12 months |
| Automate quality reporting | Manual effort reduction | >80% reduction | 6 months |

---

## 3. Evidence Base and Guidelines

### 3.1 Primary Reference

**ASHP/IDSA/SHEA/SIS Clinical Practice Guidelines for Antimicrobial Prophylaxis in Surgery (2013)**

This is the definitive evidence-based guideline for surgical prophylaxis in the United States.

### 3.2 Key Recommendations

#### 3.2.1 Timing

| Recommendation | Evidence Level |
|----------------|----------------|
| Administer within 60 minutes before incision | Strong, High |
| For vancomycin/fluoroquinolones: within 120 minutes | Strong, Moderate |
| Repeat intraoperative dose if surgery exceeds 2 half-lives | Strong, Moderate |

#### 3.2.2 Agent Selection by Procedure Type

| Procedure Category | First-Line Agent | Alternative (β-lactam allergy) |
|--------------------|------------------|-------------------------------|
| **Cardiac** | Cefazolin | Vancomycin or Clindamycin |
| **Thoracic (non-cardiac)** | Cefazolin | Vancomycin or Clindamycin |
| **GI - Upper** | Cefazolin | Clindamycin + Aminoglycoside |
| **GI - Colorectal** | Cefazolin + Metronidazole | Clindamycin + Aminoglycoside |
| **Hepatobiliary** | Cefazolin | Clindamycin + Aminoglycoside |
| **Appendectomy (non-perforated)** | Cefazolin + Metronidazole | Clindamycin + Aminoglycoside |
| **Orthopedic (with implant)** | Cefazolin | Vancomycin or Clindamycin |
| **Neurosurgery (clean)** | Cefazolin | Vancomycin or Clindamycin |
| **Neurosurgery (CSF shunt)** | Cefazolin ± Vancomycin | Vancomycin |
| **Urologic (clean)** | None or Cefazolin | Fluoroquinolone |
| **Urologic (clean-contaminated)** | Cefazolin | Fluoroquinolone |
| **Vascular** | Cefazolin | Vancomycin or Clindamycin |
| **Transplant (solid organ)** | Per protocol | Per protocol |

#### 3.2.3 Duration

| Recommendation | Evidence Level |
|----------------|----------------|
| Discontinue within 24 hours of surgery end | Strong, High |
| Cardiac surgery: may extend to 48 hours | Weak, Low |
| Single dose often sufficient for clean procedures | Strong, Moderate |
| Do NOT continue until drains/catheters removed | Strong, High |

#### 3.2.4 Dosing

| Agent | Standard Dose | Weight-Based Adjustment |
|-------|---------------|------------------------|
| Cefazolin | 2g IV | 3g if weight >120 kg |
| Cefazolin (peds) | 30 mg/kg | Max 2g (or 3g if >120kg) |
| Vancomycin | 15 mg/kg | Max 2g; infuse over 1-2h |
| Metronidazole | 500 mg | 15 mg/kg in peds |
| Clindamycin | 900 mg | 10 mg/kg in peds |

#### 3.2.5 Redosing Intervals

| Agent | Redosing Interval | Half-Life |
|-------|-------------------|-----------|
| Cefazolin | 4 hours | 1.2-2.2 h |
| Cefoxitin | 2 hours | 0.7-1.1 h |
| Cefuroxime | 4 hours | 1-2 h |
| Ampicillin-sulbactam | 2 hours | 0.8-1.3 h |
| Clindamycin | 6 hours | 2-4 h |
| Vancomycin | Not typically needed | 4-8 h |
| Metronidazole | Not typically needed | 6-8 h |

### 3.3 Procedures NOT Requiring Prophylaxis

Per guidelines, prophylaxis is NOT routinely indicated for:

- Inguinal hernia repair (without mesh in low-risk patients)
- Myringotomy with tubes
- Adenoidectomy/tonsillectomy
- Clean laparoscopic procedures (cholecystectomy in low-risk)
- Cystoscopy without manipulation
- Circumcision
- Minor skin procedures

**Important**: Giving antibiotics for procedures that don't require them is also a form of non-adherence.

### 3.4 Local Adaptations

Cincinnati Children's may have local adaptations based on:
- Local antibiogram (MRSA prevalence)
- Transplant-specific protocols
- Cardiac surgery protocols
- Neurosurgery VP shunt protocols

These should be incorporated into the module configuration.

---

## 4. Data Requirements

### 4.1 Data Elements Needed

#### 4.1.1 Surgical Case Information

| Data Element | Source | FHIR Resource | Required |
|--------------|--------|---------------|----------|
| Scheduled procedure | OR scheduling | Procedure | Yes |
| CPT code(s) | Surgical posting | Procedure.code | Yes |
| Procedure description | OR scheduling | Procedure.code.text | Yes |
| Scheduled OR time | OR scheduling | Procedure.occurence | Yes |
| Actual incision time | Anesthesia record | Procedure.performedDateTime | Yes |
| Surgery end time | Anesthesia record | Procedure.performedPeriod.end | Yes |
| Surgeon | OR scheduling | Procedure.performer | Yes |
| OR location | OR scheduling | Procedure.location | Yes |
| Case classification | Surgical posting | Procedure.category | Desired |

#### 4.1.2 Patient Information

| Data Element | Source | FHIR Resource | Required |
|--------------|--------|---------------|----------|
| Patient MRN | ADT | Patient.identifier | Yes |
| Patient weight | Nursing flowsheet | Observation (weight) | Yes |
| Age | ADT | Patient.birthDate | Yes |
| Allergies | Allergy list | AllergyIntolerance | Yes |
| Renal function | Labs | Observation (creatinine) | Desired |
| MRSA colonization status | Lab/infection control | Observation | Desired |

#### 4.1.3 Antibiotic Orders and Administration

| Data Element | Source | FHIR Resource | Required |
|--------------|--------|---------------|----------|
| Antibiotic ordered | CPOE | MedicationRequest | Yes |
| Order time | CPOE | MedicationRequest.authoredOn | Yes |
| Dose ordered | CPOE | MedicationRequest.dosageInstruction | Yes |
| Route | CPOE | MedicationRequest.dosageInstruction.route | Yes |
| Administration time | MAR | MedicationAdministration.effectiveDateTime | Yes |
| Dose administered | MAR | MedicationAdministration.dosage | Yes |
| Infusion start/end | MAR | MedicationAdministration.effectivePeriod | Desired |
| Redose administered | MAR | MedicationAdministration | Yes |
| Last dose time | MAR | MedicationAdministration | Yes |

#### 4.1.4 Outcome Data (for SSI correlation - Phase 2+)

| Data Element | Source | FHIR Resource | Required |
|--------------|--------|---------------|----------|
| SSI diagnosis | Infection control | Condition | Future |
| SSI organism | Microbiology | Observation | Future |
| Readmission | ADT | Encounter | Future |

### 4.2 Data Access Methods

#### 4.2.1 Epic FHIR API (Preferred)

```
Endpoints needed:
- GET /Procedure (surgical cases)
- GET /MedicationRequest (antibiotic orders)
- GET /MedicationAdministration (MAR data)
- GET /Observation (weight, vitals)
- GET /AllergyIntolerance (allergies)
- GET /Patient (demographics)
```

#### 4.2.2 Direct Database Access (Alternative)

If FHIR is insufficient, direct access to:
- Clarity (Epic reporting database)
- Caboodle (Epic data warehouse)
- OR scheduling tables
- MAR tables

#### 4.2.3 HL7 ADT/ORM Feeds (Real-time alerting)

For prospective alerting, we need real-time notification when:
- Patient is scheduled for surgery (ORM)
- Patient arrives in pre-op (ADT)
- Patient enters OR (ADT location update)

### 4.3 Data Quality Considerations

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Missing incision time | Can't calculate timing | Use OR in time as proxy; flag for review |
| CPT code not posted | Can't determine prophylaxis requirements | Use procedure description; flag for review |
| Weight not documented | Can't assess dosing | Alert for missing weight |
| MAR not scanned | Appears as "not given" | Cross-reference with anesthesia record |

---

## 5. Phase 1: Adherence Monitoring

### 5.1 Overview

Phase 1 focuses on **retrospective** monitoring of surgical prophylaxis adherence. This establishes baseline performance, identifies improvement opportunities, and demonstrates value before implementing real-time alerting.

### 5.2 Bundle Elements

The SAP adherence bundle consists of 6 elements:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SURGICAL PROPHYLAXIS BUNDLE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. INDICATION          Was prophylaxis indicated (or appropriately        │
│     APPROPRIATE         withheld) for this procedure?                      │
│                                                                             │
│  2. AGENT               Was the antibiotic selection consistent with       │
│     SELECTION           guidelines for this procedure type?                │
│                                                                             │
│  3. TIMING              Was the antibiotic administered within 60 minutes  │
│                         (120 min for vancomycin) of incision?              │
│                                                                             │
│  4. WEIGHT-BASED        Was the dose appropriate for patient weight?       │
│     DOSING                                                                  │
│                                                                             │
│  5. INTRAOPERATIVE      Was redosing given if surgery exceeded             │
│     REDOSING            redosing interval?                                 │
│                                                                             │
│  6. TIMELY              Was prophylaxis discontinued within 24 hours       │
│     DISCONTINUATION     (48 hours for cardiac) of surgery end?             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Element Specifications

#### 5.3.1 Indication Appropriate

**Definition**: Prophylaxis was given for procedures that require it, AND withheld for procedures that don't require it.

**Logic**:
```python
def is_indication_appropriate(cpt_code: str, prophylaxis_given: bool) -> bool:
    """
    Check if prophylaxis indication matches procedure requirements.
    """
    procedure_info = PROPHYLAXIS_REQUIREMENTS.get(cpt_code)
    
    if procedure_info is None:
        return None  # Unable to assess - CPT not in table
    
    if procedure_info.prophylaxis_indicated:
        # Prophylaxis IS indicated - was it given?
        return prophylaxis_given
    else:
        # Prophylaxis NOT indicated - was it appropriately withheld?
        return not prophylaxis_given
```

**Compliance**:
- ✅ Prophylaxis given for procedure that requires it
- ✅ Prophylaxis withheld for procedure that doesn't require it
- ❌ Prophylaxis NOT given for procedure that requires it
- ❌ Prophylaxis given for procedure that doesn't require it

#### 5.3.2 Agent Selection

**Definition**: The antibiotic selected matches guideline recommendations for the procedure type.

**Logic**:
```python
def is_agent_appropriate(
    cpt_code: str, 
    antibiotic_given: str,
    has_beta_lactam_allergy: bool
) -> Tuple[bool, str]:
    """
    Check if antibiotic selection matches guidelines.
    
    Returns:
        (compliant, reason)
    """
    procedure_info = PROPHYLAXIS_REQUIREMENTS.get(cpt_code)
    
    if has_beta_lactam_allergy:
        acceptable_agents = procedure_info.alternative_agents
    else:
        acceptable_agents = procedure_info.first_line_agents
    
    if antibiotic_given.lower() in [a.lower() for a in acceptable_agents]:
        return (True, f"Appropriate: {antibiotic_given}")
    else:
        return (False, f"Expected {acceptable_agents}, got {antibiotic_given}")
```

**Considerations**:
- β-lactam allergy affects agent selection
- Some procedures require combination therapy (cefazolin + metronidazole)
- MRSA colonization may warrant vancomycin addition
- Local protocols may differ from national guidelines

#### 5.3.3 Timing

**Definition**: Antibiotic administered within 60 minutes before incision (120 minutes for vancomycin/fluoroquinolones).

**Logic**:
```python
def is_timing_appropriate(
    incision_time: datetime,
    administration_time: datetime,
    antibiotic: str
) -> Tuple[bool, int]:
    """
    Check if antibiotic was given in appropriate window before incision.
    
    Returns:
        (compliant, minutes_before_incision)
    """
    minutes_before = (incision_time - administration_time).total_seconds() / 60
    
    # Determine acceptable window based on antibiotic
    if antibiotic.lower() in ['vancomycin', 'ciprofloxacin', 'levofloxacin']:
        max_minutes_before = 120
    else:
        max_minutes_before = 60
    
    # Must be BEFORE incision (positive) and within window
    if 0 < minutes_before <= max_minutes_before:
        return (True, int(minutes_before))
    elif minutes_before <= 0:
        return (False, int(minutes_before))  # Given AFTER incision
    else:
        return (False, int(minutes_before))  # Given too early
```

**Edge Cases**:
- Antibiotic given AFTER incision: Non-compliant (flag for urgent review)
- Antibiotic given >60 min before incision: Non-compliant (reduced efficacy)
- Multiple antibiotics: Each must meet timing requirements
- Infusion start time vs. end time: Use START time for assessment

#### 5.3.4 Weight-Based Dosing

**Definition**: Dose is appropriate for patient weight per guidelines.

**Logic**:
```python
def is_dose_appropriate(
    antibiotic: str,
    dose_mg: float,
    patient_weight_kg: float,
    patient_age_years: float
) -> Tuple[bool, str]:
    """
    Check if dose is appropriate for patient weight.
    """
    dosing_info = ANTIBIOTIC_DOSING.get(antibiotic.lower())
    
    if patient_age_years < 18:
        # Pediatric dosing
        expected_dose = patient_weight_kg * dosing_info.peds_mg_per_kg
        expected_dose = min(expected_dose, dosing_info.peds_max_dose)
    else:
        # Adult dosing
        if patient_weight_kg > 120:
            expected_dose = dosing_info.adult_high_weight_dose
        else:
            expected_dose = dosing_info.adult_standard_dose
    
    # Allow 10% variance
    if 0.9 * expected_dose <= dose_mg <= 1.1 * expected_dose:
        return (True, f"Dose appropriate: {dose_mg}mg")
    else:
        return (False, f"Expected ~{expected_dose}mg, got {dose_mg}mg")
```

**Pediatric Considerations**:
- Use mg/kg dosing with maximum dose caps
- Weight documentation is critical
- Neonates may have different dosing

#### 5.3.5 Intraoperative Redosing

**Definition**: If surgery duration exceeds the redosing interval, an additional dose was given.

**Logic**:
```python
def is_redosing_appropriate(
    antibiotic: str,
    surgery_duration_hours: float,
    doses_given: List[datetime]
) -> Tuple[bool, str]:
    """
    Check if redosing was given for prolonged surgery.
    """
    redose_interval = REDOSING_INTERVALS.get(antibiotic.lower())
    
    if redose_interval is None:
        return (True, "Redosing not typically required for this agent")
    
    # Calculate expected number of doses
    expected_doses = 1 + int(surgery_duration_hours / redose_interval)
    actual_doses = len(doses_given)
    
    if actual_doses >= expected_doses:
        return (True, f"Appropriate: {actual_doses} doses for {surgery_duration_hours:.1f}h surgery")
    else:
        return (False, f"Expected {expected_doses} doses, got {actual_doses}")
```

**Considerations**:
- Blood loss >1500 mL may warrant redosing regardless of time
- Redosing intervals vary by antibiotic (cefazolin q4h, cefoxitin q2h)
- Vancomycin and metronidazole typically don't require redosing

#### 5.3.6 Timely Discontinuation

**Definition**: Prophylaxis discontinued within 24 hours of surgery end (48 hours for cardiac surgery).

**Logic**:
```python
def is_discontinuation_timely(
    surgery_end_time: datetime,
    last_dose_time: datetime,
    procedure_category: str
) -> Tuple[bool, float]:
    """
    Check if prophylaxis was stopped within guideline timeframe.
    
    Returns:
        (compliant, hours_of_prophylaxis)
    """
    hours_of_prophylaxis = (last_dose_time - surgery_end_time).total_seconds() / 3600
    
    # Cardiac surgery gets 48h, all others 24h
    if procedure_category == 'cardiac':
        max_hours = 48
    else:
        max_hours = 24
    
    if hours_of_prophylaxis <= max_hours:
        return (True, hours_of_prophylaxis)
    else:
        return (False, hours_of_prophylaxis)
```

**Note**: This is often the lowest-performing element. Prolonged prophylaxis is common but NOT beneficial and contributes to:
- C. difficile infection
- Antibiotic resistance
- Unnecessary cost

### 5.4 Bundle Compliance Calculation

```python
def calculate_bundle_compliance(elements: Dict[str, bool]) -> float:
    """
    Calculate overall bundle compliance.
    
    Bundle is COMPLIANT only if ALL applicable elements are met.
    Individual element compliance is reported separately.
    """
    applicable_elements = {k: v for k, v in elements.items() if v is not None}
    
    if not applicable_elements:
        return None
    
    met_elements = sum(1 for v in applicable_elements.values() if v)
    total_elements = len(applicable_elements)
    
    # Overall compliance: 100% if all met, otherwise calculate percentage
    all_or_nothing = all(applicable_elements.values())
    element_percentage = met_elements / total_elements * 100
    
    return {
        'bundle_compliant': all_or_nothing,
        'element_compliance_rate': element_percentage,
        'elements_met': met_elements,
        'elements_total': total_elements
    }
```

### 5.5 Exclusion Criteria

Some cases should be excluded from adherence measurement:

| Exclusion | Rationale |
|-----------|-----------|
| Emergency surgery | Timing may not be achievable |
| Therapeutic antibiotics | Patient already on treatment |
| Documented infection | Prophylaxis not applicable |
| Allergy with no alternative | May need ID consult |
| Incomplete data | Can't assess compliance |

Exclusions should be tracked and reported separately.

### 5.6 Data Collection Frequency

| Approach | Frequency | Use Case |
|----------|-----------|----------|
| Real-time | Continuous | Dashboard updates |
| Daily batch | Overnight | Worklist generation |
| Weekly report | Every Monday | Leadership review |
| Monthly report | End of month | Quality committee |
| Quarterly report | End of quarter | JC documentation |

---

## 6. Phase 2: Real-Time Alerting

### 6.1 Overview

Phase 2 implements **prospective** alerting to prevent prophylaxis failures before they occur. The system monitors surgical patients and alerts when prophylaxis orders are missing or timing is at risk.

### 6.2 Alert Triggers

#### 6.2.1 Missing Prophylaxis Order

**Trigger**: Patient scheduled for surgery requiring prophylaxis, but no prophylaxis order exists.

**Timing**: 
- Alert 1: When surgery is scheduled (for next-day cases)
- Alert 2: When patient arrives in pre-op holding
- Alert 3: 60 minutes before scheduled OR time

**Alert Escalation**:
```
T-24h:  Passive notification to pre-op pharmacy
T-2h:   Alert to circulating nurse/pre-op nurse
T-60m:  Alert to anesthesiologist + page to surgical team
T-30m:  Escalate to OR charge nurse + ASP pharmacist
T-0:    Prevent OR entry? (requires governance approval)
```

#### 6.2.2 Timing at Risk

**Trigger**: Prophylaxis order exists, but patient approaching OR without documented administration.

**Logic**:
```python
def check_timing_risk(
    scheduled_or_time: datetime,
    current_time: datetime,
    prophylaxis_order_exists: bool,
    prophylaxis_administered: bool,
    antibiotic: str
) -> Optional[Alert]:
    """
    Check if prophylaxis timing is at risk.
    """
    minutes_to_or = (scheduled_or_time - current_time).total_seconds() / 60
    
    # Determine required lead time
    if antibiotic and antibiotic.lower() in ['vancomycin']:
        required_lead_time = 90  # Need time for infusion
    else:
        required_lead_time = 30
    
    if not prophylaxis_order_exists:
        if minutes_to_or <= 60:
            return Alert(
                severity='HIGH',
                message='No prophylaxis order - patient approaching OR',
                action='Contact surgical team immediately'
            )
    elif not prophylaxis_administered:
        if minutes_to_or <= required_lead_time:
            return Alert(
                severity='MEDIUM',
                message='Prophylaxis ordered but not yet given',
                action='Verify antibiotic is being prepared/infusing'
            )
    
    return None
```

#### 6.2.3 Prolonged Prophylaxis

**Trigger**: 24 hours (or 48h for cardiac) have elapsed since surgery end, and prophylaxis orders are still active.

**Alert**:
```
"Surgical prophylaxis has exceeded 24 hours for patient [MRN].
Surgery completed: [date/time]
Current prophylaxis: [antibiotic]

Per guidelines, prophylaxis should be discontinued.

☐ Discontinue prophylaxis (recommended)
☐ Continue for documented infection (requires diagnosis entry)
☐ Defer to ID consult
```

### 6.3 Alert Delivery Methods

| Method | Use Case | Response Required |
|--------|----------|-------------------|
| Epic BPA | Interruptive, at order entry | Acknowledge or override |
| In-basket message | Non-urgent, for awareness | Review within shift |
| Secure text/page | Urgent, needs action now | Immediate response |
| Dashboard flag | Visibility for monitoring | No response required |
| Daily worklist | Batch review | Complete by end of day |

### 6.4 Alert Logic Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     REAL-TIME ALERT DECISION TREE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Surgical case identified                                                   │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────┐                                                        │
│  │ Prophylaxis     │──── NO ───▶ Check exclusion criteria                  │
│  │ indicated?      │             │                                          │
│  └────────┬────────┘             │                                          │
│           │ YES                  ▼                                          │
│           │              ┌─────────────────┐                                │
│           │              │ Excluded?       │──── YES ──▶ No alert          │
│           │              └────────┬────────┘                                │
│           │                       │ NO                                      │
│           │                       ▼                                          │
│           │              ┌─────────────────┐                                │
│           │              │ ALERT:          │                                │
│           ▼              │ No prophylaxis  │                                │
│  ┌─────────────────┐     │ needed for this │                                │
│  │ Order exists?   │──── NO ───▶ procedure      │                          │
│  └────────┬────────┘     └─────────────────┘                                │
│           │ YES                                                             │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │ Agent           │──── NO ───▶ ALERT: Agent mismatch                     │
│  │ appropriate?    │                                                        │
│  └────────┬────────┘                                                        │
│           │ YES                                                             │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │ Given within    │──── NO ───▶ ALERT: Timing at risk                     │
│  │ window?         │                                                        │
│  └────────┬────────┘                                                        │
│           │ YES                                                             │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │ Dose            │──── NO ───▶ ALERT: Dose adjustment needed             │
│  │ appropriate?    │                                                        │
│  └────────┬────────┘                                                        │
│           │ YES                                                             │
│           ▼                                                                  │
│       ✓ Compliant                                                           │
│                                                                             │
│  [Post-surgery monitoring for duration continues separately]                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.5 Alert Fatigue Mitigation

To prevent alert fatigue:

1. **Tiered severity**: Only high-severity alerts are interruptive
2. **Smart suppression**: Don't re-alert if action taken within 30 min
3. **Batch similar alerts**: Combine multiple issues into single alert
4. **Positive feedback**: Show compliance metrics to reinforce good practice
5. **Continuous refinement**: Track override rates and adjust thresholds

### 6.6 Alert Response Tracking

```python
@dataclass
class AlertResponse:
    """Track response to prophylaxis alerts."""
    alert_id: str
    alert_type: str
    alert_time: datetime
    patient_mrn: str
    encounter_id: str
    
    response_time: Optional[datetime]
    response_action: str  # 'acknowledged', 'overridden', 'corrected', 'ignored'
    override_reason: Optional[str]
    
    # Outcome tracking
    prophylaxis_ultimately_given: bool
    timing_ultimately_appropriate: bool
```

---

## 7. Technical Architecture

### 7.1 System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SURGICAL PROPHYLAXIS MODULE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  DATA INGESTION │    │  EVALUATION     │    │  OUTPUT         │         │
│  │                 │    │  ENGINE         │    │                 │         │
│  │  • FHIR API     │───▶│                 │───▶│  • Dashboard    │         │
│  │  • HL7 feeds    │    │  • Indication   │    │  • Alerts       │         │
│  │  • Database     │    │  • Agent        │    │  • Reports      │         │
│  │                 │    │  • Timing       │    │  • Worklists    │         │
│  │                 │    │  • Dosing       │    │                 │         │
│  │                 │    │  • Redosing     │    │                 │         │
│  │                 │    │  • Duration     │    │                 │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│           │                      │                      │                   │
│           └──────────────────────┼──────────────────────┘                   │
│                                  ▼                                          │
│                     ┌─────────────────────┐                                 │
│                     │  CONFIGURATION      │                                 │
│                     │                     │                                 │
│                     │  • CPT → Procedure  │                                 │
│                     │  • Agent tables     │                                 │
│                     │  • Dosing tables    │                                 │
│                     │  • Local overrides  │                                 │
│                     └─────────────────────┘                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Module Structure

```
aegis/
├── surgical_prophylaxis/
│   ├── __init__.py
│   │
│   ├── config/
│   │   ├── procedure_requirements.py    # CPT → prophylaxis mapping
│   │   ├── antibiotic_dosing.py         # Dosing tables
│   │   ├── redosing_intervals.py        # Intraop redosing
│   │   └── local_protocols.py           # CCHMC-specific overrides
│   │
│   ├── core/
│   │   ├── models.py                    # Data classes
│   │   ├── evaluator.py                 # Bundle evaluation logic
│   │   ├── timing.py                    # Timing calculations
│   │   └── dosing.py                    # Dose calculations
│   │
│   ├── data/
│   │   ├── fhir_client.py               # FHIR data access
│   │   ├── hl7_listener.py              # Real-time HL7 feeds
│   │   └── queries.py                   # Database queries
│   │
│   ├── alerts/
│   │   ├── alert_engine.py              # Alert generation
│   │   ├── alert_router.py              # Alert delivery
│   │   └── alert_tracking.py            # Response tracking
│   │
│   ├── reporting/
│   │   ├── metrics.py                   # Aggregate calculations
│   │   ├── dashboard.py                 # Dashboard data
│   │   └── exports.py                   # Report generation
│   │
│   └── tests/
│       ├── test_evaluator.py
│       ├── test_timing.py
│       ├── test_dosing.py
│       └── test_alerts.py
```

### 7.3 Key Classes

```python
# Core data models
@dataclass
class SurgicalCase:
    """Represents a surgical case for evaluation."""
    case_id: str
    patient_mrn: str
    encounter_id: str
    
    # Procedure info
    cpt_codes: List[str]
    procedure_description: str
    procedure_category: str  # 'cardiac', 'ortho', 'neuro', etc.
    
    # Timing
    scheduled_or_time: datetime
    actual_incision_time: Optional[datetime]
    surgery_end_time: Optional[datetime]
    
    # Patient factors
    patient_weight_kg: float
    patient_age_years: float
    allergies: List[str]
    mrsa_colonized: bool
    
    # Prophylaxis data
    prophylaxis_orders: List[MedicationOrder]
    prophylaxis_administrations: List[MedicationAdministration]


@dataclass
class ProphylaxisEvaluation:
    """Result of prophylaxis bundle evaluation."""
    case_id: str
    evaluation_time: datetime
    
    # Element results
    indication_appropriate: Optional[bool]
    agent_appropriate: Optional[bool]
    timing_appropriate: Optional[bool]
    dose_appropriate: Optional[bool]
    redosing_appropriate: Optional[bool]
    duration_appropriate: Optional[bool]
    
    # Details
    element_details: Dict[str, str]
    
    # Summary
    bundle_compliant: bool
    compliance_score: float
    flags: List[str]
    recommendations: List[str]


class ProphylaxisEvaluator:
    """Main evaluation engine."""
    
    def evaluate_case(self, case: SurgicalCase) -> ProphylaxisEvaluation:
        """Evaluate a surgical case for prophylaxis compliance."""
        pass
    
    def evaluate_batch(self, cases: List[SurgicalCase]) -> List[ProphylaxisEvaluation]:
        """Evaluate multiple cases."""
        pass
    
    def check_realtime(self, case: SurgicalCase) -> Optional[Alert]:
        """Check for real-time alerting needs."""
        pass
```

### 7.4 Database Schema

```sql
-- Core tables for surgical prophylaxis tracking

CREATE TABLE surgical_cases (
    case_id VARCHAR(50) PRIMARY KEY,
    patient_mrn VARCHAR(20) NOT NULL,
    encounter_id VARCHAR(50) NOT NULL,
    
    -- Procedure info
    primary_cpt VARCHAR(10),
    procedure_description TEXT,
    procedure_category VARCHAR(50),
    surgeon_id VARCHAR(50),
    
    -- Timing
    scheduled_or_time TIMESTAMP,
    actual_incision_time TIMESTAMP,
    surgery_end_time TIMESTAMP,
    
    -- Patient factors
    patient_weight_kg DECIMAL(5,2),
    patient_age_years DECIMAL(5,2),
    has_beta_lactam_allergy BOOLEAN,
    mrsa_colonized BOOLEAN,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prophylaxis_evaluations (
    evaluation_id SERIAL PRIMARY KEY,
    case_id VARCHAR(50) REFERENCES surgical_cases(case_id),
    evaluation_time TIMESTAMP NOT NULL,
    
    -- Element compliance
    indication_appropriate BOOLEAN,
    agent_appropriate BOOLEAN,
    timing_appropriate BOOLEAN,
    dose_appropriate BOOLEAN,
    redosing_appropriate BOOLEAN,
    duration_appropriate BOOLEAN,
    
    -- Summary
    bundle_compliant BOOLEAN,
    compliance_score DECIMAL(5,2),
    
    -- Details (JSON)
    element_details JSONB,
    flags TEXT[],
    recommendations TEXT[],
    
    -- Exclusion tracking
    excluded BOOLEAN DEFAULT FALSE,
    exclusion_reason VARCHAR(100),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prophylaxis_alerts (
    alert_id SERIAL PRIMARY KEY,
    case_id VARCHAR(50) REFERENCES surgical_cases(case_id),
    alert_type VARCHAR(50) NOT NULL,
    alert_severity VARCHAR(20) NOT NULL,
    alert_message TEXT,
    
    -- Timing
    alert_time TIMESTAMP NOT NULL,
    response_time TIMESTAMP,
    
    -- Response
    response_action VARCHAR(50),
    override_reason TEXT,
    responder_id VARCHAR(50),
    
    -- Outcome
    prophylaxis_ultimately_given BOOLEAN,
    timing_ultimately_appropriate BOOLEAN,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_cases_encounter ON surgical_cases(encounter_id);
CREATE INDEX idx_cases_scheduled ON surgical_cases(scheduled_or_time);
CREATE INDEX idx_evals_case ON prophylaxis_evaluations(case_id);
CREATE INDEX idx_evals_time ON prophylaxis_evaluations(evaluation_time);
CREATE INDEX idx_alerts_case ON prophylaxis_alerts(case_id);
CREATE INDEX idx_alerts_time ON prophylaxis_alerts(alert_time);
```

---

## 8. Dashboard Specifications

### 8.1 Main Dashboard View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AEGIS - Surgical Prophylaxis Dashboard                     [Date Range ▼]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ OVERALL BUNDLE COMPLIANCE                         This Month: 847    │   │
│  │                                                   surgical cases     │   │
│  │   ████████████████████████████████░░░░░░░░  82.4%                   │   │
│  │                                                                      │   │
│  │   Target: 90%    |    Prior Month: 78.2%    |    Trend: ↑ 4.2%      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ELEMENT-LEVEL COMPLIANCE                                             │   │
│  │                                                                      │   │
│  │  Indication appropriate    █████████████████████████████████  96%   │   │
│  │  Agent selection           ████████████████████████████░░░░░  89%   │   │
│  │  Timing (within 60 min)    ███████████████████████████░░░░░░  87%   │   │
│  │  Weight-based dosing       ██████████████████████████░░░░░░░  84%   │   │
│  │  Intraop redosing          █████████████████████████████████  95%   │   │
│  │  Duration ≤24h             █████████████████░░░░░░░░░░░░░░░░  62%   │◀─ │
│  │                                                                      │   │
│  │  ◀─ Opportunity: 38% of cases had prophylaxis >24 hours             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │ BY SERVICE                   │  │ BY PROCEDURE TYPE               │   │
│  │                              │  │                                  │   │
│  │ Cardiac      ████████░ 81%   │  │ Ortho/Spine    ████████░ 79%   │   │
│  │ General      █████████ 88%   │  │ Cardiac        ████████░ 81%   │   │
│  │ Ortho        ████████░ 79%   │  │ Neuro          █████████ 85%   │   │
│  │ Neuro        █████████ 85%   │  │ GI/Colorectal  █████████ 87%   │   │
│  │ Urology      █████████ 91%   │  │ Transplant     █████████ 90%   │   │
│  │ Transplant   █████████ 90%   │  │ ENT            ██████████ 94%   │   │
│  └──────────────────────────────┘  └──────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ TREND (Last 12 Months)                                               │   │
│  │                                                                      │   │
│  │  100% ┤                                                              │   │
│  │   90% ┤                              ╭─────────────╮                 │   │
│  │   80% ┤         ╭────────────────────╯             ╰────            │   │
│  │   70% ┤    ╭────╯                                                    │   │
│  │   60% ┤────╯                                                         │   │
│  │       └────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────  │   │
│  │        Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct  Nov  Dec  Jan   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [View Non-Compliant Cases]  [Generate Report]  [Alert Settings]           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Non-Compliant Case Drill-Down

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Non-Compliant Cases - January 2025                        [Export] [Filter] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Filters: [Service ▼] [Procedure ▼] [Element ▼] [Surgeon ▼]                │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case   │ Date  │ Procedure        │ Issue           │ Details       │   │
│  ├────────┼───────┼──────────────────┼─────────────────┼───────────────┤   │
│  │ 12345  │ 01/05 │ Lap appendectomy │ Duration >24h   │ 72h total     │   │
│  │ 12346  │ 01/05 │ VP shunt         │ Timing late     │ 85 min before │   │
│  │ 12350  │ 01/06 │ Spinal fusion    │ Duration >24h   │ 48h total     │   │
│  │ 12352  │ 01/06 │ Colectomy        │ Agent mismatch  │ No metronidaz │   │
│  │ 12358  │ 01/07 │ Cardiac          │ Dose low        │ 1g (wt 85kg)  │   │
│  │ ...                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Common Issues This Period:                                                 │
│  ┌────────────────────────────────────────────────┐                        │
│  │ 1. Duration >24h              │ 89 cases (62%)  │                        │
│  │ 2. Timing >60 min from incis  │ 28 cases (19%)  │                        │
│  │ 3. Suboptimal agent           │ 15 cases (10%)  │                        │
│  │ 4. Dose not weight-adjusted   │ 12 cases  (8%)  │                        │
│  └────────────────────────────────────────────────┘                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Real-Time Monitoring View (Phase 2)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AEGIS - Surgical Prophylaxis Real-Time Monitor              🔴 3 Alerts     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ACTIVE ALERTS                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🔴 HIGH │ OR 5 │ Spinal fusion │ No prophylaxis order │ OR in 45 min│   │
│  │         │      │ MRN: 123456   │ Surgeon notified     │             │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │ 🟡 MED  │ OR 3 │ Colectomy     │ Missing metronidazole│ OR in 90 min│   │
│  │         │      │ MRN: 234567   │ Pharmacy contacted   │             │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │ 🟡 MED  │ PACU │ Cardiac valve │ >24h prophylaxis     │ D/C needed  │   │
│  │         │      │ MRN: 345678   │ Awaiting response    │             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  UPCOMING SURGERIES (Next 4 Hours)                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Time  │ OR │ Procedure           │ Prophylaxis Status    │ Status   │   │
│  ├───────┼────┼─────────────────────┼───────────────────────┼──────────┤   │
│  │ 10:00 │ 1  │ Craniotomy          │ Cefazolin ordered ✓   │ 🟢 Ready │   │
│  │ 10:00 │ 2  │ Lap chole           │ Cefazolin ordered ✓   │ 🟢 Ready │   │
│  │ 10:30 │ 3  │ Colectomy           │ Cefazolin only ⚠      │ 🟡 Review│   │
│  │ 10:30 │ 4  │ T&A                 │ Not indicated         │ 🟢 N/A   │   │
│  │ 11:00 │ 5  │ Spinal fusion       │ NO ORDER ⛔           │ 🔴 Alert │   │
│  │ 11:00 │ 6  │ Kidney transplant   │ Per protocol ✓        │ 🟢 Ready │   │
│  │ 11:30 │ 7  │ Hernia repair       │ Cefazolin ordered ✓   │ 🟢 Ready │   │
│  │ 12:00 │ 8  │ VP shunt revision   │ Cefazolin+Vanc ✓      │ 🟢 Ready │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  TODAY'S STATISTICS                                                         │
│  ┌────────────────┬────────────────┬────────────────┬────────────────┐     │
│  │ Cases Today    │ Compliant      │ Alerts Fired   │ Alerts Resolved│     │
│  │      28        │    24 (86%)    │       7        │     4 (57%)    │     │
│  └────────────────┴────────────────┴────────────────┴────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Integration Points

### 9.1 Epic Integration

| Integration | Method | Purpose |
|-------------|--------|---------|
| OR scheduling | FHIR Procedure | Identify upcoming surgeries |
| Antibiotic orders | FHIR MedicationRequest | Check prophylaxis orders |
| MAR | FHIR MedicationAdministration | Verify administration timing |
| Patient data | FHIR Patient, Observation | Weight, allergies |
| Anesthesia record | Direct query or interface | Incision/closure times |
| BPA alerts | Epic CDS Hooks | Real-time interruptive alerts |

### 9.2 AEGIS Platform Integration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AEGIS PLATFORM                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐                                                    │
│  │ Antibiotic          │◀──── Shares antibiotic classification tables      │
│  │ Appropriateness     │                                                    │
│  │ Module              │                                                    │
│  └─────────────────────┘                                                    │
│           │                                                                  │
│           │ Flags surgical patients                                         │
│           ▼                                                                  │
│  ┌─────────────────────┐                                                    │
│  │ SURGICAL            │                                                    │
│  │ PROPHYLAXIS         │◀──── New standalone module                        │
│  │ MODULE              │                                                    │
│  └─────────────────────┘                                                    │
│           │                                                                  │
│           │ Contributes to guideline adherence metrics                      │
│           ▼                                                                  │
│  ┌─────────────────────┐                                                    │
│  │ Guideline           │                                                    │
│  │ Adherence           │◀──── Surgical prophylaxis is one of the bundles   │
│  │ Dashboard           │                                                    │
│  └─────────────────────┘                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 External Reporting

| Report | Frequency | Recipient |
|--------|-----------|-----------|
| Monthly compliance | Monthly | Surgery leadership, ASP |
| Quarterly summary | Quarterly | Quality committee, CMO |
| JC documentation | Annual/On demand | Regulatory/compliance |
| SCIP measures | As required | CMS reporting |

---

## 10. Implementation Timeline

### 10.1 Phase 1: Adherence Monitoring (Months 1-6)

```
Month 1-2: Foundation
├── Week 1-2: Finalize data requirements with IT
├── Week 3-4: Build CPT → prophylaxis mapping table
├── Week 5-6: Develop evaluation engine core logic
└── Week 7-8: Create FHIR data access layer

Month 3-4: Core Development
├── Week 9-10: Implement all 6 bundle elements
├── Week 11-12: Build database schema and storage
├── Week 13-14: Develop dashboard views
└── Week 15-16: Create reporting exports

Month 5-6: Validation and Launch
├── Week 17-18: Retrospective validation (100 cases)
├── Week 19-20: Refine logic based on validation
├── Week 21-22: User acceptance testing
├── Week 23-24: Go-live with monitoring dashboard
```

### 10.2 Phase 2: Real-Time Alerting (Months 7-12)

```
Month 7-8: Alert Infrastructure
├── Week 25-26: Develop HL7 listener for real-time feeds
├── Week 27-28: Build alert engine core
├── Week 29-30: Implement alert routing
└── Week 31-32: Create response tracking

Month 9-10: Alert Development
├── Week 33-34: Missing order alerts
├── Week 35-36: Timing risk alerts
├── Week 37-38: Duration alerts
└── Week 39-40: Alert escalation logic

Month 11-12: Deployment
├── Week 41-42: Pilot in 2 ORs
├── Week 43-44: Refine based on pilot feedback
├── Week 45-46: Expand to all ORs
├── Week 47-48: Full go-live with alerting
```

### 10.3 Milestones

| Milestone | Target Date | Success Criteria |
|-----------|-------------|------------------|
| Data access confirmed | Month 1 | Can query all required data elements |
| Evaluation engine complete | Month 3 | All 6 elements evaluating correctly |
| Dashboard live | Month 6 | Leadership accessing dashboard weekly |
| Baseline compliance established | Month 6 | 3 months of data collected |
| Alert pilot | Month 10 | Alerts firing in pilot ORs |
| Full alerting live | Month 12 | All ORs receiving alerts |

---

## 11. Success Metrics

### 11.1 Process Metrics

| Metric | Baseline | 6-Month Target | 12-Month Target |
|--------|----------|----------------|-----------------|
| Bundle compliance | TBD | 85% | 90% |
| Duration ≤24h | TBD | 80% | 90% |
| Timing compliance | TBD | 90% | 95% |
| Agent selection | TBD | 90% | 95% |
| Alert response rate | N/A | N/A | 90% |

### 11.2 Outcome Metrics (Long-term)

| Metric | Baseline | Target | Timeline |
|--------|----------|--------|----------|
| SSI rate | TBD | 10% reduction | 18 months |
| Antibiotic days (prophylaxis) | TBD | 30% reduction | 12 months |
| Manual chart review time | TBD | 80% reduction | 6 months |

### 11.3 Balancing Metrics

| Metric | Target | Purpose |
|--------|--------|---------|
| Alert override rate | <20% | Ensure alerts are actionable |
| False positive rate | <10% | Minimize alert fatigue |
| User satisfaction | >80% | Ensure usability |

---

## 12. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Incomplete data access | Medium | High | Early engagement with IT; fallback to manual data entry |
| Alert fatigue | High | High | Careful threshold tuning; tiered severity; continuous refinement |
| Workflow disruption | Medium | Medium | Extensive user testing; phased rollout; feedback loops |
| Incorrect CPT mapping | Medium | Medium | Validation with surgery; regular review of unmapped procedures |
| Resistance from surgeons | Medium | Medium | Champion surgeons; demonstrate SSI reduction; non-punitive approach |
| Resource constraints | Medium | Medium | Prioritize high-impact features; leverage existing AEGIS infrastructure |

---

## 13. NSQIP Reporting Integration

### 13.1 Overview

The American College of Surgeons National Surgical Quality Improvement Program (ACS NSQIP) Pediatric is a nationally validated, risk-adjusted, outcomes-based program to measure and improve the quality of surgical care in children's hospitals. Cincinnati Children's participates in NSQIP Pediatric and reports surgical outcomes including surgical site infections (SSIs).

This module will integrate with NSQIP reporting to:
1. Auto-populate prophylaxis-related data fields
2. Track prophylaxis compliance as a process measure
3. Correlate compliance with SSI outcomes
4. Generate NSQIP-ready reports

### 13.2 NSQIP Pediatric Data Elements

#### 13.2.1 Prophylaxis-Related Variables

The following NSQIP Pediatric variables relate to surgical prophylaxis:

| Variable | Description | Source in AEGIS |
|----------|-------------|-----------------|
| `PROPHYLAXIS` | Was prophylaxis given? (Y/N) | MedicationAdministration |
| `PROPHMEDS` | Which antibiotic(s)? | MedicationRequest |
| `PROPTIMING` | Timing relative to incision | Calculated from MAR + Anesthesia |
| `PROPDURATION` | Duration of prophylaxis | Calculated from MAR |
| `SSIOCC` | Superficial SSI occurrence | Outcome (from IP data) |
| `DSSISOCC` | Deep SSI occurrence | Outcome (from IP data) |
| `ORGANSPCSSI` | Organ/space SSI occurrence | Outcome (from IP data) |

#### 13.2.2 Case Identification Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `CPT` | Primary CPT code | OR scheduling |
| `WORKRVU` | Work RVU | CPT lookup |
| `OPTIME` | Operation time (minutes) | Anesthesia record |
| `SURGSPEC` | Surgical specialty | OR scheduling |
| `WOUND_CLASS` | Wound classification (Clean, Clean-Contaminated, etc.) | Surgical posting |

### 13.3 NSQIP Reporting Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NSQIP REPORTING INTEGRATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │ AEGIS Surgical  │                                                        │
│  │ Prophylaxis     │                                                        │
│  │ Module          │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           │ Nightly export of prophylaxis data                              │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NSQIP DATA STAGING TABLE                                             │   │
│  │                                                                      │   │
│  │  Case_ID | CPT | Prophylaxis | Agent | Timing | Duration | SSI_30d  │   │
│  │  --------|-----|-------------|-------|--------|----------|--------- │   │
│  │  12345   | 443 | Yes         | Cefa  | 32 min | 18 hr    | No       │   │
│  │  12346   | 271 | Yes         | Cefa  | 55 min | 48 hr    | Yes      │   │
│  │  12347   | 421 | No          | -     | -      | -        | No       │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           │ Merge with NSQIP Surgical Clinical Reviewer (SCR) data         │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NSQIP SCR WORKBENCH                                                  │   │
│  │                                                                      │   │
│  │  • Pre-populated prophylaxis fields reduce manual abstraction       │   │
│  │  • SCR validates/corrects as needed                                 │   │
│  │  • Final data submitted to ACS NSQIP                                │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           │ Quarterly                                                        │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NSQIP SEMI-ANNUAL REPORT (SAR)                                       │   │
│  │                                                                      │   │
│  │  • Risk-adjusted SSI rates                                          │   │
│  │  • Comparison to other pediatric hospitals                          │   │
│  │  • Prophylaxis compliance benchmarks                                │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.4 Auto-Population Logic

The module will auto-populate NSQIP fields to reduce SCR abstraction burden:

```python
def generate_nsqip_record(case: SurgicalCase, evaluation: ProphylaxisEvaluation) -> Dict:
    """
    Generate NSQIP-compatible record for a surgical case.
    
    Returns dict with NSQIP variable names as keys.
    """
    record = {
        # Case identification
        'CASE_ID': case.case_id,
        'MRN': case.patient_mrn,
        'DOS': case.actual_incision_time.date().isoformat(),
        'CPT': case.cpt_codes[0] if case.cpt_codes else None,
        
        # Prophylaxis fields
        'PROPHYLAXIS': 'Yes' if case.prophylaxis_administrations else 'No',
        'PROPHMEDS': ', '.join([a.medication_name for a in case.prophylaxis_administrations]),
        
        # Timing calculation
        'PROPTIMING_MINUTES': None,
        'PROPTIMING_COMPLIANT': None,
        
        # Duration calculation  
        'PROPDURATION_HOURS': None,
        'PROPDURATION_COMPLIANT': None,
        
        # From evaluation
        'AEGIS_BUNDLE_COMPLIANT': evaluation.bundle_compliant,
        'AEGIS_COMPLIANCE_SCORE': evaluation.compliance_score,
    }
    
    # Calculate timing if prophylaxis was given
    if case.prophylaxis_administrations and case.actual_incision_time:
        first_admin = min(a.administration_time for a in case.prophylaxis_administrations)
        minutes_before = (case.actual_incision_time - first_admin).total_seconds() / 60
        record['PROPTIMING_MINUTES'] = round(minutes_before)
        record['PROPTIMING_COMPLIANT'] = 0 < minutes_before <= 60
    
    # Calculate duration if surgery end time available
    if case.prophylaxis_administrations and case.surgery_end_time:
        last_admin = max(a.administration_time for a in case.prophylaxis_administrations)
        hours_duration = (last_admin - case.surgery_end_time).total_seconds() / 3600
        record['PROPDURATION_HOURS'] = round(hours_duration, 1)
        max_hours = 48 if case.procedure_category == 'cardiac' else 24
        record['PROPDURATION_COMPLIANT'] = hours_duration <= max_hours
    
    return record
```

### 13.5 NSQIP Reports from AEGIS

#### 13.5.1 Prophylaxis Compliance Report (for NSQIP Committee)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ NSQIP PROPHYLAXIS COMPLIANCE REPORT                                         │
│ Period: Q4 2024 (October - December)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ SUMMARY                                                                     │
│ ────────────────────────────────────────────────────────────────────────── │
│ Total NSQIP-sampled cases:     342                                         │
│ Prophylaxis indicated:         298 (87%)                                   │
│ Prophylaxis given:             294 (99% of indicated)                      │
│                                                                             │
│ TIMING COMPLIANCE                                                           │
│ ────────────────────────────────────────────────────────────────────────── │
│ Within 60 minutes of incision: 268 (91%)                                   │
│ Mean time before incision:     38 minutes                                  │
│ Given AFTER incision:          4 cases (1.4%)  ◀── Review these cases     │
│                                                                             │
│ DURATION COMPLIANCE                                                         │
│ ────────────────────────────────────────────────────────────────────────── │
│ Discontinued ≤24h:             198 (67%)                                   │
│ 24-48 hours:                   62 (21%)                                    │
│ >48 hours:                     34 (12%)  ◀── Opportunity for improvement  │
│                                                                             │
│ Mean duration (non-cardiac):   22.4 hours                                  │
│ Mean duration (cardiac):       31.2 hours                                  │
│                                                                             │
│ SSI CORRELATION (Preliminary - for QI purposes only)                       │
│ ────────────────────────────────────────────────────────────────────────── │
│                          SSI Rate    Cases                                 │
│ Bundle compliant:          1.2%      (2/167)                               │
│ Bundle non-compliant:      3.8%      (5/131)                               │
│                                                                             │
│ Note: Risk adjustment pending NSQIP SAR. Not for external reporting.       │
│                                                                             │
│ CASES FOR REVIEW                                                            │
│ ────────────────────────────────────────────────────────────────────────── │
│ • 4 cases with prophylaxis AFTER incision (see Appendix A)                 │
│ • 34 cases with prophylaxis >48 hours (see Appendix B)                     │
│ • 2 SSIs in bundle-compliant cases (see Appendix C)                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 13.5.2 NSQIP Data Export Format

The module will generate exports compatible with NSQIP data submission:

```csv
CASE_ID,MRN,DOS,CPT,SURGSPEC,WOUND_CLASS,PROPHYLAXIS,PROPHMEDS,PROPTIMING_MIN,PROPDURATION_HR,SSI_30D
12345,A123456,2024-10-15,44970,PEDSURG,2,Yes,Cefazolin,32,18,No
12346,A234567,2024-10-15,27130,ORTHO,1,Yes,Cefazolin,55,48,No
12347,A345678,2024-10-16,42820,ENT,1,No,,,No
12348,A456789,2024-10-16,33533,CARDIAC,2,Yes,"Cefazolin,Vancomycin",28,42,No
```

### 13.6 SSI Outcome Tracking

To correlate prophylaxis compliance with outcomes, the module will track SSIs:

```python
@dataclass
class SSIOutcome:
    """Track SSI outcomes for prophylaxis correlation."""
    case_id: str
    patient_mrn: str
    surgery_date: date
    
    # SSI occurrence (within 30 days per NSQIP definition)
    superficial_ssi: bool = False
    deep_ssi: bool = False
    organ_space_ssi: bool = False
    
    # SSI details if occurred
    ssi_diagnosis_date: Optional[date] = None
    ssi_organism: Optional[str] = None
    ssi_treatment: Optional[str] = None
    
    # Link to prophylaxis evaluation
    prophylaxis_bundle_compliant: bool = False
    
    @property
    def any_ssi(self) -> bool:
        return self.superficial_ssi or self.deep_ssi or self.organ_space_ssi


class SSICorrelationReport:
    """
    Generate reports correlating prophylaxis compliance with SSI rates.
    
    IMPORTANT: These are internal QI reports only. Risk-adjusted 
    comparisons should use official NSQIP SAR data.
    """
    
    def calculate_ssi_rates(
        self,
        cases: List[Tuple[ProphylaxisEvaluation, SSIOutcome]]
    ) -> Dict:
        """Calculate SSI rates by compliance status."""
        
        compliant_cases = [(e, o) for e, o in cases if e.bundle_compliant]
        non_compliant_cases = [(e, o) for e, o in cases if not e.bundle_compliant]
        
        def ssi_rate(case_list):
            if not case_list:
                return 0.0
            ssi_count = sum(1 for _, o in case_list if o.any_ssi)
            return ssi_count / len(case_list) * 100
        
        return {
            'compliant': {
                'n': len(compliant_cases),
                'ssi_count': sum(1 for _, o in compliant_cases if o.any_ssi),
                'ssi_rate': ssi_rate(compliant_cases)
            },
            'non_compliant': {
                'n': len(non_compliant_cases),
                'ssi_count': sum(1 for _, o in non_compliant_cases if o.any_ssi),
                'ssi_rate': ssi_rate(non_compliant_cases)
            },
            'overall': {
                'n': len(cases),
                'ssi_count': sum(1 for _, o in cases if o.any_ssi),
                'ssi_rate': ssi_rate(cases)
            }
        }
    
    def ssi_by_element(
        self,
        cases: List[Tuple[ProphylaxisEvaluation, SSIOutcome]]
    ) -> Dict:
        """
        Calculate SSI rates stratified by individual element compliance.
        Helps identify which elements have strongest association with outcomes.
        """
        elements = ['timing', 'agent', 'dose', 'duration']
        results = {}
        
        for element in elements:
            compliant = [(e, o) for e, o in cases 
                        if getattr(e, f'{element}_appropriate', None) == True]
            non_compliant = [(e, o) for e, o in cases 
                            if getattr(e, f'{element}_appropriate', None) == False]
            
            results[element] = {
                'compliant_ssi_rate': self._calc_rate(compliant),
                'non_compliant_ssi_rate': self._calc_rate(non_compliant),
                'rate_difference': self._calc_rate(non_compliant) - self._calc_rate(compliant)
            }
        
        return results
```

### 13.7 NSQIP Committee Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ NSQIP Committee Dashboard - Prophylaxis Focus                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CURRENT QUARTER vs NSQIP BENCHMARK                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                            CCHMC     NSQIP Avg    Percentile        │   │
│  │  Prophylaxis compliance    91%       88%          72nd              │   │
│  │  Timing compliance         87%       82%          68th              │   │
│  │  Duration ≤24h             67%       71%          42nd   ◀── Below │   │
│  │  Overall SSI rate          2.1%      2.4%         58th              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  SSI RATE BY PROPHYLAXIS COMPLIANCE                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  Bundle Compliant (n=412)      █░░░░░░░░░░░░░░░░░░░  1.2%           │   │
│  │  Bundle Non-Compliant (n=186)  ████░░░░░░░░░░░░░░░░  3.8%           │   │
│  │                                                                      │   │
│  │  Relative Risk: 3.2x higher SSI risk when bundle not met            │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  TREND: PROPHYLAXIS DURATION (% ≤24 hours)                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  80% ┤                              Target ─────────────────────    │   │
│  │  70% ┤                    ╭─────╮                                    │   │
│  │  60% ┤         ╭─────────╯     ╰─────╮                              │   │
│  │  50% ┤    ╭────╯                     ╰────                          │   │
│  │  40% ┤────╯                                                          │   │
│  │      └────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────   │   │
│  │       Q1   Q2   Q3   Q4   Q1   Q2   Q3   Q4   Q1   Q2   Q3   Q4    │   │
│  │       -------- 2023 -------|------- 2024 -------|-- 2025 --        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Download NSQIP Export]  [Generate Committee Report]  [View SSI Cases]    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.8 Integration with NSQIP SCR Workflow

To minimize duplicate data entry and improve accuracy:

| Current State | Future State with AEGIS |
|---------------|-------------------------|
| SCR manually abstracts prophylaxis from chart | AEGIS pre-populates fields |
| Timing calculated manually from anesthesia record | Auto-calculated with precision |
| Duration requires review of MAR | Auto-calculated from MAR data |
| No real-time feedback | Immediate compliance scoring |
| Quarterly review of SSI trends | Continuous SSI-prophylaxis correlation |

**Estimated time savings**: 5-10 minutes per case × 50 cases/month = 4-8 hours/month

### 13.9 NSQIP-Specific Configuration

```python
# NSQIP procedure categories and their prophylaxis requirements
NSQIP_PROCEDURE_CATEGORIES = {
    'APPY': {
        'name': 'Appendectomy',
        'cpt_codes': ['44950', '44960', '44970'],
        'prophylaxis_required': True,
        'wound_class_typical': 2,  # Clean-contaminated
        'duration_limit_hours': 24
    },
    'CHOL': {
        'name': 'Cholecystectomy',
        'cpt_codes': ['47562', '47563', '47564', '47600'],
        'prophylaxis_required': True,  # For open; optional for low-risk lap
        'wound_class_typical': 2,
        'duration_limit_hours': 24
    },
    'COLO': {
        'name': 'Colectomy',
        'cpt_codes': ['44140', '44141', '44143', '44144', '44145', '44146', 
                      '44147', '44150', '44151', '44160', '44204', '44205',
                      '44206', '44207', '44208', '44210', '44211', '44212'],
        'prophylaxis_required': True,
        'wound_class_typical': 2,
        'duration_limit_hours': 24,
        'requires_anaerobic_coverage': True  # Metronidazole
    },
    'CRAN': {
        'name': 'Craniotomy',
        'cpt_codes': ['61304', '61305', '61312', '61313', '61314', '61315',
                      '61320', '61321', '61322', '61323'],
        'prophylaxis_required': True,
        'wound_class_typical': 1,  # Clean
        'duration_limit_hours': 24
    },
    'FUSE': {
        'name': 'Spinal Fusion',
        'cpt_codes': ['22551', '22552', '22554', '22556', '22558', '22585',
                      '22600', '22610', '22612', '22614', '22630', '22632',
                      '22633', '22634', '22800', '22802', '22804'],
        'prophylaxis_required': True,
        'wound_class_typical': 1,
        'duration_limit_hours': 24
    },
    # ... additional NSQIP categories
}
```

---

## 14. Local CCHMC Guidelines

### 14.1 Placeholder for Local Guidelines

> **TODO**: Insert Cincinnati Children's Hospital-specific surgical prophylaxis guidelines here.
>
> Local guidelines may include:
> - Institutional antibiotic preferences
> - MRSA screening protocols
> - Transplant-specific protocols
> - Cardiac surgery protocols (including timing of second dose for cardiopulmonary bypass)
> - Weight-based dosing thresholds specific to pediatrics
> - Allergy alternative algorithms
> - VP shunt protocols (cefazolin ± vancomycin based on local practice)

### 14.2 Expected Local Protocol Documents

Please provide the following documents for incorporation:

| Document | Purpose | Status |
|----------|---------|--------|
| General surgical prophylaxis protocol | Standard agent selection, timing, duration | ⬜ Pending |
| Cardiac surgery prophylaxis protocol | May include vancomycin, extended duration | ⬜ Pending |
| Transplant prophylaxis protocols | Liver, kidney, heart, lung, BMT | ⬜ Pending |
| Neurosurgery/VP shunt protocol | Shunt procedures, craniotomy | ⬜ Pending |
| Orthopedic implant protocol | Spine fusion, hardware | ⬜ Pending |
| MRSA screening protocol | When to add vancomycin | ⬜ Pending |
| Allergy management protocol | Alternatives for β-lactam allergy | ⬜ Pending |
| Weight-based dosing guidelines | Pediatric-specific thresholds | ⬜ Pending |

### 14.3 Local Adaptation Configuration

Once local guidelines are provided, they will be encoded here:

```python
# CCHMC-specific configurations (to be populated)
CCHMC_LOCAL_PROTOCOLS = {
    'default_agent': 'cefazolin',
    'default_dose_mg_per_kg': 30,
    'default_max_dose_mg': 2000,
    'high_weight_threshold_kg': 120,
    'high_weight_dose_mg': 3000,
    
    # MRSA considerations
    'mrsa_screening_required_procedures': [
        # List procedures requiring MRSA screening
    ],
    'mrsa_positive_add_vancomycin': True,
    
    # Cardiac surgery
    'cardiac_duration_limit_hours': 48,
    'cardiac_vancomycin_routine': False,  # or True based on local practice
    
    # VP shunt
    'vp_shunt_add_vancomycin': True,  # Based on local protocol
    
    # Colorectal
    'colorectal_anaerobic_agent': 'metronidazole',
    'colorectal_mechanical_bowel_prep': True,  # If used locally
    
    # Allergy alternatives
    'beta_lactam_allergy_alternatives': {
        'clean_procedures': ['vancomycin', 'clindamycin'],
        'colorectal': ['clindamycin', 'metronidazole', 'gentamicin'],
        'urologic': ['ciprofloxacin', 'gentamicin'],
    }
}
```

### 14.4 Validation Process

Once local guidelines are incorporated:

1. **Clinical review**: ASP and surgery review encoded logic
2. **Test cases**: Validate against 50 historical cases
3. **Edge cases**: Test allergy scenarios, high-weight patients, complex procedures
4. **Sign-off**: Formal approval from ASP Medical Director and Surgery representative

---

## 15. Appendices

### Appendix A: CPT Code Mapping (Partial)

See `pediatric_abx_indications.py` SURGICAL_PROPHYLAXIS_CPT dictionary for complete mapping.

### Appendix B: Antibiotic Dosing Tables

See `pediatric_abx_reference.json` for complete dosing information.

### Appendix C: Local Protocol Variations

To be documented with Pediatric Surgery, Cardiac Surgery, Transplant, and Neurosurgery.

### Appendix D: Alert Message Templates

To be developed in collaboration with clinical informatics.

### Appendix E: User Training Materials

To be developed prior to go-live.

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | January 2025 | AEGIS Team | Initial draft |

---

## Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| ASP Medical Director | | | |
| Surgery Representative | | | |
| Pharmacy Director | | | |
| IT Lead | | | |
| Quality Officer | | | |
