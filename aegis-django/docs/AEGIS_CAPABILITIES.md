# AEGIS — Antimicrobial & Epidemiologic Guidance Intelligence System

## Comprehensive Capabilities Overview

*For evaluation by Information Services, Infection Prevention, and Antimicrobial Stewardship stakeholders*

---

## Platform Summary

AEGIS is a purpose-built antimicrobial stewardship and infection prevention platform designed for pediatric academic medical centers. It integrates real-time EHR data (via FHIR R4, HL7 v2.x, and Epic Clarity) with AI-powered clinical decision support to provide continuous surveillance, alerting, and regulatory reporting across 12 clinical modules.

**Architecture:** Django 5.x / PostgreSQL 16 / Redis / Celery / Ollama LLM
**Test Coverage:** 1,120 automated tests across all modules
**Deployment:** Systemd-managed services behind Nginx with TLS, health monitoring endpoint
**Authentication:** SAML 2.0, LDAP, and local credentials with RBAC and HIPAA audit logging

---

## 1. Antimicrobial Stewardship Alerts & Interventions

*Real-time prospective audit and feedback for ASP pharmacists and physicians*

- [ ] **27 distinct clinical alert types** spanning stewardship, infection prevention, dosing, and regulatory domains
- [ ] **5-level severity classification** (Info, Low, Medium, High, Critical) with numeric priority scoring (0–100)
- [ ] **7-stage alert lifecycle** (Pending → Sent → Acknowledged → In Progress → Snoozed → Resolved → Expired)
- [ ] **23 structured resolution reasons** (therapy changed, dose adjusted, culture pending, clinical justification, etc.)
- [ ] **Snooze functionality** with configurable duration and automatic re-alert
- [ ] **Multi-channel notifications** — email, Microsoft Teams, and SMS delivery with per-user preferences
- [ ] **Complete audit trail** — every alert action logged with user, timestamp, IP address, old/new status
- [ ] **Patient-centric alert grouping** — view all active alerts for a given patient across all modules
- [ ] **Priority-ranked alert queue** — actionable alerts sorted by clinical urgency
- [ ] **Automatic alert expiration** with configurable time-to-live
- [ ] **Soft-delete support** — alerts are never permanently destroyed, preserving historical record

---

## 2. Drug–Bug Mismatch Detection

*Continuous surveillance for discordant antimicrobial therapy based on culture and susceptibility data*

- [ ] **Automated susceptibility-based mismatch detection** — compares active antimicrobial orders against finalized culture results in real-time
- [ ] **35+ antimicrobial agent mappings** (RxNorm-coded) with organism-specific susceptibility interpretation
- [ ] **7 mismatch classification types:**
  - [ ] Resistant organism on active therapy (immediate escalation alert)
  - [ ] Intermediate susceptibility (dose/frequency review prompt)
  - [ ] No culture-directed coverage for identified pathogen
  - [ ] Susceptible — confirmed appropriate coverage
  - [ ] Pending culture — no susceptibility data yet available
  - [ ] Full mismatch assessment summary
  - [ ] Culture-positive, no antimicrobial therapy ordered
- [ ] **Severity auto-classification** — resistant organism mismatches trigger HIGH severity alerts
- [ ] **FHIR-integrated** — pulls MedicationRequest (active orders) and DiagnosticReport/Observation (culture results) in real-time
- [ ] **Deduplication logic** — prevents repeat alerts for the same culture–medication pair
- [ ] **CSV export** for stewardship committee reporting
- [ ] **Dashboard with filter controls** — filter by mismatch type, unit, date range

---

## 3. Dosing Verification & Clinical Decision Support

*9-module rules engine for antimicrobial dose optimization in pediatric patients*

