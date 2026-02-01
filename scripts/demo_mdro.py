#!/usr/bin/env python3
"""Generate demo patients with MDRO cultures for testing MDRO Surveillance.

Creates patients with positive cultures and susceptibility patterns that
will trigger MDRO classification (MRSA, VRE, CRE, ESBL, CRPA, CRAB).

Usage:
    # Single MRSA case
    python demo_mdro.py --scenario mrsa

    # Single VRE case
    python demo_mdro.py --scenario vre

    # All MDRO types
    python demo_mdro.py --all

    # Community-onset (culture on admission day)
    python demo_mdro.py --scenario mrsa --community

    # Interactive mode
    python demo_mdro.py --interactive

    # List scenarios
    python demo_mdro.py --list
"""

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

# ============================================================================
# ORGANISMS with MDRO susceptibility patterns
# ============================================================================
ORGANISMS = {
    "mrsa": {
        "code": "115329001",
        "display": "Staphylococcus aureus",
        "susceptibilities": {
            "oxacillin": {"result": "R", "mic": ">4"},
            "cefazolin": {"result": "R", "mic": ">8"},
            "vancomycin": {"result": "S", "mic": "1"},
            "daptomycin": {"result": "S", "mic": "0.5"},
            "linezolid": {"result": "S", "mic": "2"},
            "clindamycin": {"result": "R", "mic": ">8"},
            "trimethoprim-sulfamethoxazole": {"result": "S", "mic": "<=0.5"},
        },
    },
    "vre": {
        "code": "113727004",
        "display": "Enterococcus faecium",
        "susceptibilities": {
            "ampicillin": {"result": "R", "mic": ">16"},
            "vancomycin": {"result": "R", "mic": ">256"},
            "linezolid": {"result": "S", "mic": "2"},
            "daptomycin": {"result": "S", "mic": "2"},
            "gentamicin-synergy": {"result": "R", "mic": ">500"},
        },
    },
    "cre": {
        "code": "56415008",
        "display": "Klebsiella pneumoniae",
        "susceptibilities": {
            "ampicillin": {"result": "R", "mic": ">32"},
            "ceftriaxone": {"result": "R", "mic": ">64"},
            "cefepime": {"result": "R", "mic": ">32"},
            "piperacillin-tazobactam": {"result": "R", "mic": ">128"},
            "meropenem": {"result": "R", "mic": ">8"},
            "ertapenem": {"result": "R", "mic": ">8"},
            "ciprofloxacin": {"result": "R", "mic": ">4"},
            "gentamicin": {"result": "R", "mic": ">8"},
            "ceftazidime-avibactam": {"result": "S", "mic": "<=1"},
        },
    },
    "esbl": {
        "code": "112283007",
        "display": "Escherichia coli",
        "susceptibilities": {
            "ampicillin": {"result": "R", "mic": ">32"},
            "ampicillin-sulbactam": {"result": "R", "mic": ">32"},
            "ceftriaxone": {"result": "R", "mic": ">64"},
            "cefepime": {"result": "R", "mic": ">16"},
            "piperacillin-tazobactam": {"result": "I", "mic": "64"},
            "meropenem": {"result": "S", "mic": "<=0.25"},
            "ertapenem": {"result": "S", "mic": "<=0.5"},
            "ciprofloxacin": {"result": "R", "mic": ">4"},
            "gentamicin": {"result": "S", "mic": "<=1"},
        },
    },
    "crpa": {
        "code": "52499004",
        "display": "Pseudomonas aeruginosa",
        "susceptibilities": {
            "piperacillin-tazobactam": {"result": "R", "mic": ">128"},
            "cefepime": {"result": "R", "mic": ">32"},
            "ceftazidime": {"result": "R", "mic": ">32"},
            "meropenem": {"result": "R", "mic": ">8"},
            "ciprofloxacin": {"result": "R", "mic": ">4"},
            "gentamicin": {"result": "R", "mic": ">8"},
            "tobramycin": {"result": "I", "mic": "4"},
            "aztreonam": {"result": "R", "mic": ">16"},
            "ceftolozane-tazobactam": {"result": "S", "mic": "2"},
        },
    },
    "crab": {
        "code": "91288006",
        "display": "Acinetobacter baumannii",
        "susceptibilities": {
            "ampicillin-sulbactam": {"result": "R", "mic": ">32"},
            "ceftazidime": {"result": "R", "mic": ">32"},
            "meropenem": {"result": "R", "mic": ">8"},
            "imipenem": {"result": "R", "mic": ">8"},
            "ciprofloxacin": {"result": "R", "mic": ">4"},
            "gentamicin": {"result": "R", "mic": ">8"},
            "tobramycin": {"result": "R", "mic": ">8"},
            "tigecycline": {"result": "S", "mic": "1"},
            "colistin": {"result": "S", "mic": "<=0.5"},
        },
    },
    # Non-MDRO control
    "mssa": {
        "code": "115329001",
        "display": "Staphylococcus aureus",
        "susceptibilities": {
            "oxacillin": {"result": "S", "mic": "<=0.25"},
            "cefazolin": {"result": "S", "mic": "<=1"},
            "vancomycin": {"result": "S", "mic": "1"},
            "clindamycin": {"result": "S", "mic": "<=0.25"},
        },
    },
}

