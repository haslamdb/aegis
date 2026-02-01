# Outbreak Detection Module Documentation

## Purpose

The Outbreak Detection module identifies and tracks clusters of related infections to enable early outbreak recognition and response. It aggregates data from multiple surveillance sources (MDRO, HAI, CDI) and applies clustering algorithms to detect potential outbreaks requiring IP investigation.

## Clinical Background

### What is an Outbreak?

An outbreak is the occurrence of more cases of a disease than expected in a given area or among a specific group of people over a particular period. In healthcare settings, outbreaks often involve:

- Transmission of pathogens between patients
- Common-source exposures (contaminated equipment, environment)
- Lapses in infection control practices

### Why Automated Detection?

Manual outbreak detection relies on IP staff noticing patterns across disparate data sources. Automated detection:

- Reduces time to recognition
- Catches subtle patterns across units
- Provides consistent, objective criteria
- Enables earlier intervention

## Detection Algorithm

### Clustering Criteria

Cases are grouped into clusters when they share:

1. **Infection Type**: Same pathogen category (e.g., MRSA, CLABSI, CDI)
2. **Location**: Same unit or nursing station
3. **Time Window**: Within configurable period (default: 14 days)

### Cluster Formation

```
Day 1: MRSA case in ICU-A
Day 3: MRSA case in ICU-A  → Cluster formed (2 cases)
Day 7: MRSA case in ICU-A  → Cluster grows (3 cases)
Day 10: MRSA case in ICU-B → Separate case (different unit)
```

### Severity Calculation

| Cases | Severity | Alert Priority |
|-------|----------|----------------|
| 2-3 | Low | Standard review |
| 4-5 | Medium | Expedited review |
| 6-9 | High | Urgent investigation |
| 10+ | Critical | Immediate response |

Severity can also escalate based on:
- Mortality associated with cases
- Spread to additional units
- Involvement of high-risk organisms (CRE, CRAB)

## Technical Architecture

### Data Source Pattern

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ MDRO Source │     │ HAI Source  │     │ CDI Source  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   Detector    │
                   └───────┬───────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   Database    │
                   └───────┬───────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   Dashboard   │
                   └───────────────┘
```

### Data Source Interface

All sources implement the `DataSource` abstract class:

```python
class DataSource(ABC):
    name: str  # Source identifier (mdro, hai, cdi)

    @abstractmethod
    def get_recent_cases(self, days: int = 14) -> list[dict]:
        """Return cases with standardized fields."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if source database is accessible."""
        pass
```

### Standardized Case Format

```python
{
    "source": "mdro",           # Which module provided the case
    "source_id": "uuid",        # Original case ID
    "patient_id": "uuid",       # Patient identifier
    "patient_mrn": "12345",     # Medical record number
    "event_date": datetime,     # Culture/diagnosis date
    "organism": "MRSA",         # Pathogen (if applicable)
    "infection_type": "mrsa",   # Normalized type for clustering
    "unit": "ICU-A",            # Location
    "location": "Main Hospital" # Facility
}
```

### Database Schema

```sql
CREATE TABLE outbreak_clusters (
    id TEXT PRIMARY KEY,
    infection_type TEXT NOT NULL,
    organism TEXT,
    unit TEXT NOT NULL,
    status TEXT DEFAULT 'active',  -- active, investigating, resolved
    severity TEXT DEFAULT 'low',   -- low, medium, high, critical
    case_count INTEGER DEFAULT 0,
    first_case_date TIMESTAMP,
    last_case_date TIMESTAMP,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status_changed_at TIMESTAMP,
    resolved_by TEXT,
    resolved_at TIMESTAMP,
    notes TEXT
);

CREATE TABLE cluster_cases (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL REFERENCES outbreak_clusters(id),
    source TEXT NOT NULL,      -- mdro, hai, cdi
    source_id TEXT NOT NULL,   -- Original case ID
    patient_id TEXT NOT NULL,
    patient_mrn TEXT NOT NULL,
    event_date TIMESTAMP NOT NULL,
    organism TEXT,
    infection_type TEXT NOT NULL,
    unit TEXT NOT NULL,
    location TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, source, source_id)
);

