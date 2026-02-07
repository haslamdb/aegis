"""SQLite-backed storage for dosing verification alerts."""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    DoseAlertRecord,
    DoseAlertSeverity,
    DoseAlertStatus,
    DoseFlag,
    DoseResolution,
)

logger = logging.getLogger(__name__)


def _log_dosing_activity(
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
            module=ModuleSource.DOSING_VERIFICATION,
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


class DoseAlertStore:
    """SQLite-backed store for dosing verification alerts."""

    def __init__(self, db_path: str | None = None):
        """Initialize dose alert store.

        Args:
            db_path: Path to SQLite database. Defaults to DOSE_ALERT_DB_PATH env var
                     or ~/.aegis/dose_alerts.db
        """
        if db_path:
            self.db_path = os.path.expanduser(db_path)
        else:
            self.db_path = os.path.expanduser(
                os.environ.get("DOSE_ALERT_DB_PATH", "~/.aegis/dose_alerts.db")
            )

        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

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
        """Generate a unique alert ID."""
        return f"DA-{uuid.uuid4().hex[:8].upper()}"

    def _audit(
        self,
        alert_id: str,
        action: str,
        performed_by: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log action to audit trail."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dose_alert_audit (alert_id, action, performed_by, details)
                VALUES (?, ?, ?, ?)
                """,
                (alert_id, action, performed_by, details),
            )

    # --- CRUD ---

    def save_alert(
        self,
        assessment_id: str,
        patient_id: str,
        patient_mrn: str,
        patient_name: str,
        flag: DoseFlag,
        patient_factors: dict,
        assessment_details: dict,
        encounter_id: str | None = None,
    ) -> DoseAlertRecord:
        """Save a new dose alert.

        Args:
            assessment_id: Assessment ID from DoseAssessment
            patient_id: FHIR Patient resource ID
            patient_mrn: Patient MRN
            patient_name: Patient display name
            flag: DoseFlag that triggered the alert
            patient_factors: Dict with patient clinical data
            assessment_details: Full assessment details
            encounter_id: FHIR Encounter resource ID

        Returns:
            The created DoseAlertRecord
        """
        alert_id = self._generate_id()
        now = datetime.now().isoformat()

        patient_factors_json = json.dumps(patient_factors)
        assessment_json = json.dumps(assessment_details)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dose_alerts (
                    id, assessment_id, patient_id, patient_mrn, patient_name, encounter_id,
                    drug, indication, flag_type, severity, message,
                    expected_dose, actual_dose, rule_source,
                    patient_factors, assessment_details,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    assessment_id,
                    patient_id,
                    patient_mrn,
                    patient_name,
                    encounter_id,
                    flag.drug,
                    flag.indication,
                    flag.flag_type.value,
                    flag.severity.value,
                    flag.message,
                    flag.expected,
                    flag.actual,
                    flag.rule_source,
                    patient_factors_json,
                    assessment_json,
                    DoseAlertStatus.PENDING.value,
                    now,
                ),
            )

        self._audit(alert_id, "created", details=f"Alert created for {flag.drug}")

        # Log to metrics store
        _log_dosing_activity(
            activity_type="review",
            entity_id=alert_id,
            entity_type="dose_alert",
            action_taken="created",
            patient_mrn=patient_mrn,
            details={
                "drug": flag.drug,
                "flag_type": flag.flag_type.value,
                "severity": flag.severity.value,
            },
        )

        return self.get_alert(alert_id)

    def get_alert(self, alert_id: str) -> DoseAlertRecord | None:
        """Get alert by ID.

        Args:
            alert_id: Alert ID

        Returns:
            DoseAlertRecord or None if not found
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dose_alerts WHERE id = ?", (alert_id,)
            ).fetchone()

        if not row:
            return None

        return DoseAlertRecord.from_row(row)

    def check_if_alerted(
        self, patient_mrn: str, drug: str, flag_type: str
    ) -> bool:
        """Check if an active alert already exists for this combination.

        Args:
            patient_mrn: Patient MRN
            drug: Drug name
            flag_type: DoseFlagType value

        Returns:
            True if an active alert exists
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM dose_alerts
                WHERE patient_mrn = ? AND drug = ? AND flag_type = ?
                AND status != 'resolved'
                """,
                (patient_mrn, drug, flag_type),
            ).fetchone()

        return row[0] > 0

    # --- Status transitions ---

    def mark_sent(self, alert_id: str) -> None:
        """Mark alert as sent.

        Args:
            alert_id: Alert ID
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE dose_alerts
                SET status = ?, sent_at = ?
                WHERE id = ?
                """,
                (DoseAlertStatus.SENT.value, now, alert_id),
            )

        self._audit(alert_id, "sent", details="Notification sent")

    def acknowledge(self, alert_id: str, by: str) -> None:
        """Acknowledge an alert.

        Args:
            alert_id: Alert ID
            by: User acknowledging
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE dose_alerts
                SET status = ?, acknowledged_at = ?, acknowledged_by = ?
                WHERE id = ?
                """,
                (DoseAlertStatus.ACKNOWLEDGED.value, now, by, alert_id),
            )

        self._audit(alert_id, "acknowledged", performed_by=by)

        # Log to metrics store
        alert = self.get_alert(alert_id)
        if alert:
            _log_dosing_activity(
                activity_type="acknowledgment",
                entity_id=alert_id,
                entity_type="dose_alert",
                action_taken="acknowledged",
                provider_id=by,
                patient_mrn=alert.patient_mrn,
            )

    def resolve(
        self, alert_id: str, by: str, resolution: str, notes: str = ""
    ) -> None:
        """Resolve an alert.

        Args:
            alert_id: Alert ID
            by: User resolving
            resolution: DoseResolution value
            notes: Resolution notes
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE dose_alerts
                SET status = ?, resolved_at = ?, resolved_by = ?,
                    resolution = ?, resolution_notes = ?
                WHERE id = ?
                """,
                (DoseAlertStatus.RESOLVED.value, now, by, resolution, notes, alert_id),
            )

        self._audit(
            alert_id,
            "resolved",
            performed_by=by,
            details=f"Resolution: {resolution}",
        )

        # Log to metrics store
        alert = self.get_alert(alert_id)
        if alert:
            _log_dosing_activity(
                activity_type="resolution",
                entity_id=alert_id,
                entity_type="dose_alert",
                action_taken="resolved",
                outcome=resolution,
                provider_id=by,
                patient_mrn=alert.patient_mrn,
                details={"resolution_notes": notes},
            )

    def add_note(self, alert_id: str, by: str, note: str) -> None:
        """Add a note to an alert.

        Args:
            alert_id: Alert ID
            by: User adding note
            note: Note text
        """
        with self._connect() as conn:
            # Append to existing notes
            existing = conn.execute(
                "SELECT notes FROM dose_alerts WHERE id = ?", (alert_id,)
            ).fetchone()

            current_notes = existing[0] if existing and existing[0] else ""
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_notes = f"{current_notes}\n[{timestamp}] {by}: {note}".strip()

            conn.execute(
                "UPDATE dose_alerts SET notes = ? WHERE id = ?",
                (new_notes, alert_id),
            )

        self._audit(alert_id, "note_added", performed_by=by, details=note)

    # --- Queries ---

    def list_active(
        self,
        severity: str | None = None,
        flag_type: str | None = None,
        drug: str | None = None,
        mrn: str | None = None,
    ) -> list[DoseAlertRecord]:
        """List active (non-resolved) alerts with optional filters.

        Args:
            severity: Filter by severity
            flag_type: Filter by flag type
            drug: Filter by drug name
            mrn: Filter by patient MRN

        Returns:
            List of DoseAlertRecord
        """
        query = "SELECT * FROM dose_alerts WHERE status != 'resolved'"
        params = []

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        if flag_type:
            query += " AND flag_type = ?"
            params.append(flag_type)

        if drug:
            query += " AND drug = ?"
            params.append(drug)

        if mrn:
            query += " AND patient_mrn = ?"
            params.append(mrn)

        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [DoseAlertRecord.from_row(row) for row in rows]

    def list_resolved(
        self,
        days_back: int = 30,
        resolution: str | None = None,
        severity: str | None = None,
    ) -> list[DoseAlertRecord]:
        """List resolved alerts.

        Args:
            days_back: Number of days to look back
            resolution: Filter by resolution type
            severity: Filter by severity

        Returns:
            List of DoseAlertRecord
        """
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
        query = "SELECT * FROM dose_alerts WHERE status = 'resolved' AND resolved_at >= ?"
        params = [cutoff]

        if resolution:
            query += " AND resolution = ?"
            params.append(resolution)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY resolved_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [DoseAlertRecord.from_row(row) for row in rows]

    def list_by_patient(self, patient_mrn: str) -> list[DoseAlertRecord]:
        """List all alerts for a patient.

        Args:
            patient_mrn: Patient MRN

        Returns:
            List of DoseAlertRecord
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dose_alerts WHERE patient_mrn = ? ORDER BY created_at DESC",
                (patient_mrn,),
            ).fetchall()

        return [DoseAlertRecord.from_row(row) for row in rows]

    # --- Analytics ---

    def get_stats(self) -> dict:
        """Get current alert statistics.

        Returns:
            Dict with counts by status, severity, and flag type
        """
        with self._connect() as conn:
            # By status
            status_rows = conn.execute(
                "SELECT status, COUNT(*) FROM dose_alerts GROUP BY status"
            ).fetchall()
            by_status = {row[0]: row[1] for row in status_rows}

            # By severity (active only)
            severity_rows = conn.execute(
                """
                SELECT severity, COUNT(*)
                FROM dose_alerts
                WHERE status != 'resolved'
                GROUP BY severity
                """
            ).fetchall()
            by_severity = {row[0]: row[1] for row in severity_rows}

            # By flag type (active only)
            flag_rows = conn.execute(
                """
                SELECT flag_type, COUNT(*)
                FROM dose_alerts
                WHERE status != 'resolved'
                GROUP BY flag_type
                """
            ).fetchall()
            by_flag_type = {row[0]: row[1] for row in flag_rows}

            # By drug (active only)
            drug_rows = conn.execute(
                """
                SELECT drug, COUNT(*)
                FROM dose_alerts
                WHERE status != 'resolved'
                GROUP BY drug
                ORDER BY COUNT(*) DESC
                LIMIT 10
                """
            ).fetchall()
            top_drugs = {row[0]: row[1] for row in drug_rows}

        return {
            "by_status": by_status,
            "by_severity": by_severity,
            "by_flag_type": by_flag_type,
            "top_drugs": top_drugs,
            "total_active": sum(v for k, v in by_status.items() if k != "resolved"),
        }

    def get_analytics(self, days: int = 30) -> dict:
        """Get analytics for the specified time period.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with resolution rates, response times, trends
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            # Total created in period
            created = conn.execute(
                "SELECT COUNT(*) FROM dose_alerts WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()[0]

            # Total resolved in period
            resolved = conn.execute(
                "SELECT COUNT(*) FROM dose_alerts WHERE resolved_at >= ?",
                (cutoff,),
            ).fetchone()[0]

            # Resolution breakdown
            resolution_rows = conn.execute(
                """
                SELECT resolution, COUNT(*)
                FROM dose_alerts
                WHERE resolved_at >= ?
                GROUP BY resolution
                """,
                (cutoff,),
            ).fetchall()
            resolution_breakdown = [{"resolution": row[0], "count": row[1]} for row in resolution_rows]

            # Average time to resolution (in hours)
            avg_resolution_time = conn.execute(
                """
                SELECT AVG(
                    CAST((julianday(resolved_at) - julianday(created_at)) * 24 AS REAL)
                )
                FROM dose_alerts
                WHERE resolved_at >= ?
                """,
                (cutoff,),
            ).fetchone()[0]

            # Top drugs by alert count
            top_drugs = conn.execute(
                """
                SELECT drug, COUNT(*) as count,
                       (SELECT flag_type FROM dose_alerts WHERE drug = a.drug AND created_at >= ?
                        GROUP BY flag_type ORDER BY COUNT(*) DESC LIMIT 1) as most_common_flag
                FROM dose_alerts a
                WHERE created_at >= ?
                GROUP BY drug
                ORDER BY count DESC
                LIMIT 10
                """,
                (cutoff, cutoff),
            ).fetchall()
            top_drugs_list = [{"drug": row[0], "count": row[1], "most_common_flag": row[2]} for row in top_drugs]

            # Top flag types
            top_flags = conn.execute(
                """
                SELECT flag_type, COUNT(*) as count
                FROM dose_alerts
                WHERE created_at >= ?
                GROUP BY flag_type
                ORDER BY count DESC
                LIMIT 10
                """,
                (cutoff,),
            ).fetchall()
            top_flags_list = [{"flag_type": row[0], "count": row[1]} for row in top_flags]

            # Most common flag overall
            most_common = conn.execute(
                """
                SELECT flag_type FROM dose_alerts
                WHERE created_at >= ?
                GROUP BY flag_type
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """,
                (cutoff,),
            ).fetchone()
            most_common_flag = most_common[0] if most_common else None

            # Volume by day
            volume_rows = conn.execute(
                """
                SELECT DATE(created_at) as day,
                       SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical,
                       SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high,
                       SUM(CASE WHEN severity = 'moderate' THEN 1 ELSE 0 END) as moderate
                FROM dose_alerts
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY day
                """,
                (cutoff,),
            ).fetchall()
            volume_by_day = [{"date": row[0], "critical": row[1], "high": row[2], "moderate": row[3]} for row in volume_rows]

            # Resolution action counts
            dose_adjusted = sum(1 for r in resolution_breakdown if r["resolution"] == "dose_adjusted")
            interval_adjusted = sum(1 for r in resolution_breakdown if r["resolution"] == "interval_adjusted")
            route_changed = sum(1 for r in resolution_breakdown if r["resolution"] == "route_changed")
            therapy_changed = sum(1 for r in resolution_breakdown if r["resolution"] == "therapy_changed")
            therapy_stopped = sum(1 for r in resolution_breakdown if r["resolution"] == "therapy_stopped")

            # Action rate (dose adjusted + interval adjusted + route/therapy changed)
            action_count = dose_adjusted + interval_adjusted + route_changed + therapy_changed + therapy_stopped
            action_rate = (action_count / resolved * 100) if resolved > 0 else 0

        # Format avg time to resolution
        if avg_resolution_time:
            if avg_resolution_time < 1:
                avg_time_str = f"{int(avg_resolution_time * 60)}m"
            elif avg_resolution_time < 24:
                avg_time_str = f"{avg_resolution_time:.1f}h"
            else:
                avg_time_str = f"{avg_resolution_time / 24:.1f}d"
        else:
            avg_time_str = None

        return {
            "period_days": days,
            "total_alerts": created,
            "alerts_created": created,
            "alerts_resolved": resolved,
            "resolution_rate": (resolved / created * 100) if created > 0 else 0,
            "action_rate": action_rate,
            "resolution_breakdown": resolution_breakdown,
            "avg_resolution_hours": round(avg_resolution_time, 1) if avg_resolution_time else None,
            "avg_time_to_resolution": avg_time_str,
            "top_drugs": top_drugs_list,
            "top_flags": top_flags_list,
            "most_common_flag": most_common_flag,
            "volume_by_day": volume_by_day,
            "dose_adjusted_count": dose_adjusted,
            "interval_adjusted_count": interval_adjusted,
            "route_changed_count": route_changed,
            "therapy_changed_count": therapy_changed,
            "therapy_stopped_count": therapy_stopped,
        }

    # --- Maintenance ---

    def auto_accept_old(self, hours: int = 72) -> int:
        """Auto-accept old unreviewed alerts.

        Args:
            hours: Age threshold in hours

        Returns:
            Number of alerts auto-accepted
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE dose_alerts
                SET status = 'resolved',
                    resolved_at = datetime('now'),
                    resolved_by = 'system',
                    resolution = 'auto_accepted'
                WHERE status = 'pending'
                AND created_at < ?
                """,
                (cutoff,),
            )
            count = result.rowcount

        logger.info(f"Auto-accepted {count} alerts older than {hours} hours")
        return count

    def cleanup_old_resolved(self, days: int = 90) -> int:
        """Delete resolved alerts older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of alerts deleted
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            result = conn.execute(
                """
                DELETE FROM dose_alerts
                WHERE status = 'resolved'
                AND resolved_at < ?
                """,
                (cutoff,),
            )
            count = result.rowcount

        logger.info(f"Cleaned up {count} resolved alerts older than {days} days")
        return count

    # --- Audit ---

    def get_audit_log(self, alert_id: str) -> list[dict]:
        """Get audit log for an alert.

        Args:
            alert_id: Alert ID

        Returns:
            List of audit entries
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT action, performed_by, performed_at, details
                FROM dose_alert_audit
                WHERE alert_id = ?
                ORDER BY performed_at ASC
                """,
                (alert_id,),
            ).fetchall()

        return [
            {
                "action": row[0],
                "performed_by": row[1],
                "performed_at": row[2],
                "details": row[3],
            }
            for row in rows
        ]
