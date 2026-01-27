# Pediatric Antibiotic Indication Classifier for AEGIS

## Overview

This module provides automated classification of antibiotic indication appropriateness for the AEGIS (Automated Evaluation and Guidance for Infection Surveillance) antimicrobial stewardship platform. It enables real-time assessment of whether antibiotic orders have documented indications, supporting Joint Commission MM.09.01.01 compliance.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AEGIS ANTIBIOTIC APPROPRIATENESS                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  LAYER 1        │    │  LAYER 2        │    │  LAYER 3        │         │
│  │  Indication     │ +  │  Agent          │ +  │  Duration       │         │
│  │  Appropriate?   │    │  Appropriate?   │    │  Appropriate?   │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│  ┌────────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐         │
│  │ Chua ICD-10     │    │ CCHMC Pocket    │    │ PIDS/IDSA       │         │
│  │ Classification  │    │ Docs (Bugs &    │    │ Guidelines      │         │
│  │ (This Module)   │    │ Drugs)          │    │ (Future)        │         │
│  │                 │    │                 │    │                 │         │
│  │ ✓ IMPLEMENTED   │    │ ✓ IMPLEMENTED   │    │ □ PLANNED       │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Three-Layer Appropriateness Model

| Layer | Question | Data Source | Status |
|-------|----------|-------------|--------|
| **Layer 1** | Is there ANY indication for antibiotics? | Chua ICD-10 classification | ✅ Implemented |
| **Layer 2** | Is THIS antibiotic appropriate for the indication? | CCHMC Pocket Docs | ✅ Implemented |
| **Layer 3** | Is the DURATION appropriate? | PIDS/IDSA guidelines | 🔲 Phase 3 |

---

## Current Functionality (Layer 1)

### Files

| File | Description |
|------|-------------|
| `pediatric_abx_indications.py` | Main Python module with `AntibioticIndicationClassifier` class |
| `pediatric_icd10_abx_classification.csv` | Modified Chua classification (94,249 ICD-10 codes) |
| `pediatric_abx_reference.json` | Surgical/medical prophylaxis tables, febrile neutropenia logic |
| `aegis_integration_example.py` | Example AEGIS dashboard integration |
| `cchmc_guidelines.py` | CCHMC Guidelines Engine for agent appropriateness (Layer 2) |
| `data/cchmc_disease_guidelines.json` | ~100 disease entities with first-line/alternative agents |
| `data/cchmc_antimicrobial_dosing.json` | ~50 drugs with age-stratified dosing recommendations |

### Classification Categories

| Category | Code | Meaning | Dashboard Color |
|----------|------|---------|-----------------|
| Always | `A` | Antibiotic indicated - documented bacterial infection | 🟢 Green |
| Sometimes | `S` | May need antibiotics - clinical judgment required | 🟡 Yellow |
| Never | `N` | No antibiotic indication - likely inappropriate | 🔴 Red |
| Prophylaxis | `P` | Surgical or medical prophylaxis indication | 🔵 Blue |
| Febrile Neutropenia | `FN` | Neutropenia + fever - empiric therapy indicated | 🟢 Green |

### Quick Start

```python
from pediatric_abx_indications import AntibioticIndicationClassifier

# Initialize with Chua CSV
classifier = AntibioticIndicationClassifier('chuk046645_ww2.csv')

# Classify an encounter
result = classifier.classify(
    icd10_codes=['J18.9', 'R50.9'],  # Pneumonia + Fever
    cpt_codes=['47562'],              # Lap chole (optional)
    fever_present=True                # From vital signs
)

print(result.overall_category)      # IndicationCategory.ALWAYS
print(result.primary_indication)    # "Pneumonia, unspecified organism"
print(result.flags)                 # []
print(result.recommendations)       # []
```

### Special Logic

#### Febrile Neutropenia Detection
```python
# Automatically detected when:
# - ANY neutropenia code (D70.x) is present
# - AND fever code (R50.x) OR fever_present=True

result = classifier.classify(
    icd10_codes=['D70.9'],  # Neutropenia
    fever_present=True       # Temp >= 38.0°C
)
# Result: Category FN with recommendation for empiric protocol
```

