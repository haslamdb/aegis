# Antimicrobial Usage Alerts

Monitors antimicrobial usage patterns including broad-spectrum duration and antibiotic indication documentation. Part of the [AEGIS](../README.md) system.

> **Disclaimer:** All patient data used for testing is **simulated**. **No actual patient data exists in this repository.**

## Overview

This module provides two complementary antimicrobial stewardship monitoring capabilities:

1. **Broad-Spectrum Duration Monitoring** - Tracks active medication orders for broad-spectrum antibiotics (meropenem, vancomycin, etc.) and generates alerts when usage duration exceeds a configurable threshold (default: 72 hours).

2. **Antibiotic Indication Monitoring** - Validates that antibiotic orders have documented indications using ICD-10 classification (Chua et al.) combined with LLM extraction from clinical notes. Only "Never appropriate" (N) classifications generate ASP alerts.

## Features

### Broad-Spectrum Duration Monitoring
- **Duration monitoring** - Tracks time since medication start date
- **Configurable thresholds** - Default 72 hours, adjustable per site
- **Severity escalation** - Warning at threshold, Critical at 2x threshold

### Antibiotic Indication Monitoring
- **Two-track classification** - ICD-10 codes first, then LLM extraction from clinical notes
- **Note priority** - Clinical notes override ICD-10 codes (codes may be stale or inaccurate)
- **N-only alerts** - Only "Never appropriate" classifications generate alerts
- **Override tracking** - Track when pharmacist disagrees with system classification

### Shared Infrastructure
- **Persistent deduplication** - SQLite-backed tracking prevents re-alerting
- **Multi-channel alerts** - Email and Teams with action buttons
- **Dashboard integration** - View, acknowledge, snooze, and resolve alerts

## Quick Start

```bash
# From the asp-alerts root directory
cd antimicrobial-usage-alerts

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.template .env
# Edit .env with your settings

# Run once (dry-run mode)
python -m src.runner --once --dry-run

# Run once (send alerts)
python -m src.runner --once

# Run continuous monitoring
python -m src.runner
```

## Configuration

Copy `.env.template` to `.env` and configure:

### FHIR Server

```bash
# Local development
FHIR_BASE_URL=http://localhost:8081/fhir

# Epic production
EPIC_FHIR_BASE_URL=https://epicfhir.yoursite.org/api/FHIR/R4
EPIC_CLIENT_ID=your-client-id
EPIC_PRIVATE_KEY_PATH=./keys/epic_private_key.pem
```

### Alert Channels

```bash
# Microsoft Teams (recommended)
TEAMS_WEBHOOK_URL=https://prod-XX.westus.logic.azure.com:443/workflows/...

# Email
SMTP_SERVER=smtp.yoursite.org
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
ALERT_EMAIL_FROM=asp-alerts@yoursite.org
ALERT_EMAIL_TO=asp-team@yoursite.org
```

### Monitoring Settings

```bash
# Alert threshold (hours)
ALERT_THRESHOLD_HOURS=72

# Add additional medications to monitor (RxNorm code:Name)
EXTRA_MONITORED_MEDICATIONS=4053:Piperacillin-tazobactam,5479:Linezolid

# Poll interval (seconds)
POLL_INTERVAL=300
```

### Dashboard Integration

```bash
# Dashboard URL for Teams action buttons
DASHBOARD_BASE_URL=https://aegis-asp.com

# API key for secure callbacks
DASHBOARD_API_KEY=your-secret-key

# Alert database path (shared with dashboard)
ALERT_DB_PATH=~/.aegis/alerts.db
```

### Indication Monitoring Settings

```bash
# Indication database path (separate from alerts)
INDICATION_DB_PATH=~/.aegis/indications.db

# Path to Chua et al. ICD-10 classification CSV
CHUA_CSV_PATH=/path/to/aegis/data/chuk046645.ww2.csv

# LLM settings for note extraction (Ollama)
LLM_MODEL=llama3.1:70b
LLM_BASE_URL=http://localhost:11434
```

## Monitored Medications

Default monitored medications (by RxNorm code):

| RxNorm Code | Medication |
|-------------|------------|
| 29561 | Meropenem |
| 11124 | Vancomycin |

Add more via `EXTRA_MONITORED_MEDICATIONS` environment variable.

## Alert Severity

| Severity | Condition | Actions |
|----------|-----------|---------|
| **Warning** | Duration >= threshold | Teams + Email |
| **Critical** | Duration >= 2x threshold | Teams + Email (urgent styling) |

## CLI Usage

### Broad-Spectrum Duration Monitoring (Default)

```bash
# Single check, dry run (no alerts sent)
python -m src.runner --once --dry-run

# Single check, send alerts
python -m src.runner --once

# Show all patients exceeding threshold (no dedup)
python -m src.runner --once --all

# Continuous monitoring (daemon mode)
python -m src.runner

# Verbose logging
python -m src.runner --once --verbose
```

### Antibiotic Indication Monitoring

```bash
# Run indication monitor only
python -m src.runner --indication --once

# Run indication monitor with dry-run (no alerts)
python -m src.runner --indication --once --dry-run

# Run indication monitor without LLM extraction (ICD-10 only)
python -m src.runner --indication --once --no-llm

# Run both monitors together
python -m src.runner --both --once

# Verbose output for indication monitoring
python -m src.runner --indication --once --verbose
```

### Cron Setup (Nightly Indication Batch)

