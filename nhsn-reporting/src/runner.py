#!/usr/bin/env python3
"""CLI runner for NHSN HAI candidate detection.

Usage:
    python -m nhsn-reporting.src.runner --once
    python -m nhsn-reporting.src.runner --once --dry-run
    python -m nhsn-reporting.src.runner  # Continuous mode
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta

from .config import Config
from .monitor import NHSNMonitor
from .models import HAIType


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from HTTP libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def run_once(
    monitor: NHSNMonitor,
    dry_run: bool = False,
    lookback_hours: int | None = None,
) -> int:
    """Run a single detection cycle.

    Args:
        monitor: The monitor instance.
        dry_run: If True, don't persist anything.
        lookback_hours: Override lookback period.

    Returns:
        Number of candidates found.
    """
    if lookback_hours:
        monitor.lookback_hours = lookback_hours

    return monitor.run_once(dry_run=dry_run)


def run_daemon(monitor: NHSNMonitor, interval: int | None = None) -> None:
    """Run continuous monitoring."""
    monitor.run_continuous(interval_seconds=interval)


def show_stats(monitor: NHSNMonitor) -> None:
    """Display current statistics."""
    stats = monitor.get_stats()

    print("\n=== NHSN Reporting Statistics ===")
    print(f"Total candidates:         {stats['total_candidates']}")
    print(f"Pending classification:   {stats['pending_classification']}")
    print(f"Pending IP review:        {stats['pending_review']}")
    print(f"Confirmed HAI:            {stats['confirmed_hai']}")
    print(f"Total NHSN events:        {stats['total_events']}")
    print(f"Unreported events:        {stats['unreported_events']}")
    print()


def show_recent(monitor: NHSNMonitor, limit: int = 10) -> None:
    """Display recent candidates."""
    candidates = monitor.get_recent_candidates(limit=limit)

    print(f"\n=== Recent CLABSI Candidates (last {limit}) ===")
    print("-" * 80)

    if not candidates:
        print("No candidates found.")
        return

    for c in candidates:
        status_icon = "✓" if c.meets_initial_criteria else "✗"
        print(
            f"{status_icon} {c.patient.mrn:12s} | "
            f"{c.culture.organism or 'Pending':30s} | "
            f"Device days: {c.device_days_at_culture or '?':>2} | "
            f"{c.status.value:15s} | "
            f"{c.created_at.strftime('%Y-%m-%d %H:%M')}"
        )

    print("-" * 80)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NHSN HAI candidate detection and classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Single run with dry-run (no database writes)
    python -m nhsn_reporting.src.runner --once --dry-run

    # Single run, process all cultures from last 48 hours
    python -m nhsn_reporting.src.runner --once --lookback 48

    # Continuous monitoring mode
    python -m nhsn_reporting.src.runner

    # Show current statistics
    python -m nhsn_reporting.src.runner --stats

    # Show recent candidates
    python -m nhsn_reporting.src.runner --recent
        """,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (default: continuous mode)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save candidates or send alerts (for testing)",
    )

    parser.add_argument(
        "--lookback",
        type=int,
        default=None,
        help=f"Hours to look back for new cultures (default: {Config.LOOKBACK_HOURS})",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help=f"Polling interval in seconds (default: {Config.POLL_INTERVAL})",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current statistics and exit",
    )

    parser.add_argument(
        "--recent",
        type=int,
        nargs="?",
        const=10,
        default=None,
        help="Show recent candidates (default: 10)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help=f"Path to NHSN database (default: {Config.NHSN_DB_PATH})",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger(__name__)

    # Override database path if specified
    if args.db_path:
        Config.NHSN_DB_PATH = args.db_path

    # Create monitor
    try:
        monitor = NHSNMonitor(lookback_hours=args.lookback)
    except Exception as e:
        logger.error(f"Failed to initialize monitor: {e}")
        return 1

    # Handle stats/recent commands
    if args.stats:
        show_stats(monitor)
        return 0

    if args.recent is not None:
        show_recent(monitor, args.recent)
        return 0

    # Run detection
    if args.once:
        logger.info("Running single detection cycle...")
        try:
            count = run_once(
                monitor,
                dry_run=args.dry_run,
                lookback_hours=args.lookback,
            )
            logger.info(f"Completed: {count} new candidates identified")
            return 0
        except Exception as e:
            logger.error(f"Detection failed: {e}", exc_info=True)
            return 1
    else:
        logger.info("Starting continuous monitoring mode...")
        try:
            run_daemon(monitor, interval=args.interval)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            return 0
        except Exception as e:
            logger.error(f"Monitor failed: {e}", exc_info=True)
            return 1


if __name__ == "__main__":
    sys.exit(main())
