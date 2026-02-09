"""Management command for batch surgical prophylaxis evaluation.

Usage:
    python manage.py monitor_prophylaxis --once
    python manage.py monitor_prophylaxis --continuous --interval 300
    python manage.py monitor_prophylaxis --stats
    python manage.py monitor_prophylaxis --once --dry-run
    python manage.py monitor_prophylaxis --once --hours 48
"""

import time
import signal

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Evaluate surgical cases for ASHP prophylaxis bundle compliance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once', action='store_true',
            help='Run a single evaluation cycle',
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
            help='Show current compliance statistics',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Evaluate without creating alerts',
        )
        parser.add_argument(
            '--hours', type=int, default=24,
            help='Lookback hours for procedure search (default: 24)',
        )

    def handle(self, *args, **options):
        from apps.surgical_prophylaxis.services import SurgicalProphylaxisService

        service = SurgicalProphylaxisService()

        if options['stats']:
            self._show_stats(service)
            return

        if options['once']:
            self._run_once(service, hours=options['hours'], dry_run=options['dry_run'])
            return

        if options['continuous']:
            self._run_continuous(service, interval=options['interval'],
                                hours=options['hours'])
            return

        self.stdout.write(self.style.WARNING(
            'Specify --once, --continuous, or --stats'
        ))

    def _run_once(self, service, hours=24, dry_run=False):
        """Run a single evaluation cycle."""
        self.stdout.write(f'Checking for surgical cases (last {hours}h)...')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no alerts will be created'))

        results = service.check_new_cases(hours_back=hours)
        self.stdout.write(self.style.SUCCESS(
            f'Processed: {len(results)} cases evaluated'
        ))

        for case, evaluation in results:
            status = 'EXCLUDED' if evaluation.excluded else (
                'COMPLIANT' if evaluation.bundle_compliant else 'NON-COMPLIANT'
            )
            self.stdout.write(
                f'  [{status}] {case.procedure_description[:50]} - '
                f'{case.patient_mrn} ({evaluation.compliance_score:.0f}%)'
            )

    def _run_continuous(self, service, interval, hours):
        """Run continuously with polling."""
        self.stdout.write(self.style.SUCCESS(
            f'Starting continuous prophylaxis monitoring (interval: {interval}s)'
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
                results = service.check_new_cases(hours_back=hours)
                if results:
                    non_compliant = sum(
                        1 for _, ev in results if not ev.bundle_compliant and not ev.excluded
                    )
                    self.stdout.write(
                        f'[{time.strftime("%H:%M:%S")}] {len(results)} cases, '
                        f'{non_compliant} non-compliant'
                    )
            except Exception as e:
                self.stderr.write(f'Error: {e}')

            for _ in range(interval):
                if not running:
                    break
                time.sleep(1)

        self.stdout.write('Monitoring stopped.')

    def _show_stats(self, service):
        """Display current compliance statistics."""
        stats = service.get_stats()

        self.stdout.write(self.style.SUCCESS('\nSurgical Prophylaxis Compliance Statistics'))
        self.stdout.write('=' * 55)

        self.stdout.write(f"\nTotal cases (30d):       {stats.get('total_cases', 0)}")
        self.stdout.write(f"Assessed:                {stats.get('assessed_cases', 0)}")
        self.stdout.write(f"Bundle compliant:        {stats.get('compliant_cases', 0)}")
        self.stdout.write(f"Non-compliant:           {stats.get('non_compliant_cases', 0)}")
        self.stdout.write(f"Excluded:                {stats.get('excluded_cases', 0)}")
        self.stdout.write(f"Compliance rate:         {stats.get('compliance_rate', 0):.1f}%")
        self.stdout.write(f"Average score:           {stats.get('avg_score', 0):.1f}%")
        self.stdout.write(f"Pending alerts:          {stats.get('pending_alerts', 0)}")

        element_rates = stats.get('element_rates', {})
        if element_rates:
            self.stdout.write('\nPer-Element Compliance:')
            for name, rate in element_rates.items():
                bar = '#' * int(rate / 5) + '-' * (20 - int(rate / 5))
                self.stdout.write(f"  {name:25s} [{bar}] {rate:.1f}%")

        by_category = stats.get('by_category', {})
        if by_category:
            self.stdout.write('\nBy Procedure Category:')
            for cat, data in sorted(by_category.items()):
                self.stdout.write(
                    f"  {cat:30s} {data['total']:3d} cases, "
                    f"{data['rate']:.1f}% compliant"
                )