#### Surgical Prophylaxis Validation
```python
# Automatically detected when CPT code matches surgical prophylaxis table

result = classifier.classify(
    icd10_codes=['K80.20'],   # Cholelithiasis (not an infection)
    cpt_codes=['47562']        # Laparoscopic cholecystectomy
)
# Result: Category P with prophylaxis recommendations
# - Agent: cefazolin
# - Max duration: 24 hours
# - Note: "Single dose often sufficient for low-risk"
```

#### Pediatric Inpatient Overrides
The base Chua classification is designed for outpatient use. We apply these modifications for inpatient pediatrics:

| Code | Original | Modified | Rationale |
|------|----------|----------|-----------|
| R78.81 (Bacteremia) | N | **A** | Inpatient bacteremia always requires treatment |
| J69.0 (Aspiration PNA) | N | **S** | Often requires empiric coverage |
| K65.x (Peritonitis) | S | **A** | Surgical emergency requiring antibiotics |

---

## Layer 2: Agent Appropriateness (CCHMC Pocket Docs)

### Overview

Layer 2 uses the CCHMC Guidelines Engine (`cchmc_guidelines.py`) to answer: "Given the diagnosis, is the SPECIFIC antibiotic ordered appropriate?"

### Data Sources

1. **Cincinnati Children's Pocket Docs** - Bugs & Drugs guidelines with ~100 disease entities
2. **CCHMC Antimicrobial Dosing Tables** - Age-stratified dosing for ~50 drugs

### CCHMCGuidelinesEngine Class

```python
from cchmc_guidelines import CCHMCGuidelinesEngine, AgentCategory

engine = CCHMCGuidelinesEngine()

# Check agent appropriateness
result = engine.check_agent_appropriateness(
    icd10_codes=['J18.9'],           # Pneumonia
    prescribed_agent='azithromycin',
    patient_age_months=84,           # 7 years old
    allergies=['penicillin']
)

print(result.disease_matched)           # "Community-Acquired Pneumonia"
print(result.current_agent_category)    # AgentCategory.ALTERNATIVE
print(result.first_line_agents)         # ["amoxicillin", "ampicillin"]
print(result.recommendation)            # "azithromycin is an acceptable alternative..."
```

### Agent Categories

| Category | Meaning | Alert Level |
|----------|---------|-------------|
| `FIRST_LINE` | Guideline-recommended first choice | None |
| `ALTERNATIVE` | Acceptable alternative (allergy, atypical coverage) | Informational |
| `OFF_GUIDELINE` | Not in CCHMC guidelines for this indication | Warning |
| `NOT_ASSESSED` | No matching disease in guidelines | None |

### Disease Coverage by Body System

| System | Diseases | Examples |
|--------|----------|----------|
| Febrile/SBI | 6 | Septic shock, Fever & Neutropenia, RMSF, Lyme |
| CNS | 2 | Bacterial meningitis, VP shunt infection |
| Eyes | 2 | Orbital cellulitis, Preseptal cellulitis |
| HENT | 5 | AOM, Sinusitis, Pharyngitis, Mastoiditis |
| RTI | 3 | CAP, Aspiration pneumonia, Pertussis |
| GI | 5 | Appendicitis, C. diff, Peritonitis |
| GU | 3 | UTI, Cystitis, Pyelonephritis |
| SST | 4 | Cellulitis, Necrotizing fasciitis, Lymphadenitis |
| Ortho | 2 | Osteomyelitis, Septic arthritis |
| Neonatal | 4 | Neonatal meningitis, NEC, Pneumonia, UTI |
| Bites | 3 | Cat, Dog, Human bites |

### Dosing Lookup

```python
# Get dosing recommendation
dosing = engine.get_dosing_recommendation(
    drug_name='amoxicillin',
    age_months=36,
    indication='pneumonia'
)

print(dosing.dose_mg_kg)          # 45
print(dosing.frequency)           # "Q12H"
print(dosing.max_single_dose_mg)  # 1000
print(dosing.notes)               # "High-dose for CAP"
```

### Integration with Indication Monitor

The CCHMC engine is integrated into the antimicrobial-usage-alerts module:

```python
# In indication_monitor.py
if final_classification in ("A", "S", "P", "FN"):
    agent_recommendation = self.cchmc_engine.check_agent_appropriateness(
        icd10_codes=icd10_codes,
        prescribed_agent=order.medication_name,
        patient_age_months=patient_age_months,
        allergies=patient_allergies
    )

    # Generate warning alert if off-guideline
    if agent_recommendation.current_agent_category == AgentCategory.OFF_GUIDELINE:
        self._create_agent_alert(candidate, agent_recommendation)
```

### Alert Logic

| Scenario | Alert Type |
|----------|------------|
| Classification = N (Never) | CRITICAL - No indication |
| Classification = A/S/P AND agent = OFF_GUIDELINE | WARNING - Off-guideline agent |
| Classification = A/S/P AND agent = ALTERNATIVE | Informational only |
| Classification = A/S/P AND agent = FIRST_LINE | No alert |

### Data Files

#### cchmc_disease_guidelines.json

```json
{
  "body_systems": {
    "rti": {
      "name": "Respiratory Tract Infections",
      "diseases": [
        {
          "disease_id": "cap",
          "name": "Community-Acquired Pneumonia",
          "icd10_codes": ["J13", "J14", "J18.9"],
          "icd10_patterns": ["J15", "J18"],
          "first_line": [
            {"agent": "amoxicillin", "dose_mg_kg": 45, "frequency": "Q12H"},
            {"agent": "ampicillin", "dose_mg_kg": 50, "frequency": "Q6H", "route": "IV"}
          ],
          "alternatives": [
            {"agent": "azithromycin", "indication": "atypical coverage >=5 years"}
          ],
          "age_modifications": [
            {"age_group": ">=5 years", "agents": ["azithromycin"], "notes": "Add for atypical"}
          ]
        }
      ]
    }
  }
}
```

#### cchmc_antimicrobial_dosing.json

```json
{
  "drugs": [
    {
      "drug_id": "amoxicillin",
      "generic_name": "Amoxicillin",
      "brand_names": ["Amoxil", "Trimox"],
      "drug_class": "Penicillin",
      "route": "PO",
      "dosing": [
        {
          "indication": "standard",
          "dose_mg_kg": 25,
          "frequency": "Q8H",
          "max_single_dose_mg": 500,
          "max_daily_dose_mg": 1500
        },
        {
          "indication": "pneumonia",
          "dose_mg_kg": 45,
          "frequency": "Q12H",
          "max_single_dose_mg": 1000,
          "notes": "High-dose for CAP"
        }
      ]
    }
  ]
}
```

---

## Phase 3: Duration Appropriateness

### Goal
Answer: "Is the antibiotic being continued longer than guidelines recommend?"

### Implementation Approach

```python
# Track antibiotic duration and compare to guidelines
DURATION_GUIDELINES = {
    'pneumonia_uncomplicated': {
        'recommended_days': 5,
        'max_days': 7,
        'alert_at_days': 6,
        'exceptions': ['empyema', 'necrotizing', 'immunocompromised']
    },
    'uti_cystitis': {
        'recommended_days': 3,
        'max_days': 5,
        'alert_at_days': 4
    },
    'surgical_prophylaxis': {
        'recommended_hours': 24,
        'max_hours': 48,  # Cardiac surgery exception
        'alert_at_hours': 25
    }
}
```

---

## Surgical Prophylaxis Validation

### Current Coverage (55+ procedures)

The module includes detailed surgical prophylaxis recommendations organized by specialty:

| Specialty | Procedures | Key Agents |
|-----------|------------|------------|
| Cardiac | VSD repair, valve replacement, CABG, transplant | Cefazolin, Vancomycin |
| Thoracic | Lobectomy, pneumonectomy | Cefazolin, Amp-sulbactam |
| Hepatobiliary | Cholecystectomy, liver transplant | Cefazolin, Pip-tazo |
| Colorectal | Colectomy, appendectomy | Cefazolin + Metronidazole |
| GU | Pyeloplasty, nephrectomy, transplant | Cefazolin |
| Orthopedic | Arthroplasty, spinal fusion, ORIF | Cefazolin |
| Neurosurgery | Craniotomy, VP shunt, laminectomy | Cefazolin, Vancomycin |
| Vascular | Endarterectomy, bypass | Cefazolin |
| Neonatal | G-tube, hernia repair, TEF repair | Cefazolin |