- [ ] **Allergy cross-reactivity checking** — drug class allergy detection with known cross-reactivity alerts (e.g., penicillin → cephalosporin)
- [ ] **Age-stratified dosing rules** — neonatal, pediatric, and adolescent dose ranges with weight-band validation
- [ ] **Renal dose adjustment** — GFR-tiered dosing recommendations for 15 nephrotoxic antimicrobials (vancomycin, aminoglycosides, carbapenems, etc.)
- [ ] **Weight-based dosing** — IBW, ABW, and obesity-adjusted dose calculations for pediatric patients
- [ ] **Route appropriateness checking** — flags inappropriate routes (e.g., oral vancomycin for systemic infection, IV daptomycin for pneumonia)
- [ ] **Indication-specific dosing** — dose recommendations adjusted for 9 clinical syndromes (meningitis, endocarditis, osteomyelitis, etc.)
- [ ] **Drug interaction detection** — 17 specific drug pairs plus class-level interaction screening with severity grading
- [ ] **Duration monitoring** — evidence-based duration limits for 12 infection types with alerts for excessive or insufficient courses
- [ ] **Extended infusion recommendations** — 10 beta-lactam agents with extended/continuous infusion benefit flagging
- [ ] **16 dosing flag types** covering allergy, age, renal, weight, route, interaction, duration, and frequency concerns
- [ ] **FHIR-integrated** — pulls patient demographics, lab values (serum creatinine, weight), allergies, and medication orders
- [ ] **Clinical impact reporting** — tracks intervention rates and acceptance by prescribers

---

## 4. Healthcare-Associated Infection (HAI) Detection

*AI-assisted surveillance for CLABSI, CAUTI, VAE, SSI, and CDI with IP review workflow*

- [ ] **5 HAI types monitored:** CLABSI, CAUTI, VAE, SSI, CDI
- [ ] **Multi-stage detection pipeline:**
  - [ ] Rule-based screening (organism detection, device association, timing criteria)
  - [ ] LLM-powered clinical note extraction (structured evidence extraction from free text)
  - [ ] NHSN criteria engine (automated application of CDC/NHSN surveillance definitions)
  - [ ] Infection Preventionist review queue with override tracking
- [ ] **LLM classification with confidence scoring** — AI assigns HAI probability with supporting and contradicting evidence
- [ ] **IP review workflow:**
  - [ ] Candidates triaged into IP Review or Manual Review queues
  - [ ] IP decisions: Confirmed, Rejected, Needs More Information
  - [ ] Override categories: extraction error, rules error, clinical judgment, missing documentation, NHSN interpretation
  - [ ] Override tracking feeds back into system accuracy monitoring
- [ ] **Device-day association** — automatic catheter-day, ventilator-day, and central line–day tracking
- [ ] **Type-specific data capture:**
  - [ ] CLABSI: central line type, insertion date, line-days
  - [ ] CAUTI: catheter type, catheter-days, urine culture colony count
  - [ ] VAE: ventilator parameters (FiO2, PEEP trends), onset timing
  - [ ] SSI: procedure type, wound class, SSI depth (superficial/deep/organ-space)
  - [ ] CDI: onset classification (community vs. healthcare), recurrence tracking
- [ ] **LLM audit logging** — model version, token counts, response time, success/failure rate for quality monitoring
- [ ] **NHSN reporting integration** — confirmed HAIs automatically staged for NHSN event submission
- [ ] **FHIR-integrated** — Observation (cultures, vitals, device info), DocumentReference (clinical notes), Encounter (location/timing)

---

## 5. MDRO Surveillance

*Multidrug-resistant organism detection, classification, and transmission tracking*

