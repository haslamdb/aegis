"""AEGIS Validation Framework.

This module provides tools for validating LLM extraction workflows
against gold standard adjudicated cases.

Key components:
- Gold standard templates for each HAI type
- Validation runner for scoring extractions
- Field comparison with semantic matching
- Aggregate metrics (precision, recall, F1)

Usage:
    from validation.validation_runner import ValidationRunner

    runner = ValidationRunner(model="llama3.3:70b")
    report = runner.validate_all(
        gold_dir=Path("validation/cases/clabsi"),
        hai_type="clabsi",
    )
    print(f"Accuracy: {report.overall_accuracy:.1%}")
"""

from pathlib import Path

VALIDATION_DIR = Path(__file__).parent
CASES_DIR = VALIDATION_DIR / "cases"
TEMPLATES_DIR = VALIDATION_DIR

# HAI types supported
HAI_TYPES = ["clabsi", "cauti", "vae", "ssi", "cdi"]

# Indication extraction (separate workflow)
INDICATION_TYPES = ["indication"]

__all__ = [
    "VALIDATION_DIR",
    "CASES_DIR",
    "TEMPLATES_DIR",
    "HAI_TYPES",
    "INDICATION_TYPES",
]
