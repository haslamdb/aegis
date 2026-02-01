"""Data sources for outbreak detection.

Adapters that pull infection case data from various AEGIS modules
to feed into the outbreak detection engine.
"""

import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import config

logger = logging.getLogger(__name__)


class DataSource(ABC):
    """Abstract base class for outbreak data sources."""

    @abstractmethod
    def get_recent_cases(self, days: int = 14) -> list[dict]:
        """Get recent infection cases formatted for outbreak detection.

        Returns list of dicts with:
        - source: str (e.g., 'mdro', 'hai')
        - source_id: str
        - patient_id: str
        - patient_mrn: str
        - event_date: str (ISO format)
        - organism: str or None
        - infection_type: str
        - unit: str
        - location: str or None
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this data source is available."""
        pass


class MDROSource(DataSource):
    """Data source for MDRO cases."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or config.MDRO_DB_PATH).expanduser()

    def is_available(self) -> bool:
        """Check if MDRO database exists."""
        return self.db_path.exists()

    def get_recent_cases(self, days: int = 14) -> list[dict]:
        """Get recent MDRO cases."""
        if not self.is_available():
            logger.warning(f"MDRO database not found at {self.db_path}")
            return []

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                """
                SELECT id, patient_id, patient_mrn, culture_date,
                       organism, mdro_type, unit, location
                FROM mdro_cases
                WHERE culture_date >= ?
                ORDER BY culture_date DESC
                """,
                (cutoff,),
            ).fetchall()
            conn.close()

            return [
                {
                    "source": "mdro",
                    "source_id": row["id"],
                    "patient_id": row["patient_id"],
                    "patient_mrn": row["patient_mrn"],
                    "event_date": row["culture_date"],
                    "organism": row["organism"],
                    "infection_type": row["mdro_type"],
                    "unit": row["unit"] or "",
                    "location": row["location"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error reading MDRO cases: {e}")
            return []


class HAISource(DataSource):
    """Data source for HAI cases."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or config.HAI_DB_PATH).expanduser()

    def is_available(self) -> bool:
        """Check if HAI database exists."""
        return self.db_path.exists()

    def get_recent_cases(self, days: int = 14) -> list[dict]:
        """Get recent confirmed HAI cases."""
        if not self.is_available():
            logger.warning(f"HAI database not found at {self.db_path}")
            return []

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # Only get confirmed HAI cases
            rows = conn.execute(
                """
                SELECT id, patient_id, patient_mrn, culture_date,
                       organism, hai_type
                FROM hai_candidates
                WHERE status = 'confirmed'
                AND culture_date >= ?
                ORDER BY culture_date DESC
                """,
                (cutoff,),
            ).fetchall()
            conn.close()

            # Note: HAI doesn't have unit in the base table, would need
            # to join with encounter data or get from device_info
            return [
                {
                    "source": "hai",
                    "source_id": row["id"],
                    "patient_id": row["patient_id"],
                    "patient_mrn": row["patient_mrn"],
                    "event_date": row["culture_date"],
                    "organism": row["organism"],
                    "infection_type": row["hai_type"],
                    "unit": "",  # Would need to enhance with location data
                    "location": None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error reading HAI cases: {e}")
            return []


class CDISource(DataSource):
    """Data source for C. diff cases (via HAI CDI type)."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or config.HAI_DB_PATH).expanduser()

    def is_available(self) -> bool:
        """Check if HAI database exists."""
        return self.db_path.exists()

    def get_recent_cases(self, days: int = 14) -> list[dict]:
        """Get recent C. diff cases."""
        if not self.is_available():
            return []

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                """
                SELECT id, patient_id, patient_mrn, culture_date
                FROM hai_candidates
                WHERE hai_type = 'cdi'
                AND status = 'confirmed'
                AND culture_date >= ?
                ORDER BY culture_date DESC
                """,
                (cutoff,),
            ).fetchall()
            conn.close()

            return [
                {
                    "source": "cdi",
                    "source_id": row["id"],
                    "patient_id": row["patient_id"],
                    "patient_mrn": row["patient_mrn"],
                    "event_date": row["culture_date"],
                    "organism": "Clostridioides difficile",
                    "infection_type": "cdi",
                    "unit": "",
                    "location": None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error reading CDI cases: {e}")
            return []


def get_all_sources() -> list[DataSource]:
    """Get all available data sources."""
    sources = [
        MDROSource(),
        HAISource(),
        CDISource(),
    ]
    return [s for s in sources if s.is_available()]


def get_all_recent_cases(days: int = 14) -> list[dict]:
    """Get all recent cases from all available sources."""
    all_cases = []
    for source in get_all_sources():
        cases = source.get_recent_cases(days)
        all_cases.extend(cases)
    return all_cases
