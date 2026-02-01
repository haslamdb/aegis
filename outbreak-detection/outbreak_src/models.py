"""Data models for Outbreak Detection."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ClusterStatus(Enum):
    """Status of an outbreak cluster."""
    ACTIVE = "active"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


class ClusterSeverity(Enum):
    """Severity level of an outbreak cluster."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ClusterCase:
    """A case that is part of an outbreak cluster."""
    id: str  # Unique ID for cluster membership
    cluster_id: str
    source: str  # mdro, hai, cdi, etc.
    source_id: str  # ID in the source system
    patient_id: str
    patient_mrn: str
    event_date: datetime
    organism: Optional[str]
    infection_type: str  # MDRO type, HAI type, etc.
    unit: str
    location: Optional[str]
    added_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cluster_id": self.cluster_id,
            "source": self.source,
            "source_id": self.source_id,
            "patient_id": self.patient_id,
            "patient_mrn": self.patient_mrn,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "organism": self.organism,
            "infection_type": self.infection_type,
            "unit": self.unit,
            "location": self.location,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


@dataclass
class OutbreakCluster:
    """A potential outbreak cluster of related infection cases."""
    id: str
    infection_type: str  # MDRO type, HAI type, etc.
    organism: Optional[str]
    unit: str
    location: Optional[str]

    # Cluster members
    cases: list[ClusterCase] = field(default_factory=list)
    case_count: int = 0

    # Time window
    first_case_date: Optional[datetime] = None
    last_case_date: Optional[datetime] = None
    window_days: int = 14

    # Status
    status: ClusterStatus = ClusterStatus.ACTIVE
    severity: ClusterSeverity = ClusterSeverity.LOW
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None

    # Alert tracking
    alerted: bool = False
    alerted_at: Optional[datetime] = None

    def add_case(self, case: ClusterCase) -> bool:
        """Add a case to this cluster.

        Returns True if case was added, False if already present.
        """
        if any(c.source_id == case.source_id and c.source == case.source for c in self.cases):
            return False

        case.cluster_id = self.id
        self.cases.append(case)
        self.case_count = len(self.cases)

        if self.first_case_date is None or case.event_date < self.first_case_date:
            self.first_case_date = case.event_date
        if self.last_case_date is None or case.event_date > self.last_case_date:
            self.last_case_date = case.event_date

        self._update_severity()
        return True

    def _update_severity(self):
        """Update severity based on case count."""
        if self.case_count >= 5:
            self.severity = ClusterSeverity.CRITICAL
        elif self.case_count >= 4:
            self.severity = ClusterSeverity.HIGH
        elif self.case_count >= 3:
            self.severity = ClusterSeverity.MEDIUM
        else:
            self.severity = ClusterSeverity.LOW

    def resolve(self, resolved_by: str, notes: str | None = None):
        """Mark cluster as resolved."""
        self.status = ClusterStatus.RESOLVED
        self.resolved_at = datetime.now()
        self.resolved_by = resolved_by
        self.resolution_notes = notes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "infection_type": self.infection_type,
            "organism": self.organism,
            "unit": self.unit,
            "location": self.location,
            "case_count": self.case_count,
            "first_case_date": self.first_case_date.isoformat() if self.first_case_date else None,
            "last_case_date": self.last_case_date.isoformat() if self.last_case_date else None,
            "window_days": self.window_days,
            "status": self.status.value,
            "severity": self.severity.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution_notes": self.resolution_notes,
            "alerted": self.alerted,
            "alerted_at": self.alerted_at.isoformat() if self.alerted_at else None,
        }
