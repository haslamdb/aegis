#!/usr/bin/env python3
"""Surgical Prophylaxis Demo with Sample Patients.

This script demonstrates the surgical prophylaxis monitoring system with
realistic patient scenarios covering different compliance levels.

Usage:
    python demo_patients.py           # Uses temp database (data deleted after)
    python demo_patients.py --persist # Uses real database (data persists for dashboard)

The demo creates sample scenarios for:
1. VSD Repair (Cardiac) - Full bundle compliance
2. Spinal Fusion (Orthopedic) - Full compliance with MRSA coverage
3. Appendectomy (Uncomplicated) - Timing failure (>60 min window)
4. Colorectal Surgery - Wrong agent selection
5. Cochlear Implant (ENT) - Missing prophylaxis entirely
6. Cholecystectomy (Low-risk lap) - Correctly withheld (N/A)
7. Emergency Craniotomy - Excluded from measurement
8. Perforated Appendectomy - Post-op continuation required
"""

import sys
import os
import argparse
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.models import (
    ComplianceStatus,
    MedicationAdministration,
    MedicationOrder,
    ProcedureCategory,
    SurgicalCase,
)
from src.evaluator import ProphylaxisEvaluator
from src.database import ProphylaxisDatabase


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_subheader(text: str):
    """Print a formatted subheader."""
    print("\n" + "-" * 50)
    print(f"  {text}")
    print("-" * 50)


def print_element_status(element_name: str, status: str, details: str = ""):
    """Print element status with icon."""
    icons = {
        "met": "\u2713",      # checkmark
        "not_met": "\u2717",  # X
        "pending": "\u25cb",  # circle
        "n/a": "-",
        "unable": "?",
    }
    icon = icons.get(status, "?")
    detail_str = f" - {details}" if details else ""
    print(f"    [{icon}] {element_name}: {status.upper()}{detail_str}")


def create_cardiac_case_compliant(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create a cardiac surgery case with full compliance.

    Patient: 8-month-old with VSD
    Scenario: All bundle elements met
    """
    print_subheader("Patient 1: VSD Repair - Cardiac (FULL COMPLIANCE)")

    now = datetime.now()
    scheduled = now - timedelta(hours=6)
    incision = scheduled + timedelta(minutes=30)
    surgery_end = incision + timedelta(hours=4)

    print(f"""
    MRN: SP-CARD-001
    Age: 8 months (0.67 years)
    Weight: 7.5 kg
    Procedure: VSD Repair (33681)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}
    Incision: {incision.strftime('%H:%M')}
    Surgery End: {surgery_end.strftime('%H:%M')}
    Duration: 4 hours

    Expected: Cefazolin 300mg (40 mg/kg), within 60 min of incision
    """)

    # Create case
    case = SurgicalCase(
        case_id="SP-CARD-001",
        patient_mrn="CARD-2024-001",
        encounter_id="ENC-CARD-001",
        cpt_codes=["33681"],
        procedure_description="VSD Repair, Median Sternotomy",
        procedure_category=ProcedureCategory.CARDIAC,
        surgeon_id="SURG-101",
        surgeon_name="Dr. Smith",
        location="OR-3",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=7.5,
        patient_age_years=0.67,
    )

    # Add prophylaxis - correct agent, dose, timing
    admin_time = incision - timedelta(minutes=45)  # 45 min before incision
    case.prophylaxis_administrations = [
        MedicationAdministration(
            admin_id="ADM-CARD-001",
            medication_name="cefazolin",
            dose_mg=300,  # 40 mg/kg * 7.5 kg = 300 mg
            route="IV",
            admin_time=admin_time,
        ),
        # Redose at 3 hours (Q3H for cefazolin)
        MedicationAdministration(
            admin_id="ADM-CARD-002",
            medication_name="cefazolin",
            dose_mg=300,
            route="IV",
            admin_time=incision + timedelta(hours=3),
        ),
    ]

    # Save and evaluate
    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    # Print results
    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%
    - Elements Met: {evaluation.elements_met}/{evaluation.elements_total}
    """)

    return case.case_id