- [ ] **6 MDRO types tracked:** MRSA, VRE, CRE, ESBL-producing Enterobacterales, CRPA, CRAB
- [ ] **Automated culture result screening** — FHIR DiagnosticReport polling identifies resistant organisms from susceptibility panels
- [ ] **Transmission classification** — community-onset vs. healthcare-onset determination based on admission date and culture timing
- [ ] **Prior isolation history** — tracks patient history of MDRO colonization/infection for precaution decision support
- [ ] **Unit-level clustering** — identifies geographic concentrations of same-organism MDRO cases for outbreak signaling
- [ ] **IP classification and review** — dedicated review workflow with reviewer notes and reclassification capability
- [ ] **Deduplication logic** — processing log prevents duplicate case creation from repeated culture results
- [ ] **Analytics dashboards:**
  - [ ] Cases by MDRO type (trending over time)
  - [ ] Healthcare-onset vs. community-onset distribution
  - [ ] Unit-level case density maps
  - [ ] 30-day recent case summary
- [ ] **Integration with Outbreak Detection** — MDRO cases feed directly into spatial/temporal clustering algorithms

---

## 6. Outbreak Detection & Cluster Analysis

*Automated spatial-temporal clustering of MDRO and HAI events for early outbreak identification*

- [ ] **Multi-algorithm cluster detection:**
  - [ ] Spatial clustering (same unit, same organism within defined time window)
  - [ ] Temporal clustering (case count exceeding baseline threshold in rolling window)
  - [ ] Organism-based grouping (species-level or resistance phenotype–level clustering)
- [ ] **Combined MDRO + HAI integration** — detects outbreaks from both resistant organism cases and HAI events
- [ ] **Cluster lifecycle management:**
  - [ ] Status tracking: Active → Controlled → Resolved
  - [ ] Severity assessment with attack rate calculation
  - [ ] Case count and affected unit tracking
- [ ] **Transmission pathway analysis:**
  - [ ] Index case identification
  - [ ] Secondary and tertiary case role assignment
  - [ ] Transmission chain visualization data
- [ ] **Unit-level risk assessment** — identifies units with elevated organism activity before formal cluster declaration
- [ ] **Dashboard with active cluster monitoring** — real-time view of active outbreaks with case timelines and unit maps
- [ ] **Automated alerting** — OUTBREAK_CLUSTER alerts generated with affected unit and organism details

---

## 7. Antimicrobial Usage Monitoring

*Broad-spectrum antibiotic duration tracking with de-escalation workflow support*

- [ ] **Broad-spectrum duration monitoring** — automatic tracking of meropenem, vancomycin, and other high-priority agents
- [ ] **Tiered severity escalation:**
  - [ ] ≥ 72 hours on broad-spectrum agent → HIGH severity alert
  - [ ] ≥ 144 hours on broad-spectrum agent → CRITICAL severity alert
- [ ] **De-escalation workflow documentation** — structured resolution for therapy narrowing, discontinuation, or clinical justification
- [ ] **Medication order tracking** — order ID, start/stop dates, cumulative days on therapy, indication
- [ ] **Deduplication** — prevents duplicate alerts for the same medication order
- [ ] **FHIR-integrated** — pulls MedicationRequest (active orders) and MedicationAdministration (actual administration records)
- [ ] **Dashboard with medication-type filtering** — view active alerts by specific antimicrobial agent

---

## 8. Antibiotic Indication Assessment

*AI-powered extraction and evaluation of antibiotic indications from clinical documentation*

- [ ] **41-syndrome clinical taxonomy** — standardized syndrome classification (CAP, UTI, meningitis, bacteremia, SSTI, febrile neutropenia, etc.)
- [ ] **LLM-powered indication extraction** — parses clinical notes to identify documented indications for antimicrobial therapy
- [ ] **Syndrome confidence scoring** — Definite, Probable, or Unclear indication assessment
- [ ] **Therapy intent classification** — Empiric, Directed, Prophylaxis, or Unknown
- [ ] **Red flag detection:**
  - [ ] Indication not documented in clinical notes
  - [ ] Likely viral syndrome treated with antibiotics
  - [ ] Asymptomatic bacteriuria treatment
  - [ ] Never-appropriate antibiotic use
