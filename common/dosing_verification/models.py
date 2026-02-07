"""Data models for dosing verification module."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class DoseFlagType(str, Enum):
    """Category of dosing issue detected."""
    SUBTHERAPEUTIC_DOSE = "subtherapeutic_dose"
    SUPRATHERAPEUTIC_DOSE = "supratherapeutic_dose"
    WRONG_INTERVAL = "wrong_interval"
    WRONG_ROUTE = "wrong_route"
    NO_RENAL_ADJUSTMENT = "no_renal_adjustment"
    EXCESSIVE_RENAL_ADJUSTMENT = "excessive_renal_adj"
    WEIGHT_DOSE_MISMATCH = "weight_dose_mismatch"
    AGE_DOSE_MISMATCH = "age_dose_mismatch"
    MAX_DOSE_EXCEEDED = "max_dose_exceeded"
    DRUG_INTERACTION = "drug_interaction"
    ALLERGY_CONTRAINDICATED = "allergy_contraindicated"
    ALLERGY_CROSS_REACTIVITY = "allergy_cross_reactivity"
    DURATION_EXCESSIVE = "duration_excessive"
    DURATION_INSUFFICIENT = "duration_insufficient"
    CONTRAINDICATED = "contraindicated"
    EXTENDED_INFUSION_CANDIDATE = "extended_infusion"

    @classmethod
    def display_name(cls, value):
        """Get human-readable display name for a flag type."""
        display_map = {
            cls.SUBTHERAPEUTIC_DOSE: "Subtherapeutic Dose",
            cls.SUPRATHERAPEUTIC_DOSE: "Supratherapeutic Dose",
            cls.WRONG_INTERVAL: "Wrong Interval",
            cls.WRONG_ROUTE: "Wrong Route",
            cls.NO_RENAL_ADJUSTMENT: "No Renal Adjustment",
            cls.EXCESSIVE_RENAL_ADJUSTMENT: "Excessive Renal Adjustment",
            cls.WEIGHT_DOSE_MISMATCH: "Weight Dose Mismatch",
            cls.AGE_DOSE_MISMATCH: "Age Dose Mismatch",
            cls.MAX_DOSE_EXCEEDED: "Max Dose Exceeded",
            cls.DRUG_INTERACTION: "Drug Interaction",
            cls.ALLERGY_CONTRAINDICATED: "Allergy Contraindicated",
            cls.ALLERGY_CROSS_REACTIVITY: "Allergy Cross-Reactivity",
            cls.DURATION_EXCESSIVE: "Duration Excessive",
            cls.DURATION_INSUFFICIENT: "Duration Insufficient",
            cls.CONTRAINDICATED: "Contraindicated",
            cls.EXTENDED_INFUSION_CANDIDATE: "Extended Infusion Candidate",
        }
        # Handle both enum values and string values
        if isinstance(value, cls):
            return display_map.get(value, value.value.replace("_", " ").title())
        return display_map.get(cls(value) if value else None, value.replace("_", " ").title() if value else "")

    @classmethod
    def all_options(cls):
        """Get all options as (value, display_name) tuples for dropdowns."""
        return [(f.value, cls.display_name(f)) for f in cls]


class DoseAlertSeverity(str, Enum):
    """Alert severity determines notification channel."""
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"

    @classmethod
    def all_options(cls):
        """Get all options as (value, display_name) tuples for dropdowns."""
        return [
            (cls.CRITICAL.value, "Critical"),
            (cls.HIGH.value, "High"),
            (cls.MODERATE.value, "Moderate"),
            (cls.LOW.value, "Low"),
        ]


class DoseAlertStatus(str, Enum):
    """Alert lifecycle status."""
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class DoseResolution(str, Enum):
    """How the alert was resolved."""
    DOSE_ADJUSTED = "dose_adjusted"
    INTERVAL_ADJUSTED = "interval_adjusted"
    ROUTE_CHANGED = "route_changed"
    THERAPY_CHANGED = "therapy_changed"
    THERAPY_STOPPED = "therapy_stopped"
    DISCUSSED_WITH_TEAM = "discussed_with_team"
    CLINICAL_JUSTIFICATION = "clinical_justification"
    MESSAGED_TEAM = "messaged_team"
    ESCALATED_TO_ATTENDING = "escalated_to_attending"
    NO_ACTION_NEEDED = "no_action_needed"
    AUTO_ACCEPTED = "auto_accepted"
    OTHER = "other"

    @classmethod
    def display_name(cls, value):
        """Get human-readable display name for a resolution."""
        return {
            cls.DOSE_ADJUSTED: "Dose Adjusted",
            cls.INTERVAL_ADJUSTED: "Interval Adjusted",
            cls.ROUTE_CHANGED: "Route Changed",
            cls.THERAPY_CHANGED: "Therapy Changed",
            cls.THERAPY_STOPPED: "Therapy Stopped",
            cls.DISCUSSED_WITH_TEAM: "Discussed with Team",
            cls.CLINICAL_JUSTIFICATION: "Clinical Justification",
            cls.MESSAGED_TEAM: "Messaged Team",
            cls.ESCALATED_TO_ATTENDING: "Escalated to Attending",
            cls.NO_ACTION_NEEDED: "No Action Needed",
            cls.AUTO_ACCEPTED: "Auto-Accepted",
            cls.OTHER: "Other",
        }.get(value, value)

    @classmethod
    def all_options(cls):
        """Get all options as (value, display_name) tuples for dropdowns."""
        return [(r.value, cls.display_name(r)) for r in cls if r != cls.AUTO_ACCEPTED]


@dataclass
class DoseFlag:
    """A single dosing issue found by the rules engine."""
    flag_type: DoseFlagType
    severity: DoseAlertSeverity
    drug: str
    message: str
    expected: str
    actual: str
    rule_source: str
    indication: str
    details: dict | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "flag_type": self.flag_type.value if isinstance(self.flag_type, DoseFlagType) else self.flag_type,
            "severity": self.severity.value if isinstance(self.severity, DoseAlertSeverity) else self.severity,
            "drug": self.drug,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "rule_source": self.rule_source,
            "indication": self.indication,
            "details": self.details or {},
        }


@dataclass
class DoseAssessment:
    """Complete assessment of a patient's antimicrobial dosing."""
    assessment_id: str
    patient_id: str
    patient_mrn: str
    patient_name: str
    encounter_id: str | None

    # Patient factors used in evaluation
    age_years: float | None
    weight_kg: float | None
    height_cm: float | None
    scr: float | None
    gfr: float | None
    is_on_dialysis: bool
    gestational_age_weeks: int | None

    # What was evaluated
    medications_evaluated: list[dict]
    indication: str | None
    indication_confidence: float | None
    indication_source: str | None

    # Results
    flags: list[DoseFlag]
    max_severity: DoseAlertSeverity | None
    assessed_at: str
    assessed_by: str

    # Co-medications (for DDI checking)
    co_medications: list[dict]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "assessment_id": self.assessment_id,
            "patient_id": self.patient_id,
            "patient_mrn": self.patient_mrn,
            "patient_name": self.patient_name,
            "encounter_id": self.encounter_id,
            "age_years": self.age_years,
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
            "scr": self.scr,
            "gfr": self.gfr,
            "is_on_dialysis": self.is_on_dialysis,
            "gestational_age_weeks": self.gestational_age_weeks,
            "medications_evaluated": self.medications_evaluated,
            "indication": self.indication,
            "indication_confidence": self.indication_confidence,
            "indication_source": self.indication_source,
            "flags": [f.to_dict() for f in self.flags],
            "max_severity": self.max_severity.value if self.max_severity else None,
            "assessed_at": self.assessed_at,
            "assessed_by": self.assessed_by,
            "co_medications": self.co_medications,
        }

    def to_alert_content(self) -> dict:
        """Convert to content dict suitable for AlertStore."""
        return {
            "assessment": self.to_dict(),
            "patient_factors": {
                "age_years": self.age_years,
                "weight_kg": self.weight_kg,
                "scr": self.scr,
                "gfr": self.gfr,
                "is_on_dialysis": self.is_on_dialysis,
            },
            "medications": self.medications_evaluated,
            "flags": [f.to_dict() for f in self.flags],
        }


