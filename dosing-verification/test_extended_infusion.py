"""Tests for extended infusion rules."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.models import PatientContext, MedicationOrder
from src.rules.extended_infusion_rules import (
    ExtendedInfusionRules,
    get_infusion_duration,
)
from common.dosing_verification import DoseAlertSeverity, DoseFlagType


def test_get_infusion_duration():
    """Test getting infusion durations from medication orders."""
    # Test case 1: Standard 30-minute infusion
    med1 = MedicationOrder(
        drug_name="piperacillin-tazobactam",
        dose_value=4.5,
        dose_unit="g",
        interval="q6h",
        route="IV",
        frequency_hours=6,
        daily_dose=18,
        daily_dose_per_kg=None,
        start_date="2024-01-01",
        order_id="ORD-1",
        infusion_duration_minutes=30,
    )
    assert get_infusion_duration(med1, default_minutes=30) == 30

    # Test case 2: Extended 3-hour infusion
    med2 = MedicationOrder(
        drug_name="meropenem",
        dose_value=2,
        dose_unit="g",
        interval="q8h",
        route="IV",
        frequency_hours=8,
        daily_dose=6,
        daily_dose_per_kg=None,
        start_date="2024-01-01",
        order_id="ORD-2",
        infusion_duration_minutes=180,
    )
    assert get_infusion_duration(med2, default_minutes=30) == 180

    # Test case 3: Continuous infusion (9999 sentinel value)
    med3 = MedicationOrder(
        drug_name="nafcillin",
        dose_value=12,
        dose_unit="g",
        interval="daily",
        route="IV",
        frequency_hours=24,
        daily_dose=12,
        daily_dose_per_kg=None,
        start_date="2024-01-01",
        order_id="ORD-3",
        infusion_duration_minutes=9999,
    )
    assert get_infusion_duration(med3, default_minutes=30) == 9999

    # Test case 4: No infusion duration specified - use default
    med4 = MedicationOrder(
        drug_name="cefepime",
        dose_value=2,
        dose_unit="g",
        interval="q8h",
        route="IV",
        frequency_hours=8,
        daily_dose=6,
        daily_dose_per_kg=None,
        start_date="2024-01-01",
        order_id="ORD-4",
        infusion_duration_minutes=None,
    )
    assert get_infusion_duration(med4, default_minutes=30) == 30

    print("✓ All infusion duration tests passed")


def test_pipetazo_standard_infusion():
    """Test that standard 30-min pip-tazo infusion is flagged for optimization."""
    rules = ExtendedInfusionRules()

    # Patient with severe sepsis
    context = PatientContext(
        patient_id="PT-001",
        patient_mrn="123456",
        patient_name="Test Patient",
        encounter_id="ENC-001",
        age_years=65,
        weight_kg=80,
        height_cm=175,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.0,
        gfr=60,
        crcl=65,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="piperacillin-tazobactam",
                dose_value=4.5,
                dose_unit="g",
                interval="q6h",
                route="IV",
                frequency_hours=6,
                daily_dose=18,
                daily_dose_per_kg=None,
                start_date="2024-01-01T08:00:00Z",
                order_id="ORD-001",
                infusion_duration_minutes=30,
            ),
        ],
        indication="severe sepsis",
        indication_confidence=0.9,
        indication_source="LLM",
        co_medications=[],
        allergies=[],
    )

    flags = rules.evaluate(context)

    assert len(flags) == 1
    flag = flags[0]
    assert flag.flag_type == DoseFlagType.EXTENDED_INFUSION_CANDIDATE
    assert flag.severity == DoseAlertSeverity.HIGH  # High risk condition
    assert "extended infusion" in flag.message.lower()
    assert flag.details["current_infusion_min"] == 30
    assert flag.details["recommended_infusion_min"] == 240  # 4 hours

    print("✓ Pip-tazo standard infusion test passed")


def test_meropenem_extended_already():
    """Test that meropenem already on extended infusion is not flagged."""
    rules = ExtendedInfusionRules()

    context = PatientContext(
        patient_id="PT-002",
        patient_mrn="234567",
        patient_name="Test Patient 2",
        encounter_id="ENC-002",
        age_years=55,
        weight_kg=70,
        height_cm=170,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.2,
        gfr=55,
        crcl=58,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="meropenem",
                dose_value=2,
                dose_unit="g",
                interval="q8h",
                route="IV",
                frequency_hours=8,
                daily_dose=6,
                daily_dose_per_kg=None,
                start_date="2024-01-01T08:00:00Z",
                order_id="ORD-002",
                infusion_duration_minutes=180,  # Already extended
            ),
        ],
        indication="Pseudomonas aeruginosa pneumonia",
        indication_confidence=0.95,
        indication_source="Culture",
        co_medications=[],
        allergies=[],
    )

    flags = rules.evaluate(context)

    # Should not flag - already on extended infusion
    assert len(flags) == 0

    print("✓ Meropenem extended infusion test passed")


def test_continuous_infusion():
    """Test that continuous infusion is not flagged."""
    rules = ExtendedInfusionRules()

    context = PatientContext(
        patient_id="PT-003",
        patient_mrn="345678",
        patient_name="Test Patient 3",
        encounter_id="ENC-003",
        age_years=45,
        weight_kg=75,
        height_cm=172,
        gestational_age_weeks=None,
        bsa=None,
        scr=0.9,
        gfr=85,
        crcl=90,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="nafcillin",
                dose_value=12,
                dose_unit="g",
                interval="daily",
                route="IV",
                frequency_hours=24,
                daily_dose=12,
                daily_dose_per_kg=None,
                start_date="2024-01-01T08:00:00Z",
                order_id="ORD-003",
                infusion_duration_minutes=9999,  # Continuous
            ),
        ],
        indication="MSSA bacteremia",
        indication_confidence=0.95,
        indication_source="Blood culture",
        co_medications=[],
        allergies=[],
    )

    flags = rules.evaluate(context)

    # Should not flag - already on continuous infusion
    assert len(flags) == 0

    print("✓ Continuous infusion test passed")


def test_cefepime_pseudomonas():
    """Test cefepime for Pseudomonas gets flagged for extended infusion."""
    rules = ExtendedInfusionRules()

    context = PatientContext(
        patient_id="PT-004",
        patient_mrn="456789",
        patient_name="Test Patient 4",
        encounter_id="ENC-004",
        age_years=72,
        weight_kg=68,
        height_cm=165,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.5,
        gfr=42,
        crcl=45,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="cefepime",
                dose_value=2,
                dose_unit="g",
                interval="q8h",
                route="IV",
                frequency_hours=8,
                daily_dose=6,
                daily_dose_per_kg=None,
                start_date="2024-01-01T08:00:00Z",
                order_id="ORD-004",
                infusion_duration_minutes=30,
            ),
        ],
        indication="Pseudomonas aeruginosa pneumonia",
        indication_confidence=0.92,
        indication_source="BAL culture",
        co_medications=[],
        allergies=[],
    )

    flags = rules.evaluate(context)

    assert len(flags) == 1
    flag = flags[0]
    assert flag.flag_type == DoseFlagType.EXTENDED_INFUSION_CANDIDATE
    assert flag.severity == DoseAlertSeverity.MODERATE  # Indication match but not high-risk condition
    assert "Pseudomonas aeruginosa" in flag.details["indication_match"]

    print("✓ Cefepime Pseudomonas test passed")


def test_no_matching_drug():
    """Test that non-beta-lactam doesn't get flagged."""
    rules = ExtendedInfusionRules()

    context = PatientContext(
        patient_id="PT-005",
        patient_mrn="567890",
        patient_name="Test Patient 5",
        encounter_id="ENC-005",
        age_years=35,
        weight_kg=82,
        height_cm=180,
        gestational_age_weeks=None,
        bsa=None,
        scr=0.8,
        gfr=95,
        crcl=100,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="vancomycin",
                dose_value=1500,
                dose_unit="mg",
                interval="q12h",
                route="IV",
                frequency_hours=12,
                daily_dose=3000,
                daily_dose_per_kg=None,
                start_date="2024-01-01T08:00:00Z",
                order_id="ORD-005",
                infusion_duration_minutes=60,
            ),
        ],
        indication="MRSA bacteremia",
        indication_confidence=0.95,
        indication_source="Blood culture",
        co_medications=[],
        allergies=[],
    )

    flags = rules.evaluate(context)

    # Vancomycin not in extended infusion candidates
    assert len(flags) == 0

    print("✓ Non-beta-lactam test passed")


