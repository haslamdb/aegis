"""Management command for ABX indication monitoring.

Usage:
    python manage.py monitor_indications --once
    python manage.py monitor_indications --continuous --interval 300
    python manage.py monitor_indications --stats
    python manage.py monitor_indications --auto-accept
"""

import time
import signal
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Monitor antibiotic orders for indication documentation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once', action='store_true',
            help='Run a single check cycle',
        )
        parser.add_argument(
            '--continuous', action='store_true',
            help='Run continuously (daemon mode)',
        )
        parser.add_argument(
            '--interval', type=int, default=300,
            help='Poll interval in seconds (default: 300)',
        )
        parser.add_argument(
            '--stats', action='store_true',
            help='Show current statistics',
        )
        parser.add_argument(
            '--auto-accept', action='store_true',
            help='Auto-accept old candidates past threshold',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be processed without saving',
        )

    def handle(self, *args, **options):
        from apps.abx_indications.services import IndicationMonitorService

        service = IndicationMonitorService()

        if options['stats']:
            self._show_stats(service)
            return

        if options['auto_accept']:
            count = service.auto_accept_old()
            self.stdout.write(self.style.SUCCESS(f'Auto-accepted {count} candidates'))
            return

        if options['once']:
            self._run_once(service, dry_run=options['dry_run'])
            return

        if options['continuous']:
            self._run_continuous(service, interval=options['interval'])
            return

        self.stdout.write(self.style.WARNING(
            'Specify --once, --continuous, --stats, or --auto-accept'
        ))

    def _run_once(self, service, dry_run=False):
        """Run a single check cycle."""
        self.stdout.write('Checking for new antibiotic orders...')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be saved'))
            # Just show what FHIR returns
            orders = service.fhir_client.get_recent_medication_requests()
            self.stdout.write(f'Found {len(orders)} active medication orders')
            for order in orders:
                from apps.abx_indications.models import IndicationCandidate
                already = IndicationCandidate.objects.filter(
                    medication_request_id=order['fhir_id'],
                ).exists()
                status = 'SKIP (already tracked)' if already else 'NEW'
                self.stdout.write(
                    f"  [{status}] {order['medication_name']} - "
                    f"Patient {order['patient_id']}"
                )
            return

        results = service.check_new_alerts()
        self.stdout.write(self.style.SUCCESS(
            f'Processed: {len(results)} new alerts created'
        ))

        for candidate, alert in results:
            self.stdout.write(
                f'  {alert.get_alert_type_display()}: '
                f'{candidate.medication_name} - {candidate.patient_mrn} '
                f'({candidate.clinical_syndrome_display})'
            )

    def _run_continuous(self, service, interval):
        """Run continuously with polling."""
        self.stdout.write(self.style.SUCCESS(
            f'Starting continuous monitoring (interval: {interval}s)'
        ))

        running = True

        def signal_handler(sig, frame):
            nonlocal running
            self.stdout.write('\nShutting down...')
            running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while running:
            try:
                results = service.check_new_alerts()
                if results:
                    self.stdout.write(f'[{time.strftime("%H:%M:%S")}] {len(results)} new alerts')

                # Auto-accept old candidates
                accepted = service.auto_accept_old()
                if accepted:
                    self.stdout.write(f'[{time.strftime("%H:%M:%S")}] Auto-accepted {accepted}')

            except Exception as e:
                self.stderr.write(f'Error: {e}')

            # Sleep in small increments for responsiveness
            for _ in range(interval):
                if not running:
                    break
                time.sleep(1)

        self.stdout.write('Monitoring stopped.')

    def _show_stats(self, service):
        """Display current statistics."""
        stats = service.get_stats()

        self.stdout.write(self.style.SUCCESS('\nABX Indication Monitoring Statistics'))
        self.stdout.write('=' * 50)

        self.stdout.write(f"\nTotal candidates:     {stats.get('total_candidates', 0)}")
        self.stdout.write(f"Active (pending):     {stats.get('pending_count', 0)}")
        self.stdout.write(f"Active (alerted):     {stats.get('alerted_count', 0)}")
        self.stdout.write(f"Reviewed today:       {stats.get('reviewed_today', 0)}")
        self.stdout.write(f"Auto-accepted:        {stats.get('auto_accepted', 0)}")
        self.stdout.write(f"Active alerts:        {stats.get('active_alerts', 0)}")

        red_flags = stats.get('red_flags', {})
        if any(red_flags.values()):
            self.stdout.write(self.style.WARNING('\nRed Flags:'))
            for flag, count in red_flags.items():
                if count:
                    self.stdout.write(f"  {flag}: {count}")

        by_category = stats.get('by_category', {})
        if by_category:
            self.stdout.write('\nBy Syndrome Category:')
            for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
                self.stdout.write(f"  {cat}: {count}")

        by_agent = stats.get('by_agent_category', {})
        if by_agent:
            self.stdout.write('\nBy Agent Category:')
            for cat, count in sorted(by_agent.items(), key=lambda x: -x[1]):
                self.stdout.write(f"  {cat}: {count}")

        by_med = stats.get('by_medication', {})
        if by_med:
            self.stdout.write('\nBy Medication:')
            for med, count in sorted(by_med.items(), key=lambda x: -x[1])[:10]:
                self.stdout.write(f"  {med}: {count}")
