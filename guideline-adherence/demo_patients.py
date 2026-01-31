#!/usr/bin/env python3
"""Guideline Adherence Demo with Sample Patients.

This script demonstrates the guideline adherence monitoring system with
realistic patient scenarios for different bundles.

Usage:
    python demo_patients.py           # Uses temp database (data deleted after)
    python demo_patients.py --persist # Uses real database (data persists for dashboard)
    python demo_patients.py --persist --fhir  # Also create FHIR resources with clinical notes

The demo creates sample scenarios for:
1. Febrile Infant (14-day-old) - Full adherence scenario
2. Sepsis (3-year-old) - Partial adherence with missed elements
3. Neonatal HSV (10-day-old) - Critical alerts scenario
4. C. diff Testing - Diagnostic stewardship check
"""

import sys
import os
import argparse
import tempfile
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from guideline_adherence import (
    GUIDELINE_BUNDLES,
    BundleElementStatus,
    AdherenceLevel,
)
from guideline_src.episode_db import (
    EpisodeDB,
    BundleEpisode,
    ElementResult,
    BundleAlert,
)
from guideline_src.fhir_client import HAPIGuidelineFHIRClient

logger = logging.getLogger(__name__)


# Clinical notes for demo patients - these will be parsed by the LLM
CLINICAL_NOTES = {
    "febrile_infant_well": {
        "physical_exam": """Physical Exam:
General: Well-appearing, alert, active infant. Good tone.
Vitals: T 38.5°C (rectal), HR 145, RR 36, SpO2 99% RA, BP 72/45
Skin: Pink, warm, well-perfused, cap refill <2 sec
HEENT: Fontanelle soft and flat, TMs clear bilaterally, moist mucous membranes
Lungs: Clear to auscultation bilaterally, no distress
CV: Regular rate and rhythm, no murmur, strong femoral pulses
Abdomen: Soft, non-tender, no hepatosplenomegaly
Neuro: Alert, active, good tone, strong suck and grasp reflexes

Assessment: Well-appearing 14-day-old febrile infant, no source identified.""",
        "nursing_note": """Nursing Assessment (0830):
14-day-old male presenting with fever. T 38.5°C rectal at triage.
Baby is alert and active, feeding well - took 60ml formula without difficulty.
Good eye contact with parents, consolable when fussy, strong cry.
Parents report normal activity and feeding at home until noticed felt warm.
Wet diapers normal - 6 wet in past 24 hours.
No rash, no respiratory distress. Parents appropriately concerned but baby looks well.""",
        "ed_note": """ED Physician Note:
14-day-old previously healthy male presents with fever noted at home.
Birth history: Term, uncomplicated vaginal delivery, GBS negative, NICU stay 0 days.
Feeding: Formula, taking well.
Per parents, baby has been his normal self, feeding well, active and alert.
No URI symptoms, no vomiting, no diarrhea, no rash.

On exam, this is a well-appearing infant with normal activity and tone.
Good interaction, strong cry, consolable. No distress.

Plan: Febrile infant workup per protocol given age 8-21 days.
LP performed - clear CSF obtained.
Blood and urine cultures sent before antibiotics.
Starting empiric ampicillin and gentamicin.
Admit to pediatrics for observation and culture results.""",
    },
    "febrile_infant_ill": {
        "physical_exam": """Physical Exam:
General: Ill-appearing, lethargic infant. Poor tone.
Vitals: T 39.2°C (rectal), HR 185, RR 56, SpO2 94% RA, BP 58/32
Skin: Mottled appearance on trunk and extremities, pallor, delayed cap refill 4 sec
HEENT: Fontanelle slightly bulging, decreased tearing, dry mucous membranes
Lungs: Grunting respirations, mild subcostal retractions
CV: Tachycardic, thready pulses, cool extremities
Abdomen: Distended, decreased bowel sounds
Neuro: Hypotonic, poor suck, difficult to arouse, weak cry

Assessment: Ill-appearing 10-day-old febrile infant, concerning for sepsis.""",
        "nursing_note": """Nursing Assessment:
10-day-old presenting with fever and lethargy.
Baby is very sleepy, difficult to wake for assessments.
Only took 15ml formula before falling back asleep - poor feeding.
Weak cry when stimulated. Color pale with mottling on legs and trunk.
Parents very concerned - state baby is "not acting like himself" since yesterday.
Poor urine output - only 1 wet diaper in past 8 hours.
Required O2 via NC 1L to maintain sats >94%.""",
        "ed_note": """ED Physician Note:
10-day-old male with fever and altered mental status, concerning presentation.

Birth history: Late preterm (36 weeks), brief NICU stay, GBS unknown.
Per parents, baby was noted to be less active yesterday, feeding less.
Today found to be febrile and "floppy" at home.

On exam, this is an ill-appearing infant with poor tone and perfusion.
Mottled, delayed cap refill, tachycardic with weak pulses.
Grunting respirations requiring supplemental oxygen.

High concern for bacterial sepsis vs meningitis.
Initiating sepsis workup and resuscitation.
LP performed - CSF appears cloudy.
Broad spectrum antibiotics started immediately - ampicillin, gentamicin, acyclovir given HSV concern.
Fluid resuscitation initiated.
PICU consulted for admission.""",
    },
    "sepsis_pediatric": {
        "physical_exam": """Physical Exam:
General: Ill-appearing 3-year-old, lethargic but responsive to voice
Vitals: T 39.8°C, HR 175, RR 42, SpO2 92% RA, BP 78/45 (hypotensive for age)
Skin: Mottled, cool extremities, cap refill 4 seconds
HEENT: Dry mucous membranes, sunken eyes
Lungs: Tachypneic, no focal findings
CV: Tachycardic, thready peripheral pulses, cool extremities
Abdomen: Soft, non-tender
Neuro: Lethargic, responds to voice, GCS 13

Assessment: Septic shock, source unclear. Requires aggressive resuscitation.""",
        "nursing_note": """Nursing Assessment:
3-year-old with fever, lethargy, and poor perfusion.
Arrived via EMS with IV access established.
Initial lactate 4.2 mmol/L - critically elevated.
Two large bore IVs placed. First fluid bolus (20mL/kg) given.
Repeat assessment after first bolus: still mottled, cap refill 3 sec.
Second bolus initiated. Blood cultures drawn before antibiotics.
Parents report 2-day history of fever and decreased activity.
No recent travel or sick contacts identified.
Pharmacy notified for urgent antibiotics.""",
        "ed_note": """ED Physician Note:
3-year-old previously healthy male with 2-day history of fever, now with
signs of septic shock.

Presenting with tachycardia, hypotension, mottled skin, and altered mental status.
Initial lactate 4.2 mmol/L.

Sepsis bundle initiated:
- Blood cultures obtained
- Lactate drawn
- Fluid resuscitation: 60 mL/kg given over first hour
- Broad spectrum antibiotics ordered (ceftriaxone + vancomycin)

Note: Antibiotics delayed approximately 80 minutes from sepsis recognition
due to pharmacy preparation time. Will document in QI report.

Repeat lactate pending.
Admitted to PICU for continued resuscitation and monitoring.""",
    },
    "neonatal_hsv": {
        "physical_exam": """Physical Exam:
General: Irritable infant, intermittently lethargic
Vitals: T 38.8°C, HR 170, RR 48, SpO2 97% RA
Skin: Scattered vesicular lesions on scalp and forehead (cluster of 5-6 vesicles)
HEENT: Fontanelle flat, some vesicles near hairline
Lungs: Clear
CV: Tachycardic, good perfusion
Abdomen: Soft, liver edge palpable 2cm below costal margin
Neuro: Irritable, intermittent tremors noted, witnessed focal seizure activity lasting ~30 seconds

Assessment: Suspected neonatal HSV - vesicular rash with seizure activity.
CRITICAL: Requires immediate acyclovir.""",
        "nursing_note": """Nursing Assessment:
10-day-old with vesicular rash and new seizure.
Parents report noting "blisters" on baby's head yesterday.
Today witnessed baby having shaking episode lasting about 30 seconds.
Baby now irritable, difficult to console.
Rash: Cluster of small clear blisters on scalp and forehead.
No maternal history of HSV known, but mother reports "cold sore" 2 weeks ago.
HSV precautions initiated.
Neuro checks ordered q1 hour.""",
        "ed_note": """ED Physician Note:
10-day-old presenting with vesicular rash and witnessed seizure.

HIGH CONCERN FOR NEONATAL HSV:
Risk factors present:
- Vesicular skin lesions (SEM involvement)
- Seizure activity (CNS involvement)
- Mother with recent oral herpes lesion

HSV workup initiated:
- CSF sent for HSV PCR
- Blood sent for HSV PCR
- Surface cultures obtained (conjunctiva, mouth, rectum, vesicle base)
- LFTs obtained (mildly elevated)

CRITICAL: Acyclovir 20 mg/kg IV Q8H must be started IMMEDIATELY.
Do not wait for PCR results.

ID consulted urgently.
MRI brain ordered to evaluate for HSV encephalitis.
Admit to NICU for close monitoring and IV acyclovir.""",
    },
}


