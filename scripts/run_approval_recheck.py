#!/usr/bin/env python3
"""
Wrapper script to run the antibiotic approval recheck scheduler.

This script is designed to be run via cron to automatically check
approvals that have reached their planned end date and create
re-approval requests if needed.

Usage:
    python3 /home/david/projects/aegis/scripts/run_approval_recheck.py

Cron example (runs at 6am, 12pm, and 6pm daily):
    0 6,12,18 * * * /usr/bin/python3 /home/david/projects/aegis/scripts/run_approval_recheck.py >> /var/log/aegis/recheck.log 2>&1
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.abx_approvals import AbxApprovalStore
from common.abx_approvals.recheck_scheduler import RecheckScheduler
from common.channels.email import EmailChannel
from dashboard.services.fhir import FHIRService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from environment or defaults."""
    config = {
        'db_path': os.environ.get('ABX_APPROVALS_DB_PATH', os.path.expanduser('~/.aegis/abx_approvals.db')),
        'fhir_url': os.environ.get('FHIR_BASE_URL', 'http://localhost:8081/fhir'),
        'smtp_server': os.environ.get('SMTP_SERVER'),
        'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
        'smtp_username': os.environ.get('SMTP_USERNAME'),
        'smtp_password': os.environ.get('SMTP_PASSWORD'),
        'email_from': os.environ.get('ASP_EMAIL_FROM', 'asp-alerts@hospital.org'),
        'email_to': os.environ.get('ASP_EMAIL_TO', 'asp-team@hospital.org').split(','),
    }
    return config


def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("Starting antibiotic approval recheck job")
    logger.info(f"Execution time: {datetime.now()}")
    logger.info("=" * 60)

    try:
        # Load configuration
        config = load_config()
        logger.info(f"Using database: {config['db_path']}")
        logger.info(f"Using FHIR server: {config['fhir_url']}")

        # Initialize approval store
        approval_store = AbxApprovalStore(db_path=config['db_path'])

        # Initialize FHIR service
        fhir_service = None
        try:
            fhir_service = FHIRService(config['fhir_url'])
            logger.info("FHIR service initialized")
        except Exception as e:
            logger.warning(f"Could not initialize FHIR service: {e}")
            logger.warning("Will continue without FHIR - rechecks will be skipped")

        # Initialize email notification (optional)
        email_notifier = None
        if config['smtp_server']:
            try:
                email_notifier = EmailChannel(
                    smtp_server=config['smtp_server'],
                    smtp_port=config['smtp_port'],
                    smtp_username=config['smtp_username'],
                    smtp_password=config['smtp_password'],
                    from_address=config['email_from'],
                    to_addresses=config['email_to'],
                )
                logger.info("Email notifications enabled")
            except Exception as e:
                logger.warning(f"Could not initialize email: {e}")
                logger.warning("Will continue without email notifications")
        else:
            logger.info("Email notifications not configured (SMTP_SERVER not set)")

        # Initialize recheck scheduler
        scheduler = RecheckScheduler(
            approval_store=approval_store,
            fhir_service=fhir_service,
            email_notifier=email_notifier
        )

        # Run recheck
        logger.info("Starting recheck process...")
        stats = scheduler.check_and_create_reapprovals()

        # Log results
        logger.info("-" * 60)
        logger.info("Recheck completed successfully")
        logger.info(f"Approvals checked: {stats['checked']}")
        logger.info(f"Still on antibiotic: {stats['still_on_antibiotic']}")
        logger.info(f"Discontinued: {stats['discontinued']}")
        logger.info(f"Re-approvals created: {stats['reapprovals_created']}")
        logger.info(f"Errors: {stats['errors']}")

        if stats['errors'] > 0:
            logger.warning("Errors occurred during recheck:")
            for error in stats['error_details']:
                logger.warning(
                    f"  - Approval {error['approval_id']} (MRN {error['patient_mrn']}): {error['error']}"
                )

        logger.info("=" * 60)

        # Exit with error code if there were errors
        if stats['errors'] > 0:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Fatal error during recheck job: {e}", exc_info=True)
        logger.info("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
