"""
Management command for HAI detection monitoring.

Replaces hai_src/runner.py with Django management command interface.

Usage:
    python manage.py monitor_hai --once              # Single detection cycle
    python manage.py monitor_hai --once --classify   # Detection + classification
    python manage.py monitor_hai --once --dry-run    # Preview without saving
    python manage.py monitor_hai --continuous         # Continuous monitoring
    python manage.py monitor_hai --stats              # Show statistics
"""

import time
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.hai_detection.services import HAIDetectionService
from apps.hai_detection.models import (
    HAICandidate, HAIClassification, HAIReview,
    CandidateStatus, HAIType,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run HAI detection monitoring pipeline'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument(
            '--once', action='store_true',
            help='Run detection once and exit',
        )
        mode.add_argument(
            '--continuous', action='store_true',
            help='Run continuous monitoring loop',
        )
        mode.add_argument(
            '--stats', action='store_true',
            help='Show current statistics',
        )

        parser.add_argument(
            '--classify', action='store_true',
            help='Also classify pending candidates (with --once)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview without saving to database',
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Limit number of candidates to classify',
        )
        parser.add_argument(
            '--interval', type=int, default=None,
            help='Polling interval in seconds (with --continuous)',
        )

    def handle(self, *args, **options):
        if options['stats']:
            self._show_stats()
            return

        service = HAIDetectionService()

        if options['once']:
            if options['classify']:
                results = service.run_full_pipeline(dry_run=options['dry_run'])
                self._show_pipeline_results(results)
            else:
                results = service.run_detection(dry_run=options['dry_run'])
                self._show_detection_results(results)

        elif options['continuous']:
            hai_settings = getattr(settings, 'HAI_DETECTION', {})
            interval = options['interval'] or hai_settings.get('POLL_INTERVAL', 300)
            self.stdout.write(f"Starting continuous monitoring (interval: {interval}s)")

            while True:
                try:
                    results = service.run_detection()
                    self._show_detection_results(results)
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error in monitoring cycle: {e}"))

                self.stdout.write(f"Sleeping for {interval} seconds...")
                time.sleep(interval)

    def _show_stats(self):
        """Display current HAI detection statistics."""
        self.stdout.write(self.style.SUCCESS("\n=== HAI Detection Statistics ===\n"))

        total = HAICandidate.objects.count()
        pending = HAICandidate.objects.filter(status=CandidateStatus.PENDING).count()
        pending_review = HAICandidate.objects.filter(status=CandidateStatus.PENDING_REVIEW).count()
        confirmed = HAICandidate.objects.filter(status=CandidateStatus.CONFIRMED).count()
        rejected = HAICandidate.objects.filter(status=CandidateStatus.REJECTED).count()

        self.stdout.write(f"  Total candidates:      {total}")
        self.stdout.write(f"  Pending classification: {pending}")
        self.stdout.write(f"  Pending IP review:     {pending_review}")
        self.stdout.write(f"  Confirmed HAI:         {confirmed}")
        self.stdout.write(f"  Rejected (not HAI):    {rejected}")

        self.stdout.write("\n  By HAI Type:")
        for hai_type in HAIType:
            count = HAICandidate.objects.filter(hai_type=hai_type).count()
            conf = HAICandidate.objects.filter(hai_type=hai_type, status=CandidateStatus.CONFIRMED).count()
            self.stdout.write(f"    {hai_type.label}: {count} total, {conf} confirmed")

        reviews = HAIReview.objects.filter(reviewed=True).count()
        overrides = HAIReview.objects.filter(reviewed=True, is_override=True).count()
        self.stdout.write(f"\n  Reviews completed:     {reviews}")
        self.stdout.write(f"  Overrides:             {overrides}")
        if reviews > 0:
            accuracy = 100 * (reviews - overrides) / reviews
            self.stdout.write(f"  LLM acceptance rate:   {accuracy:.1f}%")

    def _show_detection_results(self, results):
        """Display detection results."""
        self.stdout.write(self.style.SUCCESS(
            f"\nDetection: {results['new_candidates']} new candidates"
        ))
        for hai_type, count in results.get('by_type', {}).items():
            if count > 0:
                self.stdout.write(f"  {hai_type.upper()}: {count}")
        for error in results.get('errors', []):
            self.stderr.write(self.style.ERROR(f"  Error: {error}"))

    def _show_pipeline_results(self, results):
        """Display full pipeline results."""
        self.stdout.write(self.style.SUCCESS("\n=== Pipeline Results ==="))
        self._show_detection_results(results.get('detection', {}))

        classification = results.get('classification', {})
        self.stdout.write(self.style.SUCCESS(
            f"\nClassification: {classification.get('classified', 0)} classified, "
            f"{classification.get('errors', 0)} errors"
        ))
        for decision, count in classification.get('by_decision', {}).items():
            self.stdout.write(f"  {decision}: {count}")
