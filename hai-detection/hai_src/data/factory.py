"""Factory functions for data source creation."""

import logging

from ..config import Config
from .base import BaseNoteSource, BaseDeviceSource, BaseCultureSource, BaseVentilatorSource
from .fhir_source import (
    FHIRNoteSource,
    FHIRDeviceSource,
    FHIRCultureSource,
    FHIRVentilatorSource,
    FHIRUrinaryCatheterSource,
    FHIRUrineCultureSource,
    FHIRCDITestSource,
)
from .clarity_source import ClarityNoteSource, ClarityDeviceSource, ClarityCultureSource
from .procedure_source import (
    BaseProcedureSource,
    MockProcedureSource,
    FHIRProcedureSource,
    ClarityProcedureSource,
)

logger = logging.getLogger(__name__)


def get_note_source(source_type: str | None = None) -> BaseNoteSource:
    """Get the configured note source.

    FHIR is strongly preferred for real-time HAI surveillance as it provides
    immediate access to clinical notes. Clarity should only be used for bulk
    historical extraction where FHIR pagination would be impractical.

    Args:
        source_type: Override source type (fhir, clarity, both). Uses config if not specified.

    Returns:
        Configured note source implementation.
    """
    source = source_type or Config.NOTE_SOURCE

    if source == "clarity":
        if not Config.is_clarity_configured():
            logger.warning("Clarity not configured, falling back to FHIR")
            return FHIRNoteSource()
        logger.info("Using Clarity for note source (consider FHIR for real-time)")
        return ClarityNoteSource()

    if source == "both":
        # Return a composite source that tries both (deduplicates results)
        return CompositeNoteSource()

    # Default to FHIR (preferred for real-time surveillance)
    return FHIRNoteSource()


def get_device_source(source_type: str | None = None) -> BaseDeviceSource:
    """Get the configured device source.

    FHIR is strongly preferred for real-time HAI surveillance as it provides
    current device status. Clarity should only be used for historical analysis.

    Args:
        source_type: Override source type (fhir, clarity). Uses config if not specified.

    Returns:
        Configured device source implementation.
    """
    source = source_type or Config.DEVICE_SOURCE

    if source == "clarity":
        if not Config.is_clarity_configured():
            logger.warning("Clarity not configured, falling back to FHIR")
            return FHIRDeviceSource()
        logger.info("Using Clarity for device source (consider FHIR for real-time)")
        return ClarityDeviceSource()

    # Default to FHIR (preferred for real-time surveillance)
    return FHIRDeviceSource()


def get_culture_source(source_type: str | None = None) -> BaseCultureSource:
    """Get the configured culture source.

    FHIR is strongly preferred for real-time HAI surveillance as it provides
    current culture results as they finalize. Clarity should only be used for
    bulk historical extraction where FHIR pagination would be impractical.

    Args:
        source_type: Override source type (fhir, clarity). Uses config if not specified.

    Returns:
        Configured culture source implementation.
    """
    source = source_type or Config.CULTURE_SOURCE

    if source == "clarity":
        if not Config.is_clarity_configured():
            logger.warning("Clarity not configured, falling back to FHIR")
            return FHIRCultureSource()
        logger.info("Using Clarity for culture source (consider FHIR for real-time)")
        return ClarityCultureSource()

    # Default to FHIR (preferred for real-time surveillance)
    return FHIRCultureSource()