### Validation Logic

```python
def validate_surgical_prophylaxis(
    cpt_code: str,
    antibiotic_ordered: str,
    hours_since_incision: float,
    mrsa_risk: bool = False
) -> Dict:
    """
    Validate surgical prophylaxis appropriateness.
    
    Returns:
        {
            'prophylaxis_indicated': True/False,
            'agent_appropriate': True/False,
            'duration_appropriate': True/False,
            'recommendations': [...]
        }
    """
    
    info = SURGICAL_PROPHYLAXIS_CPT.get(cpt_code)
    
    if not info:
        return {'error': 'CPT code not in prophylaxis table'}
    
    if not info.prophylaxis_indicated:
        return {
            'prophylaxis_indicated': False,
            'recommendation': f'Prophylaxis not routinely indicated for {info.procedure_name}'
        }
    
    # Check agent
    agent_ok = antibiotic_ordered.lower() in [a.lower() for a in info.recommended_agents]
    
    # Check duration
    duration_ok = hours_since_incision <= info.max_duration_hours
    
    return {
        'prophylaxis_indicated': True,
        'procedure': info.procedure_name,
        'agent_appropriate': agent_ok,
        'agent_ordered': antibiotic_ordered,
        'recommended_agents': info.recommended_agents,
        'duration_appropriate': duration_ok,
        'hours_elapsed': hours_since_incision,
        'max_hours': info.max_duration_hours,
        'flags': [] if (agent_ok and duration_ok) else ['REVIEW_PROPHYLAXIS'],
        'special_considerations': info.special_considerations
    }
```

### Dashboard Integration

```
┌────────────────────────────────────────────────────────────────────────┐
│ SURGICAL PROPHYLAXIS MONITOR                                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│ Patient: Smith, John (MRN: 123456)                                     │
│ Procedure: Laparoscopic cholecystectomy (CPT 47562)                    │
│ OR Start: 2025-01-24 08:00                                             │
│                                                                        │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ Antibiotic: Cefazolin 1g IV                                      │   │
│ │ Given: 07:45 (15 min before incision) ✓                          │   │
│ │ Status: APPROPRIATE                                         🟢   │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│ Duration Monitor:                                                      │
│ ├─────────────────────────────────────────┤                           │
│ 0h              12h              24h      ← Max recommended            │
│ ▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                              │
│ Current: 6h elapsed                                                    │
│                                                                        │
│ ⚠ ALERT AT: 24h - Recommend discontinuation                           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Integration with Epic FHIR

### Required FHIR Resources

```python
FHIR_RESOURCES_NEEDED = {
    'Condition': 'ICD-10 diagnosis codes',
    'Procedure': 'CPT codes for surgical prophylaxis',
    'MedicationRequest': 'Antibiotic orders',
    'MedicationAdministration': 'Actual doses given (for duration tracking)',
    'Observation': 'Vital signs (temperature for fever detection)',
    'Patient': 'Demographics, allergies'
}
```

### Example FHIR Query Flow

```python
async def assess_patient_antibiotics(patient_id: str, encounter_id: str):
    """
    Full antibiotic appropriateness assessment from FHIR data.
    """
    
    # 1. Get active diagnoses
    conditions = await fhir_client.search('Condition', {
        'patient': patient_id,
        'encounter': encounter_id,
        'clinical-status': 'active'
    })
    icd10_codes = [c.code.coding[0].code for c in conditions]
    
    # 2. Get procedures (for surgical prophylaxis)
    procedures = await fhir_client.search('Procedure', {
        'patient': patient_id,
        'encounter': encounter_id
    })
    cpt_codes = [p.code.coding[0].code for p in procedures]
    
    # 3. Get vital signs (for fever detection)
    vitals = await fhir_client.search('Observation', {
        'patient': patient_id,
        'code': '8310-5',  # Body temperature LOINC
        '_sort': '-date',
        '_count': 1
    })
    temp = vitals[0].valueQuantity.value if vitals else None
    fever_present = temp and temp >= 38.0
    
    # 4. Get active antibiotic orders
    med_requests = await fhir_client.search('MedicationRequest', {
        'patient': patient_id,
        'encounter': encounter_id,
        'status': 'active',
        'category': 'antibiotic'  # May need local mapping
    })
    
    # 5. Classify each antibiotic order
    results = []
    for order in med_requests:
        result = classifier.classify(
            icd10_codes=icd10_codes,
            cpt_codes=cpt_codes,
            fever_present=fever_present
        )
        results.append({
            'medication': order.medicationCodeableConcept.text,
            'classification': result.to_dict()
        })
    
    return results
