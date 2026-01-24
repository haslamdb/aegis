# HAI Detection Module

Healthcare-Associated Infection (HAI) candidate detection, LLM-assisted classification, and IP review workflow.

## Overview

The HAI Detection module identifies potential HAIs from clinical data and assists Infection Preventionists (IPs) in classifying them. Currently supported HAI types:

- **CLABSI** - Central Line-Associated Bloodstream Infections
- **CAUTI** - Catheter-Associated Urinary Tract Infections
- **SSI** - Surgical Site Infections (Superficial, Deep, Organ/Space)
- **VAE** - Ventilator-Associated Events (VAC, IVAC, Possible/Probable VAP)

## Architecture

The system uses a four-stage workflow:

```
1. Rule-based Screening → 2. LLM Fact Extraction → 3. Rules Engine → 4. IP Review
```

1. **Rule-based screening** - Identifies candidates (BSI + line for CLABSI; catheter + positive urine for CAUTI; procedure + infection signals for SSI; ventilator worsening for VAE)
2. **LLM fact extraction** - Extracts clinical facts from notes (symptoms, alternate sources, wound assessments)
3. **Rules engine** - Applies deterministic NHSN criteria to extracted facts
4. **IP Review** - ALL candidates go to IP for final decision

**Key principle**: The LLM extracts facts and provides a preliminary classification, but the Infection Preventionist always makes the final determination.

## Installation

```bash
cd hai-detection
pip install -r requirements.txt
```

## Usage

### Run HAI Detection

```bash
# Single detection cycle
cd /home/david/projects/aegis/hai-detection
python -m src.runner --once

# Full pipeline: detection + classification
python -m src.runner --full

# Dry run (no database writes)
python -m src.runner --full --dry-run

# Continuous monitoring mode
python -m src.runner
```

### View Statistics

```bash
python -m src.runner --stats
python -m src.runner --recent
```

## Project Structure

```
hai-detection/
├── src/
│   ├── __init__.py
│   ├── config.py         # Configuration
│   ├── db.py             # Database operations
│   ├── models.py         # Domain models
│   ├── monitor.py        # Main orchestrator
│   ├── runner.py         # CLI entry point
│   ├── candidates/       # Rule-based candidate detection
│   │   ├── base.py
│   │   ├── clabsi.py
│   │   ├── cauti.py
│   │   ├── ssi.py
│   │   └── vae.py
│   ├── classifiers/      # LLM-assisted classification
│   │   ├── base.py
│   │   ├── clabsi_classifier.py
│   │   ├── clabsi_classifier_v2.py
│   │   ├── cauti_classifier.py
│   │   ├── ssi_classifier.py
│   │   └── vae_classifier.py
│   ├── extraction/       # LLM fact extraction
│   │   ├── clabsi_extractor.py
│   │   ├── cauti_extractor.py
│   │   ├── ssi_extractor.py
│   │   └── vae_extractor.py
│   ├── rules/            # NHSN criteria rules engines
│   │   ├── schemas.py
│   │   ├── nhsn_criteria.py
│   │   ├── clabsi_engine.py
│   │   ├── cauti_schemas.py
│   │   ├── cauti_engine.py
│   │   ├── ssi_schemas.py
│   │   ├── ssi_engine.py
│   │   ├── vae_schemas.py
│   │   └── vae_engine.py
│   ├── notes/            # Clinical note retrieval
│   │   ├── retriever.py
│   │   └── chunker.py
│   ├── llm/              # LLM backends
│   │   ├── factory.py
│   │   └── ollama.py
│   ├── review/           # IP review workflow
│   │   └── queue.py
│   ├── alerters/         # Notification channels
│   │   └── teams.py
│   └── data/             # Data sources
│       ├── factory.py
│       ├── fhir_source.py
│       └── clarity_source.py
├── prompts/              # LLM prompt templates
│   ├── clabsi_extraction_v1.txt
│   ├── cauti_extraction_v1.txt
│   ├── ssi_extraction_v1.txt
│   └── vae_extraction_v1.txt
├── tests/
│   ├── test_candidates.py
│   ├── test_clabsi_rules.py
│   ├── test_cauti_rules.py
│   ├── test_ssi_rules.py
│   └── test_vae_rules.py
├── schema.sql            # Database schema
├── requirements.txt
└── README.md
```

## Configuration

Configuration is read from environment variables or a `.env` file. Key settings:

```bash
# Data Sources
FHIR_BASE_URL=http://localhost:8081/fhir
CLARITY_CONNECTION_STRING=

# LLM Backend
LLM_BACKEND=ollama  # or 'claude'
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:70b

# Classification Thresholds
AUTO_CLASSIFY_THRESHOLD=0.85
IP_REVIEW_THRESHOLD=0.60

# CLABSI Criteria
MIN_DEVICE_DAYS=2
POST_REMOVAL_WINDOW_DAYS=1

# Database
HAI_DB_PATH=~/.aegis/nhsn.db

# Notifications
TEAMS_WEBHOOK_URL=
HAI_NOTIFICATION_EMAIL=
```

