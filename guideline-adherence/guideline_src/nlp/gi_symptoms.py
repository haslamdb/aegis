"""LLM-based GI symptom extraction from clinical notes.

Uses a local LLM (via Ollama) to extract GI symptom details from clinical
notes. Primary use case is C. diff testing appropriateness assessment.

Extracts:
- Stool count (number of stools in 24 hours)
- Stool consistency (liquid, loose, formed, watery)
- Symptom duration (how long symptoms have been present)
- Associated symptoms (abdominal pain, cramping, fever)
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)


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

        Criteria: >= 3 liquid/watery stools in 24 hours
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
    """Extract GI symptoms from clinical notes using LLM."""

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
            model: LLM model name (e.g., "llama3.2").
            base_url: Ollama API base URL.
        """
        self.model = model or "llama3.3:70b"
        self.base_url = base_url or "http://localhost:11434"

    def is_available(self) -> bool:
        """Check if the LLM is available."""
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            if response.status_code != 200:
                return False

            models = response.json().get("models", [])
            full_names = [m.get("name", "") for m in models]
            base_names = [name.split(":")[0] for name in full_names]

            if self.model in full_names:
                return True
            if self.model in base_names:
                return True
            if f"{self.model}:latest" in full_names:
                return True

            return False
        except Exception as e:
            logger.debug(f"LLM availability check failed: {e}")
            return False

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
        """Call the LLM API."""
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 1024,
                    "num_ctx": 4096,
                },
            },
            timeout=60,
        )

        if response.status_code != 200:
            raise Exception(f"LLM API error: {response.status_code} - {response.text}")

        result = response.json()
        response_text = result.get("message", {}).get("content", "")

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            return self._extract_json(response_text)

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

        logger.warning(f"Could not extract JSON from LLM response")
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


def get_gi_symptom_extractor() -> Optional[GISymptomExtractor]:
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


if __name__ == "__main__":
    # Test LLM availability and extraction
    logging.basicConfig(level=logging.INFO)

    extractor = GISymptomExtractor()
    if extractor.is_available():
        print(f"LLM available: {extractor.model}")

        # Test with sample notes
        test_notes = [
            """
            Chief Complaint: Diarrhea x 3 days

            HPI: 6-year-old with history of recent amoxicillin course for otitis media.
            Started having watery diarrhea 3 days ago. Reports 5-6 loose watery stools
            per day. Associated with mild cramping abdominal pain. No blood in stool.
            No fever. Taking fluids well.

            Recent Antibiotics: Amoxicillin 10 days ago for ear infection
            """,
            """
            Nursing Note 0800:
            Patient had 2 large loose stools overnight. No blood noted. Taking PO well.
            Abdomen soft, mild tenderness in LLQ. Afebrile.
            """
        ]

        result = extractor.extract(test_notes)
        print(f"\nGI Symptom Result:")
        print(f"  Stool Count (24h): {result.stool_count_24h}")
        print(f"  Consistency: {result.stool_consistency.value}")
        print(f"  Symptom Duration: {result.symptom_duration_hours} hours")
        print(f"  Has Diarrhea: {result.has_diarrhea}")
        print(f"  Has Abdominal Pain: {result.has_abdominal_pain}")
        print(f"  Has Fever: {result.has_fever}")
        print(f"  Has Bloody Stool: {result.has_bloody_stool}")
        print(f"  Meets C. diff Criteria: {result.meets_cdiff_criteria()}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Response Time: {result.response_time_ms}ms")
    else:
        print(f"LLM not available: {extractor.model}")
