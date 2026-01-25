#!/usr/bin/env python3
"""Test script to demonstrate SSI demo patient and keyword filtering.

This script creates a mock SSI candidate with realistic clinical notes
(8 SSI-relevant + 22 irrelevant) and tests keyword filtering performance.
"""

import logging
import time
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Reduce noise from other loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def create_mock_ssi_candidate():
    """Create a mock SSI candidate for testing."""
    from hai_src.models import (
        HAICandidate,
        HAIType,
        Patient,
        CultureResult,
        CandidateStatus,
        SurgicalProcedure,
        SSICandidate,
    )
    import uuid

    candidate_id = str(uuid.uuid4())
    procedure_date = datetime.now() - timedelta(days=10)
    culture_date = datetime.now() - timedelta(days=5)

    patient = Patient(
        fhir_id="patient-demo-ssi-001",
        mrn="DEMO-SSI-001",
        name="Demo SSI Patient",
        birth_date=datetime(1966, 7, 15),
        location="4 South - Surgical Floor",
    )

    # Wound culture positive for S. aureus
    culture = CultureResult(
        fhir_id="culture-demo-ssi-001",
        collection_date=culture_date,
        organism="Staphylococcus aureus",
        is_positive=True,
    )

    # Surgical procedure (appendectomy)
    procedure = SurgicalProcedure(
        id="proc-demo-ssi-001",
        procedure_code="44970",
        procedure_name="Open Appendectomy",
        procedure_date=procedure_date,
        patient_id=patient.fhir_id,
        nhsn_category="APPY",  # NHSN category for appendectomy
        wound_class=3,  # Contaminated (perforated appendix)
        duration_minutes=90,
        asa_score=2,
        primary_surgeon="Dr. James Peterson",
        implant_used=False,
    )

    candidate = HAICandidate(
        id=candidate_id,
        hai_type=HAIType.SSI,
        patient=patient,
        culture=culture,
        meets_initial_criteria=True,
        status=CandidateStatus.PENDING,
    )

    # Create SSI-specific data and attach to candidate
    ssi_data = SSICandidate(
        candidate_id=candidate_id,
        procedure=procedure,
        days_post_op=5,  # SSI diagnosed on POD 5
        wound_culture_organism="Staphylococcus aureus",
        wound_culture_date=culture_date,
    )
    candidate._ssi_data = ssi_data  # type: ignore

    return candidate


def test_note_retrieval():
    """Test note retrieval with and without keyword filtering."""
    from hai_src.data.mock_notes import MockNoteSource
    from hai_src.notes.retriever import NoteRetriever, HAI_KEYWORDS
    from hai_src.models import HAIType

    print("\n" + "=" * 70)
    print("TEST 1: Note Retrieval and Filtering (SSI)")
    print("=" * 70)

    # Create mock note source with SSI notes
    mock_source = MockNoteSource(hai_type="ssi", include_irrelevant=True, num_irrelevant=22)
    candidate = create_mock_ssi_candidate()

    # Get all notes (no filtering)
    all_notes = mock_source.get_notes_for_patient(
        patient_id=candidate.patient.fhir_id,
        start_date=datetime.now() - timedelta(days=14),
        end_date=datetime.now() + timedelta(days=3),
    )

    print(f"\nTotal notes generated: {len(all_notes)}")
    print(f"  - SSI-relevant notes: 8")
    print(f"  - Irrelevant notes: {len(all_notes) - 8}")

    # Calculate total character count
    total_chars = sum(len(n.content) for n in all_notes)
    avg_chars = total_chars / len(all_notes) if all_notes else 0
    print(f"\nTotal content size: {total_chars:,} characters")
    print(f"Average note length: {avg_chars:,.0f} characters")

    # Show note types
    print(f"\nNote types in SSI demo:")
    note_types = {}
    for note in all_notes:
        note_types[note.note_type] = note_types.get(note.note_type, 0) + 1
    for note_type, count in sorted(note_types.items()):
        print(f"  - {note_type}: {count}")

    # Create NoteRetriever with mock source
    retriever = NoteRetriever(note_source=mock_source)

    # Test with keyword filtering
    ssi_keywords = HAI_KEYWORDS.get('ssi', [])
    print(f"\nSSI Keywords ({len(ssi_keywords)} total):")
    print(f"  Sample: {', '.join(ssi_keywords[:10])}...")

    filtered_notes = retriever.filter_by_keywords(all_notes, HAIType.SSI)
    filtered_chars = sum(len(n.content) for n in filtered_notes)

    print(f"\nAfter keyword filtering:")
    print(f"  - Notes kept: {len(filtered_notes)}")
    print(f"  - Notes filtered out: {len(all_notes) - len(filtered_notes)}")
    print(f"  - Content size: {filtered_chars:,} characters")
    print(f"  - Reduction: {100 * (1 - filtered_chars / total_chars):.1f}%")

    # Show which notes were kept
    print(f"\nNotes kept by filter:")
    for note in filtered_notes:
        print(f"  - {note.note_type}: {note.id} ({len(note.content):,} chars)")

    return all_notes, filtered_notes


