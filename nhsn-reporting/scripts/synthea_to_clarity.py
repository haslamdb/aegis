#!/usr/bin/env python3
"""Sync Synthea FHIR data to mock Clarity database.

This script reads Synthea-generated FHIR bundles and creates corresponding
records in the mock Clarity SQLite database, ensuring patient MRNs match
between the two systems.

This enables:
- FHIR-based real-time HAI detection (using patient MRN)
- Clarity-based aggregate denominator calculations (using same MRN)

Usage:
    python synthea_to_clarity.py --fhir-dir /path/to/fhir/bundles
    python synthea_to_clarity.py --fhir-dir ../data/synthea/fhir --db-path mock_clarity.db
"""

import argparse
import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Device SNOMED codes to flowsheet mapping
DEVICE_FLOWSHEET_MAP = {
    # Central lines
    "52124006": {"flo_meas_id": 1001, "name": "Central Line Present", "type": "central_line"},
    "303728004": {"flo_meas_id": 1006, "name": "PICC Line Present", "type": "central_line"},
    "706689003": {"flo_meas_id": 1007, "name": "Tunneled Catheter Present", "type": "central_line"},
    # Urinary catheters
    "25062003": {"flo_meas_id": 2101, "name": "Foley Catheter Present", "type": "urinary_catheter"},
    # Ventilation
    "129121000": {"flo_meas_id": 3104, "name": "Intubation Status", "type": "ventilator"},  # ETT
    "40617009": {"flo_meas_id": 3102, "name": "Mechanical Ventilation", "type": "ventilator"},
    "129122007": {"flo_meas_id": 3104, "name": "Intubation Status", "type": "ventilator"},  # Trach
}

# NHSN location mapping (assign based on encounter type/reason)
NHSN_LOCATIONS = [
    {"dept_id": 100, "code": "T5A", "type": "ICU"},
    {"dept_id": 101, "code": "T5B", "type": "ICU"},
    {"dept_id": 102, "code": "T4", "type": "NICU"},
    {"dept_id": 103, "code": "G5S", "type": "Oncology"},
    {"dept_id": 104, "code": "G6N", "type": "BMT"},
    {"dept_id": 105, "code": "A6N", "type": "Ward"},
]


def parse_fhir_datetime(dt_str: str | None) -> datetime | None:
    """Parse FHIR datetime string."""
    if not dt_str:
        return None
    # Handle various FHIR datetime formats
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]:
        try:
            # Remove timezone offset for simplicity
            clean = dt_str.replace("+00:00", "").replace("Z", "")
            if "+" in clean:
                clean = clean.rsplit("+", 1)[0]
            if "-" in clean and "T" in clean:
                parts = clean.rsplit("-", 1)
                if len(parts[1]) <= 2:  # Timezone offset
                    clean = parts[0]
            return datetime.strptime(clean[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    try:
        return datetime.strptime(dt_str[:10], "%Y-%m-%d")
    except ValueError:
        return None


def extract_patient_data(bundle: dict) -> dict | None:
    """Extract patient information from FHIR bundle."""
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            # Get MRN from identifiers
            mrn = None
            for ident in resource.get("identifier", []):
                ident_type = ident.get("type", {}).get("coding", [{}])[0].get("code", "")
                if ident_type == "MR" or "medical" in ident.get("type", {}).get("text", "").lower():
                    mrn = ident.get("value")
                    break

            if not mrn:
                # Fall back to first identifier or generate from ID
                mrn = resource.get("identifier", [{}])[0].get("value", resource.get("id", ""))

            name_parts = resource.get("name", [{}])[0]
            family = name_parts.get("family", "Unknown")
            given = name_parts.get("given", ["Unknown"])[0]

            return {
                "fhir_id": resource.get("id"),
                "mrn": mrn,
                "name": f"{family}, {given}",
                "birth_date": resource.get("birthDate"),
                "gender": resource.get("gender"),
            }
    return None


def extract_encounters(bundle: dict, patient_fhir_id: str) -> list[dict]:
    """Extract inpatient encounters from FHIR bundle."""
    encounters = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Encounter":
            enc_class = resource.get("class", {}).get("code", "")
            if enc_class in ["IMP", "inpatient", "ACUTE", "EMER"]:
                period = resource.get("period", {})

                # Determine location based on encounter type/reason
                reason_codes = []
                for reason in resource.get("reasonCode", []):
                    for coding in reason.get("coding", []):
                        reason_codes.append(coding.get("display", "").lower())

                # Assign location based on reason/type
                if any("respiratory" in r or "ventilat" in r for r in reason_codes):
                    location = random.choice([l for l in NHSN_LOCATIONS if l["type"] == "ICU"])
                elif any("cancer" in r or "leukemia" in r or "lymphoma" in r for r in reason_codes):
                    location = random.choice([l for l in NHSN_LOCATIONS if l["type"] in ["Oncology", "BMT"]])
                elif any("neonat" in r or "prematur" in r for r in reason_codes):
                    location = next((l for l in NHSN_LOCATIONS if l["type"] == "NICU"), NHSN_LOCATIONS[0])
                else:
                    # Random assignment weighted toward wards
                    location = random.choices(
                        NHSN_LOCATIONS,
                        weights=[2, 2, 1, 1, 1, 4],  # ICU, ICU, NICU, Onc, BMT, Ward
                    )[0]

                encounters.append({
                    "fhir_id": resource.get("id"),
                    "patient_fhir_id": patient_fhir_id,
                    "class": enc_class,
                    "start": parse_fhir_datetime(period.get("start")),
                    "end": parse_fhir_datetime(period.get("end")),
                    "department_id": location["dept_id"],
                    "location_code": location["code"],
                })
    return encounters


def extract_devices(bundle: dict) -> list[dict]:
    """Extract device information from FHIR bundle."""
    devices = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})

        if resource.get("resourceType") == "Device":
            device_type = resource.get("type", {})
            coding = device_type.get("coding", [{}])[0]
            snomed_code = coding.get("code", "")
            display = coding.get("display", "")

            if snomed_code in DEVICE_FLOWSHEET_MAP:
                devices.append({
                    "fhir_id": resource.get("id"),
                    "snomed_code": snomed_code,
                    "display": display,
                    "type": DEVICE_FLOWSHEET_MAP[snomed_code]["type"],
                    "flo_meas_id": DEVICE_FLOWSHEET_MAP[snomed_code]["flo_meas_id"],
                })

    return devices


