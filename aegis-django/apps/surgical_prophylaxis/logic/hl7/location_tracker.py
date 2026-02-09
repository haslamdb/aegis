"""
Patient location tracking state machine for surgical workflow.

Tracks patients as they move through the surgical pathway:
UNKNOWN -> PRE_OP_HOLDING -> OR_SUITE -> PACU -> DISCHARGED

Adapted from surgical-prophylaxis/src/realtime/location_tracker.py.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Awaitable

from .parser import HL7Message, extract_adt_a02_data

logger = logging.getLogger(__name__)

# Use string values matching Django TextChoices
UNKNOWN = 'unknown'
INPATIENT = 'inpatient'
PRE_OP_HOLDING = 'pre_op'
OR_SUITE = 'or_suite'
PACU = 'pacu'
DISCHARGED = 'discharged'


@dataclass
class LocationPatterns:
    """Configurable patterns for matching location codes to states."""

    pre_op_patterns: list[str] = field(
        default_factory=lambda: [
            r"PREOP", r"PHOLD", r"PRE-OP", r"SURG\s*PREP",
            r"PRESURG", r"SDS", r"ASC", r"PRE\s*ADMISSION",
        ]
    )
    or_patterns: list[str] = field(
        default_factory=lambda: [
            r"^OR\d*$", r"^OR\s", r"OPER", r"SURG\s*SUITE",
            r"THEATER", r"PROC\s*ROOM", r"CATH\s*LAB", r"IR\s*SUITE",
        ]
    )
    pacu_patterns: list[str] = field(
        default_factory=lambda: [
            r"PACU", r"RECOVERY", r"POST\s*ANES",
            r"POST\s*OP", r"STAGE\s*2", r"PHASE\s*II",
        ]
    )
    inpatient_patterns: list[str] = field(
        default_factory=lambda: [
            r"^\d+[A-Z]?$", r"WARD", r"UNIT",
            r"MED\s*SURG", r"ICU", r"PICU", r"NICU",
        ]
    )
    discharge_patterns: list[str] = field(
        default_factory=lambda: [
            r"DISCH", r"HOME", r"TRANSFER", r"EXPIRED", r"DECEASED",
        ]
    )

    def match_location(self, location_code: str) -> str:
        """Match a location code to a state string."""
        location_upper = location_code.upper().strip()
        pattern_groups = [
            (self.or_patterns, OR_SUITE),
            (self.pre_op_patterns, PRE_OP_HOLDING),
            (self.pacu_patterns, PACU),
            (self.discharge_patterns, DISCHARGED),
            (self.inpatient_patterns, INPATIENT),
        ]
        for patterns, state in pattern_groups:
            for pattern in patterns:
                if re.search(pattern, location_upper, re.IGNORECASE):
                    return state
        return UNKNOWN


@dataclass
class PatientLocationUpdate:
    """Represents a patient location change event."""
    patient_mrn: str
    new_location_code: str
    new_location_state: str
    prior_location_code: Optional[str] = None
    prior_location_state: Optional[str] = None
    event_time: Optional[datetime] = None
    message_control_id: Optional[str] = None
    visit_number: Optional[str] = None
    patient_name: Optional[str] = None


StateTransitionCallback = Callable[[PatientLocationUpdate], Awaitable[None]]


class LocationTracker:
    """Tracks patient locations and triggers callbacks on state transitions."""

    def __init__(self, patterns: Optional[LocationPatterns] = None):
        self.patterns = patterns or LocationPatterns()
        self.on_pre_op_arrival: Optional[StateTransitionCallback] = None
        self.on_or_entry: Optional[StateTransitionCallback] = None
        self.on_pacu_arrival: Optional[StateTransitionCallback] = None
        self.on_discharge: Optional[StateTransitionCallback] = None
        self._patient_states: dict[str, str] = {}

    def get_patient_state(self, patient_mrn: str) -> str:
        return self._patient_states.get(patient_mrn, UNKNOWN)

    def set_patient_state(self, patient_mrn: str, state: str) -> None:
        self._patient_states[patient_mrn] = state

    async def process_adt(self, message: HL7Message) -> Optional[PatientLocationUpdate]:
        if message.message_event not in ("A02", "A01", "A03", "A08"):
            return None

        data = extract_adt_a02_data(message)
        patient_mrn = data.get("patient_mrn")
        if not patient_mrn:
            return None

        current_location = data.get("current_location_code", "")
        new_state = self.patterns.match_location(current_location)
        prior_state = self._patient_states.get(patient_mrn, UNKNOWN)
        prior_location = data.get("prior_location", "")

        update = PatientLocationUpdate(
            patient_mrn=patient_mrn,
            new_location_code=current_location,
            new_location_state=new_state,
            prior_location_code=prior_location,
            prior_location_state=prior_state,
            event_time=data.get("message_time") or datetime.now(),
            message_control_id=data.get("message_control_id"),
            visit_number=data.get("visit_number"),
            patient_name=data.get("patient_name"),
        )

        self._patient_states[patient_mrn] = new_state
        await self._handle_state_transition(prior_state, new_state, update)

        logger.info(
            f"Patient {patient_mrn} location: {current_location} -> {new_state} "
            f"(was {prior_state})"
        )
        return update

    async def _handle_state_transition(self, prior_state, new_state, update):
        if new_state == PRE_OP_HOLDING and prior_state not in (OR_SUITE, PACU):
            if self.on_pre_op_arrival:
                try:
                    await self.on_pre_op_arrival(update)
                except Exception as e:
                    logger.error(f"Error in on_pre_op_arrival callback: {e}")
        elif new_state == OR_SUITE and prior_state != OR_SUITE:
            if self.on_or_entry:
                try:
                    await self.on_or_entry(update)
                except Exception as e:
                    logger.error(f"Error in on_or_entry callback: {e}")
        elif new_state == PACU and prior_state != PACU:
            if self.on_pacu_arrival:
                try:
                    await self.on_pacu_arrival(update)
                except Exception as e:
                    logger.error(f"Error in on_pacu_arrival callback: {e}")
        elif new_state == DISCHARGED:
            if self.on_discharge:
                try:
                    await self.on_discharge(update)
                except Exception as e:
                    logger.error(f"Error in on_discharge callback: {e}")

    def classify_location(self, location_code: str) -> str:
        return self.patterns.match_location(location_code)

    def clear_patient(self, patient_mrn: str) -> None:
        self._patient_states.pop(patient_mrn, None)

    def clear_all(self) -> None:
        self._patient_states.clear()

    @property
    def tracked_patients(self) -> dict[str, str]:
        return self._patient_states.copy()
