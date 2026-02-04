"""HAI Detection data sources.

This module provides data source abstractions for HAI surveillance.
FHIR is the preferred data source for real-time surveillance. Clarity
should only be used for bulk historical data extraction.

Factory functions:
    get_note_source: Clinical notes (FHIR DocumentReference preferred)
    get_device_source: Device tracking (FHIR DeviceUseStatement preferred)
    get_culture_source: Culture results (FHIR DiagnosticReport preferred)
    get_ventilator_source: Ventilator data for VAE (FHIR only)
    get_procedure_source: Surgical procedures for SSI (FHIR preferred)
    get_urinary_catheter_source: Urinary catheters for CAUTI (FHIR only)
    get_urine_culture_source: Urine cultures for CAUTI (FHIR only)
    get_cdi_test_source: C. difficile tests for CDI (FHIR only)
"""

from .factory import (
    get_note_source,
    get_device_source,
    get_culture_source,
    get_ventilator_source,
    get_procedure_source,
    get_urinary_catheter_source,
    get_urine_culture_source,
    get_cdi_test_source,
)

from .base import (
    BaseNoteSource,
    BaseDeviceSource,
    BaseCultureSource,
    BaseVentilatorSource,
)

__all__ = [
    # Factory functions
    "get_note_source",
    "get_device_source",
    "get_culture_source",
    "get_ventilator_source",
    "get_procedure_source",
    "get_urinary_catheter_source",
    "get_urine_culture_source",
    "get_cdi_test_source",
    # Base classes
    "BaseNoteSource",
    "BaseDeviceSource",
    "BaseCultureSource",
    "BaseVentilatorSource",
]
