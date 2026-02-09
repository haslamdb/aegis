"""FHIR client for Guideline Adherence monitoring.

Provides patient, condition, lab, vital sign, medication administration,
and clinical note queries. Supports both local HAPI FHIR and Epic FHIR
via a simplified single-class client.

Adapted from guideline-adherence/guideline_src/fhir_client.py (1147 lines).
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    """Get guideline adherence configuration from Django settings."""
    return getattr(settings, 'GUIDELINE_ADHERENCE', {})


class GuidelineAdherenceFHIRClient:
    """FHIR client for guideline adherence monitoring.

    Queries Patient, Condition, Observation (labs + vitals),
    MedicationAdministration, DocumentReference (notes), and
    Encounter resources for guideline bundle evaluation.
    """

    def __init__(self, base_url: str | None = None):
        config = _get_config()
        self.base_url = (base_url or config.get(
            'FHIR_BASE_URL', 'http://localhost:8081/fhir'
        )).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

    def _get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET a FHIR resource or search."""
        response = self.session.get(
            f"{self.base_url}/{resource_path}",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_entries(bundle: dict) -> list[dict]:
        """Extract resource entries from a FHIR Bundle."""
        if bundle.get("resourceType") != "Bundle":
            return []
        return [
            entry.get("resource", {})
            for entry in bundle.get("entry", [])
            if "resource" in entry
        ]

    @staticmethod
    def _parse_datetime(dt_str: str | None) -> datetime | None:
        """Parse FHIR datetime string to Python datetime."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                return None

    # ------------------------------------------------------------------
    # Patient queries
    # ------------------------------------------------------------------

    def get_patient(self, patient_id: str) -> dict | None:
        """Get patient by FHIR ID.

        Returns:
            Dict with fhir_id, mrn, name, birth_date, gender, age_days
            or None if not found.
        """
        try:
            resource = self._get(f"Patient/{patient_id}")
            return self._resource_to_patient(resource)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def _resource_to_patient(self, resource: dict) -> dict:
        """Convert FHIR Patient resource to dict."""
        # Extract name
        name = "Unknown"
        if names := resource.get("name", []):
            name_obj = names[0]
            given = " ".join(name_obj.get("given", []))
            family = name_obj.get("family", "")
            name = f"{given} {family}".strip() or "Unknown"

        # Extract MRN from identifiers
        mrn = ""
        for ident in resource.get("identifier", []):
            if ident.get("type", {}).get("coding", [{}])[0].get("code") == "MR":
                mrn = ident.get("value", "")
                break
        if not mrn and resource.get("identifier"):
            mrn = resource["identifier"][0].get("value", "")

        # Calculate age in days
        age_days = None
        if birth_date_str := resource.get("birthDate"):
            try:
                birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
                age_days = (datetime.now() - birth_date).days
            except ValueError:
                pass

        return {
            "fhir_id": resource.get("id", ""),
            "mrn": mrn,
            "name": name,
            "birth_date": resource.get("birthDate"),
            "gender": resource.get("gender"),
            "age_days": age_days,
        }

    # ------------------------------------------------------------------
    # Condition queries
    # ------------------------------------------------------------------

    def get_patient_conditions(self, patient_id: str) -> list[str]:
        """Get active ICD-10 codes for a patient.

        Returns:
            List of ICD-10 codes.
        """
        params = {
            "patient": patient_id,
            "clinical-status": "active",
            "_count": "100",
        }

        try:
            response = self._get("Condition", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(f"Failed to get conditions for patient {patient_id}: {e}")
            return []

        icd10_codes = []
        for resource in resources:
            for coding in resource.get("code", {}).get("coding", []):
                system = coding.get("system", "").lower()
                if "icd" in system or "i10" in system:
                    code = coding.get("code")
                    if code:
                        icd10_codes.append(code)

        return icd10_codes

    def get_patients_by_condition(
        self,
        icd10_prefixes: list[str],
        min_age_days: int | None = None,
        max_age_days: int | None = None,
    ) -> list[dict]:
        """Find patients with conditions matching ICD-10 prefixes.

        Args:
            icd10_prefixes: List of ICD-10 code prefixes to search for.
            min_age_days: Optional minimum patient age in days.
            max_age_days: Optional maximum patient age in days.

        Returns:
            List of dicts with patient_id, encounter_id, condition_code,
            onset_time, age_days.
        """
        icd10_codes = [
            f"http://hl7.org/fhir/sid/icd-10-cm|{prefix}"
            for prefix in icd10_prefixes
        ]

        params = {
            "code": ",".join(icd10_codes),
            "clinical-status": "active",
            "_count": "200",
        }

        try:
            response = self._get("Condition", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(f"Failed to get conditions for ICD-10 {icd10_prefixes}: {e}")
            return []

        patients = []
        for resource in resources:
            patient_ref = resource.get("subject", {}).get("reference", "")
            patient_id = patient_ref.replace("Patient/", "") if patient_ref else ""

            if not patient_id:
                continue

            encounter_ref = resource.get("encounter", {}).get("reference", "")
            encounter_id = encounter_ref.replace("Encounter/", "") if encounter_ref else ""

            # Get onset time
            onset = resource.get("onsetDateTime") or resource.get("recordedDate")
            onset_time = self._parse_datetime(onset)

            # Get ICD-10 code
            code = ""
            for coding in resource.get("code", {}).get("coding", []):
                if "icd" in coding.get("system", "").lower():
                    code = coding.get("code", "")
                    break

            # Get patient age
            age_days = None
            try:
                patient = self.get_patient(patient_id)
                if patient:
                    age_days = patient.get("age_days")
            except Exception as e:
                logger.debug(f"Could not get age for patient {patient_id}: {e}")

            # Filter by age if specified
            if max_age_days is not None and age_days is not None:
                if age_days > max_age_days:
                    continue
            if min_age_days is not None and age_days is not None:
                if age_days < min_age_days:
                    continue

            patients.append({
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "condition_code": code,
                "onset_time": onset_time,
                "age_days": age_days,
            })

        return patients

    # ------------------------------------------------------------------
    # Lab queries
    # ------------------------------------------------------------------

    def get_lab_results(
        self,
        patient_id: str,
        loinc_codes: list[str],
        since_time: datetime | None = None,
        since_hours: int = 24,
    ) -> list[dict]:
        """Get lab results for specific LOINC codes.

        Args:
            patient_id: FHIR patient ID.
            loinc_codes: List of LOINC codes to search for.
            since_time: Optional start time for search.
            since_hours: Hours back to search if since_time not provided.

        Returns:
            List of dicts with loinc_code, value, unit, effective_time.
        """
        if not since_time:
            since_time = datetime.now() - timedelta(hours=since_hours)

        params = {
            "patient": patient_id,
            "code": ",".join(f"http://loinc.org|{code}" for code in loinc_codes),
            "date": f"ge{since_time.strftime('%Y-%m-%dT%H:%M:%S')}",
            "_count": "100",
            "_sort": "-date",
        }

        try:
            response = self._get("Observation", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(f"Failed to get lab results for patient {patient_id}: {e}")
            return []

        results = []
        for resource in resources:
            # Get LOINC code
            loinc_code = ""
            for coding in resource.get("code", {}).get("coding", []):
                if "loinc" in coding.get("system", "").lower():
                    loinc_code = coding.get("code", "")
                    break

            # Get value
            value = None
            unit = None
            if value_qty := resource.get("valueQuantity"):
                value = value_qty.get("value")
                unit = value_qty.get("unit")
            elif value_str := resource.get("valueString"):
                value = value_str

            # Get effective time
            effective = resource.get("effectiveDateTime") or resource.get("issued")
            effective_time = self._parse_datetime(effective)

            results.append({
                "loinc_code": loinc_code,
                "value": value,
                "unit": unit,
                "effective_time": effective_time,
            })

        return results

    # ------------------------------------------------------------------
    # Vital signs queries
    # ------------------------------------------------------------------

    def get_vital_signs(
        self,
        patient_id: str,
        since_time: datetime | None = None,
        since_hours: int = 24,
    ) -> list[dict]:
        """Get vital signs (temperature, HR, RR, BP, SpO2).

        Args:
            patient_id: FHIR patient ID.
            since_time: Optional start time.
            since_hours: Hours back to search if since_time not provided.

        Returns:
            List of dicts with code, display, value, unit, effective_time.
        """
        if not since_time:
            since_time = datetime.now() - timedelta(hours=since_hours)

        params = {
            "patient": patient_id,
            "category": "vital-signs",
            "date": f"ge{since_time.strftime('%Y-%m-%dT%H:%M:%S')}",
            "_count": "200",
            "_sort": "-date",
        }

        try:
            response = self._get("Observation", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(f"Failed to get vital signs for patient {patient_id}: {e}")
            return []

        vitals = []
        for resource in resources:
            code = ""
            display = ""
            for coding in resource.get("code", {}).get("coding", []):
                code = coding.get("code", "")
                display = coding.get("display", "")
                break

            value = None
            unit = None
            if value_qty := resource.get("valueQuantity"):
                value = value_qty.get("value")
                unit = value_qty.get("unit")

            effective = resource.get("effectiveDateTime")
            effective_time = self._parse_datetime(effective)

            vitals.append({
                "code": code,
                "display": display,
                "value": value,
                "unit": unit,
                "effective_time": effective_time,
            })

        return vitals

    # ------------------------------------------------------------------
    # Medication administration queries
    # ------------------------------------------------------------------

    def get_medication_administrations(
        self,
        patient_id: str,
        since_time: datetime | None = None,
        since_hours: int = 24,
    ) -> list[dict]:
        """Get medication administrations (actual given times).

        Args:
            patient_id: FHIR patient ID.
            since_time: Optional start time.
            since_hours: Hours back to search.

        Returns:
            List of dicts with medication_name, dose, admin_time, route.
        """
        if not since_time:
            since_time = datetime.now() - timedelta(hours=since_hours)

        params = {
            "patient": patient_id,
            "effective-time": f"ge{since_time.strftime('%Y-%m-%dT%H:%M:%S')}",
            "_count": "200",
            "_sort": "-effective-time",
        }

        try:
            response = self._get("MedicationAdministration", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(
                f"Failed to get medication administrations for patient {patient_id}: {e}"
            )
            return []

        admins = []
        for resource in resources:
            # Get medication name
            med_name = ""
            if med_concept := resource.get("medicationCodeableConcept"):
                med_name = med_concept.get("text", "")
                if not med_name:
                    for coding in med_concept.get("coding", []):
                        med_name = coding.get("display", "")
                        if med_name:
                            break

            # Get dose
            dose = ""
            if dosage := resource.get("dosage"):
                if dose_qty := dosage.get("dose"):
                    dose = f"{dose_qty.get('value', '')} {dose_qty.get('unit', '')}".strip()

            # Get administration time
            admin_time = None
            if effective := resource.get("effectiveDateTime"):
                admin_time = self._parse_datetime(effective)
            elif effective_period := resource.get("effectivePeriod"):
                admin_time = self._parse_datetime(effective_period.get("start"))

            # Get route
            route = ""
            if dosage := resource.get("dosage"):
                if route_concept := dosage.get("route"):
                    route = route_concept.get("text", "")
                    if not route:
                        for coding in route_concept.get("coding", []):
                            route = coding.get("display", "")
                            if route:
                                break

            admins.append({
                "medication_name": med_name,
                "dose": dose,
                "admin_time": admin_time,
                "route": route,
            })

        return admins

    # ------------------------------------------------------------------
    # Clinical notes queries
    # ------------------------------------------------------------------

    def get_recent_notes(
        self,
        patient_id: str,
        since_time: datetime | None = None,
        since_hours: int = 48,
        note_types: list[str] | None = None,
    ) -> list[dict]:
        """Get recent clinical notes.

        Args:
            patient_id: FHIR patient ID.
            since_time: Optional specific start time.
            since_hours: Hours back to search (if since_time not provided).
            note_types: Optional LOINC codes for note types to filter by.

        Returns:
            List of dicts with text, type, date, author.
        """
        if not since_time:
            since_time = datetime.now() - timedelta(hours=since_hours)

        params = {
            "patient": patient_id,
            "date": f"ge{since_time.strftime('%Y-%m-%d')}",
            "_count": "50",
            "_sort": "-date",
        }

        if note_types:
            params["type"] = ",".join(note_types)

        try:
            response = self._get("DocumentReference", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(f"Failed to get notes for patient {patient_id}: {e}")
            return []

        notes = []
        for resource in resources:
            note = self._extract_note_content(resource)
            if note:
                notes.append(note)

        return notes

    def _extract_note_content(self, resource: dict) -> dict | None:
        """Extract content from DocumentReference resource."""
        # Get type
        note_type = "Unknown"
        type_coding = resource.get("type", {}).get("coding", [])
        if type_coding:
            note_type = type_coding[0].get(
                "display", type_coding[0].get("code", "Unknown")
            )

        # Get date
        note_date = resource.get("date") or resource.get(
            "context", {}
        ).get("period", {}).get("start")

        # Get author
        author = None
        authors = resource.get("author", [])
        if authors:
            author_ref = authors[0].get("display") or authors[0].get("reference", "")
            if author_ref:
                author = author_ref.replace("Practitioner/", "")

        # Get content from base64-encoded attachment
        text = None
        content_list = resource.get("content", [])
        for content in content_list:
            attachment = content.get("attachment", {})
            if data := attachment.get("data"):
                try:
                    text = base64.b64decode(data).decode("utf-8")
                    break
                except Exception:
                    pass

        if not text:
            return None

        return {
            "text": text,
            "type": note_type,
            "date": note_date,
            "author": author,
        }

    # ------------------------------------------------------------------
    # Encounter queries
    # ------------------------------------------------------------------

    def get_active_encounters(self) -> list[dict]:
        """Get current active inpatient encounters.

        Returns:
            List of dicts with encounter_id, patient_id, location,
            service, admit_time.
        """
        params = {
            "status": "in-progress",
            "class": "IMP",  # Inpatient
            "_count": "500",
        }

        try:
            response = self._get("Encounter", params)
            resources = self._extract_entries(response)
        except Exception as e:
            logger.warning(f"Failed to get active encounters: {e}")
            return []

        encounters = []
        for resource in resources:
            patient_ref = resource.get("subject", {}).get("reference", "")
            patient_id = patient_ref.replace("Patient/", "") if patient_ref else ""

            # Location
            location = ""
            for loc in resource.get("location", []):
                loc_ref = loc.get("location", {})
                if display := loc_ref.get("display"):
                    location = display
                    break

            # Service
            service = ""
            if service_type := resource.get("serviceType"):
                for coding in service_type.get("coding", []):
                    if display := coding.get("display"):
                        service = display
                        break

            # Admit time
            admit_time = None
            if period := resource.get("period"):
                admit_time = self._parse_datetime(period.get("start"))

            encounters.append({
                "encounter_id": resource.get("id", ""),
                "patient_id": patient_id,
                "location": location,
                "service": service,
                "admit_time": admit_time,
            })

        return encounters


def get_fhir_client() -> GuidelineAdherenceFHIRClient:
    """Factory function - returns configured FHIR client."""
    return GuidelineAdherenceFHIRClient()
