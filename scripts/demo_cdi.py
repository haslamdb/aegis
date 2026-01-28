#!/usr/bin/env python3
"""Generate demo CDI (C. difficile Infection) candidates for dashboard demonstration.

Creates scenarios:
1. HO-CDI (Hospital Onset) - Positive C. diff test >3 days after admission
2. CO-CDI (Community Onset) - Positive C. diff test ≤3 days after admission
3. Not CDI - Negative test or asymptomatic colonization

NHSN CDI Criteria:
- Positive NAAT/PCR for toxin-producing C. difficile, OR
- Positive toxin A/B test (EIA)
- HO-CDI: >3 days after admission (day 4+)
- CO-CDI: ≤3 days after admission (day 1-3)

Note: This facility uses NAAT/PCR-only testing (no toxin EIA or GDH screening).
Demo scenarios default to PCR test type.

Usage:
    # Create one HO-CDI + one CO-CDI case
    python demo_cdi.py

    # Create specific scenario types
    python demo_cdi.py --scenario ho-cdi
    python demo_cdi.py --scenario co-cdi
    python demo_cdi.py --scenario negative

    # Dry run (don't upload to FHIR)
    python demo_cdi.py --dry-run
"""

import argparse
import base64
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

# FHIR server
DEFAULT_FHIR_URL = "http://localhost:8081/fhir"

# Locations
LOCATIONS = [
    {"code": "A6N", "display": "Hospital Medicine"},
    {"code": "G5S", "display": "Oncology"},
    {"code": "T5A", "display": "PICU"},
    {"code": "SURG", "display": "Surgery Floor"},
]

# Patient names
FIRST_NAMES = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]


def generate_mrn():
    return f"CDI{random.randint(10000, 99999)}"


def create_patient(patient_id: str, mrn: str) -> dict:
    """Create a FHIR Patient resource."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    age_days = random.randint(730, 6570)  # 2-18 years
    birth_date = (datetime.now() - timedelta(days=age_days)).strftime("%Y-%m-%d")

    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [{
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]},
            "value": mrn
        }],
        "name": [{"given": [first_name], "family": last_name}],
        "birthDate": birth_date,
        "gender": random.choice(["male", "female"]),
    }


def create_encounter(encounter_id: str, patient_id: str, location: dict, admit_date: datetime) -> dict:
    """Create a FHIR Encounter resource."""
    return {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "in-progress",
        "class": {"code": "IMP", "display": "inpatient"},
        "subject": {"reference": f"Patient/{patient_id}"},
        "location": [{"location": {"display": location["display"]}}],
        "period": {"start": admit_date.isoformat()},
    }


def create_cdi_test(obs_id: str, patient_id: str, encounter_id: str,
                    test_date: datetime, test_type: str, is_positive: bool) -> dict:
    """Create a FHIR Observation for C. difficile test.

    Args:
        test_type: 'toxin' for toxin A/B test, 'pcr' for molecular test
        is_positive: True for positive result
    """
    if test_type == "toxin":
        code = "34712-0"
        display = "Clostridioides difficile toxin A+B"
    else:  # pcr
        code = "82197-9"
        display = "Clostridioides difficile toxin B gene [Presence] by NAA"

    result_code = "10828004" if is_positive else "260385009"
    result_display = "Positive" if is_positive else "Negative"

    return {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": code,
                "display": display
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": test_date.isoformat(),
        "valueCodeableConcept": {
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": result_code,
                "display": result_display
            }]
        },
        "interpretation": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": "POS" if is_positive else "NEG",
                "display": "Positive" if is_positive else "Negative"
            }]
        }]
    }


def create_clinical_note(doc_id: str, patient_id: str, encounter_id: str,
                         note_date: datetime, note_text: str) -> dict:
    """Create a FHIR DocumentReference with clinical note."""
    encoded = base64.b64encode(note_text.encode()).decode()
    return {
        "resourceType": "DocumentReference",
        "id": doc_id,
        "status": "current",
        "type": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "11506-3",
                "display": "Progress note"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "context": {"encounter": [{"reference": f"Encounter/{encounter_id}"}]},
        "date": note_date.isoformat(),
        "content": [{
            "attachment": {
                "contentType": "text/plain",
                "data": encoded
            }
        }]
    }


# Scenario definitions
SCENARIOS = {
    "ho-cdi": {
        "description": "Hospital-Onset CDI: Positive PCR on day 5 of admission",
        "expected": "HO-CDI (Hospital Onset)",
        "admission_days": 5,  # How long ago patient was admitted
        "test_day": 5,        # Day of test (specimen day)
        "test_type": "pcr",   # NAAT-only testing per facility protocol
        "is_positive": True,
        "note": """Hospital Medicine Progress Note - Hospital Day 5

