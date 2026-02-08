"""
Management command to run dosing verification monitoring.

Fetches patients with active antimicrobial orders from FHIR,
evaluates dosing rules, and creates alerts for issues found.

Usage:
    python manage.py monitor_dosing --once               # Run once
    python manage.py monitor_dosing --once --hours 24    # Check last 24h
    python manage.py monitor_dosing --continuous          # Run continuously
    python manage.py monitor_dosing --continuous --interval 900  # Every 15 min
"""

import logging
import time
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from apps.dosing.fhir_client import DosingFHIRClient
from apps.dosing.rules_engine import DosingRulesEngine
from apps.dosing.alert_models import DoseAlertSeverity, DoseFlagType
from apps.dosing.views import FLAG_TYPE_TO_ALERT_TYPE

logger = logging.getLogger(__name__)

# Map DoseAlertSeverity to AlertSeverity
SEVERITY_MAP = {
    DoseAlertSeverity.CRITICAL: AlertSeverity.CRITICAL,
    DoseAlertSeverity.HIGH: AlertSeverity.HIGH,
    DoseAlertSeverity.MODERATE: AlertSeverity.MEDIUM,
    DoseAlertSeverity.LOW: AlertSeverity.LOW,
}


class Command(BaseCommand):
    help = 'Run dosing verification monitoring against FHIR server'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run once and exit',
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuously at specified interval',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=900,
            help='Seconds between checks in continuous mode (default: 900)',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Look back window in hours (default: 24)',
        )

    def handle(self, *args, **options):
        if options['continuous']:
            self.stdout.write(self.style.SUCCESS(
                f'Starting continuous dosing monitoring (interval: {options["interval"]}s)'
            ))
            while True:
                try:
                    self._run_check(options['hours'])
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'Error during check: {e}'))
                    logger.exception('Error during dosing monitoring check')
                time.sleep(options['interval'])
        else:
            self._run_check(options['hours'])

    def _run_check(self, hours):
        """Run a single dosing verification check."""
        self.stdout.write(f'Running dosing verification check (lookback: {hours}h)...')

        try:
            client = DosingFHIRClient()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to initialize FHIR client: {e}'))
            return

        engine = DosingRulesEngine()

        try:
            patients = client.get_patients_with_active_antimicrobials(hours=hours)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to fetch patients from FHIR: {e}'))
            return

        self.stdout.write(f'Found {len(patients)} patients with active antimicrobials')

        total_flags = 0
        alerts_created = 0
        alerts_skipped = 0

        for patient_id in patients:
            try:
                context = client.build_patient_context(patient_id)
                if not context:
                    continue

                assessment = engine.evaluate(context)

                if not assessment.flags:
                    continue

                total_flags += len(assessment.flags)

                for flag in assessment.flags:
                    # Determine alert type from flag type
                    flag_value = flag.flag_type.value if hasattr(flag.flag_type, 'value') else flag.flag_type
                    alert_type = FLAG_TYPE_TO_ALERT_TYPE.get(flag_value, AlertType.DOSING_INDICATION)

                    # Build source_id for deduplication
                    source_id = f'{patient_id}-{flag_value}-{flag.drug}'

                    # Check for existing active alert (deduplication)
                    existing = Alert.objects.filter(
                        source_module='dosing_verification',
                        source_id=source_id,
                        status__in=[
                            AlertStatus.PENDING,
                            AlertStatus.SENT,
                            AlertStatus.ACKNOWLEDGED,
                            AlertStatus.IN_PROGRESS,
                        ],
                    ).exists()

                    if existing:
                        alerts_skipped += 1
                        continue

                    # Map severity
                    severity_value = flag.severity.value if hasattr(flag.severity, 'value') else flag.severity
                    try:
                        dose_severity = DoseAlertSeverity(severity_value)
                    except (ValueError, KeyError):
                        dose_severity = DoseAlertSeverity.MODERATE
                    django_severity = SEVERITY_MAP.get(dose_severity, AlertSeverity.MEDIUM)

                    # Build details JSONField
                    details = {
                        'drug': flag.drug,
                        'flag_type': flag_value,
                        'flag_type_display': DoseFlagType.display_name(flag_value),
                        'indication': flag.indication or '',
                        'expected_dose': flag.expected,
                        'actual_dose': flag.actual,
                        'rule_source': flag.rule_source,
                        'patient_factors': assessment.to_alert_content().get('patient_factors', {}),
                        'assessment': assessment.to_dict(),
                        'medications': assessment.medications_evaluated,
                        'flags': [f.to_dict() for f in assessment.flags],
                    }

                    if flag.details:
                        details['flag_details'] = flag.details

                    # Priority score
                    if django_severity == AlertSeverity.CRITICAL:
                        priority = 95
                    elif django_severity == AlertSeverity.HIGH:
                        priority = 75
                    elif django_severity == AlertSeverity.MEDIUM:
                        priority = 50
                    else:
                        priority = 25

                    alert = Alert.objects.create(
                        alert_type=alert_type,
                        source_module='dosing_verification',
                        source_id=source_id,
                        title=f'Dosing: {DoseFlagType.display_name(flag_value)} - {flag.drug}',
                        summary=flag.message,
                        details=details,
                        patient_id=assessment.patient_id,
                        patient_mrn=assessment.patient_mrn,
                        patient_name=assessment.patient_name,
                        severity=django_severity,
                        priority_score=priority,
                    )

                    AlertAudit.objects.create(
                        alert=alert,
                        action='created',
                        old_status=None,
                        new_status=AlertStatus.PENDING,
                        details={'source': 'dosing_verification_monitor'},
                    )

                    alerts_created += 1

            except Exception as e:
                logger.warning(f'Error processing patient {patient_id}: {e}')
                continue

        self.stdout.write(self.style.SUCCESS(
            f'Check complete: {total_flags} flags found, '
            f'{alerts_created} alerts created, {alerts_skipped} duplicates skipped'
        ))