def test_sample_content():
    """Show sample content from SSI notes."""
    from hai_src.data.mock_notes import MockNoteSource

    print("\n" + "=" * 70)
    print("TEST 2: Sample SSI Note Content")
    print("=" * 70)

    mock_source = MockNoteSource(hai_type="ssi", include_irrelevant=False)
    notes = mock_source.get_notes_for_patient(
        patient_id="demo-patient",
        start_date=datetime.now() - timedelta(days=14),
        end_date=datetime.now(),
    )

    print(f"\nSSI Demo Patient has {len(notes)} relevant notes:\n")

    for i, note in enumerate(notes[:3]):  # Show first 3
        print(f"--- Note {i+1}: {note.note_type} ({len(note.content):,} chars) ---")
        # Show first 500 chars
        preview = note.content[:500].strip()
        print(preview)
        print("...\n")


def test_llm_classification(use_filtering: bool = True, debug: bool = False):
    """Test LLM classification for SSI.

    Args:
        use_filtering: Whether to use keyword filtering
        debug: If True, show detailed extraction output

    Returns:
        Tuple of (classification_result, elapsed_time)
    """
    from hai_src.data.mock_notes import MockNoteSource
    from hai_src.notes.retriever import NoteRetriever
    from hai_src.classifiers import SSIClassifierV2

    print(f"\n{'=' * 70}")
    print(f"LLM Classification ({'WITH' if use_filtering else 'WITHOUT'} filtering)")
    print("=" * 70)

    # Create mock source and candidate
    mock_source = MockNoteSource(hai_type="ssi", include_irrelevant=True, num_irrelevant=22)
    candidate = create_mock_ssi_candidate()

    # Create retriever
    retriever = NoteRetriever(note_source=mock_source)

    # Get notes
    print("\nRetrieving notes...")
    start_retrieve = time.time()

    notes = retriever.get_notes_for_candidate(
        candidate,
        days_before=14,
        days_after=3,
        hai_type="ssi",
        use_keyword_filter=use_filtering,
    )

    retrieve_time = time.time() - start_retrieve
    total_chars = sum(len(n.content) for n in notes)

    print(f"  Notes retrieved: {len(notes)}")
    print(f"  Total content: {total_chars:,} characters")
    print(f"  Retrieval time: {retrieve_time:.2f}s")

    # Run LLM classification
    # Note: SSIClassifierV2 will build structured_data from candidate._ssi_data
    print("\nRunning LLM classification (this may take 60-90 seconds)...")
    classifier = SSIClassifierV2()

    start_llm = time.time()
    try:
        # Use classify_with_extraction to get detailed output
        classification, extraction, rules_result = classifier.classify_with_extraction(candidate, notes)
        llm_time = time.time() - start_llm

        print(f"\n  LLM classification completed in {llm_time:.1f}s")
        print(f"\n  Results:")
        print(f"    - Decision: {classification.decision.value}")
        print(f"    - Confidence: {classification.confidence:.2f}")
        if classification.reasoning:
            print(f"    - Reasoning: {classification.reasoning[:300]}...")

        if debug:
            print(f"\n{'=' * 70}")
            print("DEBUG: Extraction Output")
            print("=" * 70)

            # Superficial findings
            sup = extraction.superficial_findings
            print(f"\nSuperficial Findings:")
            print(f"  - purulent_drainage_superficial: {sup.purulent_drainage_superficial.value}")
            if sup.purulent_drainage_quote:
                print(f"    quote: '{sup.purulent_drainage_quote}'")
            print(f"  - organisms_from_superficial_culture: {sup.organisms_from_superficial_culture.value}")
            if sup.organism_identified:
                print(f"    organism: {sup.organism_identified}")
            print(f"  - pain_or_tenderness: {sup.pain_or_tenderness.value}")
            print(f"  - localized_swelling: {sup.localized_swelling.value}")
            print(f"  - erythema: {sup.erythema.value}")
            print(f"  - heat: {sup.heat.value}")
            print(f"  - incision_deliberately_opened: {sup.incision_deliberately_opened.value}")
            print(f"  - physician_diagnosis_superficial_ssi: {sup.physician_diagnosis_superficial_ssi.value}")
            if sup.diagnosis_quote:
                print(f"    diagnosis quote: '{sup.diagnosis_quote}'")

            # Wound assessments
            print(f"\nWound Assessments ({len(extraction.wound_assessments)} total):")
            for i, wa in enumerate(extraction.wound_assessments[:5]):  # Show first 5
                print(f"  Assessment {i+1}:")
                print(f"    - drainage_present: {wa.drainage_present.value}, type: {wa.drainage_type}")
                print(f"    - erythema_present: {wa.erythema_present.value}, extent: {wa.erythema_extent}")
                print(f"    - wound_dehisced: {wa.wound_dehisced.value}")
                print(f"    - wound_opened_deliberately: {wa.wound_opened_deliberately.value}")
                if wa.assessment_date:
                    print(f"    - date: {wa.assessment_date}")

            # General findings
            print(f"\nGeneral Findings:")
            print(f"  - fever_documented: {extraction.fever_documented.value}")
            print(f"  - leukocytosis_documented: {extraction.leukocytosis_documented.value}")
            print(f"  - antibiotics_for_wound_infection: {extraction.antibiotics_for_wound_infection.value}")
            if extraction.antibiotic_names:
                print(f"    antibiotics: {', '.join(extraction.antibiotic_names)}")
            print(f"  - ssi_suspected_by_team: {extraction.ssi_suspected_by_team.value}")
            print(f"  - clinical_team_impression: {extraction.clinical_team_impression}")

            # Rules result
            print(f"\nRules Engine Result:")
            print(f"  - classification: {rules_result.classification.value}")
            print(f"  - ssi_type: {rules_result.ssi_type}")
            print(f"  - eligibility_checks: {rules_result.eligibility_checks}")
            print(f"  - superficial_criteria_met: {rules_result.superficial_criteria_met}")
            print(f"  - deep_criteria_met: {rules_result.deep_criteria_met}")
            print(f"  - organ_space_criteria_met: {rules_result.organ_space_criteria_met}")

        return classification, llm_time

    except Exception as e:
        llm_time = time.time() - start_llm
        print(f"\n  LLM classification failed after {llm_time:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return None, llm_time


def main():
    """Run SSI demo tests."""
    print("\n" + "#" * 70)
    print("# SSI (Surgical Site Infection) Demo Patient Test")
    print("# Realistic clinical notes for wound infection case")
    print("#" * 70)

    # Test 1: Note retrieval and filtering
    all_notes, filtered_notes = test_note_retrieval()

    # Test 2: Sample content
    test_sample_content()

    # Test 3: LLM classification
    print("\n" + "#" * 70)
    print("# LLM Classification Test")
    print("#" * 70)

    result_filtered, time_filtered = test_llm_classification(use_filtering=True, debug=True)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_chars_all = sum(len(n.content) for n in all_notes)
    total_chars_filtered = sum(len(n.content) for n in filtered_notes)

    print(f"\nSSI Demo Patient:")
    print(f"  - Scenario: Post-appendectomy superficial incisional SSI")
    print(f"  - Organisms: MSSA + E. coli (polymicrobial)")
    print(f"  - Treatment: Wound vac + antibiotics")

    print(f"\nNotes:")
    print(f"  - Total available: {len(all_notes)} ({total_chars_all:,} chars)")
    print(f"  - After SSI filtering: {len(filtered_notes)} ({total_chars_filtered:,} chars)")
    print(f"  - Reduction: {100 * (1 - total_chars_filtered / total_chars_all):.1f}%")

    if result_filtered:
        print(f"\nLLM Classification:")
        print(f"  - Time: {time_filtered:.1f}s")
        print(f"  - Decision: {result_filtered.decision.value}")
        print(f"  - Confidence: {result_filtered.confidence:.2f}")


if __name__ == "__main__":
    main()