def create_orthopedic_case_mrsa(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create orthopedic spinal fusion case with MRSA coverage.

    Patient: 14-year-old with scoliosis, MRSA colonized
    Scenario: Full compliance with vancomycin added for MRSA
    """
    print_subheader("Patient 2: Spinal Fusion - Orthopedic (MRSA+)")

    now = datetime.now()
    scheduled = now - timedelta(hours=10)
    incision = scheduled + timedelta(minutes=45)
    surgery_end = incision + timedelta(hours=6)

    print(f"""
    MRN: SP-ORTHO-001
    Age: 14 years
    Weight: 55 kg
    Procedure: Posterior Spinal Fusion (22800)
    MRSA Status: POSITIVE (colonized)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}
    Duration: 6 hours

    Expected: Cefazolin + Vancomycin for MRSA coverage
    """)

    case = SurgicalCase(
        case_id="SP-ORTHO-001",
        patient_mrn="ORTHO-2024-001",
        encounter_id="ENC-ORTHO-001",
        cpt_codes=["22800"],
        procedure_description="Posterior Spinal Fusion for Idiopathic Scoliosis",
        procedure_category=ProcedureCategory.ORTHOPEDIC,
        surgeon_id="SURG-102",
        surgeon_name="Dr. Jones",
        location="OR-5",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=55,
        patient_age_years=14,
        mrsa_colonized=True,
    )

    # Add prophylaxis with MRSA coverage
    admin_time = incision - timedelta(minutes=55)
    vanco_admin_time = incision - timedelta(minutes=90)  # 90 min for vancomycin (120 min window)

    case.prophylaxis_administrations = [
        # Cefazolin - standard coverage
        MedicationAdministration(
            admin_id="ADM-ORTHO-001",
            medication_name="cefazolin",
            dose_mg=2000,  # 40 mg/kg * 55 kg = 2200, capped at max 2000
            route="IV",
            admin_time=admin_time,
        ),
        # Vancomycin for MRSA
        MedicationAdministration(
            admin_id="ADM-ORTHO-002",
            medication_name="vancomycin",
            dose_mg=825,  # 15 mg/kg * 55 kg
            route="IV",
            admin_time=vanco_admin_time,
        ),
        # Redose #1 at 3 hours (cefazolin Q3H)
        MedicationAdministration(
            admin_id="ADM-ORTHO-003",
            medication_name="cefazolin",
            dose_mg=2000,
            route="IV",
            admin_time=incision + timedelta(hours=3),
        ),
        # Redose #2 at 6 hours (end of surgery)
        MedicationAdministration(
            admin_id="ADM-ORTHO-004",
            medication_name="cefazolin",
            dose_mg=2000,
            route="IV",
            admin_time=incision + timedelta(hours=5, minutes=50),  # Just before surgery end
        ),
    ]

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%
    - MRSA coverage included with vancomycin
    """)

    return case.case_id


