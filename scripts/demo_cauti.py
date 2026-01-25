#!/usr/bin/env python3
"""Generate demo CAUTI (Catheter-Associated UTI) candidates for dashboard demonstration.

Creates scenarios:
1. CAUTI case - Patient with catheter >2 days, positive urine culture, and symptoms
2. Not CAUTI case - Asymptomatic bacteriuria (catheter + positive culture but no symptoms)
3. Not CAUTI case - Catheter <2 days

NHSN CAUTI Criteria:
- Indwelling urinary catheter in place >2 calendar days
- Positive urine culture ≥100,000 CFU/mL with ≤2 organisms
- At least one symptom: fever >38C, suprapubic tenderness, CVA pain, urgency, frequency, dysuria

Usage:
    # Create one CAUTI + one Not CAUTI pair
    python demo_cauti.py

    # Create specific scenario types
    python demo_cauti.py --scenario cauti
    python demo_cauti.py --scenario asymptomatic
    python demo_cauti.py --scenario short-catheter

    # Dry run (don't upload to FHIR)
    python demo_cauti.py --dry-run
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
    {"code": "T5A", "display": "PICU"},
    {"code": "A6N", "display": "Hospital Medicine"},
    {"code": "SURG", "display": "Surgery Floor"},
]

# Organisms for urine cultures
ORGANISMS = {
    "ecoli": {"code": "112283007", "display": "Escherichia coli"},
    "klebsiella": {"code": "56415008", "display": "Klebsiella pneumoniae"},
    "enterococcus": {"code": "76327009", "display": "Enterococcus faecalis"},
    "pseudomonas": {"code": "52499004", "display": "Pseudomonas aeruginosa"},
}

# Patient names
FIRST_NAMES = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]


def generate_mrn():
    return f"CAUTI{random.randint(10000, 99999)}"


def create_patient(patient_id: str, mrn: str) -> dict:
    """Create a FHIR Patient resource."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    age_days = random.randint(365, 6570)  # 1-18 years
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


def create_urinary_catheter(device_id: str, patient_id: str, encounter_id: str,
                             insert_date: datetime, remove_date: datetime = None) -> dict:
    """Create a FHIR DeviceUseStatement for indwelling urinary catheter."""
    device = {
        "resourceType": "DeviceUseStatement",
        "id": device_id,
        "status": "active" if remove_date is None else "completed",
        "subject": {"reference": f"Patient/{patient_id}"},
        "derivedFrom": [{"reference": f"Encounter/{encounter_id}"}],
        "timingPeriod": {
            "start": insert_date.isoformat(),
        },
        "device": {
            "concept": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "68135008",
                    "display": "Foley catheter"
                }]
            }
        },
        "bodySite": {
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "87953007",
                "display": "Urinary bladder"
            }]
        }
    }
    if remove_date:
        device["timingPeriod"]["end"] = remove_date.isoformat()
    return device


def create_urine_culture(report_id: str, patient_id: str, encounter_id: str,
                         collection_date: datetime, organism: dict, cfu_ml: int) -> dict:
    """Create a FHIR DiagnosticReport for urine culture."""
    return {
        "resourceType": "DiagnosticReport",
        "id": report_id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                "code": "MB",
                "display": "Microbiology"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "630-4",
                "display": "Bacteria identified in urine by Culture"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": collection_date.isoformat(),
        "issued": (collection_date + timedelta(days=2)).isoformat(),
        "conclusion": f"Positive: {organism['display']} >= {cfu_ml:,} CFU/mL",
        "conclusionCode": [{
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": organism["code"],
                "display": organism["display"]
            }]
        }]
    }


