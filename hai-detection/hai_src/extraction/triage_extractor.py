"""Fast triage extraction for HAI candidate screening.

This module implements a lightweight first-pass extraction using a smaller,
faster model (e.g., llama3.1:8b). The triage determines whether a case
requires full analysis with the larger model or can be classified directly.

Architecture:
    Stage 1 (Triage): 8B model, ~5 seconds, simplified extraction
        ↓
    Decision: needs_full_analysis?
        ↓ No                    ↓ Yes
    Use triage results      Stage 2 (Full): 70B model, ~60 seconds
        ↓                       ↓
    Rules Engine            Rules Engine

Escalation triggers (go to Stage 2):
    - Documentation quality is poor/limited
    - Alternate infection source mentioned
    - Contamination signals present
    - MBI-LCBI factors detected
    - Clinical impression is ambiguous
    - Multiple organisms or polymicrobial
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..config import Config
from ..models import HAICandidate, ClinicalNote, HAIType
from ..llm.ollama import OllamaClient
from ..llm.base import LLMProfile
from ..notes.chunker import NoteChunker

logger = logging.getLogger(__name__)


class TriageDecision(str, Enum):
    """Triage decision outcome."""
    CLEAR_HAI = "clear_hai"  # Obvious HAI, no escalation needed
    CLEAR_NOT_HAI = "clear_not_hai"  # Obvious non-HAI, no escalation needed
    NEEDS_FULL_ANALYSIS = "needs_full_analysis"  # Escalate to 70B model


@dataclass
class TriageExtraction:
    """Simplified extraction from triage pass.

    Contains only the fields needed to decide:
    1. Can we classify without full analysis?
    2. If so, what's the likely classification?
    """

    # Documentation assessment
    documentation_quality: str = "unknown"  # poor/limited/adequate/detailed

    # Clear signals
    obvious_hai_signals: bool = False
    obvious_not_hai_signals: bool = False

    # Complexity indicators (trigger escalation)
    alternate_source_mentioned: bool = False
    contamination_mentioned: bool = False
    mbi_factors_present: bool = False
    multiple_organisms: bool = False
    clinical_impression_ambiguous: bool = False

    # Quick assessment
    primary_impression: str | None = None  # e.g., "line infection", "UTI source"
    quick_reasoning: str = ""

    # Decision
    needs_full_analysis: bool = True
    decision: TriageDecision = TriageDecision.NEEDS_FULL_ANALYSIS

    # Profiling
    profile: LLMProfile | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "documentation_quality": self.documentation_quality,
            "obvious_hai_signals": self.obvious_hai_signals,
            "obvious_not_hai_signals": self.obvious_not_hai_signals,
            "alternate_source_mentioned": self.alternate_source_mentioned,
            "contamination_mentioned": self.contamination_mentioned,
            "mbi_factors_present": self.mbi_factors_present,
            "multiple_organisms": self.multiple_organisms,
            "clinical_impression_ambiguous": self.clinical_impression_ambiguous,
            "primary_impression": self.primary_impression,
            "quick_reasoning": self.quick_reasoning,
            "needs_full_analysis": self.needs_full_analysis,
            "decision": self.decision.value,
        }


# Simplified JSON schema for triage extraction
TRIAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "documentation_quality": {
            "type": "string",
            "enum": ["poor", "limited", "adequate", "detailed"],
            "description": "Quality of clinical documentation for HAI assessment",
        },
        "obvious_hai_signals": {
            "type": "boolean",
            "description": "True if documentation clearly indicates HAI (e.g., 'line infection confirmed')",
        },
        "obvious_not_hai_signals": {
            "type": "boolean",
            "description": "True if documentation clearly rules out HAI (e.g., 'contaminant', 'UTI source')",
        },
        "alternate_source_mentioned": {
            "type": "boolean",
            "description": "True if an alternate infection source is mentioned (UTI, pneumonia, etc.)",
        },
        "contamination_mentioned": {
            "type": "boolean",
            "description": "True if contamination is mentioned or suspected",
        },
        "mbi_factors_present": {
            "type": "boolean",
            "description": "True if MBI-LCBI factors present (neutropenia, mucositis, GI GVHD, chemo)",
        },
        "multiple_organisms": {
            "type": "boolean",
            "description": "True if multiple organisms or polymicrobial infection mentioned",
        },
        "clinical_impression_ambiguous": {
            "type": "boolean",
            "description": "True if clinical team's impression is unclear or conflicting",
        },
        "primary_impression": {
            "type": ["string", "null"],
            "description": "Brief statement of most likely diagnosis if clear",
        },
        "quick_reasoning": {
            "type": "string",
            "description": "One sentence explaining triage assessment",
        },
    },
    "required": [
        "documentation_quality",
        "obvious_hai_signals",
        "obvious_not_hai_signals",
        "alternate_source_mentioned",
        "contamination_mentioned",
        "mbi_factors_present",
        "quick_reasoning",
    ],
}


# Triage prompt templates by HAI type
TRIAGE_PROMPTS = {
    HAIType.CLABSI: """You are performing a QUICK TRIAGE of a potential Central Line-Associated Bloodstream Infection (CLABSI).

