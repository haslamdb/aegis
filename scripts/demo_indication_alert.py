#!/usr/bin/env python3
"""Generate demo patients for antibiotic indication alert testing.

Creates patients with antibiotics, ICD-10 diagnoses, and clinical notes
that will trigger (or not trigger) indication alerts.

The monitor prioritizes clinical notes over ICD-10 codes since:
- ICD-10 codes may be stale (from previous encounters)
- Notes reflect real-time clinical reasoning
- Notes capture nuance that codes cannot

Usage:
    # Create patient with ceftriaxone for viral URI (N = Never appropriate -> ALERT)
    python demo_indication_alert.py --scenario viral-uri-ceftriaxone

    # Create patient with misleading ICD-10 but note says pneumonia (note wins -> no alert)
    python demo_indication_alert.py --scenario note-overrides-icd10

    # Create patient with good ICD-10 but note says viral (note wins -> ALERT)
    python demo_indication_alert.py --scenario note-contradicts-icd10

    # List available scenarios
    python demo_indication_alert.py --list
"""

import argparse
import base64
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

FHIR_URL = "http://localhost:8081/fhir"

# Antibiotics with RxNorm codes
ANTIBIOTICS = {
    "ceftriaxone": {"code": "309090", "display": "Ceftriaxone", "dose": "50 mg/kg IV"},
    "vancomycin": {"code": "11124", "display": "Vancomycin", "dose": "15 mg/kg IV"},
    "meropenem": {"code": "29561", "display": "Meropenem", "dose": "40 mg/kg IV"},
    "ampicillin": {"code": "733", "display": "Ampicillin", "dose": "50 mg/kg IV"},
    "cefazolin": {"code": "309092", "display": "Cefazolin", "dose": "25 mg/kg IV"},
    "metronidazole": {"code": "6922", "display": "Metronidazole", "dose": "10 mg/kg IV"},
}

# ICD-10 codes with expected classifications for common antibiotics
ICD10_CODES = {
    # Viral/inappropriate for antibiotics (N = Never)
    "J06.9": {"display": "Acute upper respiratory infection, unspecified", "category": "N"},
    "J00": {"display": "Acute nasopharyngitis (common cold)", "category": "N"},
    "J11.1": {"display": "Influenza with other respiratory manifestations", "category": "N"},
    "B34.9": {"display": "Viral infection, unspecified", "category": "N"},

    # Bacterial infections (A = Always or S = Sometimes appropriate)
    "J18.9": {"display": "Pneumonia, unspecified organism", "category": "A"},
    "J15.9": {"display": "Bacterial pneumonia, unspecified", "category": "A"},
    "N39.0": {"display": "Urinary tract infection, site not specified", "category": "A"},
    "A41.9": {"display": "Sepsis, unspecified organism", "category": "A"},
    "L03.90": {"display": "Cellulitis, unspecified", "category": "A"},
    "K65.9": {"display": "Peritonitis, unspecified", "category": "A"},

    # Surgical prophylaxis (P = Prophylaxis)
    "Z51.81": {"display": "Encounter for therapeutic drug monitoring", "category": "P"},
}