def create_fhir_patient_with_notes(
    fhir_client: HAPIGuidelineFHIRClient,
    mrn: str,
    given_name: str,
    family_name: str,
    birth_date: str,
    gender: str,
    notes_key: str,
    note_time: datetime | None = None,
) -> str:
    """Create a FHIR patient with clinical notes.

    Args:
        fhir_client: HAPI FHIR client.
        mrn: Medical record number.
        given_name: First name.
        family_name: Last name.
        birth_date: Birth date (YYYY-MM-DD).
        gender: Gender.
        notes_key: Key into CLINICAL_NOTES dict.
        note_time: Time for notes (defaults to now).

    Returns:
        FHIR Patient ID.
    """
    # Check if patient already exists
    existing = fhir_client.find_patient_by_mrn(mrn)
    if existing:
        print(f"    Found existing FHIR patient: {existing['fhir_id']}")
        patient_id = existing["fhir_id"]
        # Delete and recreate to ensure clean state
        fhir_client.delete_patient_cascade(patient_id)
        print(f"    Deleted existing patient to recreate with fresh notes")

    # Create patient
    patient = fhir_client.create_patient(
        mrn=mrn,
        given_name=given_name,
        family_name=family_name,
        birth_date=birth_date,
        gender=gender,
    )
    patient_id = patient["id"]
    print(f"    Created FHIR Patient: {patient_id}")

    # Add clinical notes
    if notes_key in CLINICAL_NOTES:
        notes = CLINICAL_NOTES[notes_key]
        note_time = note_time or datetime.now()

        # Note type LOINC codes
        note_types = {
            "physical_exam": ("29545-1", "Physical findings"),
            "nursing_note": ("34746-8", "Nurse Note"),
            "ed_note": ("34878-9", "Emergency department Note"),
        }

        for note_key, note_text in notes.items():
            loinc_code, display = note_types.get(note_key, ("11506-3", "Progress note"))
            doc = fhir_client.create_clinical_note(
                patient_id=patient_id,
                note_text=note_text,
                note_type=display,
                note_type_code=loinc_code,
                author_name="Demo Provider",
                note_date=note_time,
            )
            print(f"    Created {display}: DocumentReference/{doc['id']}")

    return patient_id