## Database

The module uses a SQLite database shared with the NHSN Reporting module. HAI detection tables:

- `hai_candidates` - Detected HAI candidates
- `hai_classifications` - LLM classification results
- `hai_reviews` - IP review decisions
- `hai_llm_audit` - LLM call audit log
- `ssi_procedures` - Tracked surgical procedures
- `ssi_candidate_details` - SSI-specific candidate data
- `cauti_catheter_episodes` - Tracked urinary catheter episodes
- `cauti_candidate_details` - CAUTI-specific candidate data (symptoms, CFU/mL)
- `vae_ventilation_episodes` - Tracked ventilator episodes
- `vae_daily_parameters` - FiO2/PEEP time series data
- `vae_candidate_details` - VAE-specific candidate data (VAC/IVAC/VAP details)

## Integration with Dashboard

Access the HAI Detection dashboard at: `/hai-detection/`

The dashboard provides:
- Active cases awaiting IP review
- Case history (confirmed/rejected)
- Reports and analytics
- LLM override statistics

## CAUTI (Catheter-Associated Urinary Tract Infections)

The CAUTI module implements NHSN CAUTI surveillance criteria for detecting urinary tract infections associated with indwelling urinary catheters.

### CAUTI Classification Hierarchy

| Classification | Description |
|----------------|-------------|
| **CAUTI** | Catheter >2 days + positive culture + qualifying symptoms |
| **Asymptomatic Bacteriuria** | Positive culture but no symptoms (not reported as HAI) |
| **Not Eligible** | Does not meet catheter/culture criteria |

### CAUTI Detection Algorithm

1. **Catheter Eligibility**: Indwelling urinary catheter in place >2 calendar days on date of event
2. **Culture Criteria**: Positive urine culture with:
   - ≥10⁵ CFU/mL
   - ≤2 organisms (no mixed flora)
   - Not Candida-only (yeast excluded)
3. **Symptom Requirement**: At least one of:
   - Fever >38.0°C
   - Suprapubic tenderness
   - CVA (costovertebral angle) pain/tenderness
   - Urinary urgency
   - Urinary frequency
   - Dysuria

### Age-Based Fever Rule

- **Patient ≤65 years**: Fever alone can qualify as the symptom criterion
- **Patient >65 years**: Fever alone requires catheter >2 days; other symptoms always valid

This rule helps distinguish CAUTI from other causes of fever in elderly patients with short catheter durations.

### Excluded Organisms

- Candida species
- Yeast (any)
- Fungal organisms

These organisms are excluded from CAUTI surveillance per NHSN criteria.

## VAE (Ventilator-Associated Events)

The VAE module implements the NHSN VAE surveillance protocol with a tiered classification hierarchy.

### VAE Hierarchy (most specific first)

| Classification | Tier | Criteria |
|----------------|------|----------|
| **Probable VAP** | 3 | IVAC + purulent secretions + positive quantitative culture |
| **Possible VAP** | 3 | IVAC + purulent secretions OR positive respiratory culture |
| **IVAC** | 2 | VAC + fever/WBC abnormality + new antimicrobial ≥4 days |
| **VAC** | 1 | ≥2 days stable ventilator settings followed by ≥2 days sustained worsening |

### VAC Detection Algorithm

The candidate detector identifies VAC by analyzing ventilator parameter trends:

1. **Baseline Period**: ≥2 days of stable or improving FiO2/PEEP
2. **Worsening Period**: ≥2 days of sustained increase in:
   - FiO2 ≥20 percentage points above baseline minimum, OR
   - PEEP ≥3 cmH2O above baseline minimum

### IVAC Criteria

IVAC requires VAC criteria PLUS:
- Temperature >38°C or <36°C
- WBC ≥12,000 or ≤4,000 cells/mm³
- New qualifying antimicrobial started within ±2 days of VAC onset, continued ≥4 calendar days

### VAP Criteria

- **Possible VAP**: IVAC + purulent secretions (≥25 PMNs, ≤10 epithelial cells/LPF) OR positive respiratory culture
- **Probable VAP**: IVAC + purulent secretions + quantitative culture meeting threshold:
  - BAL: ≥10⁴ CFU/mL
  - ETA: ≥10⁶ CFU/mL
  - PSB: ≥10³ CFU/mL

## Related Modules

- **nhsn-reporting** - NHSN submission, AU/AR data extraction
- **common** - Shared utilities (alert store, channels)
- **dashboard** - Web interface

## Testing

```bash
cd hai-detection
pytest tests/
```
