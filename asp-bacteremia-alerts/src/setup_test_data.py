#!/usr/bin/env python3
"""Set up test data in local HAPI FHIR server.

Creates test patients with various bacteremia and broad-spectrum antibiotic
scenarios to validate the coverage alerting logic.

Customized for CCHMC pediatric infectious disease scenarios.
"""

import random
import sys
from datetime import datetime, timedelta

import requests

FHIR_BASE = "http://localhost:8081/fhir"

# CCHMC-specific units and departments
CCHMC_UNITS = {
    "A6N": {"beds": 42, "department": "Hospital Medicine"},
    "A6S": {"beds": 42, "department": "Hospital Medicine"},
    "G5S": {"beds": 24, "department": "Oncology"},
    "G6N": {"beds": 24, "department": "Bone Marrow Transplant"},
    "T5A": {"beds": 20, "department": "PICU"},
    "T5B": {"beds": 16, "department": "CICU"},
    "T4": {"beds": 48, "department": "NICU"},
    "A5N": {"beds": 30, "department": "Surgery"},
    "A5S": {"beds": 30, "department": "General Pediatrics"},
}

DEPARTMENTS = [
    "Oncology",
    "Bone Marrow Transplant",
    "Hospital Medicine",
    "PICU",
    "CICU",
    "NICU",
    "Infectious Disease",
    "Surgery",
    "General Pediatrics",
]

# Pediatric first names
PEDIATRIC_FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason",
    "Isabella", "William", "Mia", "James", "Charlotte", "Benjamin", "Amelia",
    "Lucas", "Harper", "Henry", "Evelyn", "Alexander", "Abigail", "Michael",
    "Emily", "Daniel", "Elizabeth", "Jacob", "Sofia", "Logan", "Avery", "Jackson",
    "Ella", "Sebastian", "Scarlett", "Mateo", "Grace", "Owen", "Chloe", "Samuel",
    "Victoria", "Ryan", "Riley", "Nathan", "Aria", "Leo", "Lily", "Isaac",
    "Aurora", "Jayden", "Zoey", "Luke",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
]


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


def random_location() -> tuple[str, str]:
    """Generate a random CCHMC location (unit, bed, department)."""
    unit = random.choice(list(CCHMC_UNITS.keys()))
    bed = random.randint(1, CCHMC_UNITS[unit]["beds"])
    department = CCHMC_UNITS[unit]["department"]
    return f"{unit}-{bed:02d}", department


def random_pediatric_birthdate() -> str:
    """Generate a random pediatric birthdate (0-18 years old)."""
    days_old = random.randint(1, 18 * 365)
    birth_date = datetime.now() - timedelta(days=days_old)
    return birth_date.strftime("%Y-%m-%d")


