"""
Real-time pre-operative compliance checker.

Checks prophylaxis status at trigger points (T-24h, T-2h, T-60m, T-0)
and determines if alerts are needed.

Adapted from surgical-prophylaxis/src/realtime/preop_checker.py.
"""

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

from apps.alerts.models import AlertSeverity
from apps.surgical_prophylaxis.models import AlertTrigger, SurgicalJourney

logger = logging.getLogger(__name__)


class PreOpChecker:
    """Performs compliance checks at specific trigger points."""

    def __init__(self, fhir_client=None):
        self.fhir_client = fhir_client

    def check_at_trigger(self, journey: SurgicalJourney, trigger: str) -> dict:
        """
        Check prophylaxis status at a trigger point.

        Returns dict with check result data for PreOpCheck creation.
        """
        now = timezone.now()
        minutes_to_or = None
        if journey.scheduled_time:
            delta = (journey.scheduled_time - now).total_seconds() / 60
            minutes_to_or = int(delta)

        # Determine if alert is required
        alert_required = False
        alert_severity = ''
        recommendation = ''

        if journey.excluded:
            recommendation = f"Excluded: {journey.exclusion_reason}"
        elif journey.prophylaxis_indicated is False:
            recommendation = "Prophylaxis not indicated for this procedure"
        elif not journey.order_exists and not journey.administered:
            alert_required = True
            if trigger in (AlertTrigger.T0, AlertTrigger.OR_ENTRY):
                alert_severity = AlertSeverity.CRITICAL
                recommendation = "CRITICAL: No prophylaxis order or administration. Patient entering OR without prophylaxis."
            elif trigger in (AlertTrigger.T60,):
                alert_severity = AlertSeverity.HIGH
                recommendation = "No prophylaxis order found. Surgery in ~60 minutes. Order prophylaxis now."
            elif trigger in (AlertTrigger.T2, AlertTrigger.PREOP_ARRIVAL):
                alert_severity = AlertSeverity.HIGH
                recommendation = "No prophylaxis order found. Place order for surgical prophylaxis."
            else:
                alert_severity = AlertSeverity.MEDIUM
                recommendation = "No prophylaxis order found. Verify prophylaxis plan before surgery."
        elif journey.order_exists and not journey.administered:
            if trigger in (AlertTrigger.T0, AlertTrigger.OR_ENTRY):
                alert_required = True
                alert_severity = AlertSeverity.CRITICAL
                recommendation = "CRITICAL: Prophylaxis ordered but NOT administered. Administer before incision."
            elif trigger == AlertTrigger.T60:
                alert_required = True
                alert_severity = AlertSeverity.HIGH
                recommendation = "Prophylaxis ordered but not yet given. Administer within timing window."

        return {
            'trigger_type': trigger,
            'trigger_time': now,
            'prophylaxis_indicated': journey.prophylaxis_indicated or False,
            'order_exists': journey.order_exists,
            'administered': journey.administered,
            'minutes_to_or': minutes_to_or,
            'alert_required': alert_required,
            'alert_severity': alert_severity,
            'recommendation': recommendation,
            'check_details': {
                'patient_mrn': journey.patient_mrn,
                'procedure': journey.procedure_description,
                'current_state': journey.current_state,
            },
        }

    def check_on_preop_arrival(self, journey: SurgicalJourney) -> dict:
        """Check when patient arrives in pre-op holding."""
        return self.check_at_trigger(journey, AlertTrigger.PREOP_ARRIVAL)

    def check_on_or_entry(self, journey: SurgicalJourney) -> dict:
        """Check when patient enters OR — most critical point."""
        return self.check_at_trigger(journey, AlertTrigger.OR_ENTRY)
