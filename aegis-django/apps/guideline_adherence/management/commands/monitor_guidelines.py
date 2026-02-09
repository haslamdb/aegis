"""Management command for guideline adherence monitoring.

Three monitoring modes:
1. Trigger monitoring - Poll FHIR for new diagnoses matching bundle triggers
2. Episode monitoring - Check active episodes for deadline violations
3. Adherence monitoring - Run element checkers, update adherence percentages

Usage:
    python manage.py monitor_guidelines --once
    python manage.py monitor_guidelines --trigger --once
    python manage.py monitor_guidelines --episodes --once
    python manage.py monitor_guidelines --adherence --once
    python manage.py monitor_guidelines --all --once
    python manage.py monitor_guidelines --continuous --interval 300
    python manage.py monitor_guidelines --stats
    python manage.py monitor_guidelines --dry-run --once
    python manage.py monitor_guidelines --bundle sepsis_peds_2024 --once
"""

import time
import signal

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Monitor guideline adherence bundles (triggers, episodes, adherence)'

    def add_arguments(self, parser):
        # Mode selection
        mode_group = parser.add_argument_group('monitoring modes')
        mode_group.add_argument(
            '--trigger', action='store_true',
            help='Mode 1: Poll for new bundle triggers',
        )
        mode_group.add_argument(
            '--episodes', action='store_true',
            help='Mode 2: Check active episodes for deadline violations',
        )
        mode_group.add_argument(
            '--adherence', action='store_true',
            help='Mode 3: Run element checkers, update adherence percentages',
        )
        mode_group.add_argument(
            '--all', action='store_true',
            help='Run all 3 modes (default if no mode specified)',
        )

        # Run modes
        run_group = parser.add_argument_group('run modes')
        run_group.add_argument(
            '--once', action='store_true',
            help='Run a single check cycle (default)',
        )
        run_group.add_argument(
            '--continuous', action='store_true',
            help='Run continuously (daemon mode)',
        )
        run_group.add_argument(
            '--interval', type=int, default=300,
            help='Poll interval in seconds for continuous mode (default: 300)',
        )

        # Filters and options
        parser.add_argument(
            '--stats', action='store_true',
            help='Show current statistics only',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Check without creating alerts or updating records',
        )
        parser.add_argument(
            '--bundle', type=str, default=None,
            help='Filter to a specific bundle ID (e.g., sepsis_peds_2024)',
        )

    def handle(self, *args, **options):
        from apps.guideline_adherence.services import GuidelineAdherenceService

        self.service = GuidelineAdherenceService()

        if options['stats']:
            self._show_stats()
            return

        # Determine which modes to run
        run_trigger = options['trigger']
        run_episodes = options['episodes']
        run_adherence = options['adherence']
        run_all = options['all']

        # If no specific mode selected, default to --all
        if not any([run_trigger, run_episodes, run_adherence, run_all]):
            run_all = True

        if run_all:
            run_trigger = True
            run_episodes = True
            run_adherence = True

        dry_run = options['dry_run']
        bundle_id = options['bundle']

        if options['continuous']:
            self._run_continuous(
                run_trigger=run_trigger,
                run_episodes=run_episodes,
                run_adherence=run_adherence,
                interval=options['interval'],
                dry_run=dry_run,
                bundle_id=bundle_id,
            )
        else:
            # Default to --once behavior
            self._run_once(
                run_trigger=run_trigger,
                run_episodes=run_episodes,
                run_adherence=run_adherence,
                dry_run=dry_run,
                bundle_id=bundle_id,
            )

    def _run_once(self, run_trigger, run_episodes, run_adherence,
                  dry_run=False, bundle_id=None):
        """Run a single check cycle."""
        self.stdout.write(self.style.HTTP_INFO(
            '\nGuideline Adherence Monitor'
        ))
        self.stdout.write('=' * 50)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be saved'))

        # Mode 1: Trigger monitoring
        if run_trigger:
            self._run_triggers(dry_run=dry_run)

        # Mode 2: Episode monitoring
        if run_episodes:
            self._run_episodes(dry_run=dry_run)

        # Mode 3: Adherence monitoring
        if run_adherence:
            self._run_adherence(dry_run=dry_run, bundle_id=bundle_id)

        # Show summary
        self._show_summary()

    def _run_triggers(self, dry_run=False):
        """Mode 1: Poll for new bundle triggers."""
        self.stdout.write(self.style.HTTP_INFO(
            '\n[1/3] Checking for new bundle triggers...'
        ))

        if dry_run:
            from apps.guideline_adherence.bundles import get_enabled_bundles
            bundles = get_enabled_bundles()
            self.stdout.write(f'  Enabled bundles: {len(bundles)}')
            for bundle in bundles:
                triggers = len(bundle.trigger_criteria)
                self.stdout.write(
                    f'    {bundle.bundle_id}: {bundle.name} '
                    f'({triggers} trigger{"s" if triggers != 1 else ""})'
                )
            return

        new_episodes = self.service.check_triggers()
        if new_episodes:
            self.stdout.write(self.style.SUCCESS(
                f'  Created {len(new_episodes)} new episodes'
            ))
            for episode in new_episodes:
                self.stdout.write(
                    f'    {episode.bundle_name} - '
                    f'{episode.patient_name} ({episode.patient_mrn}) '
                    f'@ {episode.patient_unit or "unknown unit"}'
                )
        else:
            self.stdout.write('  No new triggers found')

    def _run_episodes(self, dry_run=False):
        """Mode 2: Check active episodes for deadline violations."""
        self.stdout.write(self.style.HTTP_INFO(
            '\n[2/3] Checking active episodes for violations...'
        ))

        from apps.guideline_adherence.models import BundleEpisode, EpisodeStatus

        active_count = BundleEpisode.objects.filter(
            status=EpisodeStatus.ACTIVE,
        ).count()
        self.stdout.write(f'  Active episodes: {active_count}')

        if active_count == 0:
            self.stdout.write('  No active episodes to check')
            return

        alerts_created = self.service.check_episodes(dry_run=dry_run)
        if alerts_created:
            self.stdout.write(self.style.WARNING(
                f'  {len(alerts_created)} deadline violation alerts created'
            ))
            for alert in alerts_created:
                self.stdout.write(
                    f'    [{alert.get_severity_display()}] {alert.title}'
                )
        else:
            self.stdout.write(self.style.SUCCESS(
                '  No deadline violations found'
            ))

    def _run_adherence(self, dry_run=False, bundle_id=None):
        """Mode 3: Run element checkers, update adherence."""
        self.stdout.write(self.style.HTTP_INFO(
            '\n[3/3] Running adherence checks...'
        ))

        if bundle_id:
            self.stdout.write(f'  Filtering to bundle: {bundle_id}')

        results = self.service.check_adherence(
            bundle_id=bundle_id, dry_run=dry_run,
        )

        episodes_checked = results.get('episodes_checked', 0)
        elements_updated = results.get('elements_updated', 0)

        if episodes_checked > 0:
            self.stdout.write(self.style.SUCCESS(
                f'  Checked {episodes_checked} episodes, '
                f'{elements_updated} elements updated'
            ))
        else:
            self.stdout.write('  No episodes to check')

    def _run_continuous(self, run_trigger, run_episodes, run_adherence,
                        interval, dry_run=False, bundle_id=None):
        """Run continuously with polling."""
        modes = []
        if run_trigger:
            modes.append('triggers')
        if run_episodes:
            modes.append('episodes')
        if run_adherence:
            modes.append('adherence')

        self.stdout.write(self.style.SUCCESS(
            f'Starting continuous monitoring '
            f'(modes: {", ".join(modes)}, interval: {interval}s)'
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN mode'))

        running = True

        def signal_handler(sig, frame):
            nonlocal running
            self.stdout.write('\nShutting down...')
            running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        cycle = 0
        while running:
            cycle += 1
            timestamp = time.strftime('%H:%M:%S')

            try:
                self.stdout.write(f'\n[{timestamp}] Cycle {cycle}')

                if run_trigger and not dry_run:
                    new_episodes = self.service.check_triggers()
                    if new_episodes:
                        self.stdout.write(
                            f'  [triggers] {len(new_episodes)} new episodes'
                        )

                if run_episodes:
                    alerts = self.service.check_episodes(dry_run=dry_run)
                    if alerts:
                        self.stdout.write(self.style.WARNING(
                            f'  [episodes] {len(alerts)} violation alerts'
                        ))

                if run_adherence:
                    results = self.service.check_adherence(
                        bundle_id=bundle_id, dry_run=dry_run,
                    )
                    updated = results.get('elements_updated', 0)
                    if updated:
                        self.stdout.write(
                            f'  [adherence] {updated} elements updated'
                        )

            except Exception as e:
                self.stderr.write(f'  Error in cycle {cycle}: {e}')

            # Sleep in small increments for responsiveness
            for _ in range(interval):
                if not running:
                    break
                time.sleep(1)

        self.stdout.write('Monitoring stopped.')

    def _show_summary(self):
        """Show a brief post-run summary."""
        from apps.guideline_adherence.models import (
            BundleEpisode, EpisodeStatus, AdherenceLevel,
        )

        self.stdout.write(self.style.HTTP_INFO('\nSummary'))
        self.stdout.write('-' * 50)

        active = BundleEpisode.objects.filter(status=EpisodeStatus.ACTIVE).count()
        complete = BundleEpisode.objects.filter(status=EpisodeStatus.COMPLETE).count()
        closed = BundleEpisode.objects.filter(status=EpisodeStatus.CLOSED).count()

        self.stdout.write(f'  Active episodes:    {active}')
        self.stdout.write(f'  Completed episodes: {complete}')
        self.stdout.write(f'  Closed episodes:    {closed}')

        if complete > 0:
            full = BundleEpisode.objects.filter(
                status=EpisodeStatus.COMPLETE,
                adherence_level=AdherenceLevel.FULL,
            ).count()
            partial = BundleEpisode.objects.filter(
                status=EpisodeStatus.COMPLETE,
                adherence_level=AdherenceLevel.PARTIAL,
            ).count()
            low = BundleEpisode.objects.filter(
                status=EpisodeStatus.COMPLETE,
                adherence_level=AdherenceLevel.LOW,
            ).count()
            pct = round((full / complete * 100), 1) if complete > 0 else 0
            self.stdout.write(
                f'  Full adherence:     {full}/{complete} ({pct}%)'
            )
            self.stdout.write(f'  Partial adherence:  {partial}')
            self.stdout.write(f'  Low adherence:      {low}')

    def _show_stats(self):
        """Display comprehensive statistics."""
        stats = self.service.get_stats()

        self.stdout.write(self.style.SUCCESS(
            '\nGuideline Adherence Statistics'
        ))
        self.stdout.write('=' * 60)

        self.stdout.write(f"\nActive episodes:        {stats.get('active_episodes', 0)}")
        self.stdout.write(f"Completed (30 days):    {stats.get('completed_30d', 0)}")
        self.stdout.write(f"Full adherence (30d):   {stats.get('full_adherence', 0)}")

        overall = stats.get('overall_compliance', 0)
        if overall >= 80:
            style = self.style.SUCCESS
        elif overall >= 50:
            style = self.style.WARNING
        else:
            style = self.style.ERROR
        self.stdout.write(style(
            f"Overall compliance:     {overall}%"
        ))

        self.stdout.write(f"Active alerts:          {stats.get('active_alerts', 0)}")

        # Per-bundle breakdown
        bundle_stats = stats.get('bundle_stats', [])
        if bundle_stats:
            self.stdout.write(self.style.HTTP_INFO('\nPer-Bundle Breakdown'))
            self.stdout.write('-' * 60)
            self.stdout.write(
                f"  {'Bundle':<35} {'Active':>6} {'Done':>6} {'Compl%':>7}"
            )
            self.stdout.write('  ' + '-' * 56)
            for bs in bundle_stats:
                name = bs['bundle_name'][:34]
                active = bs.get('active_count', 0)
                total = bs.get('total', 0)
                pct = bs.get('compliance_pct', 0)

                if pct >= 80:
                    pct_str = f"{pct:>6.1f}%"
                elif pct >= 50:
                    pct_str = f"{pct:>6.1f}%"
                else:
                    pct_str = f"{pct:>6.1f}%"

                self.stdout.write(
                    f"  {name:<35} {active:>6} {total:>6} {pct_str}"
                )

        # Monitor state
        from apps.guideline_adherence.models import MonitorState

        states = MonitorState.objects.all()
        if states.exists():
            self.stdout.write(self.style.HTTP_INFO('\nMonitor State'))
            self.stdout.write('-' * 60)
            for state in states:
                last_poll = (
                    state.last_poll_time.strftime('%Y-%m-%d %H:%M:%S')
                    if state.last_poll_time else 'never'
                )
                last_count = state.state_data.get('last_count', 'n/a')
                self.stdout.write(
                    f"  {state.monitor_type:<15} "
                    f"last poll: {last_poll}  "
                    f"status: {state.last_run_status or 'n/a'}  "
                    f"count: {last_count}"
                )
