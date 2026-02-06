"""SQLite-backed storage for antibiotic approval requests."""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    ApprovalDecision,
    ApprovalStatus,
    AuditAction,
    ApprovalRequest,
    ApprovalAuditEntry,
)

logger = logging.getLogger(__name__)


def _log_abx_activity(
    activity_type: str,
    entity_id: str,
    entity_type: str,
    action_taken: str,
    provider_id: str | None = None,
    provider_name: str | None = None,
    patient_mrn: str | None = None,
    outcome: str | None = None,
    details: dict | None = None,
) -> None:
    """Log activity to the unified metrics store.

    This is a fire-and-forget operation - failures are logged but don't
    interrupt the main operation.
    """
    try:
        from common.metrics_store import MetricsStore, ModuleSource

        store = MetricsStore()
        store.log_activity(
            activity_type=activity_type,
            module=ModuleSource.ABX_APPROVALS,
            provider_id=provider_id,
            provider_name=provider_name,
            entity_id=entity_id,
            entity_type=entity_type,
            action_taken=action_taken,
            outcome=outcome,
            patient_mrn=patient_mrn,
            details=details,
        )
    except Exception as e:
        logger.debug(f"Failed to log activity to metrics store: {e}")


class AbxApprovalStore:
    """SQLite-backed storage for managing antibiotic approval requests."""

    def __init__(self, db_path: str | None = None):
        """Initialize approval store.

        Args:
            db_path: Path to SQLite database. Defaults to ABX_APPROVALS_DB_PATH env var
                     or ~/.aegis/abx_approvals.db
        """
        if db_path:
            self.db_path = os.path.expanduser(db_path)
        else:
            self.db_path = os.path.expanduser(
                os.environ.get("ABX_APPROVALS_DB_PATH", "~/.aegis/abx_approvals.db")
            )

        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

    @staticmethod
    def calculate_planned_end_date(
        approval_date: datetime,
        duration_hours: int,
        grace_period_days: int = 1
    ) -> datetime:
        """Calculate planned end date with grace period and weekend handling.

        Args:
            approval_date: When the approval was given
            duration_hours: Approved duration in hours
            grace_period_days: Grace period in days (default: 1)

        Returns:
            Planned end date adjusted for grace period and weekends
        """
        # Calculate base end date (approval date + duration + grace period)
        end_date = approval_date + timedelta(hours=duration_hours) + timedelta(days=grace_period_days)

        # If end date falls on Saturday (5) or Sunday (6), check Friday before
        if end_date.weekday() in (5, 6):
            # Move back to Friday
            days_back = end_date.weekday() - 4
            end_date = end_date - timedelta(days=days_back)

        return end_date

    def _init_db(self) -> None:
        """Initialize database schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()

        with self._connect() as conn:
            conn.executescript(schema)

    def _connect(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _generate_id(self) -> str:
        """Generate a unique approval ID."""
        return str(uuid.uuid4())[:8]

    # Core approval operations

    def create_request(
        self,
        patient_id: str,
        patient_mrn: str,
        antibiotic_name: str,
        patient_name: str | None = None,
        patient_location: str | None = None,
        antibiotic_dose: str | None = None,
        antibiotic_route: str | None = None,
        indication: str | None = None,
        duration_requested_hours: int | None = None,
        prescriber_name: str | None = None,
        prescriber_pager: str | None = None,
        clinical_context: dict | None = None,
        created_by: str | None = None,
        is_reapproval: bool = False,
        parent_approval_id: str | None = None,
    ) -> ApprovalRequest:
        """Create a new approval request.

        Args:
            patient_id: FHIR Patient resource ID
            patient_mrn: Patient MRN
            antibiotic_name: Name of the antibiotic being requested
            patient_name: Patient display name
            patient_location: Patient location/unit
            antibiotic_dose: Dose and frequency
            antibiotic_route: Route (IV, PO, etc.)
            indication: Clinical indication for antibiotic
            duration_requested_hours: Requested duration in hours
            prescriber_name: Name of requesting prescriber
            prescriber_pager: Prescriber pager number
            clinical_context: Dict with cultures, current meds, etc.
            created_by: User creating the request
            is_reapproval: Whether this is a re-approval request
            parent_approval_id: ID of parent approval if this is a re-approval

        Returns:
            The created ApprovalRequest
        """
        approval_id = self._generate_id()
        now = datetime.now()
        context_json = json.dumps(clinical_context) if clinical_context else None

        # Calculate approval chain count if this is a re-approval
        approval_chain_count = 0
        if is_reapproval and parent_approval_id:
            parent = self.get_request(parent_approval_id)
            if parent:
                approval_chain_count = parent.approval_chain_count + 1

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO abx_approval_requests (
                    id, patient_id, patient_mrn, patient_name, patient_location,
                    antibiotic_name, antibiotic_dose, antibiotic_route,
                    indication, duration_requested_hours,
                    prescriber_name, prescriber_pager,
                    clinical_context,
                    is_reapproval, parent_approval_id, approval_chain_count,
                    status, created_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id, patient_id, patient_mrn, patient_name, patient_location,
                    antibiotic_name, antibiotic_dose, antibiotic_route,
                    indication, duration_requested_hours,
                    prescriber_name, prescriber_pager,
                    context_json,
                    is_reapproval, parent_approval_id, approval_chain_count,
                    ApprovalStatus.PENDING.value, now.isoformat(), created_by
                )
            )

            # Audit log
            audit_details = f"Request for {antibiotic_name}"
            if is_reapproval:
                audit_details = f"Re-approval request for {antibiotic_name} (chain #{approval_chain_count + 1})"

            conn.execute(
                """
                INSERT INTO abx_approval_audit (approval_id, action, performed_by, performed_at, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (approval_id, AuditAction.CREATED.value, created_by, now.isoformat(), audit_details)
            )

            conn.commit()

        log_msg = f"Created {'re-approval' if is_reapproval else 'approval'} request {approval_id} for {antibiotic_name} (patient {patient_mrn})"
        logger.info(log_msg)

        # Log to unified metrics store
        _log_abx_activity(
            activity_type="request_created" if not is_reapproval else "reapproval_request_created",
            entity_id=approval_id,
            entity_type="approval_request",
            action_taken="created",
            provider_name=created_by,
            patient_mrn=patient_mrn,
            details={
                "antibiotic": antibiotic_name,
                "prescriber": prescriber_name,
                "is_reapproval": is_reapproval,
                "parent_approval_id": parent_approval_id,
                "approval_chain_count": approval_chain_count,
            },
        )

        return ApprovalRequest(
            id=approval_id,
            patient_id=patient_id,
            patient_mrn=patient_mrn,
            patient_name=patient_name,
            patient_location=patient_location,
            antibiotic_name=antibiotic_name,
            antibiotic_dose=antibiotic_dose,
            antibiotic_route=antibiotic_route,
            indication=indication,
            duration_requested_hours=duration_requested_hours,
            prescriber_name=prescriber_name,
            prescriber_pager=prescriber_pager,
            clinical_context=clinical_context or {},
            is_reapproval=is_reapproval,
            parent_approval_id=parent_approval_id,
            approval_chain_count=approval_chain_count,
            status=ApprovalStatus.PENDING.value,
            created_at=now,
            created_by=created_by,
        )

    def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Get an approval request by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, patient_id, patient_mrn, patient_name, patient_location,
                       antibiotic_name, antibiotic_dose, antibiotic_route,
                       indication, duration_requested_hours,
                       prescriber_name, prescriber_pager, clinical_context,
                       decision, decision_by, decision_at, decision_notes,
                       alternative_recommended,
                       approval_duration_hours, planned_end_date, is_reapproval,
                       parent_approval_id, approval_chain_count, recheck_status,
                       last_recheck_date,
                       status, created_at, created_by
                FROM abx_approval_requests WHERE id = ?
                """,
                (approval_id,)
            )
            row = cursor.fetchone()

            if row:
                return ApprovalRequest.from_row(tuple(row))
            return None

    def decide(
        self,
        approval_id: str,
        decision: ApprovalDecision | str,
        decision_by: str,
        decision_notes: str | None = None,
        alternative_recommended: str | None = None,
        approval_duration_hours: int | None = None,
    ) -> bool:
        """Record a decision on an approval request.

        Args:
            approval_id: The approval request ID
            decision: The decision (approved, suggested_alternate, etc.)
            decision_by: Who made the decision
            decision_notes: Notes about the decision
            alternative_recommended: For suggested_alternate, the recommended alternative
            approval_duration_hours: For approved, the approved duration in hours

        Returns:
            True if decision was recorded successfully
        """
        now = datetime.now()

        # Convert enum to string if needed
        if isinstance(decision, ApprovalDecision):
            decision_value = decision.value
        else:
            decision_value = decision

        # Get request info for activity logging
        request = self.get_request(approval_id)

        # Calculate planned_end_date if decision is "approved" and duration is provided
        planned_end_date = None
        recheck_status = None
        if decision_value == ApprovalDecision.APPROVED.value and approval_duration_hours:
            planned_end_date = self.calculate_planned_end_date(now, approval_duration_hours)
            recheck_status = "pending"

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE abx_approval_requests
                SET decision = ?, decision_by = ?, decision_at = ?,
                    decision_notes = ?, alternative_recommended = ?,
                    approval_duration_hours = ?, planned_end_date = ?,
                    recheck_status = ?,
                    status = ?
                WHERE id = ? AND status = ?
                """,
                (
                    decision_value, decision_by, now.isoformat(),
                    decision_notes, alternative_recommended,
                    approval_duration_hours,
                    planned_end_date.isoformat() if planned_end_date else None,
                    recheck_status,
                    ApprovalStatus.COMPLETED.value,
                    approval_id, ApprovalStatus.PENDING.value
                )
            )

            if cursor.rowcount > 0:
                # Build audit details
                details_parts = [f"Decision: {ApprovalDecision.display_name(decision_value)}"]
                if alternative_recommended:
                    details_parts.append(f"Alternative: {alternative_recommended}")
                if decision_notes:
                    details_parts.append(f"Notes: {decision_notes[:100]}")

                conn.execute(
                    """
                    INSERT INTO abx_approval_audit (approval_id, action, performed_by, performed_at, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (approval_id, AuditAction.DECISION_MADE.value, decision_by,
                     now.isoformat(), "; ".join(details_parts))
                )
                conn.commit()
                logger.info(f"Approval {approval_id} decided as {decision_value} by {decision_by}")

                # Log to unified metrics store
                _log_abx_activity(
                    activity_type="decision",
                    entity_id=approval_id,
                    entity_type="approval_request",
                    action_taken=decision_value,
                    provider_name=decision_by,
                    patient_mrn=request.patient_mrn if request else None,
                    outcome=decision_value,
                    details={
                        "antibiotic": request.antibiotic_name if request else None,
                        "alternative": alternative_recommended,
                        "notes": decision_notes[:200] if decision_notes else None,
                    },
                )

                return True

            return False

    def add_note(
        self,
        approval_id: str,
        note: str,
        added_by: str | None = None,
    ) -> bool:
        """Add a note to an approval request."""
        now = datetime.now()

        with self._connect() as conn:
            # Append to existing notes
            cursor = conn.execute(
                """
                UPDATE abx_approval_requests
                SET decision_notes = CASE
                    WHEN decision_notes IS NULL OR decision_notes = '' THEN ?
                    ELSE decision_notes || char(10) || char(10) || ?
                END
                WHERE id = ?
                """,
                (note, note, approval_id)
            )

            if cursor.rowcount > 0:
                conn.execute(
                    """
                    INSERT INTO abx_approval_audit (approval_id, action, performed_by, performed_at, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (approval_id, AuditAction.NOTE_ADDED.value, added_by,
                     now.isoformat(), note[:200])
                )
                conn.commit()
                return True

            return False

    # Query methods

    def list_requests(
        self,
        status: ApprovalStatus | str | None = None,
        patient_mrn: str | None = None,
        antibiotic_name: str | None = None,
        decision: ApprovalDecision | str | None = None,
        days_back: int | None = None,
        limit: int = 100,
    ) -> list[ApprovalRequest]:
        """List approval requests with optional filters.

        Args:
            status: Filter by status (pending, completed)
            patient_mrn: Filter by patient MRN
            antibiotic_name: Filter by antibiotic name (partial match)
            decision: Filter by decision type
            days_back: Only include requests from last N days
            limit: Maximum results

        Returns:
            List of matching ApprovalRequest objects
        """
        conditions = []
        params: list[Any] = []

        if status:
            status_value = status.value if isinstance(status, ApprovalStatus) else status
            conditions.append("status = ?")
            params.append(status_value)

        if patient_mrn:
            conditions.append("patient_mrn = ?")
            params.append(patient_mrn)

        if antibiotic_name:
            conditions.append("antibiotic_name LIKE ?")
            params.append(f"%{antibiotic_name}%")

        if decision:
            decision_value = decision.value if isinstance(decision, ApprovalDecision) else decision
            conditions.append("decision = ?")
            params.append(decision_value)

        if days_back:
            cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
            conditions.append("created_at >= ?")
            params.append(cutoff)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, patient_id, patient_mrn, patient_name, patient_location,
                       antibiotic_name, antibiotic_dose, antibiotic_route,
                       indication, duration_requested_hours,
                       prescriber_name, prescriber_pager, clinical_context,
                       decision, decision_by, decision_at, decision_notes,
                       alternative_recommended,
                       approval_duration_hours, planned_end_date, is_reapproval,
                       parent_approval_id, approval_chain_count, recheck_status,
                       last_recheck_date,
                       status, created_at, created_by
                FROM abx_approval_requests
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params
            )

            return [ApprovalRequest.from_row(tuple(row)) for row in cursor.fetchall()]

    def list_pending(self) -> list[ApprovalRequest]:
        """List all pending approval requests."""
        return self.list_requests(status=ApprovalStatus.PENDING)

    def list_approvals_needing_recheck(self) -> list[ApprovalRequest]:
        """List approved requests that have reached their planned_end_date and need rechecking.

        Returns approvals where:
        - recheck_status = 'pending'
        - planned_end_date is today or in the past
        """
        now = datetime.now().date().isoformat()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, patient_id, patient_mrn, patient_name, patient_location,
                       antibiotic_name, antibiotic_dose, antibiotic_route,
                       indication, duration_requested_hours,
                       prescriber_name, prescriber_pager, clinical_context,
                       decision, decision_by, decision_at, decision_notes,
                       alternative_recommended,
                       approval_duration_hours, planned_end_date, is_reapproval,
                       parent_approval_id, approval_chain_count, recheck_status,
                       last_recheck_date,
                       status, created_at, created_by
                FROM abx_approval_requests
                WHERE recheck_status = 'pending'
                  AND date(planned_end_date) <= ?
                ORDER BY planned_end_date ASC
                """,
                (now,)
            )

            return [ApprovalRequest.from_row(tuple(row)) for row in cursor.fetchall()]

    def get_audit_log(self, approval_id: str) -> list[ApprovalAuditEntry]:
        """Get audit history for an approval request."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, approval_id, action, performed_by, performed_at, details
                FROM abx_approval_audit
                WHERE approval_id = ?
                ORDER BY performed_at ASC
                """,
                (approval_id,)
            )

            return [ApprovalAuditEntry.from_row(tuple(row)) for row in cursor.fetchall()]

    # Statistics

    def get_stats(
        self,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get approval statistics.

        Args:
            days: Number of days to include in analysis
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            stats: dict[str, Any] = {"period_days": days}

            # Total in period
            cursor = conn.execute(
                "SELECT COUNT(*) FROM abx_approval_requests WHERE created_at >= ?",
                (cutoff,)
            )
            stats["total"] = cursor.fetchone()[0]

            # Pending count (all time)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM abx_approval_requests WHERE status = ?",
                (ApprovalStatus.PENDING.value,)
            )
            stats["pending"] = cursor.fetchone()[0]

            # Today's count
            today = datetime.now().date().isoformat()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM abx_approval_requests WHERE date(created_at) = ?",
                (today,)
            )
            stats["today"] = cursor.fetchone()[0]

            # Count by decision (in period)
            cursor = conn.execute(
                """
                SELECT decision, COUNT(*) FROM abx_approval_requests
                WHERE created_at >= ? AND decision IS NOT NULL
                GROUP BY decision
                """,
                (cutoff,)
            )
            stats["by_decision"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Count by antibiotic (top 10 in period)
            cursor = conn.execute(
                """
                SELECT antibiotic_name, COUNT(*) as cnt
                FROM abx_approval_requests
                WHERE created_at >= ?
                GROUP BY antibiotic_name
                ORDER BY cnt DESC
                LIMIT 10
                """,
                (cutoff,)
            )
            stats["by_antibiotic"] = [
                {"name": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]

            return stats

    def get_analytics(
        self,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get comprehensive analytics for reporting.

        Args:
            days: Number of days to include in analysis

        Returns:
            Dictionary with analytics data
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            analytics: dict[str, Any] = {"period_days": days}

            # Total requests in period
            cursor = conn.execute(
                "SELECT COUNT(*) FROM abx_approval_requests WHERE created_at >= ?",
                (cutoff,)
            )
            analytics["total_requests"] = cursor.fetchone()[0]

            # Requests by day
            cursor = conn.execute(
                """
                SELECT date(created_at) as day, COUNT(*) as count
                FROM abx_approval_requests
                WHERE created_at >= ?
                GROUP BY date(created_at)
                ORDER BY day DESC
                """,
                (cutoff,)
            )
            analytics["requests_by_day"] = [
                {"date": row[0], "count": row[1]} for row in cursor.fetchall()
            ]

            # Average per day
            if analytics["requests_by_day"]:
                analytics["avg_requests_per_day"] = round(
                    analytics["total_requests"] / len(analytics["requests_by_day"]), 1
                )
            else:
                analytics["avg_requests_per_day"] = 0

            # Decision breakdown
            cursor = conn.execute(
                """
                SELECT decision, COUNT(*) as count
                FROM abx_approval_requests
                WHERE created_at >= ? AND status = 'completed' AND decision IS NOT NULL
                GROUP BY decision
                ORDER BY count DESC
                """,
                (cutoff,)
            )
            decision_data = cursor.fetchall()
            total_decided = sum(row[1] for row in decision_data)
            analytics["decision_breakdown"] = [
                {
                    "decision": row[0],
                    "display": ApprovalDecision.display_name(row[0]),
                    "count": row[1],
                    "percentage": round(row[1] / total_decided * 100, 1) if total_decided > 0 else 0
                }
                for row in decision_data
            ]
            analytics["total_decided"] = total_decided

            # Approval rate
            approved = next(
                (d["count"] for d in analytics["decision_breakdown"] if d["decision"] == "approved"),
                0
            )
            if total_decided > 0:
                analytics["approval_rate"] = round(approved / total_decided * 100, 1)
            else:
                analytics["approval_rate"] = 0

            # Top antibiotics
            cursor = conn.execute(
                """
                SELECT antibiotic_name, COUNT(*) as count
                FROM abx_approval_requests
                WHERE created_at >= ?
                GROUP BY antibiotic_name
                ORDER BY count DESC
                LIMIT 10
                """,
                (cutoff,)
            )
            analytics["top_antibiotics"] = [
                {"name": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]

            # Response time metrics (time from creation to decision)
            cursor = conn.execute(
                """
                SELECT
                    AVG(CAST((julianday(decision_at) - julianday(created_at)) * 24 * 60 AS INTEGER)) as avg_min,
                    MIN(CAST((julianday(decision_at) - julianday(created_at)) * 24 * 60 AS INTEGER)) as min_min,
                    MAX(CAST((julianday(decision_at) - julianday(created_at)) * 24 * 60 AS INTEGER)) as max_min
                FROM abx_approval_requests
                WHERE created_at >= ?
                  AND status = 'completed'
                  AND decision_at IS NOT NULL
                """,
                (cutoff,)
            )
            row = cursor.fetchone()
            analytics["response_times"] = {
                "avg_minutes": round(row[0]) if row[0] else None,
                "min_minutes": round(row[1]) if row[1] else None,
                "max_minutes": round(row[2]) if row[2] else None,
            }

            # Format response times
            def format_duration(minutes):
                if minutes is None:
                    return None
                if minutes < 60:
                    return f"{minutes} min"
                hours = minutes // 60
                mins = minutes % 60
                return f"{hours}h {mins}m" if mins else f"{hours}h"

            analytics["response_times_formatted"] = {
                "avg": format_duration(analytics["response_times"]["avg_minutes"]),
                "min": format_duration(analytics["response_times"]["min_minutes"]),
                "max": format_duration(analytics["response_times"]["max_minutes"]),
            }

            # By day of week
            cursor = conn.execute(
                """
                SELECT
                    CASE CAST(strftime('%w', created_at) AS INTEGER)
                        WHEN 0 THEN 'Sunday'
                        WHEN 1 THEN 'Monday'
                        WHEN 2 THEN 'Tuesday'
                        WHEN 3 THEN 'Wednesday'
                        WHEN 4 THEN 'Thursday'
                        WHEN 5 THEN 'Friday'
                        WHEN 6 THEN 'Saturday'
                    END as day_name,
                    COUNT(*) as count
                FROM abx_approval_requests
                WHERE created_at >= ?
                GROUP BY strftime('%w', created_at)
                ORDER BY CAST(strftime('%w', created_at) AS INTEGER)
                """,
                (cutoff,)
            )
            analytics["by_day_of_week"] = [
                {"day": row[0], "count": row[1]} for row in cursor.fetchall()
            ]

            # Re-approval metrics
            # Total re-approval requests
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM abx_approval_requests
                WHERE created_at >= ? AND is_reapproval = 1
                """,
                (cutoff,)
            )
            analytics["total_reapprovals"] = cursor.fetchone()[0]

            # Re-approval rate (percentage of all requests)
            if analytics["total_requests"] > 0:
                analytics["reapproval_rate"] = round(
                    analytics["total_reapprovals"] / analytics["total_requests"] * 100, 1
                )
            else:
                analytics["reapproval_rate"] = 0

            # Average approval chain length
            cursor = conn.execute(
                """
                SELECT AVG(approval_chain_count) FROM abx_approval_requests
                WHERE created_at >= ? AND is_reapproval = 1
                """,
                (cutoff,)
            )
            avg_chain = cursor.fetchone()[0]
            analytics["avg_chain_length"] = round(avg_chain, 1) if avg_chain else 0

            # Max approval chain count
            cursor = conn.execute(
                """
                SELECT MAX(approval_chain_count) FROM abx_approval_requests
                WHERE created_at >= ? AND is_reapproval = 1
                """,
                (cutoff,)
            )
            max_chain = cursor.fetchone()[0]
            analytics["max_chain_length"] = max_chain if max_chain else 0

            # Most frequently re-approved antibiotics
            cursor = conn.execute(
                """
                SELECT antibiotic_name, COUNT(*) as count
                FROM abx_approval_requests
                WHERE created_at >= ? AND is_reapproval = 1
                GROUP BY antibiotic_name
                ORDER BY count DESC
                LIMIT 10
                """,
                (cutoff,)
            )
            analytics["most_reapproved_antibiotics"] = [
                {"name": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]

            # Recheck status breakdown
            cursor = conn.execute(
                """
                SELECT recheck_status, COUNT(*) as count
                FROM abx_approval_requests
                WHERE created_at >= ?
                  AND decision = 'approved'
                  AND recheck_status IS NOT NULL
                GROUP BY recheck_status
                """,
                (cutoff,)
            )
            analytics["recheck_status_breakdown"] = [
                {"status": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]

            # Average approval duration for approved requests
            cursor = conn.execute(
                """
                SELECT AVG(approval_duration_hours) FROM abx_approval_requests
                WHERE created_at >= ?
                  AND decision = 'approved'
                  AND approval_duration_hours IS NOT NULL
                """,
                (cutoff,)
            )
            avg_duration = cursor.fetchone()[0]
            analytics["avg_approval_duration_hours"] = round(avg_duration) if avg_duration else None
            if avg_duration:
                analytics["avg_approval_duration_days"] = round(avg_duration / 24, 1)

            # Compliance rate (how many actually stopped at approved duration)
            cursor = conn.execute(
                """
                SELECT
                    COUNT(CASE WHEN recheck_status = 'completed' THEN 1 END) as stopped,
                    COUNT(CASE WHEN recheck_status = 'extended' THEN 1 END) as continued,
                    COUNT(*) as total
                FROM abx_approval_requests
                WHERE created_at >= ?
                  AND decision = 'approved'
                  AND recheck_status IN ('completed', 'extended')
                """,
                (cutoff,)
            )
            compliance_row = cursor.fetchone()
            if compliance_row and compliance_row[2] > 0:
                analytics["compliance_rate"] = round(compliance_row[0] / compliance_row[2] * 100, 1)
                analytics["compliance_stopped"] = compliance_row[0]
                analytics["compliance_continued"] = compliance_row[1]
                analytics["compliance_total"] = compliance_row[2]
            else:
                analytics["compliance_rate"] = None
                analytics["compliance_stopped"] = 0
                analytics["compliance_continued"] = 0
                analytics["compliance_total"] = 0

            return analytics

    # Cleanup

    def cleanup_old_completed(self, days: int = 365) -> int:
        """Remove completed requests older than specified days.

        Returns number of requests removed.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            # First delete audit entries
            conn.execute(
                """
                DELETE FROM abx_approval_audit
                WHERE approval_id IN (
                    SELECT id FROM abx_approval_requests
                    WHERE status = ? AND decision_at < ?
                )
                """,
                (ApprovalStatus.COMPLETED.value, cutoff)
            )

            # Then delete requests
            cursor = conn.execute(
                "DELETE FROM abx_approval_requests WHERE status = ? AND decision_at < ?",
                (ApprovalStatus.COMPLETED.value, cutoff)
            )

            conn.commit()
            count = cursor.rowcount

            if count > 0:
                logger.info(f"Cleaned up {count} old completed approval requests")

            return count
