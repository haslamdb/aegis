"""Data models for antibiotic approval requests."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class ApprovalDecision(Enum):
    """Possible decisions for an antibiotic approval request."""
    APPROVED = "approved"
    CHANGED_THERAPY = "changed_therapy"
    DENIED = "denied"
    DEFERRED = "deferred"  # Needs more info, will call back

    @classmethod
    def display_name(cls, decision: "ApprovalDecision | str") -> str:
        """Get human-readable display name for a decision."""
        display_names = {
            cls.APPROVED: "Approved",
            cls.CHANGED_THERAPY: "Changed Therapy",
            cls.DENIED: "Denied",
            cls.DEFERRED: "Deferred",
        }
        if isinstance(decision, str):
            try:
                decision = cls(decision)
            except ValueError:
                return decision.replace("_", " ").title()
        return display_names.get(decision, decision.value)

    @classmethod
    def all_options(cls) -> list[tuple[str, str]]:
        """Get all options as (value, display_name) tuples for dropdowns."""
        return [(d.value, cls.display_name(d)) for d in cls]


class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    COMPLETED = "completed"


class AuditAction(Enum):
    """Actions tracked in approval audit log."""
    CREATED = "created"
    DECISION_MADE = "decision_made"
    NOTE_ADDED = "note_added"
    UPDATED = "updated"


@dataclass
class ApprovalRequest:
    """An antibiotic approval request with lifecycle tracking."""
    id: str

    # Patient info (captured at time of request)
    patient_id: str
    patient_mrn: str
    patient_name: str | None = None
    patient_location: str | None = None

    # Request details
    antibiotic_name: str = ""
    antibiotic_dose: str | None = None
    antibiotic_route: str | None = None
    indication: str | None = None
    duration_requested_hours: int | None = None
    prescriber_name: str | None = None
    prescriber_pager: str | None = None

    # Clinical context (JSON blob for cultures, current meds snapshot)
    clinical_context: dict = field(default_factory=dict)

    # Decision
    decision: str | None = None
    decision_by: str | None = None
    decision_at: datetime | None = None
    decision_notes: str | None = None
    alternative_recommended: str | None = None

    # Workflow
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str | None = None

    def is_pending(self) -> bool:
        """Check if request is still pending a decision."""
        return self.status == ApprovalStatus.PENDING.value

    def is_completed(self) -> bool:
        """Check if request has been decided."""
        return self.status == ApprovalStatus.COMPLETED.value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_mrn": self.patient_mrn,
            "patient_name": self.patient_name,
            "patient_location": self.patient_location,
            "antibiotic_name": self.antibiotic_name,
            "antibiotic_dose": self.antibiotic_dose,
            "antibiotic_route": self.antibiotic_route,
            "indication": self.indication,
            "duration_requested_hours": self.duration_requested_hours,
            "prescriber_name": self.prescriber_name,
            "prescriber_pager": self.prescriber_pager,
            "clinical_context": self.clinical_context,
            "decision": self.decision,
            "decision_display": ApprovalDecision.display_name(self.decision) if self.decision else None,
            "decision_by": self.decision_by,
            "decision_at": self.decision_at.isoformat() if self.decision_at else None,
            "decision_notes": self.decision_notes,
            "alternative_recommended": self.alternative_recommended,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "ApprovalRequest":
        """Create from database row tuple."""
        # Row order matches schema
        clinical_context_json = row[12]
        clinical_context = json.loads(clinical_context_json) if clinical_context_json else {}

        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=row[0],
            patient_id=row[1],
            patient_mrn=row[2],
            patient_name=row[3],
            patient_location=row[4],
            antibiotic_name=row[5] or "",
            antibiotic_dose=row[6],
            antibiotic_route=row[7],
            indication=row[8],
            duration_requested_hours=row[9],
            prescriber_name=row[10],
            prescriber_pager=row[11],
            clinical_context=clinical_context,
            decision=row[13],
            decision_by=row[14],
            decision_at=parse_datetime(row[15]),
            decision_notes=row[16],
            alternative_recommended=row[17],
            status=row[18],
            created_at=parse_datetime(row[19]),
            created_by=row[20],
        )


@dataclass
class ApprovalAuditEntry:
    """Audit log entry for approval request actions."""
    id: int
    approval_id: str
    action: AuditAction
    performed_by: str | None
    performed_at: datetime
    details: str | None = None

    @classmethod
    def from_row(cls, row: tuple) -> "ApprovalAuditEntry":
        """Create from database row tuple."""
        performed_at = row[4]
        if isinstance(performed_at, str):
            performed_at = datetime.fromisoformat(performed_at)

        return cls(
            id=row[0],
            approval_id=row[1],
            action=AuditAction(row[2]),
            performed_by=row[3],
            performed_at=performed_at,
            details=row[5],
        )
