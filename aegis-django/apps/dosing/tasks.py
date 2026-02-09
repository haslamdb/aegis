"""Celery tasks for Dosing Verification module."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=60,
)
def monitor_dosing(self):
    """Run dosing verification checks against FHIR."""
    from .services import DosingMonitorService

    service = DosingMonitorService()
    result = service.run_check()
    logger.info(
        "Dosing monitor: %d flags, %d alerts created, %d skipped",
        result['total_flags'], result['alerts_created'], result['alerts_skipped'],
    )
    return result
