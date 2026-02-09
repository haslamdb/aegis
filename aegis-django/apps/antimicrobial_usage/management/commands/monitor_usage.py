"""
Management command for broad-spectrum antibiotic usage monitoring.

Replaces au_alerts_src/runner.py (broad-spectrum only) with Django management command.

Usage:
    python manage.py monitor_usage --once              # Single check cycle
    python manage.py monitor_usage --once --dry-run    # Show what would be alerted
    python manage.py monitor_usage --continuous         # Daemon mode
    python manage.py monitor_usage --stats              # Show current statistics
"""

import time
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.antimicrobial_usage.services import BroadSpectrumMonitorService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run broad-spectrum antibiotic usage monitoring'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument(
            '--once', action='store_true',
            help='Run monitoring once and exit',
        )
        mode.add_argument(
            '--continuous', action='store_true',
            help='Run continuous monitoring loop',
        )
        mode.add_argument(
            '--stats', action='store_true',
            help='Show current alert statistics',
        )

        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be alerted without creating alerts (with --once)',
        )
        parser.add_argument(
            '--interval', type=int, default=None,
            help='Poll interval in seconds (with --continuous)',
        )

    def handle(self, *args, **options):
        if options['stats']:
            self._show_stats()
            return

        if options['once']:
            if options['dry_run']:
                self._dry_run()
            else:
                self._run_once()

        elif options['continuous']:
            conf = getattr(settings, 'ANTIMICROBIAL_USAGE', {})
            interval = options['interval'] or conf.get('POLL_INTERVAL_SECONDS', 300)
            self.stdout.write(f"Starting continuous monitoring (interval: {interval}s)")

            while True:
                try:
                    self._run_once()
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error in monitoring cycle: {e}"))

                self.stdout.write(f"Sleeping for {interval} seconds...")
                time.sleep(interval)

    def _run_once(self):
        """Run a single monitoring check cycle."""
        service = BroadSpectrumMonitorService()
        new_alerts = service.check_new_alerts()

        if not new_alerts:
            self.stdout.write("No new alerts.")
            return

        self.stdout.write(self.style.SUCCESS(f"\nCreated {len(new_alerts)} new alert(s):"))
        for assessment, alert in new_alerts:
            self.stdout.write(
                f"  [{assessment.severity.upper()}] "
                f"{assessment.medication.medication_name} - "
                f"{assessment.patient.name} (MRN: {assessment.patient.mrn}) - "
                f"{assessment.duration_hours:.1f}h "
                f"(Alert: {alert.id})"
            )

    def _dry_run(self):
        """Show what would be alerted without creating alerts."""
        service = BroadSpectrumMonitorService()
        assessments = service.check_all_patients()

        if not assessments:
            self.stdout.write("No patients exceeding threshold.")
            return

        self.stdout.write(self.style.SUCCESS(
            f"\n[DRY RUN] {len(assessments)} order(s) exceeding threshold:"
        ))
        for assessment in assessments:
            self.stdout.write(
                f"  [{assessment.severity.upper()}] "
                f"{assessment.medication.medication_name} - "
                f"{assessment.patient.name} (MRN: {assessment.patient.mrn}) - "
                f"{assessment.duration_hours:.1f}h ({assessment.duration_hours / 24:.1f} days)"
            )
            self.stdout.write(f"    {assessment.recommendation}")

    def _show_stats(self):
        """Display current monitoring statistics."""
        self.stdout.write(self.style.SUCCESS("\n=== Antimicrobial Usage Monitoring Statistics ===\n"))

        service = BroadSpectrumMonitorService()
        stats = service.get_stats()

        self.stdout.write(f"  Active alerts:     {stats['active_count']}")
        self.stdout.write(f"    Critical:        {stats['critical_count']}")
        self.stdout.write(f"    High:            {stats['high_count']}")
        self.stdout.write(f"  Resolved today:    {stats['resolved_today']}")

        if stats['by_medication']:
            self.stdout.write("\n  By Medication:")
            for med, count in stats['by_medication'].items():
                self.stdout.write(f"    {med}: {count}")

        conf = getattr(settings, 'ANTIMICROBIAL_USAGE', {})
        self.stdout.write(f"\n  Threshold: {conf.get('ALERT_THRESHOLD_HOURS', 72)} hours")
        monitored = conf.get('MONITORED_MEDICATIONS', {})
        self.stdout.write(f"  Monitored medications: {list(monitored.values())}")
