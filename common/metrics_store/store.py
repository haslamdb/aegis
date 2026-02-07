"""SQLite-backed storage for unified metrics and activity tracking."""

import json
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

from .models import (
    ActivityType,
    ModuleSource,
    InterventionType,
    TargetType,
    TargetStatus,
    IssueType,
    ProviderActivity,
    InterventionSession,
    DailySnapshot,
    InterventionTarget,
    InterventionOutcome,
)

logger = logging.getLogger(__name__)


class MetricsStore:
    """SQLite-backed storage for ASP/IP metrics and activity tracking."""

    def __init__(self, db_path: str | None = None):
        """Initialize metrics store.

        Args:
            db_path: Path to SQLite database. Defaults to METRICS_DB_PATH env var
                     or ~/.aegis/metrics.db
        """
        if db_path:
            self.db_path = os.path.expanduser(db_path)
        else:
            self.db_path = os.path.expanduser(
                os.environ.get("METRICS_DB_PATH", "~/.aegis/metrics.db")
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

    # =========================================================================
    # Provider Activity Operations
    # =========================================================================

    def log_activity(
        self,
        activity_type: ActivityType | str,
        module: ModuleSource | str,
        provider_id: str | None = None,
        provider_name: str | None = None,
        provider_role: str | None = None,
        entity_id: str | None = None,
        entity_type: str | None = None,
        action_taken: str | None = None,
        outcome: str | None = None,
        patient_mrn: str | None = None,
        location_code: str | None = None,
        service: str | None = None,
        duration_minutes: int | None = None,
        details: dict | None = None,
    ) -> int:
        """Log a provider activity.

        Args:
            activity_type: Type of activity (review, acknowledgment, etc.)
            module: Source module
            provider_id: Provider badge ID or identifier
            provider_name: Provider display name
            provider_role: Provider role (pharmacist, physician, etc.)
            entity_id: ID of the entity being acted upon
            entity_type: Type of entity (alert, candidate, etc.)
            action_taken: Specific action taken
            outcome: Result of the action
            patient_mrn: Patient MRN if applicable
            location_code: Unit/ward code
            service: Medical service
            duration_minutes: Time spent on activity
            details: Additional context as dict

        Returns:
            ID of the created activity record
        """
        now = datetime.now()
        activity_type_val = activity_type.value if isinstance(activity_type, ActivityType) else activity_type
        module_val = module.value if isinstance(module, ModuleSource) else module
        details_json = json.dumps(details) if details else None

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO provider_activity (
                    provider_id, provider_name, provider_role,
                    activity_type, module, entity_id, entity_type,
                    action_taken, outcome, patient_mrn, location_code,
                    service, duration_minutes, performed_at, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider_id, provider_name, provider_role,
                    activity_type_val, module_val, entity_id, entity_type,
                    action_taken, outcome, patient_mrn, location_code,
                    service, duration_minutes, now.isoformat(), details_json
                )
            )
            conn.commit()
            activity_id = cursor.lastrowid

        logger.debug(
            f"Logged activity: {activity_type_val} in {module_val} by {provider_name or provider_id}"
        )
        return activity_id

    def get_activity(self, activity_id: int) -> ProviderActivity | None:
        """Get a single activity by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM provider_activity WHERE id = ?",
                (activity_id,)
            )
            row = cursor.fetchone()
            if row:
                return ProviderActivity.from_row(row)
            return None

    def list_activities(
        self,
        provider_id: str | None = None,
        module: ModuleSource | str | None = None,
        activity_type: ActivityType | str | None = None,
        location_code: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[ProviderActivity]:
        """List activities with optional filters.

        Args:
            provider_id: Filter by provider
            module: Filter by module
            activity_type: Filter by activity type
            location_code: Filter by location
            start_date: Filter activities on or after this date
            end_date: Filter activities on or before this date
            limit: Maximum results

        Returns:
            List of matching activities
        """
        conditions = []
        params: list[Any] = []

        if provider_id:
            conditions.append("provider_id = ?")
            params.append(provider_id)

        if module:
            module_val = module.value if isinstance(module, ModuleSource) else module
            conditions.append("module = ?")
            params.append(module_val)

        if activity_type:
            type_val = activity_type.value if isinstance(activity_type, ActivityType) else activity_type
            conditions.append("activity_type = ?")
            params.append(type_val)

        if location_code:
            conditions.append("location_code = ?")
            params.append(location_code)

        if start_date:
            conditions.append("date(performed_at) >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("date(performed_at) <= ?")
            params.append(end_date.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM provider_activity
                WHERE {where_clause}
                ORDER BY performed_at DESC
                LIMIT ?
                """,
                params
            )
            return [ProviderActivity.from_row(row) for row in cursor.fetchall()]

    def get_provider_workload(
        self,
        days: int = 30,
        provider_id: str | None = None,
    ) -> list[dict]:
        """Get workload summary by provider.

        Args:
            days: Number of days to include
            provider_id: Optional filter to single provider

        Returns:
            List of dicts with provider workload stats
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        params: list[Any] = [cutoff]

        provider_filter = ""
        if provider_id:
            provider_filter = " AND provider_id = ?"
            params.append(provider_id)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT
                    provider_id,
                    provider_name,
                    provider_role,
                    COUNT(*) as total_activities,
                    COUNT(DISTINCT date(performed_at)) as active_days,
                    SUM(CASE WHEN activity_type = 'review' THEN 1 ELSE 0 END) as reviews,
                    SUM(CASE WHEN activity_type = 'acknowledgment' THEN 1 ELSE 0 END) as acknowledgments,
                    SUM(CASE WHEN activity_type = 'resolution' THEN 1 ELSE 0 END) as resolutions,
                    SUM(CASE WHEN activity_type = 'intervention' THEN 1 ELSE 0 END) as interventions,
                    SUM(COALESCE(duration_minutes, 0)) as total_minutes
                FROM provider_activity
                WHERE date(performed_at) >= ?{provider_filter}
                GROUP BY provider_id, provider_name, provider_role
                ORDER BY total_activities DESC
                """,
                params
            )

            results = []
            for row in cursor.fetchall():
                results.append({
                    "provider_id": row["provider_id"],
                    "provider_name": row["provider_name"],
                    "provider_role": row["provider_role"],
                    "total_activities": row["total_activities"],
                    "active_days": row["active_days"],
                    "reviews": row["reviews"],
                    "acknowledgments": row["acknowledgments"],
                    "resolutions": row["resolutions"],
                    "interventions": row["interventions"],
                    "total_minutes": row["total_minutes"],
                    "avg_per_day": round(row["total_activities"] / max(row["active_days"], 1), 1),
                })
            return results

    def get_activity_by_location(
        self,
        days: int = 30,
    ) -> list[dict]:
        """Get activity summary by location.

        Args:
            days: Number of days to include

        Returns:
            List of dicts with location activity stats
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT
                    location_code,
                    COUNT(*) as total_activities,
                    COUNT(DISTINCT provider_id) as unique_providers,
                    SUM(CASE WHEN activity_type = 'review' THEN 1 ELSE 0 END) as reviews,
                    SUM(CASE WHEN activity_type = 'intervention' THEN 1 ELSE 0 END) as interventions
                FROM provider_activity
                WHERE date(performed_at) >= ? AND location_code IS NOT NULL
                GROUP BY location_code
                ORDER BY total_activities DESC
                """,
                (cutoff,)
            )

            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Intervention Session Operations
    # =========================================================================

    def create_intervention_session(
        self,
        session_type: InterventionType | str,
        session_date: date,
        target_type: TargetType | str,
        target_id: str | None = None,
        target_name: str | None = None,
        topic: str | None = None,
        attendees: list[str] | None = None,
        notes: str | None = None,
        related_alerts: list[str] | None = None,
        related_targets: list[int] | None = None,
        conducted_by: str | None = None,
    ) -> int:
        """Create a new intervention session.

        Returns:
            ID of the created session
        """
        now = datetime.now()
        session_type_val = session_type.value if isinstance(session_type, InterventionType) else session_type
        target_type_val = target_type.value if isinstance(target_type, TargetType) else target_type

        attendees_json = json.dumps(attendees) if attendees else None
        related_alerts_json = json.dumps(related_alerts) if related_alerts else None
        related_targets_json = json.dumps(related_targets) if related_targets else None

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO intervention_sessions (
                    session_type, session_date, target_type, target_id, target_name,
                    topic, attendees, notes, related_alerts, related_targets,
                    conducted_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_type_val, session_date.isoformat(), target_type_val,
                    target_id, target_name, topic, attendees_json, notes,
                    related_alerts_json, related_targets_json, conducted_by,
                    now.isoformat(), now.isoformat()
                )
            )
            conn.commit()
            session_id = cursor.lastrowid

        logger.info(f"Created intervention session {session_id}: {session_type_val} for {target_name}")
        return session_id

    def get_intervention_session(self, session_id: int) -> InterventionSession | None:
        """Get a single intervention session by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM intervention_sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                return InterventionSession.from_row(row)
            return None

    def list_intervention_sessions(
        self,
        session_type: InterventionType | str | None = None,
        target_type: TargetType | str | None = None,
        target_id: str | None = None,
        conducted_by: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[InterventionSession]:
        """List intervention sessions with optional filters."""
        conditions = []
        params: list[Any] = []

        if session_type:
            type_val = session_type.value if isinstance(session_type, InterventionType) else session_type
            conditions.append("session_type = ?")
            params.append(type_val)

        if target_type:
            target_val = target_type.value if isinstance(target_type, TargetType) else target_type
            conditions.append("target_type = ?")
            params.append(target_val)

        if target_id:
            conditions.append("target_id = ?")
            params.append(target_id)

        if conducted_by:
            conditions.append("conducted_by = ?")
            params.append(conducted_by)

        if start_date:
            conditions.append("session_date >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("session_date <= ?")
            params.append(end_date.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM intervention_sessions
                WHERE {where_clause}
                ORDER BY session_date DESC
                LIMIT ?
                """,
                params
            )
            return [InterventionSession.from_row(row) for row in cursor.fetchall()]

    def update_intervention_session(
        self,
        session_id: int,
        topic: str | None = None,
        attendees: list[str] | None = None,
        notes: str | None = None,
        related_alerts: list[str] | None = None,
        related_targets: list[int] | None = None,
    ) -> bool:
        """Update an intervention session.

        Returns:
            True if updated successfully
        """
        updates = []
        params: list[Any] = []

        if topic is not None:
            updates.append("topic = ?")
            params.append(topic)

        if attendees is not None:
            updates.append("attendees = ?")
            params.append(json.dumps(attendees))

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)

        if related_alerts is not None:
            updates.append("related_alerts = ?")
            params.append(json.dumps(related_alerts))

        if related_targets is not None:
            updates.append("related_targets = ?")
            params.append(json.dumps(related_targets))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(session_id)

        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE intervention_sessions SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Daily Snapshot Operations
    # =========================================================================

    def save_daily_snapshot(self, snapshot: DailySnapshot) -> int:
        """Save or update a daily snapshot.

        Uses INSERT OR REPLACE to handle updates.

        Returns:
            ID of the snapshot
        """
        now = datetime.now()
        by_location_json = json.dumps(snapshot.by_location) if snapshot.by_location else None
        by_service_json = json.dumps(snapshot.by_service) if snapshot.by_service else None

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO metrics_daily_snapshot (
                    snapshot_date,
                    alerts_created, alerts_resolved, alerts_acknowledged,
                    avg_time_to_ack_minutes, avg_time_to_resolve_minutes,
                    hai_candidates_created, hai_candidates_reviewed, hai_confirmed, hai_override_count,
                    bundle_episodes_active, bundle_alerts_created, bundle_adherence_rate,
                    indication_reviews, appropriate_count, inappropriate_count, inappropriate_rate,
                    drug_bug_alerts_created, drug_bug_alerts_resolved, drug_bug_therapy_changed_count,
                    mdro_cases_identified, mdro_cases_reviewed, mdro_confirmed,
                    outbreak_clusters_active, outbreak_alerts_triggered,
                    surgical_prophylaxis_cases, surgical_prophylaxis_compliant, surgical_prophylaxis_compliance_rate,
                    llm_extractions_total, llm_accepted_count, llm_modified_count,
                    llm_overridden_count, llm_acceptance_rate, llm_override_rate, llm_avg_confidence,
                    total_reviews, unique_reviewers, total_interventions,
                    by_location, by_service, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_date.isoformat(),
                    snapshot.alerts_created, snapshot.alerts_resolved, snapshot.alerts_acknowledged,
                    snapshot.avg_time_to_ack_minutes, snapshot.avg_time_to_resolve_minutes,
                    snapshot.hai_candidates_created, snapshot.hai_candidates_reviewed,
                    snapshot.hai_confirmed, snapshot.hai_override_count,
                    snapshot.bundle_episodes_active, snapshot.bundle_alerts_created,
                    snapshot.bundle_adherence_rate,
                    snapshot.indication_reviews, snapshot.appropriate_count,
                    snapshot.inappropriate_count, snapshot.inappropriate_rate,
                    snapshot.drug_bug_alerts_created, snapshot.drug_bug_alerts_resolved,
                    snapshot.drug_bug_therapy_changed_count,
                    snapshot.mdro_cases_identified, snapshot.mdro_cases_reviewed,
                    snapshot.mdro_confirmed,
                    snapshot.outbreak_clusters_active, snapshot.outbreak_alerts_triggered,
                    snapshot.surgical_prophylaxis_cases, snapshot.surgical_prophylaxis_compliant,
                    snapshot.surgical_prophylaxis_compliance_rate,
                    snapshot.llm_extractions_total, snapshot.llm_accepted_count,
                    snapshot.llm_modified_count, snapshot.llm_overridden_count,
                    snapshot.llm_acceptance_rate, snapshot.llm_override_rate,
                    snapshot.llm_avg_confidence,
                    snapshot.total_reviews, snapshot.unique_reviewers, snapshot.total_interventions,
                    by_location_json, by_service_json, now.isoformat()
                )
            )
            conn.commit()
            return cursor.lastrowid

    def get_daily_snapshot(self, snapshot_date: date) -> DailySnapshot | None:
        """Get snapshot for a specific date."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM metrics_daily_snapshot WHERE snapshot_date = ?",
                (snapshot_date.isoformat(),)
            )
            row = cursor.fetchone()
            if row:
                return DailySnapshot.from_row(row)
            return None

    def list_daily_snapshots(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 90,
    ) -> list[DailySnapshot]:
        """List daily snapshots in date range."""
        conditions = []
        params: list[Any] = []

        if start_date:
            conditions.append("snapshot_date >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("snapshot_date <= ?")
            params.append(end_date.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM metrics_daily_snapshot
                WHERE {where_clause}
                ORDER BY snapshot_date DESC
                LIMIT ?
                """,
                params
            )
            return [DailySnapshot.from_row(row) for row in cursor.fetchall()]

    # =========================================================================
    # Intervention Target Operations
    # =========================================================================

    def create_intervention_target(
        self,
        target_type: TargetType | str,
        target_id: str,
        issue_type: IssueType | str,
        target_name: str | None = None,
        issue_description: str | None = None,
        priority_score: float | None = None,
        priority_reason: str | None = None,
        baseline_value: float | None = None,
        target_value: float | None = None,
        metric_name: str | None = None,
        metric_unit: str | None = None,
        identified_date: date | None = None,
    ) -> int:
        """Create a new intervention target.

        Returns:
            ID of the created target
        """
        now = datetime.now()
        target_type_val = target_type.value if isinstance(target_type, TargetType) else target_type
        issue_type_val = issue_type.value if isinstance(issue_type, IssueType) else issue_type
        identified = identified_date or date.today()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO intervention_targets (
                    target_type, target_id, target_name, issue_type, issue_description,
                    priority_score, priority_reason, baseline_value, target_value,
                    current_value, metric_name, metric_unit, status, identified_date,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_type_val, target_id, target_name, issue_type_val, issue_description,
                    priority_score, priority_reason, baseline_value, target_value,
                    baseline_value,  # current_value starts at baseline
                    metric_name, metric_unit, TargetStatus.IDENTIFIED.value,
                    identified.isoformat(), now.isoformat(), now.isoformat()
                )
            )
            conn.commit()
            target_id_int = cursor.lastrowid

        logger.info(f"Created intervention target {target_id_int}: {issue_type_val} for {target_name}")
        return target_id_int

    def get_intervention_target(self, target_id: int) -> InterventionTarget | None:
        """Get a single intervention target by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM intervention_targets WHERE id = ?",
                (target_id,)
            )
            row = cursor.fetchone()
            if row:
                return InterventionTarget.from_row(row)
            return None

    def list_intervention_targets(
        self,
        status: TargetStatus | str | list[TargetStatus | str] | None = None,
        target_type: TargetType | str | None = None,
        issue_type: IssueType | str | None = None,
        assigned_to: str | None = None,
        limit: int = 100,
    ) -> list[InterventionTarget]:
        """List intervention targets with optional filters."""
        conditions = []
        params: list[Any] = []

        if status:
            if isinstance(status, list):
                placeholders = ",".join("?" * len(status))
                conditions.append(f"status IN ({placeholders})")
                for s in status:
                    params.append(s.value if isinstance(s, TargetStatus) else s)
            else:
                status_val = status.value if isinstance(status, TargetStatus) else status
                conditions.append("status = ?")
                params.append(status_val)

        if target_type:
            type_val = target_type.value if isinstance(target_type, TargetType) else target_type
            conditions.append("target_type = ?")
            params.append(type_val)

        if issue_type:
            issue_val = issue_type.value if isinstance(issue_type, IssueType) else issue_type
            conditions.append("issue_type = ?")
            params.append(issue_val)

        if assigned_to:
            conditions.append("assigned_to = ?")
            params.append(assigned_to)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM intervention_targets
                WHERE {where_clause}
                ORDER BY priority_score DESC NULLS LAST, identified_date DESC
                LIMIT ?
                """,
                params
            )
            return [InterventionTarget.from_row(row) for row in cursor.fetchall()]

    def update_intervention_target(
        self,
        target_id: int,
        status: TargetStatus | str | None = None,
        assigned_to: str | None = None,
        current_value: float | None = None,
        planned_date: date | None = None,
        started_date: date | None = None,
        completed_date: date | None = None,
    ) -> bool:
        """Update an intervention target.

        Returns:
            True if updated successfully
        """
        updates = []
        params: list[Any] = []

        if status is not None:
            status_val = status.value if isinstance(status, TargetStatus) else status
            updates.append("status = ?")
            params.append(status_val)

        if assigned_to is not None:
            updates.append("assigned_to = ?")
            params.append(assigned_to)

        if current_value is not None:
            updates.append("current_value = ?")
            params.append(current_value)

        if planned_date is not None:
            updates.append("planned_date = ?")
            params.append(planned_date.isoformat())

        if started_date is not None:
            updates.append("started_date = ?")
            params.append(started_date.isoformat())

        if completed_date is not None:
            updates.append("completed_date = ?")
            params.append(completed_date.isoformat())

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(target_id)

        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE intervention_targets SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Intervention Outcome Operations
    # =========================================================================

    def create_intervention_outcome(
        self,
        target_id: int,
        pre_period_start: date,
        pre_period_end: date,
        pre_value: float,
        session_id: int | None = None,
        pre_sample_size: int | None = None,
    ) -> int:
        """Create a new intervention outcome record.

        Returns:
            ID of the created outcome
        """
        now = datetime.now()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO intervention_outcomes (
                    target_id, session_id, pre_period_start, pre_period_end,
                    pre_value, pre_sample_size, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id, session_id, pre_period_start.isoformat(),
                    pre_period_end.isoformat(), pre_value, pre_sample_size,
                    now.isoformat(), now.isoformat()
                )
            )
            conn.commit()
            return cursor.lastrowid

    def update_intervention_outcome(
        self,
        outcome_id: int,
        post_period_start: date | None = None,
        post_period_end: date | None = None,
        post_value: float | None = None,
        post_sample_size: int | None = None,
        day_30_value: float | None = None,
        day_60_value: float | None = None,
        day_90_value: float | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update an intervention outcome with post-intervention data.

        Returns:
            True if updated successfully
        """
        # First get the outcome to calculate changes
        outcome = self.get_intervention_outcome(outcome_id)
        if not outcome:
            return False

        updates = []
        params: list[Any] = []

        if post_period_start is not None:
            updates.append("post_period_start = ?")
            params.append(post_period_start.isoformat())

        if post_period_end is not None:
            updates.append("post_period_end = ?")
            params.append(post_period_end.isoformat())

        if post_value is not None:
            updates.append("post_value = ?")
            params.append(post_value)

            # Calculate changes if we have both pre and post values
            if outcome.pre_value is not None:
                absolute_change = post_value - outcome.pre_value
                updates.append("absolute_change = ?")
                params.append(absolute_change)

                if outcome.pre_value != 0:
                    percent_change = (post_value - outcome.pre_value) / outcome.pre_value * 100
                    updates.append("percent_change = ?")
                    params.append(percent_change)

        if post_sample_size is not None:
            updates.append("post_sample_size = ?")
            params.append(post_sample_size)

        if day_30_value is not None:
            updates.append("day_30_value = ?")
            params.append(day_30_value)

        if day_60_value is not None:
            updates.append("day_60_value = ?")
            params.append(day_60_value)

        if day_90_value is not None:
            updates.append("day_90_value = ?")
            params.append(day_90_value)

            # Check for sustained improvement at 90 days
            if outcome.pre_value is not None and outcome.post_value is not None:
                # Assuming lower is better for most metrics
                improvement_at_post = outcome.post_value < outcome.pre_value
                improvement_at_90 = day_90_value < outcome.pre_value
                sustained = improvement_at_post and improvement_at_90
                updates.append("sustained_improvement = ?")
                params.append(1 if sustained else 0)

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(outcome_id)

        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE intervention_outcomes SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_intervention_outcome(self, outcome_id: int) -> InterventionOutcome | None:
        """Get a single outcome by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM intervention_outcomes WHERE id = ?",
                (outcome_id,)
            )
            row = cursor.fetchone()
            if row:
                return InterventionOutcome.from_row(row)
            return None

    def list_intervention_outcomes(
        self,
        target_id: int | None = None,
        session_id: int | None = None,
        is_improvement: bool | None = None,
        limit: int = 100,
    ) -> list[InterventionOutcome]:
        """List intervention outcomes with optional filters."""
        conditions = []
        params: list[Any] = []

        if target_id is not None:
            conditions.append("target_id = ?")
            params.append(target_id)

        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)

        if is_improvement is not None:
            conditions.append("is_improvement = ?")
            params.append(1 if is_improvement else 0)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM intervention_outcomes
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params
            )
            return [InterventionOutcome.from_row(row) for row in cursor.fetchall()]

    # =========================================================================
    # Summary Statistics
    # =========================================================================

    def get_activity_summary(self, days: int = 30) -> dict:
        """Get summary statistics for provider activity.

        Args:
            days: Number of days to include

        Returns:
            Dict with summary statistics
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            summary = {"period_days": days}

            # Total activities
            cursor = conn.execute(
                "SELECT COUNT(*) FROM provider_activity WHERE date(performed_at) >= ?",
                (cutoff,)
            )
            summary["total_activities"] = cursor.fetchone()[0]

            # By activity type
            cursor = conn.execute(
                """
                SELECT activity_type, COUNT(*) as count
                FROM provider_activity
                WHERE date(performed_at) >= ?
                GROUP BY activity_type
                """,
                (cutoff,)
            )
            summary["by_activity_type"] = {row["activity_type"]: row["count"] for row in cursor.fetchall()}

            # By module
            cursor = conn.execute(
                """
                SELECT module, COUNT(*) as count
                FROM provider_activity
                WHERE date(performed_at) >= ?
                GROUP BY module
                """,
                (cutoff,)
            )
            summary["by_module"] = {row["module"]: row["count"] for row in cursor.fetchall()}

            # Unique providers
            cursor = conn.execute(
                "SELECT COUNT(DISTINCT provider_id) FROM provider_activity WHERE date(performed_at) >= ?",
                (cutoff,)
            )
            summary["unique_providers"] = cursor.fetchone()[0]

            # Activities per day
            cursor = conn.execute(
                """
                SELECT date(performed_at) as day, COUNT(*) as count
                FROM provider_activity
                WHERE date(performed_at) >= ?
                GROUP BY date(performed_at)
                ORDER BY day DESC
                """,
                (cutoff,)
            )
            summary["by_day"] = [{"date": row["day"], "count": row["count"]} for row in cursor.fetchall()]

            return summary

    def get_intervention_summary(self, days: int = 90) -> dict:
        """Get summary statistics for intervention targets and sessions.

        Args:
            days: Number of days to include

        Returns:
            Dict with intervention summary
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            summary = {"period_days": days}

            # Target counts by status
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM intervention_targets
                WHERE identified_date >= ?
                GROUP BY status
                """,
                (cutoff,)
            )
            summary["targets_by_status"] = {row["status"]: row["count"] for row in cursor.fetchall()}

            # Target counts by issue type
            cursor = conn.execute(
                """
                SELECT issue_type, COUNT(*) as count
                FROM intervention_targets
                WHERE identified_date >= ?
                GROUP BY issue_type
                """,
                (cutoff,)
            )
            summary["targets_by_issue"] = {row["issue_type"]: row["count"] for row in cursor.fetchall()}

            # Session counts by type
            cursor = conn.execute(
                """
                SELECT session_type, COUNT(*) as count
                FROM intervention_sessions
                WHERE session_date >= ?
                GROUP BY session_type
                """,
                (cutoff,)
            )
            summary["sessions_by_type"] = {row["session_type"]: row["count"] for row in cursor.fetchall()}

            # Total sessions
            cursor = conn.execute(
                "SELECT COUNT(*) FROM intervention_sessions WHERE session_date >= ?",
                (cutoff,)
            )
            summary["total_sessions"] = cursor.fetchone()[0]

            # Outcome success rate
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_improvement = 1 THEN 1 ELSE 0 END) as improved,
                    SUM(CASE WHEN sustained_improvement = 1 THEN 1 ELSE 0 END) as sustained
                FROM intervention_outcomes
                WHERE created_at >= ?
                """,
                (cutoff,)
            )
            row = cursor.fetchone()
            total = row["total"] or 0
            summary["outcomes"] = {
                "total": total,
                "improved": row["improved"] or 0,
                "sustained": row["sustained"] or 0,
                "improvement_rate": round((row["improved"] or 0) / total * 100, 1) if total > 0 else 0,
                "sustained_rate": round((row["sustained"] or 0) / total * 100, 1) if total > 0 else 0,
            }

            return summary