def create_appendectomy_timing_failure(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create appendectomy case with timing failure.

    Patient: 10-year-old with appendicitis
    Scenario: Prophylaxis given but too early (>60 min before incision)
    """
    print_subheader("Patient 3: Appendectomy - TIMING FAILURE")

    now = datetime.now()
    scheduled = now - timedelta(hours=4)
    incision = scheduled + timedelta(minutes=60)
    surgery_end = incision + timedelta(hours=1, minutes=30)

    print(f"""
    MRN: SP-APPY-001
    Age: 10 years
    Weight: 35 kg
    Procedure: Laparoscopic Appendectomy (44970)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}

    ISSUE: Prophylaxis given 2 hours before incision (window is 60 min)
    """)

    case = SurgicalCase(
        case_id="SP-APPY-001",
        patient_mrn="APPY-2024-001",
        encounter_id="ENC-APPY-001",
        cpt_codes=["44970"],
        procedure_description="Laparoscopic Appendectomy, Uncomplicated",
        procedure_category=ProcedureCategory.GASTROINTESTINAL_COLORECTAL,
        surgeon_id="SURG-103",
        surgeon_name="Dr. Williams",
        location="OR-2",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=35,
        patient_age_years=10,
    )

    # Add prophylaxis - given too early!
    admin_time = incision - timedelta(minutes=120)  # 2 hours early - FAIL

    case.prophylaxis_administrations = [
        MedicationAdministration(
            admin_id="ADM-APPY-001",
            medication_name="ceftriaxone",
            dose_mg=1750,  # 50 mg/kg * 35 kg
            route="IV",
            admin_time=admin_time,
        ),
        MedicationAdministration(
            admin_id="ADM-APPY-002",
            medication_name="metronidazole",
            dose_mg=525,  # 15 mg/kg * 35 kg
            route="IV",
            admin_time=admin_time,
        ),
    ]

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    # Save alert for timing failure
    if not evaluation.bundle_compliant:
        db.save_alert(
            case_id=case.case_id,
            alert_type="timing_outside_window",
            severity="medium",
            message=f"Prophylaxis given 120 min before incision (target: <=60 min)",
            element_name="Pre-op Timing",
            evaluation_id=db.get_latest_evaluation(case.case_id)["evaluation_id"],
        )

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%

    *** TIMING FAILURE ***
    Prophylaxis given 120 min before incision
    Standard window is 60 min for ceftriaxone
    """)

    return case.case_id


def create_colorectal_wrong_agent(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create colorectal surgery case with wrong agent selection.

    Patient: 6-year-old with Hirschsprung disease
    Scenario: Cefazolin given instead of cefoxitin (needs anaerobic coverage)
    """
    print_subheader("Patient 4: Colectomy - WRONG AGENT")

    now = datetime.now()
    scheduled = now - timedelta(hours=8)
    incision = scheduled + timedelta(minutes=30)
    surgery_end = incision + timedelta(hours=3)

    print(f"""
    MRN: SP-COLON-001
    Age: 6 years
    Weight: 22 kg
    Procedure: Segmental Colectomy (44140)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}

    ISSUE: Cefazolin given instead of Cefoxitin
    Colorectal procedures require anaerobic coverage!
    """)

    case = SurgicalCase(
        case_id="SP-COLON-001",
        patient_mrn="COLON-2024-001",
        encounter_id="ENC-COLON-001",
        cpt_codes=["44140"],
        procedure_description="Segmental Colectomy for Hirschsprung Disease",
        procedure_category=ProcedureCategory.GASTROINTESTINAL_COLORECTAL,
        surgeon_id="SURG-104",
        surgeon_name="Dr. Brown",
        location="OR-4",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=22,
        patient_age_years=6,
    )

    # Wrong agent! Should be cefoxitin, gave cefazolin
    admin_time = incision - timedelta(minutes=40)

    case.prophylaxis_administrations = [
        MedicationAdministration(
            admin_id="ADM-COLON-001",
            medication_name="cefazolin",  # WRONG! Should be cefoxitin
            dose_mg=880,  # 40 mg/kg * 22 kg
            route="IV",
            admin_time=admin_time,
        ),
    ]

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    if not evaluation.bundle_compliant:
        db.save_alert(
            case_id=case.case_id,
            alert_type="agent_mismatch",
            severity="high",
            message="Cefazolin given for colorectal surgery. Cefoxitin recommended for anaerobic coverage.",
            element_name="Agent Selection",
            evaluation_id=db.get_latest_evaluation(case.case_id)["evaluation_id"],
        )

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%

    *** AGENT SELECTION FAILURE ***
    Cefazolin does NOT provide anaerobic coverage
    Colorectal procedures require Cefoxitin (or clindamycin+gent)
    """)

    return case.case_id