Assessment: 12-year-old male admitted for pneumonia, now with C. difficile infection.

History:
- Admitted day 1 for community-acquired pneumonia
- Treated with ceftriaxone for 4 days
- Day 4: Developed watery diarrhea (>6 BMs)
- Day 5: C. diff PCR test POSITIVE

Current Symptoms:
- Profuse watery diarrhea (8 episodes yesterday)
- Mild abdominal cramping
- Low-grade fever (38.2°C)
- No blood in stool

Risk Factors:
- Recent antibiotic exposure (ceftriaxone x 4 days)
- Hospitalization

Labs:
- C. difficile PCR (NAAT): POSITIVE
- WBC: 15.8 (elevated)
- Creatinine: normal

Impression:
Hospital-onset C. difficile infection (HO-CDI). Meets NHSN criteria as positive
NAAT obtained >3 calendar days after admission (specimen day 5).

Plan:
- STOP ceftriaxone
- Start oral vancomycin 10mg/kg QID x 10 days
- Contact precautions
- Monitor for complications (toxic megacolon, ileus)
- Infection Prevention notified
"""
    },
    "co-cdi": {
        "description": "Community-Onset CDI: Positive PCR on admission (day 1)",
        "expected": "CO-CDI (Community Onset)",
        "admission_days": 2,
        "test_day": 1,        # Tested on admission
        "test_type": "pcr",
        "is_positive": True,
        "note": """ED Admission Note

Chief Complaint: Diarrhea x 3 days, dehydration

Assessment: 8-year-old female with C. difficile infection, community onset.

History of Present Illness:
- 3 days of profuse watery diarrhea at home
- 10+ bowel movements per day
- Associated abdominal cramping
- Decreased oral intake, appears dehydrated
- Recently completed 10-day course of amoxicillin for strep throat (finished 1 week ago)

Exam:
- Ill-appearing, mildly dehydrated
- Tachycardic, afebrile
- Abdomen: diffusely tender, hyperactive bowel sounds

Labs (collected in ED):
- C. difficile PCR: POSITIVE (resulted)
- Stool WBC: Positive
- BMP: mild hypokalemia

Impression:
Community-onset C. difficile infection (CO-CDI). Positive test obtained ≤3 days
after admission (day 1 - ED). Associated with recent outpatient antibiotic use.

Plan:
- Admit for IV fluids and monitoring
- Start oral vancomycin
- Contact precautions
- Correct electrolytes
"""
    },
    "negative": {
        "description": "Not CDI: Negative C. diff PCR despite diarrhea",
        "expected": "Not CDI - negative test",
        "admission_days": 4,
        "test_day": 4,
        "test_type": "pcr",   # NAAT-only testing per facility protocol
        "is_positive": False,
        "note": """Hospital Medicine Progress Note - Day 4

Assessment: 6-year-old male on chemotherapy with diarrhea, C. diff negative.

History:
- Admitted for febrile neutropenia, on broad-spectrum antibiotics
- Developed loose stools day 3 (likely antibiotic-associated)
- C. diff testing sent due to protocol

Symptoms:
- 3-4 loose stools per day (mild)
- No fever, no abdominal pain
- Tolerating oral intake

Labs:
- C. difficile PCR (NAAT): NEGATIVE
- Stool culture: No enteric pathogens

Impression:
Antibiotic-associated diarrhea, NOT C. difficile. Negative PCR rules out CDI.

Plan:
- Continue antibiotics as indicated for febrile neutropenia
- Supportive care for diarrhea
- No isolation precautions required
- Consider probiotics
"""
    },
    "colonization": {
        "description": "Not CDI: Asymptomatic C. diff colonization (formed stool)",
        "expected": "Not CDI - colonization (not diarrhea)",
        "admission_days": 3,
        "test_day": 3,
        "test_type": "pcr",
        "is_positive": True,
        "note": """Hospital Medicine Progress Note - Day 3

Assessment: 10-year-old with history of C. diff, now colonized but asymptomatic.

History:
- Admitted for elective surgery
- Known history of C. diff infection 6 months ago
- Pre-operative screening PCR positive
- NO DIARRHEA - formed stools, 1x/day

Current Status:
- Completely asymptomatic
- Normal bowel function
- Afebrile
- No abdominal symptoms

Labs:
- C. difficile PCR: POSITIVE (screening)
- Stool is FORMED (not unformed)

Impression:
C. difficile colonization, NOT active infection. Per NHSN guidelines, CDI requires
unformed stool specimen. This formed stool PCR positive represents colonization only
and does NOT qualify as a CDI LabID event.

