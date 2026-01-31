"""Training data collection for clinical appearance extraction.

Collects training examples from LLM extractions and human reviews
for future model fine-tuning. Follows the pattern from ABX training collector.

Training data is stored as JSONL files, with each line containing:
- Input: clinical notes and patient context
- Triage output: fast 7B model results
- Full output: 70B model results (if escalated)
- Human review: clinician corrections and missed findings

Usage:
    from guideline_src.nlp.training_collector import (
        ClinicalAppearanceTrainingCollector,
        get_training_collector,
    )

    collector = get_training_collector()

    # Log an extraction
    record_id = collector.log_extraction(
        episode_id=123,
        patient_id="patient-456",
        triage_result=triage_result,
        full_result=full_result,  # Optional if not escalated
        final_appearance="well",
    )

    # Log human review
    collector.log_human_review(
        record_id=record_id,
        reviewer="dr_smith",
        appearance_decision="confirm",
        missed_findings=["lethargy"],
    )

    # Export for fine-tuning
    collector.export_training_data("training_export.jsonl")
"""

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_TRAINING_DIR = Path(__file__).parent.parent.parent / "data" / "training"


# Override reason taxonomy for clinical appearance
OVERRIDE_REASONS = {
    "llm_missed_lethargy": "LLM missed documented lethargy",
    "llm_missed_mottling": "LLM missed mottling/poor perfusion",
    "llm_missed_poor_feeding": "LLM missed poor feeding",
    "llm_missed_hypotonia": "LLM missed hypotonia/floppiness",
    "llm_missed_irritability": "LLM missed irritability/inconsolable",
    "llm_missed_toxic": "LLM missed toxic appearance",
    "llm_overinterpreted": "LLM found insignificant signs",
    "context_missing": "Important notes not available",
    "clinical_judgment": "Physician exam differs",
    "documentation_ambiguous": "Notes unclear",
    "other": "Free text required",
}

# Possible missed findings for tracking
MISSED_FINDING_OPTIONS = [
    "lethargy",
    "mottling",
    "poor_feeding",
    "hypotonia",
    "irritability",
    "inconsolable",
    "poor_perfusion",
    "delayed_cap_refill",
    "pallor",
    "cyanosis",
    "grunting",
    "retractions",
    "toxic_appearing",
    "well_appearing",
]


@dataclass
class ClinicalAppearanceExtractionRecord:
    """Record of a clinical appearance extraction for training."""

    # Identifiers
    id: str
    episode_id: int | None = None
    patient_id: str | None = None
    patient_mrn: str | None = None

    # Input
    input_notes: list[str] = field(default_factory=list)
    note_count: int = 0
    patient_age_days: int | None = None

    # Triage extraction (7B model)
    triage_model: str = ""
    triage_decision: str = ""  # clear_well, clear_ill, needs_full_analysis
    triage_escalated: bool = False
    triage_escalation_reasons: list[str] = field(default_factory=list)
    triage_confidence: str = ""
    triage_documentation_quality: str = ""
    triage_response_time_ms: int = 0

    # Full extraction (70B model, if escalated)
    full_model: str = ""
    full_extraction_done: bool = False
    full_response_time_ms: int = 0

    # Final result
    extracted_appearance: str = ""  # well, ill, toxic, unknown
    extraction_confidence: str = ""
    concerning_signs: list[str] = field(default_factory=list)
    reassuring_signs: list[str] = field(default_factory=list)
    supporting_quotes: list[str] = field(default_factory=list)

    # Human review (filled in later)
    human_reviewed: bool = False
    reviewer_id: str | None = None
    review_timestamp: str | None = None

    # Appearance decision
    appearance_decision: str | None = None  # confirm, override_well, override_ill, override_toxic
    corrected_appearance: str | None = None

    # Override details
    override_reason: str | None = None
    override_reason_text: str | None = None  # Free text for "other"
    missed_findings: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    review_notes: str | None = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str | None = None

    def to_training_example(self) -> dict:
        """Convert to training example format for fine-tuning.

        Returns dict with:
        - input: The clinical notes and context
        - output: The expected extraction (human-corrected if available)
        - metadata: Additional context about extraction
        """
        # Use human-corrected values if available, else LLM values
        final_appearance = self.corrected_appearance or self.extracted_appearance

        return {
            "input": {
                "notes": self.input_notes,
                "note_count": self.note_count,
                "patient_age_days": self.patient_age_days,
            },
            "output": {
                "appearance": final_appearance,
                "confidence": self.extraction_confidence,
                "concerning_signs": self.concerning_signs,
                "reassuring_signs": self.reassuring_signs,
            },
            "metadata": {
                "record_id": self.id,
                "episode_id": self.episode_id,
                "triage_model": self.triage_model,
                "triage_decision": self.triage_decision,
                "triage_escalated": self.triage_escalated,
                "full_model": self.full_model,
                "human_reviewed": self.human_reviewed,
                "appearance_decision": self.appearance_decision,
                "was_corrected": self.corrected_appearance is not None
                    and self.corrected_appearance != self.extracted_appearance,
                "missed_findings": self.missed_findings,
                "created_at": self.created_at,
            },
        }


