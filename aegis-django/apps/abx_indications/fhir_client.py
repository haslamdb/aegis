"""FHIR client for ABX Indication Monitoring.

Provides medication order and clinical note queries for indication
extraction. Extends the antimicrobial_usage FHIR client pattern with
DocumentReference (notes), Condition, and Encounter queries.
"""

import base64
import logging
from datetime import datetime, timedelta

import requests
from django.conf import settings

from .logic.config import Config

logger = logging.getLogger(__name__)


# Monitored antibiotics: RxNorm code → display name
# These are the antibiotics we track for indication documentation.
# Covers the most commonly prescribed systemic antibiotics in pediatrics.
MONITORED_MEDICATIONS = {
    # Penicillins
    "723":    "amoxicillin",
    "392151": "amoxicillin-clavulanate",
    "733":    "ampicillin",
    "733-1":  "ampicillin-sulbactam",
    # Cephalosporins
    "20481":  "cefazolin",
    "309090": "ceftriaxone",
    "309092": "ceftazidime",
    "309097": "cefepime",
    "2193":   "cephalexin",
    "2231":   "cefdinir",
    # Carbapenems
    "29046":  "meropenem",
    "29561":  "ertapenem",
    # Fluoroquinolones
    "2551":   "ciprofloxacin",
    "82122":  "levofloxacin",
    # Glycopeptides / Lipopeptides
    "11124":  "vancomycin",
    "190376": "daptomycin",
    # Macrolides
    "18631":  "azithromycin",
    # Aminoglycosides
    "5691":   "gentamicin",
    "10109":  "tobramycin",
    # Anti-anaerobes
    "6922":   "metronidazole",
    # Anti-pseudomonal penicillins
    "7984":   "piperacillin-tazobactam",
}


