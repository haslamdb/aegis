"""
Management command for outbreak detection.

Replaces outbreak_src/runner.py with Django management command interface.

Usage:
    python manage.py detect_outbreaks --once              # Single detection cycle
    python manage.py detect_outbreaks --once --days 30    # Custom lookback
    python manage.py detect_outbreaks --continuous         # Continuous monitoring
    python manage.py detect_outbreaks --stats              # Show statistics
"""

import time
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.outbreak_detection.services import OutbreakDetectionService
from apps.outbreak_detection.models import (
    OutbreakCluster, ClusterStatus, ClusterSeverity,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run outbreak detection monitoring'

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
            '--days', type=int, default=None,
            help='Days to look back (default: from settings)',
        )
        parser.add_argument(
            '--interval', type=int, default=None,
            help='Poll interval in seconds (with --continuous)',
        )

    def handle(self, *args, **options):
        if options['stats']:
            self._show_stats()
            return

        service = OutbreakDetectionService()

        if options['once']:
            results = service.run_detection(days=options['days'])
            self._show_results(results)

        elif options['continuous']:
            conf = getattr(settings, 'OUTBREAK_DETECTION', {})
            interval = options['interval'] or conf.get('POLL_INTERVAL_MINUTES', 30) * 60
            self.stdout.write(f"Starting continuous monitoring (interval: {interval}s)")

            while True:
                try:
                    results = service.run_detection(days=options['days'])
                    self._show_results(results)
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error in detection cycle: {e}"))

                self.stdout.write(f"Sleeping for {interval} seconds...")
                time.sleep(interval)

    def _show_stats(self):
        """Display current outbreak detection statistics."""
        self.stdout.write(self.style.SUCCESS("\n=== Outbreak Detection Statistics ===\n"))

        service = OutbreakDetectionService()
        stats = service.get_stats()

        self.stdout.write(f"  Active clusters:        {stats['active_clusters']}")
        self.stdout.write(f"  Under investigation:    {stats['investigating_clusters']}")
        self.stdout.write(f"  Resolved clusters:      {stats['resolved_clusters']}")
        self.stdout.write(f"  Pending alerts:         {stats['pending_alerts']}")

        if stats['by_severity']:
            self.stdout.write("\n  By Severity:")
            for sev, count in stats['by_severity'].items():
                self.stdout.write(f"    {sev.capitalize()}: {count}")

        if stats['by_type']:
            self.stdout.write("\n  By Infection Type:")
            for itype, count in stats['by_type'].items():
                self.stdout.write(f"    {itype.upper()}: {count}")

        # Show active clusters
        active = OutbreakCluster.objects.filter(
            status__in=[ClusterStatus.ACTIVE, ClusterStatus.INVESTIGATING],
        ).order_by('-severity')

        if active.exists():
            self.stdout.write(self.style.SUCCESS("\n  Active Clusters:"))
            for cluster in active:
                self.stdout.write(
                    f"    [{cluster.get_severity_display()}] "
                    f"{cluster.infection_type.upper()} in {cluster.unit} - "
                    f"{cluster.case_count} cases ({cluster.get_status_display()})"
                )

    def _show_results(self, results):
        """Display detection results."""
        self.stdout.write(self.style.SUCCESS(
            f"\nDetection: {results['cases_analyzed']} cases analyzed, "
            f"{results['new_cases_processed']} new"
        ))
        if results['clusters_formed']:
            self.stdout.write(f"  New clusters: {results['clusters_formed']}")
        if results['clusters_updated']:
            self.stdout.write(f"  Clusters updated: {results['clusters_updated']}")
        if results['alerts_created']:
            self.stdout.write(f"  Alerts created: {results['alerts_created']}")
