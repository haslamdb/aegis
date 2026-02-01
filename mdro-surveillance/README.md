# MDRO Surveillance Module

Multi-Drug Resistant Organism (MDRO) surveillance for Infection Prevention teams. This module automatically detects and tracks MDRO cases from microbiology culture data with susceptibility results.

## Overview

The MDRO Surveillance module:
- Classifies organisms as MDRO based on antibiotic susceptibility patterns
- Tracks transmission status (healthcare-onset vs community-onset)
- Provides case management and IP review workflows
- Exports data to the Outbreak Detection module for cluster analysis

## Supported MDRO Types

Classification criteria are aligned with CDC/NHSN definitions for consistency between real-time surveillance and quarterly NHSN AR reporting.

| Type | Full Name | Classification Criteria |
|------|-----------|------------------------|
| MRSA | Methicillin-resistant Staphylococcus aureus | Oxacillin R, Methicillin R, Nafcillin R, or Cefoxitin R |
| VRE | Vancomycin-resistant Enterococcus | Vancomycin R in E. faecium/faecalis |
| CRE | Carbapenem-resistant Enterobacterales | Meropenem R, Imipenem R, Ertapenem R, or Doripenem R |
| ESBL | Extended-spectrum Beta-lactamase | Ceftriaxone R, Ceftazidime R, Cefotaxime R, or Aztreonam R (in E. coli, Klebsiella, or P. mirabilis) |
| CRPA | Carbapenem-resistant Pseudomonas aeruginosa | Meropenem R, Imipenem R, or Doripenem R |
| CRAB | Carbapenem-resistant Acinetobacter baumannii | Meropenem R, Imipenem R, or Doripenem R |

**Note:** CRE classification takes precedence over ESBL - organisms resistant to carbapenems are classified as CRE, not ESBL.

## Transmission Classification

Cases are classified based on time from admission to culture collection:

- **Community Onset**: Culture collected ≤48 hours after admission
- **Healthcare Onset**: Culture collected >48 hours after admission

## Architecture

```
mdro-surveillance/
├── mdro_src/
│   ├── __init__.py
│   ├── config.py         # Configuration settings
│   ├── models.py         # MDROCase, TransmissionStatus
│   ├── classifier.py     # MDRO classification logic
│   ├── fhir_client.py    # FHIR data retrieval
│   ├── db.py             # SQLite database operations
│   └── monitor.py        # Main monitoring loop
├── schema.sql            # Database schema
└── README.md
```

## Database Schema

### mdro_cases
Stores detected MDRO cases with patient, organism, and classification details.

### mdro_reviews
Stores IP reviews and decisions for each case.

### mdro_processing_log
Tracks processed cultures to avoid duplicates.

## Dashboard Routes

| Route | Description |
|-------|-------------|
| `/mdro-surveillance/` | Dashboard overview with stats |
| `/mdro-surveillance/cases` | List all cases with filtering |
| `/mdro-surveillance/cases/<id>` | Case detail and review form |
| `/mdro-surveillance/analytics` | Trend analysis and reporting |

## API Endpoints

### GET /mdro-surveillance/api/stats
Returns summary statistics for a time period.

```json
{
  "total_cases": 42,
  "healthcare_onset": 28,
  "community_onset": 14,
  "by_type": {"mrsa": 15, "vre": 12, "cre": 8, "esbl": 7},
  "by_unit": {"ICU": 18, "Med/Surg": 12, "ED": 8}
}
```

### GET /mdro-surveillance/api/export
Exports cases for the Outbreak Detection module.

Query parameters:
- `days` (default: 14): Number of days to include

## Configuration

Environment variables:
- `MDRO_DB_PATH`: Path to SQLite database
- `FHIR_BASE_URL`: FHIR server URL for microbiology data

## Integration with Outbreak Detection

The MDRO module provides case data to the Outbreak Detection module via:
1. Direct database access through `MDROSource` adapter
2. REST API at `/mdro-surveillance/api/export`

Cases exported include:
- Patient identifier and MRN
- MDRO type and organism
- Culture date and unit
- Transmission status

## Usage

### Running the Monitor

```bash
cd /home/david/projects/aegis/mdro-surveillance
python -m mdro_src.monitor
```

### Manual Classification

```python
from mdro_src.classifier import MDROClassifier, MDROType

classifier = MDROClassifier()
result = classifier.classify(organism="Staphylococcus aureus", susceptibilities=[
    {"antibiotic": "Oxacillin", "result": "R"},
    {"antibiotic": "Vancomycin", "result": "S"}
])
# result.mdro_type == MDROType.MRSA
```

## Related Modules

- **Outbreak Detection**: Uses MDRO cases for cluster detection
- **HAI Detection**: Separate module for healthcare-associated infections
- **Drug-Bug Mismatch**: Real-time therapy coverage alerts