Plan:
- NO treatment indicated (asymptomatic colonization)
- Proceed with planned surgery
- Standard precautions (not Contact)
- Repeat testing NOT recommended (will remain positive as carrier)
"""
    },
}


def create_cdi_scenario(scenario_key: str, fhir_url: str, dry_run: bool = False):
    """Create a CDI demo scenario."""
    scenario = SCENARIOS[scenario_key]

    # Generate IDs
    patient_id = str(uuid.uuid4())
    encounter_id = str(uuid.uuid4())
    test_id = str(uuid.uuid4())
    note_id = str(uuid.uuid4())
    mrn = generate_mrn()
    location = random.choice(LOCATIONS)

    # Dates
    now = datetime.now(timezone.utc)
    admit_date = now - timedelta(days=scenario["admission_days"])
    test_date = admit_date + timedelta(days=scenario["test_day"] - 1)

    # Create resources
    resources = []

    # Patient and Encounter
    resources.append(create_patient(patient_id, mrn))
    resources.append(create_encounter(encounter_id, patient_id, location, admit_date))

    # C. diff test
    resources.append(create_cdi_test(
        test_id, patient_id, encounter_id, test_date,
        scenario["test_type"], scenario["is_positive"]
    ))

    # Clinical note
    note_date = now - timedelta(hours=2)
    resources.append(create_clinical_note(note_id, patient_id, encounter_id, note_date, scenario["note"]))

    # Print scenario info
    specimen_day = scenario["test_day"]
    onset_type = "HO" if specimen_day > 3 else "CO"

    print(f"\n{'-'*70}")
    print(f"Scenario: {scenario_key.upper()}")
    print(f"{'-'*70}")
    print(f"  Patient MRN:    {mrn}")
    print(f"  Location:       {location['display']}")
    print(f"  Admission:      {scenario['admission_days']} days ago")
    print(f"  Specimen Day:   {specimen_day} ({onset_type if scenario['is_positive'] else 'N/A'})")
    print(f"  Test Type:      {scenario['test_type'].upper()}")
    print(f"  Result:         {'POSITIVE' if scenario['is_positive'] else 'NEGATIVE'}")
    print(f"  Description:    {scenario['description']}")
    print(f"  Expected:       {scenario['expected']}")

    if dry_run:
        print(f"\n  [DRY RUN] Would upload {len(resources)} resources")
        return

    # Upload to FHIR
    print(f"\n  Uploading {len(resources)} resources...")

    session = requests.Session()
    for resource in resources:
        resource_type = resource["resourceType"]
        resource_id = resource["id"]

        response = session.put(
            f"{fhir_url}/{resource_type}/{resource_id}",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
        )

        if response.status_code not in (200, 201):
            print(f"  ERROR uploading {resource_type}/{resource_id}: {response.status_code}")
            print(f"    {response.text[:200]}")
            return

    print(f"  Created successfully")


def main():
    parser = argparse.ArgumentParser(
        description="Generate demo CDI candidates for HAI detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()),
                        help="Specific scenario to create")
    parser.add_argument("--all", action="store_true",
                        help="Create all scenario types")
    parser.add_argument("--fhir-url", default=DEFAULT_FHIR_URL,
                        help=f"FHIR server URL (default: {DEFAULT_FHIR_URL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without uploading")

    args = parser.parse_args()

    # Verify FHIR server connectivity
    if not args.dry_run:
        try:
            response = requests.get(f"{args.fhir_url}/metadata", timeout=5)
            print(f"Connected to FHIR server at {args.fhir_url}")
        except requests.RequestException as e:
            print(f"ERROR: Cannot connect to FHIR server at {args.fhir_url}")
            print(f"  {e}")
            sys.exit(1)

    print("=" * 70)
    print("CDI DEMO SCENARIOS")
    print("=" * 70)

    if args.all:
        for scenario_key in SCENARIOS:
            create_cdi_scenario(scenario_key, args.fhir_url, args.dry_run)
    elif args.scenario:
        create_cdi_scenario(args.scenario, args.fhir_url, args.dry_run)
    else:
        # Default: create one HO-CDI and one CO-CDI case
        create_cdi_scenario("ho-cdi", args.fhir_url, args.dry_run)
        create_cdi_scenario("co-cdi", args.fhir_url, args.dry_run)

    print("\n" + "=" * 70)
    print("\nDemo data created. To see the candidates:")
    print("  1. Run the HAI monitor: cd hai-detection && python -m src.runner --full")
    print("  2. View in dashboard: https://aegis-asp.com/hai-detection/")
    print()


if __name__ == "__main__":
    main()
