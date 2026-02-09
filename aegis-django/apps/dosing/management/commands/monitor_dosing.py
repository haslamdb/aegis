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

from django.core.management.base import BaseCommand

from apps.dosing.services import DosingMonitorService

logger = logging.getLogger(__name__)


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
        service = DosingMonitorService()

        if options['continuous']:
            self.stdout.write(self.style.SUCCESS(
                f'Starting continuous dosing monitoring (interval: {options["interval"]}s)'
            ))
            while True:
                try:
                    result = service.run_check(options['hours'])
                    self.stdout.write(
                        f'Check complete: {result["total_flags"]} flags, '
                        f'{result["alerts_created"]} alerts created'
                    )
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'Error during check: {e}'))
                    logger.exception('Error during dosing monitoring check')
                time.sleep(options['interval'])
        else:
            result = service.run_check(options['hours'])
            self.stdout.write(self.style.SUCCESS(
                f'Check complete: {result["total_flags"]} flags found, '
                f'{result["alerts_created"]} alerts created, '
                f'{result["alerts_skipped"]} duplicates skipped'
            ))
