# AEGIS Integration Requirements

> **Document Purpose:** Technical requirements for Information Services (IS) integration
> **Audience:** IS leadership, integration engineers, security team
> **Last Updated:** February 2026

---

## Executive Summary

AEGIS (Antimicrobial stewardship and infection prevention platform) requires integration with the following hospital data systems:

| Integration Type | Priority | Use Case |
|-----------------|----------|----------|
| **FHIR R4 API** | Critical | Real-time clinical data access |
| **HL7 v2.x Feed** | High | Real-time ADT events for surgical prophylaxis |
| **Clarity Data Warehouse** | Medium | Historical data extraction and NHSN reporting |

The application is a **clinical decision support system** that performs:
- Real-time surveillance for healthcare-associated infections (HAI)
- Antimicrobial stewardship alerts (drug-bug mismatches, duration monitoring)
- Automated NHSN reporting (AU/AR/HAI modules)

---

## Section 1: FHIR API Requirements

### 1.1 Access Request Summary

> **Request:** Read-only access to the Epic FHIR R4 API (or equivalent certified EHR FHIR endpoint) for backend application integration.

**Integration Pattern:** Backend system-to-system (no user-facing OAuth flow)

**Authentication Method Requested:** OAuth 2.0 Client Credentials with JWT Bearer Token (Backend Services specification)

**Scope Requested:** `system/*.read` (read-only access to all FHIR resources listed below)

### 1.2 FHIR Resources Required

| Resource | Search Parameters | Use Case |
|----------|------------------|----------|
| **Patient** | `identifier`, `_id` | Demographics, MRN lookup |
| **Encounter** | `patient`, `status`, `date`, `class` | Admission/discharge dates, location tracking |
| **DiagnosticReport** | `patient`, `category=MB`, `code`, `date`, `status` | Culture results, microbiology reports |
| **Observation** | `patient`, `code`, `date`, `derived-from`, `category` | Lab values, vital signs, susceptibilities |
| **MedicationRequest** | `patient`, `status=active`, `date` | Current antibiotic orders |
| **MedicationAdministration** | `patient`, `effective-time` | Medication administration timing |
| **DocumentReference** | `patient`, `date`, `type`, `status` | Clinical notes for NLP extraction |
| **Procedure** | `patient`, `code`, `date` | Surgical procedures for SSI surveillance |
| **Device** | `patient`, `type` | Central lines, catheters, ventilators |
| **DeviceUseStatement** | `patient`, `status` | Device presence/timing |
| **Condition** | `patient`, `code`, `clinical-status` | ICD-10 diagnoses |
| **Specimen** | `_id` | Specimen type verification |

### 1.3 Terminology Systems Required

#### LOINC Codes (Laboratory)

**Microbiology:**
| LOINC | Description | Module |
|-------|-------------|--------|
| 600-7 | Blood culture | HAI, Bacteremia |
| 630-4 | Urine culture | HAI (CAUTI), Guideline |
| 43409-2 | Respiratory culture | HAI |
| 88461-2 | Urine colony count | HAI (CAUTI) |

**C. difficile Testing:**
| LOINC | Description |
|-------|-------------|
| 34713-8 | C. diff toxin A |
| 34714-6 | C. diff toxin B |
| 34712-0 | C. diff toxin A+B |
| 82197-9 | C. diff toxin B gene (PCR) |
| 80685-5 | C. diff toxin genes (NAAT) |
| 76580-0 | C. diff GDH antigen |

**Vital Signs:**
| LOINC | Description |
|-------|-------------|
| 8310-5 | Body temperature |
| 8867-4 | Heart rate |
| 9279-1 | Respiratory rate |
| 2708-6 | Oxygen saturation (SpO2) |
| 8480-6 | Systolic blood pressure |
| 8462-4 | Diastolic blood pressure |

**Ventilator Parameters (VAE Surveillance):**
| LOINC | Description |
|-------|-------------|
| 3150-0 | Inhaled oxygen concentration (FiO2) |
| 19994-3 | FiO2 ventilator setting |
| 76530-5 | PEEP |
| 20077-4 | PEEP ventilator setting |

