"""Celery tasks for Antimicrobial Usage Alerts module."""

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
def monitor_usage(self):
    """Check for broad-spectrum antibiotic usage exceeding thresholds."""
    from .services import BroadSpectrumMonitorService

    service = BroadSpectrumMonitorService()
    new_alerts = service.check_new_alerts()
    logger.info("Usage monitor: %d new alerts created", len(new_alerts))
    return {'alerts_created': len(new_alerts)}
