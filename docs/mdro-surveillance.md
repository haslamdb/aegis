# MDRO Surveillance Module Documentation

## Purpose

The MDRO Surveillance module provides automated detection and tracking of Multi-Drug Resistant Organisms from microbiology culture results. It serves as the foundation for Infection Prevention surveillance workflows and feeds data to the Outbreak Detection module for cluster analysis.

## Clinical Background

### What are MDROs?

Multi-Drug Resistant Organisms are bacteria that have developed resistance to multiple antibiotics, making them difficult to treat and posing significant infection control challenges. Key MDROs tracked by this module include:

- **MRSA** (Methicillin-resistant Staphylococcus aureus): Common cause of skin/soft tissue and bloodstream infections
- **VRE** (Vancomycin-resistant Enterococcus): Associated with urinary tract and bloodstream infections
- **CRE** (Carbapenem-resistant Enterobacteriaceae): High-mortality gram-negative infections
- **ESBL** (Extended-spectrum Beta-lactamase producers): Resistant to most cephalosporins
- **CRPA** (Carbapenem-resistant Pseudomonas aeruginosa): Difficult-to-treat respiratory infections
- **CRAB** (Carbapenem-resistant Acinetobacter baumannii): ICU-associated infections

### Transmission Classification

Understanding where the organism was acquired is critical for IP interventions:

| Classification | Definition | IP Implications |
|---------------|------------|-----------------|
| Community Onset | Culture ≤48h after admission | Patient arrived with MDRO; focus on screening/isolation |
| Healthcare Onset | Culture >48h after admission | Possible hospital acquisition; investigate transmission |

## Technical Architecture

### Data Flow

```
FHIR Server (DiagnosticReport + Observation)
           │
           ▼
    ┌──────────────┐
    │ FHIR Client  │  Queries microbiology cultures
    └──────────────┘
           │
           ▼
    ┌──────────────┐
    │  Classifier  │  Applies MDRO criteria to susceptibilities
    └──────────────┘
           │
           ▼
    ┌──────────────┐
    │   Monitor    │  Calculates transmission status, saves cases
    └──────────────┘
           │
           ▼
    ┌──────────────┐
    │   Database   │  SQLite storage for cases and reviews
    └──────────────┘
           │
           ▼
    ┌──────────────┐
    │  Dashboard   │  Flask routes for IP interface
    └──────────────┘
```

### Classification Algorithm

The classifier examines susceptibility results (S/I/R) to determine MDRO type. Definitions are aligned with CDC/NHSN standards for consistency between real-time surveillance and quarterly NHSN AR reporting.

```python
# Example: MRSA detection
if organism == "Staphylococcus aureus":
    mrsa_agents = ["Oxacillin", "Methicillin", "Nafcillin", "Cefoxitin"]
    if any(susceptibilities.get(abx) == "R" for abx in mrsa_agents):
        return MDROType.MRSA

# Example: CRE detection (takes precedence over ESBL)
if organism in ENTEROBACTERALES:
    carbapenems = ["Meropenem", "Imipenem", "Ertapenem", "Doripenem"]
    if any(susceptibilities.get(abx) == "R" for abx in carbapenems):
        return MDROType.CRE

# Example: ESBL detection
if organism in ["E. coli", "Klebsiella", "Proteus mirabilis"]:
    esbl_agents = ["Ceftriaxone", "Ceftazidime", "Cefotaxime", "Aztreonam"]
    if any(susceptibilities.get(abx) == "R" for abx in esbl_agents):
        return MDROType.ESBL
```

**Important:** CRE classification takes precedence over ESBL. If an organism is resistant to carbapenems, it is classified as CRE rather than ESBL.

### Database Schema

