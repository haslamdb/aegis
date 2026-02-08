"""Clinical information extraction module.

This module provides LLM-based extraction of clinical information from
notes. The extracted data is used by the rules engine to apply NHSN
criteria deterministically.

Architecture (standard):
    Notes → ClinicalExtractor (LLM) → ClinicalExtraction → RulesEngine

Architecture (two-stage):
    Notes → TriageExtractor (7B) → [escalate?] → ClinicalExtractor (70B) → RulesEngine
"""

from .clabsi_extractor import CLABSIExtractor
from .ssi_extractor import SSIExtractor
from .vae_extractor import VAEExtractor
from .cauti_extractor import CAUTIExtractor
from .cdi_extractor import CDIExtractor

# Two-stage triage
from .triage_extractor import (
    TriageExtractor,
    TriageExtraction,
    TriageDecision,
    should_escalate,
)

# Training data collection
from .training_collector import (
    TrainingCollector,
    get_collector,
    get_escalation_stats,
    log_extraction,
    log_human_review,
)

__all__ = [
    # HAI-specific extractors
    "CLABSIExtractor",
    "SSIExtractor",
    "VAEExtractor",
    "CAUTIExtractor",
    "CDIExtractor",
    # Triage
    "TriageExtractor",
    "TriageExtraction",
    "TriageDecision",
    "should_escalate",
    # Training data
    "TrainingCollector",
    "get_collector",
    "get_escalation_stats",
    "log_extraction",
    "log_human_review",
]
