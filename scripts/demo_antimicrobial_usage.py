#!/usr/bin/env python3
"""Generate a demo patient with prolonged antibiotic use for alert testing.

Creates a new patient in the FHIR server with:
- An active broad-spectrum antibiotic order
- Specified duration (triggers alert if > 72 hours by default)

This triggers antimicrobial usage alerts when the monitor runs.

Usage:
    # Meropenem for 4 days (should trigger warning alert)
    python demo_antimicrobial_usage.py --antibiotic meropenem --days 4

    # Vancomycin for 7 days (should trigger critical alert)
    python demo_antimicrobial_usage.py --antibiotic vancomycin --days 7

    # Meropenem for 2 days (no alert - under threshold)
    python demo_antimicrobial_usage.py --antibiotic meropenem --days 2

    # Specify hours instead of days
    python demo_antimicrobial_usage.py --antibiotic vancomycin --hours 80

    # Interactive mode
    python demo_antimicrobial_usage.py --interactive
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

# Monitored broad-spectrum antibiotics with RxNorm codes
ANTIBIOTICS = {
    "meropenem": {
        "code": "29561",
        "display": "Meropenem",
        "dose": "40 mg/kg",
        "route": "IV",
        "monitored": True,
    },
    "vancomycin": {
        "code": "11124",
        "display": "Vancomycin",
        "dose": "15 mg/kg",
        "route": "IV",
        "monitored": True,
    },
    "piperacillin-tazobactam": {
        "code": "312619",
        "display": "Piperacillin-tazobactam",
        "dose": "100 mg/kg",
        "route": "IV",
        "monitored": True,
    },
    "cefepime": {
        "code": "309091",
        "display": "Cefepime",
        "dose": "50 mg/kg",
        "route": "IV",
        "monitored": True,
    },
    "linezolid": {
        "code": "190376",
        "display": "Linezolid",
        "dose": "10 mg/kg",
        "route": "IV",
        "monitored": True,
    },
    # Non-monitored antibiotics (for comparison)
    "ceftriaxone": {
        "code": "309092",
        "display": "Ceftriaxone",
        "dose": "50 mg/kg",
        "route": "IV",
        "monitored": False,
    },
    "ampicillin": {
        "code": "733",
        "display": "Ampicillin",
        "dose": "50 mg/kg",
        "route": "IV",
        "monitored": False,
    },
}

# Default threshold (can be overridden)
DEFAULT_THRESHOLD_HOURS = 72

# Names for demo patients
FIRST_NAMES = ["Demo", "Test", "Alert", "Sample", "Trial", "Usage"]
LAST_NAMES = ["Patient", "Case", "Subject", "Duration", "Therapy"]


def generate_mrn() -> str:
    """Generate a demo MRN."""
    return f"USAGE{random.randint(1000, 9999)}"


def create_patient(mrn: str) -> dict:
    """Create a Patient FHIR resource."""
    patient_id = str(uuid.uuid4())
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)

    # Random pediatric age (1 month to 18 years)
    age_days = random.randint(30, 6570)
    birth_date = datetime.now() - timedelta(days=age_days)

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
        "birthDate": birth_date.strftime("%Y-%m-%d"),
    }


def create_encounter(patient_id: str, admission_hours_ago: float) -> dict:
    """Create an inpatient Encounter FHIR resource."""
    admission_time = datetime.now(timezone.utc) - timedelta(hours=admission_hours_ago)

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


def create_condition(patient_id: str) -> dict:
    """Create a Condition FHIR resource (reason for antibiotics)."""
    return {
        "resourceType": "Condition",
        "id": str(uuid.uuid4()),
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                }
            ]
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "encounter-diagnosis",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "10001005",
                    "display": "Bacterial sepsis",
                }
            ],
            "text": "Bacterial sepsis",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "onsetDateTime": datetime.now(timezone.utc).isoformat(),
    }


def create_medication_request(
    patient_id: str, antibiotic_key: str, hours_ago: float
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
        "dosageInstruction": [
            {
                "text": f"{antibiotic['dose']} {antibiotic['route']} every 8 hours",
                "route": {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "47625008",
                            "display": antibiotic["route"],
                        }
                    ]
                },
            }
        ],
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


def interactive_mode() -> tuple[str, float]:
    """Run interactive prompts to select antibiotic and duration."""
    print("\n=== Antimicrobial Usage Demo - Interactive Mode ===\n")

    print("Available antibiotics:")
    monitored = [(k, v) for k, v in ANTIBIOTICS.items() if v["monitored"]]
    other = [(k, v) for k, v in ANTIBIOTICS.items() if not v["monitored"]]

    print("\nMonitored (will trigger alerts if > 72h):")
    for i, (key, abx) in enumerate(monitored, 1):
        print(f"  {i}. {key}: {abx['display']}")

    print("\nOther (not monitored):")
    for i, (key, abx) in enumerate(other, len(monitored) + 1):
        print(f"  {i}. {key}: {abx['display']}")

    while True:
        try:
            choice = input("\nSelect antibiotic (number or name): ").strip().lower()
            if choice.isdigit():
                idx = int(choice) - 1
                all_abx = monitored + other
                antibiotic_key = all_abx[idx][0]
            elif choice in ANTIBIOTICS:
                antibiotic_key = choice
            else:
                print("Invalid choice. Try again.")
                continue
            break
        except (ValueError, IndexError):
            print("Invalid choice. Try again.")

    print(f"\nSelected: {ANTIBIOTICS[antibiotic_key]['display']}")

    while True:
        try:
            duration_input = input(
                "\nDuration (e.g., '4d' for 4 days, '80h' for 80 hours): "
            ).strip().lower()

            if duration_input.endswith("d"):
                days = float(duration_input[:-1])
                hours = days * 24
            elif duration_input.endswith("h"):
                hours = float(duration_input[:-1])
            else:
                # Assume days if no suffix
                hours = float(duration_input) * 24

            if hours <= 0:
                print("Duration must be positive.")
                continue
            break
        except ValueError:
            print("Invalid duration. Use format like '4d' or '80h'.")

    return antibiotic_key, hours


def main():
    parser = argparse.ArgumentParser(
        description="Generate a demo patient with prolonged antibiotic use",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--antibiotic", "-a",
        choices=list(ANTIBIOTICS.keys()),
        help="Antibiotic to prescribe",
    )
    parser.add_argument(
        "--days", "-d",
        type=float,
        help="Number of days on antibiotic",
    )
    parser.add_argument(
        "--hours",
        type=float,
        help="Number of hours on antibiotic (alternative to --days)",
    )
    parser.add_argument(
        "--fhir-url",
        default="http://localhost:8081/fhir",
        help="FHIR server base URL",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD_HOURS,
        help=f"Alert threshold in hours (default: {DEFAULT_THRESHOLD_HOURS})",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resources without uploading",
    )

    args = parser.parse_args()

    # Interactive or command-line mode
    if args.interactive:
        antibiotic_key, duration_hours = interactive_mode()
    elif args.antibiotic and (args.days or args.hours):
        antibiotic_key = args.antibiotic
        if args.hours:
            duration_hours = args.hours
        else:
            duration_hours = args.days * 24
    else:
        parser.error("Either --interactive or (--antibiotic and --days/--hours) required")

    antibiotic = ANTIBIOTICS[antibiotic_key]
    threshold = args.threshold

    # Generate resources
    mrn = generate_mrn()
    patient = create_patient(mrn)
    patient_id = patient["id"]
    patient_name = f"{patient['name'][0]['given'][0]} {patient['name'][0]['family']}"

    # Admission slightly before antibiotic start
    encounter = create_encounter(patient_id, duration_hours + 4)
    condition = create_condition(patient_id)
    medication = create_medication_request(patient_id, antibiotic_key, duration_hours)

    # Determine alert status
    if not antibiotic["monitored"]:
        alert_status = "Not monitored (no alert)"
        severity = None
    elif duration_hours < threshold:
        alert_status = f"Under threshold ({duration_hours:.0f}h < {threshold}h)"
        severity = None
    elif duration_hours < threshold * 2:
        alert_status = f"WARNING ({duration_hours:.0f}h >= {threshold}h)"
        severity = "warning"
    else:
        alert_status = f"CRITICAL ({duration_hours:.0f}h >= {threshold * 2}h)"
        severity = "critical"

    print(f"\n{'='*60}")
    print("DEMO ANTIMICROBIAL USAGE SCENARIO")
    print(f"{'='*60}")
    print(f"Patient:     {patient_name} (MRN: {mrn})")
    print(f"Antibiotic:  {antibiotic['display']}")
    print(f"Duration:    {duration_hours:.0f} hours ({duration_hours/24:.1f} days)")
    print(f"Threshold:   {threshold} hours")
    print(f"Monitored:   {'Yes' if antibiotic['monitored'] else 'No'}")
    print(f"Alert:       {alert_status}")
    print(f"{'='*60}\n")

    if args.dry_run:
        print("Dry run - resources not uploaded\n")
        print("Patient:", json.dumps(patient, indent=2)[:500], "...\n")
        print("Medication:", json.dumps(medication, indent=2)[:500], "...\n")
        return 0

    # Upload to FHIR server
    print(f"Uploading to {args.fhir_url}...")

    try:
        requests.get(f"{args.fhir_url}/metadata").raise_for_status()
    except Exception as e:
        print(f"Error: Cannot connect to FHIR server: {e}")
        return 1

    resources = [patient, encounter, condition, medication]

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
    if severity:
        print(f"\n  Run the antimicrobial usage monitor to see the {severity.upper()} alert trigger.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
