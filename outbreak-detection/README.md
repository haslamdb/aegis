# Outbreak Detection Module

Cluster detection and investigation tools for Infection Prevention teams. This module identifies potential outbreaks by analyzing patterns across MDRO, HAI, and CDI cases.

## Overview

The Outbreak Detection module:
- Detects clusters of related infections by unit, organism, and time
- Aggregates cases from multiple data sources (MDRO, HAI, CDI)
- Generates alerts for IP review and action
- Tracks cluster investigation and resolution

## How Cluster Detection Works

The detector identifies clusters when:
1. Multiple cases share the same **infection type** (e.g., MRSA, CLABSI, CDI)
2. Cases occur in the same **unit/location**
3. Cases fall within a configurable **time window** (default: 14 days)
4. Case count exceeds a **threshold** (default: 2+ cases)

### Severity Levels

| Level | Criteria |
|-------|----------|
| Low | 2-3 cases in cluster |
| Medium | 4-5 cases in cluster |
| High | 6-9 cases in cluster |
| Critical | 10+ cases in cluster |

## Data Sources

The module pulls cases from multiple sources through a pluggable adapter pattern:

### MDROSource
Pulls MDRO cases (MRSA, VRE, CRE, ESBL, CRPA, CRAB) from the MDRO Surveillance module.

### HAISource
Pulls healthcare-associated infections (CLABSI, CAUTI, SSI, VAE) from the HAI Detection module.

### CDISource
Pulls C. difficile infection cases from CDI surveillance data.

## Architecture

```
outbreak-detection/
├── outbreak_src/
│   ├── __init__.py
│   ├── config.py         # Configuration settings
│   ├── models.py         # OutbreakCluster, ClusterCase, enums
│   ├── sources.py        # Data source adapters
│   ├── db.py             # SQLite database operations
│   └── detector.py       # Cluster detection algorithm
├── schema.sql            # Database schema
└── README.md
```

## Database Schema

### outbreak_clusters
Stores detected outbreak clusters with status and severity.

### cluster_cases
Links individual cases to clusters with source tracking.

### outbreak_alerts
Stores alerts generated for IP review.

## Dashboard Routes

| Route | Description |
|-------|-------------|
| `/outbreak-detection/` | Dashboard with active clusters and alerts |
| `/outbreak-detection/clusters` | List clusters by status |
| `/outbreak-detection/clusters/<id>` | Cluster detail with cases |
| `/outbreak-detection/alerts` | Pending and acknowledged alerts |

## API Endpoints

### GET /outbreak-detection/api/stats
Returns summary statistics.

```json
{
  "active_clusters": 3,
  "investigating_clusters": 2,
  "resolved_clusters": 15,
  "pending_alerts": 5,
  "by_type": {"mrsa": 2, "clabsi": 1},
  "by_severity": {"critical": 1, "high": 1, "medium": 1}
}
```

### GET /outbreak-detection/api/active-clusters
Returns list of active clusters as JSON.

### POST /outbreak-detection/run
Manually triggers cluster detection.

Form parameters:
- `days` (default: 14): Detection window in days

## Cluster Lifecycle

```
┌─────────┐     ┌──────────────┐     ┌──────────┐
│ ACTIVE  │ ──► │ INVESTIGATING│ ──► │ RESOLVED │
└─────────┘     └──────────────┘     └──────────┘
```

1. **Active**: New cluster detected, requires IP attention
2. **Investigating**: IP team is actively investigating
3. **Resolved**: Investigation complete, cluster closed

## Alert Types

- **New Cluster**: First detection of a potential outbreak
- **Cluster Growth**: Existing cluster gained new cases
- **Severity Escalation**: Cluster severity increased

## Configuration

Environment variables:
- `OUTBREAK_DB_PATH`: Path to SQLite database
- `MDRO_DB_PATH`: Path to MDRO module database
- `HAI_DB_PATH`: Path to HAI module database

Detection parameters (in config.py):
- `CLUSTER_TIME_WINDOW_DAYS`: Days to consider for clustering (default: 14)
- `MIN_CLUSTER_SIZE`: Minimum cases to form cluster (default: 2)

## Usage

### Running Detection Manually

```python
from outbreak_src.db import OutbreakDatabase
from outbreak_src.detector import OutbreakDetector
from outbreak_src.config import config

db = OutbreakDatabase(config.DB_PATH)
detector = OutbreakDetector(db)
result = detector.run_detection(days=14)
```

### Adding a Custom Data Source

```python
from outbreak_src.sources import DataSource

class CustomSource(DataSource):
    name = "custom"

    def get_recent_cases(self, days: int = 14) -> list[dict]:
        # Return cases with required fields:
        # patient_id, patient_mrn, event_date, organism,
        # infection_type, unit, location
        pass

    def is_available(self) -> bool:
        return True
```

## Related Modules

- **MDRO Surveillance**: Primary source for MDRO cases
- **HAI Detection**: Source for device-associated infections
- **ASP Alerts**: May reference outbreak context for antibiotic decisions
