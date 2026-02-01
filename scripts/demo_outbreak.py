#!/usr/bin/env python3
"""Generate demo outbreak scenarios for testing Outbreak Detection.

Creates clusters of cases in the same unit to trigger outbreak alerts.
Can create MDRO cases directly in the MDRO database, or use FHIR to
trigger the full pipeline.

Usage:
    # MRSA outbreak in ICU-A (3 cases)
    python demo_outbreak.py --scenario mrsa-icu --cases 3

    # VRE outbreak in Med-Surg
    python demo_outbreak.py --scenario vre-medsurg --cases 4

    # Create outbreak directly in database (no FHIR)
    python demo_outbreak.py --scenario mrsa-icu --direct

    # Multi-unit outbreak
    python demo_outbreak.py --scenario multi-unit

    # List scenarios
    python demo_outbreak.py --list
"""

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mdro-surveillance"))
sys.path.insert(0, str(Path(__file__).parent.parent / "outbreak-detection"))

import requests

# ============================================================================
# OUTBREAK SCENARIOS
# ============================================================================
SCENARIOS = {
    "mrsa-icu": {
        "name": "MRSA ICU Outbreak",
        "description": "Multiple MRSA cases in ICU-A",
        "infection_type": "mrsa",
        "unit": "ICU-A",
        "default_cases": 3,
    },
    "vre-medsurg": {
        "name": "VRE Med-Surg Outbreak",
        "description": "VRE cluster on Med-Surg 3",
        "infection_type": "vre",
        "unit": "Med-Surg 3",
        "default_cases": 4,
    },
    "cre-micu": {
        "name": "CRE MICU Outbreak",
        "description": "CRE cluster in Medical ICU (critical)",
        "infection_type": "cre",
        "unit": "MICU",
        "default_cases": 5,
    },
    "esbl-oncology": {
        "name": "ESBL Oncology Outbreak",
        "description": "ESBL E. coli on Oncology unit",
        "infection_type": "esbl",
        "unit": "Oncology",
        "default_cases": 3,
    },
    "cdi-medsurg": {
        "name": "C. diff Med-Surg Outbreak",
        "description": "CDI cluster on Med-Surg 4",
        "infection_type": "cdi",
        "unit": "Med-Surg 4",
        "default_cases": 4,
    },
    "multi-unit": {
        "name": "Multi-Unit MRSA",
        "description": "MRSA spreading across ICU-A and ICU-B",
        "infection_type": "mrsa",
        "units": ["ICU-A", "ICU-B"],
        "default_cases": 6,
    },
}

FIRST_NAMES = ["Outbreak", "Cluster", "Demo", "Test", "Alert"]
LAST_NAMES = ["Patient", "Case", "Subject", "Index", "Contact"]

ORGANISMS = {
    "mrsa": "Staphylococcus aureus (MRSA)",
    "vre": "Enterococcus faecium (VRE)",
    "cre": "Klebsiella pneumoniae (CRE)",
    "esbl": "Escherichia coli (ESBL)",
    "crpa": "Pseudomonas aeruginosa (CRPA)",
    "crab": "Acinetobacter baumannii (CRAB)",
    "cdi": "Clostridioides difficile",
}


def generate_mrn() -> str:
    return f"OB{random.randint(10000, 99999)}"


def create_mdro_case_direct(
    infection_type: str,
    unit: str,
    days_ago: int = 0,
) -> dict:
    """Create a case dict for direct database insertion."""
    case_id = str(uuid.uuid4())
    mrn = generate_mrn()
    patient_id = str(uuid.uuid4())
    culture_date = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 12))

    return {
        "id": case_id,
        "patient_id": patient_id,
        "patient_mrn": mrn,
        "patient_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        "culture_id": str(uuid.uuid4()),
        "culture_date": culture_date,
        "organism": ORGANISMS.get(infection_type, infection_type),
        "mdro_type": infection_type,
        "specimen_type": random.choice(["Blood", "Urine", "Wound", "Respiratory"]),
        "unit": unit,
        "location": "Main Hospital",
        "transmission_status": "healthcare",
        "days_since_admission": random.randint(3, 10),
        "resistant_antibiotics": [],
        "classification_reason": f"Demo {infection_type.upper()} case for outbreak testing",
        "is_new": True,
        "prior_history": False,
        "created_at": datetime.now(),
    }