**Inflammatory Markers:**
| LOINC | Description |
|-------|-------------|
| 33959-8 | Procalcitonin |
| 1988-5 | C-reactive protein (CRP) |
| 6690-2 | White blood cell count |
| 751-8 | Absolute neutrophil count |

**Renal Function:**
| LOINC | Description |
|-------|-------------|
| 2160-0, 38483-4 | Creatinine |
| 33914-3, 48642-3, 88293-6 | eGFR |

**CSF Analysis:**
| LOINC | Description |
|-------|-------------|
| 806-0 | CSF WBC |
| 804-5 | CSF RBC |
| 16955-7 | HSV DNA PCR in CSF |

**Susceptibility Testing:**
| LOINC | Antibiotic |
|-------|------------|
| 6932-8 | Oxacillin |
| 20475-8 | Vancomycin |
| 35811-4 | Daptomycin |
| 29258-1 | Linezolid |
| 18864-9 | Cefazolin |
| 18886-2 | Ceftriaxone |
| 18879-7 | Cefepime |
| 18888-8 | Ceftazidime |
| 18945-6 | Piperacillin-tazobactam |
| 18932-4 | Meropenem |
| 18906-8 | Ciprofloxacin |
| 18928-2 | Gentamicin |
| 18878-9 | Clindamycin |
| 18998-5 | Trimethoprim-sulfamethoxazole |
| 35659-7 | MIC (general) |

#### SNOMED CT Codes (Devices/Procedures)

**Central Venous Catheters:**
| SNOMED | Description |
|--------|-------------|
| 52124006 | Central venous catheter |
| 303728004 | PICC (Peripherally inserted central catheter) |
| 706689003 | Tunneled CVC |
| 706687001 | Non-tunneled CVC |

**Urinary Catheters:**
| SNOMED | Description |
|--------|-------------|
| 20568009 | Urinary catheter |
| 68135008 | Foley catheter |
| 286558007 | Indwelling urinary catheter |

**Mechanical Ventilation:**
| SNOMED | Description |
|--------|-------------|
| 40617009 | Artificial respiration |
| 243147009 | Controlled mechanical ventilation |
| 129121000 | Endotracheal tube |
| 426854004 | Ventilator device |

#### RxNorm Codes (Antibiotics)

The system monitors ~40 antibiotic medication codes including:
- Carbapenems (meropenem, ertapenem, imipenem)
- Glycopeptides (vancomycin, dalbavancin)
- Cephalosporins (cefazolin, ceftriaxone, cefepime, ceftazidime)
- Penicillins (ampicillin, piperacillin-tazobactam)
- Fluoroquinolones (ciprofloxacin, levofloxacin)
- Aminoglycosides (gentamicin, tobramycin, amikacin)

*Full RxNorm code list available upon request.*

### 1.4 Query Volume Estimates

| Query Type | Frequency | Volume |
|------------|-----------|--------|
| Culture polling | Every 5 minutes | ~50-100 queries/hour |
| Patient lookups | Per alert | ~20-50/hour |
| Medication queries | Per case evaluation | ~20-50/hour |
| Note retrieval | Per HAI candidate | ~10-30/hour |

**Total estimated FHIR API calls:** 500-1,000 per hour during peak operations

---

## Section 2: HL7 v2.x Feed Requirements

### 2.1 Access Request Summary

> **Request:** Read-only HL7 v2.x message feed for real-time ADT and surgical scheduling events.

**Integration Pattern:** TCP/IP MLLP listener (receive-only)

**Message Types Required:**

| Message Type | Trigger Events | Use Case |
|--------------|----------------|----------|
| **ADT** (Admit/Discharge/Transfer) | A01, A02, A03, A04, A08 | Patient location tracking |
| **ORM** (Order Message) | O01 | Surgical case scheduling |
| **ORU** (Observation Result) | R01 | Lab result notifications (optional) |

