"""Celery tasks for NHSN Reporting module."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=300,
)
def nhsn_nightly_extract(self):
    """Nightly batch extraction of AU/AR/denominator data from Clarity."""
    from .logic import config as cfg

    if not cfg.is_clarity_configured():
        logger.warning("NHSN nightly extract skipped: Clarity not configured")
        return {'skipped': True, 'reason': 'clarity_not_configured'}

    results = {}

    try:
        from .logic.au_extractor import AUDataExtractor
        extractor = AUDataExtractor()
        au_summary = extractor.get_monthly_summary()
        results['au'] = {
            'total_dot': au_summary.get('overall_totals', {}).get('total_dot', 0),
            'locations': len(au_summary.get('locations', [])),
        }
        logger.info("NHSN AU extraction complete: %s", results['au'])
    except Exception as e:
        logger.error("NHSN AU extraction failed: %s", e)
        results['au_error'] = str(e)

    try:
        from .logic.ar_extractor import ARDataExtractor
        extractor = ARDataExtractor()
        from datetime import date
        year = date.today().year
        quarter = (date.today().month - 1) // 3 + 1
        ar_summary = extractor.get_quarterly_summary(None, year, quarter)
        results['ar'] = {
            'total_cultures': ar_summary.get('overall_totals', {}).get('total_cultures', 0),
            'first_isolates': ar_summary.get('overall_totals', {}).get('first_isolates', 0),
        }
        logger.info("NHSN AR extraction complete: %s", results['ar'])
    except Exception as e:
        logger.error("NHSN AR extraction failed: %s", e)
        results['ar_error'] = str(e)

    try:
        from .logic.denominator import DenominatorCalculator
        calc = DenominatorCalculator()
        denom_summary = calc.get_denominator_summary()
        results['denominators'] = {
            'locations': len(denom_summary.get('locations', [])),
        }
        logger.info("NHSN denominator extraction complete: %s", results['denominators'])
    except Exception as e:
        logger.error("NHSN denominator extraction failed: %s", e)
        results['denominator_error'] = str(e)

    return results


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=300,
)
def nhsn_create_events(self):
    """Create NHSN events from confirmed HAI candidates."""
    from .services import NHSNReportingService

    service = NHSNReportingService()
    count = service.create_nhsn_events()
    logger.info("NHSN events: %d new events created", count)
    return {'events_created': count}