def create_cfu_observation(obs_id: str, patient_id: str, report_id: str,
                            collection_date: datetime, cfu_ml: int) -> dict:
    """Create a FHIR Observation for colony count."""
    return {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "88461-2",
                "display": "Urine culture colony count"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "derivedFrom": [{"reference": f"DiagnosticReport/{report_id}"}],
        "effectiveDateTime": collection_date.isoformat(),
        "valueQuantity": {
            "value": cfu_ml,
            "unit": "CFU/mL",
            "system": "http://unitsofmeasure.org",
            "code": "{CFU}/mL"
        }
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
    "cauti": {
        "description": "CAUTI case: Foley catheter 5 days, E. coli 100K CFU/mL, fever and dysuria",
        "expected": "CAUTI",
        "organism": "ecoli",
        "cfu_ml": 150000,
        "catheter_days": 5,
        "note": """Hospital Medicine Progress Note - Day 5

Assessment: 8-year-old male with spinal cord injury, post-operative day 5 from spinal fusion.

Indwelling Foley catheter placed on admission (5 days).

Current Issues:
1. NEW FEVER - Tmax 38.9°C this morning
2. Patient reports suprapubic discomfort and dysuria
3. Urine appears cloudy with foul odor

Labs:
- UA: Positive leukocyte esterase, positive nitrites, >50 WBC/hpf
- Urine culture: PENDING (collected today)
- CBC: WBC 14.2, no left shift

Impression:
Symptomatic UTI in setting of indwelling urinary catheter >48 hours. Meets clinical
criteria for catheter-associated UTI (CAUTI).

Plan:
- Start empiric ceftriaxone pending culture results
- Consider catheter removal/replacement
- Monitor fever curve
- Urology consult for long-term bladder management
"""
    },
    "asymptomatic": {
        "description": "Not CAUTI: Positive culture but asymptomatic bacteriuria",
        "expected": "Not CAUTI - Asymptomatic bacteriuria",
        "organism": "enterococcus",
        "cfu_ml": 200000,
        "catheter_days": 4,
        "note": """Hospital Medicine Progress Note - Day 4

Assessment: 6-year-old female with spina bifida, admitted for VP shunt revision.

Indwelling Foley catheter placed on admission (4 days).

Current Status:
- Afebrile, Tmax 37.2°C
- No urinary symptoms (baseline neurogenic bladder)
- No suprapubic tenderness on exam
- Urine appears clear

Labs:
- Routine urine culture (pre-operative screening): Enterococcus faecalis >100,000 CFU/mL
- UA: Mild pyuria (10-20 WBC/hpf), common in catheterized patients
- Patient completely asymptomatic

Impression:
Asymptomatic bacteriuria in setting of indwelling catheter. This does NOT represent
a catheter-associated UTI per NHSN criteria as the patient has no signs or symptoms
of infection. Treatment is not indicated per IDSA guidelines.

Plan:
- DO NOT treat bacteriuria (asymptomatic)
- Continue catheter care
- Proceed with planned surgery
"""
    },
    "short-catheter": {
        "description": "Not CAUTI: Catheter only 1 day (does not meet >2 day criteria)",
        "expected": "Not CAUTI - Catheter <2 days",
        "organism": "klebsiella",
        "cfu_ml": 100000,
        "catheter_days": 1,
        "note": """ED to Floor Transfer Note

Assessment: 10-year-old male with appendicitis, post-operative day 0 from appendectomy.

Foley catheter placed in OR for surgery (1 day).

Events:
- Urgent appendectomy performed today for perforated appendicitis
- Foley placed intraoperatively for urine output monitoring
- Post-op urine sample sent (routine)

Labs:
- Urine culture: Klebsiella pneumoniae 100,000 CFU/mL
- Likely colonization from OR procedure

Clinical Status:
- Afebrile currently (immediate post-op)
- Catheter only in place <24 hours
- No urinary symptoms

Impression:
Positive urine culture but catheter was only in place for <2 calendar days. Does NOT
meet NHSN criteria for CAUTI regardless of symptoms. This is likely contamination or
colonization related to recent catheter insertion.

Plan:
- Remove Foley catheter tomorrow morning
- Do not treat positive culture (does not meet CAUTI criteria)
- Monitor for development of actual symptoms
"""
    },
}


def create_cauti_scenario(scenario_key: str, fhir_url: str, dry_run: bool = False):
    """Create a CAUTI demo scenario."""
    scenario = SCENARIOS[scenario_key]

    # Generate IDs
    patient_id = str(uuid.uuid4())
    encounter_id = str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())
    cfu_obs_id = str(uuid.uuid4())
    note_id = str(uuid.uuid4())
    mrn = generate_mrn()
    location = random.choice(LOCATIONS)

    # Dates
    now = datetime.now(timezone.utc)
    admit_date = now - timedelta(days=scenario["catheter_days"] + 1)
    catheter_insert = now - timedelta(days=scenario["catheter_days"])
    culture_date = now - timedelta(hours=12)

    organism = ORGANISMS[scenario["organism"]]

    # Create resources
    resources = []

    # Patient and Encounter
    resources.append(create_patient(patient_id, mrn))
    resources.append(create_encounter(encounter_id, patient_id, location, admit_date))

    # Urinary catheter
    resources.append(create_urinary_catheter(device_id, patient_id, encounter_id, catheter_insert))

    # Urine culture
    resources.append(create_urine_culture(
        report_id, patient_id, encounter_id, culture_date, organism, scenario["cfu_ml"]
    ))

    # CFU observation
    resources.append(create_cfu_observation(
        cfu_obs_id, patient_id, report_id, culture_date, scenario["cfu_ml"]
    ))

    # Clinical note
    note_date = now - timedelta(hours=2)
    resources.append(create_clinical_note(note_id, patient_id, encounter_id, note_date, scenario["note"]))

    # Print scenario info
    print(f"\n{'-'*70}")
    print(f"Scenario: {scenario_key.upper()}")
    print(f"{'-'*70}")
    print(f"  Patient MRN:    {mrn}")
    print(f"  Location:       {location['display']}")
    print(f"  Catheter Days:  {scenario['catheter_days']}")
    print(f"  Organism:       {organism['display']}")
    print(f"  CFU/mL:         {scenario['cfu_ml']:,}")
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
        description="Generate demo CAUTI candidates for HAI detection",
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
    print("CAUTI DEMO SCENARIOS")
    print("=" * 70)

    if args.all:
        for scenario_key in SCENARIOS:
            create_cauti_scenario(scenario_key, args.fhir_url, args.dry_run)
    elif args.scenario:
        create_cauti_scenario(args.scenario, args.fhir_url, args.dry_run)
    else:
        # Default: create one CAUTI and one asymptomatic case
        create_cauti_scenario("cauti", args.fhir_url, args.dry_run)
        create_cauti_scenario("asymptomatic", args.fhir_url, args.dry_run)

    print("\n" + "=" * 70)
    print("\nDemo data created. To see the candidates:")
    print("  1. Run the HAI monitor: cd hai-detection && python -m src.runner --full")
    print("  2. View in dashboard: https://aegis-asp.com/hai-detection/")
    print()


if __name__ == "__main__":
    main()
