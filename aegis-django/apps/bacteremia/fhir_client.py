"""FHIR client for Bacteremia Monitoring.

Provides methods to query blood cultures and current medications.
"""

from datetime import datetime, timedelta
from typing import Optional

from apps.drug_bug.fhir_client import FHIRClient, HAPIFHIRClient, EpicFHIRClient, get_fhir_client

from .data_models import Antibiotic, CultureResult, Patient


class BacteremiaFHIRClient:
    """High-level client for bacteremia monitoring queries."""

    def __init__(self, fhir_client: FHIRClient | None = None):
        self.fhir = fhir_client or get_fhir_client()

    def parse_patient(self, patient_resource: dict) -> Patient:
        """Parse FHIR Patient resource into model."""
        # Extract MRN
        mrn = "Unknown"
        for identifier in patient_resource.get("identifier", []):
            if "mrn" in identifier.get("system", "").lower():
                mrn = identifier.get("value", mrn)
                break
            mrn = identifier.get("value", mrn)

        # Extract name
        name = "Unknown"
        for name_entry in patient_resource.get("name", []):
            given = " ".join(name_entry.get("given", []))
            family = name_entry.get("family", "")
            name = f"{given} {family}".strip() or name
            break

        # Extract location
        location = None
        for ext in patient_resource.get("extension", []):
            if "location" in ext.get("url", "").lower():
                location = ext.get("valueString")

        return Patient(
            fhir_id=patient_resource.get("id", ""),
            mrn=mrn,
            name=name,
            birth_date=patient_resource.get("birthDate"),
            gender=patient_resource.get("gender"),
            location=location,
        )

    def parse_culture(self, report: dict) -> Optional[CultureResult]:
        """Parse FHIR DiagnosticReport into CultureResult."""
        # Extract patient reference
        patient_ref = report.get("subject", {}).get("reference", "")
        patient_id = patient_ref.replace("Patient/", "") if patient_ref else ""
        if not patient_id:
            return None

        # Extract organism and gram stain from conclusion
        organism = None
        gram_stain = None
        conclusion = report.get("conclusion", "")
        if conclusion:
            parts = conclusion.split(".")
            for part in parts:
                part_stripped = part.strip()
                if not part_stripped:
                    continue
                part_lower = part_stripped.lower()
                if "gram" in part_lower and ("cocci" in part_lower or "rod" in part_lower or "bacill" in part_lower):
                    gram_stain = part_stripped
                elif organism is None:
                    organism = part_stripped

        # Also check conclusionCode
        for code_entry in report.get("conclusionCode", []):
            text = code_entry.get("text", "")
            if text and "pending" not in text.lower():
                organism = text
            for coding in code_entry.get("coding", []):
                display = coding.get("display")
                if display and "pending" not in display.lower():
                    organism = display

        # Parse dates
        collected_date = None
        resulted_date = None
        if report.get("effectiveDateTime"):
            try:
                collected_date = datetime.fromisoformat(
                    report["effectiveDateTime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        if report.get("issued"):
            try:
                resulted_date = datetime.fromisoformat(
                    report["issued"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return CultureResult(
            fhir_id=report.get("id", ""),
            patient_id=patient_id,
            organism=organism,
            gram_stain=gram_stain,
            status=report.get("status", "final"),
            collected_date=collected_date,
            resulted_date=resulted_date,
        )

    def parse_medication_request(self, med_request: dict) -> Antibiotic:
        """Parse FHIR MedicationRequest into Antibiotic model."""
        medication_name = "Unknown"
        rxnorm_code = None

        med_concept = med_request.get("medicationCodeableConcept", {})
        medication_name = med_concept.get("text", medication_name)

        for coding in med_concept.get("coding", []):
            if "rxnorm" in coding.get("system", "").lower():
                rxnorm_code = coding.get("code")
                if not medication_name or medication_name == "Unknown":
                    medication_name = coding.get("display", medication_name)

        # Extract route
        route = None
        for dosage in med_request.get("dosageInstruction", []):
            route_info = dosage.get("route", {})
            for coding in route_info.get("coding", []):
                route = coding.get("display")
                break

        return Antibiotic(
            fhir_id=med_request.get("id", ""),
            medication_name=medication_name,
            rxnorm_code=rxnorm_code,
            route=route,
            status=med_request.get("status", "active"),
        )

    def get_recent_blood_cultures(self, hours_back: int = 24) -> list[CultureResult]:
        """Get recent blood culture reports."""
        date_from = datetime.now() - timedelta(hours=hours_back)
        params = {
            "code": "http://loinc.org|600-7",  # Blood culture LOINC
            "status": "preliminary,final",
            "date": f"ge{date_from.strftime('%Y-%m-%dT%H:%M:%S')}",
            "_count": "500",
        }
        response = self.fhir.get("DiagnosticReport", params)
        entries = self.fhir._extract_entries(response)

        cultures = []
        for entry in entries:
            culture = self.parse_culture(entry)
            if culture:
                cultures.append(culture)

        return cultures

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Get patient information."""
        patient_resource = self.fhir.get_patient(patient_id)
        if patient_resource:
            return self.parse_patient(patient_resource)
        return None

    def get_current_antibiotics(self, patient_id: str) -> list[Antibiotic]:
        """Get current antibiotic orders for a patient."""
        med_requests = self.fhir.get_active_medication_requests(patient_id)
        antibiotics = []
        for mr in med_requests:
            abx = self.parse_medication_request(mr)
            if abx.rxnorm_code:
                antibiotics.append(abx)
        return antibiotics
