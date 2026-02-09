"""Management command to run the real-time surgical prophylaxis monitoring daemon.

Starts the HL7 MLLP listener, FHIR appointment polling, and escalation engine.

Usage:
    python manage.py run_realtime_prophylaxis
    python manage.py run_realtime_prophylaxis --debug
"""

import asyncio
import logging

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run real-time surgical prophylaxis monitoring (HL7 listener + escalation engine)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug', action='store_true',
            help='Enable debug logging',
        )

    def handle(self, *args, **options):
        if options['debug']:
            logging.getLogger('apps.surgical_prophylaxis').setLevel(logging.DEBUG)

        from apps.surgical_prophylaxis.realtime.service import RealtimeProphylaxisService

        self.stdout.write(self.style.SUCCESS(
            'Starting real-time surgical prophylaxis monitoring...'
        ))

        service = RealtimeProphylaxisService()

        try:
            asyncio.run(service.run())
        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')

        self.stdout.write('Real-time monitoring stopped.')