def clear_fhir_demo_patients(fhir_client: HAPIGuidelineFHIRClient, demo_mrns: list[str]):
    """Clear demo patients from FHIR server."""
    print("  Clearing existing FHIR demo patients...")
    for mrn in demo_mrns:
        existing = fhir_client.find_patient_by_mrn(mrn)
        if existing:
            fhir_client.delete_patient_cascade(existing["fhir_id"])
            print(f"    Deleted FHIR patient: {mrn}")


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


def print_element_status(element_name: str, status: str, value: str = None, notes: str = None):
    """Print element status with icon."""
    icons = {
        "met": "\u2713",      # checkmark
        "not_met": "\u2717",  # X
        "pending": "\u25cb",  # circle
        "na": "-",
        "unknown": "?",
    }
    icon = icons.get(status, "?")
    value_str = f" = {value}" if value else ""
    notes_str = f" ({notes})" if notes else ""
    print(f"    [{icon}] {element_name}: {status}{value_str}{notes_str}")


def create_febrile_infant_episode(
    db: EpisodeDB,
    fhir_client: HAPIGuidelineFHIRClient | None = None,
) -> int:
    """Create a febrile infant episode with full adherence.

    Patient: 14-day-old with fever 38.5°C
    Expected: All required elements for 8-21 day age group
    """
    print_subheader("Patient 1: Febrile Infant - Well-Appearing (14 days old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=2)
    mrn = "FI-2024-001"
    patient_id = "PT-FI-001"
    birth_date = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    # Create FHIR patient with clinical notes if client provided
    if fhir_client:
        print("  Creating FHIR resources...")
        patient_id = create_fhir_patient_with_notes(
            fhir_client=fhir_client,
            mrn=mrn,
            given_name="Baby",
            family_name="WellAppearing",
            birth_date=birth_date,
            gender="male",
            notes_key="febrile_infant_well",
            note_time=trigger_time,
        )

    print(f"""
    MRN: {mrn}
    Age: 14 days
    Chief Complaint: Fever (38.5°C) at home
    Presentation: Well-appearing, no source identified
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')}

    Bundle: Febrile Infant (8-60 days) - AAP 2021 Guideline
    Age Group: 8-21 days (requires LP, admission, IV antibiotics)
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id=patient_id,
        patient_mrn=mrn,
        encounter_id="ENC-FI-001",
        bundle_id="febrile_infant_2024",
        bundle_name="Febrile Infant Bundle (0-60 days)",
        trigger_type="diagnosis",
        trigger_code="R50.9",
        trigger_description="Fever, unspecified",
        trigger_time=trigger_time,
        patient_age_days=14,
        patient_age_months=0.47,
        patient_unit="Pediatric Emergency",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - FULL ADHERENCE
    bundle = GUIDELINE_BUNDLES["febrile_infant_2024"]

    elements_data = [
        # All elements completed within time window
        ("fi_ua", "Urinalysis obtained", "met", "Negative", "Cath specimen"),
        ("fi_blood_culture", "Blood culture obtained", "met", "Collected 10:15", "Before antibiotics"),
        ("fi_inflammatory_markers", "Inflammatory markers obtained", "met", "ANC 8500, CRP 0.8", "Normal"),
        ("fi_lp_8_21d", "LP performed (8-21 days)", "met", "WBC 2, protein 45", "Normal CSF"),
        ("fi_abx_8_21d", "Parenteral antibiotics (8-21 days)", "met", "Ampicillin + Gentamicin", "Given at 10:30"),
        ("fi_hsv_risk_assessment", "HSV risk assessment", "met", "No risk factors", "Documented in note"),
        ("fi_admit_8_21d", "Hospital admission (8-21 days)", "met", "Admitted", "To pediatrics"),
    ]

    print("    Element Status:")
    met_count = 0
    for elem_id, elem_name, status, value, notes in elements_data:
        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=2.0,
            deadline=trigger_time + timedelta(hours=2),
            completed_at=trigger_time + timedelta(minutes=30) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)
        if status == "met":
            met_count += 1

    # Update episode with adherence stats
    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = len(elements_data)
    episode.elements_met = met_count
    episode.elements_not_met = 0
    episode.elements_pending = len(elements_data) - met_count
    episode.adherence_percentage = (met_count / len(elements_data)) * 100
    episode.adherence_level = "full" if episode.adherence_percentage == 100 else "partial"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{len(elements_data)}
    - Adherence: {episode.adherence_percentage:.0f}%
    - Level: {episode.adherence_level.upper()}
    - Alerts: None (full compliance)
    """)

    return episode_id


def create_sepsis_episode(
    db: EpisodeDB,
    fhir_client: HAPIGuidelineFHIRClient | None = None,
) -> int:
    """Create a sepsis episode with partial adherence.

    Patient: 3-year-old with septic shock
    Scenario: Antibiotics delayed >1 hour, no repeat lactate
    """
    print_subheader("Patient 2: Pediatric Sepsis (3 years old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=4)
    mrn = "SEP-2024-002"
    patient_id = "PT-SEP-002"
    birth_date = (now - timedelta(days=1095)).strftime("%Y-%m-%d")

    # Create FHIR patient with clinical notes if client provided
    if fhir_client:
        print("  Creating FHIR resources...")
        patient_id = create_fhir_patient_with_notes(
            fhir_client=fhir_client,
            mrn=mrn,
            given_name="Tommy",
            family_name="Sepsis",
            birth_date=birth_date,
            gender="male",
            notes_key="sepsis_pediatric",
            note_time=trigger_time,
        )

    print(f"""
    MRN: {mrn}
    Age: 3 years
    Chief Complaint: Fever, lethargy, poor perfusion
    Presentation: Hypotensive, tachycardic, mottled extremities
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')} (sepsis alert fired)

    Bundle: Pediatric Sepsis Bundle
    Critical Elements: ABX within 1 hour, blood culture, lactate
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id=patient_id,
        patient_mrn=mrn,
        encounter_id="ENC-SEP-002",
        bundle_id="sepsis_peds_2024",
        bundle_name="Pediatric Sepsis Bundle",
        trigger_type="diagnosis",
        trigger_code="A41.9",
        trigger_description="Sepsis, unspecified organism",
        trigger_time=trigger_time,
        patient_age_days=1095,
        patient_age_months=36,
        patient_weight_kg=15.0,
        patient_unit="PICU",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - PARTIAL ADHERENCE with issues
    elements_data = [
        ("sepsis_blood_cx", "Blood culture obtained", "met", "Collected 14:05", "Before antibiotics"),
        ("sepsis_lactate", "Lactate measured", "met", "4.2 mmol/L", "Elevated - needs repeat"),
        ("sepsis_abx_1hr", "Antibiotics within 1 hour", "not_met", "Given at 15:20", "DELAYED 80 min - pharmacy delay"),
        ("sepsis_fluid_bolus", "Fluid resuscitation initiated", "met", "60 mL/kg given", "3 boluses"),
        ("sepsis_repeat_lactate", "Repeat lactate if elevated", "not_met", None, "NOT DONE - initial was 4.2"),
        ("sepsis_reassess_48h", "Antibiotic reassessment at 48h", "pending", None, "Due in 44 hours"),
    ]

    print("    Element Status:")
    met_count = 0
    not_met_count = 0
    pending_count = 0

    for elem_id, elem_name, status, value, notes in elements_data:
        # Determine time window based on element
        time_window = 1.0 if "1hr" in elem_id or "1h" in elem_name.lower() else 6.0
        if "48h" in elem_id:
            time_window = 72.0

        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=time_window,
            deadline=trigger_time + timedelta(hours=time_window),
            completed_at=trigger_time + timedelta(minutes=20) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)

        if status == "met":
            met_count += 1
        elif status == "not_met":
            not_met_count += 1
        else:
            pending_count += 1

    # Create alerts for missed elements
    alert_count = 0

    # Alert for delayed antibiotics (CRITICAL)
    alert1 = BundleAlert(
        episode_id=episode_id,
        patient_id="PT-SEP-002",
        patient_mrn="SEP-2024-002",
        encounter_id="ENC-SEP-002",
        bundle_id="sepsis_peds_2024",
        bundle_name="Pediatric Sepsis Bundle",
        element_id="sepsis_abx_1hr",
        element_name="Antibiotics within 1 hour",
        alert_type="element_not_met",
        severity="critical",
        title="SEPSIS: Antibiotic delay >1 hour",
        message="Antibiotics administered 80 minutes after sepsis recognition. Target: <60 minutes. Delay attributed to pharmacy.",
    )
    db.save_alert(alert1)
    alert_count += 1

    # Alert for missing repeat lactate (WARNING)
    alert2 = BundleAlert(
        episode_id=episode_id,
        patient_id="PT-SEP-002",
        patient_mrn="SEP-2024-002",
        encounter_id="ENC-SEP-002",
        bundle_id="sepsis_peds_2024",
        bundle_name="Pediatric Sepsis Bundle",
        element_id="sepsis_repeat_lactate",
        element_name="Repeat lactate if elevated",
        alert_type="element_overdue",
        severity="warning",
        title="SEPSIS: Repeat lactate overdue",
        message="Initial lactate was 4.2 mmol/L. Repeat lactate required within 6 hours but not yet obtained.",
    )
    db.save_alert(alert2)
    alert_count += 1

    # Update episode stats
    applicable = len(elements_data) - pending_count
    adherence_pct = (met_count / applicable * 100) if applicable > 0 else 0

    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = applicable
    episode.elements_met = met_count
    episode.elements_not_met = not_met_count
    episode.elements_pending = pending_count
    episode.adherence_percentage = adherence_pct
    episode.adherence_level = "partial" if adherence_pct > 50 else "low"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{applicable} (+ {pending_count} pending)
    - Adherence: {adherence_pct:.0f}%
    - Level: {episode.adherence_level.upper()}
    - Alerts Generated: {alert_count}
      * CRITICAL: Antibiotic delay (80 min vs 60 min target)
      * WARNING: Repeat lactate not obtained
    """)

    return episode_id


def create_neonatal_hsv_episode(
    db: EpisodeDB,
    fhir_client: HAPIGuidelineFHIRClient | None = None,
) -> int:
    """Create a neonatal HSV episode with critical alerts.

    Patient: 10-day-old with vesicular rash and seizure
    Scenario: HSV workup incomplete, acyclovir not started
    """
    print_subheader("Patient 3: Neonatal HSV Suspected (10 days old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=3)
    mrn = "HSV-2024-003"
    patient_id = "PT-HSV-003"
    birth_date = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    # Create FHIR patient with clinical notes if client provided
    if fhir_client:
        print("  Creating FHIR resources...")
        patient_id = create_fhir_patient_with_notes(
            fhir_client=fhir_client,
            mrn=mrn,
            given_name="Baby",
            family_name="Vesicles",
            birth_date=birth_date,
            gender="male",
            notes_key="neonatal_hsv",
            note_time=trigger_time,
        )

    print(f"""
    MRN: {mrn}
    Age: 10 days
    Chief Complaint: Vesicular rash, new seizure
    Presentation: Irritable, vesicles on scalp, witnessed seizure
    HSV Risk Factors: Vesicular rash, seizures, maternal HSV unknown
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')}

    Bundle: Neonatal HSV Bundle (CCHMC 2024)
    CRITICAL: Acyclovir must be started within 1 hour
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id=patient_id,
        patient_mrn=mrn,
        encounter_id="ENC-HSV-003",
        bundle_id="neonatal_hsv_2024",
        bundle_name="Neonatal HSV Bundle",
        trigger_type="diagnosis",
        trigger_code="B00.9",
        trigger_description="Herpesviral infection suspected",
        trigger_time=trigger_time,
        patient_age_days=10,
        patient_age_months=0.33,
        patient_weight_kg=3.5,
        patient_unit="NICU",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - CRITICAL ISSUES
    elements_data = [
        ("hsv_csf_pcr", "CSF HSV PCR", "met", "Sent", "LP done at 15:30"),
        ("hsv_surface_cultures", "Surface cultures (SEM)", "met", "Collected", "Conjunctiva, mouth, rectum"),
        ("hsv_blood_pcr", "Blood HSV PCR", "met", "Sent", "Collected with blood cx"),
        ("hsv_lfts", "LFTs obtained", "met", "ALT 45, AST 52", "Mildly elevated"),
        ("hsv_acyclovir_started", "Acyclovir started", "not_met", None, "NOT GIVEN - 3 HOURS ELAPSED"),
        ("hsv_acyclovir_dose", "Acyclovir 60 mg/kg/day Q8H", "pending", None, "Awaiting acyclovir start"),
        ("hsv_id_consult", "ID consult", "met", "Placed", "ID to see within 2h"),
        ("hsv_neuroimaging", "Neuroimaging (CNS suspected)", "pending", None, "MRI scheduled"),
    ]

    print("    Element Status:")
    met_count = 0
    not_met_count = 0
    pending_count = 0

    for elem_id, elem_name, status, value, notes in elements_data:
        time_window = 1.0 if "acyclovir_started" in elem_id else 4.0
        if "consult" in elem_id:
            time_window = 24.0
        if "neuroimaging" in elem_id:
            time_window = 48.0

        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=time_window,
            deadline=trigger_time + timedelta(hours=time_window),
            completed_at=trigger_time + timedelta(minutes=45) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)

        if status == "met":
            met_count += 1
        elif status == "not_met":
            not_met_count += 1
        else:
            pending_count += 1

    # Create CRITICAL alert for missing acyclovir
    alert = BundleAlert(
        episode_id=episode_id,
        patient_id="PT-HSV-003",
        patient_mrn="HSV-2024-003",
        encounter_id="ENC-HSV-003",
        bundle_id="neonatal_hsv_2024",
        bundle_name="Neonatal HSV Bundle",
        element_id="hsv_acyclovir_started",
        element_name="Acyclovir started",
        alert_type="element_overdue",
        severity="critical",
        title="URGENT: Acyclovir NOT started - HSV suspected",
        message=f"Neonatal HSV suspected with vesicles and seizure. Acyclovir required within 1 hour but NOT YET GIVEN. "
                f"Time elapsed: 3 hours. Risk factors: vesicular rash, seizures. "
                f"ACTION REQUIRED: Start IV acyclovir 20 mg/kg Q8H immediately.",
    )
    db.save_alert(alert)

    # Update episode stats
    applicable = len(elements_data) - pending_count
    adherence_pct = (met_count / applicable * 100) if applicable > 0 else 0

    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = applicable
    episode.elements_met = met_count
    episode.elements_not_met = not_met_count
    episode.elements_pending = pending_count
    episode.adherence_percentage = adherence_pct
    episode.adherence_level = "low"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{applicable} (+ {pending_count} pending)
    - Adherence: {adherence_pct:.0f}%
    - Level: {episode.adherence_level.upper()}

    *** CRITICAL ALERT ***
    Acyclovir NOT started in neonate with suspected HSV!
    - Vesicular rash present
    - Seizure documented
    - 3 hours elapsed (target: 1 hour)
    - Mortality risk increases with treatment delay

    ACTION: Start IV acyclovir 20 mg/kg Q8H IMMEDIATELY
    """)

    return episode_id


def create_febrile_infant_ill_episode(
    db: EpisodeDB,
    fhir_client: HAPIGuidelineFHIRClient | None = None,
) -> int:
    """Create a febrile infant episode - ILL-APPEARING.

    Patient: 10-day-old with fever and poor appearance
    Expected: High-risk management path
    """
    print_subheader("Patient 4: Febrile Infant - Ill-Appearing (10 days old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=1)
    mrn = "FI-2024-004"
    patient_id = "PT-FI-004"
    birth_date = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    # Create FHIR patient with clinical notes if client provided
    if fhir_client:
        print("  Creating FHIR resources...")
        patient_id = create_fhir_patient_with_notes(
            fhir_client=fhir_client,
            mrn=mrn,
            given_name="Baby",
            family_name="IllAppearing",
            birth_date=birth_date,
            gender="male",
            notes_key="febrile_infant_ill",
            note_time=trigger_time,
        )

    print(f"""
    MRN: {mrn}
    Age: 10 days
    Chief Complaint: Fever (39.2°C), lethargy
    Presentation: ILL-APPEARING - mottled, hypotonic, poor feeding
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')}

    Bundle: Febrile Infant (8-60 days) - AAP 2021 Guideline
    Age Group: 8-21 days (requires LP, admission, IV antibiotics)
    Clinical Appearance: ILL - high-risk management
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id=patient_id,
        patient_mrn=mrn,
        encounter_id="ENC-FI-004",
        bundle_id="febrile_infant_2024",
        bundle_name="Febrile Infant Bundle (0-60 days)",
        trigger_type="diagnosis",
        trigger_code="R50.9",
        trigger_description="Fever, unspecified",
        trigger_time=trigger_time,
        patient_age_days=10,
        patient_age_months=0.33,
        patient_unit="Pediatric Emergency",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - elements tracked
    bundle = GUIDELINE_BUNDLES["febrile_infant_2024"]

    elements_data = [
        ("fi_ua", "Urinalysis obtained", "met", "Pending", "Cath specimen"),
        ("fi_blood_culture", "Blood culture obtained", "met", "Collected 08:15", "Before antibiotics"),
        ("fi_inflammatory_markers", "Inflammatory markers obtained", "met", "ANC 15000, CRP 8.5", "Elevated"),
        ("fi_lp_8_21d", "LP performed (8-21 days)", "met", "WBC 45, protein 120", "Concerning CSF"),
        ("fi_abx_8_21d", "Parenteral antibiotics (8-21 days)", "met", "Ampicillin + Gentamicin + Acyclovir", "Given at 08:30"),
        ("fi_hsv_risk_assessment", "HSV risk assessment", "met", "Acyclovir added empirically", "Ill appearance"),
        ("fi_admit_8_21d", "Hospital admission (8-21 days)", "met", "Admitted to PICU", "Critical care"),
    ]

    print("    Element Status:")
    met_count = 0
    for elem_id, elem_name, status, value, notes in elements_data:
        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=2.0,
            deadline=trigger_time + timedelta(hours=2),
            completed_at=trigger_time + timedelta(minutes=30) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)
        if status == "met":
            met_count += 1

    # Update episode with adherence stats
    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = len(elements_data)
    episode.elements_met = met_count
    episode.elements_not_met = 0
    episode.elements_pending = len(elements_data) - met_count
    episode.adherence_percentage = (met_count / len(elements_data)) * 100
    episode.adherence_level = "full" if episode.adherence_percentage == 100 else "partial"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{len(elements_data)}
    - Adherence: {episode.adherence_percentage:.0f}%
    - Level: {episode.adherence_level.upper()}
    - Note: ILL-APPEARING infant - appropriately escalated care
    """)

    return episode_id


def create_cdiff_testing_episode(
    db: EpisodeDB,
    fhir_client: HAPIGuidelineFHIRClient | None = None,
) -> int:
    """Create a C. diff testing appropriateness episode.

    Patient: 8-year-old with diarrhea, recent antibiotics
    Scenario: Testing appropriateness check (diagnostic stewardship)
    """
    print_subheader("Patient 5: C. diff Testing Appropriateness (8 years old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=1)

    print(f"""
    MRN: CDIFF-2024-004
    Age: 8 years
    Chief Complaint: Watery diarrhea x 3 days
    History: Completed amoxicillin course 5 days ago (for strep throat)
    Stool Count: 5 liquid stools in 24 hours

    Bundle: C. diff Testing Appropriateness (Diagnostic Stewardship)
    Purpose: Verify testing criteria met before resulting
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id="PT-CDIFF-004",
        patient_mrn="CDIFF-2024-004",
        encounter_id="ENC-CDIFF-004",
        bundle_id="cdiff_testing_2024",
        bundle_name="C. diff Testing Appropriateness Bundle",
        trigger_type="lab",
        trigger_code="C_DIFF_PCR",
        trigger_description="C. diff PCR test ordered",
        trigger_time=trigger_time,
        patient_age_days=2920,
        patient_age_months=96,
        patient_unit="Pediatric Unit",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Check appropriateness criteria - ALL MET (appropriate test)
    elements_data = [
        ("cdiff_age_appropriate", "Age ≥3 years", "met", "8 years", "Meets age criteria"),
        ("cdiff_liquid_stools", "≥3 liquid stools/24h", "met", "5 stools", "Documented in nursing notes"),
        ("cdiff_no_laxatives", "No laxatives 48h", "met", "None given", "MAR reviewed"),
        ("cdiff_no_contrast", "No enteral contrast 48h", "met", "None given", "No recent imaging"),
        ("cdiff_no_tube_feed_changes", "No tube feed changes", "na", None, "Not on tube feeds"),
        ("cdiff_no_gi_bleed", "No active GI bleed", "met", "No blood", "Stools non-bloody"),
        ("cdiff_risk_factor_present", "Risk factor present", "met", "Recent antibiotics", "Amoxicillin 5 days ago"),
        ("cdiff_symptom_duration", "Symptoms persist 48h", "met", "3 days", "Symptoms x 72 hours"),
    ]

    print("    Appropriateness Criteria:")
    met_count = 0
    na_count = 0

    for elem_id, elem_name, status, value, notes in elements_data:
        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=status != "na",
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)

        if status == "met":
            met_count += 1
        elif status == "na":
            na_count += 1

    applicable = len(elements_data) - na_count
    adherence_pct = (met_count / applicable * 100) if applicable > 0 else 0

    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = applicable
    episode.elements_met = met_count
    episode.elements_not_met = 0
    episode.elements_pending = 0
    episode.adherence_percentage = adherence_pct
    episode.adherence_level = "full"
    episode.status = "completed"
    db.save_episode(episode)

    print(f"""
    Appropriateness Assessment:
    - Criteria Met: {met_count}/{applicable}
    - Score: {adherence_pct:.0f}%
    - Classification: APPROPRIATE TEST

    Test may proceed - all diagnostic stewardship criteria satisfied:
    - Age appropriate (≥3 years)
    - Symptomatic (≥3 liquid stools)
    - No confounders (laxatives, contrast, GI bleed)
    - Risk factor present (recent antibiotics)
    - Symptoms persistent (>48 hours)
    """)

    return episode_id


def display_dashboard_summary(db: EpisodeDB):
    """Display a summary dashboard of all episodes."""
    print_header("GUIDELINE ADHERENCE DASHBOARD SUMMARY")

    # Get all episodes
    episodes = db.get_active_episodes(limit=10)
    if not episodes:
        # Try to get any episodes including completed
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bundle_episodes ORDER BY created_at DESC LIMIT 10")
            episodes = [db._row_to_episode(row) for row in cursor.fetchall()]

    print(f"\n  Active/Recent Episodes: {len(episodes)}")
    print("\n  " + "-" * 66)
    print(f"  {'MRN':<15} {'Bundle':<25} {'Adherence':<12} {'Status':<10}")
    print("  " + "-" * 66)

    for ep in episodes:
        mrn = ep.patient_mrn or ep.patient_id[:12]
        bundle_name = (ep.bundle_name or ep.bundle_id)[:23]
        adherence = f"{ep.adherence_percentage or 0:.0f}%"
        level = ep.adherence_level or "unknown"

        # Color coding simulation with text
        level_indicator = {
            "full": "(FULL)",
            "partial": "(PART)",
            "low": "(LOW!)",
        }.get(level, "")

        print(f"  {mrn:<15} {bundle_name:<25} {adherence:<12} {level_indicator:<10}")

    # Get active alerts
    alerts = db.get_active_alerts(limit=10)

    print(f"\n  Active Alerts: {len(alerts)}")
    if alerts:
        print("\n  " + "-" * 66)
        print(f"  {'Severity':<10} {'Bundle':<20} {'Element':<25}")
        print("  " + "-" * 66)

        for alert in alerts:
            severity = alert.severity.upper()
            bundle = (alert.bundle_name or "")[:18]
            element = (alert.element_name or "")[:23]
            print(f"  {severity:<10} {bundle:<20} {element:<25}")

    # Adherence stats
    stats = db.get_adherence_stats(days=30)
    if stats:
        print(f"\n  Adherence Statistics (Last 30 Days):")
        print("  " + "-" * 66)
        for bundle_id, s in stats.items():
            name = (s.get("bundle_name") or bundle_id)[:30]
            total = s.get("total_episodes", 0)
            avg = s.get("avg_adherence_pct") or s.get("avg_adherence") or 0
            print(f"  {name}: {total} episodes, {avg:.1f}% avg adherence")


def run_demo(db_path: str, persist: bool = False, use_fhir: bool = False):
    """Run the demo with specified database."""
    # Initialize database
    db = EpisodeDB(db_path)

    # Initialize FHIR client if requested
    fhir_client = None
    if use_fhir:
        try:
            fhir_client = HAPIGuidelineFHIRClient()
            # Test connection
            fhir_client.get("metadata")
            print("  Connected to FHIR server at:", fhir_client.base_url)
        except Exception as e:
            print(f"  WARNING: Could not connect to FHIR server: {e}")
            print("  Continuing without FHIR resources...")
            fhir_client = None

    # Create patient scenarios
    create_febrile_infant_episode(db, fhir_client)
    create_sepsis_episode(db, fhir_client)
    create_neonatal_hsv_episode(db, fhir_client)
    create_febrile_infant_ill_episode(db, fhir_client)
    create_cdiff_testing_episode(db, fhir_client)

    # Display summary dashboard
    display_dashboard_summary(db)

    print_header("DEMO COMPLETE")
    print("""
    Key Observations:

    1. FEBRILE INFANT (Well-Appearing): 100% adherence
       - LP performed (required for 8-21 days)
       - Parenteral antibiotics given
       - HSV risk assessed (no risk factors)
       - Admitted per guideline
       - LLM should identify: WELL-APPEARING

    2. SEPSIS: 60% adherence - critical delays identified
       - ALERT: Antibiotic delay (80 min vs 60 min target)
       - ALERT: Repeat lactate not obtained
       - Fluid resuscitation met
       - LLM should identify: ILL-APPEARING (septic shock)

    3. NEONATAL HSV: 71% adherence - CRITICAL safety issue
       - CRITICAL: Acyclovir not started (3 hours elapsed!)
       - Workup appropriately sent (CSF, blood, surface cultures)
       - ID consulted
       - LLM should identify: ILL-APPEARING (seizures, vesicles)

    4. FEBRILE INFANT (Ill-Appearing): 100% adherence
       - High-risk management appropriately initiated
       - PICU admission
       - Empiric acyclovir added
       - LLM should identify: ILL-APPEARING

    5. C. DIFF TESTING: 100% criteria met - appropriate test
       - All diagnostic stewardship criteria satisfied
       - Recent antibiotics = valid risk factor
       - Symptomatic with liquid stools

    This system enables:
    - Real-time monitoring of guideline adherence
    - Automated alerts for missed elements
    - LLM extraction of clinical appearance from notes
    - Compliance metrics for QI dashboards
    """)

    if persist:
        print(f"""
    Data persisted to: {db_path}
    View in dashboard: http://localhost:8082/guideline-adherence/active
        """)
    if use_fhir:
        print("""
    FHIR resources created:
    - Patient resources with MRNs
    - DocumentReference resources with clinical notes
    - Notes available for LLM analysis via get_recent_notes()
        """)


def main():
    """Run the demo."""
    parser = argparse.ArgumentParser(description="Guideline Adherence Demo")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist data to real database (for dashboard viewing)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing demo data before creating new episodes",
    )
    parser.add_argument(
        "--fhir",
        action="store_true",
        help="Create FHIR resources (Patient, DocumentReference) with clinical notes",
    )
    args = parser.parse_args()

    print_header("AEGIS GUIDELINE ADHERENCE MONITORING - DEMO")

    print("""
    This demo creates sample patient scenarios to demonstrate the
    guideline adherence monitoring system.

    Patients:
    1. Febrile Infant - Well-Appearing (14 days) - Full adherence
    2. Sepsis (3 years) - Partial adherence with alerts
    3. Neonatal HSV (10 days) - Critical alert scenario
    4. Febrile Infant - Ill-Appearing (10 days) - High-risk management
    5. C. diff Testing (8 years) - Diagnostic stewardship
    """)

    if args.fhir:
        print("  FHIR mode: Will create Patient and DocumentReference resources")
        print("             Clinical notes will be stored in FHIR for LLM parsing")

    if args.persist:
        # Use real database
        from guideline_src.config import Config
        db_path = str(Config.ADHERENCE_DB_PATH)
        print(f"  Using persistent database: {db_path}")

        demo_mrns = ["FI-2024-001", "SEP-2024-002", "HSV-2024-003", "FI-2024-004", "CDIFF-2024-004"]

        if args.clear:
            # Clear existing demo data from SQLite
            import sqlite3
            conn = sqlite3.connect(db_path)
            for mrn in demo_mrns:
                conn.execute("DELETE FROM bundle_alerts WHERE episode_id IN (SELECT id FROM bundle_episodes WHERE patient_mrn = ?)", (mrn,))
                conn.execute("DELETE FROM bundle_element_results WHERE episode_id IN (SELECT id FROM bundle_episodes WHERE patient_mrn = ?)", (mrn,))
                conn.execute("DELETE FROM episode_assessments WHERE episode_id IN (SELECT id FROM bundle_episodes WHERE patient_mrn = ?)", (mrn,))
                conn.execute("DELETE FROM episode_reviews WHERE episode_id IN (SELECT id FROM bundle_episodes WHERE patient_mrn = ?)", (mrn,))
                conn.execute("DELETE FROM bundle_episodes WHERE patient_mrn = ?", (mrn,))
            conn.commit()
            conn.close()
            print("  Cleared existing demo data from SQLite")

            # Clear FHIR data if FHIR mode
            if args.fhir:
                try:
                    fhir_client = HAPIGuidelineFHIRClient()
                    clear_fhir_demo_patients(fhir_client, demo_mrns)
                except Exception as e:
                    print(f"  Could not clear FHIR data: {e}")

        run_demo(db_path, persist=True, use_fhir=args.fhir)
    else:
        # Use temporary database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "demo_guideline_adherence.db")
            print(f"  Demo database: {db_path}")
            run_demo(db_path, persist=False, use_fhir=args.fhir)


if __name__ == "__main__":
    main()
