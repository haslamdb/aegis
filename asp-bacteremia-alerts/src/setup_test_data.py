#!/usr/bin/env python3
"""Set up test data in local HAPI FHIR server.

Creates test patients with various bacteremia scenarios to validate
the coverage alerting logic.
"""

import sys
from datetime import datetime, timedelta

import requests

FHIR_BASE = "http://localhost:8081/fhir"


def check_server():
    """Verify FHIR server is running."""
    try:
        response = requests.get(f"{FHIR_BASE}/metadata", timeout=5)
        response.raise_for_status()
        print("FHIR server is running")
        return True
    except Exception as e:
        print(f"ERROR: Cannot connect to FHIR server at {FHIR_BASE}")
        print(f"  {e}")
        print("\nMake sure to start the server with: docker-compose up -d")
        return False


def create_patient(mrn: str, name: str, birth_date: str = "2015-03-15") -> str:
    """Create a test patient, return FHIR ID."""
    name_parts = name.split()
    patient = {
        "resourceType": "Patient",
        "identifier": [{
            "system": "http://hospital.org/mrn",
            "value": mrn,
        }],
        "name": [{
            "family": name_parts[-1],
            "given": name_parts[:-1],
        }],
        "birthDate": birth_date,
        "gender": "female" if mrn.endswith(("1", "3", "5", "7")) else "male",
    }

    response = requests.post(
        f"{FHIR_BASE}/Patient",
        json=patient,
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]


def create_antibiotic_order(
    patient_id: str,
    medication_name: str,
    rxnorm_code: str,
    start_date: datetime | None = None,
) -> str:
    """Create an active antibiotic order."""
    start_date = start_date or (datetime.now() - timedelta(days=1))

    med_request = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "code": rxnorm_code,
                "display": medication_name,
            }],
            "text": medication_name,
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "authoredOn": start_date.isoformat(),
        "dosageInstruction": [{
            "text": f"{medication_name} IV",
            "route": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "47625008",
                    "display": "Intravenous route",
                }],
            },
        }],
    }

    response = requests.post(
        f"{FHIR_BASE}/MedicationRequest",
        json=med_request,
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]


def create_blood_culture_result(
    patient_id: str,
    organism: str,
    gram_stain: str | None = None,
    collected_date: datetime | None = None,
    resulted_date: datetime | None = None,
    status: str = "final",
) -> str:
    """Create a blood culture result."""
    collected_date = collected_date or (datetime.now() - timedelta(hours=24))
    resulted_date = resulted_date or (datetime.now() - timedelta(hours=1))

    # Determine SNOMED code based on organism
    snomed_code = "409822003"  # Default bacterial organism
    if "MRSA" in organism:
        snomed_code = "115329001"
    elif "VRE" in organism:
        snomed_code = "113727004"
    elif "Candida" in organism:
        snomed_code = "3265006"
    elif "Pseudomonas" in organism:
        snomed_code = "52499004"

    diagnostic_report = {
        "resourceType": "DiagnosticReport",
        "status": status,
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                "code": "MB",
                "display": "Microbiology",
            }],
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "600-7",
                "display": "Blood culture",
            }],
            "text": "Blood Culture",
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "effectiveDateTime": collected_date.isoformat(),
        "issued": resulted_date.isoformat(),
        "conclusion": organism if not gram_stain else f"{gram_stain}. {organism}",
        "conclusionCode": [{
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": snomed_code,
                "display": organism,
            }],
            "text": organism,
        }],
    }

    response = requests.post(
        f"{FHIR_BASE}/DiagnosticReport",
        json=diagnostic_report,
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]


