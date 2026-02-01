"""Configuration for MDRO Surveillance module."""

import os
from pathlib import Path


class MDROConfig:
    """Configuration settings for MDRO surveillance."""

    # Database
    DB_PATH: str = os.environ.get(
        "MDRO_DB_PATH",
        str(Path.home() / ".aegis" / "mdro_surveillance.db")
    )

    # FHIR settings (shared with other modules)
    FHIR_BASE_URL: str = os.environ.get(
        "FHIR_BASE_URL",
        "http://localhost:8080/fhir"
    )

    # Epic FHIR (if using Epic)
    EPIC_FHIR_BASE_URL: str = os.environ.get("EPIC_FHIR_BASE_URL", "")
    EPIC_CLIENT_ID: str = os.environ.get("EPIC_CLIENT_ID", "")
    EPIC_PRIVATE_KEY_PATH: str = os.environ.get("EPIC_PRIVATE_KEY_PATH", "")

    # Monitoring settings
    POLL_INTERVAL_MINUTES: int = int(os.environ.get("MDRO_POLL_INTERVAL", "15"))
    LOOKBACK_HOURS: int = int(os.environ.get("MDRO_LOOKBACK_HOURS", "24"))

    def is_epic_configured(self) -> bool:
        """Check if Epic FHIR is configured."""
        return bool(self.EPIC_FHIR_BASE_URL and self.EPIC_CLIENT_ID)


config = MDROConfig()
