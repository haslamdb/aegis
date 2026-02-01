#!/usr/bin/env python3
"""CLI entry point for MDRO Surveillance Monitor.

Usage:
    # Run once and exit
    python -m mdro_src.runner --once

    # Run with custom lookback
    python -m mdro_src.runner --once --hours 48

    # Run continuously
    python -m mdro_src.runner --continuous

    # Run with custom interval
    python -m mdro_src.runner --continuous --interval 30

    # Debug mode
    python -m mdro_src.runner --once --debug
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .config import config
from .monitor import MDROMonitor


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MDRO Surveillance Monitor - Detect multi-drug resistant organisms from cultures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (default behavior)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run in continuous monitoring mode",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help=f"Poll interval in minutes for continuous mode (default: {config.POLL_INTERVAL_MINUTES})",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help=f"Hours to look back for cultures (default: {config.LOOKBACK_HOURS})",
    )
    parser.add_argument(
        "--fhir-url",
        type=str,
        default=None,
        help=f"FHIR server URL (default: {config.FHIR_BASE_URL})",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Database path (default from config)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Override config if arguments provided
    if args.fhir_url:
        config.FHIR_BASE_URL = args.fhir_url
    if args.db_path:
        config.DB_PATH = args.db_path

    # Create monitor
    monitor = MDROMonitor()

    # Run
    if args.continuous:
        interval = args.interval or config.POLL_INTERVAL_MINUTES
        print(f"Starting MDRO monitor in continuous mode (interval: {interval} min)")
        print(f"FHIR Server: {config.FHIR_BASE_URL}")
        print(f"Database: {config.DB_PATH}")
        print("-" * 60)
        monitor.run_continuous(interval_minutes=interval)
    else:
        # Default to run once
        hours = args.hours or config.LOOKBACK_HOURS
        print(f"Running MDRO monitor (lookback: {hours} hours)")
        print(f"FHIR Server: {config.FHIR_BASE_URL}")
        print(f"Database: {config.DB_PATH}")
        print("-" * 60)

        result = monitor.run_once(hours_back=hours)

        print(f"\nResults:")
        print(f"  Cultures checked:     {result['cultures_checked']}")
        print(f"  New MDRO cases:       {result['new_mdro_cases']}")
        print(f"  Already processed:    {result['skipped_already_processed']}")
        print(f"  Not MDRO:             {result['skipped_not_mdro']}")

        if result['errors']:
            print(f"  Errors:               {len(result['errors'])}")
            for err in result['errors'][:5]:
                print(f"    - {err}")

        print(f"\nCompleted at: {result['completed_at']}")


if __name__ == "__main__":
    main()
