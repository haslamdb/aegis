"""FHIR client for MDRO Surveillance.

Queries microbiology cultures with susceptibility results to identify MDROs.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests

from .config import config


@dataclass
class CultureResult:
    """A culture result with susceptibilities."""
    fhir_id: str
    patient_id: str
    patient_mrn: str
    patient_name: str
    organism: str
    collection_date: datetime
    resulted_date: Optional[datetime]
    specimen_type: Optional[str]
    location: Optional[str]
    unit: Optional[str]
    encounter_id: Optional[str]
    susceptibilities: list[dict]  # [{antibiotic, result (S/I/R), mic}]


class FHIRClient(ABC):
    """Abstract FHIR client interface."""

    @abstractmethod
    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET a FHIR resource."""
        pass

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


class HAPIFHIRClient(FHIRClient):
    """Client for local HAPI FHIR server."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or config.FHIR_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET request to FHIR server."""
        response = self.session.get(
            f"{self.base_url}/{resource_path}",
            params=params,
        )
        response.raise_for_status()
        return response.json()


class EpicFHIRClient(FHIRClient):
    """Client for Epic FHIR API with OAuth 2.0."""

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        private_key_path: str | None = None,
    ):
        self.base_url = base_url or config.EPIC_FHIR_BASE_URL
        self.client_id = client_id or config.EPIC_CLIENT_ID
        self.private_key_path = private_key_path or config.EPIC_PRIVATE_KEY_PATH

        self.access_token: str | None = None
        self.token_expires_at: datetime | None = None

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

        self.private_key: str | None = None
        if self.private_key_path:
            with open(self.private_key_path) as f:
                self.private_key = f.read()

    def _get_token_url(self) -> str:
        """Derive token URL from FHIR base URL."""
        base = self.base_url.rsplit("/FHIR", 1)[0]
        return f"{base}/oauth2/token"

    def _get_access_token(self) -> str:
        """OAuth 2.0 JWT bearer flow for backend apps."""
        import jwt

        if self.access_token and self.token_expires_at:
            if self.token_expires_at > datetime.now():
                return self.access_token

        if not self.private_key:
            raise ValueError("Private key not loaded")

        token_url = self._get_token_url()
        now = int(time.time())

        claims = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": token_url,
            "jti": f"{now}-{self.client_id}",
            "exp": now + 300,
        }

        assertion = jwt.encode(claims, self.private_key, algorithm="RS384")

        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": assertion,
            },
        )
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

        return self.access_token

    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET request with OAuth authentication."""
        token = self._get_access_token()

        response = self.session.get(
            f"{self.base_url}/{resource_path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


def get_fhir_client() -> FHIRClient:
    """Factory function for FHIR client."""
    if config.is_epic_configured():
        return EpicFHIRClient()
    else:
        return HAPIFHIRClient()


class MDROFHIRClient:
    """High-level client for MDRO surveillance queries."""

    def __init__(self, fhir_client: FHIRClient | None = None):
        self.fhir = fhir_client or get_fhir_client()
        self._patient_cache: dict[str, dict] = {}
        self._encounter_cache: dict[str, dict] = {}

    def get_recent_cultures(self, hours_back: int = 24) -> list[CultureResult]:
        """Get recent finalized microbiology cultures with susceptibilities.

        Args:
            hours_back: Hours to look back for cultures

        Returns:
            List of CultureResult with susceptibility data
        """
        cultures = []
        date_from = datetime.now() - timedelta(hours=hours_back)

        # Query microbiology DiagnosticReports
        params = {
            "category": "MB",  # Microbiology
            "status": "final",
            "date": f"ge{date_from.strftime('%Y-%m-%dT%H:%M:%S')}",
            "_count": "500",
        }
        response = self.fhir.get("DiagnosticReport", params)
        reports = self.fhir._extract_entries(response)

        for report in reports:
            culture = self._parse_culture_report(report)
            if culture and culture.organism and culture.susceptibilities:
                cultures.append(culture)

        return cultures

    def _parse_culture_report(self, report: dict) -> Optional[CultureResult]:
        """Parse a DiagnosticReport into CultureResult with susceptibilities."""
        # Extract organism from conclusion or conclusionCode
        organism = None
        conclusion = report.get("conclusion", "")
        if conclusion:
            parts = conclusion.split(".")
            for part in parts:
                if "gram" not in part.lower():
                    organism = part.strip()
                    break
            if not organism:
                organism = conclusion

        for code_entry in report.get("conclusionCode", []):
            text = code_entry.get("text", "")
            if text and "pending" not in text.lower() and "no growth" not in text.lower():
                organism = text
            for coding in code_entry.get("coding", []):
                display = coding.get("display")
                if display and "pending" not in display.lower() and "no growth" not in display.lower():
                    organism = display

        if not organism or "no growth" in organism.lower():
            return None

        # Extract patient reference
        patient_ref = report.get("subject", {}).get("reference", "")
        patient_id = patient_ref.replace("Patient/", "") if patient_ref else ""
        if not patient_id:
            return None

        # Get patient details
        patient_data = self._get_patient(patient_id)
        patient_mrn = patient_data.get("mrn", "Unknown")
        patient_name = patient_data.get("name", "Unknown")

        # Parse dates
        collection_date = None
        resulted_date = None
        if report.get("effectiveDateTime"):
            try:
                collection_date = datetime.fromisoformat(
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

        if not collection_date:
            return None

        # Get specimen type
        specimen_type = self._extract_specimen_type(report)

        # Get encounter info for location/unit
        encounter_id = None
        location = None
        unit = None
        encounter_ref = report.get("encounter", {}).get("reference", "")
        if encounter_ref:
            encounter_id = encounter_ref.replace("Encounter/", "")
            encounter_data = self._get_encounter(encounter_id)
            location = encounter_data.get("facility")
            unit = encounter_data.get("unit")

        # Get susceptibility observations
        susceptibilities = self._get_susceptibilities(report)

        return CultureResult(
            fhir_id=report.get("id", ""),
            patient_id=patient_id,
            patient_mrn=patient_mrn,
            patient_name=patient_name,
            organism=organism,
            collection_date=collection_date,
            resulted_date=resulted_date,
            specimen_type=specimen_type,
            location=location,
            unit=unit,
            encounter_id=encounter_id,
            susceptibilities=susceptibilities,
        )

    def _extract_specimen_type(self, report: dict) -> Optional[str]:
        """Extract specimen type from report."""
        # Try specimen array first
        specimen_refs = report.get("specimen", [])
        for spec_ref in specimen_refs:
            if "display" in spec_ref:
                return spec_ref.get("display")

        # Extract from code text
        code_text = report.get("code", {}).get("text", "")
        if code_text:
            code_lower = code_text.lower()
            if "blood" in code_lower:
                return "Blood"
            elif "urine" in code_lower:
                return "Urine"
            elif "respiratory" in code_lower or "sputum" in code_lower:
                return "Respiratory"
            elif "wound" in code_lower:
                return "Wound"
            elif "csf" in code_lower or "cerebrospinal" in code_lower:
                return "CSF"

        return None

    def _get_susceptibilities(self, report: dict) -> list[dict]:
        """Get susceptibility results for a culture report."""
        susceptibilities = []

        # Check result array for observation references
        for result in report.get("result", []):
            obs_ref = result.get("reference", "")
            if obs_ref:
                obs_id = obs_ref.replace("Observation/", "")
                try:
                    obs = self.fhir.get(f"Observation/{obs_id}")
                    susc = self._parse_susceptibility(obs)
                    if susc:
                        susceptibilities.append(susc)
                except requests.HTTPError:
                    pass

        # Also query for linked observations
        report_id = report.get("id")
        if report_id:
            try:
                response = self.fhir.get("Observation", {
                    "derived-from": f"DiagnosticReport/{report_id}",
                    "_count": "100",
                })
                for obs in self.fhir._extract_entries(response):
                    susc = self._parse_susceptibility(obs)
                    if susc:
                        # Avoid duplicates
                        if not any(s["antibiotic"] == susc["antibiotic"] for s in susceptibilities):
                            susceptibilities.append(susc)
            except requests.HTTPError:
                pass

        return susceptibilities

    def _parse_susceptibility(self, observation: dict) -> Optional[dict]:
        """Parse a susceptibility Observation into dict."""
        # Get antibiotic name
        antibiotic = None
        code_concept = observation.get("code", {})
        antibiotic = code_concept.get("text")
        if not antibiotic:
            for coding in code_concept.get("coding", []):
                antibiotic = coding.get("display")
                if antibiotic:
                    break

        if not antibiotic:
            return None

        # Get interpretation (S/I/R)
        result = None
        for interp in observation.get("interpretation", []):
            for coding in interp.get("coding", []):
                code = coding.get("code", "")
                if code in ("S", "I", "R"):
                    result = code
                    break
                display = coding.get("display", "").upper()
                if display in ("SUSCEPTIBLE", "INTERMEDIATE", "RESISTANT"):
                    result = display[0]
                    break

        if not result:
            value_cc = observation.get("valueCodeableConcept", {})
            for coding in value_cc.get("coding", []):
                code = coding.get("code", "")
                if code in ("S", "I", "R"):
                    result = code
                    break

        if not result:
            return None

        # Get MIC value
        mic = None
        value_quantity = observation.get("valueQuantity", {})
        if value_quantity:
            mic_val = value_quantity.get("value")
            mic_units = value_quantity.get("unit", "")
            comparator = value_quantity.get("comparator", "")
            if mic_val is not None:
                mic = f"{comparator}{mic_val} {mic_units}".strip()

        return {
            "antibiotic": antibiotic.lower().strip(),
            "result": result,
            "mic": mic,
        }

    def _get_patient(self, patient_id: str) -> dict:
        """Get patient details (cached)."""
        if patient_id in self._patient_cache:
            return self._patient_cache[patient_id]

        try:
            patient = self.fhir.get(f"Patient/{patient_id}")

            # Extract MRN
            mrn = "Unknown"
            for identifier in patient.get("identifier", []):
                if "mrn" in identifier.get("system", "").lower():
                    mrn = identifier.get("value", mrn)
                    break
                mrn = identifier.get("value", mrn)

            # Extract name
            name = "Unknown"
            for name_entry in patient.get("name", []):
                given = " ".join(name_entry.get("given", []))
                family = name_entry.get("family", "")
                name = f"{given} {family}".strip() or name
                break

            result = {"mrn": mrn, "name": name}
            self._patient_cache[patient_id] = result
            return result
        except requests.HTTPError:
            return {"mrn": "Unknown", "name": "Unknown"}

    def _get_encounter(self, encounter_id: str) -> dict:
        """Get encounter details for location (cached)."""
        if encounter_id in self._encounter_cache:
            return self._encounter_cache[encounter_id]

        try:
            encounter = self.fhir.get(f"Encounter/{encounter_id}")

            facility = None
            unit = None

            # Extract location from encounter.location array
            for loc in encounter.get("location", []):
                loc_ref = loc.get("location", {})
                display = loc_ref.get("display")
                if display:
                    # Try to extract unit from location display
                    if unit is None:
                        unit = display
                    if facility is None:
                        facility = display

            # Try serviceProvider for facility
            service_provider = encounter.get("serviceProvider", {})
            if service_provider.get("display"):
                facility = service_provider["display"]

            result = {"facility": facility, "unit": unit}
            self._encounter_cache[encounter_id] = result
            return result
        except requests.HTTPError:
            return {"facility": None, "unit": None}

    def get_patient_admission_date(self, patient_id: str, encounter_id: str | None) -> Optional[datetime]:
        """Get admission date for the patient's current encounter."""
        if not encounter_id:
            return None

        try:
            encounter = self.fhir.get(f"Encounter/{encounter_id}")
            period = encounter.get("period", {})
            start = period.get("start")
            if start:
                return datetime.fromisoformat(start.replace("Z", "+00:00"))
        except (requests.HTTPError, ValueError):
            pass

        return None

    def get_patient_mdro_history(self, patient_id: str) -> list[dict]:
        """Check if patient has prior MDRO history (previous positive cultures).

        Returns list of prior positive culture info.
        """
        # Query historical cultures for this patient
        try:
            response = self.fhir.get("DiagnosticReport", {
                "patient": patient_id,
                "category": "MB",
                "status": "final",
                "_count": "100",
                "_sort": "-date",
            })
            reports = self.fhir._extract_entries(response)

            history = []
            for report in reports:
                conclusion = report.get("conclusion", "")
                if conclusion and "no growth" not in conclusion.lower():
                    date_str = report.get("effectiveDateTime")
                    try:
                        date = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else None
                    except (ValueError, TypeError):
                        date = None
                    history.append({
                        "fhir_id": report.get("id"),
                        "organism": conclusion,
                        "date": date,
                    })

            return history
        except requests.HTTPError:
            return []