def create_ent_missing_prophylaxis(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create ENT case with missing prophylaxis entirely.

    Patient: 3-year-old undergoing cochlear implant
    Scenario: No prophylaxis given despite being indicated
    """
    print_subheader("Patient 5: Cochlear Implant - MISSING PROPHYLAXIS")

    now = datetime.now()
    scheduled = now - timedelta(hours=5)
    incision = scheduled + timedelta(minutes=45)
    surgery_end = incision + timedelta(hours=2)

    print(f"""
    MRN: SP-ENT-001
    Age: 3 years
    Weight: 15 kg
    Procedure: Cochlear Implant (69930)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}

    CRITICAL: NO PROPHYLAXIS GIVEN!
    Expected: Ampicillin-sulbactam (or clindamycin if allergic)
    """)

    case = SurgicalCase(
        case_id="SP-ENT-001",
        patient_mrn="ENT-2024-001",
        encounter_id="ENC-ENT-001",
        cpt_codes=["69930"],
        procedure_description="Cochlear Implant Insertion",
        procedure_category=ProcedureCategory.ENT,
        surgeon_id="SURG-105",
        surgeon_name="Dr. Davis",
        location="OR-6",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=15,
        patient_age_years=3,
    )

    # NO prophylaxis - empty administrations
    case.prophylaxis_administrations = []

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    if not evaluation.bundle_compliant:
        db.save_alert(
            case_id=case.case_id,
            alert_type="missing_prophylaxis",
            severity="high",
            message="No prophylaxis given for cochlear implant. Ampicillin-sulbactam recommended.",
            element_name="Indication",
            evaluation_id=db.get_latest_evaluation(case.case_id)["evaluation_id"],
        )

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%

    *** CRITICAL: PROPHYLAXIS NOT GIVEN ***
    Cochlear implant surgery requires prophylaxis
    Risk of surgical site infection with implant material
    """)

    return case.case_id


def create_cholecystectomy_appropriate_withhold(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create cholecystectomy case where prophylaxis correctly withheld.

    Patient: 12-year-old with cholelithiasis (low-risk laparoscopic)
    Scenario: Prophylaxis correctly NOT given (not indicated per guidelines)
    """
    print_subheader("Patient 6: Lap Cholecystectomy - CORRECTLY WITHHELD")

    now = datetime.now()
    scheduled = now - timedelta(hours=3)
    incision = scheduled + timedelta(minutes=25)
    surgery_end = incision + timedelta(hours=1)

    print(f"""
    MRN: SP-BILI-001
    Age: 12 years
    Weight: 45 kg
    Procedure: Laparoscopic Cholecystectomy, Low-risk (47562)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}

    Prophylaxis NOT indicated for low-risk laparoscopic biliary procedures
    No prophylaxis given = COMPLIANT
    """)

    case = SurgicalCase(
        case_id="SP-BILI-001",
        patient_mrn="BILI-2024-001",
        encounter_id="ENC-BILI-001",
        cpt_codes=["47562"],
        procedure_description="Laparoscopic Cholecystectomy, Uncomplicated",
        procedure_category=ProcedureCategory.HEPATOBILIARY,
        surgeon_id="SURG-106",
        surgeon_name="Dr. Miller",
        location="OR-1",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=45,
        patient_age_years=12,
    )

    # No prophylaxis - correctly withheld
    case.prophylaxis_administrations = []

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%

    Prophylaxis correctly withheld per ASHP guidelines
    Low-risk lap cholecystectomy does not require prophylaxis
    """)

    return case.case_id