# Clinical note templates
# These are used by the LLM to extract indications
CLINICAL_NOTES = {
    "pneumonia": """
PROGRESS NOTE - {date}
Provider: Dr. Smith, Pediatric Hospitalist

S: 5 year old with 3 days of fever, cough, and increased work of breathing.
   Parents report decreased oral intake and lethargy.

O: T 39.2, HR 130, RR 32, SpO2 94% on RA
   Lungs: Decreased breath sounds RLL, crackles
   CXR: Right lower lobe infiltrate consistent with pneumonia

A/P:
1. Community-acquired pneumonia
   - Started on Ceftriaxone 50mg/kg IV q24h for bacterial pneumonia coverage
   - Will monitor respiratory status closely
   - Blood culture pending
""",

    "viral_uri": """
PROGRESS NOTE - {date}
Provider: Dr. Johnson, Pediatric Hospitalist

S: 3 year old with 2 days of runny nose, congestion, and low-grade fever.
   No respiratory distress. Good oral intake.

O: T 37.8, HR 110, RR 24, SpO2 99% on RA
   HEENT: Clear rhinorrhea, mild pharyngeal erythema, TMs normal
   Lungs: Clear bilaterally, no wheezes or crackles
   CXR: No infiltrate or consolidation

A/P:
1. Viral upper respiratory infection
   - Supportive care, antipyretics as needed
   - Antibiotics NOT indicated - viral etiology
   - Reassurance to family about expected course
""",

    "viral_with_abx": """
PROGRESS NOTE - {date}
Provider: Dr. Williams, Pediatric Hospitalist

S: 4 year old admitted with URI symptoms. Parents very anxious, requesting antibiotics.

O: T 37.5, HR 105, RR 22, SpO2 100% on RA
   Exam consistent with viral syndrome - rhinorrhea, mild cough
   CXR clear, no bacterial source identified
   Rapid flu negative, RSV negative

A/P:
1. Viral upper respiratory infection - LIKELY VIRAL ETIOLOGY
   - Started Ceftriaxone per family request despite viral presentation
   - Will discuss antibiotic stewardship with family
   - Plan to discontinue antibiotics if cultures negative at 48h
   - This is likely inappropriate antibiotic use
""",

    "sepsis": """
PROGRESS NOTE - {date}
Provider: Dr. Chen, PICU Attending

S: 8 year old transferred from ED with fever, tachycardia, and hypotension.
   Ill-appearing, required fluid resuscitation.

O: T 40.1, HR 165, BP 75/40, RR 35, SpO2 92% on 4L NC
   Lactate 4.2, WBC 22k with 15% bands
   Appearing toxic, delayed capillary refill

A/P:
1. Sepsis, suspected bacterial source
   - Broad spectrum coverage initiated: Meropenem + Vancomycin
   - Aggressive fluid resuscitation
   - Blood cultures x2 drawn prior to antibiotics
   - Source workup in progress
""",

    "uti": """
PROGRESS NOTE - {date}
Provider: Dr. Park, Pediatric Hospitalist

S: 2 year old with fever x2 days, foul-smelling urine, decreased appetite.
   History of prior UTI at 6 months.

O: T 38.9, HR 125, RR 26
   Abd: Mild suprapubic tenderness
   UA: Positive nitrites, >100 WBC, bacteria present
   Urine culture pending

A/P:
1. Urinary tract infection, likely bacterial
   - Started Ceftriaxone IV for pyelonephritis coverage
   - Will narrow based on culture sensitivities
   - Renal ultrasound ordered given recurrent UTI
""",

    "no_indication_documented": """
PROGRESS NOTE - {date}
Provider: Dr. Lee, Pediatric Hospitalist

S: 6 year old admitted for observation after minor head injury.
   No fever, no infectious symptoms.

O: T 36.8, HR 90, RR 18, SpO2 100% on RA
   Neuro exam intact, GCS 15
   No signs of infection

A/P:
1. Minor closed head injury - neuro checks stable
2. Started on Vancomycin (reason not documented)
   - No clear indication for antibiotic therapy
   - Will clarify with day team
""",

    "cellulitis": """
PROGRESS NOTE - {date}
Provider: Dr. Garcia, Pediatric Hospitalist

S: 10 year old with spreading redness and swelling of left lower leg x3 days.
   Scratched leg on playground equipment last week.

O: T 38.2, HR 115, RR 20
   Left lower leg: 8x10cm area of erythema, warmth, induration
   No crepitus, no fluctuance
   Marked demarcation with Sharpie

A/P:
1. Cellulitis, left lower extremity
   - Started Cefazolin IV for skin/soft tissue coverage
   - Leg elevation, warm compresses
   - Mark borders to monitor progression
""",
}

