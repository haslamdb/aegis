"""Database operations for MDRO Surveillance module."""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .config import config
from .classifier import MDROType
from .models import MDROCase, TransmissionStatus

logger = logging.getLogger(__name__)


class MDRODatabase:
    """SQLite database for MDRO case tracking."""

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

    # --- Case Operations ---

    def save_case(self, case: MDROCase) -> None:
        """Save or update an MDRO case."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mdro_cases (
                    id, patient_id, patient_mrn, patient_name,
                    culture_id, culture_date, specimen_type, organism,
                    mdro_type, resistant_antibiotics, susceptibilities, classification_reason,
                    location, unit, admission_date, days_since_admission,
                    transmission_status,
                    is_new, prior_history, created_at,
                    reviewed_at, reviewed_by, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case.id,
                    case.patient_id,
                    case.patient_mrn,
                    case.patient_name,
                    case.culture_id,
                    case.culture_date.isoformat(),
                    case.specimen_type,
                    case.organism,
                    case.mdro_type.value,
                    json.dumps(case.resistant_antibiotics),
                    json.dumps(case.susceptibilities),
                    case.classification_reason,
                    case.location,
                    case.unit,
                    case.admission_date.isoformat() if case.admission_date else None,
                    case.days_since_admission,
                    case.transmission_status.value,
                    case.is_new,
                    case.prior_history,
                    case.created_at.isoformat(),
                    case.reviewed_at.isoformat() if case.reviewed_at else None,
                    case.reviewed_by,
                    case.notes,
                ),
            )
            conn.commit()

    def get_case(self, case_id: str) -> Optional[MDROCase]:
        """Get a case by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM mdro_cases WHERE id = ?", (case_id,)
            ).fetchone()
            if row:
                return self._row_to_case(row)
            return None

    def get_case_by_culture(self, culture_id: str) -> Optional[MDROCase]:
        """Get a case by culture ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM mdro_cases WHERE culture_id = ?", (culture_id,)
            ).fetchone()
            if row:
                return self._row_to_case(row)
            return None

    def culture_already_processed(self, culture_id: str) -> bool:
        """Check if a culture has already been processed."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM mdro_processing_log WHERE culture_id = ?",
                (culture_id,)
            ).fetchone()
            return row is not None

    def log_culture_processed(
        self,
        culture_id: str,
        is_mdro: bool,
        mdro_type: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> None:
        """Log that a culture has been processed."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mdro_processing_log
                (culture_id, processed_at, is_mdro, mdro_type, case_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (culture_id, datetime.now().isoformat(), is_mdro, mdro_type, case_id),
            )
            conn.commit()

    def get_recent_cases(
        self,
        days: int = 30,
        mdro_type: MDROType | None = None,
        unit: str | None = None,
    ) -> list[MDROCase]:
        """Get recent MDRO cases."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            query = "SELECT * FROM mdro_cases WHERE culture_date >= ?"
            params: list[Any] = [cutoff]

            if mdro_type:
                query += " AND mdro_type = ?"
                params.append(mdro_type.value)
            if unit:
                query += " AND unit = ?"
                params.append(unit)

            query += " ORDER BY culture_date DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_case(row) for row in rows]

    def get_patient_prior_cases(self, patient_id: str) -> list[MDROCase]:
        """Get all prior MDRO cases for a patient."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM mdro_cases
                WHERE patient_id = ?
                ORDER BY culture_date DESC
                """,
                (patient_id,),
            ).fetchall()
            return [self._row_to_case(row) for row in rows]

    def update_case_transmission_status(
        self,
        case_id: str,
        status: TransmissionStatus,
    ) -> None:
        """Update transmission status for a case."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE mdro_cases
                SET transmission_status = ?
                WHERE id = ?
                """,
                (status.value, case_id),
            )
            conn.commit()

    def _row_to_case(self, row: sqlite3.Row) -> MDROCase:
        """Convert database row to MDROCase."""
        # Handle susceptibilities - may not exist in older records or be NULL
        susceptibilities = []
        try:
            susc_data = row["susceptibilities"]
            if susc_data:
                susceptibilities = json.loads(susc_data)
        except (KeyError, TypeError, IndexError):
            pass

        return MDROCase(
            id=row["id"],
            patient_id=row["patient_id"],
            patient_mrn=row["patient_mrn"],
            patient_name=row["patient_name"] or "",
            culture_id=row["culture_id"],
            culture_date=datetime.fromisoformat(row["culture_date"]),
            specimen_type=row["specimen_type"] or "",
            organism=row["organism"],
            mdro_type=MDROType(row["mdro_type"]),
            resistant_antibiotics=json.loads(row["resistant_antibiotics"] or "[]"),
            susceptibilities=susceptibilities,
            classification_reason=row["classification_reason"] or "",
            location=row["location"] or "",
            unit=row["unit"] or "",
            admission_date=datetime.fromisoformat(row["admission_date"]) if row["admission_date"] else None,
            days_since_admission=row["days_since_admission"],
            transmission_status=TransmissionStatus(row["transmission_status"]),
            is_new=bool(row["is_new"]),
            prior_history=bool(row["prior_history"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            reviewed_by=row["reviewed_by"],
            notes=row["notes"],
        )

    # --- Review Operations ---

    def save_review(
        self,
        case_id: str,
        reviewer: str,
        decision: str,
        notes: str | None = None,
    ) -> str:
        """Save a case review."""
        review_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO mdro_reviews (id, case_id, reviewer, decision, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (review_id, case_id, reviewer, decision, notes, datetime.now().isoformat()),
            )

            # Update case reviewed status
            conn.execute(
                """
                UPDATE mdro_cases
                SET reviewed_at = ?, reviewed_by = ?, notes = COALESCE(notes || ' ' || ?, ?)
                WHERE id = ?
                """,
                (datetime.now().isoformat(), reviewer, notes, notes, case_id),
            )
            conn.commit()

        return review_id

    # --- Statistics ---

    def get_summary_stats(self, days: int = 30) -> dict[str, Any]:
        """Get summary statistics for dashboard."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            # Total cases in period
            total = conn.execute(
                "SELECT COUNT(*) FROM mdro_cases WHERE culture_date >= ?",
                (cutoff,),
            ).fetchone()[0]

            # By MDRO type
            by_type_rows = conn.execute(
                """
                SELECT mdro_type, COUNT(*) as count
                FROM mdro_cases
                WHERE culture_date >= ?
                GROUP BY mdro_type
                ORDER BY count DESC
                """,
                (cutoff,),
            ).fetchall()
            by_type = {row["mdro_type"]: row["count"] for row in by_type_rows}

            # By unit
            by_unit_rows = conn.execute(
                """
                SELECT unit, COUNT(*) as count
                FROM mdro_cases
                WHERE culture_date >= ? AND unit IS NOT NULL AND unit != ''
                GROUP BY unit
                ORDER BY count DESC
                LIMIT 10
                """,
                (cutoff,),
            ).fetchall()
            by_unit = {row["unit"]: row["count"] for row in by_unit_rows}

            # Healthcare vs community onset
            healthcare_onset = conn.execute(
                """
                SELECT COUNT(*) FROM mdro_cases
                WHERE culture_date >= ?
                AND transmission_status = 'healthcare'
                """,
                (cutoff,),
            ).fetchone()[0]

            community_onset = conn.execute(
                """
                SELECT COUNT(*) FROM mdro_cases
                WHERE culture_date >= ?
                AND transmission_status = 'community'
                """,
                (cutoff,),
            ).fetchone()[0]

            return {
                "total_cases": total,
                "by_type": by_type,
                "by_unit": by_unit,
                "healthcare_onset": healthcare_onset,
                "community_onset": community_onset,
                "days": days,
            }

    def get_trend_data(self, days: int = 30) -> list[dict]:
        """Get daily case counts for trend chart."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DATE(culture_date) as date, mdro_type, COUNT(*) as count
                FROM mdro_cases
                WHERE culture_date >= ?
                GROUP BY DATE(culture_date), mdro_type
                ORDER BY date
                """,
                (cutoff,),
            ).fetchall()

            return [
                {"date": row["date"], "mdro_type": row["mdro_type"], "count": row["count"]}
                for row in rows
            ]

    def get_cases_for_export(
        self,
        days: int = 30,
        mdro_type: MDROType | None = None,
    ) -> list[dict]:
        """Get cases formatted for export to outbreak detection module."""
        cases = self.get_recent_cases(days=days, mdro_type=mdro_type)
        return [
            {
                "source": "mdro",
                "source_id": c.id,
                "patient_id": c.patient_id,
                "patient_mrn": c.patient_mrn,
                "event_date": c.culture_date.isoformat(),
                "organism": c.organism,
                "infection_type": c.mdro_type.value,
                "unit": c.unit,
                "location": c.location,
            }
            for c in cases
        ]