def extract_device_periods(bundle: dict, devices: list[dict]) -> list[dict]:
    """Extract device use periods from Procedures and DeviceUseStatements."""
    device_periods = []

    # Build device ID to device info map
    device_map = {d["fhir_id"]: d for d in devices}

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")

        # Get device periods from Procedures (insertion/removal)
        if rtype == "Procedure":
            code = resource.get("code", {}).get("coding", [{}])[0]
            display = code.get("display", "").lower()

            # Central line insertion
            if "central" in display and "catheter" in display and "insert" in display:
                period = resource.get("performedPeriod", {})
                if not period:
                    performed = resource.get("performedDateTime")
                    if performed:
                        period = {"start": performed}

                device_periods.append({
                    "type": "central_line",
                    "flo_meas_id": 1001,
                    "start": parse_fhir_datetime(period.get("start")),
                    "end": None,  # Will be set from encounter end or device end
                    "value": "CVC",
                })

            # Urinary catheterization
            elif "catheter" in display and ("urinary" in display or "bladder" in display):
                period = resource.get("performedPeriod", {})
                if not period:
                    performed = resource.get("performedDateTime")
                    if performed:
                        period = {"start": performed}

                device_periods.append({
                    "type": "urinary_catheter",
                    "flo_meas_id": 2101,
                    "start": parse_fhir_datetime(period.get("start")),
                    "end": None,
                    "value": "Foley",
                })

            # Intubation
            elif "intub" in display or "endotracheal" in display:
                period = resource.get("performedPeriod", {})
                if not period:
                    performed = resource.get("performedDateTime")
                    if performed:
                        period = {"start": performed}

                device_periods.append({
                    "type": "ventilator",
                    "flo_meas_id": 3102,
                    "start": parse_fhir_datetime(period.get("start")),
                    "end": None,
                    "value": "Yes",
                })

    return device_periods