def setup_test_scenarios() -> list[dict]:
    """Create test patients with various bacteremia scenarios."""
    scenarios = []

    # Scenario 1: MRSA bacteremia, patient only on cefazolin (MISMATCH)
    print("Creating Scenario 1: MRSA + cefazolin (should alert)...")
    patient_id = create_patient("TEST001", "Alice Johnson")
    create_antibiotic_order(patient_id, "Cefazolin 2g IV", "4053")
    create_blood_culture_result(
        patient_id,
        "MRSA - Methicillin resistant Staphylococcus aureus",
    )
    scenarios.append({
        "name": "MRSA on cefazolin",
        "patient_id": patient_id,
        "mrn": "TEST001",
        "expected": "ALERT - inadequate coverage",
    })

    # Scenario 2: MRSA bacteremia, patient on vancomycin (OK)
    print("Creating Scenario 2: MRSA + vancomycin (should NOT alert)...")
    patient_id = create_patient("TEST002", "Bob Smith")
    create_antibiotic_order(patient_id, "Vancomycin 1g IV", "11124")
    create_blood_culture_result(
        patient_id,
        "MRSA - Methicillin resistant Staphylococcus aureus",
    )
    scenarios.append({
        "name": "MRSA on vancomycin",
        "patient_id": patient_id,
        "mrn": "TEST002",
        "expected": "OK - adequate coverage",
    })

    # Scenario 3: Pseudomonas, patient on ceftriaxone (MISMATCH)
    print("Creating Scenario 3: Pseudomonas + ceftriaxone (should alert)...")
    patient_id = create_patient("TEST003", "Carol Davis")
    create_antibiotic_order(patient_id, "Ceftriaxone 2g IV", "2193")
    create_blood_culture_result(patient_id, "Pseudomonas aeruginosa")
    scenarios.append({
        "name": "Pseudomonas on ceftriaxone",
        "patient_id": patient_id,
        "mrn": "TEST003",
        "expected": "ALERT - inadequate coverage",
    })

    # Scenario 4: Pseudomonas, patient on cefepime (OK)
    print("Creating Scenario 4: Pseudomonas + cefepime (should NOT alert)...")
    patient_id = create_patient("TEST004", "David Wilson")
    create_antibiotic_order(patient_id, "Cefepime 2g IV", "2180")
    create_blood_culture_result(patient_id, "Pseudomonas aeruginosa")
    scenarios.append({
        "name": "Pseudomonas on cefepime",
        "patient_id": patient_id,
        "mrn": "TEST004",
        "expected": "OK - adequate coverage",
    })

    # Scenario 5: E. coli bacteremia, patient on pip-tazo (OK)
    print("Creating Scenario 5: E. coli + pip-tazo (should NOT alert)...")
    patient_id = create_patient("TEST005", "Eve Brown")
    create_antibiotic_order(patient_id, "Piperacillin-tazobactam 4.5g IV", "152834")
    create_blood_culture_result(patient_id, "Escherichia coli")
    scenarios.append({
        "name": "E. coli on pip-tazo",
        "patient_id": patient_id,
        "mrn": "TEST005",
        "expected": "OK - adequate coverage",
    })

    # Scenario 6: Candida, patient on antibacterials only (MISMATCH)
    print("Creating Scenario 6: Candida + vanc/cefepime only (should alert)...")
    patient_id = create_patient("TEST006", "Frank Miller")
    create_antibiotic_order(patient_id, "Vancomycin 1g IV", "11124")
    create_antibiotic_order(patient_id, "Cefepime 2g IV", "2180")
    create_blood_culture_result(patient_id, "Candida albicans")
    scenarios.append({
        "name": "Candidemia on antibacterials",
        "patient_id": patient_id,
        "mrn": "TEST006",
        "expected": "ALERT - inadequate coverage (needs antifungal)",
    })

    # Scenario 7: VRE, patient on vancomycin (MISMATCH)
    print("Creating Scenario 7: VRE + vancomycin (should alert)...")
    patient_id = create_patient("TEST007", "Grace Taylor")
    create_antibiotic_order(patient_id, "Vancomycin 1g IV", "11124")
    create_blood_culture_result(
        patient_id,
        "VRE - Vancomycin resistant Enterococcus faecium",
    )
    scenarios.append({
        "name": "VRE on vancomycin",
        "patient_id": patient_id,
        "mrn": "TEST007",
        "expected": "ALERT - inadequate coverage",
    })

    # Scenario 8: Preliminary gram stain only (GPC clusters on cefazolin)
    print("Creating Scenario 8: GPC clusters + cefazolin (should alert - empiric MRSA)...")
    patient_id = create_patient("TEST008", "Henry White")
    create_antibiotic_order(patient_id, "Cefazolin 2g IV", "4053")
    create_blood_culture_result(
        patient_id,
        organism="Pending identification",
        gram_stain="Gram positive cocci in clusters",
        status="preliminary",
    )
    scenarios.append({
        "name": "GPC clusters on cefazolin",
        "patient_id": patient_id,
        "mrn": "TEST008",
        "expected": "ALERT - add empiric MRSA coverage",
    })

    # Scenario 9: Klebsiella on ceftriaxone (OK for susceptible)
    print("Creating Scenario 9: Klebsiella + ceftriaxone (should NOT alert)...")
    patient_id = create_patient("TEST009", "Irene Martinez")
    create_antibiotic_order(patient_id, "Ceftriaxone 2g IV", "2193")
    create_blood_culture_result(patient_id, "Klebsiella pneumoniae")
    scenarios.append({
        "name": "Klebsiella on ceftriaxone",
        "patient_id": patient_id,
        "mrn": "TEST009",
        "expected": "OK - adequate coverage",
    })

    # Scenario 10: No antibiotics at all with positive culture
    print("Creating Scenario 10: E. coli with NO antibiotics (should alert)...")
    patient_id = create_patient("TEST010", "Jack Lee")
    create_blood_culture_result(patient_id, "Escherichia coli")
    scenarios.append({
        "name": "E. coli with no antibiotics",
        "patient_id": patient_id,
        "mrn": "TEST010",
        "expected": "ALERT - no antibiotics ordered",
    })

    return scenarios


def main():
    """Main entry point."""
    print("=" * 60)
    print("ASP Bacteremia Alerts - Test Data Setup")
    print("=" * 60)
    print()

    if not check_server():
        sys.exit(1)

    print()
    print("Creating test scenarios...")
    print("-" * 60)

    scenarios = setup_test_scenarios()

    print()
    print("=" * 60)
    print("TEST SCENARIOS CREATED")
    print("=" * 60)
    print()

    for i, s in enumerate(scenarios, 1):
        print(f"  {i:2}. {s['name']}")
        print(f"      Patient ID: {s['patient_id']}")
        print(f"      MRN: {s['mrn']}")
        print(f"      Expected: {s['expected']}")
        print()

    print("=" * 60)
    print("Setup complete! You can now run the monitor to test alerts.")
    print("  python -m src.monitor")
    print("=" * 60)


if __name__ == "__main__":
    main()