class FHIRClient:
    """FHIR client for ABX indication monitoring.

    Queries MedicationRequest, DocumentReference, Condition, and
    Encounter resources for indication extraction workflows.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or Config.FHIR_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET a FHIR resource or search."""
        response = self.session.get(
            f"{self.base_url}/{resource_path}",
            params=params,
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

    # ------------------------------------------------------------------
    # MedicationRequest queries
    # ------------------------------------------------------------------

    def get_recent_medication_requests(
        self,
        lookback_hours: int | None = None,
    ) -> list[dict]:
        """Get recent antibiotic MedicationRequests for monitored medications.

        Args:
            lookback_hours: How far back to search (defaults to Config.LOOKBACK_HOURS).

        Returns:
            List of parsed medication order dicts with keys:
            fhir_id, patient_id, medication_name, rxnorm_code,
            dose, route, start_date, status.
        """
        hours = lookback_hours or Config.LOOKBACK_HOURS
        since = datetime.utcnow() - timedelta(hours=hours)

        monitored = Config.MONITORED_MEDICATIONS or MONITORED_MEDICATIONS
        rxnorm_codes = list(monitored.keys())

        params = {
            "status": "active",
            "authoredon": f"ge{since.strftime('%Y-%m-%dT%H:%M:%S')}",
            "_count": "500",
        }
        if rxnorm_codes:
            code_param = ",".join(
                f"http://www.nlm.nih.gov/research/umls/rxnorm|{code}"
                for code in rxnorm_codes
            )
            params["code"] = code_param

        try:
            bundle = self.get("MedicationRequest", params)
            resources = self._extract_entries(bundle)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch MedicationRequests: {e}")
            return []

        orders = []
        for resource in resources:
            order = self._resource_to_medication_order(resource, monitored)
            if order:
                orders.append(order)

        logger.info(f"Found {len(orders)} monitored medication orders (last {hours}h)")
        return orders

    def _resource_to_medication_order(
        self, resource: dict, monitored: dict,
    ) -> dict | None:
        """Convert a FHIR MedicationRequest to a medication order dict."""
        rxnorm_code = None
        medication_name = None

        if med_concept := resource.get("medicationCodeableConcept"):
            for coding in med_concept.get("coding", []):
                if "rxnorm" in coding.get("system", "").lower():
                    rxnorm_code = coding.get("code")
                    medication_name = coding.get("display")
                    break
            if not medication_name:
                medication_name = med_concept.get("text")

        # Only include monitored medications
        if rxnorm_code and rxnorm_code not in monitored:
            return None

        if not medication_name and rxnorm_code:
            medication_name = monitored.get(rxnorm_code, "Unknown")

        if not medication_name:
            return None

        # Extract patient reference
        patient_ref = resource.get("subject", {}).get("reference", "")
        patient_id = patient_ref.replace("Patient/", "") if patient_ref else ""

        # Extract dosage info
        dose = None
        route = None
        if dosage_instructions := resource.get("dosageInstruction", []):
            dosage = dosage_instructions[0]
            if dose_quantity := dosage.get("doseAndRate", [{}])[0].get("doseQuantity"):
                dose = f"{dose_quantity.get('value', '')} {dose_quantity.get('unit', '')}".strip()
            if route_coding := dosage.get("route", {}).get("coding", [{}]):
                route = route_coding[0].get("display")

        # Extract start date
        start_date = None
        if authored_on := resource.get("authoredOn"):
            try:
                if "T" in authored_on:
                    start_date = datetime.fromisoformat(authored_on.replace("Z", "+00:00"))
                else:
                    start_date = datetime.strptime(authored_on, "%Y-%m-%d")
            except ValueError:
                pass

        return {
            "fhir_id": resource.get("id", ""),
            "patient_id": patient_id,
            "medication_name": medication_name,
            "rxnorm_code": rxnorm_code,
            "dose": dose,
            "route": route,
            "start_date": start_date,
            "status": resource.get("status", "active"),
        }

    # ------------------------------------------------------------------
    # Clinical notes (DocumentReference)
    # ------------------------------------------------------------------

    def get_recent_notes(
        self,
        patient_id: str,
        lookback_hours: int | None = None,
        note_types: list[str] | None = None,
    ) -> list[dict]:
        """Get recent clinical notes for a patient.

        Args:
            patient_id: FHIR Patient ID.
            lookback_hours: Hours to look back (defaults to Config.LOOKBACK_HOURS).
            note_types: Filter by note type (progress_note, h_and_p, etc.).

        Returns:
            List of note dicts with keys: id, patient_id, note_type,
            author, date, content.
        """
        hours = lookback_hours or Config.LOOKBACK_HOURS
        since = datetime.utcnow() - timedelta(hours=hours)

        params = {
            "patient": patient_id,
            "date": f"ge{since.strftime('%Y-%m-%dT%H:%M:%S')}",
            "status": "current",
            "_count": "50",
            "_sort": "-date",
        }

        if note_types:
            type_codes = self._map_note_types_to_codes(note_types)
            if type_codes:
                params["type"] = ",".join(type_codes)

        try:
            bundle = self.get("DocumentReference", params)
            resources = self._extract_entries(bundle)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch notes for patient {patient_id}: {e}")
            return []

        notes = []
        for resource in resources:
            note = self._resource_to_clinical_note(resource)
            if note:
                notes.append(note)

        logger.debug(f"Found {len(notes)} notes for patient {patient_id}")
        return notes

    def _resource_to_clinical_note(self, resource: dict) -> dict | None:
        """Convert a FHIR DocumentReference to a clinical note dict."""
        try:
            note_id = resource.get("id")
            patient_ref = resource.get("subject", {}).get("reference", "")
            patient_id = patient_ref.split("/")[-1] if patient_ref else ""

            # Note type from type coding
            note_type = "other"
            for coding in resource.get("type", {}).get("coding", []):
                if coding.get("display"):
                    note_type = self._normalize_note_type(coding.get("display"))
                    break

            # Author
            author = None
            for auth in resource.get("author", []):
                if auth.get("display"):
                    author = auth.get("display")
                    break

            # Date
            date_str = resource.get("date") or resource.get(
                "context", {}
            ).get("period", {}).get("start")
            note_date = (
                datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if date_str
                else datetime.utcnow()
            )

            # Content - inline base64 or URL
            content = ""
            for content_item in resource.get("content", []):
                attachment = content_item.get("attachment", {})
                if attachment.get("data"):
                    content = base64.b64decode(attachment["data"]).decode("utf-8")
                elif attachment.get("url"):
                    content = self._fetch_binary_content(attachment["url"])

            if not content:
                return None

            return {
                "id": note_id,
                "patient_id": patient_id,
                "note_type": note_type,
                "author": author,
                "date": note_date,
                "content": content,
            }

        except Exception as e:
            logger.error(f"Failed to parse DocumentReference: {e}")
            return None

    def _fetch_binary_content(self, url: str) -> str:
        """Fetch binary content from a FHIR Binary resource URL."""
        try:
            if url.startswith("/"):
                url = f"{self.base_url}{url}"
            elif not url.startswith("http"):
                url = f"{self.base_url}/{url}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch binary content: {e}")
            return ""

    def _map_note_types_to_codes(self, note_types: list[str]) -> list[str]:
        """Map note type names to LOINC codes for FHIR query."""
        type_map = {
            "progress_note": "11506-3",
            "id_consult": "11488-4",
            "discharge_summary": "18842-5",
            "h_and_p": "34117-2",
            "operative": "11504-8",
        }
        return [type_map[t] for t in note_types if t in type_map]

    def _normalize_note_type(self, display: str) -> str:
        """Normalize FHIR note type display to internal type."""
        display_lower = display.lower()
        if "progress" in display_lower:
            return "progress_note"
        if "consult" in display_lower and "id" in display_lower:
            return "id_consult"
        if "infectious" in display_lower:
            return "id_consult"
        if "discharge" in display_lower:
            return "discharge_summary"
        if "history" in display_lower and "physical" in display_lower:
            return "h_and_p"
        if "operative" in display_lower:
            return "operative"
        return "other"

    # ------------------------------------------------------------------
    # Condition (diagnosis codes)
    # ------------------------------------------------------------------

    def get_patient_conditions(self, patient_id: str) -> list[dict]:
        """Get active conditions (diagnoses) for a patient.

        Returns list of dicts with keys: code, system, display.
        """
        params = {
            "patient": patient_id,
            "clinical-status": "active",
            "_count": "100",
        }

        try:
            bundle = self.get("Condition", params)
            resources = self._extract_entries(bundle)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch conditions for patient {patient_id}: {e}")
            return []

        conditions = []
        for resource in resources:
            code_obj = resource.get("code", {})
            for coding in code_obj.get("coding", []):
                conditions.append({
                    "code": coding.get("code", ""),
                    "system": coding.get("system", ""),
                    "display": coding.get("display", ""),
                })

        return conditions

    # ------------------------------------------------------------------
    # Patient + Encounter info
    # ------------------------------------------------------------------

    def get_patient_encounter_info(self, patient_id: str) -> dict:
        """Get patient demographics and current encounter info.

        Returns dict with keys: patient_name, mrn, birth_date, gender,
        age_months, location, service.
        """
        info = {
            "patient_name": "",
            "mrn": "",
            "birth_date": None,
            "gender": "",
            "age_months": None,
            "location": "",
            "service": "",
        }

        # Patient demographics
        try:
            patient = self.get(f"Patient/{patient_id}")
            info.update(self._parse_patient(patient))
        except requests.RequestException as e:
            logger.error(f"Failed to fetch patient {patient_id}: {e}")

        # Current encounter (most recent active)
        try:
            bundle = self.get("Encounter", {
                "patient": patient_id,
                "status": "in-progress",
                "_count": "1",
                "_sort": "-date",
            })
            encounters = self._extract_entries(bundle)
            if encounters:
                info.update(self._parse_encounter(encounters[0]))
        except requests.RequestException as e:
            logger.debug(f"No active encounter for patient {patient_id}: {e}")

        return info

    def _parse_patient(self, resource: dict) -> dict:
        """Extract patient demographics from FHIR Patient resource."""
        # Name
        name = "Unknown"
        if names := resource.get("name", []):
            name_obj = names[0]
            given = " ".join(name_obj.get("given", []))
            family = name_obj.get("family", "")
            name = f"{given} {family}".strip() or "Unknown"

        # MRN
        mrn = ""
        for ident in resource.get("identifier", []):
            if ident.get("type", {}).get("coding", [{}])[0].get("code") == "MR":
                mrn = ident.get("value", "")
                break
        if not mrn and resource.get("identifier"):
            mrn = resource["identifier"][0].get("value", "")

        # Age in months
        age_months = None
        if birth_date_str := resource.get("birthDate"):
            try:
                birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
                age_days = (datetime.utcnow() - birth_date).days
                age_months = age_days // 30
            except ValueError:
                pass

        return {
            "patient_name": name,
            "mrn": mrn,
            "birth_date": resource.get("birthDate"),
            "gender": resource.get("gender", ""),
            "age_months": age_months,
        }

    def _parse_encounter(self, resource: dict) -> dict:
        """Extract location and service from FHIR Encounter resource."""
        location = ""
        service = ""

        # Location from encounter.location
        for loc in resource.get("location", []):
            loc_ref = loc.get("location", {})
            if display := loc_ref.get("display"):
                location = display
                break

        # Service from encounter.serviceType or type
        if service_type := resource.get("serviceType"):
            for coding in service_type.get("coding", []):
                if display := coding.get("display"):
                    service = display
                    break
        if not service:
            for enc_type in resource.get("type", []):
                for coding in enc_type.get("coding", []):
                    if display := coding.get("display"):
                        service = display
                        break
                if service:
                    break

        return {
            "location": location,
            "service": service,
        }


def get_fhir_client() -> FHIRClient:
    """Factory function - returns configured FHIR client."""
    return FHIRClient()
