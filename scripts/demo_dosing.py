#!/usr/bin/env python3
"""Generate demo patients with dosing issues for alert testing.

Creates patients with:
- Antimicrobials with inappropriate dosing, intervals, or routes
- Documented allergies with cross-reactive drugs
- Drug-drug interactions
- Renal impairment without dose adjustments

This triggers dosing verification alerts when the monitor runs.

Usage:
    # IV vancomycin for C. difficile (CRITICAL - wrong route)
    python demo_dosing.py --scenario cdi-iv-vanc

    # Penicillin allergy + cephalosporin (HIGH - cross-reactivity)
    python demo_dosing.py --scenario pcn-allergy-cephalosporin

    # Meningitis with subtherapeutic ceftriaxone (CRITICAL - underdosing)
    python demo_dosing.py --scenario meningitis-low-dose

    # Linezolid + SSRI (CRITICAL - DDI serotonin syndrome risk)
    python demo_dosing.py --scenario linezolid-ssri

    # Interactive mode
    python demo_dosing.py --interactive

    # Run all critical scenarios
    python demo_dosing.py --all-critical

    # List all scenarios
    python demo_dosing.py --list
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

# ============================================================================
# PREDEFINED SCENARIOS
# ============================================================================
SCENARIOS = {
    # === CRITICAL ROUTE ERRORS ===
    "cdi-iv-vanc": {
        "name": "C. difficile on IV Vancomycin",
        "description": "C. difficile colitis on IV vancomycin - CRITICAL (doesn't reach colon)",
        "indication": "c_difficile",
        "diagnosis_code": "A04.7",
        "diagnosis_display": "Enterocolitis due to Clostridium difficile",
        "antibiotic": "vancomycin",
        "dose": "1000",
        "dose_unit": "mg",
        "route": "IV",  # WRONG - should be PO
        "interval": "q12h",
        "expected_flag": "WRONG_ROUTE",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    "nitrofurantoin-bacteremia": {
        "name": "Bacteremia on Nitrofurantoin",
        "description": "E. coli bacteremia on nitrofurantoin - CRITICAL (no serum levels)",
        "indication": "bacteremia",
        "diagnosis_code": "A41.51",
        "diagnosis_display": "Sepsis due to Escherichia coli",
        "antibiotic": "nitrofurantoin",
        "dose": "100",
        "dose_unit": "mg",
        "route": "PO",
        "interval": "q6h",
        "expected_flag": "CONTRAINDICATED",
        "expected_severity": "critical",
        "expected_alert": True,
        "has_blood_culture": True,
        "organism": "112283007",  # E. coli
        "organism_display": "Escherichia coli",
    },

    "daptomycin-pneumonia": {
        "name": "Pneumonia on Daptomycin",
        "description": "MRSA pneumonia on daptomycin - CRITICAL (inactivated by surfactant)",
        "indication": "pneumonia",
        "diagnosis_code": "J15.212",
        "diagnosis_display": "Pneumonia due to Methicillin resistant Staphylococcus aureus",
        "antibiotic": "daptomycin",
        "dose": "6",
        "dose_unit": "mg/kg",
        "route": "IV",
        "interval": "q24h",
        "expected_flag": "CONTRAINDICATED",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    # === ALLERGY / CROSS-REACTIVITY ===
    "pcn-allergy-cephalosporin": {
        "name": "Penicillin Allergy + Cephalosporin",
        "description": "Penicillin allergy (anaphylaxis) on ceftriaxone - CRITICAL (cross-reactivity)",
        "indication": "pneumonia",
        "diagnosis_code": "J18.9",
        "diagnosis_display": "Pneumonia, unspecified organism",
        "antibiotic": "ceftriaxone",
        "dose": "1000",
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q24h",
        "allergies": [{
            "substance": "penicillin",
            "reaction": "anaphylaxis",
            "severity": "severe",
        }],
        "expected_flag": "ALLERGY_CROSS_REACTIVITY",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    "pcn-allergy-cephalexin": {
        "name": "Penicillin Allergy + Cephalexin (High Risk)",
        "description": "Penicillin allergy on cephalexin - CRITICAL (R1 side chain identical)",
        "indication": "cellulitis",
        "diagnosis_code": "L03.90",
        "diagnosis_display": "Cellulitis, unspecified",
        "antibiotic": "cephalexin",
        "dose": "500",
        "dose_unit": "mg",
        "route": "PO",
        "interval": "q6h",
        "allergies": [{
            "substance": "amoxicillin",
            "reaction": "rash",
            "severity": "moderate",
        }],
        "expected_flag": "ALLERGY_CROSS_REACTIVITY",
        "expected_severity": "high",  # Moderate reaction but high cross-reactivity
        "expected_alert": True,
    },

    "direct-allergy": {
        "name": "Direct Allergy Match",
        "description": "Vancomycin allergy on vancomycin - CRITICAL (exact match)",
        "indication": "bacteremia",
        "diagnosis_code": "A41.9",
        "diagnosis_display": "Sepsis, unspecified organism",
        "antibiotic": "vancomycin",
        "dose": "1000",
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q12h",
        "allergies": [{
            "substance": "vancomycin",
            "reaction": "red man syndrome",
            "severity": "moderate",
        }],
        "expected_flag": "ALLERGY_CONTRAINDICATED",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    # === DRUG-DRUG INTERACTIONS ===
    "linezolid-ssri": {
        "name": "Linezolid + SSRI",
        "description": "Linezolid + sertraline - CRITICAL (serotonin syndrome risk)",
        "indication": "bacteremia",
        "diagnosis_code": "A41.9",
        "diagnosis_display": "Sepsis, unspecified organism",
        "antibiotic": "linezolid",
        "dose": "600",
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q12h",
        "co_medications": [{
            "name": "sertraline",
            "dose": "50 mg daily",
        }],
        "expected_flag": "DRUG_INTERACTION",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    "meropenem-valproic": {
        "name": "Meropenem + Valproic Acid",
        "description": "Meropenem + valproic acid - CRITICAL (reduces VPA levels, seizure risk)",
        "indication": "meningitis",
        "diagnosis_code": "G03.9",
        "diagnosis_display": "Meningitis, unspecified",
        "antibiotic": "meropenem",
        "dose": "2000",
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q8h",
        "co_medications": [{
            "name": "valproic acid",
            "dose": "500 mg q12h",
        }],
        "expected_flag": "DRUG_INTERACTION",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    # === INDICATION-BASED DOSING ===
    "meningitis-low-dose": {
        "name": "Meningitis Underdosed Ceftriaxone",
        "description": "Meningitis on ceftriaxone 50 mg/kg/day - CRITICAL (should be 100 mg/kg/day)",
        "indication": "meningitis",
        "diagnosis_code": "G03.9",
        "diagnosis_display": "Meningitis, unspecified",
        "antibiotic": "ceftriaxone",
        "dose": "450",  # For 18 kg patient = 25 mg/kg/dose q12h = 50 mg/kg/day
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q12h",
        "patient_weight_kg": 18,
        "patient_age_years": 4,
        "expected_flag": "SUBTHERAPEUTIC_DOSE",
        "expected_severity": "critical",
        "expected_alert": True,
    },

    "endocarditis-low-dapto": {
        "name": "Endocarditis Low Daptomycin",
        "description": "Endocarditis on daptomycin 4 mg/kg - HIGH (should be 8-10 mg/kg)",
        "indication": "endocarditis",
        "diagnosis_code": "I33.0",
        "diagnosis_display": "Acute and subacute infective endocarditis",
        "antibiotic": "daptomycin",
        "dose": "280",  # For 70 kg patient = 4 mg/kg (skin dose, not endocarditis dose)
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q24h",
        "patient_weight_kg": 70,
        "patient_age_years": 45,
        "expected_flag": "SUBTHERAPEUTIC_DOSE",
        "expected_severity": "high",
        "expected_alert": True,
    },

    # === SAFE SCENARIOS (should NOT trigger alerts) ===
    "cdi-po-vanc": {
        "name": "C. difficile on PO Vancomycin (CORRECT)",
        "description": "C. difficile on PO vancomycin - Correct route",
        "indication": "c_difficile",
        "diagnosis_code": "A04.7",
        "diagnosis_display": "Enterocolitis due to Clostridium difficile",
        "antibiotic": "vancomycin",
        "dose": "125",
        "dose_unit": "mg",
        "route": "PO",  # CORRECT
        "interval": "q6h",
        "expected_alert": False,
    },

    "pcn-allergy-aztreonam": {
        "name": "Penicillin Allergy + Aztreonam (SAFE)",
        "description": "Penicillin allergy on aztreonam - No cross-reactivity",
        "indication": "pneumonia",
        "diagnosis_code": "J18.9",
        "diagnosis_display": "Pneumonia, unspecified organism",
        "antibiotic": "aztreonam",
        "dose": "2000",
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q8h",
        "allergies": [{
            "substance": "penicillin",
            "reaction": "anaphylaxis",
            "severity": "severe",
        }],
        "expected_alert": False,
    },

    "meningitis-correct-dose": {
        "name": "Meningitis Correct Dose (CORRECT)",
        "description": "Meningitis on ceftriaxone 100 mg/kg/day - Correct dosing",
        "indication": "meningitis",
        "diagnosis_code": "G03.9",
        "diagnosis_display": "Meningitis, unspecified",
        "antibiotic": "ceftriaxone",
        "dose": "900",  # For 18 kg patient = 50 mg/kg/dose q12h = 100 mg/kg/day
        "dose_unit": "mg",
        "route": "IV",
        "interval": "q12h",
        "patient_weight_kg": 18,
        "patient_age_years": 4,
        "expected_alert": False,
    },
}

# Antibiotics with RxNorm codes
ANTIBIOTICS = {
    "vancomycin": {"code": "11124", "display": "Vancomycin"},
    "ceftriaxone": {"code": "309092", "display": "Ceftriaxone"},
    "cephalexin": {"code": "2403", "display": "Cephalexin"},
    "daptomycin": {"code": "262090", "display": "Daptomycin"},
    "linezolid": {"code": "190376", "display": "Linezolid"},
    "nitrofurantoin": {"code": "7220", "display": "Nitrofurantoin"},
    "aztreonam": {"code": "858", "display": "Aztreonam"},
}

# Patient name components
FIRST_NAMES = ["Demo", "Test", "Dosing", "Alert", "Verify"]
LAST_NAMES = ["Patient", "Case", "Scenario", "Example", "Subject"]


def generate_mrn() -> str:
    """Generate a demo MRN."""
    return f"DOSE{random.randint(10000, 99999)}"


def create_patient(mrn: str, age_years: float = None, weight_kg: float = None) -> dict:
    """Create a Patient FHIR resource."""
    patient_id = str(uuid.uuid4())
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)

    # Calculate birth date from age
    if age_years is None:
        age_years = random.randint(2, 80)
    birth_date = (datetime.now() - timedelta(days=int(age_years * 365.25))).strftime("%Y-%m-%d")

    patient = {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {
                "type": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]
                },
                "value": mrn,
            }
        ],
        "name": [{"family": last_name, "given": [first_name]}],
        "gender": random.choice(["male", "female"]),
        "birthDate": birth_date,
    }

    return patient, age_years, weight_kg or (age_years * 3 + 7)  # Rough pediatric weight estimation


def create_encounter(patient_id: str) -> dict:
    """Create an inpatient Encounter."""
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
        "period": {"start": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 3))).isoformat()},
    }


def create_condition(patient_id: str, diagnosis_code: str, diagnosis_display: str) -> dict:
    """Create a Condition resource for the diagnosis."""
    return {
        "resourceType": "Condition",
        "id": str(uuid.uuid4()),
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": "active"
            }]
        },
        "code": {
            "coding": [{
                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                "code": diagnosis_code,
                "display": diagnosis_display
            }],
            "text": diagnosis_display
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "onsetDateTime": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    }


def create_weight_observation(patient_id: str, weight_kg: float) -> dict:
    """Create a weight Observation."""
    return {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
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
                "code": "29463-7",
                "display": "Body Weight"
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": datetime.now(timezone.utc).isoformat(),
        "valueQuantity": {
            "value": weight_kg,
            "unit": "kg",
            "system": "http://unitsofmeasure.org",
            "code": "kg"
        }
    }


def create_allergy_intolerance(patient_id: str, allergy: dict) -> dict:
    """Create an AllergyIntolerance resource."""
    severity_map = {
        "severe": "severe",
        "moderate": "moderate",
        "mild": "mild"
    }

    return {
        "resourceType": "AllergyIntolerance",
        "id": str(uuid.uuid4()),
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                "code": "active"
            }]
        },
        "type": "allergy",
        "category": ["medication"],
        "criticality": "high" if allergy["severity"] == "severe" else "low",
        "code": {
            "text": allergy["substance"].title()
        },
        "patient": {"reference": f"Patient/{patient_id}"},
        "reaction": [{
            "manifestation": [{
                "text": allergy["reaction"].title()
            }],
            "severity": severity_map.get(allergy["severity"], "moderate")
        }]
    }


def create_medication_request(
    patient_id: str,
    antibiotic_key: str,
    dose: str,
    dose_unit: str,
    route: str,
    interval: str,
    hours_ago: float = 12
) -> dict:
    """Create a MedicationRequest for an antibiotic."""
    antibiotic = ANTIBIOTICS.get(antibiotic_key, {"code": "unknown", "display": antibiotic_key})
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    route_code_map = {
        "IV": {"code": "47625008", "display": "Intravenous"},
        "PO": {"code": "26643006", "display": "Oral"},
        "IM": {"code": "78421000", "display": "Intramuscular"},
    }
    route_coding = route_code_map.get(route, {"code": "unknown", "display": route})

    return {
        "resourceType": "MedicationRequest",
        "id": str(uuid.uuid4()),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": antibiotic["code"], "display": antibiotic["display"]}
            ],
            "text": antibiotic["display"],
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": start_time.isoformat(),
        "dosageInstruction": [
            {
                "text": f"{dose} {dose_unit} {interval} {route}",
                "timing": {
                    "repeat": {
                        "frequency": 1,
                        "period": int(interval.replace("q", "").replace("h", "")),
                        "periodUnit": "h"
                    }
                },
                "route": {
                    "coding": [{"system": "http://snomed.info/sct", "code": route_coding["code"], "display": route_coding["display"]}]
                },
                "doseAndRate": [{
                    "doseQuantity": {
                        "value": float(dose),
                        "unit": dose_unit
                    }
                }]
            }
        ],
    }


def create_co_medication(patient_id: str, med: dict) -> dict:
    """Create a MedicationRequest for a co-medication."""
    return {
        "resourceType": "MedicationRequest",
        "id": str(uuid.uuid4()),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "text": med["name"].title()
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        "dosageInstruction": [{
            "text": med["dose"]
        }]
    }


def upload_resource(resource: dict, fhir_url: str) -> bool:
    """Upload a FHIR resource."""
    url = f"{fhir_url}/{resource['resourceType']}/{resource['id']}"
    try:
        response = requests.put(url, json=resource, headers={"Content-Type": "application/fhir+json"})
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  Error uploading {resource['resourceType']}: {e}")
        return False


def run_scenario(scenario_key: str, fhir_url: str, dry_run: bool = False) -> dict:
    """Run a single scenario and return results."""
    scenario = SCENARIOS[scenario_key]

    # Create resources
    mrn = generate_mrn()
    patient, age, weight = create_patient(
        mrn,
        age_years=scenario.get("patient_age_years"),
        weight_kg=scenario.get("patient_weight_kg")
    )
    patient_id = patient["id"]
    patient_name = f"{patient['name'][0]['given'][0]} {patient['name'][0]['family']}"

    encounter = create_encounter(patient_id)
    condition = create_condition(patient_id, scenario["diagnosis_code"], scenario["diagnosis_display"])
    weight_obs = create_weight_observation(patient_id, weight)

    medication = create_medication_request(
        patient_id,
        scenario["antibiotic"],
        scenario["dose"],
        scenario["dose_unit"],
        scenario["route"],
        scenario["interval"]
    )

    # Allergies
    allergies = []
    if scenario.get("allergies"):
        for allergy_data in scenario["allergies"]:
            allergies.append(create_allergy_intolerance(patient_id, allergy_data))

    # Co-medications
    co_meds = []
    if scenario.get("co_medications"):
        for med_data in scenario["co_medications"]:
            co_meds.append(create_co_medication(patient_id, med_data))

    result = {
        "scenario": scenario_key,
        "name": scenario["name"],
        "patient_name": patient_name,
        "mrn": mrn,
        "patient_id": patient_id,
        "indication": scenario.get("indication"),
        "antibiotic": scenario["antibiotic"],
        "route": scenario["route"],
        "expected_alert": scenario["expected_alert"],
        "expected_flag": scenario.get("expected_flag"),
        "success": False,
    }

    print(f"\n{'─'*70}")
    print(f"Scenario: {scenario['name']}")
    print(f"{'─'*70}")
    print(f"  Patient:      {patient_name} (MRN: {mrn})")
    print(f"  Age/Weight:   {age:.1f} years, {weight:.1f} kg")
    print(f"  Diagnosis:    {scenario['diagnosis_display']}")
    print(f"  Antibiotic:   {scenario['antibiotic']} {scenario['dose']} {scenario['dose_unit']} {scenario['interval']} {scenario['route']}")
    if scenario.get("allergies"):
        for allergy in scenario["allergies"]:
            print(f"  Allergy:      {allergy['substance'].title()} ({allergy['reaction']})")
    if scenario.get("co_medications"):
        for med in scenario["co_medications"]:
            print(f"  Co-Med:       {med['name'].title()} ({med['dose']})")
    print(f"  Expected:     {'ALERT (' + scenario.get('expected_flag', '') + ')' if scenario['expected_alert'] else 'No alert'}")

    if dry_run:
        print("  [DRY RUN - not uploaded]")
        result["success"] = True
        return result

    print(f"\n  Uploading to {fhir_url}...")

    # Upload resources
    resources = [patient, encounter, condition, weight_obs, medication] + allergies + co_meds
    for resource in resources:
        if upload_resource(resource, fhir_url):
            print(f"    ✓ {resource['resourceType']}")
        else:
            print(f"    ✗ {resource['resourceType']} FAILED")
            return result

    result["success"] = True
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate dosing verification demo scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--scenario", "-s", choices=list(SCENARIOS.keys()), help="Specific scenario to run")
    parser.add_argument("--all-critical", action="store_true", help="Run all critical alert scenarios")
    parser.add_argument("--all", action="store_true", help="Run ALL scenarios (including safe ones)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--fhir-url", default="http://localhost:8081/fhir", help="FHIR server URL")
    parser.add_argument("--dry-run", action="store_true", help="Print without uploading")
    parser.add_argument("--list", "-l", action="store_true", help="List available scenarios")

    args = parser.parse_args()

    if args.list:
        print("\nAvailable scenarios:\n")
        print(f"{'Scenario':<30} {'Flag Type':<25} {'Severity':<10} {'Alert?'}")
        print("─" * 80)
        for key, scenario in SCENARIOS.items():
            flag = scenario.get("expected_flag", "N/A")
            severity = scenario.get("expected_severity", "N/A")
            alert = "YES" if scenario["expected_alert"] else "No"
            print(f"{key:<30} {flag:<25} {severity:<10} {alert}")
        return 0

    # Check FHIR server connectivity
    if not args.dry_run:
        try:
            requests.get(f"{args.fhir_url}/metadata", timeout=5).raise_for_status()
        except Exception as e:
            print(f"Error: Cannot connect to FHIR server at {args.fhir_url}: {e}")
            return 1

    results = []

    if args.scenario:
        results = [run_scenario(args.scenario, args.fhir_url, args.dry_run)]
    elif args.all_critical:
        print("\n" + "=" * 70)
        print("RUNNING ALL CRITICAL SCENARIOS")
        print("=" * 70)
        for key, scenario in SCENARIOS.items():
            if scenario["expected_alert"] and scenario.get("expected_severity") == "critical":
                results.append(run_scenario(key, args.fhir_url, args.dry_run))
    elif args.all:
        print("\n" + "=" * 70)
        print("RUNNING ALL SCENARIOS")
        print("=" * 70)
        for key in SCENARIOS:
            results.append(run_scenario(key, args.fhir_url, args.dry_run))
    else:
        parser.error("Specify --scenario, --all-critical, --all, or --interactive")

    # Summary
    if results:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        success_count = sum(1 for r in results if r["success"])
        alert_count = sum(1 for r in results if r["success"] and r["expected_alert"])

        print(f"\nCreated {success_count}/{len(results)} scenarios successfully")
        print(f"Expected alerts: {alert_count}")

        if not args.dry_run:
            print("\nTo test, run the dosing verification monitor:")
            print("  cd dosing-verification && python -m src.runner --once")

    return 0


if __name__ == "__main__":
    sys.exit(main())
