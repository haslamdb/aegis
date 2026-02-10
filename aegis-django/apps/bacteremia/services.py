"""
Bacteremia Monitor Service.

Encapsulates the bacteremia coverage detection pipeline so it can be
called from both the management command (CLI) and Celery tasks.
"""

import logging

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from .fhir_client import BacteremiaFHIRClient
from .matcher import assess_coverage, should_alert

logger = logging.getLogger(__name__)


class BacteremiaMonitorService:
    """Service for bacteremia coverage monitoring."""

    def run_detection(self, hours_back=24, fhir_client=None):
        """
        Run a single bacteremia coverage detection cycle.

        Args:
            hours_back: Hours to look back for blood cultures.
            fhir_client: Optional pre-configured FHIR client.

        Returns:
            Dict with keys: cultures_checked, alerts_created, errors.
        """
        if fhir_client is None:
            fhir_client = BacteremiaFHIRClient()

        result = {
            'cultures_checked': 0,
            'alerts_created': 0,
            'errors': [],
        }

        processed_cultures = set()

        try:
            cultures = fhir_client.get_recent_blood_cultures(
                hours_back=hours_back
            )
            result['cultures_checked'] = len(cultures)
            logger.info(
                f"Found {len(cultures)} blood culture(s) "
                f"in the last {hours_back} hours"
            )

            for culture in cultures:
                try:
                    alerted = self._check_culture(
                        fhir_client, culture, processed_cultures
                    )
                    if alerted:
                        result['alerts_created'] += 1
                except Exception as e:
                    logger.error(f"Error processing culture {culture.fhir_id}: {e}")
                    result['errors'].append({
                        'culture_id': culture.fhir_id,
                        'error': str(e),
                    })

        except Exception as e:
            logger.error(f"Error fetching blood cultures: {e}")
            result['errors'].append({
                'stage': 'fetch_cultures',
                'error': str(e),
            })

        logger.info(
            f"Bacteremia check complete: {result['cultures_checked']} cultures, "
            f"{result['alerts_created']} alerts created"
        )
        return result

    def _check_culture(self, fhir_client, culture, processed_cultures):
        """Check a single blood culture for inadequate coverage."""
        # Skip if already processed this cycle
        if culture.fhir_id in processed_cultures:
            return False

        # Check persistent store for duplicates
        existing = Alert.objects.filter(
            source_module='bacteremia_monitor',
            source_id=culture.fhir_id,
        ).exists()

        if existing:
            processed_cultures.add(culture.fhir_id)
            return False

        processed_cultures.add(culture.fhir_id)

        # Skip if no organism and no gram stain
        if not culture.organism and not culture.gram_stain:
            return False

        if not culture.patient_id:
            return False

        # Get patient info
        patient = fhir_client.get_patient(culture.patient_id)
        if not patient:
            return False

        # Get active antibiotics
        antibiotics = fhir_client.get_current_antibiotics(culture.patient_id)

        # Assess coverage
        assessment = assess_coverage(patient, culture, antibiotics)

        # Generate alert if needed
        if should_alert(assessment):
            self._create_alert(assessment)
            return True

        return False

    def _create_alert(self, assessment):
        """Create and save Alert record for inadequate coverage."""
        patient = assessment.patient
        culture = assessment.culture

        organism_display = culture.organism or culture.gram_stain or "Unknown organism"
        title = f"Bacteremia: Inadequate coverage for {organism_display}"
        summary = assessment.recommendation[:100]

        alert = Alert.objects.create(
            alert_type=AlertType.BACTEREMIA,
            source_module='bacteremia_monitor',
            source_id=culture.fhir_id,
            title=title,
            summary=summary,
            details=assessment.to_alert_content(),
            patient_id=patient.fhir_id,
            patient_mrn=patient.mrn,
            patient_name=patient.name,
            patient_location=patient.location,
            severity=AlertSeverity.HIGH,
            priority_score=80,
            status=AlertStatus.PENDING,
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            old_status=None,
            new_status=AlertStatus.PENDING,
            details={'source': 'bacteremia_monitor'},
        )

        logger.info(
            f"Created bacteremia alert {str(alert.id)[:8]}... "
            f"for {patient.name} ({patient.mrn})"
        )
