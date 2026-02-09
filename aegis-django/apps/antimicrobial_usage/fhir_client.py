"""FHIR client for Antimicrobial Usage Alerts.

Provides medication-focused queries for monitoring broad-spectrum
antibiotic usage duration. Adapted from Flask fhir_client.py for Django.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import requests
from django.conf import settings

from .data_models import Patient, MedicationOrder

logger = logging.getLogger(__name__)


def _get_config():
    """Get antimicrobial usage config from Django settings."""
    return getattr(settings, 'ANTIMICROBIAL_USAGE', {})


class FHIRClient(ABC):
    """Abstract FHIR client for broad-spectrum monitoring."""

    @abstractmethod
    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET a FHIR resource or search."""
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

    def get_patient(self, patient_id: str) -> Patient | None:
        """Get a patient by ID and convert to model."""
        try:
            resource = self.get(f"Patient/{patient_id}")
            return self._resource_to_patient(resource)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_monitored_medications(self) -> list[MedicationOrder]:
        """Get active medication requests for monitored broad-spectrum antibiotics."""
        conf = _get_config()
        monitored = conf.get('MONITORED_MEDICATIONS', {})
        rxnorm_codes = list(monitored.keys())

        params = {"status": "active", "_count": "500"}
        if rxnorm_codes:
            code_param = ",".join(
                f"http://www.nlm.nih.gov/research/umls/rxnorm|{code}"
                for code in rxnorm_codes
            )
            params["code"] = code_param

        response = self.get("MedicationRequest", params)
        resources = self._extract_entries(response)

        orders = []
        for resource in resources:
            order = self._resource_to_medication_order(resource)
            if order:
                orders.append(order)

        return orders

    def _resource_to_patient(self, resource: dict) -> Patient:
        """Convert FHIR Patient resource to Patient model."""
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
        if not mrn:
            if resource.get("identifier"):
                mrn = resource["identifier"][0].get("value", "")

        # Extract location/department from extensions
        location = None
        department = None
        for ext in resource.get("extension", []):
            if "location" in ext.get("url", "").lower():
                location = ext.get("valueString")
            elif "department" in ext.get("url", "").lower():
                department = ext.get("valueString")

        return Patient(
            fhir_id=resource.get("id", ""),
            mrn=mrn,
            name=name,
            birth_date=resource.get("birthDate"),
            gender=resource.get("gender"),
            location=location,
            department=department,
        )

    def _resource_to_medication_order(self, resource: dict) -> MedicationOrder | None:
        """Convert FHIR MedicationRequest resource to MedicationOrder model."""
        conf = _get_config()
        monitored = conf.get('MONITORED_MEDICATIONS', {})

        rxnorm_code = None
        medication_name = None

        # Try medicationCodeableConcept first
        if med_concept := resource.get("medicationCodeableConcept"):
            for coding in med_concept.get("coding", []):
                if "rxnorm" in coding.get("system", "").lower():
                    rxnorm_code = coding.get("code")
                    medication_name = coding.get("display")
                    break
            if not medication_name:
                medication_name = med_concept.get("text")

        # Check if this is a monitored medication
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

        return MedicationOrder(
            fhir_id=resource.get("id", ""),
            patient_id=patient_id,
            medication_name=medication_name,
            rxnorm_code=rxnorm_code,
            dose=dose,
            route=route,
            start_date=start_date,
            status=resource.get("status", "active"),
        )


class HAPIFHIRClient(FHIRClient):
    """Client for local HAPI FHIR server (no auth required)."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or getattr(settings, 'FHIR_BASE_URL', 'http://localhost:8081/fhir')
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
    """Client for Epic FHIR API (OAuth 2.0 backend auth)."""

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        private_key_path: str | None = None,
    ):
        self.base_url = base_url or getattr(settings, 'EPIC_FHIR_BASE_URL', '')
        self.client_id = client_id or getattr(settings, 'EPIC_CLIENT_ID', '')
        self.private_key_path = private_key_path or getattr(settings, 'EPIC_PRIVATE_KEY_PATH', '')

        self.access_token: str | None = None
        self.token_expires_at: datetime | None = None

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

        # Load private key
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
            raise ValueError("Private key not loaded - cannot authenticate to Epic")

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
    """Factory function - returns appropriate client based on settings."""
    if getattr(settings, 'EPIC_FHIR_BASE_URL', None):
        logger.info("Using Epic FHIR client")
        return EpicFHIRClient()
    else:
        logger.info("Using local HAPI FHIR client")
        return HAPIFHIRClient()