# Pre-defined test scenarios
SCENARIOS = {
    # === ICD-10 only scenarios (no notes) ===
    "viral-uri-ceftriaxone": {
        "description": "Ceftriaxone for viral URI (ICD-10 only) - should trigger N alert",
        "antibiotic": "ceftriaxone",
        "icd10_codes": ["J06.9"],
        "note_template": None,
        "expected": "N (alert)",
    },
    "pneumonia-ceftriaxone": {
        "description": "Ceftriaxone for pneumonia (ICD-10 only) - appropriate, no alert",
        "antibiotic": "ceftriaxone",
        "icd10_codes": ["J18.9"],
        "note_template": None,
        "expected": "A (no alert)",
    },

    # === Note-based scenarios (notes override ICD-10) ===
    "note-pneumonia": {
        "description": "Note documents pneumonia - appropriate even without ICD-10",
        "antibiotic": "ceftriaxone",
        "icd10_codes": [],  # No ICD-10
        "note_template": "pneumonia",
        "expected": "A via note (no alert)",
    },
    "note-overrides-icd10": {
        "description": "ICD-10 says viral, but note documents pneumonia - note wins",
        "antibiotic": "ceftriaxone",
        "icd10_codes": ["J06.9"],  # Viral URI code
        "note_template": "pneumonia",  # But note says pneumonia
        "expected": "A via note (no alert - note overrides)",
    },
    "note-contradicts-icd10": {
        "description": "ICD-10 says pneumonia, but note says viral - note wins -> ALERT",
        "antibiotic": "ceftriaxone",
        "icd10_codes": ["J18.9"],  # Pneumonia code
        "note_template": "viral_with_abx",  # But note says viral
        "expected": "N via note (ALERT - note overrides)",
    },
    "note-viral-uri": {
        "description": "Note explicitly documents viral illness with inappropriate abx",
        "antibiotic": "ceftriaxone",
        "icd10_codes": [],
        "note_template": "viral_with_abx",
        "expected": "N via note (ALERT)",
    },
    "note-sepsis": {
        "description": "Note documents sepsis requiring broad spectrum",
        "antibiotic": "meropenem",
        "icd10_codes": ["A41.9"],
        "note_template": "sepsis",
        "expected": "A via note (no alert)",
    },
    "note-uti": {
        "description": "Note documents UTI with appropriate antibiotic",
        "antibiotic": "ceftriaxone",
        "icd10_codes": ["N39.0"],
        "note_template": "uti",
        "expected": "A via note (no alert)",
    },
    "note-no-indication": {
        "description": "Note explicitly says no indication documented",
        "antibiotic": "vancomycin",
        "icd10_codes": [],
        "note_template": "no_indication_documented",
        "expected": "N via note (ALERT)",
    },
    "note-cellulitis": {
        "description": "Note documents cellulitis with cefazolin",
        "antibiotic": "cefazolin",
        "icd10_codes": ["L03.90"],
        "note_template": "cellulitis",
        "expected": "A via note (no alert)",
    },

    # === Legacy scenarios ===
    "no-diagnosis": {
        "description": "Vancomycin with no diagnosis or notes - unknown",
        "antibiotic": "vancomycin",
        "icd10_codes": [],
        "note_template": None,
        "expected": "U (no alert - unknown)",
    },
}


def generate_mrn() -> str:
    """Generate a demo MRN."""
    return f"IND{random.randint(10000, 99999)}"


def create_patient(mrn: str) -> dict:
    """Create a Patient FHIR resource."""
    first_names = ["Indication", "Demo", "Test", "Alert"]
    last_names = ["Patient", "Case", "Subject"]

    age_days = random.randint(365, 6570)  # 1-18 years
    birth_date = datetime.now() - timedelta(days=age_days)

    return {
        "resourceType": "Patient",
        "id": str(uuid.uuid4()),
        "identifier": [{
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]},
            "value": mrn,
        }],
        "name": [{"family": random.choice(last_names), "given": [random.choice(first_names)]}],
        "gender": random.choice(["male", "female"]),
        "birthDate": birth_date.strftime("%Y-%m-%d"),
    }


def create_condition(patient_id: str, icd10_code: str) -> dict:
    """Create a Condition FHIR resource with ICD-10 code."""
    icd10_info = ICD10_CODES.get(icd10_code, {"display": icd10_code, "category": "U"})

    return {
        "resourceType": "Condition",
        "id": str(uuid.uuid4()),
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
        },
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]
        },
        "code": {
            "coding": [{
                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                "code": icd10_code,
                "display": icd10_info["display"],
            }],
            "text": icd10_info["display"],
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "onsetDateTime": datetime.now(timezone.utc).isoformat(),
    }


def create_medication_request(patient_id: str, antibiotic_key: str, hours_ago: float = 2) -> dict:
    """Create a MedicationRequest FHIR resource."""
    abx = ANTIBIOTICS[antibiotic_key]
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    return {
        "resourceType": "MedicationRequest",
        "id": str(uuid.uuid4()),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "code": abx["code"],
                "display": abx["display"],
            }],
            "text": abx["display"],
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": start_time.isoformat(),
        "dosageInstruction": [{"text": abx["dose"]}],
    }


def create_encounter(patient_id: str) -> dict:
    """Create an inpatient Encounter."""
    admission_time = datetime.now(timezone.utc) - timedelta(hours=24)

    return {
        "resourceType": "Encounter",
        "id": str(uuid.uuid4()),
        "status": "in-progress",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "IMP",
            "display": "inpatient encounter",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "period": {"start": admission_time.isoformat()},
    }