Patient has a positive blood culture with a central line in place. Your job is to quickly assess:
1. Is this CLEARLY a line infection? (obvious HAI)
2. Is this CLEARLY NOT a line infection? (obvious non-HAI: contamination, secondary to another source)
3. Or does this need detailed analysis?

Patient: {patient_id}
Organism: {organism}
Central Line Days: {device_days}

Clinical Notes (abbreviated):
{notes}

Assess QUICKLY - this is triage, not full analysis. Look for:
- Clear statements like "line infection", "CLABSI", "line-related sepsis" → obvious_hai_signals = true
- Clear statements like "contaminant", "UTI source", "pneumonia source" → obvious_not_hai_signals = true
- Mentions of alternate sources (UTI, pneumonia, wound) → alternate_source_mentioned = true
- Mentions of neutropenia, mucositis, chemo, transplant → mbi_factors_present = true
- Uncertainty or conflicting opinions → clinical_impression_ambiguous = true

Respond with JSON only.""",

    HAIType.CAUTI: """You are performing a QUICK TRIAGE of a potential Catheter-Associated Urinary Tract Infection (CAUTI).

Patient has a positive urine culture with a urinary catheter in place. Quickly assess:
1. Is this CLEARLY a catheter-associated UTI? (obvious HAI)
2. Is this CLEARLY NOT a CAUTI? (asymptomatic bacteriuria, contamination)
3. Or does this need detailed analysis?

Patient: {patient_id}
Organism: {organism}
Catheter Days: {device_days}

Clinical Notes (abbreviated):
{notes}

Respond with JSON only.""",

    HAIType.SSI: """You are performing a QUICK TRIAGE of a potential Surgical Site Infection (SSI).

Patient had recent surgery and now has signs concerning for infection. Quickly assess:
1. Is this CLEARLY an SSI? (obvious HAI)
2. Is this CLEARLY NOT an SSI? (normal healing, unrelated infection)
3. Or does this need detailed analysis?

Patient: {patient_id}
Procedure: {procedure}
Days Post-Op: {days_post_op}

Clinical Notes (abbreviated):
{notes}

Respond with JSON only.""",

    HAIType.VAE: """You are performing a QUICK TRIAGE of a potential Ventilator-Associated Event (VAE).

Patient is on mechanical ventilation with worsening respiratory status. Quickly assess:
1. Is this CLEARLY a VAE? (obvious HAI)
2. Is this CLEARLY NOT a VAE? (fluid overload, atelectasis)
3. Or does this need detailed analysis?

Patient: {patient_id}
Ventilator Days: {device_days}

Clinical Notes (abbreviated):
{notes}

Respond with JSON only.""",

    HAIType.CDI: """You are performing a QUICK TRIAGE of a potential Clostridioides difficile Infection (CDI).

