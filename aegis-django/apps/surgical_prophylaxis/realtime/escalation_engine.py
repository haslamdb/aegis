"""
Alert escalation engine for real-time prophylaxis monitoring.

Routes alerts with automatic escalation based on trigger type and response time.

Adapted from surgical-prophylaxis/src/realtime/escalation_engine.py.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus
from apps.surgical_prophylaxis.models import AlertEscalation, AlertTrigger, SurgicalJourney

logger = logging.getLogger(__name__)


@dataclass
class EscalationRule:
    """Defines escalation routing for a trigger type."""
    trigger: str
    initial_role: str
    initial_channel: str
    escalation_delay_minutes: int = 30
    escalation_role: str = ""
    escalation_channel: str = ""


DEFAULT_RULES = [
    EscalationRule(
        trigger=AlertTrigger.T24,
        initial_role='pharmacy',
        initial_channel='dashboard',
        escalation_delay_minutes=60,
    ),
    EscalationRule(
        trigger=AlertTrigger.T2,
        initial_role='preop_rn',
        initial_channel='dashboard',
        escalation_delay_minutes=30,
        escalation_role='anesthesia',
        escalation_channel='dashboard',
    ),
    EscalationRule(
        trigger=AlertTrigger.T60,
        initial_role='anesthesia',
        initial_channel='dashboard',
        escalation_delay_minutes=15,
        escalation_role='surgeon',
        escalation_channel='dashboard',
    ),
    EscalationRule(
        trigger=AlertTrigger.T0,
        initial_role='anesthesia',
        initial_channel='dashboard',
        escalation_delay_minutes=5,
        escalation_role='asp',
        escalation_channel='dashboard',
    ),
]


class EscalationEngine:
    """Routes alerts with automatic escalation."""

    def __init__(self, rules: Optional[list[EscalationRule]] = None):
        self.rules = {r.trigger: r for r in (rules or DEFAULT_RULES)}

    def send_alert(self, journey: SurgicalJourney, trigger: str,
                   severity: str, recommendation: str) -> Optional[Alert]:
        """Create an alert and record initial escalation."""
        rule = self.rules.get(trigger)
        if not rule:
            return None

        now = timezone.now()

        # Create the alert
        alert = Alert.objects.create(
            alert_type=AlertType.SURGICAL_PROPHYLAXIS,
            source_module='surgical_prophylaxis_realtime',
            source_id=journey.journey_id,
            title=f"Pre-Op Prophylaxis: {journey.procedure_description[:100]}",
            summary=recommendation,
            details={
                'journey_id': journey.journey_id,
                'trigger': trigger,
                'patient_mrn': journey.patient_mrn,
                'procedure': journey.procedure_description,
                'scheduled_time': journey.scheduled_time.isoformat() if journey.scheduled_time else None,
                'order_exists': journey.order_exists,
                'administered': journey.administered,
            },
            patient_mrn=journey.patient_mrn,
            patient_name=journey.patient_name,
            severity=severity,
            status=AlertStatus.PENDING,
        )

        alert.create_audit_entry(action='created', extra_details={'trigger': trigger})

        # Record escalation
        next_escalation = now + timedelta(minutes=rule.escalation_delay_minutes) if rule.escalation_role else None

        AlertEscalation.objects.create(
            alert_ref=str(alert.id),
            journey=journey,
            escalation_level=1,
            trigger_type=trigger,
            recipient_role=rule.initial_role,
            delivery_channel=rule.initial_channel,
            sent_at=now,
            delivery_status='sent',
            next_escalation_at=next_escalation,
        )

        return alert

    def acknowledge_alert(self, alert_id: str, user=None):
        """Acknowledge an alert and cancel pending escalations."""
        try:
            alert = Alert.objects.get(id=alert_id)
            if user:
                alert.acknowledge(user)

            AlertEscalation.objects.filter(
                alert_ref=str(alert_id),
                escalated=False,
            ).update(
                delivery_status='acknowledged',
                response_at=timezone.now(),
            )
        except Alert.DoesNotExist:
            logger.warning(f"Alert {alert_id} not found for acknowledgment")

    def check_escalations(self):
        """Check for overdue escalations and escalate if needed."""
        now = timezone.now()
        overdue = AlertEscalation.objects.filter(
            escalated=False,
            next_escalation_at__lte=now,
            delivery_status='sent',
        ).select_related('journey')

        for escalation in overdue:
            rule = self.rules.get(escalation.trigger_type)
            if not rule or not rule.escalation_role:
                continue

            # Create escalation record
            AlertEscalation.objects.create(
                alert_ref=escalation.alert_ref,
                journey=escalation.journey,
                escalation_level=escalation.escalation_level + 1,
                trigger_type=escalation.trigger_type,
                recipient_role=rule.escalation_role,
                delivery_channel=rule.escalation_channel,
                sent_at=now,
                delivery_status='sent',
            )

            escalation.escalated = True
            escalation.save(update_fields=['escalated', 'updated_at'])

            logger.info(
                f"Escalated alert {escalation.alert_ref} to {rule.escalation_role} "
                f"(level {escalation.escalation_level + 1})"
            )