def insert_case_to_mdro_db(case: dict, db_path: str) -> bool:
    """Insert a case directly into the MDRO database."""
    import sqlite3
    import json

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO mdro_cases (
                id, patient_id, patient_mrn, patient_name, culture_id, culture_date,
                organism, mdro_type, specimen_type, unit, location, transmission_status,
                days_since_admission, resistant_antibiotics, classification_reason,
                is_new, prior_history, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case["id"],
            case["patient_id"],
            case["patient_mrn"],
            case["patient_name"],
            case["culture_id"],
            case["culture_date"].isoformat(),
            case["organism"],
            case["mdro_type"],
            case["specimen_type"],
            case["unit"],
            case["location"],
            case["transmission_status"],
            case["days_since_admission"],
            json.dumps(case["resistant_antibiotics"]),
            case["classification_reason"],
            case["is_new"],
            case["prior_history"],
            case["created_at"].isoformat(),
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  Error inserting case: {e}")
        return False


def insert_outbreak_case_direct(case: dict, db_path: str, cluster_id: str = None) -> bool:
    """Insert a case directly into the outbreak detection database."""
    import sqlite3

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Insert into cluster_cases if we have a cluster
        if cluster_id:
            cursor.execute("""
                INSERT INTO cluster_cases (
                    id, cluster_id, source, source_id, patient_id, patient_mrn,
                    event_date, organism, infection_type, unit, location, added_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                cluster_id,
                "mdro",
                case["id"],
                case["patient_id"],
                case["patient_mrn"],
                case["culture_date"].isoformat(),
                case["organism"],
                case["mdro_type"],
                case["unit"],
                case["location"],
                datetime.now().isoformat(),
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  Error inserting outbreak case: {e}")
        return False


def create_cluster_direct(
    infection_type: str,
    unit: str,
    case_count: int,
    db_path: str,
) -> str:
    """Create a cluster directly in the outbreak database."""
    import sqlite3

    cluster_id = str(uuid.uuid4())
    now = datetime.now()
    first_case = now - timedelta(days=random.randint(5, 10))
    last_case = now - timedelta(days=random.randint(0, 2))

    # Determine severity
    if case_count >= 10:
        severity = "critical"
    elif case_count >= 6:
        severity = "high"
    elif case_count >= 4:
        severity = "medium"
    else:
        severity = "low"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO outbreak_clusters (
                id, infection_type, organism, unit, status, severity,
                case_count, first_case_date, last_case_date, detected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cluster_id,
            infection_type,
            ORGANISMS.get(infection_type, infection_type),
            unit,
            "active",
            severity,
            case_count,
            first_case.isoformat(),
            last_case.isoformat(),
            now.isoformat(),
        ))

        # Create alert
        cursor.execute("""
            INSERT INTO outbreak_alerts (
                id, cluster_id, alert_type, severity, title, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            cluster_id,
            "cluster_formed",
            severity,
            f"Potential Outbreak: {infection_type.upper()} in {unit}",
            f"{case_count} cases detected. Investigation recommended.",
            now.isoformat(),
        ))

        conn.commit()
        conn.close()
        return cluster_id
    except Exception as e:
        print(f"  Error creating cluster: {e}")
        return None


def run_scenario_direct(
    scenario_key: str,
    num_cases: int,
    mdro_db_path: str,
    outbreak_db_path: str,
) -> dict:
    """Run scenario by inserting directly into databases."""
    scenario = SCENARIOS[scenario_key]
    infection_type = scenario["infection_type"]

    # Handle multi-unit scenarios
    units = scenario.get("units", [scenario.get("unit")])

    result = {
        "scenario": scenario_key,
        "name": scenario["name"],
        "cases_created": 0,
        "clusters_created": 0,
        "success": False,
    }

    print(f"\n{'─'*60}")
    print(f"Scenario: {scenario['name']}")
    print(f"{'─'*60}")
    print(f"  Type:       {infection_type.upper()}")
    print(f"  Unit(s):    {', '.join(units)}")
    print(f"  Cases:      {num_cases}")

    # Distribute cases across units
    cases_per_unit = num_cases // len(units)
    remainder = num_cases % len(units)

    for i, unit in enumerate(units):
        unit_cases = cases_per_unit + (1 if i < remainder else 0)
        if unit_cases < 2:
            continue

        print(f"\n  Creating {unit_cases} cases in {unit}...")

        # Create cluster
        cluster_id = create_cluster_direct(infection_type, unit, unit_cases, outbreak_db_path)
        if not cluster_id:
            continue
        result["clusters_created"] += 1

        # Create cases
        for j in range(unit_cases):
            days_ago = random.randint(0, 10)
            case = create_mdro_case_direct(infection_type, unit, days_ago)

            # Insert into MDRO database
            if insert_case_to_mdro_db(case, mdro_db_path):
                # Insert into outbreak database
                if insert_outbreak_case_direct(case, outbreak_db_path, cluster_id):
                    result["cases_created"] += 1
                    print(f"    ✓ Case {j+1}: {case['patient_mrn']} ({case['patient_name']})")

    result["success"] = result["cases_created"] > 0
    return result


def run_scenario_fhir(
    scenario_key: str,
    num_cases: int,
    fhir_url: str,
) -> dict:
    """Run scenario by creating FHIR resources."""
    # Import the MDRO demo script's functions
    from demo_mdro import run_scenario as run_mdro_scenario

    scenario = SCENARIOS[scenario_key]
    infection_type = scenario["infection_type"]
    units = scenario.get("units", [scenario.get("unit")])

    result = {
        "scenario": scenario_key,
        "name": scenario["name"],
        "cases_created": 0,
        "success": False,
    }

    print(f"\n{'─'*60}")
    print(f"Scenario: {scenario['name']} (via FHIR)")
    print(f"{'─'*60}")
    print(f"  Type:       {infection_type.upper()}")
    print(f"  Unit(s):    {', '.join(units)}")
    print(f"  Cases:      {num_cases}")

    # Map infection types to MDRO scenarios
    mdro_scenario_map = {
        "mrsa": "mrsa",
        "vre": "vre",
        "cre": "cre",
        "esbl": "esbl",
        "crpa": "crpa",
        "crab": "crab",
    }

    mdro_scenario = mdro_scenario_map.get(infection_type)
    if not mdro_scenario:
        print(f"  Warning: No MDRO scenario for {infection_type}, skipping FHIR creation")
        return result

    cases_per_unit = num_cases // len(units)
    remainder = num_cases % len(units)

    for i, unit in enumerate(units):
        unit_cases = cases_per_unit + (1 if i < remainder else 0)

        for j in range(unit_cases):
            case_result = run_mdro_scenario(mdro_scenario, fhir_url, community_onset=False, unit=unit)
            if case_result["success"]:
                result["cases_created"] += 1

    result["success"] = result["cases_created"] > 0
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate outbreak demo scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--scenario", "-s", choices=list(SCENARIOS.keys()), help="Outbreak scenario")
    parser.add_argument("--cases", "-n", type=int, help="Number of cases to create")
    parser.add_argument("--direct", "-d", action="store_true", help="Insert directly to database (no FHIR)")
    parser.add_argument("--fhir-url", default="http://localhost:8081/fhir", help="FHIR server URL")
    parser.add_argument("--mdro-db", default=str(Path(__file__).parent.parent / "mdro-surveillance" / "data" / "mdro.db"), help="MDRO database path")
    parser.add_argument("--outbreak-db", default=str(Path(__file__).parent.parent / "outbreak-detection" / "data" / "outbreak.db"), help="Outbreak database path")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--list", "-l", action="store_true", help="List scenarios")

    args = parser.parse_args()

    if args.list:
        print("\nAvailable outbreak scenarios:\n")
        print(f"{'Scenario':<15} {'Cases':<6} {'Description'}")
        print("─" * 60)
        for key, scenario in SCENARIOS.items():
            print(f"{key:<15} {scenario['default_cases']:<6} {scenario['description']}")
        return 0

    # Ensure database directories exist
    Path(args.mdro_db).parent.mkdir(parents=True, exist_ok=True)
    Path(args.outbreak_db).parent.mkdir(parents=True, exist_ok=True)

    results = []

    if args.scenario:
        scenario = SCENARIOS[args.scenario]
        num_cases = args.cases or scenario["default_cases"]

        if args.direct:
            results.append(run_scenario_direct(args.scenario, num_cases, args.mdro_db, args.outbreak_db))
        else:
            try:
                requests.get(f"{args.fhir_url}/metadata", timeout=5).raise_for_status()
                results.append(run_scenario_fhir(args.scenario, num_cases, args.fhir_url))
            except Exception as e:
                print(f"FHIR server not available ({e}), using direct mode")
                results.append(run_scenario_direct(args.scenario, num_cases, args.mdro_db, args.outbreak_db))

    elif args.all:
        print("\n" + "=" * 60)
        print("RUNNING ALL OUTBREAK SCENARIOS")
        print("=" * 60)

        for key, scenario in SCENARIOS.items():
            num_cases = scenario["default_cases"]
            if args.direct:
                results.append(run_scenario_direct(key, num_cases, args.mdro_db, args.outbreak_db))
            else:
                try:
                    requests.get(f"{args.fhir_url}/metadata", timeout=5)
                    results.append(run_scenario_fhir(key, num_cases, args.fhir_url))
                except Exception:
                    results.append(run_scenario_direct(key, num_cases, args.mdro_db, args.outbreak_db))
    else:
        parser.error("Specify --scenario or --all")

    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        total_cases = sum(r.get("cases_created", 0) for r in results)
        total_clusters = sum(r.get("clusters_created", 0) for r in results)

        print(f"\nCreated {total_cases} cases in {total_clusters} clusters")

        if args.direct:
            print("\nTo detect outbreaks, run:")
            print("  cd outbreak-detection && python -m outbreak_src.runner --once")
        else:
            print("\nTo process pipeline:")
            print("  1. Run MDRO monitor: cd mdro-surveillance && python -m mdro_src.runner --once")
            print("  2. Run outbreak detection: cd outbreak-detection && python -m outbreak_src.runner --once")

    return 0


if __name__ == "__main__":
    sys.exit(main())