# LOINC codes for susceptibility tests
SUSCEPTIBILITY_LOINC = {
    "oxacillin": {"code": "6932-8", "display": "Oxacillin [Susceptibility]"},
    "vancomycin": {"code": "20475-8", "display": "Vancomycin [Susceptibility]"},
    "daptomycin": {"code": "35811-4", "display": "Daptomycin [Susceptibility]"},
    "linezolid": {"code": "29258-1", "display": "Linezolid [Susceptibility]"},
    "cefazolin": {"code": "18864-9", "display": "Cefazolin [Susceptibility]"},
    "clindamycin": {"code": "18878-9", "display": "Clindamycin [Susceptibility]"},
    "trimethoprim-sulfamethoxazole": {"code": "18998-5", "display": "TMP-SMX [Susceptibility]"},
    "ampicillin": {"code": "18862-3", "display": "Ampicillin [Susceptibility]"},
    "ampicillin-sulbactam": {"code": "18865-6", "display": "Ampicillin-sulbactam [Susceptibility]"},
    "ceftriaxone": {"code": "18886-2", "display": "Ceftriaxone [Susceptibility]"},
    "cefepime": {"code": "18879-7", "display": "Cefepime [Susceptibility]"},
    "ceftazidime": {"code": "18888-8", "display": "Ceftazidime [Susceptibility]"},
    "piperacillin-tazobactam": {"code": "18945-6", "display": "Piperacillin+Tazobactam [Susceptibility]"},
    "meropenem": {"code": "18932-4", "display": "Meropenem [Susceptibility]"},
    "ertapenem": {"code": "35802-3", "display": "Ertapenem [Susceptibility]"},
    "imipenem": {"code": "18923-3", "display": "Imipenem [Susceptibility]"},
    "ciprofloxacin": {"code": "18906-8", "display": "Ciprofloxacin [Susceptibility]"},
    "gentamicin": {"code": "18928-2", "display": "Gentamicin [Susceptibility]"},
    "gentamicin-synergy": {"code": "18929-0", "display": "Gentamicin High Level [Susceptibility]"},
    "tobramycin": {"code": "18996-9", "display": "Tobramycin [Susceptibility]"},
    "aztreonam": {"code": "18868-0", "display": "Aztreonam [Susceptibility]"},
    "tigecycline": {"code": "42357-5", "display": "Tigecycline [Susceptibility]"},
    "colistin": {"code": "18908-4", "display": "Colistin [Susceptibility]"},
    "ceftazidime-avibactam": {"code": "73602-5", "display": "Ceftazidime-avibactam [Susceptibility]"},
    "ceftolozane-tazobactam": {"code": "73603-3", "display": "Ceftolozane-tazobactam [Susceptibility]"},
}

INTERPRETATION = {
    "S": {"code": "S", "display": "Susceptible", "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"},
    "I": {"code": "I", "display": "Intermediate", "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"},
    "R": {"code": "R", "display": "Resistant", "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"},
}

UNITS = ["ICU-A", "ICU-B", "Med-Surg 3", "Med-Surg 4", "Oncology", "MICU", "SICU"]
SPECIMEN_TYPES = ["Blood", "Urine", "Wound", "Respiratory"]

SCENARIOS = {
    "mrsa": {"organism": "mrsa", "name": "MRSA", "description": "Methicillin-resistant Staph aureus"},
    "vre": {"organism": "vre", "name": "VRE", "description": "Vancomycin-resistant Enterococcus"},
    "cre": {"organism": "cre", "name": "CRE", "description": "Carbapenem-resistant Enterobacteriaceae"},
    "esbl": {"organism": "esbl", "name": "ESBL", "description": "Extended-spectrum Beta-lactamase E. coli"},
    "crpa": {"organism": "crpa", "name": "CRPA", "description": "Carbapenem-resistant Pseudomonas"},
    "crab": {"organism": "crab", "name": "CRAB", "description": "Carbapenem-resistant Acinetobacter"},
    "mssa": {"organism": "mssa", "name": "MSSA (control)", "description": "Susceptible Staph - should NOT trigger MDRO"},
}

