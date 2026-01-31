"""LLM-based clinical impression extraction from clinical notes.

Uses a local LLM (via Ollama) to extract clinical appearance and status
markers from clinical notes. Primary use case is febrile infant risk
stratification (ill-appearing vs well-appearing).

Clinical Appearance Categories:
- WELL: Well-appearing, playful, active, good eye contact, feeding well
- ILL: Ill-appearing, lethargic, irritable, poor feeding, mottled, toxic
- TOXIC: Toxic-appearing, severely ill, obtunded, shock, septic appearing
- UNKNOWN: Unable to determine from available notes

Tiered Extraction:
- Uses fast 7B model (qwen2.5:7b) for triage (~1 sec)
- Escalates to full 70B model (llama3.3:70b) only when ambiguous (~60 sec)
- Captures training data for future fine-tuning
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .triage_extractor import ClinicalAppearanceTriageExtractor, AppearanceTriageResult
    from .training_collector import ClinicalAppearanceTrainingCollector

logger = logging.getLogger(__name__)


class ClinicalAppearance(Enum):
    """Clinical appearance classification."""
    WELL = "well_appearing"
    ILL = "ill_appearing"
    TOXIC = "toxic_appearing"
    UNKNOWN = "unknown"


@dataclass
class ClinicalImpressionResult:
    """Result of clinical impression extraction."""
    appearance: ClinicalAppearance
    confidence: str  # HIGH, MEDIUM, LOW
    supporting_findings: list[str] = field(default_factory=list)
    concerning_signs: list[str] = field(default_factory=list)
    reassuring_signs: list[str] = field(default_factory=list)
    supporting_quotes: list[str] = field(default_factory=list)
    model_used: str = ""
    response_time_ms: int = 0

    def is_high_risk(self) -> bool:
        """Return True if clinical appearance suggests high risk."""
        return self.appearance in (ClinicalAppearance.ILL, ClinicalAppearance.TOXIC)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "appearance": self.appearance.value,
            "confidence": self.confidence,
            "is_high_risk": self.is_high_risk(),
            "supporting_findings": self.supporting_findings,
            "concerning_signs": self.concerning_signs,
            "reassuring_signs": self.reassuring_signs,
            "supporting_quotes": self.supporting_quotes,
            "model_used": self.model_used,
            "response_time_ms": self.response_time_ms,
        }


class ClinicalImpressionExtractor:
    """Extract clinical impression/appearance from clinical notes using LLM."""

    PROMPT_VERSION = "clinical_impression_v1"

    # Default prompt template
    DEFAULT_PROMPT = """You are a clinical decision support system analyzing pediatric clinical notes.

Analyze the following clinical notes and determine the patient's clinical appearance status.

Focus on identifying:
1. Overall appearance: well-appearing, ill-appearing, or toxic-appearing
2. Activity level: active, playful, lethargic, listless, irritable
3. Feeding/interaction: feeding well, poor feeding, no eye contact, inconsolable
4. Perfusion: good color, mottled, pale, cyanotic, delayed cap refill
5. Mental status: alert, drowsy, difficult to arouse, obtunded

CLINICAL NOTES:
{notes}

Respond with JSON in this exact format:
{{
    "appearance": "well_appearing" | "ill_appearing" | "toxic_appearing" | "unknown",
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "concerning_signs": ["list of concerning findings from the notes"],
    "reassuring_signs": ["list of reassuring findings from the notes"],
    "supporting_quotes": ["exact quotes from notes that support your assessment"]
}}

Definitions:
- well_appearing: Alert, active, good eye contact, feeding normally, good color/perfusion
- ill_appearing: Lethargic, irritable, poor feeding, decreased activity, mottled, fussy but consolable
- toxic_appearing: Severely ill, obtunded, inconsolable, poor perfusion, septic appearance, shock

