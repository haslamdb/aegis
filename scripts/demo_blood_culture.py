#!/usr/bin/env python3
"""Generate a demo patient with a positive blood culture for alert testing.

Creates a new patient in the FHIR server with:
- A positive blood culture (organism of your choice)
- Optionally on an antibiotic (may or may not cover the organism)

This triggers bacteremia alerts when the monitor runs.

Usage:
    # MRSA without vancomycin (should trigger alert)
    python demo_blood_culture.py --organism mrsa

    # MRSA with vancomycin (should NOT trigger alert)
    python demo_blood_culture.py --organism mrsa --antibiotic vancomycin

    # Pseudomonas with cefazolin (should trigger alert - inadequate coverage)
    python demo_blood_culture.py --organism pseudomonas --antibiotic cefazolin

    # E. coli with meropenem (appropriate)
    python demo_blood_culture.py --organism ecoli --antibiotic meropenem

    # Interactive mode
    python demo_blood_culture.py --interactive
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

# Organism definitions with SNOMED codes
ORGANISMS = {
    "mrsa": {
        "code": "115329001",
        "display": "Methicillin resistant Staphylococcus aureus",
        "condition_code": "266096002",
        "condition_display": "MRSA infection",
        "appropriate_abx": ["vancomycin", "daptomycin", "linezolid"],
    },
    "mssa": {
        "code": "3092008",
        "display": "Staphylococcus aureus",
        "condition_code": "3092008",
        "condition_display": "Staphylococcus aureus infection",
        "appropriate_abx": ["cefazolin", "nafcillin", "vancomycin"],
    },
    "ecoli": {
        "code": "112283007",
        "display": "Escherichia coli",
        "condition_code": "112283007",
        "condition_display": "Escherichia coli infection",
        "appropriate_abx": ["ceftriaxone", "meropenem", "piperacillin-tazobactam"],
    },
    "pseudomonas": {
        "code": "52499004",
        "display": "Pseudomonas aeruginosa",
        "condition_code": "52499004",
        "condition_display": "Pseudomonas aeruginosa infection",
        "appropriate_abx": ["meropenem", "cefepime", "piperacillin-tazobactam"],
    },
    "klebsiella": {
        "code": "56415008",
        "display": "Klebsiella pneumoniae",
        "condition_code": "56415008",
        "condition_display": "Klebsiella infection",
        "appropriate_abx": ["ceftriaxone", "meropenem", "piperacillin-tazobactam"],
    },
    "enterococcus": {
        "code": "78065002",
        "display": "Enterococcus faecalis",
        "condition_code": "78065002",
        "condition_display": "Enterococcus infection",
        "appropriate_abx": ["vancomycin", "ampicillin"],
    },
    "vre": {
        "code": "113727004",
        "display": "Vancomycin resistant Enterococcus",
        "condition_code": "413563001",
        "condition_display": "VRE infection",
        "appropriate_abx": ["daptomycin", "linezolid"],
    },
    "candida": {
        "code": "78048006",
        "display": "Candida albicans",
        "condition_code": "78048006",
        "condition_display": "Candida infection",
        "appropriate_abx": ["micafungin", "fluconazole", "caspofungin"],
    },
}

# Antibiotic definitions with RxNorm codes
ANTIBIOTICS = {
    "vancomycin": {"code": "11124", "display": "Vancomycin"},
    "meropenem": {"code": "29561", "display": "Meropenem"},
    "cefazolin": {"code": "309090", "display": "Cefazolin"},
    "ceftriaxone": {"code": "309092", "display": "Ceftriaxone"},
    "cefepime": {"code": "309091", "display": "Cefepime"},
    "piperacillin-tazobactam": {"code": "312619", "display": "Piperacillin-tazobactam"},
    "ampicillin": {"code": "733", "display": "Ampicillin"},
    "daptomycin": {"code": "262090", "display": "Daptomycin"},
    "linezolid": {"code": "190376", "display": "Linezolid"},
    "micafungin": {"code": "121243", "display": "Micafungin"},
    "fluconazole": {"code": "4450", "display": "Fluconazole"},
    "nafcillin": {"code": "7233", "display": "Nafcillin"},
    "caspofungin": {"code": "202553", "display": "Caspofungin"},
}

# Names for demo patients
FIRST_NAMES = ["Demo", "Test", "Alert", "Sample", "Trial"]
LAST_NAMES = ["Patient", "Case", "Subject", "Example", "Scenario"]


def generate_mrn() -> str:
    """Generate a demo MRN."""
    return f"DEMO{random.randint(1000, 9999)}"


def create_patient(mrn: str) -> dict:
    """Create a Patient FHIR resource."""
    patient_id = str(uuid.uuid4())
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)

    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                            "code": "MR",
                        }
                    ]
                },
                "value": mrn,
            }
        ],
        "name": [{"family": last_name, "given": [first_name]}],
        "gender": random.choice(["male", "female"]),
        "birthDate": (datetime.now() - timedelta(days=random.randint(365, 6570))).strftime(
            "%Y-%m-%d"
        ),
    }


def create_encounter(patient_id: str) -> dict:
    """Create an inpatient Encounter FHIR resource."""
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
        "period": {"start": datetime.now(timezone.utc).isoformat()},
    }


def create_blood_culture_observation(
    patient_id: str, organism_key: str, hours_ago: float = 2
) -> dict:
    """Create a positive blood culture Observation FHIR resource."""
    organism = ORGANISMS[organism_key]
    collected_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    return {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "600-7",
                    "display": "Bacteria identified in Blood by Culture",
                }
            ],
            "text": "Blood Culture",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": collected_time.isoformat(),
        "valueCodeableConcept": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": organism["code"],
                    "display": organism["display"],
                }
            ],
            "text": organism["display"],
        },
    }


def create_medication_request(
    patient_id: str, antibiotic_key: str, hours_ago: float = 4
) -> dict:
    """Create a MedicationRequest FHIR resource."""
    antibiotic = ANTIBIOTICS[antibiotic_key]
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    return {
        "resourceType": "MedicationRequest",
        "id": str(uuid.uuid4()),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "code": antibiotic["code"],
                    "display": antibiotic["display"],
                }
            ],
            "text": antibiotic["display"],
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": start_time.isoformat(),
    }


def upload_to_fhir(resource: dict, fhir_url: str) -> bool:
    """Upload a resource to the FHIR server."""
    resource_type = resource["resourceType"]
    resource_id = resource["id"]
    url = f"{fhir_url}/{resource_type}/{resource_id}"

    try:
        response = requests.put(
            url,
            json=resource,
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  Error uploading {resource_type}: {e}")
        return False


def interactive_mode() -> tuple[str, str | None]:
    """Run interactive prompts to select organism and antibiotic."""
    print("\n=== Blood Culture Demo - Interactive Mode ===\n")

    print("Available organisms:")
    for i, (key, org) in enumerate(ORGANISMS.items(), 1):
        print(f"  {i}. {key}: {org['display']}")

    while True:
        try:
            choice = input("\nSelect organism (number or name): ").strip().lower()
            if choice.isdigit():
                idx = int(choice) - 1
                organism_key = list(ORGANISMS.keys())[idx]
            elif choice in ORGANISMS:
                organism_key = choice
            else:
                print("Invalid choice. Try again.")
                continue
            break
        except (ValueError, IndexError):
            print("Invalid choice. Try again.")

    organism = ORGANISMS[organism_key]
    print(f"\nSelected: {organism['display']}")
    print(f"Appropriate antibiotics: {', '.join(organism['appropriate_abx'])}")

    print("\nAvailable antibiotics:")
    print("  0. None (no antibiotic)")
    for i, (key, abx) in enumerate(ANTIBIOTICS.items(), 1):
        coverage = "✓" if key in organism["appropriate_abx"] else "✗"
        print(f"  {i}. {key}: {abx['display']} [{coverage}]")

    while True:
        try:
            choice = input("\nSelect antibiotic (number, name, or 0 for none): ").strip().lower()
            if choice == "0" or choice == "none":
                antibiotic_key = None
            elif choice.isdigit():
                idx = int(choice) - 1
                antibiotic_key = list(ANTIBIOTICS.keys())[idx]
            elif choice in ANTIBIOTICS:
                antibiotic_key = choice
            else:
                print("Invalid choice. Try again.")
                continue
            break
        except (ValueError, IndexError):
            print("Invalid choice. Try again.")

    return organism_key, antibiotic_key


def main():
    parser = argparse.ArgumentParser(
        description="Generate a demo patient with positive blood culture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--organism", "-o",
        choices=list(ORGANISMS.keys()),
        help="Organism for blood culture",
    )
    parser.add_argument(
        "--antibiotic", "-a",
        choices=list(ANTIBIOTICS.keys()),
        help="Current antibiotic (optional)",
    )
    parser.add_argument(
        "--fhir-url",
        default="http://localhost:8081/fhir",
        help="FHIR server base URL",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--culture-hours",
        type=float,
        default=2,
        help="Hours ago blood culture was collected (default: 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resources without uploading",
    )

    args = parser.parse_args()

    # Interactive or command-line mode
    if args.interactive:
        organism_key, antibiotic_key = interactive_mode()
    elif args.organism:
        organism_key = args.organism
        antibiotic_key = args.antibiotic
    else:
        parser.error("Either --organism or --interactive is required")

    organism = ORGANISMS[organism_key]

    # Generate resources
    mrn = generate_mrn()
    patient = create_patient(mrn)
    patient_id = patient["id"]
    patient_name = f"{patient['name'][0]['given'][0]} {patient['name'][0]['family']}"

    encounter = create_encounter(patient_id)
    observation = create_blood_culture_observation(patient_id, organism_key, args.culture_hours)

    medication = None
    if antibiotic_key:
        medication = create_medication_request(patient_id, antibiotic_key)

    # Determine if alert should trigger
    will_alert = antibiotic_key is None or antibiotic_key not in organism["appropriate_abx"]

    print(f"\n{'='*60}")
    print("DEMO BLOOD CULTURE SCENARIO")
    print(f"{'='*60}")
    print(f"Patient:     {patient_name} (MRN: {mrn})")
    print(f"Organism:    {organism['display']}")
    if antibiotic_key:
        coverage = "adequate" if antibiotic_key in organism["appropriate_abx"] else "INADEQUATE"
        print(f"Antibiotic:  {ANTIBIOTICS[antibiotic_key]['display']} ({coverage})")
    else:
        print("Antibiotic:  None")
    print(f"Alert:       {'YES - should trigger alert' if will_alert else 'No - adequate coverage'}")
    print(f"{'='*60}\n")

    if args.dry_run:
        print("Dry run - resources not uploaded\n")
        print("Patient:", json.dumps(patient, indent=2)[:500], "...\n")
        print("Observation:", json.dumps(observation, indent=2)[:500], "...\n")
        if medication:
            print("Medication:", json.dumps(medication, indent=2)[:500], "...\n")
        return 0

    # Upload to FHIR server
    print(f"Uploading to {args.fhir_url}...")

    try:
        requests.get(f"{args.fhir_url}/metadata").raise_for_status()
    except Exception as e:
        print(f"Error: Cannot connect to FHIR server: {e}")
        return 1

    resources = [patient, encounter, observation]
    if medication:
        resources.append(medication)

    for resource in resources:
        rtype = resource["resourceType"]
        if upload_to_fhir(resource, args.fhir_url):
            print(f"  ✓ {rtype} created")
        else:
            print(f"  ✗ {rtype} failed")
            return 1

    print(f"\n✓ Demo patient created successfully!")
    print(f"  Patient ID: {patient_id}")
    print(f"  MRN: {mrn}")
    if will_alert:
        print(f"\n  Run the bacteremia monitor to see the alert trigger.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