def random_name() -> str:
    """Generate a random pediatric name."""
    first = random.choice(PEDIATRIC_FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"


def create_patient(
    mrn: str,
    name: str,
    birth_date: str | None = None,
    location: str | None = None,
    department: str | None = None,
) -> str:
    """Create a test patient, return FHIR ID."""
    if birth_date is None:
        birth_date = random_pediatric_birthdate()

    if location is None:
        location, department = random_location()
    elif department is None:
        department = "Hospital Medicine"

    name_parts = name.split()
    patient = {
        "resourceType": "Patient",
        "identifier": [
            {
                "system": "http://cchmc.org/mrn",
                "value": mrn,
            }
        ],
        "name": [
            {
                "family": name_parts[-1],
                "given": name_parts[:-1],
            }
        ],
        "birthDate": birth_date,
        "gender": random.choice(["male", "female"]),
        # Store location in an extension (FHIR way to track current location)
        "extension": [
            {
                "url": "http://cchmc.org/fhir/StructureDefinition/patient-location",
                "valueString": location,
            },
            {
                "url": "http://cchmc.org/fhir/StructureDefinition/patient-department",
                "valueString": department,
            },
        ],
    }

    response = requests.post(
        f"{FHIR_BASE}/Patient",
        json=patient,
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]


def create_encounter(
    patient_id: str,
    location: str,
    department: str,
    admit_date: datetime | None = None,
) -> str:
    """Create an active encounter for the patient."""
    admit_date = admit_date or (datetime.now() - timedelta(days=random.randint(1, 14)))

    encounter = {
        "resourceType": "Encounter",
        "status": "in-progress",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "IMP",
            "display": "inpatient encounter",
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "period": {
            "start": admit_date.isoformat(),
        },
        "location": [
            {
                "location": {
                    "display": location,
                },
                "status": "active",
            }
        ],
        "serviceType": {
            "coding": [
                {
                    "system": "http://cchmc.org/department",
                    "display": department,
                }
            ],
        },
    }

    response = requests.post(
        f"{FHIR_BASE}/Encounter",
        json=encounter,
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]


def create_antibiotic_order(
    patient_id: str,
    medication_name: str,
    rxnorm_code: str,
    start_date: datetime | None = None,
    dose: str = "",
) -> str:
    """Create an active antibiotic order."""
    start_date = start_date or (datetime.now() - timedelta(days=1))

    med_request = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "code": rxnorm_code,
                    "display": medication_name,
                }
            ],
            "text": f"{medication_name} {dose}".strip(),
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "authoredOn": start_date.isoformat(),
        "dosageInstruction": [
            {
                "text": f"{medication_name} {dose} IV".strip(),
                "route": {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "47625008",
                            "display": "Intravenous route",
                        }
                    ],
                },
            }
        ],
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
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "MB",
                        "display": "Microbiology",
                    }
                ],
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "600-7",
                    "display": "Blood culture",
                }
            ],
            "text": "Blood Culture",
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "effectiveDateTime": collected_date.isoformat(),
        "issued": resulted_date.isoformat(),
        "conclusion": organism if not gram_stain else f"{gram_stain}. {organism}",
        "conclusionCode": [
            {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": snomed_code,
                        "display": organism,
                    }
                ],
                "text": organism,
            }
        ],
    }

    response = requests.post(
        f"{FHIR_BASE}/DiagnosticReport",
        json=diagnostic_report,
        headers={"Content-Type": "application/fhir+json"},
    )
    response.raise_for_status()
    return response.json()["id"]