FIRST_NAMES = ["Demo", "Test", "MDRO", "Surveillance", "Alert"]
LAST_NAMES = ["Patient", "Case", "Subject", "Sample", "Example"]


def generate_mrn() -> str:
    return f"MDRO{random.randint(10000, 99999)}"


def create_patient(mrn: str) -> dict:
    patient_id = str(uuid.uuid4())
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]}, "value": mrn}
        ],
        "name": [{"family": random.choice(LAST_NAMES), "given": [random.choice(FIRST_NAMES)]}],
        "gender": random.choice(["male", "female"]),
        "birthDate": (datetime.now() - timedelta(days=random.randint(7300, 29200))).strftime("%Y-%m-%d"),
    }


def create_encounter(patient_id: str, days_ago: int = 3) -> dict:
    return {
        "resourceType": "Encounter",
        "id": str(uuid.uuid4()),
        "status": "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient encounter"},
        "subject": {"reference": f"Patient/{patient_id}"},
        "period": {"start": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()},
        "location": [{"location": {"display": random.choice(UNITS)}}],
    }


def create_culture_report(patient_id: str, organism_key: str, unit: str, hours_ago: float = 4) -> dict:
    organism = ORGANISMS[organism_key]
    collected_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    resulted_time = datetime.now(timezone.utc) - timedelta(hours=max(0.5, hours_ago - 2))
    specimen_type = random.choice(SPECIMEN_TYPES)

    return {
        "resourceType": "DiagnosticReport",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [{"coding": [
            {"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "LAB"},
            {"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "MB", "display": "Microbiology"},
        ]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": "600-7", "display": "Bacteria identified in Blood by Culture"}]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": collected_time.isoformat(),
        "issued": resulted_time.isoformat(),
        "specimen": [{"display": specimen_type}],
        "conclusion": organism["display"],
        "conclusionCode": [{"coding": [{"system": "http://snomed.info/sct", "code": organism["code"], "display": organism["display"]}]}],
        "result": [],
        "_location": unit,  # Custom field for demo tracking
    }


def create_susceptibility_observations(patient_id: str, report: dict, organism_key: str, hours_ago: float) -> list[dict]:
    organism = ORGANISMS[organism_key]
    resulted_time = datetime.now(timezone.utc) - timedelta(hours=max(0.5, hours_ago - 2))
    observations = []

    for abx_name, result_data in organism["susceptibilities"].items():
        loinc = SUSCEPTIBILITY_LOINC.get(abx_name, {"code": "18769-0", "display": f"{abx_name} [Susceptibility]"})
        interp = INTERPRETATION[result_data["result"]]
        obs_id = str(uuid.uuid4())

        observation = {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc["code"], "display": loinc["display"]}]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": resulted_time.isoformat(),
            "specimen": {"display": f"Culture - {organism['display']}"},
            "valueCodeableConcept": {"coding": [{"system": interp["system"], "code": interp["code"], "display": interp["display"]}]},
            "interpretation": [{"coding": [{"system": interp["system"], "code": interp["code"], "display": interp["display"]}]}],
        }

        if result_data.get("mic"):
            observation["component"] = [{"code": {"coding": [{"system": "http://loinc.org", "code": "35659-7", "display": "MIC"}]}, "valueString": f"{result_data['mic']} mcg/mL"}]

        observations.append(observation)
        report["result"].append({"reference": f"Observation/{obs_id}"})

    return observations


def upload_resource(resource: dict, fhir_url: str) -> bool:
    url = f"{fhir_url}/{resource['resourceType']}/{resource['id']}"
    try:
        response = requests.put(url, json=resource, headers={"Content-Type": "application/fhir+json"})
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  Error uploading {resource['resourceType']}: {e}")
        return False


def run_scenario(scenario_key: str, fhir_url: str, community_onset: bool = False, unit: str = None, dry_run: bool = False) -> dict:
    scenario = SCENARIOS[scenario_key]
    organism = ORGANISMS[scenario["organism"]]

    mrn = generate_mrn()
    patient = create_patient(mrn)
    patient_id = patient["id"]
    patient_name = f"{patient['name'][0]['given'][0]} {patient['name'][0]['family']}"

    # Community onset: admission same day as culture
    # Healthcare onset: admission 3+ days before culture
    admission_days_ago = 0 if community_onset else random.randint(3, 7)
    culture_hours_ago = 4

    encounter = create_encounter(patient_id, days_ago=admission_days_ago)
    selected_unit = unit or random.choice(UNITS)
    culture = create_culture_report(patient_id, scenario["organism"], selected_unit, hours_ago=culture_hours_ago)
    susceptibilities = create_susceptibility_observations(patient_id, culture, scenario["organism"], culture_hours_ago)

    onset_type = "Community" if community_onset else "Healthcare"

    result = {
        "scenario": scenario_key,
        "name": scenario["name"],
        "patient_name": patient_name,
        "mrn": mrn,
        "patient_id": patient_id,
        "unit": selected_unit,
        "onset_type": onset_type,
        "organism": organism["display"],
        "success": False,
    }

    print(f"\n{'─'*60}")
    print(f"Scenario: {scenario['name']} - {scenario['description']}")
    print(f"{'─'*60}")
    print(f"  Patient:    {patient_name} (MRN: {mrn})")
    print(f"  Unit:       {selected_unit}")
    print(f"  Onset:      {onset_type} (admitted {admission_days_ago} days ago)")
    print(f"  Organism:   {organism['display']}")

    if dry_run:
        print("  [DRY RUN - not uploaded]")
        result["success"] = True
        return result

    print(f"\n  Uploading to {fhir_url}...")

    for resource in [patient, encounter]:
        if upload_resource(resource, fhir_url):
            print(f"    ✓ {resource['resourceType']}")
        else:
            return result

    # Upload culture without result references first
    culture_results = culture.pop("result", [])
    culture.pop("_location", None)
    if upload_resource(culture, fhir_url):
        print(f"    ✓ DiagnosticReport")
    else:
        return result

    for obs in susceptibilities:
        if not upload_resource(obs, fhir_url):
            return result
    print(f"    ✓ {len(susceptibilities)} Susceptibility Observations")

    # Update culture with result references
    culture["result"] = culture_results
    upload_resource(culture, fhir_url)

    result["success"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate MDRO demo patients", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--scenario", "-s", choices=list(SCENARIOS.keys()), help="Specific MDRO scenario")
    parser.add_argument("--all", action="store_true", help="Run all MDRO scenarios")
    parser.add_argument("--community", action="store_true", help="Create as community-onset (<=48h)")
    parser.add_argument("--unit", type=str, help="Specific unit for the case")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--fhir-url", default="http://localhost:8081/fhir", help="FHIR server URL")
    parser.add_argument("--dry-run", action="store_true", help="Print without uploading")
    parser.add_argument("--list", "-l", action="store_true", help="List scenarios")

    args = parser.parse_args()

    if args.list:
        print("\nAvailable MDRO scenarios:\n")
        print(f"{'Scenario':<10} {'Name':<20} {'Description'}")
        print("─" * 60)
        for key, scenario in SCENARIOS.items():
            print(f"{key:<10} {scenario['name']:<20} {scenario['description']}")
        print(f"\nUnits: {', '.join(UNITS)}")
        return 0

    if not args.dry_run:
        try:
            requests.get(f"{args.fhir_url}/metadata", timeout=5).raise_for_status()
        except Exception as e:
            print(f"Error: Cannot connect to FHIR server at {args.fhir_url}: {e}")
            return 1

    results = []

    if args.interactive:
        print("\n=== MDRO Surveillance Demo - Interactive Mode ===\n")
        for key, scenario in SCENARIOS.items():
            print(f"  {key:<10} - {scenario['description']}")
        while True:
            choice = input("\nEnter scenario (or 'q' to quit): ").strip().lower()
            if choice == "q":
                break
            if choice in SCENARIOS:
                results.append(run_scenario(choice, args.fhir_url, args.community, args.unit, args.dry_run))
            else:
                print("Invalid scenario.")
    elif args.scenario:
        results = [run_scenario(args.scenario, args.fhir_url, args.community, args.unit, args.dry_run)]
    elif args.all:
        print("\n" + "=" * 60)
        print("RUNNING ALL MDRO SCENARIOS")
        print("=" * 60)
        for key in SCENARIOS:
            if key != "mssa":  # Skip non-MDRO control
                results.append(run_scenario(key, args.fhir_url, args.community, args.unit, args.dry_run))
    else:
        parser.error("Specify --scenario, --all, or --interactive")

    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        success_count = sum(1 for r in results if r["success"])
        print(f"\nCreated {success_count}/{len(results)} scenarios")
        if not args.dry_run:
            print("\nTo process, run the MDRO monitor:")
            print("  cd mdro-surveillance && python -m mdro_src.runner --once")

    return 0


if __name__ == "__main__":
    sys.exit(main())
