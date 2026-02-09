"""Celery tasks for MDRO Surveillance module."""

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
def monitor_mdro(self):
    """Poll FHIR for new cultures and detect MDRO cases."""
    from .services import MDROMonitorService

    service = MDROMonitorService()
    result = service.run_detection()
    logger.info(
        "MDRO monitor: %d cultures checked, %d new cases, %d errors",
        result['cultures_checked'], result['new_mdro_cases'], len(result['errors']),
    )
    return result
