"""Configuration for Outbreak Detection module."""

import os
from pathlib import Path


class OutbreakConfig:
    """Configuration settings for outbreak detection."""

    # Database
    DB_PATH: str = os.environ.get(
        "OUTBREAK_DB_PATH",
        str(Path.home() / ".aegis" / "outbreak_detection.db")
    )

    # Detection settings
    CLUSTER_WINDOW_DAYS: int = int(os.environ.get("OUTBREAK_WINDOW_DAYS", "14"))
    MIN_CLUSTER_SIZE: int = int(os.environ.get("OUTBREAK_MIN_CLUSTER", "2"))

    # Alert thresholds
    ALERT_THRESHOLD_MEDIUM: int = 3
    ALERT_THRESHOLD_HIGH: int = 4
    ALERT_THRESHOLD_CRITICAL: int = 5

    # Monitoring
    POLL_INTERVAL_MINUTES: int = int(os.environ.get("OUTBREAK_POLL_INTERVAL", "30"))

    # Source module paths (for importing data)
    MDRO_DB_PATH: str = os.environ.get(
        "MDRO_DB_PATH",
        str(Path.home() / ".aegis" / "mdro_surveillance.db")
    )
    HAI_DB_PATH: str = os.environ.get(
        "HAI_DB_PATH",
        str(Path.home() / ".aegis" / "hai_detection.db")
    )


config = OutbreakConfig()
