# Antibiotic Indication: Joint Commission Requirements

This document describes the JC-compliant clinical syndrome extraction implemented in AEGIS.

## Key Clarification

**Joint Commission wants the clinical syndrome/diagnosis, NOT ICD-10 codes.**

The relevant standards are MM.09.01.01 EP 13 (revised) and EP 15 (revised).

## Three Distinct Concepts

| Concept | What It Means | JC Requirement | AEGIS Implementation |
|---------|---------------|----------------|---------------------|
| **Indication** | The clinical syndrome being treated (e.g., "CAP", "cUTI", "sepsis") | Must be documented at order entry | LLM extraction from notes |
| **Evidence-based use** | Is the antibiotic choice consistent with hospital guidelines for that indication? | ASP must document hospital-wide alignment | CCHMC guideline matching |
| **Appropriateness** | Clinical judgment on whether therapy is optimal | NOT directly required by JC | Optional human review |

## Implementation Architecture

```
Clinical Notes → LLM Extraction → Syndrome Taxonomy → Guideline Matching
       ↓              ↓                  ↓                   ↓
   (48h window)  (qwen2.5:7b)    (40+ syndromes)      (CCHMC pathways)
                      ↓
              Human Review (optional)
                      ↓
              Training Data Collection
```

### Phase 1: Clinical Syndrome Extraction ✓ IMPLEMENTED

**File:** `abx-indications/indication_extractor.py`

The LLM extracts the clinical syndrome from notes:

```json
{
  "primary_indication": "cap",
  "primary_indication_display": "Community-Acquired Pneumonia",
  "indication_category": "respiratory",
  "indication_confidence": "definite",
  "therapy_intent": "empiric",
  "supporting_evidence": ["fever x3 days", "RLL infiltrate on CXR"],
  "evidence_quotes": ["Started ceftriaxone + azithromycin for CAP"]
}
```

**Red flags detected:**
- `likely_viral` - Notes suggest viral illness but antibiotics given
- `asymptomatic_bacteriuria` - Positive UA without UTI symptoms
- `indication_not_documented` - No indication found in notes
- `never_appropriate` - Indication where antibiotics rarely/never indicated

### Phase 2: Syndrome Taxonomy ✓ IMPLEMENTED

**File:** `abx-indications/indication_taxonomy.py`

~40 clinical syndromes mapped to CCHMC guideline disease IDs:

| Category | Syndromes |
|----------|-----------|
| Respiratory | CAP, HAP, VAP, aspiration pneumonia, empyema |
| Urinary | Simple UTI, pyelonephritis, CAUTI |
| Bloodstream | Bacteremia (GPC/GNR), sepsis, line infection, endocarditis |
| Skin/Soft Tissue | Cellulitis, abscess, wound infection, necrotizing fasciitis |
| Intra-abdominal | Appendicitis, peritonitis, C. diff |
| CNS | Meningitis, VP shunt infection, brain abscess |
| Bone/Joint | Osteomyelitis, septic arthritis |
| ENT | AOM, sinusitis, strep pharyngitis, mastoiditis |
| Eye | Orbital cellulitis, periorbital cellulitis |
| Febrile Neutropenia | Febrile neutropenia |
| Prophylaxis | Surgical prophylaxis, PCP prophylaxis, SBP prophylaxis |

**Never-appropriate indications (triggers alert):**
- Bronchiolitis (viral)
- Viral URI
- Asymptomatic bacteriuria

### Phase 3: Guideline Matching ✓ IMPLEMENTED

Each syndrome maps to CCHMC guideline disease IDs:
- `cap` → `["cap_infant_preschool", "cap_school_aged"]`
- `uti_complicated` → `["pyelonephritis", "febrile_uti"]`
- `febrile_neutropenia` → `["fever_neutropenia"]`

CCHMC engine checks if prescribed agent is:
- `first_line` - Matches guideline
- `alternative` - Acceptable alternative
- `off_guideline` - Needs ASP review

### Phase 4: Human Review ✓ IMPLEMENTED

**Syndrome Review Decisions:**
| Decision | Meaning |
|----------|---------|
| `confirm_syndrome` | LLM extraction is correct |
| `correct_syndrome` | Change to different syndrome |
| `no_indication` | No valid indication documented |
| `viral_illness` | Viral illness, antibiotics not indicated |
| `asymptomatic_bacteriuria` | ASB, treatment not indicated |

**Agent Review Decisions (optional):**
| Decision | Meaning |
|----------|---------|
| `agent_appropriate` | Good choice for this syndrome |
| `agent_acceptable` | Not first-line but reasonable |
| `agent_inappropriate` | Wrong antibiotic for syndrome |
| `agent_skip` | Not reviewed |

### Phase 5: Training Data Collection ✓ IMPLEMENTED

**File:** `abx-indications/training_collector.py`

Collects JSONL training data for model fine-tuning:
- Input: Clinical notes + antibiotic context
- Output: Extracted syndrome, confidence, red flags
- Human review: Confirmed/corrected syndrome + agent decision

Export for fine-tuning:
```bash
python -c "from training_collector import get_abx_training_collector; \
           get_abx_training_collector().export_training_data('training.jsonl')"
```

## Comparison: Legacy vs. JC-Compliant Workflow

### Legacy (ICD-10 Based)
```
ICD-10 Codes → Chua Classification → A/S/N/P/FN/U
                                        ↓
                              Human confirms/overrides
```
**Problems:**
- ICD-10 codes are billing constructs
- May not be available at time of order
- Don't reflect real-time clinical reasoning

### JC-Compliant (Syndrome Based)
```
Clinical Notes → LLM Extraction → Clinical Syndrome → Guideline Match
       ↓                              ↓                    ↓
  (Real-time)                 (CAP, UTI, sepsis)    (CCHMC pathways)
                                      ↓
                    Human reviews syndrome + agent appropriateness
                                      ↓
                           Training data for fine-tuning
```
**Benefits:**
- Extracts actual clinical reasoning from notes
- Maps to specific CCHMC guidelines
- Collects training data for model improvement
- JC-compliant documentation

## LLM Model

**Current:** `qwen2.5:7b` (fast, ~119 tok/s)
- Good JSON output for structured extraction
- Sufficient for syndrome identification
- Much faster than 70B models

**Upgrade path:** Fine-tune on collected training data after ~500 reviewed cases.

## Database Schema

New fields in `indication_candidates`:
- `clinical_syndrome` - Canonical ID (e.g., "cap")
- `clinical_syndrome_display` - Human readable
- `syndrome_category` - High-level category
- `syndrome_confidence` - definite/probable/unclear
- `therapy_intent` - empiric/directed/prophylaxis
- `guideline_disease_ids` - JSON array of CCHMC IDs
- Red flags: `likely_viral`, `asymptomatic_bacteriuria`, `indication_not_documented`, `never_appropriate`

New fields in `indication_reviews`:
- `syndrome_decision` - Syndrome review decision
- `confirmed_syndrome` - Confirmed/corrected syndrome ID
- `confirmed_syndrome_display` - Human readable
- `agent_decision` - Agent appropriateness decision
- `agent_notes` - Notes about agent choice

## References

- Joint Commission MM.09.01.01 EP 13-15 (2024 revision)
- CDC Core Elements of Hospital Antibiotic Stewardship
- IDSA/SHEA Guidelines for Antimicrobial Stewardship
- Chua KP, et al. BMJ 2019 (for ICD-10 fallback classification)

---

*Last updated: January 2026*
