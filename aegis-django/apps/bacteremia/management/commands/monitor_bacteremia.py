"""
Management command to monitor blood cultures for inadequate coverage.

Usage:
    python manage.py monitor_bacteremia --once --hours 24
    python manage.py monitor_bacteremia --continuous --interval 300
"""

import logging
import time

from django.core.management.base import BaseCommand

from apps.bacteremia.services import BacteremiaMonitorService
from apps.bacteremia.fhir_client import BacteremiaFHIRClient, HAPIFHIRClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Monitor blood cultures for inadequate antibiotic coverage'

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
        fhir_client = BacteremiaFHIRClient()
        if options.get('fhir_url'):
            fhir_client = BacteremiaFHIRClient(
                fhir_client=HAPIFHIRClient(base_url=options['fhir_url'])
            )

        service = BacteremiaMonitorService()

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
        self.stdout.write('Bacteremia Monitor - Starting')
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
