"""
MDRO Surveillance Service.

Encapsulates the MDRO detection pipeline so it can be called from
both the management command (CLI) and Celery tasks.
"""

import logging

from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity
from .classifier import MDROClassifier
from .fhir_client import MDROFHIRClient
from .models import (
    MDROCase, MDROProcessingLog,
    TransmissionStatusChoices,
)

logger = logging.getLogger(__name__)

# Severity mapping for MDRO types
MDRO_SEVERITY_MAP = {
    'cre': AlertSeverity.HIGH,
    'crab': AlertSeverity.HIGH,
    'crpa': AlertSeverity.HIGH,
    'vre': AlertSeverity.MEDIUM,
    'mrsa': AlertSeverity.MEDIUM,
    'esbl': AlertSeverity.MEDIUM,
}


class MDROMonitorService:
    """Service for MDRO surveillance detection."""

    def run_detection(self, hours_back=24):
        """
        Run a single MDRO detection cycle.

        Args:
            hours_back: Hours to look back for cultures.

        Returns:
            Dict with keys: cultures_checked, new_mdro_cases,
            skipped_already_processed, skipped_not_mdro, errors.
        """
        classifier = MDROClassifier()
        fhir = MDROFHIRClient()

        result = {
            'cultures_checked': 0,
            'new_mdro_cases': 0,
            'skipped_already_processed': 0,
            'skipped_not_mdro': 0,
            'errors': [],
        }

        try:
            cultures = fhir.get_recent_cultures(hours_back=hours_back)
            result['cultures_checked'] = len(cultures)
            logger.info(f"Found {len(cultures)} cultures in last {hours_back} hours")

            for culture in cultures:
                try:
                    # Check if already processed
                    if MDROProcessingLog.objects.filter(
                        culture_id=culture.fhir_id
                    ).exists():
                        result['skipped_already_processed'] += 1
                        continue

                    # Classify
                    classification = classifier.classify(
                        culture.organism,
                        culture.susceptibilities,
                    )

                    # Log processing
                    log_entry = MDROProcessingLog.objects.create(
                        culture_id=culture.fhir_id,
                        is_mdro=classification.is_mdro,
                        mdro_type=classification.mdro_type.value if classification.mdro_type else None,
                    )

                    if not classification.is_mdro:
                        result['skipped_not_mdro'] += 1
                        continue

                    # Calculate admission info
                    days_since_admission = None
                    admission_date = None
                    if culture.encounter_id:
                        admission_date = fhir.get_patient_admission_date(
                            culture.patient_id, culture.encounter_id
                        )
                        if admission_date and culture.collection_date:
                            delta = culture.collection_date - admission_date
                            days_since_admission = delta.days

                    # Determine transmission
                    if days_since_admission is not None:
                        if days_since_admission > 2:
                            transmission = TransmissionStatusChoices.HEALTHCARE
                        else:
                            transmission = TransmissionStatusChoices.COMMUNITY
                    else:
                        transmission = TransmissionStatusChoices.PENDING

                    # Check prior history
                    prior_cases = MDROCase.objects.filter(
                        patient_id=culture.patient_id
                    )
                    prior_history = prior_cases.exists()
                    is_new = not prior_cases.filter(
                        mdro_type=classification.mdro_type.value
                    ).exists()

                    # Create case
                    case = MDROCase.objects.create(
                        patient_id=culture.patient_id,
                        patient_mrn=culture.patient_mrn,
                        patient_name=culture.patient_name,
                        culture_id=culture.fhir_id,
                        culture_date=culture.collection_date,
                        specimen_type=culture.specimen_type or '',
                        organism=classification.organism,
                        mdro_type=classification.mdro_type.value,
                        resistant_antibiotics=classification.resistant_antibiotics,
                        susceptibilities=culture.susceptibilities,
                        classification_reason=classification.classification_reason,
                        location=culture.location or '',
                        unit=culture.unit or '',
                        admission_date=admission_date,
                        days_since_admission=days_since_admission,
                        transmission_status=transmission,
                        is_new=is_new,
                        prior_history=prior_history,
                    )

                    # Update processing log with case reference
                    log_entry.case = case
                    log_entry.save(update_fields=['case'])

                    # Create Alert record
                    severity = MDRO_SEVERITY_MAP.get(
                        classification.mdro_type.value, AlertSeverity.MEDIUM
                    )
                    Alert.objects.create(
                        alert_type=AlertType.MDRO_DETECTION,
                        source_module='mdro_surveillance',
                        source_id=str(case.id),
                        title=f"{classification.mdro_type.value.upper()} Detection - {classification.organism}",
                        summary=f"{classification.organism} classified as {classification.mdro_type.value.upper()} in {culture.unit or 'unknown unit'}.",
                        details={
                            'organism': classification.organism,
                            'mdro_type': classification.mdro_type.value,
                            'susceptibilities': culture.susceptibilities,
                            'classification_reason': classification.classification_reason,
                            'resistant_antibiotics': classification.resistant_antibiotics,
                        },
                        patient_id=culture.patient_id,
                        patient_mrn=culture.patient_mrn,
                        patient_name=culture.patient_name,
                        patient_location=culture.unit,
                        severity=severity,
                        priority_score=75 if severity == AlertSeverity.HIGH else 50,
                    )

                    result['new_mdro_cases'] += 1
                    logger.info(
                        f"New MDRO: {classification.mdro_type.value.upper()} - "
                        f"{classification.organism} ({culture.patient_mrn})"
                    )

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

        return result