def test_low_severity_general_optimization():
    """Test that general optimization without high-risk gets LOW severity."""
    rules = ExtendedInfusionRules()

    context = PatientContext(
        patient_id="PT-006",
        patient_mrn="678901",
        patient_name="Test Patient 6",
        encounter_id="ENC-006",
        age_years=45,
        weight_kg=75,
        height_cm=175,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.0,
        gfr=70,
        crcl=72,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="piperacillin-tazobactam",
                dose_value=4.5,
                dose_unit="g",
                interval="q6h",
                route="IV",
                frequency_hours=6,
                daily_dose=18,
                daily_dose_per_kg=None,
                start_date="2024-01-01T08:00:00Z",
                order_id="ORD-006",
                infusion_duration_minutes=30,
            ),
        ],
        indication="urinary tract infection",  # Not a high-risk indication
        indication_confidence=0.85,
        indication_source="LLM",
        co_medications=[],
        allergies=[],
    )

    flags = rules.evaluate(context)

    assert len(flags) == 1
    flag = flags[0]
    assert flag.severity == DoseAlertSeverity.LOW  # General optimization only

    print("✓ Low severity general optimization test passed")


if __name__ == "__main__":
    test_get_infusion_duration()
    test_pipetazo_standard_infusion()
    test_meropenem_extended_already()
    test_continuous_infusion()
    test_cefepime_pseudomonas()
    test_no_matching_drug()
    test_low_severity_general_optimization()

    print("\n✅ All extended infusion tests passed!")