### 2.2 Required Segments

**ADT Messages:**
- `MSH` - Message header (sending facility, message type)
- `PID` - Patient identification (MRN, name, DOB)
- `PV1` - Patient visit (location: point of care, room, bed, facility)
- `PV2` - Patient visit additional info (expected discharge)

**Key Fields:**
- PID-3: Patient identifier (MRN)
- PID-5: Patient name
- PV1-3: Assigned patient location (Unit^Room^Bed^Facility)
- PV1-6: Prior patient location
- PV1-19: Visit number (CSN)
- PV1-44: Admit date/time
- PV1-45: Discharge date/time

### 2.3 Network Requirements

- **Protocol:** MLLP over TCP/IP
- **Port:** Configurable (typically 2575 or custom)
- **Direction:** Inbound only (application receives messages)
- **Volume:** ~1,000-5,000 messages/day depending on facility size

---

## Section 3: Clarity Data Warehouse Requirements

### 3.1 Access Request Summary

> **Request:** Read-only SQL access to Epic Clarity reporting database for historical data extraction and NHSN reporting.

**Use Cases:**
- NHSN Antimicrobial Usage (AU) reporting - monthly aggregates
- NHSN Antimicrobial Resistance (AR) reporting - quarterly aggregates
- Historical data validation and backfill

**Note:** Clarity access is **not required for real-time surveillance**. FHIR is the preferred data source for all real-time operations.

### 3.2 Tables Required

| Table | Description | Module |
|-------|-------------|--------|
| `PATIENT` | Patient demographics | All |
| `PAT_ENC` | Patient encounters | All |
| `HNO_INFO` | Clinical notes | HAI Detection |
| `IP_NOTE_TYPE`, `ZC_NOTE_TYPE_IP` | Note type mapping | HAI Detection |
| `CLARITY_EMP` | Provider information | HAI Detection |
| `ORDER_RESULTS` | Laboratory results | HAI, NHSN |
| `ORDER_PROC` | Ordered procedures | HAI, NHSN |
| `CLARITY_COMPONENT` | Result components | HAI, NHSN |
| `IP_FLWSHT_MEAS` | Flowsheet measurements | HAI (device tracking) |
| `IP_FLWSHT_REC` | Flowsheet records | HAI (device tracking) |
| `IP_FLO_GP_DATA` | Flowsheet group data | HAI (device tracking) |
| `OR_LOG` | Operating room log | SSI surveillance |
| `OR_PROC` | Surgical procedures | SSI surveillance |

### 3.3 Query Patterns

- **Frequency:** Nightly batch (AU reporting), Weekly batch (AR reporting)
- **Data volume:** 10,000-100,000 rows per query depending on time range
- **Connection:** Read-only service account with SELECT permissions only

---

## Section 4: Compute Infrastructure Requirements

### 4.1 Application Server Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores | 8 cores |
| **RAM** | 16 GB | 32 GB |
| **Storage** | 100 GB SSD | 250 GB SSD |
| **OS** | Ubuntu 24.04 LTS | Same |
| **Python** | 3.11+ | 3.12 |

**Network Requirements:**
- Outbound HTTPS (443) to FHIR endpoints
- Inbound TCP for HL7 MLLP listener (configurable port)
- Outbound HTTPS for notification services (Teams, email)

### 4.2 LLM/NLP Inference Server Requirements

The system uses Large Language Models for clinical note extraction. Options:

#### Option A: Local GPU Server (Recommended for PHI)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | NVIDIA A10 (24GB VRAM) | NVIDIA A100 (40GB+) |
| **CPU** | 16 cores | 32 cores |
| **RAM** | 64 GB | 128 GB |
| **Storage** | 500 GB NVMe | 1 TB NVMe |
| **Model** | Llama 3.3 70B (quantized) | Qwen 2.5 72B |

**Inference Frameworks Supported:**
- **Ollama** - Simplified deployment, good for development
- **vLLM** - Production-grade, higher throughput

