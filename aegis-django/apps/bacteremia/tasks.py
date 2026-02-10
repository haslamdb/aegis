"""Celery tasks for Bacteremia Monitoring module."""

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
def monitor_bacteremia(self):
    """Poll FHIR for blood cultures and assess antibiotic coverage."""
    from .services import BacteremiaMonitorService

    service = BacteremiaMonitorService()
    result = service.run_detection()
    logger.info(
        "Bacteremia monitor: %d cultures checked, %d alerts created, %d errors",
        result['cultures_checked'], result['alerts_created'], len(result['errors']),
    )
    return result