- [ ] **CCHMC guideline matching** — 57 disease-specific guidelines with first-line and alternative agent recommendations
- [ ] **Pharmacist review workflow:**
  - [ ] Syndrome confirmation or correction
  - [ ] Agent appropriateness assessment (Appropriate, Acceptable, Inappropriate)
  - [ ] Override tracking for stewardship quality metrics
- [ ] **Supporting evidence capture** — direct quotes from clinical notes used for indication determination
- [ ] **Compliance metrics** — indication documentation rates, guideline adherence rates, inappropriate use rates
- [ ] **FHIR-integrated** — MedicationRequest, DocumentReference (clinical notes), Condition (diagnoses), Encounter

---

## 9. Surgical Prophylaxis Compliance

*Real-time 7-element ASHP surgical prophylaxis bundle monitoring with HL7 ADT integration*

- [ ] **7-element ASHP bundle evaluation:**
  - [ ] Appropriate prophylactic agent selection per procedure type
  - [ ] Timing: infusion complete within 60 min of incision (120 min for vancomycin/fluoroquinolones)
  - [ ] Weight-based dosing verification
  - [ ] Intraoperative redosing for prolonged procedures
  - [ ] Discontinuation timing (24h standard, 48h for cardiac/orthopedic)
  - [ ] Beta-lactam allergy alternative verification
  - [ ] MRSA colonization screening and vancomycin prophylaxis when indicated
- [ ] **Real-time HL7 ADT integration:**
  - [ ] MLLP async TCP server on port 2575
  - [ ] ADT^A01 (Admit), ADT^A02 (Transfer), ADT^A03 (Discharge) processing
  - [ ] ORM^O01 (surgical order) and SIU^S12 (scheduling) message parsing
- [ ] **Surgical journey state machine:**
  - [ ] Patient tracking: Inpatient → Pre-Op Holding → OR Suite → PACU → Discharged
  - [ ] Real-time location updates from ADT messages
- [ ] **Multi-level alert escalation:**
  - [ ] T-24h: initial prophylaxis order check
  - [ ] T-2h: pre-op arrival verification
  - [ ] T-60min: final timing check
  - [ ] T-0 (OR entry): last-chance escalation
  - [ ] Escalation chain: Pharmacy → Pre-Op RN → Anesthesia → Surgeon → ASP
- [ ] **Procedure classification** — CPT code–based procedure categorization with guideline mapping
- [ ] **Patient factor capture** — weight, age, allergies, MRSA colonization status, beta-lactam allergy status
- [ ] **Per-element compliance scoring** — individual element pass/fail with overall bundle compliance percentage
- [ ] **Surgeon and unit-level compliance metrics** — aggregate reporting for quality improvement
- [ ] **Dual-mode operation:**
  - [ ] Batch mode: FHIR polling for retrospective analysis
  - [ ] Real-time mode: HL7 ADT/ORM/SIU for intraoperative alerting

---

## 10. Clinical Guideline Adherence Monitoring

*Tiered NLP pipeline for monitoring adherence to evidence-based clinical practice guidelines*

- [ ] **9 clinical guideline bundles:**
  - [ ] Pediatric Sepsis (age-stratified: neonate, infant, child, adolescent)
  - [ ] Community-Acquired Pneumonia (CAP)
  - [ ] Febrile Infant — AAP 2021 guidelines (0–3 months, age-stratified criteria)
  - [ ] Neonatal HSV (classification-based: SEM, CNS, disseminated)
  - [ ] C. difficile Testing Stewardship (diagnostic appropriateness)
  - [ ] Febrile Neutropenia
  - [ ] Surgical Prophylaxis (ASHP bundle)
  - [ ] Urinary Tract Infection (UTI)
  - [ ] Skin and Soft Tissue Infection (SSTI)
- [ ] **3 coordinated monitoring modes:**
  - [ ] Trigger monitoring: FHIR polling for conditions that activate guideline bundles
  - [ ] Episode monitoring: deadline violation detection for time-sensitive elements
  - [ ] Adherence monitoring: element completion tracking against bundle requirements