```bash
# Add to crontab for nightly 4 AM runs
0 4 * * * cd /path/to/aegis/antimicrobial-usage-alerts && python -m src.runner --indication --once >> /var/log/aegis/indication-monitor.log 2>&1
```

## Architecture

```
antimicrobial-usage-alerts/
├── src/
│   ├── alerters/
│   │   ├── email_alerter.py        # Email notifications
│   │   └── teams_alerter.py        # Teams with action buttons
│   ├── config.py                   # Environment configuration
│   ├── fhir_client.py              # FHIR API client
│   ├── models.py                   # Data models
│   ├── monitor.py                  # BroadSpectrumMonitor class
│   ├── indication_monitor.py       # IndicationMonitor class
│   ├── indication_db.py            # SQLite for indication tracking
│   ├── llm_extractor.py            # LLM-based note extraction
│   └── runner.py                   # CLI entry point
├── prompts/
│   └── indication_extraction_v1.txt  # LLM prompt template
├── schema.sql                      # Indication database schema
├── tests/                          # Unit tests
├── .env.template                   # Configuration template
└── requirements.txt                # Python dependencies
```

## Indication Classification

The indication monitor uses a two-track classification approach:

### Track 1: ICD-10 Classification (Chua et al.)

Uses the pediatric antibiotic indication classification from Chua et al. to categorize ICD-10 diagnosis codes:

| Category | Description | Alert? |
|----------|-------------|--------|
| **A** (Always) | Indication always appropriate for antibiotics | No |
| **S** (Sometimes) | Indication sometimes appropriate | No |
| **N** (Never) | Indication never appropriate for antibiotics | **Yes** |
| **P** (Prophylaxis) | Appropriate for prophylaxis | No |
| **FN** (Febrile Neutropenia) | Empiric therapy appropriate | No |
| **U** (Unknown) | No matching ICD-10 codes found | Falls through to LLM |

### Track 2: LLM Note Extraction

When ICD-10 classification is N or U, the system extracts indications from clinical notes using a local LLM (Ollama):

- Searches for documented indications (e.g., "treating for pneumonia")
- Identifies supporting symptoms (fever, elevated WBC)
- Detects culture results and clinical reasoning
- **Notes take priority over ICD-10** - if the note says "viral infection" but ICD-10 says pneumonia, the note wins

### Classification Flow

```
MedicationRequest (antibiotic order)
         │
         ▼
Get Patient ICD-10 Conditions
         │
         ▼
Chua Classification (ICD-10)
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  A/S/P/FN    N/U
  (no alert)   │
               ▼
    LLM Note Extraction
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  Found       Still N
  indication   │
  (upgrade     ▼
   to A/S)  Create Alert
```

## Data Models

### UsageAssessment

```python
@dataclass
class UsageAssessment:
    patient: Patient
    medication: MedicationOrder
    duration_hours: float
    threshold_hours: float
    exceeds_threshold: bool
    recommendation: str
    severity: AlertSeverity
```

### Alert Lifecycle

1. **Monitor** detects medication exceeding threshold
2. **Alert created** in persistent store (status: PENDING)
3. **Alert sent** via configured channels (status: SENT)
4. **User action** via Teams button or dashboard:
   - Acknowledge (status: ACKNOWLEDGED)
   - Snooze 4h (status: SNOOZED, with expiration)
   - Resolve (status: RESOLVED, with reason/notes)

## Integration with Dashboard

Teams alerts include action buttons that link to the dashboard:

- **Acknowledge** - Mark as seen, stays in active list
- **Snooze 4h** - Temporarily suppress, auto-reactivates
- **View Details** - Open alert in dashboard

The dashboard provides:
- Active alert list with filters
- Resolution workflow with reasons and notes
- Historical view of resolved alerts
- Audit trail for compliance

## Testing

```bash
# Generate test data
cd ../scripts
python generate_pediatric_data.py --count 5

# Run with verbose output
cd ../antimicrobial-usage-alerts
python -m src.runner --once --verbose --dry-run
```

## Troubleshooting

### No alerts generated

1. Check FHIR server is accessible: `curl $FHIR_BASE_URL/metadata`
2. Verify monitored medications exist in FHIR
3. Check threshold setting in .env
4. Use `--verbose` flag for detailed logging

### Teams alerts not sending

1. Test webhook: `python -c "from common.channels.teams import test_webhook; test_webhook('YOUR_URL')"`
2. Verify webhook URL in .env
3. Check Teams channel permissions

### Duplicate alerts

- Alerts are deduplicated by medication order FHIR ID
- Clear alert store to reset: delete alerts.db or resolve all alerts
- Use `--all` flag to bypass deduplication (for testing)

### LLM not available (indication monitoring)

1. Check Ollama is running: `curl http://localhost:11434/api/tags`
2. Verify the model is installed: `ollama list`
3. Pull the model if missing: `ollama pull llama3.1:70b`
4. Check LLM settings in .env match your Ollama configuration
5. Use `--no-llm` flag to run with ICD-10 classification only

### Chua CSV not found

1. Verify path in CHUA_CSV_PATH environment variable
2. Default location: `aegis/data/chuk046645.ww2.csv`
3. Ensure the abx-indications module is properly installed

## Related Documentation

- [AEGIS Overview](../README.md)
- [Demo Workflow](../docs/demo-workflow.md) - Complete demo walkthrough
- [Bacteremia Alerts](../asp-bacteremia-alerts/README.md)
- [Antibiotic Indication Classification](../abx-indications/README.md) - Chua et al. methodology
- [Dashboard](../dashboard/README.md)
