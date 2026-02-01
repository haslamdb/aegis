"""MDRO Surveillance Module.

Tracks multi-drug resistant organisms using FHIR microbiology data
with susceptibility results.

MDRO Types Tracked:
- MRSA: Methicillin-resistant Staphylococcus aureus
- VRE: Vancomycin-resistant Enterococcus
- CRE: Carbapenem-resistant Enterobacteriaceae
- ESBL: Extended-spectrum beta-lactamase producers
- CRPA: Carbapenem-resistant Pseudomonas aeruginosa
- CRAB: Carbapenem-resistant Acinetobacter baumannii

Note: Outbreak detection is a separate module that can consume MDRO data.
"""

from .classifier import MDROClassifier, MDROClassification, MDROType, classify_mdro
from .config import config, MDROConfig
from .db import MDRODatabase
from .fhir_client import MDROFHIRClient, CultureResult
from .models import MDROCase, TransmissionStatus
from .monitor import MDROMonitor, run_monitor

__all__ = [
    # Classifier
    "MDROClassifier",
    "MDROClassification",
    "MDROType",
    "classify_mdro",
    # Config
    "config",
    "MDROConfig",
    # Database
    "MDRODatabase",
    # FHIR
    "MDROFHIRClient",
    "CultureResult",
    # Models
    "MDROCase",
    "TransmissionStatus",
    # Monitor
    "MDROMonitor",
    "run_monitor",
]