```

---

## Testing

### Unit Tests

```bash
# Run test cases
python pediatric_abx_indications.py chuk046645_ww2.csv
```

### Expected Test Output

```
======================================================================
TEST CASES
======================================================================

--- Bacterial pneumonia ---
ICD-10: ['J18.9'], CPT: [], Fever: False
Result: A - Antibiotic indicated - documented infection
Primary: Pneumonia, unspecified organism

--- Viral URI ---
ICD-10: ['J06.9'], CPT: [], Fever: False
Result: N - No documented indication for antibiotics
Primary: Acute upper respiratory infection, unspecified
Flags: NO_DOCUMENTED_INDICATION

--- Febrile neutropenia ---
ICD-10: ['D70.9', 'R50.9'], CPT: [], Fever: True
Result: FN - Febrile neutropenia - antibiotic indicated
Primary: Febrile neutropenia
Flags: FEBRILE_NEUTROPENIA
```

---

## Roadmap

### Phase 1 (Complete ✅)
- [x] Chua ICD-10 classification import
- [x] Pediatric inpatient modifications
- [x] Febrile neutropenia logic
- [x] Surgical prophylaxis table (55+ CPT codes)
- [x] Medical prophylaxis identification
- [x] Antifungal indication flagging
- [x] Basic AEGIS integration example

### Phase 2 (Complete ✅)
- [x] Parse CCHMC Pocket Docs → structured format
- [x] Create cchmc_disease_guidelines.json (~100 diseases)
- [x] Create cchmc_antimicrobial_dosing.json (~50 drugs)
- [x] Build CCHMCGuidelinesEngine class
- [x] Agent appropriateness scoring (FIRST_LINE/ALTERNATIVE/OFF_GUIDELINE)
- [x] Age-stratified recommendations
- [x] Allergy-aware alternatives
- [x] Integration with indication_monitor.py

### Phase 3 (Next)
- [ ] Duration tracking from MAR data
- [ ] Auto-stop recommendations
- [ ] De-escalation prompts
- [ ] IV-to-PO conversion alerts

### Phase 4 (Future)
- [ ] Local antibiogram integration
- [ ] Culture-directed therapy recommendations
- [ ] Machine learning for prediction

---

## References

1. **Chua KP, Fischer MA, Linder JA.** Appropriateness of outpatient antibiotic prescribing among privately insured US patients: ICD-10-CM based cross sectional study. BMJ. 2019;364:k5092.

2. **CCHMC Pocket Docs.** Bugs & Drugs - Antimicrobial Guidelines. Cincinnati Children's Hospital Medical Center. 2024.

3. **CCHMC Antimicrobial Dosing Tables.** Pediatric Antimicrobial Dosing Reference. Cincinnati Children's Hospital Medical Center. 2024.

4. **Stanford Children's Health.** Guidelines for Initial Therapy for Common Pediatric Infections. Updated October 2025.

5. **ASHP/IDSA/SHEA/SIS.** Clinical Practice Guidelines for Antimicrobial Prophylaxis in Surgery. 2013.

6. **Bradley JS, et al.** The Management of Community-Acquired Pneumonia in Infants and Children Older Than 3 Months of Age: Clinical Practice Guidelines by PIDS and IDSA. Clin Infect Dis. 2011.

7. **The Joint Commission.** MM.09.01.01 - Antimicrobial Stewardship Standard. Effective January 1, 2023.

---

## Contact

AEGIS Development Team  
Cincinnati Children's Hospital Medical Center  
Division of Infectious Diseases

---

## License

Internal use only - Cincinnati Children's Hospital Medical Center