```sql
CREATE TABLE mdro_cases (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    patient_mrn TEXT NOT NULL,
    patient_name TEXT,
    culture_id TEXT NOT NULL UNIQUE,
    culture_date TIMESTAMP NOT NULL,
    organism TEXT NOT NULL,
    mdro_type TEXT NOT NULL,  -- mrsa, vre, cre, esbl, crpa, crab
    specimen_type TEXT,
    unit TEXT,
    location TEXT,
    admission_date TIMESTAMP,
    days_since_admission INTEGER,
    transmission_status TEXT,  -- pending, community, healthcare
    resistant_antibiotics TEXT,  -- JSON array
    classification_reason TEXT,
    is_new BOOLEAN DEFAULT 1,
    prior_history BOOLEAN DEFAULT 0,
    reviewed_by TEXT,
    reviewed_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Dashboard Features

### Main Dashboard (`/mdro-surveillance/`)

Displays:
- Summary statistics (total cases, healthcare vs community onset)
- Cases by MDRO type (visual breakdown)
- Recent cases (last 7 days)
- Cases by unit (identifies high-burden areas)

### Cases List (`/mdro-surveillance/cases`)

Filterable list with:
- MDRO type filter
- Unit filter
- Time period selection (7/30/90/365 days)
- Sortable columns

### Case Detail (`/mdro-surveillance/cases/<id>`)

Comprehensive view including:
- Patient demographics
- Culture and organism details
- Resistance profile
- Transmission classification
- Prior MDRO history for patient
- IP review form

### Analytics (`/mdro-surveillance/analytics`)

Trend analysis with:
- Cases over time by MDRO type
- Onset distribution (healthcare vs community)
- Unit-level comparisons

## Integration Points

### Outbreak Detection Module

The MDRO module exports case data via:

1. **Direct Database Access**: The `MDROSource` adapter in outbreak-detection reads from the MDRO database directly.

2. **REST API**: `/mdro-surveillance/api/export` returns cases formatted for outbreak analysis:

```json
[
  {
    "source": "mdro",
    "source_id": "case-uuid",
    "patient_id": "patient-uuid",
    "patient_mrn": "12345",
    "event_date": "2024-01-15T10:30:00",
    "organism": "Staphylococcus aureus",
    "infection_type": "mrsa",
    "unit": "ICU-A",
    "location": "Main Hospital"
  }
]
```

### FHIR Data Requirements

The module expects:

**DiagnosticReport** (microbiology culture):
- `status`: final
- `category`: microbiology
- `code`: culture type
- `subject`: patient reference
- `effectiveDateTime`: collection time
- `result`: references to Observations

**Observation** (organism + susceptibilities):
- `code`: organism identification or antibiotic tested
- `valueCodeableConcept` or `valueString`: organism name or S/I/R result
- `interpretation`: susceptibility interpretation

## Configuration

### Environment Variables

```bash
# Database path
MDRO_DB_PATH=/path/to/mdro.db

# FHIR server
FHIR_BASE_URL=https://fhir.example.com/r4

# Optional: Authentication
FHIR_AUTH_TOKEN=Bearer xxx
```

### Classification Tuning

Edit `mdro_src/classifier.py` to adjust:
- Organism name matching patterns
- Antibiotic equivalence mappings
- MDRO classification criteria

## Operational Considerations

### Performance

- Processing runs incrementally using `mdro_processing_log` to track handled cultures
- Batch queries to FHIR server to minimize API calls
- SQLite with appropriate indexes for dashboard queries

### Error Handling

- Failed FHIR queries logged but don't halt processing
- Missing susceptibility data results in case without classification
- Duplicate cultures (same culture_id) are skipped

### Monitoring

Check `mdro_processing_log` for:
- Processing errors
- Cultures without susceptibility data
- Classification failures

## IP Workflow

1. **Daily Review**: IP checks dashboard for new cases
2. **Case Triage**: Review transmission status and unit location
3. **Investigation**: For healthcare-onset cases, check for potential transmission
4. **Documentation**: Use review form to document decision and actions
5. **Outbreak Alert**: System feeds data to Outbreak Detection for cluster analysis
