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

from django.core.management.base import BaseCommand

from apps.mdro.services import MDROMonitorService

logger = logging.getLogger(__name__)


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
        service = MDROMonitorService()

        if options['continuous']:
            self._run_continuous(service, options['hours'], options['interval'])
        else:
            # Default to --once behavior
            result = service.run_detection(hours_back=options['hours'])
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

    def _run_continuous(self, service, hours_back, interval_minutes):
        """Run continuous monitoring loop."""
        self.stdout.write(
            f"Starting MDRO monitor (polling every {interval_minutes} minutes)"
        )

        while True:
            try:
                result = service.run_detection(hours_back=hours_back)
                self.stdout.write(
                    f"Polling complete: {result['new_mdro_cases']} new cases"
                )
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                self.stderr.write(self.style.ERROR(f"Error: {e}"))

            time.sleep(interval_minutes * 60)
