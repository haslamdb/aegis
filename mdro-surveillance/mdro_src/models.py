"""Data models for MDRO surveillance."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .classifier import MDROType


class TransmissionStatus(Enum):
    """Transmission classification status."""
    PENDING = "pending"              # Not yet evaluated
    COMMUNITY_ONSET = "community"    # Detected within 48h of admission
    HEALTHCARE_ONSET = "healthcare"  # Detected after 48h of admission


@dataclass
class MDROCase:
    """A tracked MDRO case from a culture result."""
    id: str
    patient_id: str
    patient_mrn: str
    patient_name: str

    # Culture info
    culture_id: str
    culture_date: datetime
    specimen_type: str
    organism: str

    # MDRO classification
    mdro_type: MDROType
    resistant_antibiotics: list[str]
    classification_reason: str

    # Location/timing
    location: str
    unit: str
    admission_date: Optional[datetime] = None
    days_since_admission: Optional[int] = None

    # Transmission tracking
    transmission_status: TransmissionStatus = TransmissionStatus.PENDING

    # Status
    is_new: bool = True  # First isolation for this patient
    prior_history: bool = False  # Patient has prior MDRO history
    created_at: datetime = field(default_factory=datetime.now)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    notes: Optional[str] = None

    def is_healthcare_onset(self) -> bool:
        """Check if this is healthcare-onset (>48h after admission)."""
        if self.days_since_admission is not None:
            return self.days_since_admission > 2
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_mrn": self.patient_mrn,
            "patient_name": self.patient_name,
            "culture_id": self.culture_id,
            "culture_date": self.culture_date.isoformat() if self.culture_date else None,
            "specimen_type": self.specimen_type,
            "organism": self.organism,
            "mdro_type": self.mdro_type.value,
            "resistant_antibiotics": self.resistant_antibiotics,
            "classification_reason": self.classification_reason,
            "location": self.location,
            "unit": self.unit,
            "admission_date": self.admission_date.isoformat() if self.admission_date else None,
            "days_since_admission": self.days_since_admission,
            "transmission_status": self.transmission_status.value,
            "is_new": self.is_new,
            "prior_history": self.prior_history,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "notes": self.notes,
        }
