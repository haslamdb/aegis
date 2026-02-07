#!/usr/bin/env python3
"""CLI entry point for dosing verification monitor.

Usage:
    # Single pass
    python -m src.runner --once

    # Continuous monitoring (every 15 minutes)
    python -m src.runner --continuous

    # Continuous with custom interval
    python -m src.runner --continuous --interval 30

    # Dry run (no notifications)
    python -m src.runner --once --dry-run

    # Check specific patient
    python -m src.runner --patient MRN12345

    # Custom lookback period
    python -m src.runner --once --lookback 48
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.monitor import DosingVerificationMonitor


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    parser = argparse.ArgumentParser(
        description="Dosing Verification Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--once", action="store_true", help="Run single scan and exit")
    mode_group.add_argument("--continuous", action="store_true", help="Run continuous monitoring")
    mode_group.add_argument("--patient", metavar="MRN", help="Check specific patient MRN")

    # Options
    parser.add_argument("--lookback", type=int, default=24, help="Hours to look back for orders (default: 24)")
    parser.add_argument("--interval", type=int, default=15, help="Minutes between scans (continuous mode, default: 15)")
    parser.add_argument("--dry-run", action="store_true", help="Don't send notifications")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--auto-accept-hours", type=int, default=72, help="Auto-accept alerts after N hours (default: 72)")

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Initialize monitor
    logger.info("Initializing dosing verification monitor...")
    monitor = DosingVerificationMonitor(send_notifications=not args.dry_run)

    if args.dry_run:
        logger.info("DRY RUN MODE - notifications disabled")

    try:
        if args.once:
            logger.info(f"Running single scan (lookback: {args.lookback}h)...")
            summary = monitor.run_once(lookback_hours=args.lookback)
            print("\n" + "=" * 60)
            print("SCAN SUMMARY")
            print("=" * 60)
            for key, value in summary.items():
                print(f"  {key:20}: {value}")

            # Auto-accept old alerts
            auto_accepted = monitor.auto_accept_old_alerts(hours=args.auto_accept_hours)
            if auto_accepted > 0:
                print(f"\nAuto-accepted {auto_accepted} alerts older than {args.auto_accept_hours}h")

            return 0

        elif args.continuous:
            logger.info(f"Starting continuous monitoring (interval: {args.interval}m, lookback: {args.lookback}h)")
            print(f"\nMonitoring active. Scanning every {args.interval} minutes (Ctrl+C to stop)")
            monitor.run_continuous(interval_minutes=args.interval, lookback_hours=args.lookback)

        elif args.patient:
            logger.info(f"Checking patient {args.patient}...")
            alert_generated, alert_ids = monitor.check_patient(args.patient, lookback_hours=args.lookback)

            print("\n" + "=" * 60)
            print(f"PATIENT CHECK: {args.patient}")
            print("=" * 60)
            if alert_generated:
                print(f"  Alerts generated: {len(alert_ids)}")
                for alert_id in alert_ids:
                    print(f"    - {alert_id}")
            else:
                print("  No alerts generated")

            return 0

    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
