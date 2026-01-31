#!/usr/bin/env python3
"""Run the Bundle Trigger Monitor.

This script starts the guideline adherence monitoring service which:
1. On startup: Processes any episodes without LLM assessments
2. Continuously: Polls for new triggers and checks element status
3. Every 12 hours: Re-assesses active episodes for updated notes

Usage:
    python run_monitor.py              # Run continuously
    python run_monitor.py --once       # Run one cycle and exit (good for testing)
    python run_monitor.py --assess     # Only run assessment on unprocessed episodes
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from guideline_src.bundle_monitor import BundleTriggerMonitor
from guideline_src.fhir_client import HAPIGuidelineFHIRClient
from guideline_src.episode_db import EpisodeDB
from guideline_src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run Guideline Adherence Monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one monitoring cycle and exit",
    )
    parser.add_argument(
        "--assess",
        action="store_true",
        help="Only assess unprocessed episodes, then exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Poll interval in seconds (default: 60)",
    )
    args = parser.parse_args()

    # Initialize components
    logger.info("Initializing monitor components...")

    try:
        fhir_client = HAPIGuidelineFHIRClient()
        # Test connection
        fhir_client.get("metadata")
        logger.info(f"Connected to FHIR server: {fhir_client.base_url}")
    except Exception as e:
        logger.error(f"Failed to connect to FHIR server: {e}")
        sys.exit(1)

    db = EpisodeDB(str(Config.ADHERENCE_DB_PATH))
    logger.info(f"Using database: {Config.ADHERENCE_DB_PATH}")

    monitor = BundleTriggerMonitor(
        fhir_client=fhir_client,
        db=db,
        poll_interval_seconds=args.interval,
    )

    if args.assess:
        # Only run assessment on unprocessed episodes
        logger.info("Running assessment on unprocessed episodes...")
        monitor._assess_unprocessed_episodes()
        logger.info("Assessment complete")
    else:
        # Run the full monitor
        logger.info("Starting monitor...")
        monitor.run(once=args.once)


if __name__ == "__main__":
    main()
