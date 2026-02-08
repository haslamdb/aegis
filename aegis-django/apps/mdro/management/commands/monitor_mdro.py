"""
Management command for MDRO surveillance monitoring.

Polls FHIR server for new microbiology cultures and processes them
for MDRO detection. Replaces mdro_src/monitor.py + runner.py.

Usage:
    python manage.py monitor_mdro --once
    python manage.py monitor_mdro --once --hours 72
    python manage.py monitor_mdro --continuous --interval 15
"""

import logging
import time
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from apps.mdro.classifier import MDROClassifier
from apps.mdro.fhir_client import MDROFHIRClient
from apps.mdro.models import (
    MDROCase, MDROProcessingLog,
    MDROTypeChoices, TransmissionStatusChoices,
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


class Command(BaseCommand):
    help = 'Monitor FHIR server for new MDRO cases'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run once and exit',
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuously',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Hours to look back for cultures (default: 24)',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=15,
            help='Minutes between polls in continuous mode (default: 15)',
        )

    def handle(self, *args, **options):
        if options['continuous']:
            self._run_continuous(
                hours_back=options['hours'],
                interval_minutes=options['interval'],
            )
        else:
            # Default to --once behavior
            result = self._run_once(hours_back=options['hours'])
            self.stdout.write(self.style.SUCCESS(
                f"Monitor complete: {result['new_mdro_cases']} new cases, "
                f"{result['cultures_checked']} cultures checked, "
                f"{result['skipped_already_processed']} skipped (already processed), "
                f"{result['skipped_not_mdro']} not MDRO"
            ))
            if result['errors']:
                self.stdout.write(self.style.WARNING(
                    f"  Errors: {len(result['errors'])}"
                ))

    def _run_once(self, hours_back=24):
        """Run a single polling cycle."""
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
            self.stdout.write(f"Found {len(cultures)} cultures in last {hours_back} hours")

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
                    self.stdout.write(
                        f"  New MDRO: {classification.mdro_type.value.upper()} - "
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

    def _run_continuous(self, hours_back=24, interval_minutes=15):
        """Run continuous monitoring loop."""
        self.stdout.write(
            f"Starting MDRO monitor (polling every {interval_minutes} minutes)"
        )

        while True:
            try:
                result = self._run_once(hours_back=hours_back)
                self.stdout.write(
                    f"Polling complete: {result['new_mdro_cases']} new cases"
                )
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                self.stderr.write(self.style.ERROR(f"Error: {e}"))

            time.sleep(interval_minutes * 60)
