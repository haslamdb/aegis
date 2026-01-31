"""Training data collection and escalation tracking for HAI extraction.

This module collects training examples from LLM extractions for future
model fine-tuning. It also tracks escalation statistics for the two-stage
pipeline.

Training data is stored as JSONL files, with each line containing:
- Input: clinical notes and patient context
- Output: LLM extraction result
- Metadata: HAI type, model used, timing, human review

Escalation stats track:
- Rate of escalation by HAI type
- Which triggers cause escalation
- Time savings from fast path

Usage:
    from hai_src.extraction.training_collector import TrainingCollector

    collector = TrainingCollector()

    # Log an extraction
    collector.log_extraction(
        case_id="candidate-123",
        hai_type="CLABSI",
        input_notes="...",
        extraction=extraction_dict,
        model="llama3.3:70b",
        triage_result=triage,  # Optional
    )

    # Log human review
    collector.log_human_review(
        case_id="candidate-123",
        reviewer="ip_nurse_1",
        decision="HAI_CONFIRMED",
    )

    # Get escalation stats
    stats = collector.get_escalation_stats()
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Config
from ..models import HAIType

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_TRAINING_DIR = Path(__file__).parent.parent.parent / "data" / "training"


@dataclass
class ExtractionRecord:
    """A single extraction record for training data."""

    id: str
    timestamp: str
    hai_type: str
    case_id: str

    # Input data
    input_notes: str
    input_context: dict[str, Any] = field(default_factory=dict)

    # Extraction output
    extraction: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0

    # Triage info (if two-stage pipeline)
    triage_model: str | None = None
    triage_decision: str | None = None
    triage_escalated: bool | None = None
    triage_triggers: list[str] = field(default_factory=list)
    triage_latency_ms: int | None = None

    # Classification result
    classification_decision: str | None = None
    classification_confidence: float | None = None
    classification_path: str | None = None  # triage_only, triage_escalated, full_only

    # Human review (added later)
    human_reviewer: str | None = None
    human_decision: str | None = None
    human_reviewed_at: str | None = None
    human_corrections: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class EscalationStats:
    """Aggregated escalation statistics."""

    total_cases: int = 0
    escalated_cases: int = 0
    fast_path_cases: int = 0

    # By HAI type
    by_hai_type: dict[str, dict[str, int]] = field(default_factory=dict)

    # By trigger (which triggers caused escalation)
    by_trigger: dict[str, int] = field(default_factory=dict)

    # Time savings
    total_time_saved_ms: int = 0
    avg_fast_path_ms: float = 0.0
    avg_escalated_ms: float = 0.0

    @property
    def escalation_rate(self) -> float:
        """Overall escalation rate."""
        if self.total_cases == 0:
            return 0.0
        return self.escalated_cases / self.total_cases

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["escalation_rate"] = self.escalation_rate
        return d


class TrainingCollector:
    """Collects training data and tracks escalation statistics.

    Thread-safe for concurrent access from multiple classification threads.
    """

    def __init__(
        self,
        training_dir: Path | str | None = None,
        enabled: bool = True,
    ):
        """Initialize the collector.

        Args:
            training_dir: Directory for storing training data.
            enabled: If False, no data is collected (for testing).
        """
        self.training_dir = Path(training_dir or DEFAULT_TRAINING_DIR)
        self.enabled = enabled
        self._lock = threading.Lock()

        # In-memory stats (persisted periodically)
        self._stats = EscalationStats()
        self._pending_records: dict[str, ExtractionRecord] = {}

        # Ensure directory exists
        if self.enabled:
            self.training_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_file(self) -> Path:
        """Get the current month's JSONL file."""
        month = datetime.now().strftime("%Y_%m")
        return self.training_dir / f"extractions_{month}.jsonl"

    def _get_stats_file(self) -> Path:
        """Get the escalation stats file."""
        return self.training_dir / "escalation_stats.json"

    def log_extraction(
        self,
        case_id: str,
        hai_type: str | HAIType,
        input_notes: str,
        extraction: dict[str, Any],
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        input_context: dict[str, Any] | None = None,
        triage_result: Any | None = None,
        classification_decision: str | None = None,
        classification_confidence: float | None = None,
        classification_path: str | None = None,
    ) -> str:
        """Log an extraction for training data.

        Args:
            case_id: Unique case identifier.
            hai_type: Type of HAI (CLABSI, CAUTI, etc).
            input_notes: Clinical notes sent to LLM.
            extraction: Extraction result dictionary.
            model: Model used for extraction.
            tokens_in: Input token count.
            tokens_out: Output token count.
            latency_ms: Extraction latency.
            input_context: Additional context (patient info, etc).
            triage_result: TriageExtraction if two-stage pipeline.
            classification_decision: Final classification decision.
            classification_confidence: Classification confidence.
            classification_path: Pipeline path taken.

        Returns:
            Record ID for later updates (human review).
        """
        if not self.enabled:
            return ""

        import uuid
        record_id = str(uuid.uuid4())

        hai_type_str = hai_type.value if isinstance(hai_type, HAIType) else hai_type

        record = ExtractionRecord(
            id=record_id,
            timestamp=datetime.now().isoformat(),
            hai_type=hai_type_str,
            case_id=case_id,
            input_notes=input_notes,
            input_context=input_context or {},
            extraction=extraction,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            classification_decision=classification_decision,
            classification_confidence=classification_confidence,
            classification_path=classification_path,
        )

        # Add triage info if available
        if triage_result is not None:
            record.triage_model = getattr(triage_result, 'profile', None)
            if hasattr(triage_result, 'decision'):
                record.triage_decision = triage_result.decision.value
            record.triage_escalated = getattr(triage_result, 'needs_full_analysis', None)
            record.triage_triggers = self._extract_triggers(triage_result)
            if hasattr(triage_result, 'profile') and triage_result.profile:
                record.triage_latency_ms = int(triage_result.profile.total_ms)

        with self._lock:
            # Store for potential human review update
            self._pending_records[case_id] = record

            # Update escalation stats
            self._update_stats(record)

            # Write to file
            self._write_record(record)

        logger.debug(f"Logged extraction: {case_id} ({hai_type_str})")
        return record_id

    def log_human_review(
        self,
        case_id: str,
        reviewer: str,
        decision: str,
        corrections: dict[str, Any] | None = None,
    ) -> bool:
        """Log human review decision for a case.

        Args:
            case_id: Case identifier (must match previous log_extraction).
            reviewer: Reviewer identifier.
            decision: Human classification decision.
            corrections: Any corrections to the extraction.

        Returns:
            True if record was found and updated.
        """
        if not self.enabled:
            return False

        with self._lock:
            if case_id not in self._pending_records:
                logger.warning(f"No pending record for case: {case_id}")
                return False

            record = self._pending_records[case_id]
            record.human_reviewer = reviewer
            record.human_decision = decision
            record.human_reviewed_at = datetime.now().isoformat()
            record.human_corrections = corrections

            # Re-write the record (append updated version)
            self._write_record(record)

            # Remove from pending
            del self._pending_records[case_id]

        logger.debug(f"Logged human review: {case_id} -> {decision}")
        return True

    def _extract_triggers(self, triage_result: Any) -> list[str]:
        """Extract escalation triggers from triage result."""
        triggers = []

        if getattr(triage_result, 'documentation_quality', '') in ('poor', 'limited'):
            triggers.append('poor_documentation')
        if getattr(triage_result, 'alternate_source_mentioned', False):
            triggers.append('alternate_source')
        if getattr(triage_result, 'contamination_mentioned', False):
            triggers.append('contamination')
        if getattr(triage_result, 'mbi_factors_present', False):
            triggers.append('mbi_factors')
        if getattr(triage_result, 'multiple_organisms', False):
            triggers.append('multiple_organisms')
        if getattr(triage_result, 'clinical_impression_ambiguous', False):
            triggers.append('ambiguous_impression')

        return triggers

    def _update_stats(self, record: ExtractionRecord) -> None:
        """Update escalation statistics with new record."""
        self._stats.total_cases += 1

        hai_type = record.hai_type
        if hai_type not in self._stats.by_hai_type:
            self._stats.by_hai_type[hai_type] = {
                "total": 0,
                "escalated": 0,
                "fast_path": 0,
            }

        self._stats.by_hai_type[hai_type]["total"] += 1

        if record.triage_escalated is True:
            self._stats.escalated_cases += 1
            self._stats.by_hai_type[hai_type]["escalated"] += 1

            # Track triggers
            for trigger in record.triage_triggers:
                self._stats.by_trigger[trigger] = self._stats.by_trigger.get(trigger, 0) + 1

        elif record.triage_escalated is False:
            self._stats.fast_path_cases += 1
            self._stats.by_hai_type[hai_type]["fast_path"] += 1

            # Estimate time saved (assume 60s for full extraction)
            estimated_full_time = 60000
            actual_time = record.triage_latency_ms or 1000
            self._stats.total_time_saved_ms += (estimated_full_time - actual_time)

    def _write_record(self, record: ExtractionRecord) -> None:
        """Write record to JSONL file."""
        try:
            filepath = self._get_current_file()
            with open(filepath, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write training record: {e}")

    def get_escalation_stats(self) -> dict[str, Any]:
        """Get current escalation statistics.

        Returns:
            Dictionary with escalation stats.
        """
        with self._lock:
            return self._stats.to_dict()

    def save_stats(self) -> None:
        """Persist escalation stats to disk."""
        if not self.enabled:
            return

        with self._lock:
            try:
                filepath = self._get_stats_file()
                with open(filepath, "w") as f:
                    json.dump(self._stats.to_dict(), f, indent=2)
                logger.info(f"Saved escalation stats to {filepath}")
            except Exception as e:
                logger.error(f"Failed to save escalation stats: {e}")

    def load_stats(self) -> None:
        """Load escalation stats from disk."""
        if not self.enabled:
            return

        filepath = self._get_stats_file()
        if not filepath.exists():
            return

        try:
            with open(filepath) as f:
                data = json.load(f)

            self._stats = EscalationStats(
                total_cases=data.get("total_cases", 0),
                escalated_cases=data.get("escalated_cases", 0),
                fast_path_cases=data.get("fast_path_cases", 0),
                by_hai_type=data.get("by_hai_type", {}),
                by_trigger=data.get("by_trigger", {}),
                total_time_saved_ms=data.get("total_time_saved_ms", 0),
            )
            logger.info(f"Loaded escalation stats: {self._stats.total_cases} cases")
        except Exception as e:
            logger.error(f"Failed to load escalation stats: {e}")

    def get_training_examples(
        self,
        hai_type: str | None = None,
        reviewed_only: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Load training examples from stored data.

        Args:
            hai_type: Filter by HAI type (optional).
            reviewed_only: Only return human-reviewed examples.
            limit: Maximum number of examples.

        Returns:
            List of training example dictionaries.
        """
        examples = []

        # Read all JSONL files
        for filepath in sorted(self.training_dir.glob("extractions_*.jsonl")):
            try:
                with open(filepath) as f:
                    for line in f:
                        if not line.strip():
                            continue

                        record = json.loads(line)

                        # Apply filters
                        if hai_type and record.get("hai_type") != hai_type:
                            continue
                        if reviewed_only and not record.get("human_reviewer"):
                            continue

                        examples.append(record)

                        if limit and len(examples) >= limit:
                            return examples

            except Exception as e:
                logger.error(f"Failed to read {filepath}: {e}")

        return examples


# Global instance for easy access
_collector: TrainingCollector | None = None


def get_collector() -> TrainingCollector:
    """Get the global training collector instance."""
    global _collector
    if _collector is None:
        _collector = TrainingCollector()
        _collector.load_stats()
    return _collector


def get_escalation_stats() -> dict[str, Any]:
    """Convenience function to get escalation stats."""
    return get_collector().get_escalation_stats()


def log_extraction(**kwargs) -> str:
    """Convenience function to log an extraction."""
    return get_collector().log_extraction(**kwargs)


def log_human_review(**kwargs) -> bool:
    """Convenience function to log human review."""
    return get_collector().log_human_review(**kwargs)
