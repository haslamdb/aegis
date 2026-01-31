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
| **Approved** | Green | Requested antibiotic is appropriate for the clinical situation |
| **Changed Therapy** | Yellow | Recommend a different antibiotic (must specify alternative) |
| **Recommend ID Consult** | Red | Complex case requiring Infectious Disease consultation |
| **Deferred** | Gray | Need more information; plan to call back after review |

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
| `decision` | enum | approved, changed_therapy, denied, deferred |
| `decision_by` | string | Reviewer who made decision |
| `decision_at` | datetime | When decision was recorded |
| `decision_notes` | string | Free-text notes |
| `alternative_recommended` | string | For changed_therapy decisions |
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

## Comparison with Other Modules

| Module | Trigger | Workflow |
|--------|---------|----------|
| **Antibiotic Approvals** | Manual (phone call) | Pharmacist reviews and decides in real-time |
| **Broad-Spectrum Alerts** | Automatic (72h threshold) | System detects, ASP reviews retrospectively |
| **Indication Monitoring** | Automatic (missing indication) | System flags, pharmacist validates |

The Antibiotic Approvals module complements automated alerting by providing a structured way to handle prospective review requests that aren't captured by rule-based monitors.
