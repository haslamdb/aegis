"""
Drug-Bug Mismatch Service.

Encapsulates the drug-bug mismatch detection pipeline so it can be
called from both the management command (CLI) and Celery tasks.
"""

import logging

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from .data_models import AlertSeverity as LocalAlertSeverity
from .fhir_client import DrugBugFHIRClient
from .matcher import assess_mismatch, should_alert

logger = logging.getLogger(__name__)

# Map local severity enum to Django AlertSeverity
SEVERITY_MAP = {
    LocalAlertSeverity.CRITICAL: AlertSeverity.HIGH,
    LocalAlertSeverity.WARNING: AlertSeverity.MEDIUM,
    LocalAlertSeverity.INFO: AlertSeverity.LOW,
}


class DrugBugMonitorService:
    """Service for drug-bug mismatch detection."""

    def run_detection(self, hours_back=24, fhir_client=None):
        """
        Run a single drug-bug mismatch detection cycle.

        Args:
            hours_back: Hours to look back for cultures.
            fhir_client: Optional pre-configured FHIR client.

        Returns:
            Dict with keys: cultures_checked, alerts_created, errors.
        """
        if fhir_client is None:
            fhir_client = DrugBugFHIRClient()

        result = {
            'cultures_checked': 0,
            'alerts_created': 0,
            'errors': [],
        }

        processed_cultures = set()

        try:
            cultures = fhir_client.get_cultures_with_susceptibilities(
                hours_back=hours_back
            )
            result['cultures_checked'] = len(cultures)
            logger.info(
                f"Found {len(cultures)} culture(s) with susceptibilities "
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
            logger.error(f"Error fetching cultures: {e}")
            result['errors'].append({
                'stage': 'fetch_cultures',
                'error': str(e),
            })

        logger.info(
            f"Drug-bug check complete: {result['cultures_checked']} cultures, "
            f"{result['alerts_created']} alerts created"
        )
        return result

    def _check_culture(self, fhir_client, culture, processed_cultures):
        """Check a single culture for drug-bug mismatches."""
        # Skip if already processed this cycle
        if culture.fhir_id in processed_cultures:
            return False

        # Check persistent store for duplicates
        existing = Alert.objects.filter(
            source_module='drug_bug_mismatch',
            source_id=culture.fhir_id,
        ).exists()

        if existing:
            processed_cultures.add(culture.fhir_id)
            return False

        processed_cultures.add(culture.fhir_id)

        # Skip if no susceptibility data
        if not culture.susceptibilities:
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
        assessment = assess_mismatch(patient, culture, antibiotics)

        # Generate alert if needed
        if should_alert(assessment):
            self._create_alert(assessment)
            return True

        return False

    def _create_alert(self, assessment):
        """Create and save Alert record for a mismatch assessment."""
        patient = assessment.patient
        culture = assessment.culture
        severity = SEVERITY_MAP.get(assessment.severity, AlertSeverity.MEDIUM)

        # Build title
        mismatch_type = "Mismatch"
        if assessment.mismatches:
            first_mismatch = assessment.mismatches[0]
            mismatch_type = first_mismatch.mismatch_type.value.replace("_", " ").title()

        title = f"Drug-Bug Mismatch: {culture.organism} ({mismatch_type})"

        # Build summary
        resistant_abx = [
            m.antibiotic.medication_name
            for m in assessment.mismatches
            if m.mismatch_type.value == "resistant"
        ]
        if resistant_abx:
            summary = f"Resistant to {', '.join(resistant_abx)}"
        else:
            summary = assessment.recommendation[:100]

        alert = Alert.objects.create(
            alert_type=AlertType.DRUG_BUG_MISMATCH,
            source_module='drug_bug_mismatch',
            source_id=culture.fhir_id,
            title=title,
            summary=summary,
            details=assessment.to_alert_content(),
            patient_id=patient.fhir_id,
            patient_mrn=patient.mrn,
            patient_name=patient.name,
            patient_location=patient.location,
            severity=severity,
            priority_score=75 if severity == AlertSeverity.HIGH else 50,
            status=AlertStatus.PENDING,
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            old_status=None,
            new_status=AlertStatus.PENDING,
            details={'source': 'drug_bug_monitor'},
        )

        logger.info(
            f"Created alert {str(alert.id)[:8]}... for {patient.name} ({patient.mrn})"
        )