- [ ] **Tiered NLP pipeline:**
  - [ ] 7B triage model (qwen2.5:7b) for fast initial assessment
  - [ ] 70B analysis model (llama3.3:70b) for complex clinical reasoning
  - [ ] 5 escalation triggers for automatic referral to higher-tier analysis
- [ ] **7 element checker modules:**
  - [ ] Lab result requirements (blood cultures, CSF analysis, urinalysis, etc.)
  - [ ] Medication ordering (empiric therapy, targeted therapy, prophylaxis)
  - [ ] Documentation requirements (assessment notes, handoff documentation)
  - [ ] Febrile Infant–specific (AAP 2021 age-stratified WBC/UA/inflammatory markers)
  - [ ] HSV-specific (classification-based treatment algorithms)
  - [ ] CDI Testing–specific (diagnostic stewardship criteria)
  - [ ] Generic element checking (configurable for custom bundles)
- [ ] **Episode lifecycle management:**
  - [ ] Active → Complete → Closed status tracking
  - [ ] Deadline tracking with adherence calculation
  - [ ] Element-level status: Met, Not Met, Pending, N/A, Unable to Assess
- [ ] **IP review workflow** — human review with override tracking and deviation documentation
- [ ] **Analytics:**
  - [ ] Adherence rates per bundle
  - [ ] Element completion rates (identify which bundle elements are most frequently missed)
  - [ ] LLM accuracy vs. IP decision concordance
  - [ ] Override statistics for quality monitoring

---

## 11. NHSN Regulatory Reporting

*Automated CDC/NHSN data extraction, aggregation, and electronic submission for AU, AR, and HAI modules*

- [ ] **3 NHSN reporting domains:**
  - [ ] **Antimicrobial Usage (AU):**
    - [ ] Days of Therapy (DOT) calculation per antimicrobial agent
    - [ ] Defined Daily Dose (DDD) calculation (WHO standard)
    - [ ] Route-specific tracking (IV, PO, IM, topical, inhaled)
    - [ ] Monthly summary aggregation by location
    - [ ] Patient-level usage detail
  - [ ] **Antimicrobial Resistance (AR):**
    - [ ] Culture isolate tracking with organism identification
    - [ ] First-isolate rule (one per patient, organism, location per 365-day window)
    - [ ] 9 resistance phenotype detection (MRSA, VRE, ESBL, CRE, CRPA, CRAB, MDR, etc.)
    - [ ] Susceptibility result storage (S/I/R with MIC values)
    - [ ] Quarterly summary by organism and phenotype
  - [ ] **HAI Event Submission:**
    - [ ] CLABSI, CAUTI, SSI, VAE event packaging
    - [ ] Integration with HAI Detection module (confirmed cases auto-staged)
- [ ] **Denominator data management:**
  - [ ] Daily patient-day counts by location
  - [ ] Device-day tracking (central line–days, catheter-days, ventilator-days)
  - [ ] Admission counts
  - [ ] Monthly aggregation with recursive CTE calculations
- [ ] **CDA R2 XML generation** — HL7 Clinical Document Architecture for NHSN electronic submission
- [ ] **DIRECT protocol transmission** — SMTP/TLS submission via Health Information Service Provider (HISP)
- [ ] **NHSN OID mapping** — standard LOINC and SNOMED coding for interoperability
- [ ] **Submission audit trail** — complete log of all submissions with status tracking
- [ ] **Clarity database integration** — extracts MAR data and culture results from Epic reporting database
- [ ] **CSV export** for manual submission or external analysis
- [ ] **Mock data support** — SQLite-backed development mode for testing without Clarity access

---

## 12. Bacteremia Monitoring

*Blood culture coverage assessment for patients with positive blood cultures*