def setup_bacteremia_scenarios() -> list[dict]:
    """Create test patients with bacteremia coverage scenarios."""
    scenarios = []

    # Scenario 1: MRSA bacteremia, patient only on cefazolin (MISMATCH)
    print("Creating Scenario 1: MRSA + cefazolin (should alert)...")
    location, dept = "G5S-12", "Oncology"
    patient_id = create_patient("CCHMC001", "Emma Thompson", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Cefazolin", "4053", dose="50mg/kg")
    create_blood_culture_result(
        patient_id,
        "MRSA - Methicillin resistant Staphylococcus aureus",
    )
    scenarios.append({
        "name": "MRSA on cefazolin",
        "patient_id": patient_id,
        "mrn": "CCHMC001",
        "location": location,
        "expected": "ALERT - inadequate coverage",
    })

    # Scenario 2: MRSA bacteremia, patient on vancomycin (OK)
    print("Creating Scenario 2: MRSA + vancomycin (should NOT alert)...")
    location, dept = "A6N-15", "Hospital Medicine"
    patient_id = create_patient("CCHMC002", "Liam Garcia", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Vancomycin", "11124", dose="15mg/kg")
    create_blood_culture_result(
        patient_id,
        "MRSA - Methicillin resistant Staphylococcus aureus",
    )
    scenarios.append({
        "name": "MRSA on vancomycin",
        "patient_id": patient_id,
        "mrn": "CCHMC002",
        "location": location,
        "expected": "OK - adequate coverage",
    })

    # Scenario 3: Pseudomonas, patient on ceftriaxone (MISMATCH)
    print("Creating Scenario 3: Pseudomonas + ceftriaxone (should alert)...")
    location, dept = "T5A-08", "PICU"
    patient_id = create_patient("CCHMC003", "Olivia Martinez", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Ceftriaxone", "2193", dose="50mg/kg")
    create_blood_culture_result(patient_id, "Pseudomonas aeruginosa")
    scenarios.append({
        "name": "Pseudomonas on ceftriaxone",
        "patient_id": patient_id,
        "mrn": "CCHMC003",
        "location": location,
        "expected": "ALERT - inadequate coverage",
    })

    # Scenario 4: Pseudomonas, patient on meropenem (OK)
    print("Creating Scenario 4: Pseudomonas + meropenem (should NOT alert)...")
    location, dept = "G6N-05", "Bone Marrow Transplant"
    patient_id = create_patient("CCHMC004", "Noah Wilson", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Meropenem", "29561", dose="20mg/kg")
    create_blood_culture_result(patient_id, "Pseudomonas aeruginosa")
    scenarios.append({
        "name": "Pseudomonas on meropenem",
        "patient_id": patient_id,
        "mrn": "CCHMC004",
        "location": location,
        "expected": "OK - adequate coverage",
    })

    # Scenario 5: E. coli bacteremia, patient on pip-tazo (OK)
    print("Creating Scenario 5: E. coli + pip-tazo (should NOT alert)...")
    location, dept = "A5S-22", "General Pediatrics"
    patient_id = create_patient("CCHMC005", "Ava Brown", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Piperacillin-tazobactam", "152834", dose="100mg/kg")
    create_blood_culture_result(patient_id, "Escherichia coli")
    scenarios.append({
        "name": "E. coli on pip-tazo",
        "patient_id": patient_id,
        "mrn": "CCHMC005",
        "location": location,
        "expected": "OK - adequate coverage",
    })

    # Scenario 6: Candida, patient on antibacterials only (MISMATCH)
    print("Creating Scenario 6: Candida + vanc/meropenem only (should alert)...")
    location, dept = "G6N-18", "Bone Marrow Transplant"
    patient_id = create_patient("CCHMC006", "Ethan Lee", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Vancomycin", "11124", dose="15mg/kg")
    create_antibiotic_order(patient_id, "Meropenem", "29561", dose="20mg/kg")
    create_blood_culture_result(patient_id, "Candida albicans")
    scenarios.append({
        "name": "Candidemia on antibacterials",
        "patient_id": patient_id,
        "mrn": "CCHMC006",
        "location": location,
        "expected": "ALERT - inadequate coverage (needs antifungal)",
    })

    # Scenario 7: VRE, patient on vancomycin (MISMATCH)
    print("Creating Scenario 7: VRE + vancomycin (should alert)...")
    location, dept = "G5S-03", "Oncology"
    patient_id = create_patient("CCHMC007", "Sophia Davis", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Vancomycin", "11124", dose="15mg/kg")
    create_blood_culture_result(
        patient_id,
        "VRE - Vancomycin resistant Enterococcus faecium",
    )
    scenarios.append({
        "name": "VRE on vancomycin",
        "patient_id": patient_id,
        "mrn": "CCHMC007",
        "location": location,
        "expected": "ALERT - inadequate coverage",
    })

    # Scenario 8: Preliminary gram stain only (GPC clusters on cefazolin)
    print("Creating Scenario 8: GPC clusters + cefazolin (should alert - empiric MRSA)...")
    location, dept = "T5B-11", "CICU"
    patient_id = create_patient("CCHMC008", "Mason Anderson", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Cefazolin", "4053", dose="50mg/kg")
    create_blood_culture_result(
        patient_id,
        organism="Pending identification",
        gram_stain="Gram positive cocci in clusters",
        status="preliminary",
    )
    scenarios.append({
        "name": "GPC clusters on cefazolin",
        "patient_id": patient_id,
        "mrn": "CCHMC008",
        "location": location,
        "expected": "ALERT - add empiric MRSA coverage",
    })

    # Scenario 9: Klebsiella on ceftriaxone (OK for susceptible)
    print("Creating Scenario 9: Klebsiella + ceftriaxone (should NOT alert)...")
    location, dept = "T4-32", "NICU"
    patient_id = create_patient("CCHMC009", "Isabella White", location=location, department=dept,
                                birth_date=(datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"))
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(patient_id, "Ceftriaxone", "2193", dose="50mg/kg")
    create_blood_culture_result(patient_id, "Klebsiella pneumoniae")
    scenarios.append({
        "name": "Klebsiella on ceftriaxone",
        "patient_id": patient_id,
        "mrn": "CCHMC009",
        "location": location,
        "expected": "OK - adequate coverage",
    })

    # Scenario 10: No antibiotics at all with positive culture
    print("Creating Scenario 10: E. coli with NO antibiotics (should alert)...")
    location, dept = "A6S-28", "Hospital Medicine"
    patient_id = create_patient("CCHMC010", "William Harris", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_blood_culture_result(patient_id, "Escherichia coli")
    scenarios.append({
        "name": "E. coli with no antibiotics",
        "patient_id": patient_id,
        "mrn": "CCHMC010",
        "location": location,
        "expected": "ALERT - no antibiotics ordered",
    })

    return scenarios


def setup_broad_spectrum_scenarios() -> list[dict]:
    """Create test patients on broad-spectrum antibiotics for duration monitoring.

    These scenarios test alerts for meropenem and vancomycin use > 72 hours.
    """
    scenarios = []
    now = datetime.now()

    # Scenario 11: Meropenem for 24 hours (should NOT alert - too early)
    print("Creating Scenario 11: Meropenem x 24 hours (should NOT alert)...")
    location, dept = "T5A-03", "PICU"
    patient_id = create_patient("CCHMC011", "Charlotte Clark", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Meropenem", "29561", dose="20mg/kg",
        start_date=now - timedelta(hours=24)
    )
    scenarios.append({
        "name": "Meropenem x 24h",
        "patient_id": patient_id,
        "mrn": "CCHMC011",
        "location": location,
        "duration_hours": 24,
        "expected": "OK - under 72 hour threshold",
    })

    # Scenario 12: Meropenem for 48 hours (should NOT alert - too early)
    print("Creating Scenario 12: Meropenem x 48 hours (should NOT alert)...")
    location, dept = "G6N-09", "Bone Marrow Transplant"
    patient_id = create_patient("CCHMC012", "Benjamin Rodriguez", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Meropenem", "29561", dose="20mg/kg",
        start_date=now - timedelta(hours=48)
    )
    scenarios.append({
        "name": "Meropenem x 48h",
        "patient_id": patient_id,
        "mrn": "CCHMC012",
        "location": location,
        "duration_hours": 48,
        "expected": "OK - under 72 hour threshold",
    })

    # Scenario 13: Meropenem for 73 hours (should ALERT)
    print("Creating Scenario 13: Meropenem x 73 hours (should ALERT)...")
    location, dept = "G5S-17", "Oncology"
    patient_id = create_patient("CCHMC013", "Amelia Lewis", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Meropenem", "29561", dose="20mg/kg",
        start_date=now - timedelta(hours=73)
    )
    scenarios.append({
        "name": "Meropenem x 73h",
        "patient_id": patient_id,
        "mrn": "CCHMC013",
        "location": location,
        "duration_hours": 73,
        "expected": "ALERT - meropenem > 72 hours",
    })

    # Scenario 14: Meropenem for 5 days (should ALERT)
    print("Creating Scenario 14: Meropenem x 5 days (should ALERT)...")
    location, dept = "T5B-05", "CICU"
    patient_id = create_patient("CCHMC014", "James Walker", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Meropenem", "29561", dose="20mg/kg",
        start_date=now - timedelta(days=5)
    )
    scenarios.append({
        "name": "Meropenem x 5 days",
        "patient_id": patient_id,
        "mrn": "CCHMC014",
        "location": location,
        "duration_hours": 120,
        "expected": "ALERT - meropenem > 72 hours",
    })

    # Scenario 15: Vancomycin for 24 hours (should NOT alert)
    print("Creating Scenario 15: Vancomycin x 24 hours (should NOT alert)...")
    location, dept = "A6N-33", "Hospital Medicine"
    patient_id = create_patient("CCHMC015", "Harper Young", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Vancomycin", "11124", dose="15mg/kg",
        start_date=now - timedelta(hours=24)
    )
    scenarios.append({
        "name": "Vancomycin x 24h",
        "patient_id": patient_id,
        "mrn": "CCHMC015",
        "location": location,
        "duration_hours": 24,
        "expected": "OK - under 72 hour threshold",
    })

    # Scenario 16: Vancomycin for 80 hours (should ALERT)
    print("Creating Scenario 16: Vancomycin x 80 hours (should ALERT)...")
    location, dept = "G5S-21", "Oncology"
    patient_id = create_patient("CCHMC016", "Evelyn Allen", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Vancomycin", "11124", dose="15mg/kg",
        start_date=now - timedelta(hours=80)
    )
    scenarios.append({
        "name": "Vancomycin x 80h",
        "patient_id": patient_id,
        "mrn": "CCHMC016",
        "location": location,
        "duration_hours": 80,
        "expected": "ALERT - vancomycin > 72 hours",
    })

    # Scenario 17: Both meropenem AND vancomycin > 72 hours (should ALERT for both)
    print("Creating Scenario 17: Meropenem + Vancomycin x 96 hours (should ALERT)...")
    location, dept = "G6N-14", "Bone Marrow Transplant"
    patient_id = create_patient("CCHMC017", "Henry King", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Meropenem", "29561", dose="20mg/kg",
        start_date=now - timedelta(hours=96)
    )
    create_antibiotic_order(
        patient_id, "Vancomycin", "11124", dose="15mg/kg",
        start_date=now - timedelta(hours=96)
    )
    scenarios.append({
        "name": "Meropenem + Vancomycin x 96h",
        "patient_id": patient_id,
        "mrn": "CCHMC017",
        "location": location,
        "duration_hours": 96,
        "expected": "ALERT - both meropenem and vancomycin > 72 hours",
    })

    # Scenario 18: Vancomycin for 7 days with positive MRSA culture (justified use)
    print("Creating Scenario 18: Vancomycin x 7 days with MRSA (may be justified)...")
    location, dept = "A6S-11", "Hospital Medicine"
    patient_id = create_patient("CCHMC018", "Alexander Scott", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Vancomycin", "11124", dose="15mg/kg",
        start_date=now - timedelta(days=7)
    )
    create_blood_culture_result(
        patient_id, "MRSA - Methicillin resistant Staphylococcus aureus",
        collected_date=now - timedelta(days=8),
        resulted_date=now - timedelta(days=7)
    )
    scenarios.append({
        "name": "Vancomycin x 7d with MRSA",
        "patient_id": patient_id,
        "mrn": "CCHMC018",
        "location": location,
        "duration_hours": 168,
        "expected": "ALERT - but may be justified (MRSA bacteremia)",
    })

    # Scenario 19: Meropenem for 10 days - extended course
    print("Creating Scenario 19: Meropenem x 10 days (should ALERT - extended)...")
    location, dept = "T5A-12", "PICU"
    patient_id = create_patient("CCHMC019", "Mia Green", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Meropenem", "29561", dose="40mg/kg",
        start_date=now - timedelta(days=10)
    )
    scenarios.append({
        "name": "Meropenem x 10 days",
        "patient_id": patient_id,
        "mrn": "CCHMC019",
        "location": location,
        "duration_hours": 240,
        "expected": "ALERT - meropenem > 72 hours (extended course)",
    })

    # Scenario 20: Cefepime for 5 days (another broad-spectrum to potentially track)
    print("Creating Scenario 20: Cefepime x 5 days (potential future tracking)...")
    location, dept = "A5N-07", "Surgery"
    patient_id = create_patient("CCHMC020", "Daniel Baker", location=location, department=dept)
    create_encounter(patient_id, location, dept)
    create_antibiotic_order(
        patient_id, "Cefepime", "2180", dose="50mg/kg",
        start_date=now - timedelta(days=5)
    )
    scenarios.append({
        "name": "Cefepime x 5 days",
        "patient_id": patient_id,
        "mrn": "CCHMC020",
        "location": location,
        "duration_hours": 120,
        "expected": "OK - not tracking cefepime (future enhancement)",
    })

    return scenarios


def main():
    """Main entry point."""
    print("=" * 70)
    print("ASP Alerts - CCHMC Test Data Setup")
    print("=" * 70)
    print()

    if not check_server():
        sys.exit(1)

    print()
    print("Creating bacteremia coverage scenarios...")
    print("-" * 70)

    bacteremia_scenarios = setup_bacteremia_scenarios()

    print()
    print("Creating broad-spectrum antibiotic duration scenarios...")
    print("-" * 70)

    broad_spectrum_scenarios = setup_broad_spectrum_scenarios()

    all_scenarios = bacteremia_scenarios + broad_spectrum_scenarios

    print()
    print("=" * 70)
    print("TEST SCENARIOS CREATED")
    print("=" * 70)
    print()

    print("BACTEREMIA COVERAGE SCENARIOS:")
    print("-" * 70)
    for i, s in enumerate(bacteremia_scenarios, 1):
        print(f"  {i:2}. {s['name']}")
        print(f"      MRN: {s['mrn']}  |  Location: {s['location']}")
        print(f"      Expected: {s['expected']}")
        print()

    print("BROAD-SPECTRUM DURATION SCENARIOS:")
    print("-" * 70)
    for i, s in enumerate(broad_spectrum_scenarios, 1):
        print(f"  {i + 10:2}. {s['name']}")
        print(f"      MRN: {s['mrn']}  |  Location: {s['location']}")
        print(f"      Duration: {s['duration_hours']} hours")
        print(f"      Expected: {s['expected']}")
        print()

    print("=" * 70)
    print("Setup complete!")
    print()
    print("To test bacteremia coverage alerts:")
    print("  python -m src.monitor")
    print()
    print("Broad-spectrum duration monitoring coming soon...")
    print("=" * 70)


if __name__ == "__main__":
    main()
