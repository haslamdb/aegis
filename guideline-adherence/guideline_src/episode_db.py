"""Database layer for bundle episode tracking.

Handles persistence of bundle episodes, element results, and alerts.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

from .config import config

logger = logging.getLogger(__name__)


@dataclass
class BundleEpisode:
    """Represents an active bundle monitoring episode."""

    patient_id: str
    encounter_id: str
    bundle_id: str
    bundle_name: str
    trigger_type: str
    trigger_time: datetime

    # Optional fields
    id: Optional[int] = None
    patient_mrn: Optional[str] = None
    trigger_code: Optional[str] = None
    trigger_description: Optional[str] = None
    patient_age_days: Optional[int] = None
    patient_age_months: Optional[float] = None
    patient_weight_kg: Optional[float] = None
    patient_unit: Optional[str] = None

    # Status and adherence
    status: str = "active"
    elements_total: int = 0
    elements_applicable: int = 0
    elements_met: int = 0
    elements_not_met: int = 0
    elements_pending: int = 0
    adherence_percentage: Optional[float] = None
    adherence_level: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ElementResult:
    """Result of checking a single bundle element."""

    episode_id: int
    element_id: str
    element_name: str
    status: str  # 'met', 'not_met', 'pending', 'na', 'unknown'

    # Optional fields
    id: Optional[int] = None
    element_description: Optional[str] = None
    required: bool = True
    time_window_hours: Optional[float] = None
    deadline: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    value: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class BundleAlert:
    """Alert for bundle compliance issues."""

    episode_id: int
    patient_id: str
    encounter_id: str
    bundle_id: str
    bundle_name: str
    alert_type: str  # 'element_overdue', 'element_not_met', 'low_adherence', 'bundle_incomplete'
    severity: str  # 'critical', 'warning', 'info'
    title: str
    message: str

    # Optional fields
    id: Optional[int] = None
    element_result_id: Optional[int] = None
    patient_mrn: Optional[str] = None
    element_id: Optional[str] = None
    element_name: Optional[str] = None
    status: str = "active"
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class BundleTrigger:
    """Configuration for what triggers a bundle."""

    bundle_id: str
    trigger_type: str  # 'diagnosis', 'order', 'lab', 'medication', 'vital'
    trigger_code: Optional[str] = None
    trigger_pattern: Optional[str] = None
    trigger_description: Optional[str] = None
    age_min_days: Optional[int] = None
    age_max_days: Optional[int] = None
    additional_criteria: Optional[str] = None
    active: bool = True
    id: Optional[int] = None


class EpisodeDB:
    """Database operations for bundle episode tracking."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database. Uses config default if not provided.
        """
        self.db_path = db_path or config.ADHERENCE_DB_PATH
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        """Ensure database schema exists."""
        schema_path = Path(__file__).parent.parent / "schema.sql"
        if not schema_path.exists():
            logger.warning(f"Schema file not found: {schema_path}")
            return

        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            with open(schema_path, "r") as f:
                conn.executescript(f.read())
            conn.commit()

    # =========================================================================
    # EPISODE OPERATIONS
    # =========================================================================

    def save_episode(self, episode: BundleEpisode) -> int:
        """Save or update a bundle episode.

        Args:
            episode: BundleEpisode to save.

        Returns:
            Episode ID.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if episode.id:
                # Update existing
                cursor.execute(
                    """
                    UPDATE bundle_episodes SET
                        patient_mrn = ?,
                        trigger_code = ?,
                        trigger_description = ?,
                        patient_age_days = ?,
                        patient_age_months = ?,
                        patient_weight_kg = ?,
                        patient_unit = ?,
                        status = ?,
                        elements_total = ?,
                        elements_applicable = ?,
                        elements_met = ?,
                        elements_not_met = ?,
                        elements_pending = ?,
                        adherence_percentage = ?,
                        adherence_level = ?,
                        completed_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        episode.patient_mrn,
                        episode.trigger_code,
                        episode.trigger_description,
                        episode.patient_age_days,
                        episode.patient_age_months,
                        episode.patient_weight_kg,
                        episode.patient_unit,
                        episode.status,
                        episode.elements_total,
                        episode.elements_applicable,
                        episode.elements_met,
                        episode.elements_not_met,
                        episode.elements_pending,
                        episode.adherence_percentage,
                        episode.adherence_level,
                        episode.completed_at,
                        episode.id,
                    ),
                )
                conn.commit()
                return episode.id
            else:
                # Insert new
                cursor.execute(
                    """
                    INSERT INTO bundle_episodes (
                        patient_id, patient_mrn, encounter_id,
                        bundle_id, bundle_name,
                        trigger_type, trigger_code, trigger_description, trigger_time,
                        patient_age_days, patient_age_months, patient_weight_kg, patient_unit,
                        status, elements_total, elements_applicable, elements_met,
                        elements_not_met, elements_pending, adherence_percentage, adherence_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(patient_id, encounter_id, bundle_id, trigger_time)
                    DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        episode.patient_id,
                        episode.patient_mrn,
                        episode.encounter_id,
                        episode.bundle_id,
                        episode.bundle_name,
                        episode.trigger_type,
                        episode.trigger_code,
                        episode.trigger_description,
                        episode.trigger_time.isoformat() if episode.trigger_time else None,
                        episode.patient_age_days,
                        episode.patient_age_months,
                        episode.patient_weight_kg,
                        episode.patient_unit,
                        episode.status,
                        episode.elements_total,
                        episode.elements_applicable,
                        episode.elements_met,
                        episode.elements_not_met,
                        episode.elements_pending,
                        episode.adherence_percentage,
                        episode.adherence_level,
                    ),
                )
                conn.commit()
                return cursor.lastrowid

    def get_episode(self, episode_id: int) -> Optional[BundleEpisode]:
        """Get episode by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bundle_episodes WHERE id = ?", (episode_id,))
            row = cursor.fetchone()
            return self._row_to_episode(row) if row else None

    def get_active_episode(
        self, patient_id: str, encounter_id: str, bundle_id: str
    ) -> Optional[BundleEpisode]:
        """Get active episode for patient/encounter/bundle combination."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bundle_episodes
                WHERE patient_id = ? AND encounter_id = ? AND bundle_id = ?
                  AND status = 'active'
                ORDER BY trigger_time DESC
                LIMIT 1
                """,
                (patient_id, encounter_id, bundle_id),
            )
            row = cursor.fetchone()
            return self._row_to_episode(row) if row else None

    def get_active_episodes(self, limit: int = 100) -> list[BundleEpisode]:
        """Get all active episodes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bundle_episodes
                WHERE status = 'active'
                ORDER BY trigger_time DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [self._row_to_episode(row) for row in cursor.fetchall()]

    def get_episodes_by_patient(self, patient_id: str) -> list[BundleEpisode]:
        """Get all episodes for a patient."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bundle_episodes
                WHERE patient_id = ?
                ORDER BY trigger_time DESC
                """,
                (patient_id,),
            )
            return [self._row_to_episode(row) for row in cursor.fetchall()]

    def _row_to_episode(self, row: sqlite3.Row) -> BundleEpisode:
        """Convert database row to BundleEpisode."""
        return BundleEpisode(
            id=row["id"],
            patient_id=row["patient_id"],
            patient_mrn=row["patient_mrn"],
            encounter_id=row["encounter_id"],
            bundle_id=row["bundle_id"],
            bundle_name=row["bundle_name"],
            trigger_type=row["trigger_type"],
            trigger_code=row["trigger_code"],
            trigger_description=row["trigger_description"],
            trigger_time=datetime.fromisoformat(row["trigger_time"]) if row["trigger_time"] else None,
            patient_age_days=row["patient_age_days"],
            patient_age_months=row["patient_age_months"],
            patient_weight_kg=row["patient_weight_kg"],
            patient_unit=row["patient_unit"],
            status=row["status"],
            elements_total=row["elements_total"],
            elements_applicable=row["elements_applicable"],
            elements_met=row["elements_met"],
            elements_not_met=row["elements_not_met"],
            elements_pending=row["elements_pending"],
            adherence_percentage=row["adherence_percentage"],
            adherence_level=row["adherence_level"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    # =========================================================================
    # ELEMENT RESULT OPERATIONS
    # =========================================================================

    def save_element_result(self, result: ElementResult) -> int:
        """Save or update an element result.

        Args:
            result: ElementResult to save.

        Returns:
            Result ID.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if result.id:
                # Update existing
                cursor.execute(
                    """
                    UPDATE bundle_element_results SET
                        status = ?,
                        completed_at = ?,
                        value = ?,
                        notes = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        result.status,
                        result.completed_at.isoformat() if result.completed_at else None,
                        result.value,
                        result.notes,
                        result.id,
                    ),
                )
                conn.commit()
                return result.id
            else:
                # Insert or update
                cursor.execute(
                    """
                    INSERT INTO bundle_element_results (
                        episode_id, element_id, element_name, element_description,
                        required, time_window_hours, deadline, status,
                        completed_at, value, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(episode_id, element_id)
                    DO UPDATE SET
                        status = excluded.status,
                        completed_at = excluded.completed_at,
                        value = excluded.value,
                        notes = excluded.notes,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        result.episode_id,
                        result.element_id,
                        result.element_name,
                        result.element_description,
                        result.required,
                        result.time_window_hours,
                        result.deadline.isoformat() if result.deadline else None,
                        result.status,
                        result.completed_at.isoformat() if result.completed_at else None,
                        result.value,
                        result.notes,
                    ),
                )
                conn.commit()
                return cursor.lastrowid

    def get_element_results(self, episode_id: int) -> list[ElementResult]:
        """Get all element results for an episode."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bundle_element_results
                WHERE episode_id = ?
                ORDER BY element_id
                """,
                (episode_id,),
            )
            return [self._row_to_element_result(row) for row in cursor.fetchall()]

    def get_pending_elements(self, limit: int = 100) -> list[ElementResult]:
        """Get pending elements that need checking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT r.* FROM bundle_element_results r
                JOIN bundle_episodes e ON r.episode_id = e.id
                WHERE r.status = 'pending' AND e.status = 'active'
                ORDER BY r.deadline ASC NULLS LAST
                LIMIT ?
                """,
                (limit,),
            )
            return [self._row_to_element_result(row) for row in cursor.fetchall()]

    def get_overdue_elements(self) -> list[ElementResult]:
        """Get elements past their deadline."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT r.* FROM bundle_element_results r
                JOIN bundle_episodes e ON r.episode_id = e.id
                WHERE r.status = 'pending'
                  AND e.status = 'active'
                  AND r.deadline IS NOT NULL
                  AND r.deadline < CURRENT_TIMESTAMP
                ORDER BY r.deadline ASC
                """,
            )
            return [self._row_to_element_result(row) for row in cursor.fetchall()]

    def _row_to_element_result(self, row: sqlite3.Row) -> ElementResult:
        """Convert database row to ElementResult."""
        return ElementResult(
            id=row["id"],
            episode_id=row["episode_id"],
            element_id=row["element_id"],
            element_name=row["element_name"],
            element_description=row["element_description"],
            required=bool(row["required"]),
            time_window_hours=row["time_window_hours"],
            deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None,
            status=row["status"],
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            value=row["value"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    # =========================================================================
    # ALERT OPERATIONS
    # =========================================================================

    def save_alert(self, alert: BundleAlert) -> int:
        """Save a bundle alert.

        Args:
            alert: BundleAlert to save.

        Returns:
            Alert ID.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bundle_alerts (
                    episode_id, element_result_id,
                    patient_id, patient_mrn, encounter_id,
                    bundle_id, bundle_name, element_id, element_name,
                    alert_type, severity, title, message, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.episode_id,
                    alert.element_result_id,
                    alert.patient_id,
                    alert.patient_mrn,
                    alert.encounter_id,
                    alert.bundle_id,
                    alert.bundle_name,
                    alert.element_id,
                    alert.element_name,
                    alert.alert_type,
                    alert.severity,
                    alert.title,
                    alert.message,
                    alert.status,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_active_alerts(self, limit: int = 100) -> list[BundleAlert]:
        """Get active alerts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bundle_alerts
                WHERE status = 'active'
                ORDER BY
                    CASE severity
                        WHEN 'critical' THEN 1
                        WHEN 'warning' THEN 2
                        ELSE 3
                    END,
                    created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [self._row_to_alert(row) for row in cursor.fetchall()]

    def acknowledge_alert(self, alert_id: int, acknowledged_by: str):
        """Acknowledge an alert."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bundle_alerts SET
                    status = 'acknowledged',
                    acknowledged_by = ?,
                    acknowledged_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (acknowledged_by, alert_id),
            )
            conn.commit()

    def resolve_alert(self, alert_id: int, resolution_notes: Optional[str] = None):
        """Resolve an alert."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bundle_alerts SET
                    status = 'resolved',
                    resolved_at = CURRENT_TIMESTAMP,
                    resolution_notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (resolution_notes, alert_id),
            )
            conn.commit()

    def _row_to_alert(self, row: sqlite3.Row) -> BundleAlert:
        """Convert database row to BundleAlert."""
        return BundleAlert(
            id=row["id"],
            episode_id=row["episode_id"],
            element_result_id=row["element_result_id"],
            patient_id=row["patient_id"],
            patient_mrn=row["patient_mrn"],
            encounter_id=row["encounter_id"],
            bundle_id=row["bundle_id"],
            bundle_name=row["bundle_name"],
            element_id=row["element_id"],
            element_name=row["element_name"],
            alert_type=row["alert_type"],
            severity=row["severity"],
            title=row["title"],
            message=row["message"],
            status=row["status"],
            acknowledged_by=row["acknowledged_by"],
            acknowledged_at=datetime.fromisoformat(row["acknowledged_at"]) if row["acknowledged_at"] else None,
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolution_notes=row["resolution_notes"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    # =========================================================================
    # TRIGGER OPERATIONS
    # =========================================================================

    def get_triggers_by_type(self, trigger_type: str) -> list[BundleTrigger]:
        """Get active triggers by type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bundle_triggers
                WHERE trigger_type = ? AND active = 1
                """,
                (trigger_type,),
            )
            return [self._row_to_trigger(row) for row in cursor.fetchall()]

    def get_all_triggers(self) -> list[BundleTrigger]:
        """Get all active triggers."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bundle_triggers WHERE active = 1")
            return [self._row_to_trigger(row) for row in cursor.fetchall()]

    def _row_to_trigger(self, row: sqlite3.Row) -> BundleTrigger:
        """Convert database row to BundleTrigger."""
        return BundleTrigger(
            id=row["id"],
            bundle_id=row["bundle_id"],
            trigger_type=row["trigger_type"],
            trigger_code=row["trigger_code"],
            trigger_pattern=row["trigger_pattern"],
            trigger_description=row["trigger_description"],
            age_min_days=row["age_min_days"],
            age_max_days=row["age_max_days"],
            additional_criteria=row["additional_criteria"],
            active=bool(row["active"]),
        )

    # =========================================================================
    # MONITOR STATE OPERATIONS
    # =========================================================================

    def get_last_poll_time(self, monitor_type: str) -> Optional[datetime]:
        """Get last poll time for a monitor type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_poll_time FROM monitor_state WHERE monitor_type = ?",
                (monitor_type,),
            )
            row = cursor.fetchone()
            if row and row["last_poll_time"]:
                return datetime.fromisoformat(row["last_poll_time"])
            return None

    def update_poll_time(self, monitor_type: str, poll_time: datetime, count: int = 0):
        """Update last poll time for a monitor type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO monitor_state (monitor_type, last_poll_time, last_poll_count)
                VALUES (?, ?, ?)
                ON CONFLICT(monitor_type) DO UPDATE SET
                    last_poll_time = excluded.last_poll_time,
                    last_poll_count = excluded.last_poll_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (monitor_type, poll_time.isoformat(), count),
            )
            conn.commit()

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_adherence_stats(self, days: int = 30) -> dict:
        """Get adherence statistics for the last N days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    bundle_id,
                    bundle_name,
                    COUNT(*) as total_episodes,
                    SUM(CASE WHEN adherence_level = 'full' THEN 1 ELSE 0 END) as full_adherence,
                    SUM(CASE WHEN adherence_level = 'partial' THEN 1 ELSE 0 END) as partial_adherence,
                    SUM(CASE WHEN adherence_level = 'low' THEN 1 ELSE 0 END) as low_adherence,
                    ROUND(AVG(adherence_percentage), 1) as avg_adherence_pct
                FROM bundle_episodes
                WHERE created_at >= datetime('now', ?)
                  AND status IN ('completed', 'closed')
                GROUP BY bundle_id, bundle_name
                """,
                (f"-{days} days",),
            )

            stats = {}
            for row in cursor.fetchall():
                stats[row["bundle_id"]] = {
                    "bundle_name": row["bundle_name"],
                    "total_episodes": row["total_episodes"],
                    "full_adherence": row["full_adherence"],
                    "partial_adherence": row["partial_adherence"],
                    "low_adherence": row["low_adherence"],
                    "avg_adherence_pct": row["avg_adherence_pct"],
                }

            return stats
