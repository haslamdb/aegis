#!/usr/bin/env python3
"""Test script for Phase 2 dosing verification implementation.

Tests:
1. Renal adjustment rules
2. Weight-based dosing rules
3. Age-based dosing rules
4. FHIR client implementation
5. Complete rules engine with all Phase 2 modules
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import PatientContext, MedicationOrder
from src.rules_engine import DosingRulesEngine
from src.rules.renal_rules import RenalAdjustmentRules
from src.rules.weight_rules import WeightBasedRules
from src.rules.age_rules import AgeBasedRules


def create_test_medication(
    drug_name: str,
    dose_value: float,
    dose_unit: str,
    interval: str,
    route: str = "IV",
) -> MedicationOrder:
    """Create a test medication order."""
    # Parse interval to frequency hours
    if "q" in interval:
        freq_hours = int(interval.replace("q", "").replace("h", ""))
    else:
        freq_hours = 24

    doses_per_day = 24 / freq_hours
    daily_dose = dose_value * doses_per_day

    return MedicationOrder(
        drug_name=drug_name,
        dose_value=dose_value,
        dose_unit=dose_unit,
        interval=interval,
        route=route,
        frequency_hours=freq_hours,
        daily_dose=daily_dose,
        daily_dose_per_kg=None,
        start_date="2026-02-07",
        order_id="TEST-001",
    )


def test_renal_rules():
    """Test renal adjustment rules."""
    print("\n" + "=" * 60)
    print("TEST 1: Renal Adjustment Rules")
    print("=" * 60)

    # Test case: Meropenem at full dose with GFR 35
    context = PatientContext(
        patient_id="TEST001",
        patient_mrn="MRN001",
        patient_name="Test Patient",
        encounter_id=None,
        age_years=65,
        weight_kg=70,
        height_cm=170,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.8,
        gfr=35,  # Moderate renal impairment
        crcl=35,
        is_on_dialysis=False,
        antimicrobials=[
            create_test_medication("meropenem", 1000, "mg", "q8h")  # Should be q12h
        ],
    )

    rules = RenalAdjustmentRules()
    flags = rules.evaluate(context)

    print(f"\nPatient: GFR {context.gfr}, meropenem 1000mg q8h")
    print(f"Flags detected: {len(flags)}")
    for flag in flags:
        print(f"\n  - {flag.severity.value.upper()}: {flag.message}")
        print(f"    Expected: {flag.expected}")
        print(f"    Actual: {flag.actual}")

    assert len(flags) > 0, "Should detect renal adjustment needed"
    print("\n✅ Renal rules test PASSED")


def test_weight_rules():
    """Test weight-based dosing rules."""
    print("\n" + "=" * 60)
    print("TEST 2: Weight-Based Dosing Rules")
    print("=" * 60)

    # Test case: Pediatric vancomycin dose too low
    context = PatientContext(
        patient_id="TEST002",
        patient_mrn="MRN002",
        patient_name="Pediatric Patient",
        encounter_id=None,
        age_years=5,
        weight_kg=20,
        height_cm=110,
        gestational_age_weeks=None,
        bsa=None,
        scr=0.5,
        gfr=90,
        crcl=90,
        is_on_dialysis=False,
        antimicrobials=[
            create_test_medication("vancomycin", 125, "mg", "q6h")  # 500 mg/day = 25 mg/kg/day (should be 40-60)
        ],
    )

    # Calculate daily dose per kg
    for med in context.antimicrobials:
        med.daily_dose_per_kg = med.daily_dose / context.weight_kg

    rules = WeightBasedRules()
    flags = rules.evaluate(context)

    print(f"\nPatient: {context.age_years} yo, {context.weight_kg} kg, vancomycin 200mg q6h")
    print(f"Daily dose: {context.antimicrobials[0].daily_dose} mg ({context.antimicrobials[0].daily_dose_per_kg:.1f} mg/kg/day)")
    print(f"Flags detected: {len(flags)}")
    for flag in flags:
        print(f"\n  - {flag.severity.value.upper()}: {flag.message}")
        print(f"    Expected: {flag.expected}")
        print(f"    Actual: {flag.actual}")

    assert len(flags) > 0, "Should detect low pediatric vancomycin dose"
    print("\n✅ Weight rules test PASSED")


def test_age_rules():
    """Test age-based dosing rules."""
    print("\n" + "=" * 60)
    print("TEST 3: Age-Based Dosing Rules")
    print("=" * 60)

    # Test case: Ceftriaxone in neonate (contraindicated)
    context = PatientContext(
        patient_id="TEST003",
        patient_mrn="MRN003",
        patient_name="Neonate Patient",
        encounter_id=None,
        age_years=0.05,  # ~18 days
        weight_kg=3.5,
        height_cm=50,
        gestational_age_weeks=38,
        bsa=None,
        scr=0.8,
        gfr=None,
        crcl=None,
        is_on_dialysis=False,
        antimicrobials=[
            create_test_medication("ceftriaxone", 100, "mg", "q24h")
        ],
    )

    rules = AgeBasedRules()
    flags = rules.evaluate(context)

    print(f"\nPatient: {context.age_years*365:.0f} days old, ceftriaxone 100mg q24h")
    print(f"Flags detected: {len(flags)}")
    for flag in flags:
        print(f"\n  - {flag.severity.value.upper()}: {flag.message}")
        print(f"    Expected: {flag.expected}")
        print(f"    Actual: {flag.actual}")

    assert len(flags) > 0, "Should detect ceftriaxone contraindication in neonate"
    print("\n✅ Age rules test PASSED")


def test_complete_rules_engine():
    """Test complete rules engine with all Phase 2 modules."""
    print("\n" + "=" * 60)
    print("TEST 4: Complete Rules Engine (All Phase 2 Rules)")
    print("=" * 60)

    # Complex test case: Elderly patient with renal impairment on multiple drugs
    context = PatientContext(
        patient_id="TEST004",
        patient_mrn="MRN004",
        patient_name="Complex Patient",
        encounter_id=None,
        age_years=78,
        weight_kg=85,
        height_cm=170,
        gestational_age_weeks=None,
        bsa=None,
        scr=2.1,
        gfr=28,  # Severe renal impairment
        crcl=28,
        is_on_dialysis=False,
        antimicrobials=[
            create_test_medication("meropenem", 1000, "mg", "q8h"),  # Should be dose-reduced
            create_test_medication("vancomycin", 1000, "mg", "q12h"),  # Needs level monitoring
            create_test_medication("gentamicin", 300, "mg", "q24h"),  # Interval may need adjustment
        ],
        indication="pneumonia",
    )

    # Calculate daily dose per kg
    for med in context.antimicrobials:
        med.daily_dose_per_kg = med.daily_dose / context.weight_kg

    engine = DosingRulesEngine()
    assessment = engine.evaluate(context)

    print(f"\nPatient: {context.age_years} yo, {context.weight_kg} kg, GFR {context.gfr}")
    print(f"Medications: {len(context.antimicrobials)}")
    for med in context.antimicrobials:
        print(f"  - {med.drug_name} {med.dose_value} {med.dose_unit} {med.interval}")
    print(f"\nAssessment ID: {assessment.assessment_id}")
    print(f"Max severity: {assessment.max_severity}")
    print(f"Total flags: {len(assessment.flags)}")

    for flag in assessment.flags:
        print(f"\n  [{flag.severity.value.upper()}] {flag.flag_type.value}")
        print(f"    Drug: {flag.drug}")
        print(f"    Message: {flag.message}")
        print(f"    Expected: {flag.expected}")
        print(f"    Actual: {flag.actual}")
        print(f"    Source: {flag.rule_source}")

    assert len(assessment.flags) > 0, "Should detect multiple dosing issues"
    assert assessment.max_severity is not None, "Should have max severity"
    print("\n✅ Complete rules engine test PASSED")


def test_fhir_calculations():
    """Test FHIR client calculation functions."""
    print("\n" + "=" * 60)
    print("TEST 5: FHIR Client Calculations")
    print("=" * 60)

    from src.fhir_client import calculate_crcl, calculate_bsa

    # Test CrCl calculation
    crcl = calculate_crcl(scr=1.5, age_years=65, weight_kg=70, sex="male")
    print(f"\nCrCl (65yo male, 70kg, SCr 1.5): {crcl:.1f} mL/min")
    assert crcl is not None and 40 < crcl < 60, f"CrCl should be ~50, got {crcl}"

    # Test BSA calculation
    bsa = calculate_bsa(height_cm=170, weight_kg=70)
    print(f"BSA (170cm, 70kg): {bsa:.2f} m²")
    assert bsa is not None and 1.7 < bsa < 1.9, f"BSA should be ~1.8, got {bsa}"

    print("\n✅ FHIR calculations test PASSED")


def main():
    """Run all Phase 2 tests."""
    print("\n" + "=" * 60)
    print("PHASE 2 DOSING VERIFICATION TEST SUITE")
    print("=" * 60)

    try:
        test_renal_rules()
        test_weight_rules()
        test_age_rules()
        test_complete_rules_engine()
        test_fhir_calculations()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nPhase 2 implementation is working correctly!")
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
