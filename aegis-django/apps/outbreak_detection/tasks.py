"""Celery tasks for Outbreak Detection module."""

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
def detect_outbreaks(self):
    """Run outbreak detection on recent MDRO + HAI cases."""
    from .services import OutbreakDetectionService

    service = OutbreakDetectionService()
    result = service.run_detection()
    logger.info(
        "Outbreak detection: %d cases analyzed, %d clusters formed, %d alerts",
        result['cases_analyzed'], result['clusters_formed'], result['alerts_created'],
    )
    return result
