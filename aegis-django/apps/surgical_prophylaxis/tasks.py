"""Celery tasks for Surgical Prophylaxis module."""

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
def monitor_prophylaxis(self):
    """Fetch surgical cases from FHIR and evaluate prophylaxis compliance."""
    from .services import SurgicalProphylaxisService

    service = SurgicalProphylaxisService()
    results = service.check_new_cases()
    logger.info("Surgical prophylaxis: %d cases evaluated", len(results))
    return {'cases_evaluated': len(results)}
