#!/usr/bin/env python3
"""CLI entry point for Outbreak Detection.

Usage:
    # Run once and exit
    python -m outbreak_src.runner --once

    # Run with custom lookback
    python -m outbreak_src.runner --once --days 30

    # Run continuously
    python -m outbreak_src.runner --continuous

    # Run with custom interval
    python -m outbreak_src.runner --continuous --interval 60

    # Debug mode
    python -m outbreak_src.runner --once --debug
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .config import config
from .db import OutbreakDatabase
from .detector import OutbreakDetector


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Outbreak Detection - Identify infection clusters for IP investigation",
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
        default=60,
        help="Poll interval in minutes for continuous mode (default: 60)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"Days to look back for clustering (default: {config.CLUSTER_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Outbreak database path (default from config)",
    )
    parser.add_argument(
        "--mdro-db",
        type=str,
        default=None,
        help="MDRO database path for data source",
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
    logger = logging.getLogger(__name__)

    # Override config if arguments provided
    if args.db_path:
        config.DB_PATH = args.db_path

    # Create database and detector
    db = OutbreakDatabase(config.DB_PATH)
    detector = OutbreakDetector(db)

    # Run
    if args.continuous:
        print(f"Starting Outbreak Detection in continuous mode (interval: {args.interval} min)")
        print(f"Database: {config.DB_PATH}")
        print(f"Cluster window: {config.CLUSTER_WINDOW_DAYS} days")
        print(f"Min cluster size: {config.MIN_CLUSTER_SIZE}")
        print("-" * 60)

        while True:
            try:
                days = args.days or config.CLUSTER_WINDOW_DAYS
                result = detector.run_detection(days=days)

                logger.info(
                    f"Detection complete: {result['cases_analyzed']} cases, "
                    f"{result['clusters_formed']} new clusters, "
                    f"{result['alerts_created']} alerts"
                )

            except Exception as e:
                logger.error(f"Error in detection loop: {e}")

            time.sleep(args.interval * 60)

    else:
        # Default to run once
        days = args.days or config.CLUSTER_WINDOW_DAYS
        print(f"Running Outbreak Detection (lookback: {days} days)")
        print(f"Database: {config.DB_PATH}")
        print(f"Min cluster size: {config.MIN_CLUSTER_SIZE}")
        print("-" * 60)

        result = detector.run_detection(days=days)

        print(f"\nResults:")
        print(f"  Cases analyzed:       {result['cases_analyzed']}")
        print(f"  New cases processed:  {result['new_cases_processed']}")
        print(f"  Clusters formed:      {result['clusters_formed']}")
        print(f"  Clusters updated:     {result['clusters_updated']}")
        print(f"  Alerts created:       {result['alerts_created']}")

        # Show active clusters
        active_clusters = db.get_active_clusters()
        if active_clusters:
            print(f"\nActive Clusters ({len(active_clusters)}):")
            for cluster in active_clusters[:10]:
                print(f"  - {cluster.infection_type.upper()} in {cluster.unit}: "
                      f"{cluster.case_count} cases ({cluster.severity.value})")

        # Show pending alerts
        pending_alerts = db.get_pending_alerts()
        if pending_alerts:
            print(f"\nPending Alerts ({len(pending_alerts)}):")
            for alert in pending_alerts[:5]:
                print(f"  - [{alert['severity']}] {alert['title']}")

        print(f"\nCompleted at: {result['completed_at']}")


if __name__ == "__main__":
    main()
