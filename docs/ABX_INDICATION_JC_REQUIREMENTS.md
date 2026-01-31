# Antibiotic Indication: Joint Commission Requirements

This document clarifies what Joint Commission (JC) actually requires for antibiotic indication documentation and how AEGIS should implement it.

## Key Clarification

**Joint Commission wants the clinical syndrome/diagnosis, NOT ICD-10 codes.**

The relevant standards are MM.09.01.01 EP 13 (revised) and EP 15 (revised).

## Three Distinct Concepts

| Concept | What It Means | JC Requirement |
|---------|---------------|----------------|
| **Indication** | The clinical syndrome being treated (e.g., "CAP", "cUTI", "sepsis") | Must be documented at order entry |
| **Evidence-based use** | Is the antibiotic choice consistent with hospital guidelines for that indication? | ASP must document hospital-wide alignment |
| **Appropriateness** | Clinical judgment on whether therapy is optimal | NOT directly required by JC |

## Valid Clinical Syndrome Indications

JC expects indications like these (NOT ICD-10 codes):

**Respiratory:**
- Community-acquired pneumonia (CAP)
- Hospital-acquired pneumonia (HAP)
- Ventilator-associated pneumonia (VAP)
- Aspiration pneumonia

**Urinary:**
- Urinary tract infection (UTI) - uncomplicated
- Complicated UTI (cUTI)
- Catheter-associated UTI (CAUTI)
- Pyelonephritis

**Skin/Soft Tissue:**
- Cellulitis
- Wound infection
- Abscess
- Necrotizing fasciitis

**Intra-abdominal:**
- Appendicitis
- Cholecystitis
- Diverticulitis
- Peritonitis

**Bloodstream:**
- Sepsis (source unknown)
- Bacteremia (with source: e.g., "line-related bacteremia")
- Endocarditis

**Surgical:**
- Surgical prophylaxis
- Surgical site infection (SSI)

**Other:**
- Meningitis
- Osteomyelitis
- Empiric therapy (with expectation of refinement)
- Febrile neutropenia

## Current vs. Required Implementation

### Current Approach (Needs Revision)

```
ICD-10 Codes → Chua Classification → A/S/N/P/FN/U
```

**Problem**: ICD-10 codes are billing constructs, not clinical decision points. They:
- May not be available at time of antibiotic order
- Don't reflect the clinical syndrome driving treatment
- Miss the "at order entry" requirement

### Required Approach

```
Order Entry Indication Field → Clinical Syndrome Extraction → Guideline Comparison
           ↓                            ↓                            ↓
   (Epic may capture)           (LLM from notes)            (Local guidelines)
```

## Implementation Plan

### Phase 1: Extract Clinical Syndrome (Priority)

The LLM should extract the **clinical indication/syndrome** from:

1. **Order entry indication field** (if Epic captures it)
2. **Clinical notes** (Assessment/Plan, ID consult)
3. **Inferred from context** (positive culture + antibiotic start)

**Output format:**
```json
{
  "indicated_syndrome": "community-acquired pneumonia",
  "indication_source": "progress_note",
  "indication_confidence": "high",
  "supporting_quote": "Started ceftriaxone + azithromycin for CAP"
}
```

### Phase 2: Compare to Local Guidelines

Map the extracted syndrome to CCHMC's specific guidelines:

```json
{
  "syndrome": "community-acquired pneumonia",
  "prescribed_agent": "ceftriaxone",
  "guideline_first_line": ["ampicillin", "amoxicillin"],
  "guideline_alternative": ["ceftriaxone", "azithromycin"],
  "assessment": "alternative_agent",
  "note": "First-line is ampicillin; ceftriaxone acceptable for severe CAP"
}
```

### Phase 3: Flag Discordance for ASP Review

Alert when:
1. **No indication documented** - Order lacks syndrome
2. **Indication unclear** - Notes don't support antibiotic start
3. **Agent-syndrome mismatch** - Antibiotic doesn't match guideline for syndrome

## Changes Required to ABX Indications Module

### Current Structure

```
abx-indications/
├── pediatric_abx_indications.py  # Chua ICD-10 classification
├── cchmc_guidelines.py           # Agent appropriateness
└── data/
    ├── cchmc_disease_guidelines.json  # By ICD-10
    └── cchmc_antimicrobial_dosing.json
```

### Proposed Changes

1. **Add syndrome extraction** (LLM-based):
   - Extract clinical syndrome from notes
   - Map to standardized syndrome vocabulary
   - Capture at-order indication if available

2. **Revise guideline matching**:
   - Match by syndrome, not ICD-10
   - Use CCHMC-specific pathways per syndrome
   - Support "empiric" as valid indication

3. **Update alerts**:
   - "No documented indication" (not "N" per Chua)
   - "Agent not recommended for [syndrome]"
   - "Spectrum broader than syndrome requires"

## Data Collection for Training

Same pattern as HAI detection:

```json
{
  "case_id": "...",
  "input_notes": "...",
  "extraction": {
    "syndrome": "UTI",
    "confidence": "high"
  },
  "prescribed_agent": "ciprofloxacin",
  "guideline_comparison": {
    "first_line": ["nitrofurantoin", "TMP-SMX"],
    "matches_guideline": false
  },
  "human_review": {
    "confirmed_syndrome": "complicated UTI",
    "assessment": "appropriate - patient has allergy"
  }
}
```

## References

- Joint Commission MM.09.01.01 EP 13-15 (2024 revision)
- CDC Core Elements of Hospital Antibiotic Stewardship
- IDSA/SHEA Guidelines for Antimicrobial Stewardship

---

## TODO

- [ ] Add syndrome vocabulary standardization
- [ ] Update LLM prompts to extract clinical syndrome (not ICD-10)
- [ ] Revise `cchmc_disease_guidelines.json` to be syndrome-based
- [ ] Create syndrome → guideline mapping
- [ ] Update alerting logic for JC compliance
- [ ] Add training data collection to ABX workflow

---

*Last updated: January 2026*
