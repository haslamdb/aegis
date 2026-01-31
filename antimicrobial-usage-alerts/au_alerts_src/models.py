"""Data models for Antimicrobial Usage Alerts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SyndromeReviewDecision(Enum):
    """Human review decisions for clinical syndrome verification.

    Used when reviewing LLM-extracted indications per JC requirements.
    """
    CONFIRM_SYNDROME = "confirm_syndrome"  # LLM extraction is correct
    CORRECT_SYNDROME = "correct_syndrome"  # Change to different syndrome
    NO_INDICATION = "no_indication"        # No valid indication documented
    VIRAL_ILLNESS = "viral_illness"        # Viral illness, antibiotics not indicated
    ASYMPTOMATIC_BACTERIURIA = "asymptomatic_bacteriuria"  # ASB, no treatment needed


class AgentReviewDecision(Enum):
    """Human review decisions for antibiotic appropriateness.

    Assesses whether the prescribed antibiotic is appropriate for the syndrome.
    """
    APPROPRIATE = "agent_appropriate"        # Good choice for this syndrome
    ACCEPTABLE = "agent_acceptable"          # Not first-line but reasonable
    INAPPROPRIATE = "agent_inappropriate"    # Wrong antibiotic for syndrome
    SKIP = "agent_skip"                      # Not reviewed (optional field)


@dataclass
class Patient:
    """Patient information."""
    fhir_id: str
    mrn: str
    name: str
    birth_date: str | None = None
    gender: str | None = None
    location: str | None = None
    department: str | None = None


@dataclass
class MedicationOrder:
    """Active medication order."""
    fhir_id: str
    patient_id: str
    medication_name: str
    rxnorm_code: str | None = None
    dose: str | None = None
    route: str | None = None
    start_date: datetime | None = None
    status: str = "active"

    @property
    def duration_hours(self) -> float | None:
        """Calculate hours since medication started."""
        if self.start_date is None:
            return None
        delta = datetime.now() - self.start_date.replace(tzinfo=None)
        return delta.total_seconds() / 3600

    @property
    def duration_days(self) -> float | None:
        """Calculate days since medication started."""
        hours = self.duration_hours
        return hours / 24 if hours else None


@dataclass
class UsageAssessment:
    """Assessment of broad-spectrum antibiotic usage."""
    patient: Patient
    medication: MedicationOrder
    duration_hours: float
    threshold_hours: float
    exceeds_threshold: bool
    recommendation: str
    assessed_at: datetime = field(default_factory=datetime.now)
    severity: AlertSeverity = AlertSeverity.WARNING

    # Optional context
    related_cultures: list[str] = field(default_factory=list)
    justification_found: bool = False
    justification_reason: str | None = None


@dataclass
class IndicationCandidate:
    """Antibiotic order needing indication review."""
    id: str
    patient: Patient
    medication: MedicationOrder
    icd10_codes: list[str]
    icd10_classification: str  # A, S, N, P, FN, U
    icd10_primary_indication: str | None
    llm_extracted_indication: str | None
    llm_classification: str | None
    final_classification: str
    classification_source: str  # icd10, llm, manual
    status: str  # pending, alerted, reviewed
    alert_id: str | None = None
    # Location/service for analytics
    location: str | None = None  # Unit/ward (PICU, 4 West, ED)
    service: str | None = None  # Ordering service (Hospitalist, Surgery)
    # CCHMC guideline tracking
    cchmc_disease_matched: str | None = None  # Matched CCHMC disease entity
    cchmc_agent_category: str | None = None  # first_line, alternative, off_guideline
    cchmc_guideline_agents: str | None = None  # Recommended agents from CCHMC
    cchmc_recommendation: str | None = None  # Full recommendation text
    # JC-compliant clinical syndrome tracking (from taxonomy-based extraction)
    clinical_syndrome: str | None = None  # Canonical ID (e.g., "cap", "uti_complicated")
    clinical_syndrome_display: str | None = None  # Human-readable (e.g., "Community-Acquired Pneumonia")
    syndrome_category: str | None = None  # respiratory, urinary, bloodstream, etc.
    syndrome_confidence: str | None = None  # definite, probable, unclear
    therapy_intent: str | None = None  # empiric, directed, prophylaxis
    guideline_disease_ids: list[str] | None = None  # Maps to cchmc_disease_guidelines.json
    # Red flags for ASP review
    likely_viral: bool = False  # Notes suggest viral illness
    asymptomatic_bacteriuria: bool = False  # Positive UA without symptoms
    indication_not_documented: bool = False  # No indication found in notes
    never_appropriate: bool = False  # Indication where abx rarely/never appropriate


@dataclass
class IndicationAssessment:
    """Assessment result for an antibiotic order."""
    candidate: IndicationCandidate
    requires_alert: bool  # True if final_classification == 'N'
    recommendation: str
    severity: AlertSeverity
    assessed_at: datetime = field(default_factory=datetime.now)


@dataclass
class EvidenceSource:
    """Source metadata for LLM-extracted evidence.

    Tracks where in clinical notes the evidence was found,
    including provider attribution and relevant quotes.
    """
    note_type: str  # PROGRESS_NOTE, ID_CONSULT, DISCHARGE_SUMMARY, etc.
    note_date: str | None = None
    author: str | None = None  # Provider name
    quotes: list[str] = field(default_factory=list)
    relevance: str | None = None  # Brief description of why relevant

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "note_type": self.note_type,
            "note_date": self.note_date,
            "author": self.author,
            "quotes": self.quotes,
            "relevance": self.relevance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceSource":
        """Create from dictionary."""
        return cls(
            note_type=data.get("note_type", "UNKNOWN"),
            note_date=data.get("note_date"),
            author=data.get("author"),
            quotes=data.get("quotes", []),
            relevance=data.get("relevance"),
        )


@dataclass
class IndicationExtraction:
    """LLM extraction result from clinical notes."""
    found_indications: list[str]
    supporting_quotes: list[str]
    confidence: str  # HIGH, MEDIUM, LOW
    model_used: str
    prompt_version: str
    tokens_used: int | None = None
    # New fields for evidence source attribution
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    notes_filtered_count: int | None = None  # Notes included after filtering
    notes_total_count: int | None = None  # Total notes available
