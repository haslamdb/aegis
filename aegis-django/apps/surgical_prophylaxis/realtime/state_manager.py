"""
Django ORM-based state manager for surgical journeys.

Replaces SQLite state_manager.py with Django ORM operations.
"""

import logging
from datetime import datetime
from typing import Optional

from django.utils import timezone

from apps.surgical_prophylaxis.models import (
    SurgicalJourney,
    PatientLocation,
    PreOpCheck,
    LocationState,
)

logger = logging.getLogger(__name__)


class StateManager:
    """Manages surgical journey state via Django ORM."""

    def create_journey(self, journey_data: dict) -> SurgicalJourney:
        """Create a new surgical journey."""
        return SurgicalJourney.objects.create(**journey_data)

    def get_journey(self, journey_id: str) -> Optional[SurgicalJourney]:
        try:
            return SurgicalJourney.objects.get(journey_id=journey_id)
        except SurgicalJourney.DoesNotExist:
            return None

    def get_journey_for_patient(self, mrn: str) -> Optional[SurgicalJourney]:
        """Get active (incomplete) journey for a patient."""
        return SurgicalJourney.objects.filter(
            patient_mrn=mrn,
            completed_at__isnull=True,
        ).order_by('-created_at').first()

    def update_location(self, journey_id: str, location_code: str, location_state: str,
                        event_time=None, hl7_message_id: str = '') -> Optional[PatientLocation]:
        """Update journey state and save location history."""
        journey = self.get_journey(journey_id)
        if not journey:
            return None

        journey.current_state = location_state
        journey.save(update_fields=['current_state', 'updated_at'])

        return PatientLocation.objects.create(
            patient_mrn=journey.patient_mrn,
            journey=journey,
            location_code=location_code,
            location_state=location_state,
            event_time=event_time or timezone.now(),
            message_time=timezone.now(),
            hl7_message_id=hl7_message_id,
        )

    def update_prophylaxis_status(self, journey_id: str, order_exists: bool = None,
                                   administered: bool = None):
        """Update prophylaxis status on a journey."""
        journey = self.get_journey(journey_id)
        if not journey:
            return

        update_fields = ['updated_at']
        if order_exists is not None:
            journey.order_exists = order_exists
            update_fields.append('order_exists')
        if administered is not None:
            journey.administered = administered
            update_fields.append('administered')

        journey.save(update_fields=update_fields)

    def mark_alert_sent(self, journey_id: str, trigger: str):
        """Mark a trigger alert as sent."""
        journey = self.get_journey(journey_id)
        if not journey:
            return

        now = timezone.now()
        field_map = {
            't24': ('alert_t24_sent', 'alert_t24_time'),
            't2': ('alert_t2_sent', 'alert_t2_time'),
            't60': ('alert_t60_sent', 'alert_t60_time'),
            't0': ('alert_t0_sent', 'alert_t0_time'),
        }

        if trigger in field_map:
            sent_field, time_field = field_map[trigger]
            setattr(journey, sent_field, True)
            setattr(journey, time_field, now)
            journey.save(update_fields=[sent_field, time_field, 'updated_at'])

    def record_check(self, journey: SurgicalJourney, check_data: dict) -> PreOpCheck:
        """Save a pre-op check result."""
        return PreOpCheck.objects.create(journey=journey, **check_data)

    def complete_journey(self, journey_id: str):
        """Mark a journey as completed."""
        journey = self.get_journey(journey_id)
        if journey:
            journey.completed_at = timezone.now()
            journey.save(update_fields=['completed_at', 'updated_at'])

    def get_active_journeys(self):
        """Get all active (incomplete) journeys."""
        return SurgicalJourney.objects.filter(
            completed_at__isnull=True,
        ).select_related('case').order_by('-created_at')
