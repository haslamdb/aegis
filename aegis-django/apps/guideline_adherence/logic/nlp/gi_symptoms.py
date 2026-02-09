"""LLM-based GI symptom extraction from clinical notes.

Uses a local LLM (via Ollama) to extract GI symptom details from clinical
notes. Primary use case is C. diff testing appropriateness assessment.

Extracts:
- Stool count (number of stools in 24 hours)
- Stool consistency (liquid, loose, formed, watery)
- Symptom duration (how long symptoms have been present)
- Associated symptoms (abdominal pain, cramping, fever)

Adapted from guideline-adherence/guideline_src/nlp/gi_symptoms.py (395 lines).
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


class StoolConsistency(Enum):
    """Stool consistency classification."""
    LIQUID = "liquid"
    WATERY = "watery"
    LOOSE = "loose"
    SOFT = "soft"
    FORMED = "formed"
    UNKNOWN = "unknown"


@dataclass
class GISymptomResult:
    """Result of GI symptom extraction."""
    stool_count_24h: Optional[int] = None  # Number of stools in past 24h
    stool_consistency: StoolConsistency = StoolConsistency.UNKNOWN
    symptom_duration_hours: Optional[float] = None  # Duration of symptoms
    has_diarrhea: bool = False
    has_abdominal_pain: bool = False
    has_cramping: bool = False
    has_fever: bool = False
    has_bloody_stool: bool = False
    confidence: str = "LOW"  # HIGH, MEDIUM, LOW
    supporting_quotes: list[str] = field(default_factory=list)
    model_used: str = ""
    response_time_ms: int = 0

    def meets_cdiff_criteria(self) -> bool:
        """Check if symptoms meet C. diff testing criteria.

        Criteria: >= 3 liquid/watery/loose stools in 24 hours.
        """
        if self.stool_count_24h is None:
            return False
        if self.stool_count_24h < 3:
            return False
        return self.stool_consistency in (
            StoolConsistency.LIQUID,
            StoolConsistency.WATERY,
            StoolConsistency.LOOSE,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "stool_count_24h": self.stool_count_24h,
            "stool_consistency": self.stool_consistency.value,
            "symptom_duration_hours": self.symptom_duration_hours,
            "has_diarrhea": self.has_diarrhea,
            "has_abdominal_pain": self.has_abdominal_pain,
            "has_cramping": self.has_cramping,
            "has_fever": self.has_fever,
            "has_bloody_stool": self.has_bloody_stool,
            "meets_cdiff_criteria": self.meets_cdiff_criteria(),
            "confidence": self.confidence,
            "supporting_quotes": self.supporting_quotes,
            "model_used": self.model_used,
            "response_time_ms": self.response_time_ms,
        }


class GISymptomExtractor:
    """Extract GI symptoms from clinical notes using LLM.

    Uses OllamaClient from HAI Detection for LLM inference. The triage
    model (qwen2.5:7b) is used by default for speed since GI symptom
    extraction is relatively straightforward compared to clinical
    appearance assessment.
    """

    PROMPT_VERSION = "gi_symptoms_v1"

    DEFAULT_PROMPT = """You are a clinical decision support system analyzing clinical notes for GI symptoms.

Analyze the following clinical notes and extract information about GI symptoms, focusing on:
1. Number of stools in the past 24 hours
2. Stool consistency (liquid, watery, loose, soft, formed)
3. Duration of symptoms (when did diarrhea/GI symptoms start)
4. Associated symptoms (abdominal pain, cramping, fever, blood in stool)

CLINICAL NOTES:
{notes}

Respond with JSON in this exact format:
{{
    "stool_count_24h": <number or null if not documented>,
    "stool_consistency": "liquid" | "watery" | "loose" | "soft" | "formed" | "unknown",
    "symptom_duration_hours": <number of hours or null if not documented>,
    "has_diarrhea": true | false,
    "has_abdominal_pain": true | false,
    "has_cramping": true | false,
    "has_fever": true | false,
    "has_bloody_stool": true | false,
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "supporting_quotes": ["exact quotes from notes that support your findings"]
}}

