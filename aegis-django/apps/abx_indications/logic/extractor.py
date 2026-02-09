"""LLM-based clinical indication extraction from notes.

This module extracts the clinical indication/syndrome from notes when
Epic order entry only captures rudimentary values like "Empiric".

The extraction follows Joint Commission requirements:
- Extract the clinical syndrome (e.g., "CAP", "UTI", "sepsis")
- NOT ICD-10 codes (those are billing constructs)
- Document at order entry time

Usage:
    from apps.abx_indications.logic.extractor import IndicationExtractor

    extractor = IndicationExtractor()
    result = extractor.extract(notes, antibiotic="ceftriaxone")

    print(result.primary_indication)  # "community_acquired_pneumonia"
    print(result.supporting_evidence)  # ["fever x3 days", "RLL infiltrate"]
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.hai_detection.logic.llm import OllamaClient

from .config import Config
from .taxonomy import (
    TherapyIntent,
    IndicationCategory,
    INDICATION_TAXONOMY,
    get_indication_by_synonym,
)

logger = logging.getLogger(__name__)


@dataclass
class IndicationExtraction:
    """Extracted clinical indication from notes."""

    # Primary indication
    primary_indication: str = "empiric_unknown"  # ID from taxonomy
    primary_indication_display: str = ""         # Human-readable
    indication_category: str = "unknown"         # Category
    indication_confidence: str = "unclear"       # definite, probable, unclear

    # Supporting evidence
    supporting_evidence: list[str] = field(default_factory=list)
    evidence_quotes: list[str] = field(default_factory=list)

    # Therapy context
    therapy_intent: str = "unknown"  # empiric, directed, prophylaxis
    culture_organism: str | None = None
    culture_site: str | None = None

    # Red flags for ASP
    indication_not_documented: bool = False  # Nothing suggests why abx given
    likely_viral: bool = False               # Notes suggest viral but got abx
    asymptomatic_bacteriuria: bool = False   # Positive UA, no UTI symptoms
    never_appropriate: bool = False          # Indication in never-appropriate list

    # Guideline comparison
    guideline_disease_ids: list[str] = field(default_factory=list)

    # Metadata
    extraction_model: str = ""
    extraction_timestamp: str = ""
    notes_reviewed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "primary_indication": self.primary_indication,
            "primary_indication_display": self.primary_indication_display,
            "indication_category": self.indication_category,
            "indication_confidence": self.indication_confidence,
            "supporting_evidence": self.supporting_evidence,
            "evidence_quotes": self.evidence_quotes,
            "therapy_intent": self.therapy_intent,
            "culture_organism": self.culture_organism,
            "culture_site": self.culture_site,
            "indication_not_documented": self.indication_not_documented,
            "likely_viral": self.likely_viral,
            "asymptomatic_bacteriuria": self.asymptomatic_bacteriuria,
            "never_appropriate": self.never_appropriate,
            "guideline_disease_ids": self.guideline_disease_ids,
        }


# JSON schema for structured extraction
INDICATION_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_indication": {
            "type": "string",
            "description": "The clinical syndrome being treated. Use standardized terms like: CAP, HAP, UTI, pyelonephritis, cellulitis, sepsis, febrile_neutropenia, surgical_prophylaxis, etc.",
        },
        "indication_confidence": {
            "type": "string",
            "enum": ["definite", "probable", "unclear"],
            "description": "How clearly the indication is documented: definite=explicitly stated, probable=strongly implied, unclear=cannot determine",
        },
        "supporting_evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Clinical findings supporting the indication (e.g., 'fever x3 days', 'RLL infiltrate', 'WBC 18k')",
        },
        "evidence_quotes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Direct quotes from notes supporting the indication",
        },
        "therapy_intent": {
            "type": "string",
            "enum": ["empiric", "directed", "prophylaxis", "unknown"],
            "description": "Why therapy was started: empiric=suspected infection, directed=culture-based, prophylaxis=prevention",
        },
        "culture_organism": {
            "type": ["string", "null"],
            "description": "Organism if culture-directed therapy",
        },
        "culture_site": {
            "type": ["string", "null"],
            "description": "Culture source if mentioned (blood, urine, sputum, etc.)",
        },
        "red_flags": {
            "type": "object",
            "properties": {
                "indication_not_documented": {
                    "type": "boolean",
                    "description": "True if notes don't explain why antibiotics were given",
                },
                "likely_viral": {
                    "type": "boolean",
                    "description": "True if notes suggest viral illness (bronchiolitis, viral URI) but antibiotics given",
                },
                "asymptomatic_bacteriuria": {
                    "type": "boolean",
                    "description": "True if positive UA/culture but no UTI symptoms documented",
                },
            },
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of how indication was determined",
        },
    },
    "required": ["primary_indication", "indication_confidence", "therapy_intent"],
}


# Prompt template for indication extraction
INDICATION_EXTRACTION_PROMPT = """You are extracting the clinical indication for an antibiotic order from clinical notes.

ANTIBIOTIC ORDERED: {antibiotic}
ORDER DATE: {order_date}

CLINICAL NOTES:
{notes}

YOUR TASK:
Determine WHY this antibiotic was ordered. Extract the clinical syndrome/diagnosis being treated.

IMPORTANT:
- Extract the CLINICAL SYNDROME (e.g., "community-acquired pneumonia", "UTI", "cellulitis")
- NOT ICD-10 codes (those are billing constructs)
- Look for the team's assessment and plan
- If multiple possible indications, choose the most likely primary one

