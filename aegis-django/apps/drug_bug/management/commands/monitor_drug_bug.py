"""
Management command to monitor for drug-bug mismatches.

Replaces drugbug_src/monitor.py and runner.py.

Usage:
    python manage.py monitor_drug_bug --once --hours 24
    python manage.py monitor_drug_bug --continuous --interval 300
"""

import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from apps.drug_bug.data_models import AlertSeverity as LocalAlertSeverity
from apps.drug_bug.fhir_client import DrugBugFHIRClient, get_fhir_client
from apps.drug_bug.matcher import assess_mismatch, should_alert


# Map local severity enum to Django AlertSeverity
SEVERITY_MAP = {
    LocalAlertSeverity.CRITICAL: AlertSeverity.HIGH,
    LocalAlertSeverity.WARNING: AlertSeverity.MEDIUM,
    LocalAlertSeverity.INFO: AlertSeverity.LOW,
}


class Command(BaseCommand):
    help = 'Monitor FHIR server for drug-bug mismatches and generate alerts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run a single check cycle and exit',
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuous monitoring loop',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=300,
            help='Poll interval in seconds for continuous mode (default: 300)',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Lookback window in hours (default: 24)',
        )
        parser.add_argument(
            '--fhir-url',
            type=str,
            help='Override FHIR server URL',
        )

    def handle(self, *args, **options):
        lookback_hours = options['hours']
        interval = options['interval']

        # Set up FHIR client
        fhir_client = DrugBugFHIRClient()
        if options.get('fhir_url'):
            from apps.drug_bug.fhir_client import HAPIFHIRClient
            fhir_client = DrugBugFHIRClient(
                fhir_client=HAPIFHIRClient(base_url=options['fhir_url'])
            )

        self.processed_cultures = set()
        self.alerts_generated = 0

        if options.get('continuous'):
            self._run_continuous(fhir_client, lookback_hours, interval)
        else:
            self._run_once(fhir_client, lookback_hours)

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal alerts generated: {self.alerts_generated}'
        ))

    def _run_once(self, fhir_client, lookback_hours):
        """Run a single check cycle."""
        self.stdout.write(
            f'\n[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] '
            f'Checking for drug-bug mismatches...'
        )

        cultures = fhir_client.get_cultures_with_susceptibilities(
            hours_back=lookback_hours
        )

        self.stdout.write(
            f'  Found {len(cultures)} culture(s) with susceptibilities '
            f'in the last {lookback_hours} hours'
        )

        cycle_alerts = 0
        for culture in cultures:
            try:
                self.stdout.write(
                    f'  Checking: {culture.organism} (Culture {culture.fhir_id[:8]}...)'
                )
                alerted = self._check_culture(fhir_client, culture)
                if alerted:
                    cycle_alerts += 1
            except Exception as e:
                self.stderr.write(
                    f'  Error processing culture {culture.fhir_id}: {e}'
                )

        if cycle_alerts:
            self.stdout.write(f'  Generated {cycle_alerts} alert(s)')
        else:
            self.stdout.write('  No mismatches detected')

    def _run_continuous(self, fhir_client, lookback_hours, interval):
        """Run continuous monitoring loop."""
        fhir_url = getattr(settings, 'FHIR_BASE_URL', 'http://localhost:8081/fhir')

        self.stdout.write('=' * 60)
        self.stdout.write('Drug-Bug Mismatch Monitor - Starting')
        self.stdout.write('=' * 60)
        self.stdout.write(f'  FHIR Server: {fhir_url}')
        self.stdout.write(f'  Poll Interval: {interval} seconds')
        self.stdout.write(f'  Lookback Window: {lookback_hours} hours')
        self.stdout.write('=' * 60)
        self.stdout.write('\nPress Ctrl+C to stop\n')

        try:
            while True:
                self._run_once(fhir_client, lookback_hours)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('\n\nMonitor stopped by user')

    def _check_culture(self, fhir_client, culture):
        """Check a single culture for drug-bug mismatches."""
        # Skip if already processed
        if culture.fhir_id in self.processed_cultures:
            return False

        # Check persistent store for duplicates
        existing = Alert.objects.filter(
            source_module='drug_bug_mismatch',
            source_id=culture.fhir_id,
        ).exists()

        if existing:
            self.processed_cultures.add(culture.fhir_id)
            return False

        self.processed_cultures.add(culture.fhir_id)

        # Skip if no susceptibility data
        if not culture.susceptibilities:
            self.stdout.write(f'  Skipping culture {culture.fhir_id}: no susceptibility data')
            return False

        if not culture.patient_id:
            self.stdout.write(f'  Warning: Culture {culture.fhir_id} has no patient reference')
            return False

        # Get patient info
        patient = fhir_client.get_patient(culture.patient_id)
        if not patient:
            self.stdout.write(f'  Warning: Patient {culture.patient_id} not found')
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

        self.alerts_generated += 1
        self.stdout.write(
            f'  Created alert {str(alert.id)[:8]}... for {patient.name} ({patient.mrn})'
        )
