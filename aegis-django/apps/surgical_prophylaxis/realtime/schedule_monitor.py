"""
OR schedule monitor.

Polls FHIR Appointments for upcoming surgeries and processes
HL7 ORM/SIU messages for scheduling changes.

Adapted from surgical-prophylaxis/src/realtime/schedule_monitor.py.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional, Awaitable

from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class ScheduledSurgery:
    """In-memory representation of a scheduled surgery (too transient for ORM)."""
    surgery_id: str
    patient_mrn: str
    patient_name: str = ""
    procedure_description: str = ""
    procedure_cpt_codes: list[str] = field(default_factory=list)
    scheduled_time: Optional[datetime] = None
    estimated_duration_minutes: int = 120
    surgeon_id: str = ""
    surgeon_name: str = ""
    or_location: str = ""
    appointment_status: str = "booked"
    fhir_appointment_id: str = ""


class ScheduleMonitor:
    """Monitors OR schedule for upcoming surgeries."""

    def __init__(self, fhir_client=None):
        self.fhir_client = fhir_client
        self._surgeries: dict[str, ScheduledSurgery] = {}

        # Callbacks
        self.on_new_surgery: Optional[Callable] = None
        self.on_surgery_updated: Optional[Callable] = None
        self.on_surgery_cancelled: Optional[Callable] = None

    async def poll_fhir_schedule(self, lookahead_hours: int = 48):
        """Poll FHIR for upcoming surgical appointments."""
        if not self.fhir_client:
            return

        now = timezone.now()
        end = now + timedelta(hours=lookahead_hours)

        try:
            appointments = self.fhir_client.get_appointments(
                date_from=now, date_to=end,
            )

            for appt in appointments:
                surgery_id = appt.get('id', '')
                if surgery_id not in self._surgeries:
                    surgery = self._parse_appointment(appt)
                    self._surgeries[surgery_id] = surgery
                    if self.on_new_surgery:
                        await self.on_new_surgery(surgery)

        except Exception as e:
            logger.error(f"Error polling FHIR schedule: {e}")

    def _parse_appointment(self, appt: dict) -> ScheduledSurgery:
        """Parse FHIR Appointment into ScheduledSurgery."""
        # Extract patient
        patient_mrn = ""
        patient_name = ""
        for participant in appt.get("participant", []):
            actor = participant.get("actor", {})
            ref = actor.get("reference", "")
            if "Patient/" in ref:
                patient_mrn = ref.replace("Patient/", "")
                patient_name = actor.get("display", "")

        # Extract timing
        start_str = appt.get("start", "")
        scheduled_time = None
        if start_str:
            try:
                scheduled_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        return ScheduledSurgery(
            surgery_id=appt.get("id", ""),
            patient_mrn=patient_mrn,
            patient_name=patient_name,
            procedure_description=appt.get("description", ""),
            scheduled_time=scheduled_time,
            appointment_status=appt.get("status", "booked"),
            fhir_appointment_id=appt.get("id", ""),
        )

    def get_surgeries_needing_alerts(self) -> dict[str, list[ScheduledSurgery]]:
        """Get surgeries grouped by which alert trigger window they're in."""
        now = timezone.now()
        result = {'t24': [], 't2': [], 't60': [], 't0': []}

        for surgery in self._surgeries.values():
            if not surgery.scheduled_time:
                continue
            delta = (surgery.scheduled_time - now).total_seconds() / 3600

            if 22 <= delta <= 26:
                result['t24'].append(surgery)
            elif 1.5 <= delta <= 2.5:
                result['t2'].append(surgery)
            elif 0.75 <= delta <= 1.25:
                result['t60'].append(surgery)
            elif -0.5 <= delta <= 0.25:
                result['t0'].append(surgery)

        return result

    @property
    def surgery_count(self) -> int:
        return len(self._surgeries)
