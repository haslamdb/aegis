"""Mock Clarity database package for NHSN reporting development.

This package provides a SQLite-based mock of Epic Clarity tables for testing
the hybrid FHIR/Clarity architecture. It enables:
- Denominator data aggregation (device-days, patient-days)
- Bulk historical queries without FHIR pagination overhead
- Testing Clarity-based data retrieval logic
"""

from pathlib import Path

# Path to schema file
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_schema_sql() -> str:
    """Read and return the schema SQL."""
    return SCHEMA_PATH.read_text()
