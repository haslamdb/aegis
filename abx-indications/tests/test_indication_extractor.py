"""Tests for the LLM-based indication extractor.

Tests taxonomy mapping, LLM extraction, and red flag detection.
"""

import sys
from pathlib import Path

# Add abx-indications to path for imports
ABX_PATH = Path(__file__).parent.parent
if str(ABX_PATH) not in sys.path:
    sys.path.insert(0, str(ABX_PATH))

# Now import using relative style (since we're in the package)
from indication_taxonomy import (
    get_indication_by_synonym,
    get_never_appropriate_indications,
    get_indications_by_category,
    IndicationCategory,
    INDICATION_TAXONOMY,
)
from indication_extractor import (
    IndicationExtractor,
    IndicationExtraction,
    INDICATION_EXTRACTION_SCHEMA,
)


def test_taxonomy_synonym_lookup():
    """Test that synonyms correctly map to canonical indications."""
    print("\n=== Testing Taxonomy Synonym Lookup ===")

    test_cases = [
        # (input_term, expected_indication_id)
        ("CAP", "cap"),
        ("community acquired pneumonia", "cap"),
        ("PNA", "cap"),
        ("UTI", "uti_simple"),
        ("pyelonephritis", "uti_complicated"),
        ("pyelo", "uti_complicated"),
        ("CLABSI", "line_infection"),
        ("septic joint", "septic_arthritis"),
        ("AOM", "acute_otitis_media"),
        ("strep throat", "strep_pharyngitis"),
        ("bronchiolitis", "bronchiolitis"),  # Never appropriate
        ("viral URI", "viral_uri"),  # Never appropriate
        ("empiric", "empiric_unknown"),
    ]

    passed = 0
    failed = 0

    for term, expected_id in test_cases:
        result = get_indication_by_synonym(term)
        if result and result.indication_id == expected_id:
            print(f"  ✓ '{term}' -> {result.indication_id}")
            passed += 1
        elif result:
            print(f"  ✗ '{term}' -> {result.indication_id} (expected {expected_id})")
            failed += 1
        else:
            print(f"  ✗ '{term}' -> None (expected {expected_id})")
            failed += 1

    print(f"\nSynonym lookup: {passed}/{passed+failed} passed")
    return failed == 0


def test_never_appropriate_indications():
    """Test that never-appropriate indications are correctly flagged."""
    print("\n=== Testing Never-Appropriate Indications ===")

    never_appropriate = get_never_appropriate_indications()
    expected_ids = {"bronchiolitis", "viral_uri", "asymptomatic_bacteriuria"}

    found_ids = {ind.indication_id for ind in never_appropriate}

    print(f"  Found {len(never_appropriate)} never-appropriate indications:")
    for ind in never_appropriate:
        print(f"    - {ind.indication_id}: {ind.display_name}")

    if found_ids == expected_ids:
        print("  ✓ All expected never-appropriate indications found")
        return True
    else:
        missing = expected_ids - found_ids
        extra = found_ids - expected_ids
        if missing:
            print(f"  ✗ Missing: {missing}")
        if extra:
            print(f"  ? Extra (may be valid): {extra}")
        return False


def test_category_lookup():
    """Test indication category lookups."""
    print("\n=== Testing Category Lookups ===")

    respiratory = get_indications_by_category(IndicationCategory.RESPIRATORY)
    urinary = get_indications_by_category(IndicationCategory.URINARY)

    print(f"  Respiratory indications: {len(respiratory)}")
    for ind in respiratory[:3]:
        print(f"    - {ind.indication_id}")

    print(f"  Urinary indications: {len(urinary)}")
    for ind in urinary[:3]:
        print(f"    - {ind.indication_id}")

    return len(respiratory) >= 5 and len(urinary) >= 3


def test_guideline_disease_mapping():
    """Test that indications map to CCHMC guideline disease IDs."""
    print("\n=== Testing Guideline Disease ID Mapping ===")

    # Indications that should have guideline mappings
    test_indications = ["cap", "uti_complicated", "febrile_neutropenia", "cellulitis"]

    all_mapped = True
    for ind_id in test_indications:
        indication = INDICATION_TAXONOMY.get(ind_id)
        if indication and indication.guideline_disease_ids:
            print(f"  ✓ {ind_id} -> {indication.guideline_disease_ids}")
        else:
            print(f"  ✗ {ind_id} has no guideline mapping")
            all_mapped = False

    return all_mapped


def test_extraction_dataclass():
    """Test IndicationExtraction dataclass."""
    print("\n=== Testing IndicationExtraction Dataclass ===")

    extraction = IndicationExtraction(
        primary_indication="cap",
        primary_indication_display="Community-Acquired Pneumonia",
        indication_category="respiratory",
        indication_confidence="definite",
        supporting_evidence=["fever x3 days", "productive cough"],
        evidence_quotes=["Started ceftriaxone for CAP"],
        therapy_intent="empiric",
        likely_viral=False,
        never_appropriate=False,
        guideline_disease_ids=["cap_infant_preschool"],
    )

    # Test to_dict
    data = extraction.to_dict()

    print(f"  Primary indication: {data['primary_indication']}")
    print(f"  Category: {data['indication_category']}")
    print(f"  Confidence: {data['indication_confidence']}")
    print(f"  Evidence: {data['supporting_evidence']}")
    print(f"  Guideline IDs: {data['guideline_disease_ids']}")

    return data["primary_indication"] == "cap"