#### Option B: Anthropic Claude API (Cloud)

- No local GPU required
- Requires outbound HTTPS to `api.anthropic.com`
- PHI considerations: Requires BAA with Anthropic
- Cost: ~$15/1M input tokens, $75/1M output tokens

### 4.3 Database Requirements

| Database | Purpose | Size Estimate |
|----------|---------|---------------|
| SQLite | Alert storage, case tracking | 1-10 GB |
| PostgreSQL (optional) | Multi-user dashboard | 10-50 GB |

---

## Section 5: Security Requirements

### 5.1 Authentication & Authorization

| System | Auth Method | Credentials Required |
|--------|-------------|---------------------|
| FHIR API | OAuth 2.0 JWT Bearer | Client ID, Private Key (RSA) |
| Clarity | SQL Authentication | Service account credentials |
| HL7 Feed | IP whitelist + TLS | Server certificate |

### 5.2 Network Security

**Recommended Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                     Hospital Network                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │ FHIR Server │    │ HL7 Engine  │    │ Clarity Server  │  │
│  │ (Epic)      │    │ (Rhapsody)  │    │                 │  │
│  └──────┬──────┘    └──────┬──────┘    └────────┬────────┘  │
│         │                  │                     │           │
│         │ HTTPS/443        │ MLLP/2575          │ SQL/1433  │
│         │                  │                     │           │
│  ┌──────┴──────────────────┴─────────────────────┴────────┐ │
│  │                  Application Server                     │ │
│  │                  (AEGIS Platform)                       │ │
│  │   - Runs in isolated VLAN or DMZ                       │ │
│  │   - Read-only access to clinical systems               │ │
│  │   - No PHI stored long-term (alerts only)              │ │
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                  LLM Inference Server                   ││
│  │   - GPU workstation (local) OR                         ││
│  │   - API access to Anthropic (cloud, requires BAA)      ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Data Handling

| Data Type | Retention | Storage | Purpose |
|-----------|-----------|---------|---------|
| Alerts & interventions | Indefinite | Encrypted database | Program analytics, intervention tracking, outcome measurement |
| Patient identifiers in alerts | Indefinite | Encrypted database | Longitudinal tracking, deduplication |
| Extracted clinical text | Session only | Memory (not persisted) | LLM processing |
| NHSN reports | 7 years | Encrypted files | Regulatory compliance |
| Audit logs | 1 year minimum | Log files | Security compliance |

**Rationale for Long-term Alert Storage:**
- Track antimicrobial stewardship program interventions over time
- Measure impact of alerts on prescribing behavior
- Identify trends in HAI rates and resistance patterns
- Support quality improvement and research initiatives
- Enable retrospective analysis of alert accuracy and clinical outcomes

### 5.4 Compliance Considerations

- **HIPAA:** Application handles PHI; requires BAA with cloud vendors
- **HITECH:** Audit logging enabled for all data access
- **Joint Commission:** Supports antimicrobial stewardship program requirements

---

## Section 6: Glossary of Terms

### For IS Discussions

| Term | Definition | Example Usage |
|------|------------|---------------|
| **FHIR** | Fast Healthcare Interoperability Resources - HL7 standard for healthcare data exchange | "We need read access to the FHIR R4 API" |
| **FHIR Resource** | A discrete data object in FHIR (Patient, Observation, etc.) | "We'll query the DiagnosticReport resource for culture results" |
| **FHIR Endpoint** | The base URL of the FHIR server | "What is the FHIR endpoint URL for our Epic instance?" |
| **Search Parameters** | Query filters for FHIR resources | "We'll search by patient ID and date range" |
| **Backend Services** | OAuth pattern for system-to-system integration (no user login) | "This is a backend services integration, not a patient-facing app" |
| **SMART on FHIR** | Framework for healthcare app authorization | "We're using SMART Backend Services for authentication" |
| **JWT Bearer** | JSON Web Token authentication flow | "We'll authenticate using JWT bearer tokens" |
| **Clarity** | Epic's SQL reporting data warehouse | "We need read-only Clarity access for NHSN reporting" |
| **MLLP** | Minimal Lower Layer Protocol - TCP wrapper for HL7 | "The HL7 feed uses MLLP over TCP port 2575" |
| **ADT** | Admit/Discharge/Transfer messages | "We need the ADT feed for patient location tracking" |
| **LLM** | Large Language Model - AI for text understanding | "The LLM extracts clinical findings from notes" |
| **Inference** | Running an AI model to get predictions | "We need a GPU server for local LLM inference" |

