# Surgical Prophylaxis Module

Automated monitoring and validation of surgical antibiotic prophylaxis following ASHP/IDSA/SHEA/SIS guidelines.

## Overview

This module provides real-time validation of surgical prophylaxis orders to ensure:
- Appropriate antibiotic selection for the procedure
- Correct timing (within 60 minutes of incision)
- Appropriate duration (typically ≤24 hours post-op)
- Weight-based dosing compliance

## Features

### Procedure Coverage (55+ CPT codes)

| Specialty | Example Procedures | Primary Agent |
|-----------|-------------------|---------------|
| **Cardiac** | VSD repair, valve replacement, CABG | Cefazolin |
| **Thoracic** | Lobectomy, pneumonectomy | Cefazolin |
| **Hepatobiliary** | Cholecystectomy, liver transplant | Cefazolin, Pip-tazo |
| **Colorectal** | Colectomy, appendectomy | Cefazolin + Metronidazole |
| **GU** | Pyeloplasty, nephrectomy | Cefazolin |
| **Orthopedic** | Arthroplasty, spinal fusion, ORIF | Cefazolin |
| **Neurosurgery** | Craniotomy, VP shunt | Cefazolin, Vancomycin |
| **Vascular** | Endarterectomy, bypass | Cefazolin |

### Validation Checks

1. **Agent Selection**
   - Is the ordered antibiotic appropriate for this procedure?
   - Are there allergy considerations requiring alternatives?
   - Is MRSA coverage indicated (nasal screening, high-risk)?

2. **Timing Validation**
   - Was prophylaxis given within 60 minutes of incision?
   - Was re-dosing performed for long procedures?
   - Vancomycin/fluoroquinolones: within 120 minutes

3. **Duration Monitoring**
   - Alert at 24 hours post-op (most procedures)
   - Extended duration exceptions (cardiac surgery: 48h)
   - Track actual discontinuation time

4. **Dosing Compliance**
   - Weight-based dosing for cefazolin (≥120kg: 3g)
   - Appropriate pediatric dosing
   - Renal adjustment when indicated

## Dashboard Features

- **Active Cases**: Current OR cases with prophylaxis status
- **Duration Monitor**: Cases approaching/exceeding recommended duration
- **Compliance Metrics**: Weekly/monthly compliance rates
- **Agent Analysis**: Breakdown of agents used by procedure type

## Integration

### Data Sources
- OR schedule (procedure, surgeon, timing)
- Pharmacy orders (antibiotic, dose, timing)
- MAR (actual administration times)
- Microbiology (MRSA screening results)

### Alerts
- Pre-op: Missing prophylaxis order
- Intra-op: Re-dosing reminder for long cases
- Post-op: Duration exceeded alert

## References

1. ASHP/IDSA/SHEA/SIS. Clinical Practice Guidelines for Antimicrobial Prophylaxis in Surgery. 2013.
2. Bratzler DW, et al. Clinical practice guidelines for antimicrobial prophylaxis in surgery. Am J Health Syst Pharm. 2013.
