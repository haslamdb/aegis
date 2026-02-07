"""Unified LLM decision tracker with SQLite persistence."""

import json
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

from .models import LLMDecisionRecord, DecisionOutcome, LLMOverrideReason

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.expanduser("~/.aegis/llm_tracking.db")


class LLMDecisionTracker:
    """Tracks LLM extraction decisions and human review outcomes."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get("LLM_TRACKING_DB_PATH", DEFAULT_DB_PATH)
        self._ensure_db()

    def _ensure_db(self):
        """Create database and tables if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        schema_path = Path(__file__).parent / "schema.sql"
        with sqlite3.connect(self.db_path) as conn:
            with open(schema_path) as f:
                conn.executescript(f.read())

    def _connect(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_extraction(
        self,
        module: str,
        entity_id: str,
        entity_type: str = "",
        patient_mrn: str | None = None,
        encounter_id: str | None = None,
        llm_model: str | None = None,
        llm_confidence: float | None = None,
        llm_recommendation: str = "",
        llm_reasoning: str | None = None,
        llm_extracted_data: dict | None = None,
    ) -> int:
        """Record a new LLM extraction (before human review).

        Returns the record ID.
        """
        now = datetime.now()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO llm_decisions
                (module, entity_id, entity_type, patient_mrn, encounter_id,
                 llm_model, llm_confidence, llm_recommendation, llm_reasoning,
                 llm_extracted_data, outcome, extracted_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    module, entity_id, entity_type, patient_mrn, encounter_id,
                    llm_model, llm_confidence, llm_recommendation, llm_reasoning,
                    json.dumps(llm_extracted_data) if llm_extracted_data else None,
                    now.isoformat(), now.isoformat(),
                )
            )
            return cursor.lastrowid

    def record_review(
        self,
        record_id: int,
        outcome: str,
        human_decision: str | None = None,
        override_reason: str | None = None,
        override_notes: str | None = None,
        reviewer_id: str | None = None,
        reviewer_name: str | None = None,
        review_duration_seconds: int | None = None,
    ) -> bool:
        """Record the human review of an LLM extraction.

        Args:
            record_id: ID from record_extraction
            outcome: DecisionOutcome value (accepted, modified, overridden)
            human_decision: What the human chose
            override_reason: LLMOverrideReason value (required if overridden)
            override_notes: Free-text notes
            reviewer_id: Badge/user ID
            reviewer_name: Display name
            review_duration_seconds: Time spent reviewing

        Returns True if update succeeded.
        """
        now = datetime.now()
        with self._connect() as conn:
            result = conn.execute(
                """UPDATE llm_decisions SET
                    outcome = ?, human_decision = ?, override_reason = ?,
                    override_notes = ?, reviewer_id = ?, reviewer_name = ?,
                    reviewed_at = ?, review_duration_seconds = ?
                WHERE id = ?""",
                (
                    outcome, human_decision, override_reason,
                    override_notes, reviewer_id, reviewer_name,
                    now.isoformat(), review_duration_seconds,
                    record_id,
                )
            )
            return result.rowcount > 0

    def get_decision(self, record_id: int) -> LLMDecisionRecord | None:
        """Get a single decision record by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM llm_decisions WHERE id = ?", (record_id,)
            ).fetchone()
            if row:
                return self._row_to_record(row)
            return None

    def list_decisions(
        self,
        module: str | None = None,
        outcome: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        patient_mrn: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LLMDecisionRecord]:
        """List decisions with optional filters."""
        query = "SELECT * FROM llm_decisions WHERE 1=1"
        params: list = []

        if module:
            query += " AND module = ?"
            params.append(module)
        if outcome:
            query += " AND outcome = ?"
            params.append(outcome)
        if start_date:
            query += " AND date(created_at) >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date(created_at) <= ?"
            params.append(end_date.isoformat())
        if patient_mrn:
            query += " AND patient_mrn = ?"
            params.append(patient_mrn)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_accuracy_stats(
        self,
        module: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get LLM accuracy statistics.

        Returns dict with acceptance_rate, override_rate, override_reasons breakdown, etc.
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        base_where = "WHERE outcome != 'pending' AND date(created_at) >= ?"
        params: list = [cutoff]
        if module:
            base_where += " AND module = ?"
            params.append(module)

        with self._connect() as conn:
            # Total reviewed
            total = conn.execute(
                f"SELECT COUNT(*) FROM llm_decisions {base_where}",
                params
            ).fetchone()[0]

            if total == 0:
                return {
                    "total_reviewed": 0,
                    "accepted": 0, "modified": 0, "overridden": 0,
                    "acceptance_rate": None, "override_rate": None,
                    "override_reasons": {},
                    "avg_confidence_accepted": None,
                    "avg_confidence_overridden": None,
                }

            # Breakdown by outcome
            rows = conn.execute(
                f"SELECT outcome, COUNT(*) as cnt FROM llm_decisions {base_where} GROUP BY outcome",
                params
            ).fetchall()
            by_outcome = {row["outcome"]: row["cnt"] for row in rows}

            accepted = by_outcome.get("accepted", 0) + by_outcome.get("modified", 0)
            overridden = by_outcome.get("overridden", 0)

            # Override reason breakdown
            reason_rows = conn.execute(
                f"""SELECT override_reason, COUNT(*) as cnt
                FROM llm_decisions {base_where} AND override_reason IS NOT NULL
                GROUP BY override_reason ORDER BY cnt DESC""",
                params
            ).fetchall()
            override_reasons = {row["override_reason"]: row["cnt"] for row in reason_rows}

            # Average confidence for accepted vs overridden
            avg_conf_accepted = conn.execute(
                f"""SELECT AVG(llm_confidence) FROM llm_decisions
                {base_where} AND outcome IN ('accepted', 'modified') AND llm_confidence IS NOT NULL""",
                params
            ).fetchone()[0]

            avg_conf_overridden = conn.execute(
                f"""SELECT AVG(llm_confidence) FROM llm_decisions
                {base_where} AND outcome = 'overridden' AND llm_confidence IS NOT NULL""",
                params
            ).fetchone()[0]

            return {
                "total_reviewed": total,
                "accepted": by_outcome.get("accepted", 0),
                "modified": by_outcome.get("modified", 0),
                "overridden": overridden,
                "acceptance_rate": round(accepted / total * 100, 1) if total > 0 else None,
                "override_rate": round(overridden / total * 100, 1) if total > 0 else None,
                "override_reasons": override_reasons,
                "avg_confidence_accepted": round(avg_conf_accepted, 3) if avg_conf_accepted else None,
                "avg_confidence_overridden": round(avg_conf_overridden, 3) if avg_conf_overridden else None,
            }

    def get_confidence_calibration(
        self,
        module: str | None = None,
        days: int = 30,
        buckets: int = 10,
    ) -> list[dict[str, Any]]:
        """Get confidence calibration data (acceptance rate by confidence level).

        Returns list of dicts with bucket_start, bucket_end, total, accepted, acceptance_rate.
        This supports L5 (confidence calibration analysis).
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        bucket_size = 1.0 / buckets

        results = []
        with self._connect() as conn:
            for i in range(buckets):
                low = round(i * bucket_size, 2)
                high = round((i + 1) * bucket_size, 2)

                where = """WHERE outcome != 'pending' AND date(created_at) >= ?
                           AND llm_confidence >= ? AND llm_confidence < ?"""
                params: list = [cutoff, low, high]
                if module:
                    where += " AND module = ?"
                    params.append(module)

                # Include 1.0 in last bucket
                if i == buckets - 1:
                    where = where.replace("llm_confidence < ?", "llm_confidence <= ?")

                total = conn.execute(
                    f"SELECT COUNT(*) FROM llm_decisions {where}", params
                ).fetchone()[0]

                accepted = conn.execute(
                    f"SELECT COUNT(*) FROM llm_decisions {where} AND outcome IN ('accepted', 'modified')",
                    params
                ).fetchone()[0]

                results.append({
                    "bucket_start": low,
                    "bucket_end": high,
                    "total": total,
                    "accepted": accepted,
                    "acceptance_rate": round(accepted / total * 100, 1) if total > 0 else None,
                })

        return results

    def get_module_comparison(self, days: int = 30) -> list[dict[str, Any]]:
        """Get accuracy comparison across modules."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """SELECT module,
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome IN ('accepted', 'modified') THEN 1 ELSE 0 END) as accepted,
                    SUM(CASE WHEN outcome = 'overridden' THEN 1 ELSE 0 END) as overridden,
                    AVG(CASE WHEN llm_confidence IS NOT NULL THEN llm_confidence END) as avg_confidence,
                    AVG(CASE WHEN review_duration_seconds IS NOT NULL THEN review_duration_seconds END) as avg_review_time
                FROM llm_decisions
                WHERE outcome != 'pending' AND date(created_at) >= ?
                GROUP BY module
                ORDER BY total DESC""",
                (cutoff,)
            ).fetchall()

            return [{
                "module": row["module"],
                "total": row["total"],
                "accepted": row["accepted"],
                "overridden": row["overridden"],
                "acceptance_rate": round(row["accepted"] / row["total"] * 100, 1) if row["total"] > 0 else None,
                "avg_confidence": round(row["avg_confidence"], 3) if row["avg_confidence"] else None,
                "avg_review_seconds": round(row["avg_review_time"], 1) if row["avg_review_time"] else None,
            } for row in rows]

    def _row_to_record(self, row: sqlite3.Row) -> LLMDecisionRecord:
        """Convert a database row to an LLMDecisionRecord."""
        def parse_dt(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        extracted_data = row["llm_extracted_data"]
        if isinstance(extracted_data, str):
            try:
                extracted_data = json.loads(extracted_data)
            except (json.JSONDecodeError, TypeError):
                extracted_data = {}

        return LLMDecisionRecord(
            id=row["id"],
            module=row["module"],
            entity_id=row["entity_id"],
            entity_type=row["entity_type"] or "",
            patient_mrn=row["patient_mrn"],
            encounter_id=row["encounter_id"],
            llm_model=row["llm_model"],
            llm_confidence=row["llm_confidence"],
            llm_recommendation=row["llm_recommendation"] or "",
            llm_reasoning=row["llm_reasoning"],
            llm_extracted_data=extracted_data or {},
            outcome=row["outcome"],
            human_decision=row["human_decision"],
            override_reason=row["override_reason"],
            override_notes=row["override_notes"],
            reviewer_id=row["reviewer_id"],
            reviewer_name=row["reviewer_name"],
            extracted_at=parse_dt(row["extracted_at"]),
            reviewed_at=parse_dt(row["reviewed_at"]),
            review_duration_seconds=row["review_duration_seconds"],
            created_at=parse_dt(row["created_at"]),
        )