def create_emergency_excluded(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create emergency case that is excluded from compliance measurement.

    Patient: 7-year-old with traumatic brain injury
    Scenario: Emergency craniotomy - excluded from compliance metrics
    """
    print_subheader("Patient 7: Emergency Craniotomy - EXCLUDED")

    now = datetime.now()
    scheduled = now - timedelta(hours=2)
    incision = scheduled + timedelta(minutes=15)
    surgery_end = incision + timedelta(hours=3)

    print(f"""
    MRN: SP-EMERG-001
    Age: 7 years
    Weight: 25 kg
    Procedure: Emergency Craniotomy (61312)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}

    EMERGENCY CASE - Excluded from compliance measurement
    Standard timing windows may not be achievable
    """)

    case = SurgicalCase(
        case_id="SP-EMERG-001",
        patient_mrn="EMERG-2024-001",
        encounter_id="ENC-EMERG-001",
        cpt_codes=["61312"],
        procedure_description="Emergency Craniotomy for Epidural Hematoma",
        procedure_category=ProcedureCategory.NEUROSURGERY,
        surgeon_id="SURG-107",
        surgeon_name="Dr. Wilson",
        location="OR-TRAUMA",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=25,
        patient_age_years=7,
        is_emergency=True,  # EMERGENCY FLAG
    )

    # Prophylaxis given but timing was rushed
    admin_time = incision - timedelta(minutes=10)  # Only 10 min before incision

    case.prophylaxis_administrations = [
        MedicationAdministration(
            admin_id="ADM-EMERG-001",
            medication_name="cefazolin",
            dose_mg=1000,
            route="IV",
            admin_time=admin_time,
        ),
    ]

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Excluded: {evaluation.excluded}
    - Exclusion Reason: {evaluation.exclusion_reason}
    - Score: N/A (excluded from metrics)

    Emergency cases are excluded because:
    - Time-critical nature may prevent optimal timing
    - Patient stabilization takes priority
    - Standard windows may not be achievable
    """)

    return case.case_id


def create_perforated_appy_postop(db: ProphylaxisDatabase, evaluator: ProphylaxisEvaluator) -> str:
    """Create perforated appendectomy case requiring post-op continuation.

    Patient: 8-year-old with perforated appendicitis
    Scenario: Requires 24h post-op continuation Q24H
    """
    print_subheader("Patient 8: Perforated Appendectomy - POST-OP CONTINUATION")

    now = datetime.now()
    scheduled = now - timedelta(hours=28)
    incision = scheduled + timedelta(minutes=45)
    surgery_end = incision + timedelta(hours=2)

    print(f"""
    MRN: SP-PERF-001
    Age: 8 years
    Weight: 28 kg
    Procedure: Appendectomy, Perforated (44970)
    OR Time: {scheduled.strftime('%Y-%m-%d %H:%M')}

    PERFORATED APPENDICITIS requires post-op continuation:
    - Pre-op: Ceftriaxone + Metronidazole
    - Continue Q24H for 24 hours after surgery
    """)

    case = SurgicalCase(
        case_id="SP-PERF-001",
        patient_mrn="PERF-2024-001",
        encounter_id="ENC-PERF-001",
        cpt_codes=["44970"],
        procedure_description="Laparoscopic Appendectomy, Perforated",
        procedure_category=ProcedureCategory.GASTROINTESTINAL_COLORECTAL,
        surgeon_id="SURG-108",
        surgeon_name="Dr. Taylor",
        location="OR-2",
        scheduled_or_time=scheduled,
        actual_incision_time=incision,
        surgery_end_time=surgery_end,
        patient_weight_kg=28,
        patient_age_years=8,
    )

    # Pre-op dose
    preop_time = incision - timedelta(minutes=50)
    # Post-op dose at 24h (Q24H dosing)
    postop_time = surgery_end + timedelta(hours=22)

    case.prophylaxis_administrations = [
        # Pre-op ceftriaxone
        MedicationAdministration(
            admin_id="ADM-PERF-001",
            medication_name="ceftriaxone",
            dose_mg=1400,  # 50 mg/kg * 28 kg
            route="IV",
            admin_time=preop_time,
        ),
        # Pre-op metronidazole
        MedicationAdministration(
            admin_id="ADM-PERF-002",
            medication_name="metronidazole",
            dose_mg=840,  # 30 mg/kg * 28 kg (appendectomy dose)
            route="IV",
            admin_time=preop_time,
        ),
        # Post-op ceftriaxone Q24H
        MedicationAdministration(
            admin_id="ADM-PERF-003",
            medication_name="ceftriaxone",
            dose_mg=1400,
            route="IV",
            admin_time=postop_time,
        ),
        # Post-op metronidazole Q24H
        MedicationAdministration(
            admin_id="ADM-PERF-004",
            medication_name="metronidazole",
            dose_mg=840,
            route="IV",
            admin_time=postop_time,
        ),
    ]

    db.save_case(case)
    evaluation = evaluator.evaluate_case(case)
    db.save_evaluation(evaluation)

    print("    Element Results:")
    for elem in evaluation.elements:
        print_element_status(elem.element_name, elem.status.value, elem.details[:60] if elem.details else "")

    print(f"""
    Summary:
    - Bundle Compliant: {evaluation.bundle_compliant}
    - Score: {evaluation.compliance_score:.0f}%

    Perforated appendicitis protocol:
    - Pre-op: Ceftriaxone 50 mg/kg + Metronidazole 30 mg/kg
    - Continue Q24H for 24 hours after surgery
    - Total antibiotic duration: ~26 hours
    """)

    return case.case_id