COMMON INDICATIONS (use these terms):
- Respiratory: CAP, HAP, VAP, aspiration_pneumonia, empyema
- Urinary: UTI, pyelonephritis, CAUTI
- Bloodstream: sepsis, bacteremia, line_infection, endocarditis
- Skin: cellulitis, abscess, wound_infection
- Intra-abdominal: appendicitis, peritonitis, C_diff
- CNS: meningitis, shunt_infection
- Bone/Joint: osteomyelitis, septic_arthritis
- ENT: otitis_media, sinusitis, strep_pharyngitis
- Oncology: febrile_neutropenia
- Prophylaxis: surgical_prophylaxis

RED FLAGS to identify:
- No indication documented (notes don't explain why abx given)
- Likely viral illness (bronchiolitis, viral URI) treated with antibiotics
- Asymptomatic bacteriuria (positive UA but no symptoms)

Respond with JSON only."""


class IndicationExtractor:
    """Extracts clinical indications from notes using LLM."""

    # Default model for indication extraction
    # qwen2.5:7b is fast (~119 tok/s) with good JSON output
    DEFAULT_MODEL = "qwen2.5:7b"

    def __init__(
        self,
        llm_client=None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """Initialize extractor.

        Args:
            llm_client: LLM client instance. Creates default if None.
            model: Model to use. Uses config default if None.
            base_url: LLM base URL. Uses config default if None.
        """
        self._llm_client = llm_client
        self.model = model
        self.base_url = base_url

    @property
    def llm_client(self):
        """Lazy-load LLM client."""
        if self._llm_client is None:
            self._llm_client = OllamaClient(
                model=self.model or Config.LLM_MODEL,
                base_url=self.base_url or Config.OLLAMA_BASE_URL,
            )
        return self._llm_client

    def extract(
        self,
        notes: list[str] | str,
        antibiotic: str,
        order_date: str | None = None,
    ) -> IndicationExtraction:
        """Extract clinical indication from notes.

        Args:
            notes: Clinical notes (list or single string)
            antibiotic: Name of antibiotic ordered
            order_date: Date of order (optional)

        Returns:
            IndicationExtraction with extracted indication
        """
        # Prepare notes
        if isinstance(notes, list):
            notes_text = "\n\n---\n\n".join(notes)
            notes_count = len(notes)
        else:
            notes_text = notes
            notes_count = 1

        # Build prompt
        prompt = INDICATION_EXTRACTION_PROMPT.format(
            antibiotic=antibiotic,
            order_date=order_date or "Unknown",
            notes=notes_text[:20000],  # Limit context
        )

        start_time = time.time()

        try:
            # Call LLM with profiling
            result = self.llm_client.generate_structured_with_profile(
                prompt=prompt,
                output_schema=INDICATION_EXTRACTION_SCHEMA,
                temperature=0.0,
                profile_context="indication_extraction",
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            # Parse response
            extraction = self._parse_response(result.data, notes_count)

            # Audit log
            self._log_llm_call(
                success=True,
                elapsed_ms=elapsed_ms,
                result=result,
            )

            return extraction

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            self._log_llm_call(
                success=False,
                elapsed_ms=elapsed_ms,
                error=str(e),
            )
            logger.error(f"Indication extraction failed: {e}")
            return IndicationExtraction(
                primary_indication="empiric_unknown",
                indication_confidence="unclear",
                indication_not_documented=True,
                notes_reviewed_count=notes_count,
            )

    def _parse_response(
        self,
        data: dict[str, Any],
        notes_count: int,
    ) -> IndicationExtraction:
        """Parse LLM response into IndicationExtraction."""

        # Get primary indication
        raw_indication = data.get("primary_indication", "empiric_unknown")

        # Try to map to taxonomy
        mapping = get_indication_by_synonym(raw_indication)
        if mapping:
            indication_id = mapping.indication_id
            display_name = mapping.display_name
            category = mapping.category.value
            guideline_ids = mapping.guideline_disease_ids
            never_appropriate = mapping.never_appropriate
        else:
            indication_id = raw_indication.lower().replace(" ", "_")
            display_name = raw_indication
            category = "unknown"
            guideline_ids = []
            never_appropriate = False

        # Parse red flags
        red_flags = data.get("red_flags", {})

        return IndicationExtraction(
            primary_indication=indication_id,
            primary_indication_display=display_name,
            indication_category=category,
            indication_confidence=data.get("indication_confidence", "unclear"),
            supporting_evidence=data.get("supporting_evidence", []),
            evidence_quotes=data.get("evidence_quotes", []),
            therapy_intent=data.get("therapy_intent", "unknown"),
            culture_organism=data.get("culture_organism"),
            culture_site=data.get("culture_site"),
            indication_not_documented=red_flags.get("indication_not_documented", False),
            likely_viral=red_flags.get("likely_viral", False),
            asymptomatic_bacteriuria=red_flags.get("asymptomatic_bacteriuria", False),
            never_appropriate=never_appropriate,
            guideline_disease_ids=guideline_ids,
            extraction_model=getattr(self.llm_client, 'model', 'unknown'),
            extraction_timestamp=datetime.now().isoformat(),
            notes_reviewed_count=notes_count,
        )

    def _log_llm_call(self, success, elapsed_ms, result=None, error=None):
        """Log LLM call to audit table."""
        try:
            from apps.abx_indications.models import IndicationLLMAuditLog

            input_tokens = 0
            output_tokens = 0
            if result and hasattr(result, 'profile') and result.profile:
                input_tokens = result.profile.input_tokens
                output_tokens = result.profile.output_tokens

            IndicationLLMAuditLog.objects.create(
                model=getattr(self.llm_client, 'model', Config.LLM_MODEL),
                success=success,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_time_ms=elapsed_ms,
                error_message=error or '',
            )
        except Exception as e:
            logger.warning(f"Failed to log LLM call: {e}")
