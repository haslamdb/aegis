"""Standalone FHIR resource parsing utilities.

These functions extract common data elements from FHIR resource dicts.
They have no dependency on any FHIR client class and can be used anywhere.
"""

from datetime import datetime
from typing import Optional


def extract_bundle_entries(bundle: dict) -> list[dict]:
    """Extract resource entries from a FHIR Bundle.

    Args:
        bundle: A FHIR Bundle resource dict.

    Returns:
        List of resource dicts. Empty list if not a valid Bundle.
    """
    if bundle.get("resourceType") != "Bundle":
        return []
    return [
        entry.get("resource", {})
        for entry in bundle.get("entry", [])
        if "resource" in entry
    ]


def parse_fhir_datetime(dt_string: str | None) -> Optional[datetime]:
    """Parse a FHIR datetime string to a Python datetime.

    Handles:
    - Full ISO datetime with Z suffix (2024-01-15T10:30:00Z)
    - Full ISO datetime with offset (2024-01-15T10:30:00+00:00)
    - Date-only strings (2024-01-15)
    - None / empty values

    Args:
        dt_string: FHIR datetime string, or None.

    Returns:
        Timezone-aware datetime, or naive date-as-datetime, or None.
    """
    if not dt_string:
        return None
    try:
        return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(dt_string, "%Y-%m-%d")
        except ValueError:
            return None


def extract_patient_name(patient_resource: dict) -> str:
    """Extract formatted patient name from a FHIR Patient resource.

    Uses the first name entry's given + family names.

    Args:
        patient_resource: A FHIR Patient resource dict.

    Returns:
        Formatted name string, or "Unknown" if not available.
    """
    for name_entry in patient_resource.get("name", []):
        given = " ".join(name_entry.get("given", []))
        family = name_entry.get("family", "")
        full_name = f"{given} {family}".strip()
        if full_name:
            return full_name
    return "Unknown"


def extract_patient_mrn(patient_resource: dict) -> str:
    """Extract MRN from a FHIR Patient resource's identifiers.

    Looks for an identifier with 'mrn' in the system URL first,
    then falls back to the type code 'MR', then to the first
    identifier value.

    Args:
        patient_resource: A FHIR Patient resource dict.

    Returns:
        MRN string, or "Unknown" if not found.
    """
    identifiers = patient_resource.get("identifier", [])

    # First pass: look for system containing 'mrn'
    for identifier in identifiers:
        if "mrn" in identifier.get("system", "").lower():
            return identifier.get("value", "Unknown")

    # Second pass: look for type code 'MR'
    for identifier in identifiers:
        codings = identifier.get("type", {}).get("coding", [])
        if codings and codings[0].get("code") == "MR":
            return identifier.get("value", "Unknown")

    # Fallback: first identifier
    if identifiers:
        return identifiers[0].get("value", "Unknown")

    return "Unknown"


def extract_encounter_location(encounter_resource: dict) -> dict:
    """Extract location info from a FHIR Encounter resource.

    Args:
        encounter_resource: A FHIR Encounter resource dict.

    Returns:
        Dict with 'facility' and 'unit' keys (values may be None).
    """
    facility = None
    unit = None

    for loc in encounter_resource.get("location", []):
        loc_ref = loc.get("location", {})
        display = loc_ref.get("display")
        if display:
            if unit is None:
                unit = display
            if facility is None:
                facility = display

    service_provider = encounter_resource.get("serviceProvider", {})
    if service_provider.get("display"):
        facility = service_provider["display"]

    return {"facility": facility, "unit": unit}


def parse_susceptibility_observation(observation: dict) -> Optional[dict]:
    """Parse a susceptibility Observation into a dict.

    Extracts antibiotic name, S/I/R interpretation, and MIC value.

    Args:
        observation: A FHIR Observation resource dict.

    Returns:
        Dict with 'antibiotic', 'result' (S/I/R), and 'mic' keys,
        or None if essential fields are missing.
    """
    # Get antibiotic name from code
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

    # Clean up bracket suffixes (e.g. "Vancomycin [Susceptibility]")
    if "[" in antibiotic:
        antibiotic = antibiotic.split("[")[0].strip()

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
        if result:
            break

    # Also check valueCodeableConcept
    if not result:
        value_cc = observation.get("valueCodeableConcept", {})
        for coding in value_cc.get("coding", []):
            code = coding.get("code", "")
            if code in ("S", "I", "R"):
                result = code
                break

    if not result:
        return None

    # Get MIC value from valueQuantity
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
