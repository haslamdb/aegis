"""Broad-spectrum antibiotic usage monitoring service.

Monitors active medication orders for meropenem and vancomycin,
alerting when usage exceeds the configured threshold (default 72 hours).

Adapted from Flask monitor.py for Django ORM.
"""

import logging

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity

from .data_models import Patient, MedicationOrder, UsageAssessment
from .fhir_client import FHIRClient, get_fhir_client

logger = logging.getLogger(__name__)


def _get_config():
    """Get antimicrobial usage config from Django settings."""
    return getattr(settings, 'ANTIMICROBIAL_USAGE', {})


class BroadSpectrumMonitorService:
    """Monitors broad-spectrum antibiotic usage duration."""

    def __init__(self, fhir_client: FHIRClient | None = None):
        self.fhir_client = fhir_client or get_fhir_client()
        conf = _get_config()
        self.threshold_hours = conf.get('ALERT_THRESHOLD_HOURS', 72)

    def check_all_patients(self) -> list[UsageAssessment]:
        """Check all patients with monitored medications.

        Returns assessments for orders exceeding threshold.
        """
        assessments = []

        orders = self.fhir_client.get_monitored_medications()
        logger.info(f"Found {len(orders)} active monitored medication orders")

        for order in orders:
            assessment = self._assess_order(order)
            if assessment and assessment.exceeds_threshold:
                assessments.append(assessment)

        logger.info(f"Found {len(assessments)} orders exceeding {self.threshold_hours}h threshold")
        return assessments

    def check_new_alerts(self) -> list[tuple[UsageAssessment, Alert]]:
        """Check for new alerts (orders not previously alerted).

        Returns list of (UsageAssessment, Alert) tuples for new alerts only.
        """
        all_assessments = self.check_all_patients()

        new_alerts = []
        for assessment in all_assessments:
            order_fhir_id = assessment.medication.fhir_id

            # Deduplication: check if already alerted via Django ORM
            already_alerted = Alert.objects.filter(
                alert_type=AlertType.BROAD_SPECTRUM_USAGE,
                details__medication_fhir_id=order_fhir_id,
            ).exists()

            if already_alerted:
                continue

            # Create alert
            try:
                alert = self._create_alert(assessment)
                new_alerts.append((assessment, alert))
            except Exception as e:
                logger.error(f"Failed to save alert for order {order_fhir_id}: {e}")

        logger.info(f"Found {len(new_alerts)} new alerts")
        return new_alerts

    def _assess_order(self, order: MedicationOrder) -> UsageAssessment | None:
        """Assess a single medication order."""
        duration_hours = order.duration_hours
        if duration_hours is None:
            logger.warning(f"Order {order.fhir_id} has no start date, skipping")
            return None

        # Get patient info
        patient = self.fhir_client.get_patient(order.patient_id)
        if not patient:
            logger.warning(f"Could not find patient {order.patient_id} for order {order.fhir_id}")
            patient = Patient(
                fhir_id=order.patient_id,
                mrn="Unknown",
                name="Unknown Patient",
            )

        exceeds = duration_hours >= self.threshold_hours

        # Determine severity: CRITICAL if >= 2x threshold, HIGH if >= threshold
        if duration_hours >= self.threshold_hours * 2:
            severity = AlertSeverity.CRITICAL
        elif exceeds:
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.INFO

        recommendation = self._generate_recommendation(order, duration_hours)

        return UsageAssessment(
            patient=patient,
            medication=order,
            duration_hours=duration_hours,
            threshold_hours=self.threshold_hours,
            exceeds_threshold=exceeds,
            recommendation=recommendation,
            severity=severity,
        )

    def _generate_recommendation(self, order: MedicationOrder, duration_hours: float) -> str:
        """Generate a recommendation based on the medication and duration."""
        days = duration_hours / 24
        med_name = order.medication_name

        if duration_hours >= self.threshold_hours * 2:
            return (
                f"{med_name} has been active for {days:.1f} days ({duration_hours:.0f} hours). "
                f"Urgent: Please review for de-escalation or discontinuation. "
                f"Consider culture results and clinical response."
            )
        else:
            return (
                f"{med_name} has exceeded {self.threshold_hours} hours (currently {days:.1f} days). "
                f"Consider reviewing antibiotic necessity and potential de-escalation based on "
                f"culture and sensitivity results."
            )

    def _create_alert(self, assessment: UsageAssessment) -> Alert:
        """Create an Alert + AlertAudit in Django ORM."""
        med = assessment.medication
        patient = assessment.patient

        alert = Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id=med.fhir_id,
            title=f"Broad-Spectrum Alert: {med.medication_name}",
            summary=f"{med.medication_name} > {assessment.threshold_hours}h ({assessment.duration_hours:.0f}h)",
            details={
                'medication_name': med.medication_name,
                'rxnorm_code': med.rxnorm_code,
                'medication_fhir_id': med.fhir_id,
                'duration_hours': round(assessment.duration_hours, 1),
                'threshold_hours': assessment.threshold_hours,
                'dose': med.dose,
                'route': med.route,
                'start_date': med.start_date.isoformat() if med.start_date else None,
                'recommendation': assessment.recommendation,
                'location': patient.location,
                'department': patient.department,
                'patient_name': patient.name,
                'patient_mrn': patient.mrn,
                'patient_fhir_id': patient.fhir_id,
            },
            patient_id=patient.fhir_id,
            patient_mrn=patient.mrn,
            patient_name=patient.name,
            patient_location=patient.location,
            severity=assessment.severity,
            priority_score=90 if assessment.severity == AlertSeverity.CRITICAL else 75,
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            old_status=None,
            new_status=AlertStatus.PENDING,
            details={'source': 'broad_spectrum_monitor'},
        )

        return alert

    def get_stats(self) -> dict:
        """Get current alert statistics via ORM aggregation."""
        active_qs = Alert.objects.filter(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            status__in=[
                AlertStatus.PENDING,
                AlertStatus.SENT,
                AlertStatus.ACKNOWLEDGED,
                AlertStatus.IN_PROGRESS,
                AlertStatus.SNOOZED,
            ],
        )

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        resolved_today = Alert.objects.filter(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            status=AlertStatus.RESOLVED,
            resolved_at__gte=today_start,
        ).count()

        # By severity
        by_severity = {}
        for row in active_qs.values('severity').annotate(count=Count('id')):
            by_severity[row['severity']] = row['count']

        # By medication
        by_medication = {}
        for alert in active_qs:
            med_name = (alert.details or {}).get('medication_name', 'Unknown')
            by_medication[med_name] = by_medication.get(med_name, 0) + 1

        return {
            'active_count': active_qs.count(),
            'critical_count': active_qs.filter(severity=AlertSeverity.CRITICAL).count(),
            'high_count': active_qs.filter(severity=AlertSeverity.HIGH).count(),
            'resolved_today': resolved_today,
            'by_severity': by_severity,
            'by_medication': by_medication,
        }
