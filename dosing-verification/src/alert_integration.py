"""Integration with ASP AlertStore for persisting dosing verification alerts."""

import logging
from datetime import datetime
from typing import Any

from common.dosing_verification import DoseAlertStore, DoseAlertRecord, DoseAssessment
from .notifications import DosingNotificationHandler

logger = logging.getLogger(__name__)


class DosingAlertIntegration:
    """Handles persistence and notification of dosing verification alerts."""

    def __init__(
        self,
        alert_store: DoseAlertStore | None = None,
        notification_handler: DosingNotificationHandler | None = None,
        auto_notify: bool = True,
    ):
        """Initialize dosing alert integration.

        Args:
            alert_store: DoseAlertStore instance (creates default if None)
            notification_handler: DosingNotificationHandler instance (optional)
            auto_notify: Whether to automatically send notifications when saving alerts
        """
        self.alert_store = alert_store or DoseAlertStore()
        self.notification_handler = notification_handler
        self.auto_notify = auto_notify

    def save_assessment(
        self,
        assessment: DoseAssessment,
        notify_email: str | None = None,
    ) -> list[DoseAlertRecord]:
        """Save assessment and create alert records for each flag.

        Args:
            assessment: DoseAssessment with flags to persist
            notify_email: Optional email for notifications

        Returns:
            List of created DoseAlertRecords
        """
        alerts = []

        # Nothing to save if no flags
        if not assessment.flags:
            logger.debug(f"Assessment {assessment.assessment_id} has no flags, skipping save")
            return alerts

        # Build patient factors dict
        patient_factors = {
            "age_years": assessment.age_years,
            "weight_kg": assessment.weight_kg,
            "height_cm": assessment.height_cm,
            "scr": assessment.scr,
            "gfr": assessment.gfr,
            "crcl": None,  # Would come from assessment if we add it
            "is_on_dialysis": assessment.is_on_dialysis,
            "gestational_age_weeks": assessment.gestational_age_weeks,
        }

        # Build assessment details dict
        assessment_details = {
            "assessment_id": assessment.assessment_id,
            "assessed_at": assessment.assessed_at,
            "assessed_by": assessment.assessed_by,
            "indication": assessment.indication,
            "indication_confidence": assessment.indication_confidence,
            "indication_source": assessment.indication_source,
            "medications_evaluated": assessment.medications_evaluated,
            "co_medications": assessment.co_medications,
            "max_severity": assessment.max_severity.value if assessment.max_severity else None,
            "flag_count": len(assessment.flags),
        }

        # Save each flag as a separate alert
        for flag in assessment.flags:
            try:
                alert = self.alert_store.save_alert(
                    assessment_id=assessment.assessment_id,
                    patient_id=assessment.patient_id,
                    patient_mrn=assessment.patient_mrn,
                    patient_name=assessment.patient_name,
                    flag=flag,
                    patient_factors=patient_factors,
                    assessment_details=assessment_details,
                    encounter_id=assessment.encounter_id,
                )
                alerts.append(alert)

                logger.info(
                    f"Saved dose alert {alert.id} for {flag.drug} "
                    f"(flag: {flag.flag_type.value}, severity: {flag.severity.value})"
                )

            except Exception as e:
                logger.error(
                    f"Failed to save alert for {flag.drug} in assessment {assessment.assessment_id}: {e}",
                    exc_info=True,
                )
                # Continue saving other alerts even if one fails

        # Send notification if configured and auto_notify enabled
        if self.auto_notify and self.notification_handler and alerts:
            try:
                results = self.notification_handler.send_assessment_alert(
                    assessment=assessment,
                    recipient_email=notify_email,
                )
                logger.info(
                    f"Notification sent for assessment {assessment.assessment_id}: "
                    f"Teams={results.get('teams', False)}, Email={results.get('email', False)}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send notification for assessment {assessment.assessment_id}: {e}",
                    exc_info=True,
                )

        return alerts

    def bulk_save_assessments(
        self,
        assessments: list[DoseAssessment],
        notify_email: str | None = None,
    ) -> dict[str, list[DoseAlertRecord]]:
        """Save multiple assessments in bulk.

        Args:
            assessments: List of DoseAssessment objects
            notify_email: Optional email for notifications

        Returns:
            Dict mapping assessment_id to list of created DoseAlertRecords
        """
        results = {}

        for assessment in assessments:
            try:
                alerts = self.save_assessment(
                    assessment=assessment,
                    notify_email=notify_email,
                )
                results[assessment.assessment_id] = alerts

            except Exception as e:
                logger.error(
                    f"Failed to save assessment {assessment.assessment_id}: {e}",
                    exc_info=True,
                )
                results[assessment.assessment_id] = []

        total_alerts = sum(len(alerts) for alerts in results.values())
        logger.info(
            f"Bulk save complete: {len(assessments)} assessments, "
            f"{total_alerts} alerts created"
        )

        return results

    def get_alerts_for_patient(
        self,
        patient_mrn: str,
    ) -> list[DoseAlertRecord]:
        """Retrieve all alerts for a patient.

        Args:
            patient_mrn: Patient MRN

        Returns:
            List of DoseAlertRecords
        """
        return self.alert_store.list_by_patient(patient_mrn=patient_mrn)

    def resolve_alert(
        self,
        alert_id: str,
        resolution: str,
        resolution_notes: str | None = None,
        resolved_by: str | None = None,
    ) -> None:
        """Mark an alert as resolved.

        Args:
            alert_id: Alert ID to resolve
            resolution: Resolution type (from DoseResolution enum)
            resolution_notes: Optional notes about the resolution
            resolved_by: Provider who resolved the alert
        """
        self.alert_store.resolve(
            alert_id=alert_id,
            resolution=resolution,
            notes=resolution_notes,
            by=resolved_by or "system",
        )

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> None:
        """Mark an alert as acknowledged.

        Args:
            alert_id: Alert ID to acknowledge
            acknowledged_by: Provider who acknowledged the alert
        """
        self.alert_store.acknowledge(
            alert_id=alert_id,
            by=acknowledged_by,
        )

    def get_pending_alerts(
        self,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[DoseAlertRecord]:
        """Get all pending/active alerts.

        Args:
            severity: Optional severity filter (critical, high, moderate, low)
            limit: Maximum number of alerts to return

        Returns:
            List of DoseAlertRecords
        """
        return self.alert_store.list_active(
            severity=severity,
            limit=limit,
        )

    def get_alert_statistics(self, days: int = 30) -> dict:
        """Get statistics about dosing alerts.

        Args:
            days: Number of days to include in analytics (default 30)

        Returns:
            Dict with statistics (total alerts, by severity, by flag type, etc.)
        """
        return self.alert_store.get_analytics(days=days)
