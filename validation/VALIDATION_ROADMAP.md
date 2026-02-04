# AEGIS LLM Extraction Validation Roadmap

## Overview

This document outlines a prioritized plan for validating all LLM extraction workflows in AEGIS. The goal is to establish gold standard validation sets for each extractor and achieve ≥90% field-level accuracy.

## Priority Ranking Criteria

Extractors are prioritized based on:
1. **Clinical impact** - How critical is accurate extraction for patient safety?
2. **Deployment readiness** - How close is this module to production use?
3. **Complexity** - How many fields and edge cases need validation?
4. **Dependencies** - Does this extractor feed into other workflows?

---

## Phase 1: High Priority (Complete by Q2 2026)

### 1.1 CLABSI Extractor ⭐ HIGHEST PRIORITY
**Location:** `hai-detection/hai_src/extraction/clabsi_extractor.py`

**Rationale:**
- CLABSI is the most scrutinized HAI for NHSN reporting
- MBI-LCBI pathway has complex extraction requirements
- Commensal detection is prone to hallucination

**Validation Target:** 25 cases
| Case Mix | Count |
|----------|-------|
| True CLABSI (recognized pathogen) | 8 |
| True CLABSI (commensal, 2 sets) | 5 |
| Contaminant (commensal, 1 set) | 5 |
| MBI-LCBI | 4 |
| Negative (line present, no BSI) | 3 |

**Key Fields to Validate:**
- [ ] Alternate infection sites (pneumonia, UTI, SSI, intra-abdominal)
- [ ] Fever/hypothermia/apnea/bradycardia extraction
- [ ] MBI factors (mucositis, GVHD, diarrhea, NEC, neutropenia)
- [ ] Line attribution in clinical notes
- [ ] Contamination signals
- [ ] Temporal accuracy (dates)

**Hallucination Risks:**
- Template text interpreted as clinical findings
- Historical events confused with current admission
- "Rule out" language interpreted as diagnosis

---

### 1.2 Indication Extractor ⭐ HIGH PRIORITY
**Location:** `abx-indications/indication_extractor.py`, `antimicrobial-usage-alerts/au_alerts_src/llm_extractor.py`

**Rationale:**
- Feeds antimicrobial stewardship alerts
- Red flag detection (viral treatment, ASB) has direct intervention value
- Used across multiple workflows

**Validation Target:** 30 cases
| Case Mix | Count |
|----------|-------|
| Clear indication (CAP, UTI, cellulitis) | 10 |
| Empiric, unclear indication | 6 |
| Asymptomatic bacteriuria (should flag) | 4 |
| Likely viral (should flag) | 4 |
| Culture-directed therapy | 4 |
| Prophylaxis | 2 |

**Key Fields to Validate:**
- [ ] Primary indication mapping to taxonomy
- [ ] Confidence level accuracy
- [ ] Therapy intent (empiric/directed/prophylaxis)
- [ ] Red flag detection (ASB, viral)
- [ ] Evidence quote accuracy
- [ ] Culture organism extraction

---

### 1.3 Two-Stage Triage Extractor
**Location:** `hai-detection/hai_src/extraction/triage_extractor.py`

**Rationale:**
- Escalation decisions affect efficiency and accuracy
- False negatives (missed escalations) could miss infections
- Novel approach requiring validation

**Validation Target:** 40 cases
| Case Mix | Count |
|----------|-------|
| Clear well (no escalation needed) | 15 |
| Clear ill (no escalation needed) | 10 |
| Needs escalation (complex) | 10 |
| Edge cases (poor documentation) | 5 |