Guidelines:
- Count stools in past 24 hours based on nursing documentation or patient/parent report
- If notes say "multiple" or "frequent" without a number, estimate based on context
- Duration: Convert "x days" to hours (1 day = 24 hours)
- For consistency, use: liquid > watery > loose > soft > formed
- If the notes don't contain GI symptom information, return nulls with LOW confidence"""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """Initialize the extractor.

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
            timeout=60,
            num_ctx=4096,
        )

    def is_available(self) -> bool:
        """Check if the LLM is available."""
        return self._client.is_available()

    def extract(self, notes: list[str]) -> GISymptomResult:
        """Extract GI symptoms from notes.

        Args:
            notes: List of clinical note texts.

        Returns:
            GISymptomResult with extracted information.
        """
        start_time = time.time()

        combined_notes = self._prepare_notes(notes)

        if not combined_notes.strip():
            return GISymptomResult(
                model_used=self.model,
                response_time_ms=0,
            )

        prompt = self.DEFAULT_PROMPT.format(notes=combined_notes)

        try:
            result = self._call_llm(prompt)
            elapsed_ms = int((time.time() - start_time) * 1000)
            return self._parse_response(result, elapsed_ms)

        except Exception as e:
            logger.error(f"GI symptom extraction failed: {e}")
            elapsed_ms = int((time.time() - start_time) * 1000)

            return GISymptomResult(
                confidence="LOW",
                model_used=self.model,
                response_time_ms=elapsed_ms,
            )

    def _prepare_notes(self, notes: list[str], max_chars: int = 12000) -> str:
        """Prepare notes for LLM input with truncation."""
        combined = "\n\n---\n\n".join(notes)

        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n\n[Note truncated...]"

        return combined

    def _call_llm(self, prompt: str) -> dict:
        """Call the LLM via OllamaClient."""
        try:
            result = self._client.generate_structured(
                prompt=prompt,
                output_schema={
                    "type": "object",
                    "properties": {
                        "stool_count_24h": {"type": ["integer", "null"]},
                        "stool_consistency": {"type": "string"},
                        "symptom_duration_hours": {"type": ["number", "null"]},
                        "has_diarrhea": {"type": "boolean"},
                        "has_abdominal_pain": {"type": "boolean"},
                        "has_cramping": {"type": "boolean"},
                        "has_fever": {"type": "boolean"},
                        "has_bloody_stool": {"type": "boolean"},
                        "confidence": {"type": "string"},
                        "supporting_quotes": {"type": "array", "items": {"type": "string"}},
                    },
                },
                temperature=0.0,
                profile_context="gi_symptom_extraction",
            )
            return result
        except ValueError:
            # JSON parse failed; try unstructured fallback
            logger.warning("Structured GI extraction failed, trying unstructured")
            response = self._client.generate(
                prompt=prompt,
                temperature=0.0,
                max_tokens=1024,
                profile_context="gi_symptom_extraction_fallback",
            )
            return self._extract_json(response.content)

    def _extract_json(self, text: str) -> dict:
        """Try to extract JSON from text."""
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

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

        logger.warning("Could not extract JSON from LLM response")
        return {}

    def _parse_response(
        self,
        result: dict,
        elapsed_ms: int,
    ) -> GISymptomResult:
        """Parse LLM response into GISymptomResult."""
        # Parse stool count
        stool_count = result.get("stool_count_24h")
        if stool_count is not None:
            try:
                stool_count = int(stool_count)
            except (ValueError, TypeError):
                stool_count = None

        # Parse consistency
        consistency_str = result.get("stool_consistency", "unknown").lower()
        consistency_map = {
            "liquid": StoolConsistency.LIQUID,
            "watery": StoolConsistency.WATERY,
            "loose": StoolConsistency.LOOSE,
            "soft": StoolConsistency.SOFT,
            "formed": StoolConsistency.FORMED,
        }
        consistency = consistency_map.get(consistency_str, StoolConsistency.UNKNOWN)

        # Parse symptom duration
        duration = result.get("symptom_duration_hours")
        if duration is not None:
            try:
                duration = float(duration)
            except (ValueError, TypeError):
                duration = None

        # Parse boolean symptoms
        has_diarrhea = bool(result.get("has_diarrhea", False))
        has_abdominal_pain = bool(result.get("has_abdominal_pain", False))
        has_cramping = bool(result.get("has_cramping", False))
        has_fever = bool(result.get("has_fever", False))
        has_bloody_stool = bool(result.get("has_bloody_stool", False))

        # Parse confidence
        confidence = result.get("confidence", "LOW").upper()
        if confidence not in ("HIGH", "MEDIUM", "LOW"):
            confidence = "LOW"

        # Parse quotes
        quotes = result.get("supporting_quotes", [])
        if isinstance(quotes, str):
            quotes = [quotes]

        return GISymptomResult(
            stool_count_24h=stool_count,
            stool_consistency=consistency,
            symptom_duration_hours=duration,
            has_diarrhea=has_diarrhea,
            has_abdominal_pain=has_abdominal_pain,
            has_cramping=has_cramping,
            has_fever=has_fever,
            has_bloody_stool=has_bloody_stool,
            confidence=confidence,
            supporting_quotes=quotes,
            model_used=self.model,
            response_time_ms=elapsed_ms,
        )


def get_gi_symptom_extractor() -> GISymptomExtractor | None:
    """Factory function to get configured GI symptom extractor.

    Returns:
        GISymptomExtractor if LLM is available, None otherwise.
    """
    extractor = GISymptomExtractor()
    if extractor.is_available():
        return extractor

    logger.warning(
        f"LLM model {extractor.model} not available at {extractor.base_url}. "
        "GI symptom extraction will be skipped."
    )
    return None
