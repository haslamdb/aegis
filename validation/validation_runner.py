#!/usr/bin/env python3
"""AEGIS Validation Runner - Scores LLM extractions against gold standards.

This script runs LLM extractors against adjudicated gold standard cases
and computes accuracy metrics for each extraction field.

Usage:
    python validation_runner.py --hai-type clabsi --gold-dir validation/cases/clabsi/
    python validation_runner.py --hai-type all --report-only
    python validation_runner.py --summary

Output:
    - Per-field accuracy (precision, recall, F1)
    - Hallucination detection rate
    - Overall extraction quality scores
    - Detailed error analysis
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# Metrics and Scoring
# =============================================================================

@dataclass
class FieldScore:
    """Score for a single extraction field."""
    field_name: str
    expected: Any
    extracted: Any
    match: bool
    match_type: str = "exact"  # exact, partial, semantic, not_applicable
    notes: str = ""


@dataclass
class CaseScore:
    """Scores for a single validation case."""
    case_id: str
    hai_type: str
    field_scores: list[FieldScore] = field(default_factory=list)
    hallucinations_detected: list[str] = field(default_factory=list)
    hallucinations_missed: list[str] = field(default_factory=list)
    extraction_time_ms: float = 0.0
    error: str | None = None

    @property
    def accuracy(self) -> float:
        """Overall accuracy for this case."""
        if not self.field_scores:
            return 0.0
        matches = sum(1 for f in self.field_scores if f.match)
        return matches / len(self.field_scores)

    @property
    def field_count(self) -> int:
        return len(self.field_scores)

    @property
    def match_count(self) -> int:
        return sum(1 for f in self.field_scores if f.match)


@dataclass
class ValidationReport:
    """Complete validation report for a HAI type."""
    hai_type: str
    run_timestamp: str
    model_name: str
    case_scores: list[CaseScore] = field(default_factory=list)

    # Aggregate metrics
    total_cases: int = 0
    total_fields: int = 0
    total_matches: int = 0

    # Per-field metrics
    field_metrics: dict[str, dict[str, float]] = field(default_factory=dict)

    # Hallucination metrics
    hallucination_detection_rate: float = 0.0
    hallucinations_caught: int = 0
    hallucinations_total: int = 0

    @property
    def overall_accuracy(self) -> float:
        if self.total_fields == 0:
            return 0.0
        return self.total_matches / self.total_fields

    def to_dict(self) -> dict:
        return {
            "hai_type": self.hai_type,
            "run_timestamp": self.run_timestamp,
            "model_name": self.model_name,
            "summary": {
                "total_cases": self.total_cases,
                "total_fields": self.total_fields,
                "total_matches": self.total_matches,
                "overall_accuracy": round(self.overall_accuracy, 4),
                "hallucination_detection_rate": round(self.hallucination_detection_rate, 4),
            },
            "field_metrics": self.field_metrics,
            "case_details": [
                {
                    "case_id": cs.case_id,
                    "accuracy": round(cs.accuracy, 4),
                    "fields_matched": cs.match_count,
                    "fields_total": cs.field_count,
                    "hallucinations_detected": cs.hallucinations_detected,
                    "hallucinations_missed": cs.hallucinations_missed,
                    "error": cs.error,
                }
                for cs in self.case_scores
            ],
        }


# =============================================================================
# Field Comparison Logic
# =============================================================================

class FieldComparator:
    """Compares extracted values against gold standard values."""

    @staticmethod
    def compare(
        field_name: str,
        expected: Any,
        extracted: Any,
        field_type: str = "auto",
    ) -> FieldScore:
        """Compare an extracted value against expected value.

        Args:
            field_name: Name of the field being compared
            expected: Gold standard value
            extracted: LLM-extracted value
            field_type: Type hint (auto, boolean, confidence, string, list, numeric)

        Returns:
            FieldScore with match result
        """
        # Handle null/None expected (not applicable)
        if expected is None:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=True,  # null expected = not applicable, don't penalize
                match_type="not_applicable",
                notes="Expected null - field not applicable to this case",
            )

        # Auto-detect field type
        if field_type == "auto":
            field_type = FieldComparator._detect_type(expected)

        # Compare based on type
        if field_type == "boolean":
            return FieldComparator._compare_boolean(field_name, expected, extracted)
        elif field_type == "confidence":
            return FieldComparator._compare_confidence(field_name, expected, extracted)
        elif field_type == "list":
            return FieldComparator._compare_list(field_name, expected, extracted)
        elif field_type == "numeric":
            return FieldComparator._compare_numeric(field_name, expected, extracted)
        else:
            return FieldComparator._compare_string(field_name, expected, extracted)

    @staticmethod
    def _detect_type(value: Any) -> str:
        """Detect the type of a value for comparison."""
        if isinstance(value, bool):
            return "boolean"
        elif isinstance(value, (int, float)):
            return "numeric"
        elif isinstance(value, list):
            return "list"
        elif isinstance(value, str):
            # Check if it's a confidence level
            if value.lower() in ["definite", "probable", "possible", "not_found", "ruled_out"]:
                return "confidence"
            return "string"
        return "string"

    @staticmethod
    def _compare_boolean(field_name: str, expected: bool, extracted: Any) -> FieldScore:
        """Compare boolean values."""
        # Normalize extracted value
        if isinstance(extracted, str):
            extracted_bool = extracted.lower() in ["true", "yes", "1", "definite", "probable"]
        elif isinstance(extracted, (int, float)):
            extracted_bool = bool(extracted)
        else:
            extracted_bool = bool(extracted)

        match = expected == extracted_bool
        return FieldScore(
            field_name=field_name,
            expected=expected,
            extracted=extracted,
            match=match,
            match_type="exact" if match else "mismatch",
        )

    @staticmethod
    def _compare_confidence(field_name: str, expected: str, extracted: Any) -> FieldScore:
        """Compare confidence level values with semantic matching."""
        expected_norm = expected.lower().strip()

        if extracted is None:
            extracted_norm = "not_found"
        elif isinstance(extracted, str):
            extracted_norm = extracted.lower().strip()
        else:
            extracted_norm = str(extracted).lower().strip()

        # Exact match
        if expected_norm == extracted_norm:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=True,
                match_type="exact",
            )

        # Semantic match (definite ≈ probable for some purposes)
        positive_values = {"definite", "probable", "possible"}
        negative_values = {"not_found", "ruled_out", "absent", "none"}

        expected_positive = expected_norm in positive_values
        extracted_positive = extracted_norm in positive_values

        if expected_positive == extracted_positive:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=True,
                match_type="semantic",
                notes=f"Semantic match: both {'positive' if expected_positive else 'negative'}",
            )

        return FieldScore(
            field_name=field_name,
            expected=expected,
            extracted=extracted,
            match=False,
            match_type="mismatch",
        )

    @staticmethod
    def _compare_string(field_name: str, expected: str, extracted: Any) -> FieldScore:
        """Compare string values with normalization."""
        if extracted is None:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=False,
                match_type="mismatch",
                notes="Extracted value was null",
            )

        expected_norm = expected.lower().strip()
        extracted_norm = str(extracted).lower().strip()

        # Exact match after normalization
        if expected_norm == extracted_norm:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=True,
                match_type="exact",
            )

        # Partial match (expected contained in extracted or vice versa)
        if expected_norm in extracted_norm or extracted_norm in expected_norm:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=True,
                match_type="partial",
                notes="Partial string match",
            )

        return FieldScore(
            field_name=field_name,
            expected=expected,
            extracted=extracted,
            match=False,
            match_type="mismatch",
        )

    @staticmethod
    def _compare_list(field_name: str, expected: list, extracted: Any) -> FieldScore:
        """Compare list values."""
        if extracted is None:
            extracted = []
        elif not isinstance(extracted, list):
            extracted = [extracted]

        # Normalize both lists
        expected_set = {str(x).lower().strip() for x in expected}
        extracted_set = {str(x).lower().strip() for x in extracted}

        # Check overlap
        intersection = expected_set & extracted_set

        if expected_set == extracted_set:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=True,
                match_type="exact",
            )
        elif intersection:
            # Partial match
            recall = len(intersection) / len(expected_set) if expected_set else 0
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=recall >= 0.5,  # Consider match if >=50% recall
                match_type="partial",
                notes=f"Partial list match: {len(intersection)}/{len(expected_set)} items",
            )
        else:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=False,
                match_type="mismatch",
            )

    @staticmethod
    def _compare_numeric(field_name: str, expected: float, extracted: Any) -> FieldScore:
        """Compare numeric values with tolerance."""
        if extracted is None:
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=False,
                match_type="mismatch",
            )

        try:
            extracted_num = float(extracted)
        except (ValueError, TypeError):
            return FieldScore(
                field_name=field_name,
                expected=expected,
                extracted=extracted,
                match=False,
                match_type="mismatch",
                notes="Could not convert extracted value to number",
            )

        # Allow 5% tolerance for numeric comparisons
        tolerance = abs(expected) * 0.05 if expected != 0 else 0.1
        match = abs(expected - extracted_num) <= tolerance

        return FieldScore(
            field_name=field_name,
            expected=expected,
            extracted=extracted,
            match=match,
            match_type="exact" if match else "mismatch",
            notes=f"Tolerance: {tolerance:.2f}" if not match else "",
        )


# =============================================================================
# Gold Standard Case Loader
# =============================================================================

def load_gold_standard_cases(gold_dir: Path, hai_type: str) -> list[dict]:
    """Load gold standard cases from a directory.

    Args:
        gold_dir: Directory containing gold standard JSON files
        hai_type: HAI type to filter (or 'all')

    Returns:
        List of gold standard case dictionaries
    """
    cases = []
    pattern = f"*{hai_type}*.json" if hai_type != "all" else "*.json"

    for json_file in gold_dir.glob(pattern):
        if json_file.name.startswith("_"):  # Skip templates/private files
            continue
        try:
            with open(json_file) as f:
                case = json.load(f)
                cases.append(case)
                logger.info(f"Loaded case: {case.get('case_id', json_file.name)}")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse {json_file}: {e}")
        except Exception as e:
            logger.warning(f"Error loading {json_file}: {e}")

    return cases


# =============================================================================
# Extraction Field Mapping
# =============================================================================

# Maps gold standard fields to extraction output fields for each HAI type
FIELD_MAPPINGS = {
    "clabsi": {
        # Signs/symptoms
        "note_extracted_data.fever.expected_extraction": "symptoms.fever_documented",
        "note_extracted_data.hypothermia.expected_extraction": "symptoms.hypothermia_documented",
        "note_extracted_data.apnea.expected_extraction": "symptoms.apnea_documented",
        "note_extracted_data.bradycardia.expected_extraction": "symptoms.bradycardia_documented",
        "note_extracted_data.hypotension.expected_extraction": "symptoms.hypotension_documented",
        # Line assessment
        "note_extracted_data.physician_attributes_to_line.expected_extraction": "line_assessment.infection_attributed_to_line",
        "note_extracted_data.physician_treats_as_bsi.expected_extraction": "line_assessment.treated_as_bsi",
        "note_extracted_data.line_present_documented.expected_extraction": "line_assessment.line_documented",
        "note_extracted_data.line_type_from_notes.expected_extraction": "line_assessment.line_type",
        # MBI factors
        "note_extracted_data.mucositis_documented.expected_extraction": "mbi_factors.mucositis_documented",
        "note_extracted_data.diarrhea_documented.expected_extraction": "mbi_factors.diarrhea_documented",
        # Alternate sources
        "note_extracted_data.other_infection_source_documented.expected_extraction": "alternate_sources.other_source_identified",
        "note_extracted_data.other_infection_source_type.expected_extraction": "alternate_sources.source_type",
        # Treatment
        "note_extracted_data.new_antibiotic_name.expected_extraction": "treatment.antibiotic_names",
        "note_extracted_data.new_antibiotic_duration_days.expected_extraction": "treatment.duration_days",
    },
    "cauti": {
        # Symptoms
        "note_extracted_data.fever.expected_extraction": "symptoms.fever_documented",
        "note_extracted_data.suprapubic_tenderness.expected_extraction": "symptoms.suprapubic_tenderness",
        "note_extracted_data.cva_tenderness.expected_extraction": "symptoms.cva_tenderness",
        # Catheter
        "note_extracted_data.catheter_documented.expected_extraction": "catheter_status.catheter_in_place",
        # Clinical impression
        "note_extracted_data.physician_suspects_uti.expected_extraction": "uti_suspected_by_team",
        "note_extracted_data.physician_diagnoses_uti.expected_extraction": "uti_diagnosed",
        # Alternative diagnoses
        "note_extracted_data.alternative_diagnoses_mentioned.expected_extraction": "alternative_diagnoses",
    },
    "vae": {
        # Temperature
        "note_extracted_data.fever.expected_extraction": "temperature.fever_documented",
        # WBC
        "note_extracted_data.leukocytosis.expected_extraction": "wbc.leukocytosis_documented",
        # Secretions
        "note_extracted_data.purulent_secretions.expected_extraction": "secretions.purulent_secretions",
        # Antimicrobials
        "note_extracted_data.new_antimicrobials.expected_extraction": "antimicrobials[0].antimicrobial_names",
        # Ventilator
        "note_extracted_data.worsening_oxygenation.expected_extraction": "ventilator_status.worsening_oxygenation",
        # Clinical impression
        "note_extracted_data.vap_suspected_by_team.expected_extraction": "vap_suspected_by_team",
    },
    "ssi": {
        # Wound findings
        "note_extracted_data.purulent_drainage.expected_extraction": "superficial_findings.purulent_drainage_superficial",
        "note_extracted_data.erythema.expected_extraction": "superficial_findings.erythema",
        "note_extracted_data.warmth.expected_extraction": "superficial_findings.heat",
        "note_extracted_data.tenderness.expected_extraction": "superficial_findings.pain_or_tenderness",
        "note_extracted_data.incision_opened.expected_extraction": "superficial_findings.incision_deliberately_opened",
        # Physician diagnosis
        "note_extracted_data.physician_diagnosis_ssi.expected_extraction": "superficial_findings.physician_diagnosis_superficial_ssi",
        # Treatment
        "note_extracted_data.antibiotic_treatment.expected_extraction": "antibiotic_names",
    },
    "cdi": {
        # Diarrhea
        "note_extracted_data.diarrhea.expected_extraction": "diarrhea.diarrhea_documented",
        # History
        "note_extracted_data.prior_cdi_history.expected_extraction": "prior_history.prior_cdi_mentioned",
        # Risk factors
        "note_extracted_data.recent_antibiotic_use.expected_extraction": "recent_antibiotic_use",
        # Clinical impression
        "note_extracted_data.cdi_suspected_by_team.expected_extraction": "cdi_suspected_by_team",
        "note_extracted_data.cdi_diagnosed.expected_extraction": "cdi_diagnosed",
        # Treatment
        "note_extracted_data.treatment_documented.expected_extraction": "treatment.treatment_type",
    },
}


def get_nested_value(obj: dict, path: str) -> Any:
    """Get a value from a nested dictionary using dot notation.

    Supports array indexing: "items[0].name"
    """
    parts = path.replace("]", "").split(".")
    current = obj

    for part in parts:
        if current is None:
            return None

        # Handle array indexing
        if "[" in part:
            key, index = part.split("[")
            index = int(index)
            if key:
                current = current.get(key, [])
            if isinstance(current, list) and len(current) > index:
                current = current[index]
            else:
                return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None

    return current


# =============================================================================
# Validation Orchestrator
# =============================================================================

class ValidationRunner:
    """Orchestrates validation of LLM extractors against gold standards."""

    def __init__(
        self,
        extractor_factory=None,
        llm_client=None,
        model: str = "llama3.3:70b",
    ):
        """Initialize the validation runner.

        Args:
            extractor_factory: Factory function to create extractors by HAI type
            llm_client: LLM client for running extractions
            model: Model name for reporting
        """
        self.extractor_factory = extractor_factory
        self.llm_client = llm_client
        self.model = model
        self.comparator = FieldComparator()

    def validate_case(
        self,
        gold_standard: dict,
        hai_type: str,
        notes: list[str] | None = None,
    ) -> CaseScore:
        """Validate a single case against gold standard.

        Args:
            gold_standard: Gold standard case dictionary
            hai_type: HAI type (clabsi, cauti, vae, ssi, cdi)
            notes: Clinical notes (if not provided, will try to load from files)

        Returns:
            CaseScore with validation results
        """
        case_id = gold_standard.get("case_id", "unknown")
        case_score = CaseScore(case_id=case_id, hai_type=hai_type)

        # Get field mappings for this HAI type
        field_map = FIELD_MAPPINGS.get(hai_type, {})
        if not field_map:
            case_score.error = f"No field mappings defined for HAI type: {hai_type}"
            return case_score

        # If we have an extractor, run extraction
        extraction_result = None
        if self.extractor_factory and notes:
            try:
                import time
                start = time.time()
                extractor = self.extractor_factory(hai_type)
                extraction_result = extractor.extract(notes)
                case_score.extraction_time_ms = (time.time() - start) * 1000
            except Exception as e:
                case_score.error = f"Extraction failed: {e}"
                return case_score

        # Compare each field
        signs_symptoms = gold_standard.get("signs_symptoms", {})

        for gs_path, extract_path in field_map.items():
            expected = get_nested_value(signs_symptoms, gs_path)

            if extraction_result:
                extracted = get_nested_value(extraction_result, extract_path)
            else:
                extracted = None  # Will be populated when running with extractor

            field_score = self.comparator.compare(
                field_name=gs_path.split(".")[-1],
                expected=expected,
                extracted=extracted,
            )
            case_score.field_scores.append(field_score)

        # Check hallucination risks
        hallucination_risks = gold_standard.get("hallucination_risks", [])
        case_score.hallucinations_missed = hallucination_risks  # All marked as missed until extraction proves otherwise

        return case_score

    def validate_all(
        self,
        gold_dir: Path,
        hai_type: str = "all",
        notes_dir: Path | None = None,
    ) -> ValidationReport:
        """Validate all cases in a directory.

        Args:
            gold_dir: Directory containing gold standard JSON files
            hai_type: HAI type to validate (or 'all')
            notes_dir: Directory containing note files (optional)

        Returns:
            ValidationReport with aggregate metrics
        """
        report = ValidationReport(
            hai_type=hai_type,
            run_timestamp=datetime.now().isoformat(),
            model_name=self.model,
        )

        # Load cases
        cases = load_gold_standard_cases(gold_dir, hai_type)
        report.total_cases = len(cases)

        if not cases:
            logger.warning(f"No gold standard cases found in {gold_dir}")
            return report

        # Validate each case
        for case in cases:
            case_hai_type = hai_type
            if hai_type == "all":
                # Infer HAI type from case_id
                case_id = case.get("case_id", "").lower()
                for t in ["clabsi", "cauti", "vae", "ssi", "cdi"]:
                    if t in case_id:
                        case_hai_type = t
                        break

            # Load notes if available
            notes = None
            if notes_dir:
                notes = self._load_notes(case, notes_dir)

            case_score = self.validate_case(case, case_hai_type, notes)
            report.case_scores.append(case_score)

            # Aggregate metrics
            report.total_fields += case_score.field_count
            report.total_matches += case_score.match_count

        # Calculate per-field metrics
        report.field_metrics = self._calculate_field_metrics(report.case_scores)

        # Calculate hallucination metrics
        total_risks = sum(len(cs.hallucinations_missed) + len(cs.hallucinations_detected) for cs in report.case_scores)
        caught = sum(len(cs.hallucinations_detected) for cs in report.case_scores)
        report.hallucinations_total = total_risks
        report.hallucinations_caught = caught
        if total_risks > 0:
            report.hallucination_detection_rate = caught / total_risks

        return report

    def _load_notes(self, case: dict, notes_dir: Path) -> list[str]:
        """Load clinical notes for a case."""
        notes = []
        notes_files = case.get("notes_files", [])

        for note_info in notes_files:
            filename = note_info.get("filename")
            if filename:
                note_path = notes_dir / filename
                if note_path.exists():
                    notes.append(note_path.read_text())

        return notes

    def _calculate_field_metrics(self, case_scores: list[CaseScore]) -> dict:
        """Calculate per-field precision, recall, F1."""
        field_stats: dict[str, dict[str, int]] = {}

        for cs in case_scores:
            for fs in cs.field_scores:
                if fs.field_name not in field_stats:
                    field_stats[fs.field_name] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}

                stats = field_stats[fs.field_name]
                stats["total"] += 1

                if fs.match:
                    stats["tp"] += 1
                else:
                    # Simplified: count mismatches as FN
                    stats["fn"] += 1

        # Calculate metrics
        metrics = {}
        for field_name, stats in field_stats.items():
            total = stats["total"]
            tp = stats["tp"]

            accuracy = tp / total if total > 0 else 0

            metrics[field_name] = {
                "accuracy": round(accuracy, 4),
                "total_cases": total,
                "correct": tp,
            }

        return metrics


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AEGIS Validation Runner - Score LLM extractions against gold standards"
    )
    parser.add_argument(
        "--hai-type",
        choices=["clabsi", "cauti", "vae", "ssi", "cdi", "all"],
        default="all",
        help="HAI type to validate",
    )
    parser.add_argument(
        "--gold-dir",
        type=Path,
        default=Path("validation/cases"),
        help="Directory containing gold standard JSON files",
    )
    parser.add_argument(
        "--notes-dir",
        type=Path,
        help="Directory containing clinical note files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for validation report (JSON)",
    )
    parser.add_argument(
        "--model",
        default="llama3.3:70b",
        help="Model name for reporting",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary of existing validation reports",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate report structure without running extraction",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize runner (without extractor for report-only mode)
    runner = ValidationRunner(
        extractor_factory=None if args.report_only else None,  # TODO: wire up extractors
        model=args.model,
    )

    # Run validation
    report = runner.validate_all(
        gold_dir=args.gold_dir,
        hai_type=args.hai_type,
        notes_dir=args.notes_dir,
    )

    # Output report
    report_dict = report.to_dict()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report_dict, f, indent=2)
        logger.info(f"Report written to {args.output}")
    else:
        # Print to stdout
        print(json.dumps(report_dict, indent=2))

    # Print summary
    print("\n" + "=" * 60)
    print(f"VALIDATION SUMMARY - {report.hai_type.upper()}")
    print("=" * 60)
    print(f"Cases validated: {report.total_cases}")
    print(f"Total fields: {report.total_fields}")
    print(f"Correct extractions: {report.total_matches}")
    print(f"Overall accuracy: {report.overall_accuracy:.1%}")
    print(f"Hallucination detection: {report.hallucination_detection_rate:.1%}")
    print("=" * 60)

    # Return exit code based on accuracy threshold
    if report.overall_accuracy < 0.80:
        logger.warning("Accuracy below 80% threshold")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
