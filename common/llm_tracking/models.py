"""Data models for LLM decision tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class LLMModule(Enum):
    """Modules that use LLM extraction."""
    ABX_INDICATIONS = "abx_indications"
    GUIDELINE_ADHERENCE = "guideline_adherence"
    HAI_DETECTION = "hai_detection"
    DRUG_BUG_MISMATCH = "drug_bug_mismatch"
    SURGICAL_PROPHYLAXIS = "surgical_prophylaxis"


class DecisionOutcome(Enum):
    """What the user did with the LLM recommendation."""
    ACCEPTED = "accepted"           # User accepted LLM recommendation as-is
    MODIFIED = "modified"           # User accepted but modified details
    OVERRIDDEN = "overridden"       # User rejected and chose differently
    PENDING = "pending"             # Not yet reviewed


class LLMOverrideReason(Enum):
    """Unified taxonomy for why a user overrides an LLM recommendation.

    These reasons apply across all modules that use LLM extraction.
    """
    # Clinical judgment reasons
    CLINICAL_CONTEXT = "clinical_context"              # Additional clinical context not in data
    PATIENT_SPECIFIC = "patient_specific"              # Patient-specific factors (allergies, comorbidities)
    CULTURE_DATA_PENDING = "culture_data_pending"      # Awaiting culture/sensitivity data
    RECENT_CLINICAL_CHANGE = "recent_clinical_change"  # Recent change in patient condition

    # Data quality reasons
    INCOMPLETE_DATA = "incomplete_data"                # LLM had incomplete/missing data
    INCORRECT_EXTRACTION = "incorrect_extraction"      # LLM extracted data incorrectly
    STALE_DATA = "stale_data"                          # Data was outdated at time of extraction
    WRONG_PATIENT_CONTEXT = "wrong_patient_context"    # Data from wrong encounter/patient

    # Policy/protocol reasons
    INSTITUTIONAL_PROTOCOL = "institutional_protocol"  # Following local protocol over guideline
    INFECTIOUS_DISEASE_CONSULT = "id_consult"          # Per ID consult recommendation
    PHARMACY_RECOMMENDATION = "pharmacy_recommendation" # Per pharmacy recommendation

    # Classification disagreement
    DISAGREE_WITH_CLASSIFICATION = "disagree_classification"  # Simply disagree with LLM classification
    BORDERLINE_CASE = "borderline_case"                # Case is borderline, could go either way

    # Other
    OTHER = "other"                                    # Other reason (see notes)

    @classmethod
    def display_name(cls, reason: "LLMOverrideReason | str") -> str:
        """Get human-readable display name."""
        display_names = {
            cls.CLINICAL_CONTEXT: "Additional Clinical Context",
            cls.PATIENT_SPECIFIC: "Patient-Specific Factors",
            cls.CULTURE_DATA_PENDING: "Culture Data Pending",
            cls.RECENT_CLINICAL_CHANGE: "Recent Clinical Change",
            cls.INCOMPLETE_DATA: "Incomplete Data",
            cls.INCORRECT_EXTRACTION: "Incorrect Extraction",
            cls.STALE_DATA: "Stale/Outdated Data",
            cls.WRONG_PATIENT_CONTEXT: "Wrong Patient Context",
            cls.INSTITUTIONAL_PROTOCOL: "Institutional Protocol",
            cls.INFECTIOUS_DISEASE_CONSULT: "Per ID Consult",
            cls.PHARMACY_RECOMMENDATION: "Per Pharmacy Recommendation",
            cls.DISAGREE_WITH_CLASSIFICATION: "Disagree with Classification",
            cls.BORDERLINE_CASE: "Borderline Case",
            cls.OTHER: "Other",
        }
        if isinstance(reason, str):
            try:
                reason = cls(reason)
            except ValueError:
                return reason
        return display_names.get(reason, reason.value)

    @classmethod
    def all_options(cls) -> list[tuple[str, str]]:
        """Get all options as (value, display_name) tuples for dropdowns."""
        return [(r.value, cls.display_name(r)) for r in cls]


@dataclass
class LLMDecisionRecord:
    """A single LLM extraction decision and its human review outcome."""
    id: int | None = None

    # Module and context
    module: str = ""                    # LLMModule value
    entity_id: str = ""                 # ID of the record being reviewed
    entity_type: str = ""               # Type of entity (order, episode, candidate, etc.)

    # Patient context
    patient_mrn: str | None = None
    encounter_id: str | None = None

    # LLM extraction details
    llm_model: str | None = None        # Model used (e.g., "gpt-4", "claude-3")
    llm_confidence: float | None = None # Confidence score 0.0-1.0
    llm_recommendation: str = ""        # What the LLM recommended
    llm_reasoning: str | None = None    # LLM's reasoning/explanation
    llm_extracted_data: dict = field(default_factory=dict)  # Full extraction as JSON

    # Human review
    outcome: str = "pending"            # DecisionOutcome value
    human_decision: str | None = None   # What the human chose
    override_reason: str | None = None  # LLMOverrideReason value (if overridden)
    override_notes: str | None = None   # Free-text notes for override
    reviewer_id: str | None = None      # Who reviewed
    reviewer_name: str | None = None

    # Timing
    extracted_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_duration_seconds: int | None = None  # Time spent reviewing

    # Created
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "module": self.module,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "patient_mrn": self.patient_mrn,
            "encounter_id": self.encounter_id,
            "llm_model": self.llm_model,
            "llm_confidence": self.llm_confidence,
            "llm_recommendation": self.llm_recommendation,
            "llm_reasoning": self.llm_reasoning,
            "llm_extracted_data": self.llm_extracted_data,
            "outcome": self.outcome,
            "human_decision": self.human_decision,
            "override_reason": self.override_reason,
            "override_reason_display": LLMOverrideReason.display_name(self.override_reason) if self.override_reason else None,
            "override_notes": self.override_notes,
            "reviewer_id": self.reviewer_id,
            "reviewer_name": self.reviewer_name,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_duration_seconds": self.review_duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
