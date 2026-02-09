"""Celery tasks for Drug-Bug Mismatch module."""

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
def monitor_drug_bug(self):
    """Poll FHIR for cultures and detect drug-bug mismatches."""
    from .services import DrugBugMonitorService

    service = DrugBugMonitorService()
    result = service.run_detection()
    logger.info(
        "Drug-bug monitor: %d cultures checked, %d alerts created, %d errors",
        result['cultures_checked'], result['alerts_created'], len(result['errors']),
    )
    return result
