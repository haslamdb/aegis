"""
FHIR client for surgical prophylaxis data access.

Queries FHIR API for Procedure, MedicationRequest, MedicationAdministration,
Patient, and AllergyIntolerance resources.

Adapted from surgical-prophylaxis/src/fhir_client.py (702 lines).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import requests

from .logic.config import Config
from .logic.guidelines import CPT_CATEGORY_HINTS
from .models import ProcedureCategory, SurgicalCase, ProphylaxisMedication

logger = logging.getLogger(__name__)


class FHIRClient:
    """Client for querying FHIR resources related to surgical prophylaxis."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        cfg = Config()
        self.base_url = base_url or cfg.FHIR_BASE_URL
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        url = urljoin(self.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _get_all_pages(self, endpoint: str, params: Optional[dict] = None) -> list[dict]:
        results = []
        response = self._get(endpoint, params)
        while True:
            entries = response.get("entry", [])
            results.extend([e.get("resource", {}) for e in entries])
            next_link = next(
                (link for link in response.get("link", []) if link.get("relation") == "next"),
                None,
            )
            if not next_link:
                break
            response = self.session.get(next_link["url"], timeout=self.timeout).json()
        return results

    def get_surgical_procedures(self, date_from=None, date_to=None, patient_id=None) -> list[dict]:
        """Get surgical procedures from FHIR."""
        params = {"_count": 100, "status": "completed,in-progress"}
        if date_from:
            params["date"] = f"ge{date_from.isoformat()}"
        if date_to:
            if "date" in params:
                params["date"] = [params["date"], f"le{date_to.isoformat()}"]
            else:
                params["date"] = f"le{date_to.isoformat()}"
        if patient_id:
            params["subject"] = f"Patient/{patient_id}"
        return self._get_all_pages("Procedure", params)

    def get_medication_orders(self, patient_id: str, since_hours: int = 48) -> list[dict]:
        cutoff = datetime.now() - timedelta(hours=since_hours)
        params = {
            "subject": f"Patient/{patient_id}",
            "authoredon": f"ge{cutoff.isoformat()}",
            "status": "active,completed",
            "_count": 50,
        }
        orders = self._get_all_pages("MedicationRequest", params)
        prophylaxis_meds = [
            "cefazolin", "vancomycin", "clindamycin", "metronidazole",
            "gentamicin", "cefoxitin", "ampicillin", "piperacillin",
        ]
        return [
            o for o in orders
            if any(med in self._get_medication_name(o).lower() for med in prophylaxis_meds)
        ]

    def get_medication_administrations(self, patient_id: str, since_hours: int = 48) -> list[dict]:
        cutoff = datetime.now() - timedelta(hours=since_hours)
        params = {
            "subject": f"Patient/{patient_id}",
            "effective-time": f"ge{cutoff.isoformat()}",
            "status": "completed",
            "_count": 100,
        }
        admins = self._get_all_pages("MedicationAdministration", params)
        prophylaxis_meds = [
            "cefazolin", "vancomycin", "clindamycin", "metronidazole",
            "gentamicin", "cefoxitin", "ampicillin", "piperacillin",
        ]
        return [
            a for a in admins
            if any(med in self._get_admin_medication_name(a).lower() for med in prophylaxis_meds)
        ]

    def get_patient(self, patient_id: str) -> Optional[dict]:
        try:
            return self._get(f"Patient/{patient_id}")
        except requests.HTTPError:
            return None

    def get_patient_weight(self, patient_id: str) -> Optional[float]:
        params = {
            "subject": f"Patient/{patient_id}",
            "code": "29463-7",
            "_sort": "-date",
            "_count": 1,
        }
        observations = self._get_all_pages("Observation", params)
        if not observations:
            return None
        obs = observations[0]
        value_quantity = obs.get("valueQuantity", {})
        value = value_quantity.get("value")
        unit = value_quantity.get("unit", "kg")
        if value is None:
            return None
        if unit.lower() in ["lb", "lbs", "[lb_av]"]:
            return value * 0.453592
        return float(value)

    def get_patient_allergies(self, patient_id: str) -> list[str]:
        params = {"patient": f"Patient/{patient_id}", "clinical-status": "active"}
        allergies = self._get_all_pages("AllergyIntolerance", params)
        result = []
        for allergy in allergies:
            code = allergy.get("code", {})
            for coding in code.get("coding", []):
                if coding.get("display"):
                    result.append(coding["display"])
            if code.get("text"):
                result.append(code["text"])
        return result

    def has_beta_lactam_allergy(self, allergies: list[str]) -> bool:
        beta_lactam_keywords = [
            "penicillin", "amoxicillin", "ampicillin", "cephalosporin",
            "cefazolin", "ceftriaxone", "cefepime", "piperacillin",
            "beta-lactam", "carbapenem", "meropenem",
        ]
        for allergy in allergies:
            allergy_lower = allergy.lower()
            if any(kw in allergy_lower for kw in beta_lactam_keywords):
                return True
        return False

    def build_surgical_case_data(self, procedure: dict) -> dict:
        """
        Build data dict from a FHIR Procedure resource suitable for SurgicalCase creation.

        Returns a dict of field values (not a model instance).
        """
        patient_ref = procedure.get("subject", {}).get("reference", "")
        patient_id = patient_ref.replace("Patient/", "")

        cpt_codes = []
        for coding in procedure.get("code", {}).get("coding", []):
            system = coding.get("system", "")
            if "cpt" in system.lower() or coding.get("code", "").isdigit():
                cpt_codes.append(coding.get("code"))

        category = ProcedureCategory.OTHER
        for cpt in cpt_codes:
            prefix = cpt[:3] if len(cpt) >= 3 else cpt
            if prefix in CPT_CATEGORY_HINTS:
                category = CPT_CATEGORY_HINTS[prefix]
                break

        performed = procedure.get("performedPeriod", {}) or procedure.get("performedDateTime")
        incision_time = None
        surgery_end = None

        if isinstance(performed, dict):
            if performed.get("start"):
                incision_time = datetime.fromisoformat(performed["start"].replace("Z", "+00:00"))
            if performed.get("end"):
                surgery_end = datetime.fromisoformat(performed["end"].replace("Z", "+00:00"))
        elif isinstance(performed, str):
            incision_time = datetime.fromisoformat(performed.replace("Z", "+00:00"))

        weight = None
        age = None
        allergies = []
        has_bl_allergy = False

        if patient_id:
            patient = self.get_patient(patient_id)
            if patient:
                birth_date = patient.get("birthDate")
                if birth_date:
                    birth = datetime.fromisoformat(birth_date)
                    age = (datetime.now() - birth).days / 365.25

            weight = self.get_patient_weight(patient_id)
            allergies = self.get_patient_allergies(patient_id)
            has_bl_allergy = self.has_beta_lactam_allergy(allergies)

        encounter_ref = procedure.get("encounter", {}).get("reference", "")
        encounter_id = encounter_ref.replace("Encounter/", "")

        return {
            'case_id': procedure.get("id", ""),
            'patient_mrn': self._get_mrn(patient_id) if patient_id else "",
            'encounter_id': encounter_id,
            'cpt_codes': cpt_codes,
            'procedure_description': procedure.get("code", {}).get("text", ""),
            'procedure_category': category,
            'actual_incision_time': incision_time,
            'surgery_end_time': surgery_end,
            'patient_weight_kg': weight,
            'patient_age_years': age,
            'allergies': allergies,
            'has_beta_lactam_allergy': has_bl_allergy,
        }

    def get_appointments(self, date_from=None, date_to=None) -> list[dict]:
        params = {"_count": 100, "status": "booked,arrived,checked-in"}
        if date_from:
            params["date"] = [f"ge{date_from.isoformat()}"]
        if date_to:
            if "date" in params:
                params["date"].append(f"le{date_to.isoformat()}")
            else:
                params["date"] = f"le{date_to.isoformat()}"
        return self._get_all_pages("Appointment", params)

    def check_prophylaxis_order_exists(self, patient_id: str, since_hours: int = 24) -> bool:
        orders = self.get_medication_orders(patient_id, since_hours=since_hours)
        return len(orders) > 0

    def check_prophylaxis_administered(self, patient_id: str, since_hours: int = 4) -> bool:
        admins = self.get_medication_administrations(patient_id, since_hours=since_hours)
        return len(admins) > 0

    def _get_medication_name(self, order: dict) -> str:
        med_cc = order.get("medicationCodeableConcept", {})
        for coding in med_cc.get("coding", []):
            if coding.get("display"):
                return coding["display"]
        if med_cc.get("text"):
            return med_cc["text"]
        med_ref = order.get("medicationReference", {})
        if med_ref.get("display"):
            return med_ref["display"]
        return ""

    def _get_admin_medication_name(self, admin: dict) -> str:
        med_cc = admin.get("medicationCodeableConcept", {})
        for coding in med_cc.get("coding", []):
            if coding.get("display"):
                return coding["display"]
        if med_cc.get("text"):
            return med_cc["text"]
        med_ref = admin.get("medicationReference", {})
        if med_ref.get("display"):
            return med_ref["display"]
        return ""

    def _get_mrn(self, patient_id: str) -> str:
        patient = self.get_patient(patient_id)
        if not patient:
            return patient_id
        for identifier in patient.get("identifier", []):
            if "mrn" in identifier.get("type", {}).get("coding", [{}])[0].get("code", "").lower():
                return identifier.get("value", patient_id)
            if "mr" in identifier.get("type", {}).get("text", "").lower():
                return identifier.get("value", patient_id)
        if patient.get("identifier"):
            return patient["identifier"][0].get("value", patient_id)
        return patient_id