def display_dashboard_summary(db: ProphylaxisDatabase):
    """Display a summary dashboard of all evaluated cases."""
    print_header("SURGICAL PROPHYLAXIS COMPLIANCE DASHBOARD")

    # Get date range for summary
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1)

    summary = db.get_compliance_summary(start_date, end_date)

    print(f"""
    Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}

    OVERALL METRICS
    ---------------
    Total Cases:     {summary['total_cases']}
    Excluded:        {summary['excluded_cases']}
    Evaluated:       {summary['evaluated_cases']}
    Compliant:       {summary.get('compliant_cases', 0)}
    Bundle Rate:     {summary['bundle_compliance_rate']:.1f}%
    Avg Score:       {summary['avg_compliance_score']:.1f}%

    ELEMENT-LEVEL COMPLIANCE
    ------------------------""")

    for element, rate in summary.get('element_rates', {}).items():
        bar_len = int(rate / 5)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        print(f"    {element:20s} [{bar}] {rate:.1f}%")

    # Get non-compliant cases
    non_compliant = db.get_non_compliant_cases(start_date, end_date, limit=10)

    if non_compliant:
        print(f"""
    NON-COMPLIANT CASES ({len(non_compliant)})
    --------------------""")
        for case in non_compliant:
            print(f"    {case['patient_mrn']:15s} {case['procedure_description'][:30]:30s} {case['compliance_score']:.0f}%")

    # Get pending alerts
    alerts = db.get_pending_alerts()
    if alerts:
        print(f"""
    ACTIVE ALERTS ({len(alerts)})
    --------------""")
        for alert in alerts:
            print(f"    [{alert['alert_severity'].upper():6s}] {alert['patient_mrn']:15s} {alert['alert_type']}")