class CompositeNoteSource(BaseNoteSource):
    """Composite note source that queries both FHIR and Clarity."""

    def __init__(self):
        self.fhir_source = FHIRNoteSource()
        self.clarity_source = None
        if Config.is_clarity_configured():
            self.clarity_source = ClarityNoteSource()

    def get_notes_for_patient(
        self,
        patient_id: str,
        start_date,
        end_date,
        note_types=None,
    ):
        """Get notes from both sources and deduplicate."""
        from datetime import datetime

        notes = []
        seen_dates = set()

        # Try FHIR first
        try:
            fhir_notes = self.fhir_source.get_notes_for_patient(
                patient_id, start_date, end_date, note_types
            )
            for note in fhir_notes:
                key = (note.date.isoformat() if isinstance(note.date, datetime) else note.date, note.note_type)
                if key not in seen_dates:
                    notes.append(note)
                    seen_dates.add(key)
        except Exception as e:
            logger.warning(f"FHIR note retrieval failed: {e}")

        # Try Clarity if configured
        if self.clarity_source:
            try:
                clarity_notes = self.clarity_source.get_notes_for_patient(
                    patient_id, start_date, end_date, note_types
                )
                for note in clarity_notes:
                    key = (note.date.isoformat() if isinstance(note.date, datetime) else note.date, note.note_type)
                    if key not in seen_dates:
                        notes.append(note)
                        seen_dates.add(key)
            except Exception as e:
                logger.warning(f"Clarity note retrieval failed: {e}")

        # Sort by date descending
        notes.sort(key=lambda n: n.date, reverse=True)
        return notes

    def get_note_by_id(self, note_id: str):
        """Try to get note from FHIR first, then Clarity."""
        note = self.fhir_source.get_note_by_id(note_id)
        if note:
            return note

        if self.clarity_source:
            return self.clarity_source.get_note_by_id(note_id)

        return None


def get_procedure_source(source_type: str | None = None) -> BaseProcedureSource:
    """Get the configured procedure source for SSI monitoring.

    FHIR is preferred for real-time SSI surveillance. Clarity should only
    be used for bulk historical extraction. Mock is available for development.

    Args:
        source_type: Override source type (fhir, clarity, mock). Uses config if not specified.

    Returns:
        Configured procedure source implementation.
    """
    source = source_type or Config.PROCEDURE_SOURCE

    if source == "clarity":
        if not Config.is_clarity_configured():
            logger.warning("Clarity not configured, falling back to FHIR")
            return FHIRProcedureSource()
        logger.info("Using Clarity for procedure source (consider FHIR for real-time)")
        return ClarityProcedureSource()

    if source == "mock":
        return MockProcedureSource()

    # Default to FHIR (preferred for real-time surveillance)
    return FHIRProcedureSource()


def get_ventilator_source(source_type: str | None = None) -> BaseVentilatorSource:
    """Get the configured ventilator source for VAE monitoring.

    FHIR is the only supported source for ventilator data. VAE surveillance
    requires real-time access to FiO2/PEEP parameters which FHIR provides
    through Observation resources.

    Args:
        source_type: Override source type (fhir). Uses config if not specified.

    Returns:
        Configured ventilator source implementation (FHIR only).
    """
    source = source_type or Config.VENTILATOR_SOURCE

    if source != "fhir":
        logger.warning(f"Ventilator source '{source}' not supported, using FHIR")

    # FHIR is the only source for real-time ventilator parameters
    return FHIRVentilatorSource()


# ============================================================
# CAUTI-specific data source factories
# ============================================================

def get_urinary_catheter_source() -> FHIRUrinaryCatheterSource:
    """Get the urinary catheter source for CAUTI monitoring.

    FHIR is the only supported source for urinary catheter tracking.
    Queries DeviceUseStatement resources for indwelling urinary catheters.

    Returns:
        FHIRUrinaryCatheterSource for real-time catheter tracking.
    """
    return FHIRUrinaryCatheterSource()


def get_urine_culture_source() -> FHIRUrineCultureSource:
    """Get the urine culture source for CAUTI monitoring.

    FHIR is the only supported source for urine cultures with CFU values.
    Queries DiagnosticReport resources for urine culture results.

    Returns:
        FHIRUrineCultureSource for real-time urine culture retrieval.
    """
    return FHIRUrineCultureSource()


# ============================================================
# CDI-specific data source factories
# ============================================================

def get_cdi_test_source() -> FHIRCDITestSource:
    """Get the CDI test source for C. difficile surveillance.

    FHIR is the only supported source for CDI test results. Queries
    Observation resources for toxin and molecular test results, and
    Encounter resources for admission/discharge timing.

    Returns:
        FHIRCDITestSource for real-time CDI surveillance.
    """
    return FHIRCDITestSource()
