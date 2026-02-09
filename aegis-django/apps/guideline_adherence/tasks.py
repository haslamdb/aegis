"""Celery tasks for Guideline Adherence module."""

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
def check_guideline_triggers(self):
    """Poll FHIR for new diagnoses matching bundle triggers."""
    from .services import GuidelineAdherenceService

    service = GuidelineAdherenceService()
    new_episodes = service.check_triggers()
    logger.info("Guideline triggers: %d new episodes created", len(new_episodes))
    return {'new_episodes': len(new_episodes)}


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=120,
)
def check_guideline_episodes(self):
    """Check active episodes for element deadline violations."""
    from .services import GuidelineAdherenceService

    service = GuidelineAdherenceService()
    alerts = service.check_episodes()
    logger.info("Guideline episodes: %d alerts created", len(alerts))
    return {'alerts_created': len(alerts)}


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=120,
)
def check_guideline_adherence(self):
    """Run element checkers on active episodes, update adherence."""
    from .services import GuidelineAdherenceService

    service = GuidelineAdherenceService()
    result = service.check_adherence()
    logger.info(
        "Guideline adherence: %d episodes checked, %d elements updated",
        result.get('episodes_checked', 0), result.get('elements_updated', 0),
    )
    return result