class SyntheaToClarity:
    """Convert Synthea FHIR bundles to mock Clarity records."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = None

        # ID counters
        self.pat_id_counter = 5000
        self.enc_id_counter = 50000
        self.fsd_id_counter = 500000

    def _next_pat_id(self) -> int:
        self.pat_id_counter += 1
        return self.pat_id_counter

    def _next_enc_id(self) -> int:
        self.enc_id_counter += 1
        return self.enc_id_counter

    def _next_fsd_id(self) -> int:
        self.fsd_id_counter += 1
        return self.fsd_id_counter

    def connect(self):
        """Connect to the database."""
        self.conn = sqlite3.connect(self.db_path)

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    def process_bundle(self, bundle_path: Path) -> dict:
        """Process a single FHIR bundle and insert into Clarity."""
        with open(bundle_path) as f:
            bundle = json.load(f)

        result = {
            "file": bundle_path.name,
            "patient": None,
            "encounters": 0,
            "devices": 0,
            "flowsheet_days": 0,
        }

        # Extract patient
        patient = extract_patient_data(bundle)
        if not patient:
            return result

        result["patient"] = patient["mrn"]

        # Insert patient
        pat_id = self._next_pat_id()
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO PATIENT (PAT_ID, PAT_MRN_ID, PAT_NAME, BIRTH_DATE)
               VALUES (?, ?, ?, ?)""",
            (pat_id, patient["mrn"], patient["name"], patient["birth_date"]),
        )

        # Extract and insert encounters
        encounters = extract_encounters(bundle, patient["fhir_id"])
        result["encounters"] = len(encounters)

        enc_map = {}  # fhir_id -> (enc_id, inpatient_data_id, start, end, dept_id)
        for enc in encounters:
            enc_id = self._next_enc_id()
            cursor.execute(
                """INSERT OR REPLACE INTO PAT_ENC
                   (PAT_ENC_CSN_ID, PAT_ID, INPATIENT_DATA_ID, HOSP_ADMIT_DTTM, HOSP_DISCH_DTTM, DEPARTMENT_ID)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (enc_id, pat_id, enc_id, enc["start"], enc["end"], enc["department_id"]),
            )
            enc_map[enc["fhir_id"]] = (enc_id, enc_id, enc["start"], enc["end"], enc["department_id"])

        # Extract devices and device periods
        devices = extract_devices(bundle)
        device_periods = extract_device_periods(bundle, devices)
        result["devices"] = len(device_periods)

        # Generate flowsheet entries for each device period
        for period in device_periods:
            if not period["start"]:
                continue

            # Find the encounter this device belongs to (closest match)
            best_enc = None
            for enc_fhir_id, enc_data in enc_map.items():
                enc_id, inpatient_id, enc_start, enc_end, dept_id = enc_data
                if enc_start and period["start"] >= enc_start:
                    if not enc_end or period["start"] <= enc_end:
                        best_enc = enc_data
                        break

            if not best_enc:
                # No matching encounter, skip
                continue

            enc_id, inpatient_id, enc_start, enc_end, dept_id = best_enc

            # Create flowsheet record
            fsd_id = self._next_fsd_id()
            cursor.execute(
                """INSERT OR REPLACE INTO IP_FLWSHT_REC (FSD_ID, INPATIENT_DATA_ID)
                   VALUES (?, ?)""",
                (fsd_id, inpatient_id),
            )

            # Generate daily flowsheet measurements
            device_end = period["end"] or enc_end or (period["start"] + timedelta(days=7))
            current_date = period["start"]

            while current_date <= device_end:
                cursor.execute(
                    """INSERT OR REPLACE INTO IP_FLWSHT_MEAS
                       (FLO_MEAS_ID, FSD_ID, RECORDED_TIME, MEAS_VALUE)
                       VALUES (?, ?, ?, ?)""",
                    (period["flo_meas_id"], fsd_id, current_date, period["value"]),
                )
                result["flowsheet_days"] += 1
                current_date += timedelta(days=1)

        self.conn.commit()
        return result

    def process_directory(self, fhir_dir: Path) -> list[dict]:
        """Process all FHIR bundles in a directory."""
        results = []

        for bundle_path in sorted(fhir_dir.glob("*.json")):
            try:
                result = self.process_bundle(bundle_path)
                results.append(result)
                if result["encounters"] > 0 or result["devices"] > 0:
                    print(f"  {result['file'][:30]}... MRN={result['patient']}, "
                          f"enc={result['encounters']}, dev={result['devices']}, "
                          f"flowsheet_days={result['flowsheet_days']}")
            except Exception as e:
                print(f"  ERROR processing {bundle_path.name}: {e}")
                results.append({"file": bundle_path.name, "error": str(e)})

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Sync Synthea FHIR data to mock Clarity database"
    )
    parser.add_argument(
        "--fhir-dir",
        type=Path,
        required=True,
        help="Directory containing Synthea FHIR bundles",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("mock_clarity.db"),
        help="Path to mock Clarity SQLite database",
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing patient/encounter data before importing",
    )

    args = parser.parse_args()

    if not args.fhir_dir.exists():
        print(f"ERROR: FHIR directory not found: {args.fhir_dir}")
        return 1

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}")
        print("Run the mock_clarity generator first to create the schema.")
        return 1

    print(f"Synthea to Clarity Sync")
    print(f"=" * 50)
    print(f"FHIR directory: {args.fhir_dir}")
    print(f"Database: {args.db_path}")

    converter = SyntheaToClarity(args.db_path)
    converter.connect()

    if args.clear_existing:
        print("\nClearing existing data...")
        cursor = converter.conn.cursor()
        cursor.execute("DELETE FROM IP_FLWSHT_MEAS WHERE FSD_ID >= 500000")
        cursor.execute("DELETE FROM IP_FLWSHT_REC WHERE FSD_ID >= 500000")
        cursor.execute("DELETE FROM PAT_ENC WHERE PAT_ENC_CSN_ID >= 50000")
        cursor.execute("DELETE FROM PATIENT WHERE PAT_ID >= 5000")
        converter.conn.commit()

    print(f"\nProcessing FHIR bundles...")
    results = converter.process_directory(args.fhir_dir)

    converter.close()

    # Summary
    total_patients = len([r for r in results if r.get("patient")])
    total_encounters = sum(r.get("encounters", 0) for r in results)
    total_devices = sum(r.get("devices", 0) for r in results)
    total_flowsheet_days = sum(r.get("flowsheet_days", 0) for r in results)

    print(f"\n" + "=" * 50)
    print(f"Summary:")
    print(f"  Patients imported: {total_patients}")
    print(f"  Encounters: {total_encounters}")
    print(f"  Device placements: {total_devices}")
    print(f"  Flowsheet days generated: {total_flowsheet_days}")
    print(f"\nDone! Clarity database updated at: {args.db_path}")


if __name__ == "__main__":
    exit(main() or 0)
