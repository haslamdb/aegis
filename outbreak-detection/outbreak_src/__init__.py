"""Outbreak Detection Module.

General-purpose cluster detection for infection control.
Can detect outbreaks from multiple data sources:
- MDRO cases (MRSA, VRE, CRE, etc.)
- HAI cases (SSI clusters, CLABSI clusters)
- C. diff cases
- Other infection events

Clusters are formed when multiple cases of the same infection type
appear in the same unit within a configurable time window.
"""

from .config import config, OutbreakConfig
from .db import OutbreakDatabase
from .detector import OutbreakDetector, detect_outbreaks
from .models import OutbreakCluster, ClusterCase, ClusterSeverity, ClusterStatus
from .sources import DataSource, MDROSource, HAISource

__all__ = [
    # Config
    "config",
    "OutbreakConfig",
    # Database
    "OutbreakDatabase",
    # Detector
    "OutbreakDetector",
    "detect_outbreaks",
    # Models
    "OutbreakCluster",
    "ClusterCase",
    "ClusterSeverity",
    "ClusterStatus",
    # Sources
    "DataSource",
    "MDROSource",
    "HAISource",
]