def create_document_reference(patient_id: str, note_template: str) -> dict:
    """Create a DocumentReference FHIR resource with clinical note.

    Args:
        patient_id: FHIR patient ID
        note_template: Key from CLINICAL_NOTES dict

    Returns:
        FHIR DocumentReference resource
    """
    note_text = CLINICAL_NOTES.get(note_template, "")
    if not note_text:
        return None

    # Format the note with current date
    note_date = datetime.now(timezone.utc) - timedelta(hours=4)
    formatted_note = note_text.format(date=note_date.strftime("%Y-%m-%d %H:%M"))

    # Base64 encode the note content
    note_bytes = formatted_note.encode("utf-8")
    note_b64 = base64.b64encode(note_bytes).decode("ascii")

    return {
        "resourceType": "DocumentReference",
        "id": str(uuid.uuid4()),
        "status": "current",
        "type": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "11506-3",
                "display": "Progress note",
            }],
            "text": "Progress Note",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "date": note_date.isoformat(),
        "author": [{
            "display": "Pediatric Hospitalist",
        }],
        "content": [{
            "attachment": {
                "contentType": "text/plain",
                "data": note_b64,
                "title": "Progress Note",
            }
        }],
    }


def upload_resource(resource: dict, fhir_url: str) -> bool:
    """Upload a resource to the FHIR server."""
    url = f"{fhir_url}/{resource['resourceType']}/{resource['id']}"
    try:
        response = requests.put(url, json=resource, headers={"Content-Type": "application/fhir+json"})
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def list_scenarios():
    """List all available scenarios."""
    print("\nAvailable test scenarios:\n")
    for name, scenario in SCENARIOS.items():
        print(f"  {name}")
        print(f"    {scenario['description']}")
        print(f"    Antibiotic: {scenario['antibiotic']}")
        print(f"    ICD-10: {scenario['icd10_codes'] or '(none)'}")
        print(f"    Expected: {scenario['expected']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Generate demo patients for indication alert testing")
    parser.add_argument("--scenario", "-s", choices=list(SCENARIOS.keys()), help="Predefined scenario")
    parser.add_argument("--list", "-l", action="store_true", help="List available scenarios")
    parser.add_argument("--fhir-url", default=FHIR_URL, help="FHIR server URL")
    parser.add_argument("--dry-run", action="store_true", help="Print without uploading")
    parser.add_argument("--all", "-a", action="store_true", help="Create all scenarios")

    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return 0

    if args.all:
        scenarios_to_run = list(SCENARIOS.keys())
    elif args.scenario:
        scenarios_to_run = [args.scenario]
    else:
        parser.error("Either --scenario, --all, or --list required")

    for scenario_name in scenarios_to_run:
        scenario = SCENARIOS[scenario_name]

        print(f"\n{'='*60}")
        print(f"SCENARIO: {scenario_name}")
        print(f"{'='*60}")
        print(f"Description: {scenario['description']}")
        print(f"Expected:    {scenario['expected']}")

        mrn = generate_mrn()
        patient = create_patient(mrn)
        patient_id = patient["id"]
        patient_name = f"{patient['name'][0]['given'][0]} {patient['name'][0]['family']}"

        print(f"\nPatient:     {patient_name} (MRN: {mrn})")
        print(f"Antibiotic:  {ANTIBIOTICS[scenario['antibiotic']]['display']}")
        print(f"ICD-10:      {scenario['icd10_codes'] or '(none)'}")
        print(f"Note:        {scenario.get('note_template') or '(none)'}")

        if args.dry_run:
            print("\n[DRY RUN - not uploading]")
            if scenario.get("note_template"):
                note_preview = CLINICAL_NOTES.get(scenario["note_template"], "")[:200]
                print(f"\nNote preview:\n{note_preview}...")
            continue

        # Upload resources
        print(f"\nUploading to {args.fhir_url}...")

        resources = [patient, create_encounter(patient_id)]

        # Add conditions for each ICD-10 code
        for code in scenario["icd10_codes"]:
            resources.append(create_condition(patient_id, code))

        # Add clinical note if specified
        if scenario.get("note_template"):
            doc_ref = create_document_reference(patient_id, scenario["note_template"])
            if doc_ref:
                resources.append(doc_ref)

        # Add medication request
        resources.append(create_medication_request(patient_id, scenario["antibiotic"]))

        for resource in resources:
            rtype = resource["resourceType"]
            if upload_resource(resource, args.fhir_url):
                print(f"  + {rtype}")
            else:
                print(f"  x {rtype} FAILED")
                return 1

        print(f"\nCreated: {patient_name} (MRN: {mrn})")

    print(f"\n{'='*60}")
    print("Run indication monitor to see alerts:")
    print("  cd antimicrobial-usage-alerts")
    print("  python -m src.runner --indication --once")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