CREATE TABLE outbreak_alerts (
    id TEXT PRIMARY KEY,
    cluster_id TEXT REFERENCES outbreak_clusters(id),
    alert_type TEXT NOT NULL,  -- new_cluster, cluster_growth, severity_escalation
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMP
);
```

## Dashboard Features

### Main Dashboard (`/outbreak-detection/`)

Displays:
- Active cluster count with severity breakdown
- Pending alerts requiring acknowledgment
- Quick actions (view all clusters, alerts, MDRO surveillance link)
- Active clusters table with key details

### Clusters List (`/outbreak-detection/clusters`)

Filterable by status:
- **Active**: Newly detected, needs attention
- **Investigating**: Under active IP review
- **Resolved**: Investigation complete

### Cluster Detail (`/outbreak-detection/clusters/<id>`)

Comprehensive view including:
- Cluster summary (type, unit, severity, case count)
- Timeline of cases
- Individual case details with source links
- Resolution form for closing investigation

### Alerts (`/outbreak-detection/alerts`)

Two sections:
- **Pending**: Alerts awaiting acknowledgment
- **Acknowledged**: Historical alerts with reviewer info

## Alert Types

### New Cluster Alert
Generated when a new cluster is first detected (2+ cases meeting criteria).

```
Title: "New MRSA cluster detected in ICU-A"
Message: "2 cases identified within 7 days. First case: 2024-01-10."
Severity: Based on case count
```

### Cluster Growth Alert
Generated when new cases are added to existing cluster.

```
Title: "MRSA cluster in ICU-A has grown"
Message: "Cluster now has 5 cases (was 3). Latest case: 2024-01-17."
Severity: Updated based on new count
```

### Severity Escalation Alert
Generated when cluster crosses severity threshold.

```
Title: "MRSA cluster in ICU-A escalated to HIGH severity"
Message: "Cluster now has 6 cases, requiring urgent investigation."
Severity: high
```

## Cluster Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                       ACTIVE                                 │
│  - New cluster detected                                      │
│  - Awaiting IP review                                        │
│  - May receive new cases                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │ IP starts investigation
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    INVESTIGATING                             │
│  - IP actively reviewing                                     │
│  - Root cause analysis                                       │
│  - Intervention implementation                               │
└─────────────────────────┬───────────────────────────────────┘
                          │ Investigation complete
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      RESOLVED                                │
│  - Investigation documented                                  │
│  - Resolution notes captured                                 │
│  - Historical reference                                      │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

```bash
# Outbreak detection database
OUTBREAK_DB_PATH=/path/to/outbreak.db

# Source databases
MDRO_DB_PATH=/path/to/mdro.db
HAI_DB_PATH=/path/to/hai.db
```

### Detection Parameters

In `outbreak_src/config.py`:

```python
# Time window for clustering (days)
CLUSTER_TIME_WINDOW_DAYS = 14

# Minimum cases to form a cluster
MIN_CLUSTER_SIZE = 2

# Severity thresholds
SEVERITY_THRESHOLDS = {
    "low": 2,
    "medium": 4,
    "high": 6,
    "critical": 10
}
```

## Integration with Other Modules

### MDRO Surveillance
- Primary source for MDRO cases
- Reads from MDRO database via `MDROSource` adapter
- Links back to MDRO case detail pages

### HAI Detection
- Source for device-associated infections (CLABSI, CAUTI, VAE)
- Reads from HAI database via `HAISource` adapter
- Enables cross-module cluster detection

### CDI Surveillance
- Source for C. difficile cases
- Critical for CDI outbreak detection
- Often involves different transmission patterns

## Operational Workflow

### Daily Operations

1. **Check Dashboard**: IP reviews pending alerts and active clusters
2. **Acknowledge Alerts**: Document awareness of new/growing clusters
3. **Investigate Clusters**: Review case details, assess transmission risk
4. **Update Status**: Move to "investigating" when active review begins
5. **Resolve Clusters**: Document findings and close when complete

### Investigation Process

1. **Case Review**: Examine each case in cluster
2. **Timeline Analysis**: Map case dates and locations
3. **Contact Tracing**: Identify potential transmission links
4. **Environmental Review**: Assess common exposures
5. **Intervention**: Implement control measures
6. **Documentation**: Record findings in resolution notes

## Performance Considerations

### Detection Frequency
- Run detection after new case data is available
- Typically daily or after each MDRO/HAI processing cycle
- Can be triggered manually via dashboard

### Database Optimization
- Indexes on cluster status, infection type, unit
- Efficient queries for active cluster lookup
- Archive resolved clusters periodically

### Scalability
- Designed for single-facility deployment
- Can be extended for multi-facility with location hierarchy
- Consider separate databases for large health systems