def run_demo(db_path: str, persist: bool = False):
    """Run the demo with specified database."""
    # Initialize database and evaluator
    db = ProphylaxisDatabase(db_path)
    evaluator = ProphylaxisEvaluator()

    print("""
    Creating demo surgical cases...
    """)

    # Create all demo cases
    create_cardiac_case_compliant(db, evaluator)
    create_orthopedic_case_mrsa(db, evaluator)
    create_appendectomy_timing_failure(db, evaluator)
    create_colorectal_wrong_agent(db, evaluator)
    create_ent_missing_prophylaxis(db, evaluator)
    create_cholecystectomy_appropriate_withhold(db, evaluator)
    create_emergency_excluded(db, evaluator)
    create_perforated_appy_postop(db, evaluator)

    # Display summary dashboard
    display_dashboard_summary(db)

    print_header("DEMO COMPLETE")
    print("""
    Key Observations:

    1. CARDIAC VSD REPAIR: 100% compliance
       - Cefazolin given at correct dose and timing
       - Appropriate intraoperative redosing for 4-hour case

    2. SPINAL FUSION (MRSA+): 100% compliance
       - Cefazolin plus vancomycin for MRSA coverage
       - Both agents given within appropriate windows

    3. APPENDECTOMY: Timing failure
       - Prophylaxis given 120 min before incision
       - Standard window is 60 min for ceftriaxone

    4. COLORECTAL: Wrong agent selection
       - Cefazolin lacks anaerobic coverage
       - Should have been cefoxitin (or clinda+gent)

    5. COCHLEAR IMPLANT: Missing prophylaxis
       - No antibiotics given despite indication
       - Amp-sulbactam recommended for ENT procedures

    6. LAP CHOLECYSTECTOMY: Correctly withheld
       - Low-risk laparoscopic procedure
       - No prophylaxis indicated per guidelines

    7. EMERGENCY CRANIOTOMY: Excluded
       - Emergency cases excluded from metrics
       - Timing constraints may not be achievable

    8. PERFORATED APPENDECTOMY: Post-op continuation
       - Requires 24h continuation after surgery
       - Both ceftriaxone and metronidazole continued Q24H

    This system enables:
    - Retrospective compliance monitoring (7 bundle elements)
    - Automated alert generation for non-compliance
    - Real-time pre-operative alerting (with realtime module)
    - Compliance dashboards for ASP review
    """)

    if persist:
        print(f"""
    Data persisted to: {db_path}
    View in dashboard: http://localhost:8082/surgical-prophylaxis/
        """)


def main():
    """Run the demo."""
    parser = argparse.ArgumentParser(description="Surgical Prophylaxis Demo")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist data to real database (for dashboard viewing)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing demo data before creating new cases",
    )
    args = parser.parse_args()

    print_header("AEGIS SURGICAL PROPHYLAXIS MONITORING - DEMO")

    print("""
    This demo creates sample surgical cases to demonstrate the
    prophylaxis compliance monitoring system.

    Patients:
    1. VSD Repair (Cardiac) - Full compliance
    2. Spinal Fusion (MRSA+) - Full compliance with vancomycin
    3. Appendectomy - Timing failure (>60 min window)
    4. Colorectal - Wrong agent (cefazolin vs cefoxitin)
    5. Cochlear Implant - Missing prophylaxis entirely
    6. Lap Cholecystectomy - Correctly withheld (N/A)
    7. Emergency Craniotomy - Excluded from measurement
    8. Perforated Appendectomy - Post-op continuation required
    """)

    if args.persist:
        # Use real database
        aegis_dir = Path.home() / ".aegis"
        aegis_dir.mkdir(exist_ok=True)
        db_path = str(aegis_dir / "surgical_prophylaxis.db")
        print(f"  Using persistent database: {db_path}")

        if args.clear:
            # Clear existing demo MRNs
            import sqlite3
            conn = sqlite3.connect(db_path)
            demo_prefixes = ["SP-CARD", "SP-ORTHO", "SP-APPY", "SP-COLON", "SP-ENT", "SP-BILI", "SP-EMERG", "SP-PERF"]
            for prefix in demo_prefixes:
                conn.execute("DELETE FROM prophylaxis_alerts WHERE case_id LIKE ?", (f"{prefix}%",))
                conn.execute("DELETE FROM prophylaxis_evaluations WHERE case_id LIKE ?", (f"{prefix}%",))
                conn.execute("DELETE FROM prophylaxis_administrations WHERE case_id LIKE ?", (f"{prefix}%",))
                conn.execute("DELETE FROM prophylaxis_orders WHERE case_id LIKE ?", (f"{prefix}%",))
                conn.execute("DELETE FROM surgical_cases WHERE case_id LIKE ?", (f"{prefix}%",))
            conn.commit()
            conn.close()
            print("  Cleared existing demo data")

        run_demo(db_path, persist=True)
    else:
        # Use temporary database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "demo_surgical_prophylaxis.db")
            print(f"  Demo database: {db_path}")
            run_demo(db_path, persist=False)


if __name__ == "__main__":
    main()