class ClinicalAppearanceTrainingCollector:
    """Collects training data from clinical appearance extractions."""

    def __init__(self, storage_dir: Path | str | None = None):
        """Initialize the collector.

        Args:
            storage_dir: Directory for JSONL files. Uses default if None.
        """
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_TRAINING_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._records: dict[str, ClinicalAppearanceExtractionRecord] = {}

        # Load existing records from current month's file
        self._load_current_month()

    def _get_monthly_file(self, dt: datetime | None = None) -> Path:
        """Get the JSONL file path for a given month."""
        dt = dt or datetime.now()
        return self.storage_dir / f"clinical_appearance_{dt.strftime('%Y_%m')}.jsonl"

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
                        record_id = data.get("id")
                        if record_id:
                            self._records[record_id] = ClinicalAppearanceExtractionRecord(**data)
            logger.info(f"Loaded {len(self._records)} clinical appearance records from {filepath}")
        except Exception as e:
            logger.warning(f"Failed to load clinical appearance training records: {e}")

    def log_extraction(
        self,
        episode_id: int | None = None,
        patient_id: str | None = None,
        patient_mrn: str | None = None,
        input_notes: list[str] | None = None,
        patient_age_days: int | None = None,
        triage_result: Any | None = None,
        full_result: Any | None = None,
        final_appearance: str = "",
        final_confidence: str = "",
        concerning_signs: list[str] | None = None,
        reassuring_signs: list[str] | None = None,
        supporting_quotes: list[str] | None = None,
    ) -> str:
        """Log an LLM extraction for training.

        Args:
            episode_id: Bundle episode ID.
            patient_id: FHIR patient ID.
            patient_mrn: Patient MRN (for reference).
            input_notes: Clinical notes used for extraction.
            patient_age_days: Patient age in days.
            triage_result: AppearanceTriageResult from triage extractor.
            full_result: ClinicalImpressionResult from full extractor.
            final_appearance: Final appearance classification.
            final_confidence: Final confidence level.
            concerning_signs: List of concerning findings.
            reassuring_signs: List of reassuring findings.
            supporting_quotes: Supporting quotes from notes.

        Returns:
            Record ID for use in human review logging.
        """
        record_id = str(uuid.uuid4())[:12]

        record = ClinicalAppearanceExtractionRecord(
            id=record_id,
            episode_id=episode_id,
            patient_id=patient_id,
            patient_mrn=patient_mrn,
            input_notes=input_notes or [],
            note_count=len(input_notes) if input_notes else 0,
            patient_age_days=patient_age_days,
            extracted_appearance=final_appearance,
            extraction_confidence=final_confidence,
            concerning_signs=concerning_signs or [],
            reassuring_signs=reassuring_signs or [],
            supporting_quotes=supporting_quotes or [],
        )

        # Add triage result info
        if triage_result:
            record.triage_model = getattr(triage_result, "model_used", "")
            record.triage_decision = getattr(triage_result, "decision", None)
            if record.triage_decision:
                record.triage_decision = record.triage_decision.value if hasattr(record.triage_decision, "value") else str(record.triage_decision)
            record.triage_escalated = getattr(triage_result, "needs_escalation", False)
            record.triage_escalation_reasons = getattr(triage_result, "escalation_reasons", [])
            record.triage_confidence = getattr(triage_result, "confidence", "")
            record.triage_documentation_quality = getattr(triage_result, "documentation_quality", "")
            record.triage_response_time_ms = getattr(triage_result, "response_time_ms", 0)

        # Add full extraction info
        if full_result:
            record.full_model = getattr(full_result, "model_used", "")
            record.full_extraction_done = True
            record.full_response_time_ms = getattr(full_result, "response_time_ms", 0)

        with self._lock:
            self._records[record_id] = record
            self._append_to_file(record)

        logger.debug(f"Logged clinical appearance extraction {record_id}: {final_appearance}")
        return record_id

    def log_human_review(
        self,
        record_id: str,
        reviewer_id: str,
        appearance_decision: str,
        corrected_appearance: str | None = None,
        override_reason: str | None = None,
        override_reason_text: str | None = None,
        missed_findings: list[str] | None = None,
        false_positives: list[str] | None = None,
        review_notes: str | None = None,
    ):
        """Log human review of an extraction.

        Args:
            record_id: The extraction record that was reviewed.
            reviewer_id: Who performed the review.
            appearance_decision: Review decision.
                One of: confirm, override_well, override_ill, override_toxic
            corrected_appearance: The corrected appearance if overridden.
            override_reason: Reason code for override.
            override_reason_text: Free text reason if "other".
            missed_findings: List of findings LLM missed.
            false_positives: List of false positive findings.
            review_notes: Additional notes from reviewer.
        """
        with self._lock:
            record = self._records.get(record_id)
            if not record:
                logger.warning(f"No extraction record found for {record_id}")
                return

            record.human_reviewed = True
            record.reviewer_id = reviewer_id
            record.review_timestamp = datetime.now().isoformat()
            record.appearance_decision = appearance_decision
            record.override_reason = override_reason
            record.override_reason_text = override_reason_text
            record.missed_findings = missed_findings or []
            record.false_positives = false_positives or []
            record.review_notes = review_notes
            record.updated_at = datetime.now().isoformat()

            # Set corrected appearance based on decision
            if appearance_decision == "confirm":
                record.corrected_appearance = record.extracted_appearance
            elif appearance_decision == "override_well":
                record.corrected_appearance = "well"
            elif appearance_decision == "override_ill":
                record.corrected_appearance = "ill"
            elif appearance_decision == "override_toxic":
                record.corrected_appearance = "toxic"
            elif corrected_appearance:
                record.corrected_appearance = corrected_appearance

            # Re-write the file with updated record
            self._rewrite_file()

        logger.info(
            f"Logged human review for {record_id}: "
            f"decision={appearance_decision}, missed={missed_findings}"
        )

    def _append_to_file(self, record: ClinicalAppearanceExtractionRecord):
        """Append a record to the current month's file."""
        filepath = self._get_monthly_file()
        try:
            with open(filepath, "a") as f:
                f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            logger.error(f"Failed to write clinical appearance training record: {e}")

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
            logger.error(f"Failed to rewrite clinical appearance training file: {e}")

    def get_record(self, record_id: str) -> Optional[ClinicalAppearanceExtractionRecord]:
        """Get a specific record by ID."""
        with self._lock:
            return self._records.get(record_id)

    def get_record_by_episode(self, episode_id: int) -> Optional[ClinicalAppearanceExtractionRecord]:
        """Get record by episode ID."""
        with self._lock:
            for record in self._records.values():
                if record.episode_id == episode_id:
                    return record
            return None

    def get_stats(self) -> dict:
        """Get statistics on collected training data."""
        with self._lock:
            total = len(self._records)
            reviewed = sum(1 for r in self._records.values() if r.human_reviewed)
            corrected = sum(
                1 for r in self._records.values()
                if r.human_reviewed and r.corrected_appearance != r.extracted_appearance
            )

            # Triage stats
            triage_only = sum(1 for r in self._records.values() if not r.triage_escalated)
            triage_escalated = sum(1 for r in self._records.values() if r.triage_escalated)

            # Appearance distribution
            appearances = {}
            for r in self._records.values():
                appearance = r.corrected_appearance or r.extracted_appearance or "unknown"
                appearances[appearance] = appearances.get(appearance, 0) + 1

            # Missed findings distribution
            missed_findings_dist = {}
            for r in self._records.values():
                for finding in r.missed_findings:
                    missed_findings_dist[finding] = missed_findings_dist.get(finding, 0) + 1

            # Override reason distribution
            override_reasons = {}
            for r in self._records.values():
                if r.override_reason:
                    override_reasons[r.override_reason] = override_reasons.get(r.override_reason, 0) + 1

            # Response time stats
            triage_times = [r.triage_response_time_ms for r in self._records.values() if r.triage_response_time_ms > 0]
            full_times = [r.full_response_time_ms for r in self._records.values() if r.full_response_time_ms > 0]

            return {
                "total_extractions": total,
                "human_reviewed": reviewed,
                "review_rate": reviewed / total if total > 0 else 0,
                "corrections": corrected,
                "correction_rate": corrected / reviewed if reviewed > 0 else 0,
                "triage_stats": {
                    "triage_only": triage_only,
                    "triage_escalated": triage_escalated,
                    "fast_path_rate": triage_only / total if total > 0 else 0,
                },
                "appearance_distribution": appearances,
                "missed_findings_distribution": missed_findings_dist,
                "override_reason_distribution": override_reasons,
                "response_times": {
                    "triage_avg_ms": sum(triage_times) / len(triage_times) if triage_times else 0,
                    "full_avg_ms": sum(full_times) / len(full_times) if full_times else 0,
                },
            }

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
                "id": r.id,
                "episode_id": r.episode_id,
                "patient_id": r.patient_id,
                "extracted_appearance": r.extracted_appearance,
                "extraction_confidence": r.extraction_confidence,
                "triage_escalated": r.triage_escalated,
                "concerning_signs": r.concerning_signs,
                "reassuring_signs": r.reassuring_signs,
                "created_at": r.created_at,
            }
            for r in unreviewed[:limit]
        ]

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
        confidence_order = ["high", "medium", "low"]

        with self._lock:
            records = list(self._records.values())

        # Filter
        if reviewed_only:
            records = [r for r in records if r.human_reviewed]

        if min_confidence:
            min_confidence = min_confidence.lower()
            if min_confidence in confidence_order:
                min_idx = confidence_order.index(min_confidence)
                records = [
                    r for r in records
                    if r.extraction_confidence.lower() in confidence_order[:min_idx + 1]
                ]

        # Export
        count = 0
        with open(output_path, "w") as f:
            for record in records:
                example = record.to_training_example()
                f.write(json.dumps(example) + "\n")
                count += 1

        logger.info(f"Exported {count} clinical appearance training examples to {output_path}")
        return count