### Epic-Specific Terms

| Term | Definition | Example Usage |
|------|------------|---------------|
| **App Orchard** | Epic's app marketplace for third-party integrations | "Do we need to register through App Orchard or is this an internal app?" |
| **Interconnect** | Epic's web services middleware layer that hosts FHIR APIs | "The FHIR endpoint runs on Interconnect" |
| **Caboodle** | Epic's enterprise data warehouse (newer than Clarity) | "Do you use Clarity or Caboodle for reporting?" |
| **Hyperspace** | Epic's main clinical user interface | "This is a backend system, not a Hyperspace integration" |

### Security & Authentication Terms

| Term | Definition | Example Usage |
|------|------------|---------------|
| **Client Credentials Grant** | OAuth flow for server-to-server auth (no user involved) | "We'll use the client credentials grant, not authorization code" |
| **JWKS** | JSON Web Key Set - public keys for JWT verification | "We'll publish our public key via a JWKS endpoint" |
| **Scopes** | OAuth permission levels defining what data can be accessed | "We're requesting `system/*.read` scope for read-only access" |
| **Service Account** | Non-human account for system-to-system authentication | "We need a service account for Clarity access" |
| **BAA** | Business Associate Agreement - HIPAA requirement for vendors handling PHI | "If using cloud LLM, we need a BAA with Anthropic" |
| **Secrets Manager** | Secure storage for credentials and API keys | "Credentials will be stored in a secrets manager, not config files" |

### Integration & Infrastructure Terms

| Term | Definition | Example Usage |
|------|------------|---------------|
| **Sandbox** | Non-production test environment with synthetic data | "Can we get sandbox access first to validate our queries?" |
| **Rate Limiting** | API throttling to prevent overload | "What are the rate limits on the FHIR endpoint?" |
| **Bulk FHIR** | FHIR specification for large data exports | "We don't need Bulk FHIR - our queries are per-patient" |
| **DMZ** | Demilitarized zone - network segment between internal and external | "The app server could run in the DMZ" |
| **USCDI** | US Core Data for Interoperability - required data elements | "We're querying standard USCDI data elements" |
| **CDS Hooks** | Clinical Decision Support integration standard | "Future: we could expose alerts via CDS Hooks in Epic" |

### Common IS Questions & Answers

| Question | Answer |
|----------|--------|
| "Is this patient-facing?" | No, this is a backend clinical decision support system for ID/IP staff |
| "Does it write data back to Epic?" | No, read-only access. Alerts are stored in a separate database |
| "Where does PHI go?" | PHI stays on-premises. Only de-identified metrics could optionally be shared |
| "What if the FHIR API is down?" | The system queues requests and retries; no clinical workflow depends on it |
| "How do you handle PHI in the LLM?" | Local GPU inference keeps PHI on-premises; cloud option requires BAA |
| "What's the blast radius if compromised?" | Read-only access limits risk; no ability to modify clinical data |

### Correct Phrasing for Requests

**FHIR Access:**
> "We're requesting **read-only API access** to the **FHIR R4 endpoint** using **OAuth 2.0 backend services authentication**. This is a **system-to-system integration** for a **clinical decision support application**."

**HL7 Feed:**
> "We need to **subscribe to the ADT message feed** via **MLLP**. Our application will act as a **receiving system** (listener) for real-time patient location events."

