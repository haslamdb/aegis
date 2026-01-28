"""LLM-based indication extraction from clinical notes.

Uses a local LLM (via Ollama) to extract antibiotic indications from
clinical notes when ICD-10 classification results in N or U.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from .config import config
from .models import IndicationExtraction, EvidenceSource

logger = logging.getLogger(__name__)

# Note types that should always be included (high-value for indication review)
HIGH_PRIORITY_NOTE_TYPES = {
    "id_consult",
    "id consult",
    "infectious disease",
    "discharge_summary",
    "discharge summary",
    "admission_note",
    "admission note",
    "h&p",
    "history and physical",
}

# Common infection-related terms for note filtering
INFECTION_KEYWORDS = {
    "infection",
    "pneumonia",
    "sepsis",
    "bacteremia",
    "meningitis",
    "cellulitis",
    "abscess",
    "uti",
    "urinary tract",
    "pyelonephritis",
    "osteomyelitis",
    "endocarditis",
    "peritonitis",
    "fever",
    "antibiotic",
    "antimicrobial",
    "culture",
    "empiric",
    "treatment",
    "started on",
    "initiated",
}


class NoteWithMetadata:
    """Clinical note with associated metadata."""

    def __init__(
        self,
        text: str,
        note_type: str | None = None,
        note_date: str | None = None,
        author: str | None = None,
        note_id: str | None = None,
    ):
        self.text = text
        self.note_type = note_type or "UNKNOWN"
        self.note_date = note_date
        self.author = author
        self.note_id = note_id

    def format_for_llm(self) -> str:
        """Format note with metadata header for LLM context."""
        header_parts = [f"[{self.note_type.upper()}"]
        if self.note_date:
            header_parts.append(f" - {self.note_date}")
        if self.author:
            header_parts.append(f" by {self.author}")
        header_parts.append("]")
        header = "".join(header_parts)
        return f"{header}\n{self.text}"


class IndicationExtractor:
    """Extract antibiotic indications from clinical notes using LLM."""

    PROMPT_VERSION = "indication_extraction_v2"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """Initialize the extractor.

        Args:
            model: LLM model name (e.g., "llama3.2"). Uses config default if None.
            base_url: Ollama API base URL. Uses config default if None.
        """
        self.model = model or config.LLM_MODEL
        self.base_url = base_url or config.LLM_BASE_URL
        self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load extraction prompt template from file."""
        prompt_path = (
            Path(__file__).parent.parent / "prompts" / f"{self.PROMPT_VERSION}.txt"
        )
        try:
            return prompt_path.read_text()
        except FileNotFoundError:
            logger.warning(f"Prompt template not found: {prompt_path}")
            return self._default_prompt_template()

    def _default_prompt_template(self) -> str:
        """Fallback prompt if file not found."""
        return """Extract antibiotic indications from these clinical notes for {antibiotic}:

{notes}

Respond with JSON containing:
- documented_indication: string or null
- supporting_quotes: list of relevant quotes
- confidence: HIGH, MEDIUM, or LOW
"""

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
            # Get full model names and base names (without tag)
            full_names = [m.get("name", "") for m in models]
            base_names = [name.split(":")[0] for name in full_names]

            # Check if our model matches (with or without tag)
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
        notes: list[str] | list[NoteWithMetadata],
        medication: str,
    ) -> IndicationExtraction:
        """Extract potential indications from notes.

        Args:
            notes: List of clinical note texts or NoteWithMetadata objects.
            medication: The antibiotic name.

        Returns:
            IndicationExtraction with findings.
        """
        start_time = time.time()

        # Convert to NoteWithMetadata if needed
        if notes and isinstance(notes[0], str):
            notes_with_meta = [NoteWithMetadata(text=n) for n in notes]
        else:
            notes_with_meta = notes

        total_count = len(notes_with_meta)

        # Filter notes by relevance
        filtered_notes = self._filter_notes(notes_with_meta, medication)
        filtered_count = len(filtered_notes)

        logger.info(
            f"Note filtering for {medication}: {filtered_count}/{total_count} notes included"
        )

        # Combine notes with metadata headers
        combined_notes = self._prepare_notes_with_metadata(filtered_notes)

        # Build prompt
        prompt = self._prompt_template.format(
            antibiotic=medication,
            notes=combined_notes,
        )

        try:
            # Call LLM
            result = self._call_llm(prompt)
            elapsed_ms = int((time.time() - start_time) * 1000)

            # Parse response
            extraction = self._parse_response(result, elapsed_ms)

            # Add note counts
            extraction.notes_filtered_count = filtered_count
            extraction.notes_total_count = total_count

            return extraction

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            elapsed_ms = int((time.time() - start_time) * 1000)

            return IndicationExtraction(
                found_indications=[],
                supporting_quotes=[],
                confidence="LOW",
                model_used=self.model,
                prompt_version=self.PROMPT_VERSION,
                notes_filtered_count=filtered_count,
                notes_total_count=total_count,
            )

    def _filter_notes(
        self,
        notes: list[NoteWithMetadata],
        medication: str,
    ) -> list[NoteWithMetadata]:
        """Filter notes to those most relevant for indication extraction.

        Always includes high-priority note types (ID consults, discharge summaries).
        For other notes, filters by medication name or infection keywords.

        Args:
            notes: List of notes with metadata.
            medication: The antibiotic name.

        Returns:
            Filtered list of relevant notes.
        """
        if not notes:
            return []

        # Build search terms from medication name
        med_lower = medication.lower()
        # Extract base drug name (e.g., "ceftriaxone" from "Ceftriaxone 1g IV")
        med_parts = med_lower.split()
        search_terms = {med_lower, med_parts[0]} if med_parts else {med_lower}

        filtered = []
        for note in notes:
            # Always include high-priority note types
            note_type_lower = (note.note_type or "").lower()
            if any(hp in note_type_lower for hp in HIGH_PRIORITY_NOTE_TYPES):
                filtered.append(note)
                continue

            # Check if note text contains relevant content
            text_lower = note.text.lower()

            # Check for medication name
            if any(term in text_lower for term in search_terms):
                filtered.append(note)
                continue

            # Check for infection keywords
            if any(kw in text_lower for kw in INFECTION_KEYWORDS):
                filtered.append(note)
                continue

        # If filtering removed everything, fall back to all notes
        if not filtered and notes:
            logger.debug("Note filtering too aggressive, including all notes")
            return notes

        return filtered

    def _prepare_notes_with_metadata(
        self,
        notes: list[NoteWithMetadata],
        max_chars: int = 24000,
    ) -> str:
        """Prepare notes with metadata headers for LLM input.

        Args:
            notes: List of notes with metadata.
            max_chars: Maximum characters to include.

        Returns:
            Combined and truncated note text with metadata headers.
        """
        # Format each note with its metadata header
        formatted = [note.format_for_llm() for note in notes]

        # Join notes with separators
        combined = "\n\n---\n\n".join(formatted)

        # Truncate if needed
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n\n[Note truncated...]"

        return combined

    def _prepare_notes(self, notes: list[str], max_chars: int = 24000) -> str:
        """Prepare notes for LLM input with truncation.

        Args:
            notes: List of note texts.
            max_chars: Maximum characters to include.

        Returns:
            Combined and truncated note text.
        """
        # Join notes with separators
        combined = "\n\n---\n\n".join(notes)

        # Truncate if needed
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
                    "temperature": 0.0,  # Deterministic
                    "num_predict": 1024,
                    "num_ctx": 8192,
                },
            },
            timeout=120,  # Increased for larger context
        )

        if response.status_code != 200:
            raise Exception(f"LLM API error: {response.status_code} - {response.text}")

        result = response.json()
        response_text = result.get("message", {}).get("content", "")

        # Parse JSON from response
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            # Try to extract JSON from response
            return self._extract_json(response_text)

    def _extract_json(self, text: str) -> dict:
        """Try to extract JSON from text that may have surrounding content.

        Args:
            text: Text that may contain JSON.

        Returns:
            Parsed JSON dict or empty dict on failure.
        """
        import re

        # First, try direct parsing (in case it's valid JSON with whitespace)
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Look for JSON object pattern - find the outermost braces
        # Handle nested objects by finding matching braces
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
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse extracted JSON: {e}")

        # Fallback: try regex for simpler pattern
        match = re.search(r"\{[^{}]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not extract JSON from LLM response (length={len(text)})")
        return {}

    def _parse_response(
        self,
        result: dict,
        elapsed_ms: int,
    ) -> IndicationExtraction:
        """Parse LLM response into IndicationExtraction.

        Args:
            result: Parsed JSON from LLM.
            elapsed_ms: Response time in milliseconds.

        Returns:
            IndicationExtraction dataclass.
        """
        # Extract found indications
        found_indications = []

        # Check documented_indication
        doc_ind = result.get("documented_indication", {})
        if doc_ind.get("found") and doc_ind.get("indication"):
            found_indications.append(doc_ind["indication"])

        # Check overall_assessment
        overall = result.get("overall_assessment", {})
        if overall.get("indication_documented") and overall.get("primary_indication"):
            if overall["primary_indication"] not in found_indications:
                found_indications.append(overall["primary_indication"])

        # Get supporting quotes
        supporting_quotes = result.get("supporting_quotes", [])
        if isinstance(supporting_quotes, str):
            supporting_quotes = [supporting_quotes]

        # Parse evidence sources
        evidence_sources = []
        raw_sources = result.get("evidence_sources", [])
        if isinstance(raw_sources, list):
            for src in raw_sources:
                if isinstance(src, dict):
                    evidence_sources.append(EvidenceSource.from_dict(src))

        # Determine confidence
        confidence = "LOW"
        if overall.get("confidence"):
            confidence = overall["confidence"].upper()
        elif doc_ind.get("confidence"):
            confidence = doc_ind["confidence"].upper()

        # Ensure confidence is valid
        if confidence not in ("HIGH", "MEDIUM", "LOW"):
            confidence = "LOW"

        return IndicationExtraction(
            found_indications=found_indications,
            supporting_quotes=supporting_quotes,
            confidence=confidence,
            model_used=self.model,
            prompt_version=self.PROMPT_VERSION,
            tokens_used=None,  # Ollama doesn't always report this
            evidence_sources=evidence_sources,
        )