Patient has a positive C. diff test. Quickly assess:
1. Is this CLEARLY a CDI? (obvious HAI)
2. Is this CLEARLY NOT a CDI? (colonization, recurrence outside window)
3. Or does this need detailed analysis?

Patient: {patient_id}
Test Type: {test_type}

Clinical Notes (abbreviated):
{notes}

Respond with JSON only.""",
}


class TriageExtractor:
    """Fast triage extractor using a smaller model.

    This extractor performs a quick first-pass analysis to determine
    whether a case needs full analysis with the larger model.
    """

    # Default to Qwen2.5-7B for best speed + JSON output quality
    # Benchmarked at 119 tok/s, ~1s per triage (vs 15 tok/s for 70B)
    DEFAULT_TRIAGE_MODEL = "qwen2.5:7b"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        max_context_chars: int = 4000,  # Smaller context for triage
    ):
        """Initialize triage extractor.

        Args:
            model: Model to use for triage. Defaults to 8B.
            base_url: Ollama base URL. Uses config default if None.
            max_context_chars: Maximum chars of notes to include.
        """
        self.model = model or self.DEFAULT_TRIAGE_MODEL
        self.base_url = base_url or Config.OLLAMA_BASE_URL
        self.max_context_chars = max_context_chars
        self.chunker = NoteChunker()

        # Lazy-load client
        self._client: OllamaClient | None = None

    @property
    def client(self) -> OllamaClient:
        """Get or create Ollama client."""
        if self._client is None:
            self._client = OllamaClient(
                base_url=self.base_url,
                model=self.model,
                timeout=60,  # Shorter timeout for fast model
                num_ctx=4096,  # Smaller context window
            )
        return self._client

    def extract(
        self,
        candidate: HAICandidate,
        notes: list[ClinicalNote],
        hai_type: HAIType | None = None,
    ) -> TriageExtraction:
        """Perform triage extraction.

        Args:
            candidate: HAI candidate to triage.
            notes: Clinical notes.
            hai_type: HAI type (inferred from candidate if not provided).

        Returns:
            TriageExtraction with assessment and decision.
        """
        # Determine HAI type
        if hai_type is None:
            hai_type = self._infer_hai_type(candidate)

        # Build abbreviated notes context
        notes_context = self._build_notes_context(notes)

        # Build prompt
        prompt = self._build_prompt(candidate, notes_context, hai_type)

        try:
            # Call LLM with structured output
            result = self.client.generate_structured_with_profile(
                prompt=prompt,
                output_schema=TRIAGE_OUTPUT_SCHEMA,
                temperature=0.0,
                profile_context=f"triage_{hai_type.value}",
            )

            # Parse response
            extraction = self._parse_response(result.data)
            extraction.profile = result.profile

            # Make escalation decision
            extraction.decision = self._make_decision(extraction)
            extraction.needs_full_analysis = (
                extraction.decision == TriageDecision.NEEDS_FULL_ANALYSIS
            )

            logger.info(
                f"Triage [{hai_type.value}]: decision={extraction.decision.value} "
                f"| {result.profile.summary()}"
            )

            return extraction

        except Exception as e:
            logger.error(f"Triage extraction failed: {e}")
            # On error, escalate to full analysis
            return TriageExtraction(
                documentation_quality="error",
                needs_full_analysis=True,
                decision=TriageDecision.NEEDS_FULL_ANALYSIS,
                quick_reasoning=f"Triage failed: {e}",
            )

    def _infer_hai_type(self, candidate: HAICandidate) -> HAIType:
        """Infer HAI type from candidate."""
        # Check for explicit type
        if hasattr(candidate, 'hai_type') and candidate.hai_type:
            return candidate.hai_type

        # Infer from device/culture type
        if candidate.device_info:
            device_type = candidate.device_info.device_type.lower()
            if any(t in device_type for t in ['central', 'picc', 'port', 'hickman']):
                return HAIType.CLABSI
            if any(t in device_type for t in ['foley', 'urinary', 'catheter']):
                return HAIType.CAUTI
            if 'vent' in device_type:
                return HAIType.VAE

        # Default to CLABSI for blood cultures
        return HAIType.CLABSI

    def _build_notes_context(self, notes: list[ClinicalNote]) -> str:
        """Build abbreviated notes context for triage.

        Prioritizes Assessment/Plan sections and recent notes.
        """
        # Use chunker but with tighter limits
        context = self.chunker.extract_relevant_context(
            notes,
            max_length=self.max_context_chars,
        )
        return context

    def _build_prompt(
        self,
        candidate: HAICandidate,
        notes_context: str,
        hai_type: HAIType,
    ) -> str:
        """Build triage prompt."""
        template = TRIAGE_PROMPTS.get(hai_type, TRIAGE_PROMPTS[HAIType.CLABSI])

        # Build template variables
        variables = {
            "patient_id": candidate.patient.mrn if candidate.patient else "Unknown",
            "organism": candidate.culture.organism if candidate.culture else "Unknown",
            "device_days": candidate.device_days_at_culture or "Unknown",
            "notes": notes_context,
        }

        # Add HAI-specific variables
        if hai_type == HAIType.SSI:
            variables["procedure"] = getattr(candidate, 'procedure_name', 'Unknown')
            variables["days_post_op"] = getattr(candidate, 'days_post_op', 'Unknown')
        elif hai_type == HAIType.CDI:
            variables["test_type"] = getattr(candidate, 'test_type', 'Unknown')

        return template.format(**variables)

    def _parse_response(self, data: dict[str, Any]) -> TriageExtraction:
        """Parse LLM response into TriageExtraction."""
        return TriageExtraction(
            documentation_quality=data.get("documentation_quality", "unknown"),
            obvious_hai_signals=data.get("obvious_hai_signals", False),
            obvious_not_hai_signals=data.get("obvious_not_hai_signals", False),
            alternate_source_mentioned=data.get("alternate_source_mentioned", False),
            contamination_mentioned=data.get("contamination_mentioned", False),
            mbi_factors_present=data.get("mbi_factors_present", False),
            multiple_organisms=data.get("multiple_organisms", False),
            clinical_impression_ambiguous=data.get("clinical_impression_ambiguous", False),
            primary_impression=data.get("primary_impression"),
            quick_reasoning=data.get("quick_reasoning", ""),
        )

    def _make_decision(self, extraction: TriageExtraction) -> TriageDecision:
        """Make escalation decision based on triage extraction.

        Returns CLEAR_HAI or CLEAR_NOT_HAI only if confident.
        Otherwise returns NEEDS_FULL_ANALYSIS.
        """
        # Escalation triggers - any of these means we need full analysis
        escalation_triggers = [
            extraction.documentation_quality in ("poor", "limited"),
            extraction.alternate_source_mentioned,
            extraction.contamination_mentioned,
            extraction.mbi_factors_present,
            extraction.multiple_organisms,
            extraction.clinical_impression_ambiguous,
        ]

        if any(escalation_triggers):
            logger.debug(f"Escalating due to: {[t for t, v in zip(['poor_docs', 'alt_source', 'contam', 'mbi', 'multi_org', 'ambiguous'], escalation_triggers) if v]}")
            return TriageDecision.NEEDS_FULL_ANALYSIS

        # Clear cases
        if extraction.obvious_hai_signals and not extraction.obvious_not_hai_signals:
            return TriageDecision.CLEAR_HAI

        if extraction.obvious_not_hai_signals and not extraction.obvious_hai_signals:
            return TriageDecision.CLEAR_NOT_HAI

        # Conflicting signals or unclear - escalate
        return TriageDecision.NEEDS_FULL_ANALYSIS


def should_escalate(triage: TriageExtraction) -> bool:
    """Convenience function to check if escalation is needed.

    Args:
        triage: Triage extraction result.

    Returns:
        True if full analysis is needed, False if triage is sufficient.
    """
    return triage.needs_full_analysis
