"""Training data collection for ABX indication extraction.

Collects training examples from LLM extractions and human reviews
for future model fine-tuning. Mirrors the HAI training collector pattern.

Training data is stored as JSONL files, with each line containing:
- Input: clinical notes and antibiotic context
- Output: LLM extraction result (syndrome, confidence, red flags)
- Metadata: model used, timing, human review decision

Usage:
    from abx_indications.training_collector import ABXTrainingCollector

    collector = ABXTrainingCollector()

    # Log an extraction
    collector.log_extraction(
        candidate_id="candidate-123",
        antibiotic="ceftriaxone",
        input_notes=["..."],
        extraction=extraction_dict,
        model="qwen2.5:7b",
    )

    # Log human review
    collector.log_human_review(
        candidate_id="candidate-123",
        reviewer="asp_pharmacist_1",
        syndrome_decision="confirm_syndrome",
        confirmed_syndrome="cap",
        agent_decision="agent_appropriate",
    )

    # Export for fine-tuning
    collector.export_training_data("training_export.jsonl")
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_TRAINING_DIR = Path(__file__).parent / "data" / "training"


@dataclass
class ABXExtractionRecord:
    """Record of an ABX indication extraction for training."""

    # Identifiers
    candidate_id: str
    antibiotic: str
    patient_mrn: str | None = None

    # Input
    input_notes: list[str] = field(default_factory=list)
    note_count: int = 0
    order_date: str | None = None

    # LLM Extraction Output
    extracted_syndrome: str | None = None
    extracted_syndrome_display: str | None = None
    syndrome_category: str | None = None
    syndrome_confidence: str | None = None  # definite, probable, unclear
    therapy_intent: str | None = None  # empiric, directed, prophylaxis
    supporting_evidence: list[str] = field(default_factory=list)
    evidence_quotes: list[str] = field(default_factory=list)

    # Red flags
    likely_viral: bool = False
    asymptomatic_bacteriuria: bool = False
    indication_not_documented: bool = False
    never_appropriate: bool = False

    # Guideline matching
    guideline_disease_ids: list[str] = field(default_factory=list)
    cchmc_agent_category: str | None = None  # first_line, alternative, off_guideline

    # Model info
    model_used: str = ""
    extraction_time_ms: int = 0

    # Human review (filled in later)
    human_reviewed: bool = False
    reviewer: str | None = None
    review_timestamp: str | None = None

    # Syndrome review
    syndrome_decision: str | None = None  # confirm_syndrome, correct_syndrome, no_indication, viral_illness
    human_syndrome: str | None = None  # Corrected syndrome if different
    human_syndrome_display: str | None = None

    # Agent appropriateness review
    agent_decision: str | None = None  # agent_appropriate, agent_acceptable, agent_inappropriate
    agent_notes: str | None = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_training_example(self) -> dict:
        """Convert to training example format for fine-tuning.

        Returns dict with:
        - input: The prompt/context
        - output: The expected extraction
        - metadata: Additional context
        """
        # Use human-corrected values if available, else LLM values
        final_syndrome = self.human_syndrome or self.extracted_syndrome
        final_syndrome_display = self.human_syndrome_display or self.extracted_syndrome_display

        return {
            "input": {
                "antibiotic": self.antibiotic,
                "notes": self.input_notes,
                "note_count": self.note_count,
            },
            "output": {
                "primary_indication": final_syndrome,
                "primary_indication_display": final_syndrome_display,
                "indication_category": self.syndrome_category,
                "indication_confidence": self.syndrome_confidence,
                "therapy_intent": self.therapy_intent,
                "supporting_evidence": self.supporting_evidence,
                "red_flags": {
                    "likely_viral": self.likely_viral,
                    "asymptomatic_bacteriuria": self.asymptomatic_bacteriuria,
                    "indication_not_documented": self.indication_not_documented,
                },
            },
            "metadata": {
                "candidate_id": self.candidate_id,
                "model_used": self.model_used,
                "human_reviewed": self.human_reviewed,
                "syndrome_decision": self.syndrome_decision,
                "agent_decision": self.agent_decision,
                "was_corrected": self.human_syndrome is not None and self.human_syndrome != self.extracted_syndrome,
                "created_at": self.created_at,
            },
        }


class ABXTrainingCollector:
    """Collects training data from ABX indication extractions."""

    def __init__(self, storage_dir: Path | str | None = None):
        """Initialize the collector.

        Args:
            storage_dir: Directory for JSONL files. Uses default if None.
        """
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_TRAINING_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._records: dict[str, ABXExtractionRecord] = {}

        # Load existing records from current month's file
        self._load_current_month()

    def _get_monthly_file(self, dt: datetime | None = None) -> Path:
        """Get the JSONL file path for a given month."""
        dt = dt or datetime.now()
        return self.storage_dir / f"abx_extractions_{dt.strftime('%Y_%m')}.jsonl"

    def _load_current_month(self):
        """Load records from current month's file into memory."""
        filepath = self._get_monthly_file()
        if not filepath.exists():
            return

        try:
            with open(filepath, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        candidate_id = data.get("candidate_id")
                        if candidate_id:
                            self._records[candidate_id] = ABXExtractionRecord(**data)
            logger.info(f"Loaded {len(self._records)} ABX extraction records from {filepath}")
        except Exception as e:
            logger.warning(f"Failed to load ABX training records: {e}")

    def log_extraction(
        self,
        candidate_id: str,
        antibiotic: str,
        input_notes: list[str],
        extraction: dict,
        model: str,
        patient_mrn: str | None = None,
        order_date: str | None = None,
        extraction_time_ms: int = 0,
        cchmc_agent_category: str | None = None,
    ):
        """Log an LLM extraction for training.

        Args:
            candidate_id: Unique identifier for this case.
            antibiotic: The prescribed antibiotic.
            input_notes: Clinical notes used for extraction.
            extraction: The LLM extraction result dict.
            model: Model name used for extraction.
            patient_mrn: Patient MRN (for reference, will be anonymized).
            order_date: Date of the antibiotic order.
            extraction_time_ms: Time taken for extraction.
            cchmc_agent_category: CCHMC guideline agent category if available.
        """
        record = ABXExtractionRecord(
            candidate_id=candidate_id,
            antibiotic=antibiotic,
            patient_mrn=patient_mrn,
            input_notes=input_notes,
            note_count=len(input_notes),
            order_date=order_date,
            # Extraction results
            extracted_syndrome=extraction.get("primary_indication"),
            extracted_syndrome_display=extraction.get("primary_indication_display"),
            syndrome_category=extraction.get("indication_category"),
            syndrome_confidence=extraction.get("indication_confidence"),
            therapy_intent=extraction.get("therapy_intent"),
            supporting_evidence=extraction.get("supporting_evidence", []),
            evidence_quotes=extraction.get("evidence_quotes", []),
            # Red flags
            likely_viral=extraction.get("likely_viral", False),
            asymptomatic_bacteriuria=extraction.get("asymptomatic_bacteriuria", False),
            indication_not_documented=extraction.get("indication_not_documented", False),
            never_appropriate=extraction.get("never_appropriate", False),
            # Guideline info
            guideline_disease_ids=extraction.get("guideline_disease_ids", []),
            cchmc_agent_category=cchmc_agent_category,
            # Model info
            model_used=model,
            extraction_time_ms=extraction_time_ms,
        )

        with self._lock:
            self._records[candidate_id] = record
            self._append_to_file(record)

        logger.debug(f"Logged ABX extraction for {candidate_id}: {record.extracted_syndrome}")

    def log_human_review(
        self,
        candidate_id: str,
        reviewer: str,
        syndrome_decision: str,
        confirmed_syndrome: str | None = None,
        confirmed_syndrome_display: str | None = None,
        agent_decision: str | None = None,
        agent_notes: str | None = None,
    ):
        """Log human review of an extraction.

        Args:
            candidate_id: The candidate that was reviewed.
            reviewer: Who performed the review.
            syndrome_decision: Review decision for syndrome.
                One of: confirm_syndrome, correct_syndrome, no_indication, viral_illness
            confirmed_syndrome: The confirmed/corrected syndrome ID.
            confirmed_syndrome_display: Human-readable syndrome name.
            agent_decision: Review decision for agent appropriateness.
                One of: agent_appropriate, agent_acceptable, agent_inappropriate, None
            agent_notes: Optional notes about agent decision.
        """
        with self._lock:
            record = self._records.get(candidate_id)
            if not record:
                logger.warning(f"No extraction record found for {candidate_id}")
                return

            record.human_reviewed = True
            record.reviewer = reviewer
            record.review_timestamp = datetime.now().isoformat()
            record.syndrome_decision = syndrome_decision
            record.agent_decision = agent_decision
            record.agent_notes = agent_notes

            # Set confirmed syndrome based on decision
            if syndrome_decision == "confirm_syndrome":
                record.human_syndrome = record.extracted_syndrome
                record.human_syndrome_display = record.extracted_syndrome_display
            elif syndrome_decision == "correct_syndrome" and confirmed_syndrome:
                record.human_syndrome = confirmed_syndrome
                record.human_syndrome_display = confirmed_syndrome_display
            elif syndrome_decision == "no_indication":
                record.human_syndrome = "no_indication"
                record.human_syndrome_display = "No Documented Indication"
            elif syndrome_decision == "viral_illness":
                record.human_syndrome = "viral_illness"
                record.human_syndrome_display = "Viral Illness (Antibiotics Not Indicated)"

            # Re-write the file with updated record
            self._rewrite_file()

        logger.info(
            f"Logged human review for {candidate_id}: "
            f"syndrome={syndrome_decision}, agent={agent_decision}"
        )

    def _append_to_file(self, record: ABXExtractionRecord):
        """Append a record to the current month's file."""
        filepath = self._get_monthly_file()
        try:
            with open(filepath, "a") as f:
                f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            logger.error(f"Failed to write ABX training record: {e}")

    def _rewrite_file(self):
        """Rewrite the current month's file with all records."""
        filepath = self._get_monthly_file()
        try:
            # Get records for current month only
            current_month = datetime.now().strftime("%Y_%m")
            current_records = [
                r for r in self._records.values()
                if r.created_at.startswith(current_month.replace("_", "-"))
            ]

            with open(filepath, "w") as f:
                for record in current_records:
                    f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            logger.error(f"Failed to rewrite ABX training file: {e}")

    def get_stats(self) -> dict:
        """Get statistics on collected training data."""
        with self._lock:
            total = len(self._records)
            reviewed = sum(1 for r in self._records.values() if r.human_reviewed)
            corrected = sum(
                1 for r in self._records.values()
                if r.human_reviewed and r.human_syndrome != r.extracted_syndrome
            )

            # Syndrome distribution
            syndromes = {}
            for r in self._records.values():
                syndrome = r.human_syndrome or r.extracted_syndrome or "unknown"
                syndromes[syndrome] = syndromes.get(syndrome, 0) + 1

            # Agent decision distribution
            agent_decisions = {}
            for r in self._records.values():
                if r.agent_decision:
                    agent_decisions[r.agent_decision] = agent_decisions.get(r.agent_decision, 0) + 1

            return {
                "total_extractions": total,
                "human_reviewed": reviewed,
                "review_rate": reviewed / total if total > 0 else 0,
                "corrections": corrected,
                "correction_rate": corrected / reviewed if reviewed > 0 else 0,
                "syndrome_distribution": syndromes,
                "agent_decision_distribution": agent_decisions,
            }

    def export_training_data(
        self,
        output_path: Path | str,
        reviewed_only: bool = True,
        min_confidence: str | None = None,
    ) -> int:
        """Export training data to JSONL file for fine-tuning.

        Args:
            output_path: Path for output JSONL file.
            reviewed_only: If True, only export human-reviewed records.
            min_confidence: Minimum confidence level to include.

        Returns:
            Number of examples exported.
        """
        output_path = Path(output_path)
        confidence_order = ["definite", "probable", "unclear"]

        with self._lock:
            records = list(self._records.values())

        # Filter
        if reviewed_only:
            records = [r for r in records if r.human_reviewed]

        if min_confidence:
            min_idx = confidence_order.index(min_confidence)
            records = [
                r for r in records
                if r.syndrome_confidence in confidence_order[:min_idx + 1]
            ]

        # Export
        count = 0
        with open(output_path, "w") as f:
            for record in records:
                example = record.to_training_example()
                f.write(json.dumps(example) + "\n")
                count += 1

        logger.info(f"Exported {count} ABX training examples to {output_path}")
        return count

    def get_review_queue(self, limit: int = 50) -> list[dict]:
        """Get unreviewed extractions for human review.

        Args:
            limit: Maximum number to return.

        Returns:
            List of extraction summaries needing review.
        """
        with self._lock:
            unreviewed = [
                r for r in self._records.values()
                if not r.human_reviewed
            ]

        # Sort by creation time (oldest first)
        unreviewed.sort(key=lambda r: r.created_at)

        return [
            {
                "candidate_id": r.candidate_id,
                "antibiotic": r.antibiotic,
                "extracted_syndrome": r.extracted_syndrome,
                "extracted_syndrome_display": r.extracted_syndrome_display,
                "syndrome_confidence": r.syndrome_confidence,
                "cchmc_agent_category": r.cchmc_agent_category,
                "created_at": r.created_at,
            }
            for r in unreviewed[:limit]
        ]


# Module-level singleton
_collector: ABXTrainingCollector | None = None


def get_abx_training_collector() -> ABXTrainingCollector:
    """Get the singleton ABX training collector."""
    global _collector
    if _collector is None:
        _collector = ABXTrainingCollector()
    return _collector
