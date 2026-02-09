"""Fast triage-based clinical appearance extraction.

Uses a smaller 7B model (qwen2.5:7b) for initial triage (~1 sec vs ~60 sec),
escalating to the full 70B model only when ambiguous. This provides 40-60%
fast-path resolution while maintaining accuracy for complex cases.

Escalation Triggers:
- documentation_quality in ["poor", "limited"]
- conflicting_signals is True
- preliminary_appearance is "unclear"
- Low confidence with concerning signs
- Medium confidence with key concerning findings (lethargy, mottling, toxic)

Adapted from guideline-adherence/guideline_src/nlp/triage_extractor.py (485 lines).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from django.conf import settings

from apps.hai_detection.logic.llm import OllamaClient

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    """Get guideline adherence configuration from Django settings."""
    return getattr(settings, 'GUIDELINE_ADHERENCE', {})


class TriageDecision(Enum):
    """Triage decision outcome."""
    CLEAR_WELL = "clear_well"           # High confidence well-appearing
    CLEAR_ILL = "clear_ill"             # High confidence ill-appearing
    NEEDS_FULL_ANALYSIS = "needs_full"  # Ambiguous, escalate to full model


@dataclass
class AppearanceTriageResult:
    """Result of fast clinical appearance triage."""

    # Primary classification
    preliminary_appearance: str  # well, ill, toxic, unclear
    confidence: str  # high, medium, low
    documentation_quality: str  # poor, limited, adequate, detailed

    # Escalation signals
    conflicting_signals: bool
    concerning_signs_count: int
    reassuring_signs_count: int

    # Key findings for escalation decision
    lethargy_mentioned: bool = False
    mottling_mentioned: bool = False
    poor_feeding_mentioned: bool = False
    toxic_appearing_mentioned: bool = False
    well_appearing_mentioned: bool = False

    # Supporting information
    key_quotes: list[str] = field(default_factory=list)
    quick_reasoning: str = ""

    # Decision and metadata
    decision: TriageDecision = TriageDecision.NEEDS_FULL_ANALYSIS
    needs_escalation: bool = True
    escalation_reasons: list[str] = field(default_factory=list)

    # Timing
    model_used: str = ""
    response_time_ms: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "preliminary_appearance": self.preliminary_appearance,
            "confidence": self.confidence,
            "documentation_quality": self.documentation_quality,
            "conflicting_signals": self.conflicting_signals,
            "concerning_signs_count": self.concerning_signs_count,
            "reassuring_signs_count": self.reassuring_signs_count,
            "lethargy_mentioned": self.lethargy_mentioned,
            "mottling_mentioned": self.mottling_mentioned,
            "poor_feeding_mentioned": self.poor_feeding_mentioned,
            "toxic_appearing_mentioned": self.toxic_appearing_mentioned,
            "well_appearing_mentioned": self.well_appearing_mentioned,
            "key_quotes": self.key_quotes,
            "quick_reasoning": self.quick_reasoning,
            "decision": self.decision.value,
            "needs_escalation": self.needs_escalation,
            "escalation_reasons": self.escalation_reasons,
            "model_used": self.model_used,
            "response_time_ms": self.response_time_ms,
        }


class ClinicalAppearanceTriageExtractor:
    """Fast triage extraction for clinical appearance using small 7B model.

    Designed for rapid (~1 second) initial assessment to determine if a
    patient is clearly well-appearing, clearly ill-appearing, or needs
    detailed analysis with the full 70B model.

    Uses OllamaClient from HAI Detection for LLM inference.
    """

    TRIAGE_PROMPT = """You are a clinical triage system analyzing pediatric notes for clinical appearance.

TASK: Quickly assess if the infant's clinical appearance is clearly documented.

CLINICAL NOTES:
{notes}

Respond with JSON in this exact format:
{{
    "preliminary_appearance": "well" | "ill" | "toxic" | "unclear",
    "confidence": "high" | "medium" | "low",
    "documentation_quality": "poor" | "limited" | "adequate" | "detailed",
    "conflicting_signals": true | false,
    "concerning_signs_count": <number>,
    "reassuring_signs_count": <number>,
    "lethargy_mentioned": true | false,
    "mottling_mentioned": true | false,
    "poor_feeding_mentioned": true | false,
    "toxic_appearing_mentioned": true | false,
    "well_appearing_mentioned": true | false,
    "key_quotes": ["quote1", "quote2"],
    "quick_reasoning": "one sentence explanation"
}}

