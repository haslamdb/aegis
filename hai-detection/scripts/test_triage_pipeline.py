#!/usr/bin/env python3
"""Test the two-stage triage pipeline.

This script demonstrates the two-stage classification pipeline:
1. Fast triage with smaller model
2. Full extraction with 70B model (only if needed)

Prerequisites:
    # Pull the 8B model for triage (recommended for production)
    ollama pull llama3.1:8b

    # Or use gemma2:27b as a faster alternative to 70B
    # (already available on the system)

Usage:
    python scripts/test_triage_pipeline.py
    python scripts/test_triage_pipeline.py --triage-model gemma2:27b
    python scripts/test_triage_pipeline.py --no-triage  # Compare without triage
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hai_src.classifiers.clabsi_classifier_v2 import (
    CLABSIClassifierV2,
    ClassificationPath,
)
from hai_src.extraction.triage_extractor import TriageExtractor, TriageDecision
from hai_src.models import HAICandidate, Patient, CultureResult, DeviceInfo, ClinicalNote, HAIType
from hai_src.llm import get_profile_summary, clear_profile_history
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_test_case(scenario: str) -> tuple[HAICandidate, list[ClinicalNote]]:
    """Create a test case for the given scenario."""

    base_date = datetime.now() - timedelta(days=3)

    patient = Patient(
        fhir_id="test-patient-1",
        mrn="TEST001",
        name="Test Patient",
        location="7 South",
    )

    device = DeviceInfo(
        fhir_id="test-device-1",
        device_type="PICC",
        site="Right arm",
        insertion_date=base_date - timedelta(days=14),
    )

    if scenario == "clear_clabsi":
        # Clear CLABSI case - should NOT escalate
        culture = CultureResult(
            fhir_id="test-culture-1",
            organism="Staphylococcus aureus",
            collection_date=base_date,
            specimen_source="blood",
        )

        notes = [
            ClinicalNote(
                id="note-1",
                patient_id=patient.fhir_id,
                date=base_date,
                note_type="Progress Note",
                source="fhir",
                author="Dr. Smith",
                content="""
ASSESSMENT/PLAN:
1. CLABSI - Central line-associated bloodstream infection confirmed
   - PICC line removed yesterday, tip culture pending
   - Blood cultures growing Staph aureus, MSSA
   - Started nafcillin for line infection
   - No other source identified, CXR clear, UA negative
   - ID consulted, agrees with CLABSI diagnosis

2. Leukemia in remission - continue monitoring
"""
            ),
        ]

    elif scenario == "clear_not_clabsi":
        # Clear non-CLABSI case - should NOT escalate
        culture = CultureResult(
            fhir_id="test-culture-2",
            organism="Coagulase-negative Staphylococcus",
            collection_date=base_date,
            specimen_source="blood",
        )

        notes = [
            ClinicalNote(
                id="note-2",
                patient_id=patient.fhir_id,
                date=base_date,
                note_type="Progress Note",
                source="fhir",
                author="Dr. Jones",
                content="""
ASSESSMENT/PLAN:
1. Single positive blood culture - likely contaminant
   - CoNS in 1 of 2 bottles, skin flora
   - Patient afebrile, clinically well
   - No antibiotics started
   - Line site clean, no erythema
   - Will not treat, repeat cultures if fever develops
"""
            ),
        ]

    elif scenario == "complex_mbi":
        # Complex MBI-LCBI case - SHOULD escalate
        culture = CultureResult(
            fhir_id="test-culture-3",
            organism="Enterococcus faecium",
            collection_date=base_date,
            specimen_source="blood",
        )

        notes = [
            ClinicalNote(
                id="note-3",
                patient_id=patient.fhir_id,
                date=base_date,
                note_type="BMT Progress Note",
                source="fhir",
                author="Dr. BMT",
                content="""
ASSESSMENT/PLAN:
Day +28 post allo-SCT for AML

1. Enterococcal bacteremia
   - VRE in blood, started daptomycin
   - ANC 0, neutropenic
   - Grade 3 mucositis present, severe oral lesions
   - Could be MBI-LCBI vs true line infection
   - GI team following for possible GVHD
   - Unclear if line should come out

2. Conditioning-related toxicities - ongoing support
"""
            ),
        ]

    elif scenario == "alternate_source":
        # Secondary BSI case - SHOULD escalate
        culture = CultureResult(
            fhir_id="test-culture-4",
            organism="Escherichia coli",
            collection_date=base_date,
            specimen_source="blood",
        )

        notes = [
            ClinicalNote(
                id="note-4",
                patient_id=patient.fhir_id,
                date=base_date,
                note_type="Progress Note",
                source="fhir",
                author="Dr. Medicine",
                content="""
