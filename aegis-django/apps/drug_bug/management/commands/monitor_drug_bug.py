"""
Management command to monitor for drug-bug mismatches.

Replaces drugbug_src/monitor.py and runner.py.

Usage:
    python manage.py monitor_drug_bug --once --hours 24
    python manage.py monitor_drug_bug --continuous --interval 300
"""

import logging
import time

from django.core.management.base import BaseCommand

from apps.drug_bug.services import DrugBugMonitorService
from apps.drug_bug.fhir_client import DrugBugFHIRClient, HAPIFHIRClient

logger = logging.getLogger(__name__)


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
            fhir_client = DrugBugFHIRClient(
                fhir_client=HAPIFHIRClient(base_url=options['fhir_url'])
            )

        service = DrugBugMonitorService()

        if options.get('continuous'):
            self._run_continuous(service, fhir_client, lookback_hours, interval)
        else:
            result = service.run_detection(
                hours_back=lookback_hours,
                fhir_client=fhir_client,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Check complete: {result['cultures_checked']} cultures checked, "
                f"{result['alerts_created']} alerts created"
            ))

    def _run_continuous(self, service, fhir_client, lookback_hours, interval):
        """Run continuous monitoring loop."""
        self.stdout.write('=' * 60)
        self.stdout.write('Drug-Bug Mismatch Monitor - Starting')
        self.stdout.write(f'  Poll Interval: {interval} seconds')
        self.stdout.write(f'  Lookback Window: {lookback_hours} hours')
        self.stdout.write('=' * 60)

        try:
            while True:
                result = service.run_detection(
                    hours_back=lookback_hours,
                    fhir_client=fhir_client,
                )
                self.stdout.write(
                    f"Cycle complete: {result['alerts_created']} alerts created"
                )
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('\n\nMonitor stopped by user')