- [ ] **Automated blood culture detection** — FHIR Observation polling for LOINC 600-7 (blood culture) results
- [ ] **Antimicrobial coverage assessment** — evaluates whether current antimicrobial therapy provides adequate coverage for identified organisms
- [ ] **Coverage rules engine:**
  - [ ] Organism categorization (Gram-positive, Gram-negative, atypical, anaerobic, fungal)
  - [ ] Antibiotic effectiveness mapping (susceptible, resistant, intermediate)
  - [ ] ESBL-specific coverage rules (e.g., meropenem adequate for ESBL-producing Enterobacterales)
- [ ] **High-priority alerting** — BACTEREMIA alerts generated at HIGH severity with priority score 80
- [ ] **Integration with ASP Alerts** — uses shared coverage rules for consistent susceptibility interpretation

---

## 13. Action Analytics & Stewardship Metrics

*Workload analytics and intervention tracking for stewardship program evaluation*

- [ ] **Provider activity tracking** — actions per module, per user, with duration metrics
- [ ] **Daily snapshot aggregation** — module-specific counts and statistics compiled nightly
- [ ] **Dashboard analytics by module, provider, and unit**
- [ ] **Time-range filtering** for trend analysis
- [ ] **Alert acknowledgment rate tracking** — measures response times and resolution patterns
- [ ] **Workload distribution analytics** — identifies staffing patterns and alert volume trends
- [ ] **JSON API endpoints** for integration with external BI/reporting tools

---

## 14. REST API & Integration Layer

*Standards-based programmatic access for dashboards, mobile apps, and third-party system integration*

- [ ] **RESTful API at `/api/v1/`** with 11 resource endpoints + 2 authentication endpoints
- [ ] **Swagger/OpenAPI documentation** at `/api/docs/` with interactive testing
- [ ] **Token-based authentication** (DRF TokenAuth)
- [ ] **Rate limiting** — 100 reads/min, 30 writes/min per authenticated user
- [ ] **Role-based access control** — 7 permission classes mapped to clinical roles
- [ ] **PHI-safe error handling** — automatic stripping of patient MRN and name from error responses
- [ ] **Full CRUD operations** on alerts, HAI candidates, outbreak clusters, guideline episodes, surgical cases, indication candidates, and NHSN events
- [ ] **Bulk operations** — batch acknowledge, batch resolve for high-volume alert management
- [ ] **Filter and search** — query parameters for type, status, severity, patient, date range, unit

---

## 15. Authentication, Authorization & HIPAA Compliance

*Enterprise identity management with comprehensive audit logging*

- [ ] **3 authentication methods:**
  - [ ] SAML 2.0 (enterprise SSO)
  - [ ] LDAP (Active Directory integration)
  - [ ] Local credentials (fallback)
- [ ] **4 clinical roles:** ASP Pharmacist, Infection Preventionist, Physician, Administrator
- [ ] **Module-level access control** — granular permissions for dosing, HAI, MDRO, surgical prophylaxis, NHSN, guideline adherence
- [ ] **Active Directory group mapping** — automatic role assignment from AD group membership
- [ ] **Account lockout** — 5 failed login attempts trigger 30-minute lockout with IP logging
- [ ] **Session tracking** — login method, IP address, user agent, session duration, logout time
- [ ] **HIPAA-compliant audit middleware:**
  - [ ] Every HTTP request/response logged
  - [ ] User identity, timestamp, IP address, action type
  - [ ] Alert-level audit trail with old/new status tracking
- [ ] **Per-user notification preferences** — email and Microsoft Teams opt-in/out
- [ ] **Soft-delete across all clinical data** — no permanent data destruction, full historical preservation

---

## 16. Data Integration & Interoperability

*Multi-source clinical data integration for comprehensive surveillance*

- [ ] **FHIR R4 client library:**
  - [ ] HAPI FHIR server support (basic auth)
  - [ ] Epic FHIR R4 OAuth 2.0 support (JWT bearer flow, RS384 signature, non-user service credentials)
  - [ ] 10 supported FHIR resource types: Patient, Observation, MedicationRequest, MedicationAdministration, Condition, Procedure, DocumentReference, Encounter, Appointment, DiagnosticReport
  - [ ] Bundle pagination and extraction
  - [ ] FHIR datetime parsing