ASSESSMENT/PLAN:
1. E. coli bacteremia - likely urosepsis
   - Same organism in blood and urine
   - Foley catheter in place
   - Also has central line
   - Started ceftriaxone
   - Urology consulted for CAUTI workup
   - May also be line-related, unclear source
"""
            ),
        ]
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    candidate = HAICandidate(
        id=f"test-{scenario}",
        patient=patient,
        culture=culture,
        device_info=device,
        device_days_at_culture=14,
        hai_type=HAIType.CLABSI,
    )

    return candidate, notes


def test_triage_only(args):
    """Test just the triage extractor."""
    print("\n=== Testing Triage Extractor Only ===\n")

    triage = TriageExtractor(model=args.triage_model)

    # Check model availability
    if not triage.client.is_available():
        print(f"ERROR: Triage model '{args.triage_model}' not available.")
        print("Available models can be seen with: ollama list")
        print("Pull the 8B model with: ollama pull llama3.1:8b")
        return 1

    print(f"Triage model: {args.triage_model}")
    print()

    scenarios = ["clear_clabsi", "clear_not_clabsi", "complex_mbi", "alternate_source"]

    for scenario in scenarios:
        print(f"\n--- Scenario: {scenario} ---")
        candidate, notes = create_test_case(scenario)

        start = time.time()
        result = triage.extract(candidate, notes, hai_type=HAIType.CLABSI)
        elapsed = time.time() - start

        print(f"Decision: {result.decision.value}")
        print(f"Needs escalation: {result.needs_full_analysis}")
        print(f"Reasoning: {result.quick_reasoning}")
        print(f"Time: {elapsed*1000:.0f}ms")
        if result.profile:
            print(f"Tokens: in={result.profile.input_tokens} out={result.profile.output_tokens}")

    return 0


def test_full_pipeline(args):
    """Test the full two-stage pipeline."""
    print("\n=== Testing Two-Stage Pipeline ===\n")

    # Create classifier with triage enabled
    classifier = CLABSIClassifierV2(
        use_triage=not args.no_triage,
        triage_model=args.triage_model,
    )

    mode = "WITHOUT triage" if args.no_triage else f"WITH triage ({args.triage_model})"
    print(f"Mode: {mode}")
    print()

    scenarios = ["clear_clabsi", "clear_not_clabsi", "complex_mbi", "alternate_source"]

    results = []

    for scenario in scenarios:
        print(f"\n--- Scenario: {scenario} ---")
        candidate, notes = create_test_case(scenario)

        clear_profile_history()
        start = time.time()
        classification = classifier.classify(candidate, notes)
        elapsed = time.time() - start

        metrics = classifier.last_metrics

        print(f"Decision: {classification.decision.value}")
        print(f"Confidence: {classification.confidence:.2f}")
        if metrics:
            print(f"Path: {metrics.path.value}")
            if metrics.triage_ms:
                print(f"Triage time: {metrics.triage_ms}ms")
            if metrics.extraction_ms:
                print(f"Extraction time: {metrics.extraction_ms}ms")
        print(f"Total time: {elapsed*1000:.0f}ms")

        results.append({
            "scenario": scenario,
            "decision": classification.decision.value,
            "path": metrics.path.value if metrics else "unknown",
            "time_ms": int(elapsed * 1000),
            "triage_ms": metrics.triage_ms if metrics else None,
        })

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    total_time = sum(r["time_ms"] for r in results)
    triage_only = sum(1 for r in results if r["path"] == "triage_only")
    escalated = sum(1 for r in results if r["path"] == "triage_escalated")

    print(f"Total scenarios: {len(results)}")
    print(f"Fast path (triage only): {triage_only}")
    print(f"Escalated to full: {escalated}")
    print(f"Total time: {total_time}ms")

    if not args.no_triage and triage_only > 0:
        # Estimate savings (assume 60s for full extraction)
        estimated_full_time = len(results) * 60000
        print(f"Estimated time without triage: ~{estimated_full_time}ms")
        print(f"Time saved: ~{estimated_full_time - total_time}ms")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Test two-stage triage pipeline")
    parser.add_argument(
        "--triage-model", "-m",
        default="llama3.1:8b",
        help="Model for triage (default: llama3.1:8b)"
    )
    parser.add_argument(
        "--no-triage",
        action="store_true",
        help="Disable triage, use full extraction only"
    )
    parser.add_argument(
        "--triage-only",
        action="store_true",
        help="Only test triage extractor, not full pipeline"
    )

    args = parser.parse_args()

    if args.triage_only:
        return test_triage_only(args)
    else:
        return test_full_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
