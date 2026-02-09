"""Celery tasks for HAI Detection module."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=120,
)
def detect_hai_candidates(self):
    """Run HAI candidate detection (rule-based screening)."""
    from .services import HAIDetectionService

    service = HAIDetectionService()
    result = service.run_detection()
    logger.info(
        "HAI detection: %d new candidates, errors: %s",
        result['new_candidates'], result['errors'],
    )
    return result


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=120,
)
def classify_hai_candidates(self):
    """Run LLM classification on pending HAI candidates."""
    from .services import HAIDetectionService

    service = HAIDetectionService()
    result = service.run_classification()
    logger.info(
        "HAI classification: %d classified, %d errors",
        result['classified'], result['errors'],
    )
    return result