**Clarity Access:**
> "We're requesting **read-only SQL access** to the **Clarity reporting database** for **batch extraction** of historical data for NHSN reporting. This is **not for real-time queries**."

**Compute Resources:**
> "The application requires a **dedicated application server** for the surveillance platform and optionally a **GPU-enabled workstation** for **local AI inference** to keep PHI on-premises."

**Security:**
> "We recommend deploying the application in an **isolated network segment** with **firewall rules** permitting only the required connections to clinical data sources. All credentials should be stored in a **secrets manager** or **environment variables**, not in configuration files."

---

## Section 7: Future Roadmap - Multi-Site Analytics

> **Note:** This section describes a **future capability**, not part of the initial deployment request. It is included for awareness and long-term planning.

### 7.1 Vision

As a standards-based (FHIR R4) application, AEGIS is inherently portable to other Epic institutions. Our department leadership sees potential value in establishing a **multi-site analytics consortium** where participating institutions could:

1. **Contribute de-identified usage data** to improve the platform
2. **Benchmark** antimicrobial stewardship program performance
3. **Share learnings** about HAI classification practices

This model follows established precedents in healthcare quality improvement:

| Program | Sponsoring Organization | Data Shared |
|---------|------------------------|-------------|
| **NHSN** | CDC | HAI events, denominators, resistance patterns |
| **NSQIP** | American College of Surgeons | Surgical outcomes, risk-adjusted benchmarks |
| **Vizient/UHC** | Vizient | Quality metrics, utilization data |
| **Epic Benchmarking** | Epic Systems | Aggregate EHR usage and outcomes |

### 7.2 Data Elements (De-identified Only)

No protected health information (PHI) would leave participating institutions. The following **de-identified, aggregate data elements** would be collected:

#### LLM Extraction Training Feedback
```
{
  "extraction_id": "uuid",
  "hai_type": "CLABSI",
  "field_corrected": "alternative_source",
  "original_value": "none identified",
  "corrected_value": "pneumonia",
  "correction_category": "missed_finding",
  "site_id": "anonymized_site_001",
  "timestamp": "2026-02-01"
}
```
**Purpose:** Improve extraction model accuracy across diverse documentation styles.

#### Classification Override Patterns
```
{
  "candidate_id": "uuid",
  "hai_type": "CLABSI",
  "llm_decision": "hai_confirmed",
  "reviewer_decision": "rejected",
  "override_reason_category": "CLINICAL_JUDGMENT",
  "override_subcategory": "secondary_bsi_pneumonia",
  "site_id": "anonymized_site_001"
}
```
**Purpose:** Understand inter-site variability in subjective HAI classifications (e.g., MBI-LCBI, secondary BSI attribution).

#### Aggregate Usage Metrics
```
{
  "site_id": "anonymized_site_001",
  "month": "2026-02",
  "alerts_generated": 142,
  "alerts_accepted": 98,
  "alerts_dismissed": 44,
  "hai_type_breakdown": {"CLABSI": 23, "CAUTI": 45, ...},
  "avg_time_to_review_minutes": 12.5
}
```
**Purpose:** Benchmark program effectiveness, guide feature development.

### 7.3 Architecture

**Proposed Model: Opt-in Central Analytics with Local PHI**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Site A (Our Institution)                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ AEGIS Application Server                                     │   │
│  │  - Full PHI access (local only)                             │   │
│  │  - Alerts, interventions, outcomes stored indefinitely      │   │
│  │  - De-identification module for analytics export            │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                              │ De-identified                        │
│                              │ data only                            │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Central Analytics Server                          │
│                    (Coordinating Center)                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  - No PHI - only de-identified usage data                      │ │
│  │  - Aggregated benchmarks and dashboards                        │ │
│  │  - Training data for improved extraction models                │ │
│  │  - Research datasets (with IRB approval)                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                               ▲
                               │ De-identified
                               │ data only
