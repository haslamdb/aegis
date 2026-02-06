"""Recheck scheduler for antibiotic approvals.

This module handles the automated rechecking of approved antibiotics
when their approval duration has expired.
"""

import logging
from datetime import datetime
from typing import Any

from .store import AbxApprovalStore
from .models import ApprovalRequest

logger = logging.getLogger(__name__)


class RecheckScheduler:
    """Scheduler for checking expired approvals and creating re-approval requests."""

    def __init__(
        self,
        approval_store: AbxApprovalStore,
        fhir_service: Any = None,
        email_notifier: Any = None
    ):
        """Initialize the recheck scheduler.

        Args:
            approval_store: The approval store instance
            fhir_service: FHIR service for querying current medications
            email_notifier: Email notification service (optional)
        """
        self.store = approval_store
        self.fhir = fhir_service
        self.email_notifier = email_notifier

    def check_and_create_reapprovals(self) -> dict[str, Any]:
        """Check all approvals needing recheck and create re-approval requests.

        Returns:
            Dictionary with summary statistics
        """
        stats = {
            "checked": 0,
            "still_on_antibiotic": 0,
            "discontinued": 0,
            "reapprovals_created": 0,
            "errors": 0,
            "error_details": [],
        }

        # Get approvals that need rechecking
        approvals_to_check = self.store.list_approvals_needing_recheck()
        stats["checked"] = len(approvals_to_check)

        logger.info(f"Checking {len(approvals_to_check)} approvals for re-approval")

        for approval in approvals_to_check:
            try:
                result = self._check_approval(approval)
                if result == "still_on_antibiotic":
                    stats["still_on_antibiotic"] += 1
                    stats["reapprovals_created"] += 1
                elif result == "discontinued":
                    stats["discontinued"] += 1
            except Exception as e:
                stats["errors"] += 1
                stats["error_details"].append({
                    "approval_id": approval.id,
                    "patient_mrn": approval.patient_mrn,
                    "error": str(e)
                })
                logger.error(
                    f"Error checking approval {approval.id} "
                    f"(patient {approval.patient_mrn}): {e}",
                    exc_info=True
                )

        logger.info(
            f"Recheck summary: {stats['checked']} checked, "
            f"{stats['reapprovals_created']} re-approvals created, "
            f"{stats['discontinued']} discontinued, "
            f"{stats['errors']} errors"
        )

        return stats

    def _check_approval(self, approval: ApprovalRequest) -> str:
        """Check a single approval and create re-approval request if needed.

        Args:
            approval: The approval request to check

        Returns:
            "still_on_antibiotic" if patient still on antibiotic (re-approval created)
            "discontinued" if patient no longer on antibiotic
        """
        # Update last recheck date
        now = datetime.now()
        self._update_recheck_date(approval.id, now)

        # Check if patient is still on the same antibiotic
        still_on_antibiotic = self._is_patient_on_antibiotic(
            approval.patient_id,
            approval.antibiotic_name
        )

        if still_on_antibiotic:
            # Create re-approval request
            self._create_reapproval_request(approval)
            logger.info(
                f"Patient {approval.patient_mrn} still on {approval.antibiotic_name}, "
                f"created re-approval request"
            )
            return "still_on_antibiotic"
        else:
            # Mark approval as completed (patient no longer on antibiotic)
            self._mark_approval_completed(approval.id)
            logger.info(
                f"Patient {approval.patient_mrn} no longer on {approval.antibiotic_name}, "
                f"marked approval as completed"
            )
            return "discontinued"

    def _is_patient_on_antibiotic(
        self,
        patient_id: str,
        antibiotic_name: str
    ) -> bool:
        """Check if patient is currently on the specified antibiotic.

        Args:
            patient_id: FHIR Patient ID
            antibiotic_name: Name of antibiotic to check for

        Returns:
            True if patient is currently on the antibiotic
        """
        if not self.fhir:
            logger.warning("FHIR service not available, cannot check current medications")
            return False

        try:
            # Get current antibiotic medications
            medications = self.fhir.get_patient_medications(
                patient_id,
                antibiotics_only=True,
                active_only=True
            )

            # Check if any medication matches the antibiotic name
            # (case-insensitive partial match to handle variations like "Vancomycin" vs "vancomycin")
            antibiotic_lower = antibiotic_name.lower()
            for med in medications:
                med_name = med.get("medication", "").lower()
                if antibiotic_lower in med_name or med_name in antibiotic_lower:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking medications for patient {patient_id}: {e}")
            # On error, assume patient is still on antibiotic (safer to over-alert)
            return True

    def _create_reapproval_request(self, original_approval: ApprovalRequest) -> None:
        """Create a new re-approval request for an original approval.

        Args:
            original_approval: The original approval that expired
        """
        # Create re-approval request
        reapproval = self.store.create_request(
            patient_id=original_approval.patient_id,
            patient_mrn=original_approval.patient_mrn,
            patient_name=original_approval.patient_name,
            patient_location=original_approval.patient_location,
            antibiotic_name=original_approval.antibiotic_name,
            antibiotic_dose=original_approval.antibiotic_dose,
            antibiotic_route=original_approval.antibiotic_route,
            indication=original_approval.indication,
            prescriber_name=original_approval.prescriber_name,
            prescriber_pager=original_approval.prescriber_pager,
            created_by="system_recheck",
            is_reapproval=True,
            parent_approval_id=original_approval.id,
        )

        # Update original approval recheck status
        self._mark_approval_extended(original_approval.id)

        # Send email notification if configured
        if self.email_notifier:
            try:
                self._send_reapproval_notification(original_approval, reapproval)
            except Exception as e:
                logger.error(f"Failed to send re-approval notification: {e}")

        logger.info(
            f"Created re-approval request {reapproval.id} for original approval {original_approval.id}"
        )

    def _update_recheck_date(self, approval_id: str, recheck_date: datetime) -> None:
        """Update the last_recheck_date for an approval."""
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE abx_approval_requests SET last_recheck_date = ? WHERE id = ?",
                (recheck_date.isoformat(), approval_id)
            )
            conn.commit()

    def _mark_approval_completed(self, approval_id: str) -> None:
        """Mark an approval as completed (patient no longer on antibiotic)."""
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE abx_approval_requests SET recheck_status = ? WHERE id = ?",
                ("completed", approval_id)
            )
            conn.commit()

    def _mark_approval_extended(self, approval_id: str) -> None:
        """Mark an approval as extended (re-approval request created)."""
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE abx_approval_requests SET recheck_status = ? WHERE id = ?",
                ("extended", approval_id)
            )
            conn.commit()

    def _send_reapproval_notification(
        self,
        original_approval: ApprovalRequest,
        reapproval: ApprovalRequest
    ) -> None:
        """Send email notification for re-approval request.

        Args:
            original_approval: The original approval
            reapproval: The newly created re-approval request
        """
        if not self.email_notifier:
            return

        # Calculate duration text
        duration_text = "unknown duration"
        if original_approval.approval_duration_hours:
            hours = original_approval.approval_duration_hours
            if hours % 24 == 0:
                days = hours // 24
                duration_text = f"{days} day{'s' if days != 1 else ''}"
            else:
                duration_text = f"{hours} hours"

        subject = (
            f"ABX Re-approval Request: {original_approval.patient_name} "
            f"({original_approval.patient_mrn}) - {original_approval.antibiotic_name}"
        )

        body = f"""
A patient previously approved for antibiotic therapy has reached their
approval end date and is still on the same antibiotic.

Patient: {original_approval.patient_name or 'Unknown'} (MRN: {original_approval.patient_mrn})
Location: {original_approval.patient_location or 'Unknown'}

Antibiotic: {original_approval.antibiotic_name}
Dose: {original_approval.antibiotic_dose or 'Not specified'}
Route: {original_approval.antibiotic_route or 'Not specified'}

Original Approval: {original_approval.decision_at.strftime('%Y-%m-%d %H:%M') if original_approval.decision_at else 'Unknown'}
Approved By: {original_approval.decision_by or 'Unknown'}
Previous Duration: {duration_text}

This is re-approval #{reapproval.approval_chain_count + 1} for this patient.

Review request: https://aegis-asp.com/abx-approvals/approval/{reapproval.id}

---
This is an automated message from the AEGIS Antimicrobial Stewardship Platform.
"""

        try:
            self.email_notifier.send(
                subject=subject,
                body=body,
                to_addresses=["asp-team@hospital.org"],  # Configure this
            )
            logger.info(f"Sent re-approval notification email for {reapproval.id}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            raise
