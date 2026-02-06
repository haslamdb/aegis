# Antibiotic Approvals Module

The Antibiotic Approvals module provides a streamlined workflow for pharmacists handling phone-based antibiotic approval requests from prescribers.

## Overview

Unlike system-generated alerts (bacteremia, guideline deviations), antibiotic approval requests are initiated manually when a prescriber calls requesting extended use of broad-spectrum antibiotics. This module helps pharmacists:

- **Search** for patients by MRN or name
- **Review** clinical context (MDR history, allergies, renal function)
- **Assess** current antibiotics and recent culture results
- **Document** approval decisions with audit trail
- **Track** approval metrics for stewardship reporting

## Access

**URL:** [https://aegis-asp.com/abx-approvals/](https://aegis-asp.com/abx-approvals/)

| Page | URL | Description |
|------|-----|-------------|
| **Dashboard** | `/abx-approvals/dashboard` | Pending requests and today's activity |
| **New Request** | `/abx-approvals/new` | Patient search to start new request |
| **Patient Detail** | `/abx-approvals/patient/<id>` | Clinical data and approval form |
| **Approval Detail** | `/abx-approvals/approval/<id>` | View completed approval with audit log |
| **History** | `/abx-approvals/history` | Past approvals with filters |
| **Reports** | `/abx-approvals/reports` | Analytics and metrics |
| **Help** | `/abx-approvals/help` | User guide |

## Workflow

```
┌─────────────────┐
│  Prescriber     │
│  Calls          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Search Patient │  MRN (recommended) or name
│  by MRN/Name    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Review         │  • MDR history (MRSA, VRE, CRE, ESBL)
│  Clinical       │  • Drug allergies with severity
│  Alerts         │  • Renal function (CKD, dialysis, GFR)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Review         │  • Current antibiotic orders
│  Cultures &     │  • Recent cultures with susceptibilities
│  Medications    │  • Allergy-unsafe options flagged
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Enter Request  │  • Antibiotic name (required)
│  Details        │  • Duration
│                 │  • Optional: dose, route, indication
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Make Decision  │  Approve / Change Therapy / Deny / Defer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Submit         │  Recorded with timestamp and reviewer
└─────────────────┘
```

## Decision Types

| Decision | Badge | Use Case |
|----------|-------|----------|
| **Approved** | Green | Requested antibiotic is appropriate (specify approval duration) |
| **Suggested Alternate** | Yellow | Recommend a different antibiotic (must specify alternative) |
| **Suggested Discontinue** | Orange | Recommend stopping the antibiotic |
| **Requested ID Consult** | Red | Complex case requiring Infectious Disease consultation |
| **Deferred** | Gray | Need more information; plan to call back after review |
| **No Action Needed** | Blue | Reviewed, no changes recommended |
| **Spoke with Team** | Purple | Discussed with care team, pending decision |

### Duration Tracking (for "Approved" decisions)

When selecting "Approved", you must specify an approval duration:
- **Predefined options:** 24h, 48h, 72h, 5 days, 7 days, 10 days, 14 days
- **Custom:** Enter any number of days (1-30)

The system calculates a **planned end date** (approval date + duration + 1-day grace period) and automatically rechecks at that time to see if the patient is still on the same antibiotic.

## Clinical Context

The approval form displays critical clinical information to support decision-making:

### MDR Pathogen History (1-year lookback)

Scans past cultures for resistant organisms:

| Badge | Description |
|-------|-------------|
| **MRSA** | Methicillin-resistant *Staphylococcus aureus* |
| **VRE** | Vancomycin-resistant *Enterococcus* |
| **CRE** | Carbapenem-resistant Enterobacteriaceae |
| **ESBL** | Extended-spectrum beta-lactamase producer |

### Drug Allergies

- Lists all documented drug allergies
- Highlights **life-threatening** allergies (anaphylaxis)
- Culture susceptibility options conflicting with allergies are flagged

### Renal Function

- CKD stage (1-5) or ESRD
- Dialysis status (hemodialysis, peritoneal)
- Recent creatinine and GFR values
- Flags patients needing renal dose adjustments (GFR < 30)

## Culture Display

Recent cultures (30 days) are displayed with:

- **Specimen type** (Blood Culture, Urine Culture, Wound Culture, etc.)
- **Organism** identified
- **Collection date**
- **Susceptibility panel** with S/I/R results and MIC values
- **Allergy warnings** for susceptible antibiotics that conflict with patient allergies

Example:
```
Blood Culture - Escherichia coli
01/28/2026

Antibiotic         Result    MIC
─────────────────────────────────
Ampicillin         R         >16
Ceftriaxone        S         ≤1
Ciprofloxacin      S         ≤0.25
Meropenem          S         ≤0.25
Pip-Tazo           S         ≤4

Allergy History: Penicillin, Sulfonamide
```

## Common Antibiotics Requiring Approval

| Category | Antibiotics |
|----------|-------------|
| **Carbapenems** | Meropenem, Imipenem, Ertapenem |
| **Extended-spectrum cephalosporins** | Cefepime, Ceftazidime |
| **Anti-MRSA agents** | Vancomycin, Daptomycin, Linezolid |
| **BL/BLI combinations** | Piperacillin-Tazobactam, Ceftazidime-Avibactam |
| **Fluoroquinolones** | Levofloxacin, Ciprofloxacin, Moxifloxacin |
| **Antifungals** | Fluconazole, Micafungin, Voriconazole, Amphotericin B |

## Reports & Analytics

The Reports page (`/abx-approvals/reports`) provides:

- **Decision breakdown** - Approval rate, therapy changes, denials
- **Top requested antibiotics** - Most frequently requested agents
- **Response time metrics** - Average, fastest, slowest decision times
- **Volume trends** - Requests by day of week and daily trend

Use these metrics for:
- Stewardship program reporting
- Quality improvement initiatives
- Identifying prescribing patterns

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/create` | POST | Create new approval request |
| `/api/<id>/decide` | POST | Record decision on request |
| `/api/<id>/note` | POST | Add note to existing request |

### Create Request

```json
POST /abx-approvals/api/create
{
    "patient_id": "1957",
    "antibiotic_name": "Meropenem",
    "duration_requested_hours": 72,
    "reviewer": "Dr. Smith",
    "indication": "Hospital-acquired pneumonia",
    "antibiotic_dose": "1g q8h",
    "antibiotic_route": "IV"
}
```

### Record Decision

```json
POST /abx-approvals/api/abc123/decide
{
    "decision": "approved",
    "reviewer": "Dr. Smith",
    "decision_notes": "Appropriate for HAP with recent MDR history"
}
```

## Data Model

### ApprovalRequest

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (8-char hex) |
| `patient_id` | string | FHIR Patient ID |
| `patient_mrn` | string | Medical Record Number |
| `patient_name` | string | Patient display name |
| `patient_location` | string | Current unit/room |
| `antibiotic_name` | string | Requested antibiotic |
| `antibiotic_dose` | string | Dose (optional) |
| `antibiotic_route` | string | IV, PO, IM, etc. (optional) |
| `indication` | string | Clinical indication (optional) |
| `duration_requested_hours` | int | Requested duration |
| `prescriber_name` | string | Requesting prescriber (optional) |
| `status` | enum | PENDING, COMPLETED |
| `decision` | enum | approved, suggested_alternate, suggested_discontinue, requested_id_consult, deferred, no_action_needed, spoke_with_team |
| `decision_by` | string | Reviewer who made decision |
| `decision_at` | datetime | When decision was recorded |
| `decision_notes` | string | Free-text notes |
| `alternative_recommended` | string | For suggested_alternate decisions |
| **`approval_duration_hours`** | **int** | **Approved duration in hours (NEW)** |
| **`planned_end_date`** | **datetime** | **When to recheck (approval date + duration + grace) (NEW)** |
| **`is_reapproval`** | **bool** | **Whether this is a re-approval request (NEW)** |
| **`parent_approval_id`** | **string** | **ID of parent approval if re-approval (NEW)** |
| **`approval_chain_count`** | **int** | **Number of times this has been re-approved (NEW)** |
| **`recheck_status`** | **string** | **pending, completed, discontinued, extended (NEW)** |
| **`last_recheck_date`** | **datetime** | **When last automatic recheck occurred (NEW)** |
| `created_at` | datetime | When request was created |
| `created_by` | string | Who created the request |

## Database

Approval data is stored in SQLite at the path configured in `ABX_APPROVALS_DB_PATH` (default: `~/.aegis/abx_approvals.db`).

Tables:
- `approval_requests` - Main request data
- `approval_audit_log` - Audit trail of all actions
- `approval_notes` - Additional notes on requests

## Configuration

Environment variables in `.env`:

```bash
# FHIR server for patient lookup and clinical data
FHIR_BASE_URL=http://localhost:8081/fhir

# Database path (default: ~/.aegis/abx_approvals.db)
ABX_APPROVALS_DB_PATH=/path/to/abx_approvals.db
```

## Integration with FHIR

The module queries FHIR R4 resources for clinical context:

| Resource | Data Retrieved |
|----------|----------------|
| `Patient` | Demographics, MRN, location |
| `AllergyIntolerance` | Drug allergies with severity |
| `Condition` | Renal diagnoses (CKD, AKI) |
| `Procedure` | Dialysis procedures |
| `Observation` | Creatinine, GFR lab values |
| `DiagnosticReport` | Culture results |
| `MedicationRequest` | Current antibiotic orders |

## Best Practices

1. **Verify patient identity** with the prescriber before proceeding
2. **Review MDR history** - past resistance predicts future resistance
3. **Check allergies** - especially for beta-lactam alternatives
4. **Review cultures** - ensure coverage matches susceptibilities
5. **Document indication** - supports stewardship metrics
6. **Use Deferred** when you need more clinical context
7. **Recommend ID consult** for complex or failing patients

## Automatic Re-approval Workflow

**New Feature (2026-02-06):** The system now automatically tracks approval durations and creates re-approval requests when needed.

### How It Works

1. **Pharmacist approves with duration** (e.g., "approved for 3 days")
2. **System calculates planned end date:**
   - Approval date + duration + 1-day grace period
   - If end date falls on weekend, check on Friday before
3. **Automatic recheck runs 3x daily** (6am, 12pm, 6pm via cron)
4. **At planned end date:**
   - System queries FHIR for current medications
   - If patient **still on same antibiotic** → creates **re-approval request**
   - If patient **discontinued** → marks approval as complete

### Re-approval Requests

Re-approval requests are:
- Marked as **re-approval** (not a new request)
- Linked to the **parent approval** (approval chain)
- Displayed separately on dashboard with **chain count badge** ("1st re-approval", "2nd re-approval", etc.)
- Sent via **email notification** to ASP team

### Approval Chains

The system tracks sequential approvals:
- **1st approval** → chain count = 0
- **1st re-approval** → chain count = 1 (after recheck)
- **2nd re-approval** → chain count = 2 (after 2nd recheck)
- And so on...

You can view the full chain by clicking through the parent approval links on detail pages.

### Weekend Handling

If the planned end date falls on Saturday or Sunday, the system checks on **Friday before** to alert the team in advance.

### Grace Period

A 1-day grace period is automatically added to all approvals to allow for order discontinuation lag time.

## Notifications

### Email Notifications (Re-approvals)

When a re-approval request is created, an email is sent to the ASP team with:
- Patient name and MRN
- Location
- Antibiotic details
- Original approval date and reviewer
- Previous approval duration
- Re-approval number in chain
- Link to review request

**Future Enhancement:** Epic Secure Chat integration to notify prescribers directly (planned but not yet implemented).

## Analytics & Reporting

The Reports page now includes comprehensive **Re-approval Analytics**:

### Key Metrics
- **Total re-approvals** - Count of continuation requests
- **Re-approval rate** - Percentage of all approvals that get continued
- **Longest chain** - Maximum sequential re-approvals for any patient
- **Average chain length** - Mean number of sequential approvals
- **Most re-approved antibiotics** - Which antibiotics are most frequently continued

### Compliance Tracking
- **Stopped at approved duration** - Patients who discontinued on time
- **Continued beyond duration** - Patients who remained on antibiotic
- **Compliance rate** - Percentage who stopped as approved

### Duration Metrics
- **Average approval duration** - Mean approved duration across all requests
- **Recheck status breakdown** - Pending, Extended, Completed

## Comparison with Other Modules

| Module | Trigger | Workflow |
|--------|---------|----------|
| **Antibiotic Approvals** | Manual (phone call) | Pharmacist reviews and decides in real-time; system auto-rechecks at end of approval duration |
| **Broad-Spectrum Alerts** | Automatic (72h threshold) | System detects, ASP reviews retrospectively |
| **Indication Monitoring** | Automatic (missing indication) | System flags, pharmacist validates |

The Antibiotic Approvals module complements automated alerting by providing a structured way to handle prospective review requests that aren't captured by rule-based monitors.
