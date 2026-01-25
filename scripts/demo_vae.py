#!/usr/bin/env python3
"""Generate demo VAE (Ventilator-Associated Event) candidates for dashboard demonstration.

Creates scenarios:
1. VAC case - Patient with sustained worsening of ventilator settings
2. Not VAE case - Patient on ventilator with stable settings

NHSN VAE Criteria:
- Patient on mechanical ventilation ≥2 calendar days
- ≥2 days of stable or decreasing settings (baseline)
- ≥2 days of sustained worsening (FiO2 increase ≥20% or PEEP increase ≥3 cmH2O)

Usage:
    # Create one VAE + one Not VAE pair
    python demo_vae.py

    # Create specific scenario types
    python demo_vae.py --scenario vac
    python demo_vae.py --scenario stable

    # Dry run (don't upload to FHIR)
    python demo_vae.py --dry-run
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
    {"code": "T5B", "display": "CICU"},
    {"code": "T4", "display": "NICU"},
]

# Patient names
FIRST_NAMES = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]


def generate_mrn():
    return f"VAE{random.randint(10000, 99999)}"


def create_patient(patient_id: str, mrn: str) -> dict:
    """Create a FHIR Patient resource."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    age_days = random.randint(30, 3650)  # 1 month to 10 years
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


def create_ventilation_procedure(procedure_id: str, patient_id: str, encounter_id: str,
                                  start_date: datetime, end_date: datetime = None) -> dict:
    """Create a FHIR Procedure resource for mechanical ventilation."""
    procedure = {
        "resourceType": "Procedure",
        "id": procedure_id,
        "status": "in-progress" if end_date is None else "completed",
        "code": {
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "40617009",
                "display": "Artificial respiration (procedure)"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "performedPeriod": {
            "start": start_date.isoformat(),
        }
    }
    if end_date:
        procedure["performedPeriod"]["end"] = end_date.isoformat()
    return procedure


def create_fio2_observation(obs_id: str, patient_id: str, encounter_id: str,
                            timestamp: datetime, value: float) -> dict:
    """Create a FHIR Observation for FiO2 (Inhaled oxygen concentration)."""
    return {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "vital-signs"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "3150-0",
                "display": "Inhaled oxygen concentration"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": timestamp.isoformat(),
        "valueQuantity": {
            "value": value,
            "unit": "%",
            "system": "http://unitsofmeasure.org",
            "code": "%"
        }
    }


def create_peep_observation(obs_id: str, patient_id: str, encounter_id: str,
                            timestamp: datetime, value: float) -> dict:
    """Create a FHIR Observation for PEEP."""
    return {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "vital-signs"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "76530-5",
                "display": "PEEP Respiratory system by Ventilator"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": timestamp.isoformat(),
        "valueQuantity": {
            "value": value,
            "unit": "cm[H2O]",
            "system": "http://unitsofmeasure.org",
            "code": "cm[H2O]"
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
    "vac": {
        "description": "VAC case: 4 days vent with worsening FiO2/PEEP on days 3-4",
        "expected": "VAC (Ventilator-Associated Condition)",
        # Day 1-2: baseline (stable), Day 3-4: worsening
        "fio2_values": [40, 40, 65, 70],  # 25-30% increase
        "peep_values": [5, 5, 9, 10],      # 4-5 cmH2O increase
        "note": """PICU Progress Note - Day 4 on Ventilator

Assessment: 4-year-old male with RSV bronchiolitis, now with worsening respiratory status.

Ventilator Settings (today):
- Mode: SIMV
- FiO2: 70% (increased from 40% baseline)
- PEEP: 10 cmH2O (increased from 5)
- Rate: 20

Clinical Course:
- Day 1-2: Required intubation for respiratory failure. Stable on FiO2 40%, PEEP 5.
- Day 3: Worsening oxygenation, increased FiO2 to 65%, PEEP to 9
- Day 4: Continued deterioration. Now on FiO2 70%, PEEP 10.
- CXR today shows new bilateral infiltrates concerning for ARDS vs VAP.
- Started empiric vancomycin and cefepime.
- Sputum culture sent.

Plan:
- Continue mechanical ventilation
- Bronchoscopy for BAL if no improvement
- Monitor for VAP criteria
"""
    },
    "stable": {
        "description": "Not VAE: 4 days on vent with stable settings throughout",
        "expected": "Not VAE - stable ventilator settings",
        "fio2_values": [35, 35, 30, 30],  # Stable/improving
        "peep_values": [6, 6, 5, 5],       # Stable/improving
        "note": """PICU Progress Note - Day 4 on Ventilator

Assessment: 3-year-old female post-operative cardiac surgery, stable on mechanical ventilation.

Ventilator Settings:
- Mode: SIMV
- FiO2: 30% (weaning well)
- PEEP: 5 cmH2O
- Rate: 16

Clinical Course:
- Post-op day 4 from VSD repair
- Extubation planned for tomorrow
- Stable hemodynamics, good urine output
- Chest x-ray clear bilaterally
- Afebrile throughout, no signs of infection

Plan:
- Spontaneous breathing trial in AM
- Extubate if passes SBT
- Continue current supportive care
"""
    },
}


def create_vae_scenario(scenario_key: str, fhir_url: str, dry_run: bool = False):
    """Create a VAE demo scenario."""
    scenario = SCENARIOS[scenario_key]

    # Generate IDs
    patient_id = str(uuid.uuid4())
    encounter_id = str(uuid.uuid4())
    procedure_id = str(uuid.uuid4())
    mrn = generate_mrn()
    location = random.choice(LOCATIONS)

    # Dates: patient admitted 5 days ago, intubated 4 days ago
    now = datetime.now(timezone.utc)
    admit_date = now - timedelta(days=5)
    vent_start = now - timedelta(days=4)

    # Create resources
    resources = []

    # Patient and Encounter
    resources.append(create_patient(patient_id, mrn))
    resources.append(create_encounter(encounter_id, patient_id, location, admit_date))

    # Ventilation procedure
    resources.append(create_ventilation_procedure(procedure_id, patient_id, encounter_id, vent_start))

    # Daily FiO2 and PEEP observations
    for day_offset, (fio2, peep) in enumerate(zip(scenario["fio2_values"], scenario["peep_values"])):
        obs_date = vent_start + timedelta(days=day_offset, hours=8)  # Morning values

        fio2_id = str(uuid.uuid4())
        peep_id = str(uuid.uuid4())

        resources.append(create_fio2_observation(fio2_id, patient_id, encounter_id, obs_date, fio2))
        resources.append(create_peep_observation(peep_id, patient_id, encounter_id, obs_date, peep))

    # Clinical note
    note_id = str(uuid.uuid4())
    note_date = now - timedelta(hours=2)
    resources.append(create_clinical_note(note_id, patient_id, encounter_id, note_date, scenario["note"]))

    # Print scenario info
    print(f"\n{'='*70}")
    print(f"Scenario: {scenario_key.upper()}")
    print(f"{'='*70}")
    print(f"  Patient MRN:    {mrn}")
    print(f"  Location:       {location['display']}")
    print(f"  Vent Days:      4")
    print(f"  FiO2 Trend:     {' -> '.join(str(v)+'%' for v in scenario['fio2_values'])}")
    print(f"  PEEP Trend:     {' -> '.join(str(v) for v in scenario['peep_values'])}")
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
        description="Generate demo VAE candidates for HAI detection",
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
    print("VAE DEMO SCENARIOS")
    print("=" * 70)

    if args.all:
        for scenario_key in SCENARIOS:
            create_vae_scenario(scenario_key, args.fhir_url, args.dry_run)
    elif args.scenario:
        create_vae_scenario(args.scenario, args.fhir_url, args.dry_run)
    else:
        # Default: create one VAC and one stable case
        create_vae_scenario("vac", args.fhir_url, args.dry_run)
        create_vae_scenario("stable", args.fhir_url, args.dry_run)

    print("\n" + "=" * 70)
    print("\nDemo data created. To see the candidates:")
    print("  1. Run the HAI monitor: cd hai-detection && python -m src.runner --full")
    print("  2. View in dashboard: https://aegis-asp.com/hai-detection/")
    print()


if __name__ == "__main__":
    main()
