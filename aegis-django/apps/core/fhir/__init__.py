"""Shared FHIR client infrastructure for AEGIS.

Provides base client classes, an OAuth client for Epic, parsing utilities,
and a factory function for creating the appropriate client based on settings.

Usage::

    from apps.core.fhir import get_fhir_client, parse_fhir_datetime

    client = get_fhir_client()
    bundle = client.get("Patient", {"_count": "10"})
    entries = client.extract_entries(bundle)
"""

from .base import BaseFHIRClient, HAPIFHIRClient
from .factory import get_fhir_client
from .oauth import EpicFHIRClient
from .parsers import (
    extract_bundle_entries,
    extract_encounter_location,
    extract_patient_mrn,
    extract_patient_name,
    parse_fhir_datetime,
    parse_susceptibility_observation,
)

__all__ = [
    "BaseFHIRClient",
    "HAPIFHIRClient",
    "EpicFHIRClient",
    "get_fhir_client",
    "extract_bundle_entries",
    "extract_encounter_location",
    "extract_patient_mrn",
    "extract_patient_name",
    "parse_fhir_datetime",
    "parse_susceptibility_observation",
]
