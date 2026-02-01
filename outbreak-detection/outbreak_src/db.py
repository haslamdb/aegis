"""Database operations for Outbreak Detection module."""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .config import config
from .models import OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity

logger = logging.getLogger(__name__)


class OutbreakDatabase:
    """SQLite database for outbreak cluster tracking."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or config.DB_PATH).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        schema_path = Path(__file__).parent.parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()

        with self._get_connection() as conn:
            conn.executescript(schema)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Cluster Operations ---

    def save_cluster(self, cluster: OutbreakCluster) -> None:
        """Save or update an outbreak cluster."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO outbreak_clusters (
                    id, infection_type, organism, unit, location,
                    case_count, first_case_date, last_case_date, window_days,
                    status, severity, created_at,
                    resolved_at, resolved_by, resolution_notes,
                    alerted, alerted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster.id,
                    cluster.infection_type,
                    cluster.organism,
                    cluster.unit,
                    cluster.location,
                    cluster.case_count,
                    cluster.first_case_date.isoformat() if cluster.first_case_date else None,
                    cluster.last_case_date.isoformat() if cluster.last_case_date else None,
                    cluster.window_days,
                    cluster.status.value,
                    cluster.severity.value,
                    cluster.created_at.isoformat(),
                    cluster.resolved_at.isoformat() if cluster.resolved_at else None,
                    cluster.resolved_by,
                    cluster.resolution_notes,
                    cluster.alerted,
                    cluster.alerted_at.isoformat() if cluster.alerted_at else None,
                ),
            )

            # Save cluster cases
            for case in cluster.cases:
                self._save_cluster_case(conn, case)

            conn.commit()

    def _save_cluster_case(self, conn: sqlite3.Connection, case: ClusterCase) -> None:
        """Save a cluster case."""
        conn.execute(
            """
            INSERT OR REPLACE INTO cluster_cases (
                id, cluster_id, source, source_id, patient_id, patient_mrn,
                event_date, organism, infection_type, unit, location, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.id,
                case.cluster_id,
                case.source,
                case.source_id,
                case.patient_id,
                case.patient_mrn,
                case.event_date.isoformat() if case.event_date else None,
                case.organism,
                case.infection_type,
                case.unit,
                case.location,
                case.added_at.isoformat() if case.added_at else None,
            ),
        )

    def get_cluster(self, cluster_id: str) -> Optional[OutbreakCluster]:
        """Get a cluster by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM outbreak_clusters WHERE id = ?",
                (cluster_id,),
            ).fetchone()
            if row:
                return self._row_to_cluster(row, conn)
            return None

    def get_active_clusters(
        self,
        unit: str | None = None,
        infection_type: str | None = None,
    ) -> list[OutbreakCluster]:
        """Get active outbreak clusters."""
        with self._get_connection() as conn:
            query = "SELECT * FROM outbreak_clusters WHERE status = 'active'"
            params: list[Any] = []

            if unit:
                query += " AND unit = ?"
                params.append(unit)
            if infection_type:
                query += " AND infection_type = ?"
                params.append(infection_type)

            query += " ORDER BY severity DESC, created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_cluster(row, conn) for row in rows]

    def get_all_clusters(
        self,
        status: ClusterStatus | None = None,
        limit: int = 100,
    ) -> list[OutbreakCluster]:
        """Get clusters with optional status filter."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM outbreak_clusters
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM outbreak_clusters
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [self._row_to_cluster(row, conn) for row in rows]

    def find_matching_cluster(
        self,
        infection_type: str,
        unit: str,
    ) -> Optional[OutbreakCluster]:
        """Find an active cluster that matches the given parameters."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM outbreak_clusters
                WHERE infection_type = ?
                AND unit = ?
                AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (infection_type, unit),
            ).fetchone()

            if row:
                return self._row_to_cluster(row, conn)
            return None

    def _row_to_cluster(self, row: sqlite3.Row, conn: sqlite3.Connection) -> OutbreakCluster:
        """Convert database row to OutbreakCluster."""
        # Get cases for this cluster
        case_rows = conn.execute(
            "SELECT * FROM cluster_cases WHERE cluster_id = ? ORDER BY event_date",
            (row["id"],),
        ).fetchall()

        cases = [self._row_to_case(cr) for cr in case_rows]

        return OutbreakCluster(
            id=row["id"],
            infection_type=row["infection_type"],
            organism=row["organism"],
            unit=row["unit"],
            location=row["location"],
            cases=cases,
            case_count=row["case_count"],
            first_case_date=datetime.fromisoformat(row["first_case_date"]) if row["first_case_date"] else None,
            last_case_date=datetime.fromisoformat(row["last_case_date"]) if row["last_case_date"] else None,
            window_days=row["window_days"],
            status=ClusterStatus(row["status"]),
            severity=ClusterSeverity(row["severity"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolved_by=row["resolved_by"],
            resolution_notes=row["resolution_notes"],
            alerted=bool(row["alerted"]),
            alerted_at=datetime.fromisoformat(row["alerted_at"]) if row["alerted_at"] else None,
        )

    def _row_to_case(self, row: sqlite3.Row) -> ClusterCase:
        """Convert database row to ClusterCase."""
        return ClusterCase(
            id=row["id"],
            cluster_id=row["cluster_id"],
            source=row["source"],
            source_id=row["source_id"],
            patient_id=row["patient_id"],
            patient_mrn=row["patient_mrn"],
            event_date=datetime.fromisoformat(row["event_date"]) if row["event_date"] else None,
            organism=row["organism"],
            infection_type=row["infection_type"],
            unit=row["unit"],
            location=row["location"],
            added_at=datetime.fromisoformat(row["added_at"]) if row["added_at"] else None,
        )

    def is_case_processed(self, source: str, source_id: str) -> bool:
        """Check if a case has already been processed."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM outbreak_processing_log WHERE source = ? AND source_id = ?",
                (source, source_id),
            ).fetchone()
            return row is not None

    def log_case_processed(
        self,
        source: str,
        source_id: str,
        cluster_id: str | None = None,
    ) -> None:
        """Log that a case has been processed."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO outbreak_processing_log
                (source, source_id, processed_at, cluster_id)
                VALUES (?, ?, ?, ?)
                """,
                (source, source_id, datetime.now().isoformat(), cluster_id),
            )
            conn.commit()

    # --- Alert Operations ---

    def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str | None = None,
        cluster_id: str | None = None,
    ) -> str:
        """Create an alert for IP team."""
        alert_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO outbreak_alerts (
                    id, alert_type, severity, title, message,
                    cluster_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    alert_type,
                    severity,
                    title,
                    message,
                    cluster_id,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

        return alert_id

    def get_pending_alerts(self) -> list[dict[str, Any]]:
        """Get unacknowledged alerts."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM pending_alerts").fetchall()
            return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> None:
        """Mark an alert as acknowledged."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE outbreak_alerts
                SET acknowledged = 1, acknowledged_by = ?, acknowledged_at = ?
                WHERE id = ?
                """,
                (acknowledged_by, datetime.now().isoformat(), alert_id),
            )
            conn.commit()

    # --- Statistics ---

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics for dashboard."""
        with self._get_connection() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM outbreak_clusters WHERE status = 'active'"
            ).fetchone()[0]

            investigating = conn.execute(
                "SELECT COUNT(*) FROM outbreak_clusters WHERE status = 'investigating'"
            ).fetchone()[0]

            resolved = conn.execute(
                "SELECT COUNT(*) FROM outbreak_clusters WHERE status = 'resolved'"
            ).fetchone()[0]

            pending_alerts = conn.execute(
                "SELECT COUNT(*) FROM outbreak_alerts WHERE acknowledged = 0"
            ).fetchone()[0]

            # By infection type
            by_type_rows = conn.execute(
                """
                SELECT infection_type, COUNT(*) as count
                FROM outbreak_clusters
                WHERE status = 'active'
                GROUP BY infection_type
                """
            ).fetchall()
            by_type = {row["infection_type"]: row["count"] for row in by_type_rows}

            # By severity
            by_severity_rows = conn.execute(
                """
                SELECT severity, COUNT(*) as count
                FROM outbreak_clusters
                WHERE status = 'active'
                GROUP BY severity
                """
            ).fetchall()
            by_severity = {row["severity"]: row["count"] for row in by_severity_rows}

            return {
                "active_clusters": active,
                "investigating_clusters": investigating,
                "resolved_clusters": resolved,
                "pending_alerts": pending_alerts,
                "by_type": by_type,
                "by_severity": by_severity,
            }