If the notes do not contain enough information about clinical appearance, return "unknown" with LOW confidence."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """Initialize the extractor.

        Args:
            model: LLM model name (e.g., "llama3.2"). Uses default if None.
            base_url: Ollama API base URL. Uses default if None.
        """
        self.model = model or "llama3.3:70b"
        self.base_url = base_url or "http://localhost:11434"

    def is_available(self) -> bool:
        """Check if the LLM is available.

        Returns:
            True if the LLM can be reached and model is available.
        """
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

    def extract(
        self,
        notes: list[str],
        patient_context: Optional[dict] = None,
    ) -> ClinicalImpressionResult:
        """Extract clinical impression from notes.

        Args:
            notes: List of clinical note texts.
            patient_context: Optional context (age, chief complaint, etc.)

        Returns:
            ClinicalImpressionResult with assessment.
        """
        start_time = time.time()

        # Combine notes with truncation
        combined_notes = self._prepare_notes(notes)

        if not combined_notes.strip():
            return ClinicalImpressionResult(
                appearance=ClinicalAppearance.UNKNOWN,
                confidence="LOW",
                model_used=self.model,
                response_time_ms=0,
            )

        # Build prompt
        prompt = self.DEFAULT_PROMPT.format(notes=combined_notes)

        try:
            result = self._call_llm(prompt)
            elapsed_ms = int((time.time() - start_time) * 1000)
            return self._parse_response(result, elapsed_ms)

        except Exception as e:
            logger.error(f"Clinical impression extraction failed: {e}")
            elapsed_ms = int((time.time() - start_time) * 1000)

            return ClinicalImpressionResult(
                appearance=ClinicalAppearance.UNKNOWN,
                confidence="LOW",
                model_used=self.model,
                response_time_ms=elapsed_ms,
            )

    def _prepare_notes(self, notes: list[str], max_chars: int = 16000) -> str:
        """Prepare notes for LLM input with truncation.

        Args:
            notes: List of note texts.
            max_chars: Maximum characters to include.

        Returns:
            Combined and truncated note text.
        """
        combined = "\n\n---\n\n".join(notes)

        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n\n[Note truncated...]"

        return combined

    def _call_llm(self, prompt: str) -> dict:
        """Call the LLM API.

        Args:
            prompt: The prompt to send.

        Returns:
            Parsed JSON response.

        Raises:
            Exception on API or parsing errors.
        """
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
                    "num_ctx": 8192,
                },
            },
            timeout=120,
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
        """Try to extract JSON from text that may have surrounding content."""
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

        logger.warning(f"Could not extract JSON from LLM response")
        return {}

    def _parse_response(
        self,
        result: dict,
        elapsed_ms: int,
    ) -> ClinicalImpressionResult:
        """Parse LLM response into ClinicalImpressionResult.

        Args:
            result: Parsed JSON from LLM.
            elapsed_ms: Response time in milliseconds.

        Returns:
            ClinicalImpressionResult dataclass.
        """
        # Parse appearance
        appearance_str = result.get("appearance", "unknown").lower()
        appearance_map = {
            "well_appearing": ClinicalAppearance.WELL,
            "well-appearing": ClinicalAppearance.WELL,
            "well": ClinicalAppearance.WELL,
            "ill_appearing": ClinicalAppearance.ILL,
            "ill-appearing": ClinicalAppearance.ILL,
            "ill": ClinicalAppearance.ILL,
            "toxic_appearing": ClinicalAppearance.TOXIC,
            "toxic-appearing": ClinicalAppearance.TOXIC,
            "toxic": ClinicalAppearance.TOXIC,
        }
        appearance = appearance_map.get(appearance_str, ClinicalAppearance.UNKNOWN)

        # Parse confidence
        confidence = result.get("confidence", "LOW").upper()
        if confidence not in ("HIGH", "MEDIUM", "LOW"):
            confidence = "LOW"

        # Parse lists
        concerning = result.get("concerning_signs", [])
        if isinstance(concerning, str):
            concerning = [concerning]

        reassuring = result.get("reassuring_signs", [])
        if isinstance(reassuring, str):
            reassuring = [reassuring]

        quotes = result.get("supporting_quotes", [])
        if isinstance(quotes, str):
            quotes = [quotes]

        # Combine all findings
        findings = concerning + reassuring

        return ClinicalImpressionResult(
            appearance=appearance,
            confidence=confidence,
            supporting_findings=findings,
            concerning_signs=concerning,
            reassuring_signs=reassuring,
            supporting_quotes=quotes,
            model_used=self.model,
            response_time_ms=elapsed_ms,
        )


def get_clinical_impression_extractor() -> Optional[ClinicalImpressionExtractor]:
    """Factory function to get configured clinical impression extractor.

    Returns:
        ClinicalImpressionExtractor if LLM is available, None otherwise.
    """
    extractor = ClinicalImpressionExtractor()
    if extractor.is_available():
        return extractor

    logger.warning(
        f"LLM model {extractor.model} not available at {extractor.base_url}. "
        "Clinical impression extraction will be skipped."
    )
    return None


def check_llm_availability() -> tuple[bool, str]:
    """Check if LLM is available for clinical impression extraction.

    Returns:
        Tuple of (is_available, status_message).
    """
    extractor = ClinicalImpressionExtractor()
    if extractor.is_available():
        return True, f"LLM available: {extractor.model} at {extractor.base_url}"
    return False, f"LLM not available: {extractor.model} at {extractor.base_url}"


class TieredClinicalImpressionExtractor:
    """Tiered clinical impression extractor with fast triage and full analysis.

    Uses a two-stage approach:
    1. Fast triage with 7B model (~1 sec) - handles clear cases
    2. Full analysis with 70B model (~60 sec) - handles ambiguous cases

    This provides 40-60% fast-path resolution while maintaining accuracy.
    """

    def __init__(
        self,
        use_triage: bool = True,
        collect_training_data: bool = True,
        triage_model: str | None = None,
        full_model: str | None = None,
    ):
        """Initialize the tiered extractor.

        Args:
            use_triage: Whether to use fast triage (set False to always use full model).
            collect_training_data: Whether to log extractions for training.
            triage_model: Model for fast triage. Defaults to qwen2.5:7b.
            full_model: Model for full analysis. Defaults to llama3.3:70b.
        """
        self._use_triage = use_triage
        self._collect_training_data = collect_training_data

        # Initialize extractors
        self._triage_extractor: Optional["ClinicalAppearanceTriageExtractor"] = None
        self._full_extractor: Optional[ClinicalImpressionExtractor] = None
        self._training_collector: Optional["ClinicalAppearanceTrainingCollector"] = None

        # Lazy initialization of triage extractor
        if use_triage:
            try:
                from .triage_extractor import ClinicalAppearanceTriageExtractor
                self._triage_extractor = ClinicalAppearanceTriageExtractor(model=triage_model)
                if not self._triage_extractor.is_available():
                    logger.warning(
                        f"Triage model not available, falling back to full model only"
                    )
                    self._triage_extractor = None
            except ImportError:
                logger.warning("Triage extractor not available")

        # Initialize full extractor
        self._full_extractor = ClinicalImpressionExtractor(model=full_model)

        # Initialize training collector
        if collect_training_data:
            try:
                from .training_collector import get_training_collector
                self._training_collector = get_training_collector()
            except ImportError:
                logger.warning("Training collector not available")

    def is_available(self) -> bool:
        """Check if the extractor is available (at least full model)."""
        return self._full_extractor is not None and self._full_extractor.is_available()

    def extract(
        self,
        notes: list[str],
        episode_id: int | None = None,
        patient_id: str | None = None,
        patient_mrn: str | None = None,
        patient_age_days: int | None = None,
        patient_context: Optional[dict] = None,
    ) -> ClinicalImpressionResult:
        """Extract clinical impression using tiered approach.

        Args:
            notes: List of clinical note texts.
            episode_id: Bundle episode ID for training data.
            patient_id: Patient ID for training data.
            patient_mrn: Patient MRN for training data.
            patient_age_days: Patient age in days for context.
            patient_context: Optional additional context.

        Returns:
            ClinicalImpressionResult with assessment.
        """
        triage_result: Optional["AppearanceTriageResult"] = None
        full_result: Optional[ClinicalImpressionResult] = None
        used_fast_path = False

        # Stage 1: Fast triage (if enabled and available)
        if self._use_triage and self._triage_extractor:
            try:
                from .triage_extractor import TriageDecision
                triage_result = self._triage_extractor.extract(notes, patient_context)

                if not triage_result.needs_escalation:
                    # Fast path - convert triage to full result
                    used_fast_path = True
                    result = self._triage_to_result(triage_result)

                    # Log training data
                    if self._training_collector:
                        self._log_extraction(
                            notes=notes,
                            episode_id=episode_id,
                            patient_id=patient_id,
                            patient_mrn=patient_mrn,
                            patient_age_days=patient_age_days,
                            triage_result=triage_result,
                            full_result=None,
                            final_result=result,
                        )

                    logger.info(
                        f"Fast path: {result.appearance.value} "
                        f"({triage_result.response_time_ms}ms)"
                    )
                    return result

                logger.info(
                    f"Escalating to full model: {triage_result.escalation_reasons}"
                )

            except Exception as e:
                logger.warning(f"Triage failed, falling back to full model: {e}")

        # Stage 2: Full extraction (if triage skipped or escalated)
        if self._full_extractor:
            full_result = self._full_extractor.extract(notes, patient_context)

            # Log training data
            if self._training_collector:
                self._log_extraction(
                    notes=notes,
                    episode_id=episode_id,
                    patient_id=patient_id,
                    patient_mrn=patient_mrn,
                    patient_age_days=patient_age_days,
                    triage_result=triage_result,
                    full_result=full_result,
                    final_result=full_result,
                )

            return full_result

        # Fallback if no extractor available
        return ClinicalImpressionResult(
            appearance=ClinicalAppearance.UNKNOWN,
            confidence="LOW",
            model_used="none",
            response_time_ms=0,
        )

    def _triage_to_result(
        self,
        triage: "AppearanceTriageResult",
    ) -> ClinicalImpressionResult:
        """Convert triage result to full ClinicalImpressionResult.

        Args:
            triage: Triage result from fast model.

        Returns:
            ClinicalImpressionResult compatible with existing code.
        """
        # Map triage appearance to ClinicalAppearance enum
        appearance_map = {
            "well": ClinicalAppearance.WELL,
            "ill": ClinicalAppearance.ILL,
            "toxic": ClinicalAppearance.TOXIC,
            "unclear": ClinicalAppearance.UNKNOWN,
        }
        appearance = appearance_map.get(
            triage.preliminary_appearance.lower(),
            ClinicalAppearance.UNKNOWN,
        )

        # Build findings lists from triage signals
        concerning_signs = []
        reassuring_signs = []

        if triage.lethargy_mentioned:
            concerning_signs.append("Lethargy documented")
        if triage.mottling_mentioned:
            concerning_signs.append("Mottling documented")
        if triage.poor_feeding_mentioned:
            concerning_signs.append("Poor feeding documented")
        if triage.toxic_appearing_mentioned:
            concerning_signs.append("Toxic appearance documented")

        if triage.well_appearing_mentioned:
            reassuring_signs.append("Well-appearing documented")

        # Add count-based info
        if triage.concerning_signs_count > 0:
            concerning_signs.append(
                f"{triage.concerning_signs_count} concerning sign(s) identified"
            )
        if triage.reassuring_signs_count > 0:
            reassuring_signs.append(
                f"{triage.reassuring_signs_count} reassuring sign(s) identified"
            )

        return ClinicalImpressionResult(
            appearance=appearance,
            confidence=triage.confidence.upper(),
            supporting_findings=concerning_signs + reassuring_signs,
            concerning_signs=concerning_signs,
            reassuring_signs=reassuring_signs,
            supporting_quotes=triage.key_quotes,
            model_used=f"{triage.model_used} (triage)",
            response_time_ms=triage.response_time_ms,
        )

    def _log_extraction(
        self,
        notes: list[str],
        episode_id: int | None,
        patient_id: str | None,
        patient_mrn: str | None,
        patient_age_days: int | None,
        triage_result: Optional["AppearanceTriageResult"],
        full_result: Optional[ClinicalImpressionResult],
        final_result: ClinicalImpressionResult,
    ):
        """Log extraction to training collector."""
        if not self._training_collector:
            return

        try:
            self._training_collector.log_extraction(
                episode_id=episode_id,
                patient_id=patient_id,
                patient_mrn=patient_mrn,
                input_notes=notes,
                patient_age_days=patient_age_days,
                triage_result=triage_result,
                full_result=full_result,
                final_appearance=final_result.appearance.value,
                final_confidence=final_result.confidence,
                concerning_signs=final_result.concerning_signs,
                reassuring_signs=final_result.reassuring_signs,
                supporting_quotes=final_result.supporting_quotes,
            )
        except Exception as e:
            logger.warning(f"Failed to log training data: {e}")


# Module-level singleton for tiered extractor
_tiered_extractor: Optional[TieredClinicalImpressionExtractor] = None


def get_tiered_clinical_impression_extractor(
    use_triage: bool = True,
    collect_training_data: bool = True,
) -> Optional[TieredClinicalImpressionExtractor]:
    """Factory function to get configured tiered clinical impression extractor.

    Args:
        use_triage: Whether to use fast triage model.
        collect_training_data: Whether to collect training data.

    Returns:
        TieredClinicalImpressionExtractor if LLM is available, None otherwise.
    """
    global _tiered_extractor

    if _tiered_extractor is None:
        extractor = TieredClinicalImpressionExtractor(
            use_triage=use_triage,
            collect_training_data=collect_training_data,
        )
        if extractor.is_available():
            _tiered_extractor = extractor
        else:
            logger.warning(
                "LLM not available for tiered clinical impression extraction"
            )
            return None

    return _tiered_extractor


if __name__ == "__main__":
    # Test LLM availability and extraction
    logging.basicConfig(level=logging.INFO)

    available, msg = check_llm_availability()
    print(msg)

    if available:
        extractor = ClinicalImpressionExtractor()

        # Test with sample notes
        test_notes = [
            """
            Chief Complaint: Fever

            HPI: 3-week-old male with fever to 38.5C at home.
            Parents note he has been more sleepy than usual and not feeding as well.

            Physical Exam:
            General: Infant appears lethargic, decreased responsiveness to stimulation
            Skin: Mottled appearance on extremities
            HEENT: Fontanelle flat, no discharge
            Lungs: Clear
            CV: Tachycardic, delayed cap refill ~3 seconds
            Abdomen: Soft, non-tender
            Neuro: Hypotonic, poor suck reflex

            Assessment: Febrile neonate, ill-appearing with concerning exam findings
            """,
            """
            Nursing Note:
            Baby difficult to arouse for feeds. Taking only 10-15ml formula before
            falling back asleep. Parents at bedside, concerned about decreased activity.
            Color pale with mottling noted to lower extremities.
            """
        ]

        result = extractor.extract(test_notes)
        print(f"\nClinical Impression Result:")
        print(f"  Appearance: {result.appearance.value}")
        print(f"  Confidence: {result.confidence}")
        print(f"  High Risk: {result.is_high_risk()}")
        print(f"  Concerning Signs: {result.concerning_signs}")
        print(f"  Reassuring Signs: {result.reassuring_signs}")
        print(f"  Supporting Quotes: {result.supporting_quotes}")
        print(f"  Response Time: {result.response_time_ms}ms")