# Module-level singleton
_collector: ClinicalAppearanceTrainingCollector | None = None


def get_training_collector() -> ClinicalAppearanceTrainingCollector:
    """Get the singleton clinical appearance training collector."""
    global _collector
    if _collector is None:
        _collector = ClinicalAppearanceTrainingCollector()
    return _collector


# ============================================================================
# GUIDELINE REVIEW TRAINING DATA
# ============================================================================
# Captures human reviews of guideline adherence episodes for training


class GuidelineReviewCollector:
    """Collects guideline adherence review data for training.

    Follows the same pattern as HAI training data collection.
    """

    def __init__(self, storage_dir: Path | str | None = None):
        """Initialize the collector.

        Args:
            storage_dir: Directory for JSONL files. Uses default if None.
        """
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_TRAINING_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_monthly_file(self, dt: datetime | None = None) -> Path:
        """Get the JSONL file path for guideline reviews."""
        dt = dt or datetime.now()
        return self.storage_dir / f"guideline_reviews_{dt.strftime('%Y_%m')}.jsonl"

    def log_guideline_review(
        self,
        episode_id: int,
        llm_determination: str | None = None,
        llm_confidence: str | None = None,
        human_determination: str | None = None,
        is_override: bool = False,
        override_reason: str | None = None,
        corrections: dict | None = None,
        bundle_id: str | None = None,
        deviation_type: str | None = None,
        reviewer: str | None = None,
    ):
        """Log a guideline adherence review for training.

        Args:
            episode_id: Bundle episode ID.
            llm_determination: LLM's assessment (guideline_appropriate, guideline_deviation, etc.)
            llm_confidence: LLM's confidence level.
            human_determination: Human reviewer's decision.
            is_override: Whether the human disagreed with LLM.
            override_reason: Why the human overrode LLM.
            corrections: Specific extraction corrections.
            bundle_id: The guideline bundle being assessed.
            deviation_type: Type of deviation if applicable.
            reviewer: ID/name of the reviewer.
        """
        record = {
            "id": str(uuid.uuid4())[:12],
            "type": "guideline_adherence",
            "episode_id": episode_id,
            "bundle_id": bundle_id,
            "llm_determination": llm_determination,
            "llm_confidence": llm_confidence,
            "human_determination": human_determination,
            "is_override": is_override,
            "override_reason": override_reason,
            "deviation_type": deviation_type,
            "corrections": corrections,
            "reviewer": reviewer,
            "created_at": datetime.now().isoformat(),
        }

        filepath = self._get_monthly_file()
        try:
            with open(filepath, "a") as f:
                f.write(json.dumps(record) + "\n")
            logger.debug(f"Logged guideline review for episode {episode_id}: {human_determination}")
        except Exception as e:
            logger.error(f"Failed to log guideline review: {e}")

    def get_stats(self, days: int = 30) -> dict:
        """Get guideline review statistics.

        Args:
            days: Number of days to look back.

        Returns:
            Dict with statistics.
        """
        records = self._load_recent_records(days)

        total = len(records)
        overrides = sum(1 for r in records if r.get("is_override"))
        appropriate = sum(1 for r in records if r.get("human_determination") == "guideline_appropriate")
        deviations = sum(1 for r in records if r.get("human_determination") == "guideline_deviation")

        # Override reason distribution
        override_reasons = {}
        for r in records:
            if r.get("override_reason"):
                reason = r["override_reason"]
                override_reasons[reason] = override_reasons.get(reason, 0) + 1

        # Deviation type distribution
        deviation_types = {}
        for r in records:
            if r.get("deviation_type"):
                dtype = r["deviation_type"]
                deviation_types[dtype] = deviation_types.get(dtype, 0) + 1

        return {
            "total_reviews": total,
            "overrides": overrides,
            "override_rate": round(overrides / total * 100, 1) if total > 0 else 0,
            "appropriate": appropriate,
            "deviations": deviations,
            "override_reason_distribution": override_reasons,
            "deviation_type_distribution": deviation_types,
        }

    def _load_recent_records(self, days: int = 30) -> list[dict]:
        """Load records from recent files."""
        records = []
        cutoff = datetime.now() - timedelta(days=days)

        # Load from current and previous month files
        for month_offset in range(2):
            dt = datetime.now() - timedelta(days=month_offset * 30)
            filepath = self._get_monthly_file(dt)
            if filepath.exists():
                try:
                    with open(filepath, "r") as f:
                        for line in f:
                            if line.strip():
                                record = json.loads(line)
                                created = datetime.fromisoformat(record.get("created_at", ""))
                                if created >= cutoff:
                                    records.append(record)
                except Exception as e:
                    logger.warning(f"Failed to load guideline reviews from {filepath}: {e}")

        return records

    def export_training_data(
        self,
        output_path: Path | str,
        reviewed_only: bool = True,
    ) -> int:
        """Export guideline review data for analysis.

        Args:
            output_path: Path for output JSONL file.
            reviewed_only: If True, only export records with override info.

        Returns:
            Number of records exported.
        """
        output_path = Path(output_path)
        records = self._load_recent_records(days=365)

        if reviewed_only:
            records = [r for r in records if r.get("is_override")]

        count = 0
        with open(output_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
                count += 1

        logger.info(f"Exported {count} guideline review records to {output_path}")
        return count


# Module-level singleton for guideline review collector
_guideline_collector: GuidelineReviewCollector | None = None


def get_guideline_review_collector() -> GuidelineReviewCollector:
    """Get the singleton guideline review collector."""
    global _guideline_collector
    if _guideline_collector is None:
        _guideline_collector = GuidelineReviewCollector()
    return _guideline_collector