@dataclass
class DoseAlertRecord:
    """Persisted dose alert in the store."""
    id: str
    assessment_id: str
    patient_id: str
    patient_mrn: str
    patient_name: str
    encounter_id: str | None

    # Alert content
    drug: str
    indication: str | None
    flag_type: str
    severity: str
    message: str
    expected_dose: str
    actual_dose: str
    rule_source: str

    # Clinical context (JSON)
    patient_factors: str
    assessment_details: str

    # Status tracking
    status: str
    created_at: str
    sent_at: str | None
    acknowledged_at: str | None
    acknowledged_by: str | None
    resolved_at: str | None
    resolved_by: str | None
    resolution: str | None
    resolution_notes: str | None
    notes: str | None

    @classmethod
    def from_row(cls, row) -> "DoseAlertRecord":
        """Create from database row."""
        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val.isoformat()
            return val

        return cls(
            id=row[0],
            assessment_id=row[1],
            patient_id=row[2],
            patient_mrn=row[3],
            patient_name=row[4],
            encounter_id=row[5],
            drug=row[6],
            indication=row[7],
            flag_type=row[8],
            severity=row[9],
            message=row[10],
            expected_dose=row[11],
            actual_dose=row[12],
            rule_source=row[13],
            patient_factors=row[14],
            assessment_details=row[15],
            status=row[16],
            created_at=parse_datetime(row[17]),
            sent_at=parse_datetime(row[18]),
            acknowledged_at=parse_datetime(row[19]),
            acknowledged_by=row[20],
            resolved_at=parse_datetime(row[21]),
            resolved_by=row[22],
            resolution=row[23],
            resolution_notes=row[24],
            notes=row[25],
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "assessment_id": self.assessment_id,
            "patient_id": self.patient_id,
            "patient_mrn": self.patient_mrn,
            "patient_name": self.patient_name,
            "encounter_id": self.encounter_id,
            "drug": self.drug,
            "indication": self.indication,
            "flag_type": self.flag_type,
            "severity": self.severity,
            "message": self.message,
            "expected_dose": self.expected_dose,
            "actual_dose": self.actual_dose,
            "rule_source": self.rule_source,
            "patient_factors": json.loads(self.patient_factors) if self.patient_factors else {},
            "assessment_details": json.loads(self.assessment_details) if self.assessment_details else {},
            "status": self.status,
            "created_at": self.created_at,
            "sent_at": self.sent_at,
            "acknowledged_at": self.acknowledged_at,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "resolution": self.resolution,
            "resolution_display": DoseResolution.display_name(self.resolution) if self.resolution else None,
            "resolution_notes": self.resolution_notes,
            "notes": self.notes,
        }