Definitions:
- well: Alert, active, feeding well, good color, interactive
- ill: Lethargic, irritable, poor feeding, mottled, decreased activity
- toxic: Severely ill, obtunded, shock, septic appearance
- unclear: Cannot determine from documentation

Documentation quality:
- poor: No appearance information at all
- limited: Minimal mentions (just "appears well" or "fussy")
- adequate: Some exam findings supporting assessment
- detailed: Thorough exam with multiple appearance indicators

IMPORTANT: Set conflicting_signals=true if you see both well and ill indicators."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """Initialize the triage extractor.

        Args:
            model: LLM model name. Defaults to GUIDELINE_ADHERENCE.TRIAGE_MODEL.
            base_url: Ollama API base URL. Defaults to GUIDELINE_ADHERENCE.OLLAMA_BASE_URL.
        """
        config = _get_config()
        self.model = model or config.get('TRIAGE_MODEL', 'qwen2.5:7b')
        self.base_url = base_url or config.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        self._client = OllamaClient(
            base_url=self.base_url,
            model=self.model,
            timeout=30,
            num_ctx=4096,
        )

    def is_available(self) -> bool:
        """Check if the triage LLM is available."""
        return self._client.is_available()

    def extract(
        self,
        notes: list[str],
        patient_context: Optional[dict] = None,
    ) -> AppearanceTriageResult:
        """Perform fast triage extraction.

        Args:
            notes: List of clinical note texts.
            patient_context: Optional context (age, etc.)

        Returns:
            AppearanceTriageResult with triage decision.
        """
        start_time = time.time()

        # Prepare notes with truncation (smaller context for speed)
        combined_notes = self._prepare_notes(notes, max_chars=8000)

        if not combined_notes.strip():
            return AppearanceTriageResult(
                preliminary_appearance="unclear",
                confidence="low",
                documentation_quality="poor",
                conflicting_signals=False,
                concerning_signs_count=0,
                reassuring_signs_count=0,
                decision=TriageDecision.NEEDS_FULL_ANALYSIS,
                needs_escalation=True,
                escalation_reasons=["No notes provided"],
                model_used=self.model,
                response_time_ms=0,
            )

        prompt = self.TRIAGE_PROMPT.format(notes=combined_notes)

        try:
            result = self._call_llm(prompt)
            elapsed_ms = int((time.time() - start_time) * 1000)
            return self._parse_response(result, elapsed_ms)

        except Exception as e:
            logger.error(f"Triage extraction failed: {e}")
            elapsed_ms = int((time.time() - start_time) * 1000)

            return AppearanceTriageResult(
                preliminary_appearance="unclear",
                confidence="low",
                documentation_quality="poor",
                conflicting_signals=False,
                concerning_signs_count=0,
                reassuring_signs_count=0,
                decision=TriageDecision.NEEDS_FULL_ANALYSIS,
                needs_escalation=True,
                escalation_reasons=[f"Extraction error: {e}"],
                model_used=self.model,
                response_time_ms=elapsed_ms,
            )

    def _prepare_notes(self, notes: list[str], max_chars: int = 8000) -> str:
        """Prepare notes for triage (smaller context window)."""
        combined = "\n\n---\n\n".join(notes)
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n\n[Truncated for triage...]"
        return combined

    def _call_llm(self, prompt: str) -> dict:
        """Call the triage LLM via OllamaClient."""
        try:
            result = self._client.generate_structured(
                prompt=prompt,
                output_schema={
                    "type": "object",
                    "properties": {
                        "preliminary_appearance": {"type": "string"},
                        "confidence": {"type": "string"},
                        "documentation_quality": {"type": "string"},
                        "conflicting_signals": {"type": "boolean"},
                        "concerning_signs_count": {"type": "integer"},
                        "reassuring_signs_count": {"type": "integer"},
                        "lethargy_mentioned": {"type": "boolean"},
                        "mottling_mentioned": {"type": "boolean"},
                        "poor_feeding_mentioned": {"type": "boolean"},
                        "toxic_appearing_mentioned": {"type": "boolean"},
                        "well_appearing_mentioned": {"type": "boolean"},
                        "key_quotes": {"type": "array", "items": {"type": "string"}},
                        "quick_reasoning": {"type": "string"},
                    },
                },
                temperature=0.0,
                profile_context="clinical_appearance_triage",
            )
            return result
        except ValueError:
            # JSON parse failed; try unstructured fallback
            logger.warning("Structured triage failed, trying unstructured")
            response = self._client.generate(
                prompt=prompt,
                temperature=0.0,
                max_tokens=512,
                profile_context="clinical_appearance_triage_fallback",
            )
            return self._extract_json(response.content)

    def _extract_json(self, text: str) -> dict:
        """Try to extract JSON from text with surrounding content."""
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Find matching braces
        brace_count = 0
        start_idx = -1
        end_idx = -1

        for i, char in enumerate(text):
            if char == "{":
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0 and start_idx >= 0:
                    end_idx = i + 1
                    break

        if start_idx >= 0 and end_idx > start_idx:
            json_str = text[start_idx:end_idx]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        logger.warning("Could not extract JSON from triage response")
        return {}

    def _parse_response(
        self,
        result: dict,
        elapsed_ms: int,
    ) -> AppearanceTriageResult:
        """Parse triage response and determine escalation."""
        # Extract fields with defaults
        appearance = result.get("preliminary_appearance", "unclear").lower()
        confidence = result.get("confidence", "low").lower()
        doc_quality = result.get("documentation_quality", "poor").lower()
        conflicting = result.get("conflicting_signals", False)
        concerning_count = result.get("concerning_signs_count", 0)
        reassuring_count = result.get("reassuring_signs_count", 0)

        # Key findings
        lethargy = result.get("lethargy_mentioned", False)
        mottling = result.get("mottling_mentioned", False)
        poor_feeding = result.get("poor_feeding_mentioned", False)
        toxic_appearing = result.get("toxic_appearing_mentioned", False)
        well_appearing = result.get("well_appearing_mentioned", False)

        # Quotes and reasoning
        quotes = result.get("key_quotes", [])
        if isinstance(quotes, str):
            quotes = [quotes]
        reasoning = result.get("quick_reasoning", "")

        # Determine escalation
        escalation_reasons = []
        needs_escalation = False

        # Escalation trigger 1: Poor documentation
        if doc_quality in ["poor", "limited"]:
            needs_escalation = True
            escalation_reasons.append(f"Documentation quality: {doc_quality}")

        # Escalation trigger 2: Conflicting signals
        if conflicting:
            needs_escalation = True
            escalation_reasons.append("Conflicting clinical signals")

        # Escalation trigger 3: Unclear appearance
        if appearance == "unclear":
            needs_escalation = True
            escalation_reasons.append("Appearance unclear from notes")

        # Escalation trigger 4: Low confidence with concerning signs
        if confidence == "low" and concerning_count > 0:
            needs_escalation = True
            escalation_reasons.append("Low confidence with concerning signs")

        # Escalation trigger 5: Medium confidence with key concerning findings
        if confidence == "medium" and (lethargy or mottling or toxic_appearing):
            needs_escalation = True
            escalation_reasons.append("Key concerning findings need verification")

        # Determine triage decision
        if needs_escalation:
            decision = TriageDecision.NEEDS_FULL_ANALYSIS
        elif appearance in ["ill", "toxic"]:
            decision = TriageDecision.CLEAR_ILL
        elif appearance == "well" and confidence in ["high", "medium"]:
            decision = TriageDecision.CLEAR_WELL
        else:
            # Edge case: default to escalation
            decision = TriageDecision.NEEDS_FULL_ANALYSIS
            needs_escalation = True
            escalation_reasons.append("Could not determine clear classification")

        return AppearanceTriageResult(
            preliminary_appearance=appearance,
            confidence=confidence,
            documentation_quality=doc_quality,
            conflicting_signals=conflicting,
            concerning_signs_count=concerning_count,
            reassuring_signs_count=reassuring_count,
            lethargy_mentioned=lethargy,
            mottling_mentioned=mottling,
            poor_feeding_mentioned=poor_feeding,
            toxic_appearing_mentioned=toxic_appearing,
            well_appearing_mentioned=well_appearing,
            key_quotes=quotes,
            quick_reasoning=reasoning,
            decision=decision,
            needs_escalation=needs_escalation,
            escalation_reasons=escalation_reasons,
            model_used=self.model,
            response_time_ms=elapsed_ms,
        )


def get_triage_extractor() -> ClinicalAppearanceTriageExtractor | None:
    """Factory function to get configured triage extractor.

    Returns:
        ClinicalAppearanceTriageExtractor if model available, None otherwise.
    """
    extractor = ClinicalAppearanceTriageExtractor()
    if extractor.is_available():
        return extractor

    logger.warning(
        f"Triage model {extractor.model} not available at {extractor.base_url}. "
        "Fast triage will be skipped."
    )
    return None
