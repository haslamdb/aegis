"""Celery tasks for ABX Indication Monitoring module."""

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
def check_abx_indications(self):
    """Poll FHIR for new abx orders, extract indications, check guidelines."""
    from .services import IndicationMonitorService

    service = IndicationMonitorService()
    candidates = service.check_new_orders()
    new_alerts = service.check_new_alerts()
    logger.info(
        "ABX indications: %d new candidates, %d alerts created",
        len(candidates), len(new_alerts),
    )
    return {
        'candidates_processed': len(candidates),
        'alerts_created': len(new_alerts),
    }


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    default_retry_delay=120,
)
def auto_accept_old_indications(self):
    """Auto-accept indication candidates older than threshold."""
    from .services import IndicationMonitorService

    service = IndicationMonitorService()
    count = service.auto_accept_old()
    logger.info("ABX indications: auto-accepted %d old candidates", count)
    return {'auto_accepted': count}
