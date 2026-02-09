"""Base FHIR client classes.

Provides the abstract BaseFHIRClient and the concrete HAPIFHIRClient
for local HAPI FHIR servers (no auth required).
"""

from abc import ABC, abstractmethod

import requests
from django.conf import settings


class BaseFHIRClient(ABC):
    """Abstract FHIR client interface.

    All FHIR clients must implement get(). The post() method has a
    default implementation that raises NotImplementedError so read-only
    clients don't need to provide it.
    """

    @abstractmethod
    def get(self, resource_path: str, params: dict | None = None) -> dict:
        """GET a FHIR resource or search."""

    def post(self, resource_path: str, resource: dict) -> dict:
        """POST a FHIR resource. Override in subclasses that need writes."""
        raise NotImplementedError("This FHIR client does not support POST")

    @staticmethod
    def extract_entries(bundle: dict) -> list[dict]:
        """Extract resource entries from a FHIR Bundle.

        Args:
            bundle: A FHIR Bundle resource dict.

        Returns:
            List of resource dicts from the bundle entries.
            Empty list if not a valid Bundle.
        """
        if bundle.get("resourceType") != "Bundle":
            return []
        return [
            entry.get("resource", {})
            for entry in bundle.get("entry", [])
            if "resource" in entry
        ]

    # Keep _extract_entries as an alias for backwards compat
    _extract_entries = extract_entries


class HAPIFHIRClient(BaseFHIRClient):
    """Client for local HAPI FHIR server (no auth required).

    Args:
        base_url: FHIR server base URL. Defaults to settings.FHIR_BASE_URL
                  or http://localhost:8081/fhir.
        timeout: Request timeout in seconds. Defaults to 30.
    """

    def __init__(self, base_url: str | None = None, timeout: int = 30):
        self.base_url = (base_url or getattr(
            settings, 'FHIR_BASE_URL', 'http://localhost:8081/fhir'
        )).rstrip("/")
        self.timeout = timeout
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
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def post(self, resource_path: str, resource: dict) -> dict:
        """POST request to FHIR server."""
        response = self.session.post(
            f"{self.base_url}/{resource_path}",
            json=resource,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
