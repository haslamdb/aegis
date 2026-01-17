"""FHIR client abstraction layer.

Provides a unified interface for both local HAPI FHIR server
and Epic FHIR API. Switch between them via environment variables.
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from .config import config


class FHIRClient(ABC):
    """Abstract FHIR client - implement for different backends."""

    @abstractmethod
    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET a FHIR resource or search."""
        pass

    @abstractmethod
    def post(self, resource_path: str, resource: dict) -> dict:
        """POST a FHIR resource."""
        pass

    def search_patients(self, **params) -> list[dict]:
        """Search for patients."""
        response = self.get("Patient", params)
        return self._extract_entries(response)

    def get_patient(self, patient_id: str) -> dict | None:
        """Get a single patient by ID."""
        try:
            return self.get(f"Patient/{patient_id}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_active_medication_requests(self, patient_id: str) -> list[dict]:
        """Get active medication requests for a patient."""
        response = self.get("MedicationRequest", {
            "patient": patient_id,
            "status": "active",
        })
        return self._extract_entries(response)

    def get_diagnostic_reports(
        self,
        patient_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
    ) -> list[dict]:
        """Get diagnostic reports (e.g., microbiology results)."""
        params = {}
        if patient_id:
            params["patient"] = patient_id
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if date_from:
            params["date"] = f"ge{date_from.strftime('%Y-%m-%d')}"

        response = self.get("DiagnosticReport", params)
        return self._extract_entries(response)

    def get_recent_blood_cultures(
        self,
        hours_back: int = 24,
        status: str | None = None,
    ) -> list[dict]:
        """Get recent blood culture results."""
        date_from = datetime.now() - timedelta(hours=hours_back)
        params = {
            "code": "http://loinc.org|600-7",  # LOINC for blood culture
            "date": f"ge{date_from.strftime('%Y-%m-%d')}",
            "_count": "500",
        }
        if status:
            params["status"] = status

        response = self.get("DiagnosticReport", params)
        return self._extract_entries(response)

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
    """Client for local HAPI FHIR server (no auth required)."""

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

    def post(self, resource_path: str, resource: dict) -> dict:
        """POST request to FHIR server."""
        response = self.session.post(
            f"{self.base_url}/{resource_path}",
            json=resource,
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

        # Load private key
        self.private_key: str | None = None
        if self.private_key_path:
            with open(self.private_key_path) as f:
                self.private_key = f.read()

    def _get_token_url(self) -> str:
        """Derive token URL from FHIR base URL."""
        # Epic token URL is typically at the same base, just different path
        # e.g., https://epicfhir.org/api/FHIR/R4 -> https://epicfhir.org/oauth2/token
        base = self.base_url.rsplit("/FHIR", 1)[0]
        return f"{base}/oauth2/token"

    def _get_access_token(self) -> str:
        """OAuth 2.0 JWT bearer flow for backend apps."""
        import jwt

        # Return cached token if still valid
        if self.access_token and self.token_expires_at:
            if self.token_expires_at > datetime.now():
                return self.access_token

        if not self.private_key:
            raise ValueError("Private key not loaded - cannot authenticate to Epic")

        token_url = self._get_token_url()
        now = int(time.time())

        # Build JWT assertion
        claims = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": token_url,
            "jti": f"{now}-{self.client_id}",
            "exp": now + 300,  # 5 minute expiry
        }

        assertion = jwt.encode(claims, self.private_key, algorithm="RS384")

        # Request access token
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
        # Refresh 60 seconds before actual expiry
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

    def post(self, resource_path: str, resource: dict) -> dict:
        """POST request with OAuth authentication."""
        token = self._get_access_token()

        response = self.session.post(
            f"{self.base_url}/{resource_path}",
            json=resource,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


def get_fhir_client() -> FHIRClient:
    """Factory function - returns appropriate client based on config."""
    if config.is_epic_configured():
        print("Using Epic FHIR client")
        return EpicFHIRClient()
    else:
        print("Using local HAPI FHIR client")
        return HAPIFHIRClient()