- [ ] **HL7 v2.x ADT integration:**
  - [ ] MLLP async TCP server
  - [ ] ADT (A01/A02/A03), ORM (O01), SIU (S12) message parsing
  - [ ] Real-time patient location tracking
- [ ] **Epic Clarity database integration:**
  - [ ] Read-only connection to Epic reporting database
  - [ ] MAR extraction for antimicrobial usage
  - [ ] Culture/susceptibility result extraction
  - [ ] Patient census for denominator calculations
- [ ] **Ollama LLM integration:**
  - [ ] Local deployment (no PHI leaves the network)
  - [ ] Dual-model architecture: 7B triage + 70B analysis
  - [ ] Clinical note parsing, syndrome extraction, guideline adherence assessment
  - [ ] Full audit logging (tokens, latency, accuracy)
- [ ] **NHSN DIRECT protocol:**
  - [ ] SMTP/TLS electronic submission
  - [ ] CDA R2 XML formatting
  - [ ] HISP routing

---

## 17. Infrastructure & Operations

*Production-grade deployment with monitoring, scheduling, and high availability*

- [ ] **Background task scheduling (Celery):**
  - [ ] 3 task queues: default (FHIR polling), LLM (GPU inference), batch (nightly extractions)
  - [ ] 15+ periodic tasks across all clinical modules
  - [ ] 5-minute polling for critical modules (MDRO, drug-bug)
  - [ ] Nightly batch jobs for NHSN data extraction (2–3 AM)
  - [ ] Automatic retries with exponential backoff (max 3 retries)
- [ ] **Health monitoring endpoint** — `/health/` checks database, Redis, and Ollama with latency metrics
- [ ] **PostgreSQL 16** on ZFS with optimized recordsize (8K), LZ4 compression
- [ ] **Redis caching** — 2 GB, allkeys-LRU eviction
- [ ] **Gunicorn application server** — 4 workers, systemd-managed
- [ ] **Nginx reverse proxy** — TLS via Let's Encrypt, gzip compression, static file serving
- [ ] **CI/CD pipeline** — GitHub Actions (Python 3.12, automated test suite on push/PR)
- [ ] **1,120 automated tests** — unit, integration, and security tests across all 12 clinical modules
- [ ] **Management commands** — demo data generation, manual monitoring, dry-run modes for every module

---

## Comparison Summary

| Capability | AEGIS |
|---|---|
| Clinical modules | 12 |
| Alert types | 27 |
| HAI types monitored | 5 (CLABSI, CAUTI, VAE, SSI, CDI) |
| MDRO types tracked | 6 (MRSA, VRE, CRE, ESBL, CRPA, CRAB) |
| Dosing rule categories | 9 |
| Guideline bundles | 9 |
| NHSN reporting domains | 3 (AU, AR, HAI) |
| Surgical prophylaxis elements | 7 (full ASHP bundle) |
| FHIR resource types | 10 |
| Data sources | 4 (FHIR, Clarity, HL7 ADT, LLM) |
| AI/NLP capabilities | Yes — local LLM (no cloud PHI exposure) |
| Real-time alerting | Yes — HL7 ADT + FHIR polling (5-min minimum) |
| NHSN electronic submission | Yes — CDA R2 + DIRECT protocol |
| REST API | Yes — 11 endpoints + Swagger docs |
| SSO support | SAML 2.0 + LDAP |
| HIPAA audit logging | Yes — request-level + alert-level |
| Automated tests | 1,120 |
| Pediatric-specific | Yes — age-stratified dosing, AAP guidelines |

---

*Document generated for IS evaluation — AEGIS v1.0*
*Cincinnati Children's Hospital Medical Center*