**Metrics Focus:**
- [ ] Escalation sensitivity (catch all complex cases)
- [ ] Escalation specificity (don't over-escalate)
- [ ] Documentation quality assessment accuracy

---

## Phase 2: Medium Priority (Complete by Q3 2026)

### 2.1 VAE Extractor
**Location:** `hai-detection/hai_src/extraction/vae_extractor.py`

**Validation Target:** 20 cases

**Key Considerations:**
- Temperature/WBC extraction relatively straightforward
- Antimicrobial duration tracking needs validation
- Purulent secretions description extraction
- Respiratory culture result interpretation

---

### 2.2 CAUTI Extractor
**Location:** `hai-detection/hai_src/extraction/cauti_extractor.py`

**Validation Target:** 20 cases

**Key Considerations:**
- Age-based fever rule (>65 years)
- Symptom extraction when patient has catheter (urgency/frequency not assessable)
- Distinguishing ASB from CAUTI

---

### 2.3 SSI Extractor
**Location:** `hai-detection/hai_src/extraction/ssi_extractor.py`

**Validation Target:** 20 cases

**Key Considerations:**
- Three-tier classification (superficial/deep/organ-space)
- Wound assessment temporal tracking
- Reoperation findings extraction
- Multiple wound assessments over time

---

## Phase 3: Lower Priority (Complete by Q4 2026)

### 3.1 CDI Extractor
**Location:** `hai-detection/hai_src/extraction/cdi_extractor.py`

**Validation Target:** 15 cases

**Key Considerations:**
- CDI extraction simpler than device-associated HAIs
- Most classification from structured data (timing)
- Prior CDI history extraction for recurrence detection

---

### 3.2 Clinical Appearance Triage
**Location:** `guideline-adherence/guideline_src/nlp/triage_extractor.py`

**Validation Target:** 20 cases

**Key Considerations:**
- Fast triage for well/ill/toxic appearance
- Escalation triggers validation

---

## Validation Infrastructure

### Required Components

1. **Gold Standard Cases** ✅ Templates created
   - `gold_standard_example_case.json` (CLABSI)
   - `gold_standard_cauti_template.json`
   - `gold_standard_vae_template.json`
   - `gold_standard_ssi_template.json`
   - `gold_standard_cdi_template.json`

2. **Validation Runner** ✅ Created
   - `validation_runner.py`
   - Field-level comparison with semantic matching
   - Aggregate metrics (precision, recall, F1)
   - Hallucination tracking

3. **Case Collection Workflow** 🔲 TODO
   - Query templates for Clarity (`aegis_clarity_queries.sql`)
   - Adjudication template (`aegis_case_adjudication_template.docx`)
   - Note de-identification process

4. **Continuous Validation Pipeline** 🔲 TODO
   - Nightly runs against gold standard set
   - Regression detection
   - Model version comparison

---

## Metrics and Thresholds

### Minimum Acceptance Criteria

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Overall field accuracy | ≥90% | Across all extraction fields |
| Boolean field accuracy | ≥95% | Present/absent determinations |
| Confidence level accuracy | ≥85% | definite/probable/not_found |
| Hallucination rate | ≤5% | Fabricated information |
| Quote accuracy | ≥80% | Quoted text actually in notes |

### Per-Extractor Targets

| Extractor | Target Accuracy | Current | Status |
|-----------|-----------------|---------|--------|
| CLABSI | 92% | TBD | 🔲 |
| Indication | 90% | TBD | 🔲 |
| Triage | 95% | TBD | 🔲 |
| VAE | 90% | TBD | 🔲 |
| CAUTI | 90% | TBD | 🔲 |
| SSI | 88% | TBD | 🔲 |
| CDI | 92% | TBD | 🔲 |

---

## Case Collection Timeline

### Q2 2026
- [ ] Collect 25 CLABSI cases from Vigilanz matches
- [ ] Collect 30 indication extraction cases
- [ ] Collect 40 triage cases (20 well, 20 ill/complex)

### Q3 2026
- [ ] Collect 20 VAE cases
- [ ] Collect 20 CAUTI cases
- [ ] Collect 20 SSI cases

### Q4 2026
- [ ] Collect 15 CDI cases
- [ ] Collect 20 clinical appearance triage cases
- [ ] Complete full validation suite

---

## Process for Adding Cases

1. **Identify Candidate**
   - Query Clarity for encounters matching criteria
   - Ensure variety in case complexity and outcomes

2. **Pull Clinical Notes**
   - Run de-identification if needed
   - Store in `validation/cases/{hai_type}/notes/`

3. **Adjudicate**
   - Use `aegis_case_adjudication_template.docx`
   - Two-reviewer process for disputed cases
   - Document rationale thoroughly

4. **Create Gold Standard JSON**
   - Copy appropriate template
   - Fill all fields
   - Add hallucination risks
   - Store in `validation/cases/{hai_type}/`

5. **Validate**
   - Run `validation_runner.py --hai-type {type}`
   - Review mismatches
   - Update extractor or gold standard as needed

---

## Contacts

| Role | Person | Responsibility |
|------|--------|----------------|
| Validation Lead | TBD | Case collection, adjudication |
| Technical Lead | DBH | Extractor fixes, pipeline |
| Clinical SME | TBD | Complex case adjudication |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-02-04 | Claude/DBH | Initial roadmap creation |