def test_llm_extraction(notes: list[str], antibiotic: str = "ceftriaxone"):
    """Test LLM extraction with sample notes.

    Requires LLM to be available.
    """
    print("\n=== Testing LLM Extraction ===")

    try:
        extractor = IndicationExtractor()
        result = extractor.extract(
            notes=notes,
            antibiotic=antibiotic,
            order_date="2026-01-31",
        )

        print(f"  Primary indication: {result.primary_indication}")
        print(f"  Display name: {result.primary_indication_display}")
        print(f"  Category: {result.indication_category}")
        print(f"  Confidence: {result.indication_confidence}")
        print(f"  Therapy intent: {result.therapy_intent}")
        print(f"  Supporting evidence: {result.supporting_evidence[:3]}")

        if result.likely_viral:
            print("  ⚠ Red flag: Likely viral")
        if result.asymptomatic_bacteriuria:
            print("  ⚠ Red flag: Asymptomatic bacteriuria")
        if result.indication_not_documented:
            print("  ⚠ Red flag: Indication not documented")
        if result.never_appropriate:
            print("  ⚠ Red flag: Never appropriate indication")

        print(f"  Guideline disease IDs: {result.guideline_disease_ids}")
        print(f"  Extraction model: {result.extraction_model}")

        return True

    except Exception as e:
        print(f"  ✗ LLM extraction failed: {e}")
        print("  (LLM may not be available)")
        return False


# Sample clinical notes for testing
SAMPLE_NOTES_CAP = [
    """
    PROGRESS NOTE - Pediatric Medicine

    S: 8 yo M with 3 days of fever, cough, and decreased oral intake.
    Mom reports he had runny nose last week that got worse.

    O: T 39.2, HR 120, RR 28, SpO2 94% RA
    Lungs: decreased breath sounds RLL, crackles
    CXR: RLL infiltrate consistent with pneumonia
    WBC: 18,000 with left shift

    A/P:
    1. Community-acquired pneumonia - started ceftriaxone + azithromycin
       per CAP pathway. Will monitor response.
    2. Dehydration - IVF
    """,
]

SAMPLE_NOTES_UTI = [
    """
    ED NOTE

    CC: Fever and fussiness x2 days

    HPI: 6 month old F brought in for fever to 103. Mom notes
    decreased wet diapers. No vomiting, diarrhea. No URI symptoms.

    Labs: UA shows pyuria, bacteria. UCx pending.

    Assessment: Febrile UTI / likely pyelonephritis given age and fever
    Plan: Admit for IV ceftriaxone, await culture
    """,
]

SAMPLE_NOTES_VIRAL = [
    """
    URGENT CARE NOTE

    4 yo M with runny nose, cough x5 days.
    No fever. Eating well. Acting normally.

    Exam: Clear rhinorrhea, mild pharyngeal erythema.
    Lungs clear. No respiratory distress.

    Assessment: Viral upper respiratory infection
    Plan: Supportive care, return precautions

    -- Note: Parent requesting antibiotics. Explained viral illness.
       Prescribed amoxicillin "in case it turns bacterial"
    """,
]


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("INDICATION EXTRACTOR TEST SUITE")
    print("=" * 60)

    results = []

    # Unit tests (no LLM required)
    results.append(("Synonym lookup", test_taxonomy_synonym_lookup()))
    results.append(("Never-appropriate", test_never_appropriate_indications()))
    results.append(("Category lookup", test_category_lookup()))
    results.append(("Guideline mapping", test_guideline_disease_mapping()))
    results.append(("Dataclass", test_extraction_dataclass()))

    # LLM tests (require LLM to be available)
    print("\n" + "=" * 60)
    print("LLM EXTRACTION TESTS (require Ollama)")
    print("=" * 60)

    results.append(("LLM: CAP case", test_llm_extraction(SAMPLE_NOTES_CAP, "ceftriaxone")))
    results.append(("LLM: UTI case", test_llm_extraction(SAMPLE_NOTES_UTI, "ceftriaxone")))
    results.append(("LLM: Viral case", test_llm_extraction(SAMPLE_NOTES_VIRAL, "amoxicillin")))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print(f"\n{passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test indication extractor")
    parser.add_argument("--llm-only", action="store_true", help="Only run LLM tests")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM tests")
    args = parser.parse_args()

    if args.llm_only:
        test_llm_extraction(SAMPLE_NOTES_CAP, "ceftriaxone")
        test_llm_extraction(SAMPLE_NOTES_UTI, "ceftriaxone")
        test_llm_extraction(SAMPLE_NOTES_VIRAL, "amoxicillin")
    elif args.no_llm:
        test_taxonomy_synonym_lookup()
        test_never_appropriate_indications()
        test_category_lookup()
        test_guideline_disease_mapping()
        test_extraction_dataclass()
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)
