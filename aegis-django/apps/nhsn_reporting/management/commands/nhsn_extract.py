"""Batch extraction management command for NHSN AU/AR/denominator data."""

from datetime import date

from django.core.management.base import BaseCommand

from apps.nhsn_reporting.services import NHSNReportingService
from apps.nhsn_reporting.logic import config as cfg


class Command(BaseCommand):
    help = 'Extract NHSN AU/AR/denominator data from Clarity'

    def add_arguments(self, parser):
        parser.add_argument('--au', action='store_true', help='Extract AU (Antibiotic Usage) data')
        parser.add_argument('--ar', action='store_true', help='Extract AR (Antimicrobial Resistance) data')
        parser.add_argument('--denominators', action='store_true', help='Extract denominator data')
        parser.add_argument('--all', action='store_true', help='Extract all data types')
        parser.add_argument('--month', type=str, help='Month for AU/denominator (YYYY-MM)')
        parser.add_argument('--quarter', type=str, help='Quarter for AR (YYYY-Q#)')
        parser.add_argument('--location', type=str, help='Location code filter')
        parser.add_argument('--stats', action='store_true', help='Show reporting status')
        parser.add_argument('--dry-run', action='store_true', help='Extract without saving')
        parser.add_argument('--create-events', action='store_true', help='Create NHSN events from confirmed HAI candidates')

    def handle(self, *args, **options):
        if options['stats']:
            self._show_stats()
            return

        if options['create_events']:
            self._create_events()
            return

        extract_all = options['all']

        if not any([options['au'], options['ar'], options['denominators'], extract_all]):
            self.stdout.write("Specify --au, --ar, --denominators, --all, --stats, or --create-events")
            return

        if not cfg.is_clarity_configured():
            self.stdout.write(self.style.WARNING(
                "Clarity database not configured. Set NHSN_CLARITY_URL or NHSN_MOCK_CLARITY_DB."
            ))
            return

        if extract_all or options['au']:
            self._extract_au(options)
        if extract_all or options['ar']:
            self._extract_ar(options)
        if extract_all or options['denominators']:
            self._extract_denominators(options)

    def _extract_au(self, options):
        """Extract AU data."""
        self.stdout.write("Extracting AU data...")
        try:
            from apps.nhsn_reporting.logic.au_extractor import AUDataExtractor
            extractor = AUDataExtractor()
            month = options.get('month')
            location = options.get('location')

            if month:
                year, mon = month.split('-')
                start_date = date(int(year), int(mon), 1)
                if int(mon) == 12:
                    end_date = date(int(year) + 1, 1, 1)
                else:
                    end_date = date(int(year), int(mon) + 1, 1)
            else:
                start_date = date.today().replace(day=1)
                end_date = date.today()

            locations = [location] if location else None
            summary = extractor.get_monthly_summary(locations, start_date, end_date)

            total_dot = summary.get('overall_totals', {}).get('total_dot', 0)
            total_pd = summary.get('overall_totals', {}).get('total_patient_days', 0)
            rate = summary.get('overall_totals', {}).get('dot_per_1000_pd', 0)

            self.stdout.write(f"  Total DOT: {total_dot}")
            self.stdout.write(f"  Total patient-days: {total_pd}")
            self.stdout.write(f"  DOT/1000 PD: {rate}")
            self.stdout.write(f"  Locations: {len(summary.get('locations', []))}")

            if not options.get('dry_run'):
                self.stdout.write(self.style.SUCCESS("  AU extraction complete"))
            else:
                self.stdout.write("  (dry run - data not saved)")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  AU extraction failed: {e}"))

    def _extract_ar(self, options):
        """Extract AR data."""
        self.stdout.write("Extracting AR data...")
        try:
            from apps.nhsn_reporting.logic.ar_extractor import ARDataExtractor
            extractor = ARDataExtractor()
            quarter_str = options.get('quarter')
            location = options.get('location')

            if quarter_str:
                year, q = quarter_str.split('-Q')
                year, quarter = int(year), int(q)
            else:
                year = date.today().year
                quarter = (date.today().month - 1) // 3 + 1

            locations = [location] if location else None
            summary = extractor.get_quarterly_summary(locations, year, quarter)

            totals = summary.get('overall_totals', {})
            self.stdout.write(f"  Total cultures: {totals.get('total_cultures', 0)}")
            self.stdout.write(f"  First isolates: {totals.get('first_isolates', 0)}")
            self.stdout.write(f"  Unique organisms: {totals.get('unique_organisms', 0)}")
            self.stdout.write(f"  Phenotypes: {len(summary.get('phenotypes', []))}")

            if not options.get('dry_run'):
                self.stdout.write(self.style.SUCCESS("  AR extraction complete"))
            else:
                self.stdout.write("  (dry run - data not saved)")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  AR extraction failed: {e}"))

    def _extract_denominators(self, options):
        """Extract denominator data."""
        self.stdout.write("Extracting denominator data...")
        try:
            from apps.nhsn_reporting.logic.denominator import DenominatorCalculator
            calc = DenominatorCalculator()
            location = options.get('location')
            locations = [location] if location else None

            summary = calc.get_denominator_summary(locations)
            loc_count = len(summary.get('locations', []))
            self.stdout.write(f"  Locations: {loc_count}")

            for loc in summary.get('locations', []):
                totals = loc.get('totals', {})
                self.stdout.write(
                    f"    {loc['nhsn_location_code']}: "
                    f"{totals.get('patient_days', 0)} pt-days, "
                    f"{totals.get('central_line_days', 0)} CL-days, "
                    f"{totals.get('ventilator_days', 0)} vent-days"
                )

            if not options.get('dry_run'):
                self.stdout.write(self.style.SUCCESS("  Denominator extraction complete"))
            else:
                self.stdout.write("  (dry run - data not saved)")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Denominator extraction failed: {e}"))

    def _show_stats(self):
        """Show current reporting status."""
        service = NHSNReportingService()
        stats = service.get_stats()

        self.stdout.write("\n=== NHSN Reporting Status ===\n")
        self.stdout.write(f"HAI Events:     {stats['total_events']} total ({stats['unreported_events']} unreported)")
        self.stdout.write(f"AU Summaries:   {stats['au_summaries']}")
        self.stdout.write(f"AR Summaries:   {stats['ar_summaries']}")
        self.stdout.write(f"Denominators:   {stats['denominator_months']} months")

        if stats.get('events_by_type'):
            self.stdout.write("\nEvents by type:")
            for hai_type, count in stats['events_by_type'].items():
                self.stdout.write(f"  {hai_type}: {count}")

        if stats.get('latest_submission'):
            sub = stats['latest_submission']
            self.stdout.write(f"\nLast submission: {sub['action']} ({sub['type']}) on {sub['date']}")

        self.stdout.write(f"\nClarity configured: {cfg.is_clarity_configured()}")
        self.stdout.write(f"DIRECT configured:  {cfg.is_direct_configured()}")

    def _create_events(self):
        """Create NHSN events from confirmed HAI candidates."""
        service = NHSNReportingService()
        count = service.create_nhsn_events()
        self.stdout.write(self.style.SUCCESS(f"Created {count} new NHSN events"))