def get_indication_extractor() -> IndicationExtractor | None:
    """Factory function to get configured indication extractor.

    Returns:
        IndicationExtractor if LLM is available, None otherwise.
    """
    extractor = IndicationExtractor()
    if extractor.is_available():
        return extractor

    logger.warning(
        f"LLM model {extractor.model} not available at {extractor.base_url}. "
        "Indication extraction will be skipped."
    )
    return None


def check_llm_availability() -> tuple[bool, str]:
    """Check if LLM is available for extraction.

    Returns:
        Tuple of (is_available, status_message).
    """
    extractor = IndicationExtractor()
    if extractor.is_available():
        return True, f"LLM available: {extractor.model} at {extractor.base_url}"
    return False, f"LLM not available: {extractor.model} at {extractor.base_url}"


if __name__ == "__main__":
    # Test LLM availability
    logging.basicConfig(level=logging.INFO)

    available, msg = check_llm_availability()
    print(msg)

    if available:
        extractor = IndicationExtractor()

        # Test extraction with sample notes
        test_notes = [
            """
            Assessment/Plan:
            1. Pneumonia - started on ceftriaxone for community-acquired pneumonia.
               Patient has fever, productive cough, and infiltrate on CXR.
               Will continue IV antibiotics and monitor response.
            """
        ]

        result = extractor.extract(test_notes, "Ceftriaxone")
        print(f"\nExtraction result:")
        print(f"  Found indications: {result.found_indications}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Supporting quotes: {result.supporting_quotes}")