┌──────────────────────────────┼──────────────────────────────────────┐
│  Site B, Site C, ... (Other Participating Institutions)             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Independent AEGIS deployments                                │   │
│  │  - Own IS team, own infrastructure                          │   │
│  │  - Own FHIR/Clarity connections                             │   │
│  │  - Opt-in to analytics sharing                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.4 Governance Requirements

Before multi-site analytics could be implemented:

| Requirement | Responsible Party | Status |
|-------------|------------------|--------|
| **Data Use Agreements (DUA)** | Legal/Compliance at each site | Future |
| **IRB Approval** | If research use intended | Future |
| **Technical De-identification Review** | IS Security | Future |
| **Opt-in Consent Framework** | Coordinating center | Future |
| **Data Governance Committee** | Multi-site stakeholders | Future |

### 7.5 Research Opportunities

This infrastructure would enable research into:

- **Inter-site variability in HAI classification** - How do different institutions interpret subjective NHSN criteria (MBI-LCBI, secondary BSI)?
- **AI-assisted surveillance validation** - Multi-site validation of extraction accuracy
- **Stewardship program benchmarking** - Compare intervention rates and outcomes across institutions
- **Best practices identification** - Which alert configurations drive highest clinical acceptance?

### 7.6 What This Means for IS (Now)

**Immediate impact: None.** Multi-site analytics is not part of the current deployment request.

**Future consideration:** If this capability is pursued, IS would be consulted on:
- Outbound data flow approval (de-identified only)
- Network configuration for analytics export
- Security review of de-identification process

**Our commitment:** No data will leave the institution without explicit IS and compliance approval, appropriate governance (DUA/IRB), and technical review of de-identification controls.

---

## Section 8: Implementation Checklist

### Pre-Meeting Preparation
- [ ] Identify FHIR endpoint URL (production and sandbox)
- [ ] Confirm OAuth 2.0 backend services is supported
- [ ] Identify HL7 integration engine (Rhapsody, Cloverleaf, etc.)
- [ ] Confirm Clarity access approval process
- [ ] Identify server provisioning process

### FHIR Integration
- [ ] Request application registration in Epic App Orchard (or equivalent)
- [ ] Generate RSA key pair for JWT authentication
- [ ] Receive Client ID from Epic/EHR team
- [ ] Configure scopes (`system/*.read`)
- [ ] Test connectivity to sandbox environment
- [ ] Validate resource access and search parameters

### HL7 Integration
- [ ] Request ADT feed subscription
- [ ] Configure MLLP listener port
- [ ] Set up TLS certificates if required
- [ ] Test message parsing with sample ADT^A01

### Clarity Integration
- [ ] Request service account with SELECT permissions
- [ ] Document required tables (see Section 3.2)
- [ ] Test connectivity and query performance
- [ ] Schedule batch job windows (off-peak hours)

### Infrastructure
- [ ] Provision application server (see Section 4.1)
- [ ] Provision GPU server if using local LLM (see Section 4.2)
- [ ] Configure network firewall rules
- [ ] Set up monitoring and alerting
- [ ] Configure backup and disaster recovery

---

## Appendix A: Module-by-Module Integration Summary

| Module | FHIR | HL7 | Clarity | LLM |
|--------|:----:|:---:|:-------:|:---:|
| HAI Detection | ✓ | | ✓ | ✓ |
| MDRO Surveillance | ✓ | | | |
| Drug-Bug Mismatch | ✓ | | | |
| Antimicrobial Usage Alerts | ✓ | | | ✓ |
| ASP Bacteremia Alerts | ✓ | | | |
| Guideline Adherence | ✓ | | | ✓ |
| Surgical Prophylaxis | ✓ | ✓ | | |
| NHSN Reporting | ✓ | | ✓ | |
| Outbreak Detection | | | | |
| Dashboard | ✓ | | | |

---

## Appendix B: Contact Information

| Role | Contact |
|------|---------|
| Project Lead | [Your Name] |
| Technical Lead | [Your Name] |
| IS Liaison | [To be assigned] |
| Security Review | [To be assigned] |

---

*Document Version: 1.0*
*Generated: February 2026*
