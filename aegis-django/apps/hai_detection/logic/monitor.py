"""HAI Candidate Monitor.

Main service that orchestrates:
1. Rule-based candidate detection
2. Note retrieval for LLM context
3. LLM extraction + rules-based classification
4. Routing to IP review queue

Note: In the Django version, this module does NOT depend on the Flask
SQLite database (db.py) or the shared alert store (common.alert_store).
Instead, the Django ORM adapter in services.py provides persistence.
The monitor's public methods are called from services.py which handles
Django Alert model creation.
"""

import logging
import time
from datetime import datetime, timedelta

from .config import Config
from .data_models import (
    HAICandidate,
    HAIType,
    CandidateStatus,
    ClassificationDecision,
    Review,
    ReviewQueueType,
)
from .candidates import (
    CLABSICandidateDetector,
    SSICandidateDetector,
    VAECandidateDetector,
    CAUTICandidateDetector,
    CDICandidateDetector,
)
from .classifiers import (
    CLABSIClassifierV2,
    SSIClassifierV2,
    VAEClassifier,
    CAUTIClassifier,
    CDIClassifier,
)
from .notes.retriever import NoteRetriever

logger = logging.getLogger(__name__)


class HAIMonitor:
    """Monitor for HAI candidate detection and classification.

    In the Django version, this class operates without direct database
    access. The caller (services.py) is responsible for persisting
    candidates and classifications via the Django ORM.
    """

    def __init__(
        self,
        lookback_hours: int | None = None,
    ):
        """Initialize the monitor.

        Args:
            lookback_hours: Hours to look back for new cultures. Uses config if None.
        """
        self.lookback_hours = lookback_hours or Config.LOOKBACK_HOURS

        # Initialize detectors for each HAI type
        self.detectors = {
            HAIType.CLABSI: CLABSICandidateDetector(),
            HAIType.SSI: SSICandidateDetector(),
            HAIType.VAE: VAECandidateDetector(),
            HAIType.CAUTI: CAUTICandidateDetector(),
            HAIType.CDI: CDICandidateDetector(),
        }

        # Initialize classifiers and note retriever (lazy-loaded)
        self._classifiers: dict = {}
        self._note_retriever: NoteRetriever | None = None

        # Track processed cultures to avoid duplicates within session
        self._processed_cultures: set[str] = set()

    def get_classifier(self, hai_type: HAIType):
        """Get classifier for the specified HAI type (lazy-loaded)."""
        if hai_type not in self._classifiers:
            if hai_type == HAIType.CLABSI:
                self._classifiers[hai_type] = CLABSIClassifierV2(
                    use_triage=True,
                    triage_model="qwen2.5:7b",
                )
            elif hai_type == HAIType.SSI:
                self._classifiers[hai_type] = SSIClassifierV2()
            elif hai_type == HAIType.VAE:
                self._classifiers[hai_type] = VAEClassifier()
            elif hai_type == HAIType.CAUTI:
                self._classifiers[hai_type] = CAUTIClassifier()
            elif hai_type == HAIType.CDI:
                self._classifiers[hai_type] = CDIClassifier(note_retriever=self.note_retriever)
            else:
                logger.warning(f"No specific classifier for {hai_type}, using CLABSI")
                self._classifiers[hai_type] = CLABSIClassifierV2()
        return self._classifiers[hai_type]

    @property
    def note_retriever(self) -> NoteRetriever:
        """Lazy-load note retriever."""
        if self._note_retriever is None:
            self._note_retriever = NoteRetriever()
        return self._note_retriever

    def detect_candidates(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[HAICandidate]:
        """Run detection cycle and return candidates.

        Args:
            start_date: Start of detection window. Defaults to lookback_hours ago.
            end_date: End of detection window. Defaults to now.

        Returns:
            List of detected HAI candidates.
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(hours=self.lookback_hours)

        logger.info(f"Starting detection cycle: {start_date} to {end_date}")

        all_candidates = []

        for hai_type, detector in self.detectors.items():
            logger.info(f"Running {hai_type.value} detection...")
            try:
                candidates = detector.detect_candidates(start_date, end_date)
                all_candidates.extend(candidates)
                logger.info(f"{hai_type.value}: {len(candidates)} candidates found")
            except Exception as e:
                logger.error(f"Error in {hai_type.value} detection: {e}", exc_info=True)

        logger.info(f"Detection cycle complete: {len(all_candidates)} total candidates")
        return all_candidates

    def classify_candidate(
        self,
        candidate: HAICandidate,
        notes: list | None = None,
    ):
        """Classify a single candidate.

        Args:
            candidate: The HAI candidate to classify.
            notes: Clinical notes. If None, will retrieve automatically.

        Returns:
            Classification result.
        """
        if notes is None:
            notes = self.note_retriever.get_notes_for_candidate(candidate)

        if not notes:
            logger.warning(
                f"No notes found for candidate {candidate.id} "
                f"(patient {candidate.patient.mrn})"
            )
            notes = []

        logger.info(
            f"Classifying {candidate.hai_type.value} candidate {candidate.id}: "
            f"patient={candidate.patient.mrn}, "
            f"organism={candidate.culture.organism}, "
            f"notes={len(notes)}"
        )

        classifier = self.get_classifier(candidate.hai_type)
        classification = classifier.classify(candidate, notes)

        logger.info(
            f"Classified {candidate.id} as {classification.decision.value} "
            f"(confidence={classification.confidence:.2f})"
        )

        return classification

    def build_summary(self, candidate: HAICandidate) -> str:
        """Build alert summary text for a candidate."""
        if candidate.hai_type == HAIType.SSI:
            ssi_data = getattr(candidate, "_ssi_data", None)
            if ssi_data:
                parts = [
                    f"{ssi_data.procedure.procedure_name} ({ssi_data.procedure.nhsn_category})",
                    f"day {ssi_data.days_post_op} post-op",
                ]
                if candidate.culture.organism:
                    parts.append(f"- {candidate.culture.organism}")
                return ", ".join(parts)
            return f"SSI signal detected ({candidate.culture.organism or 'keyword-based'})"

        elif candidate.hai_type == HAIType.VAE:
            vae_data = getattr(candidate, "_vae_data", None)
            if vae_data:
                parts = ["VAC detected"]
                if vae_data.episode:
                    parts.append(f"on ventilator day {vae_data.episode.get_ventilator_days()}")
                if vae_data.fio2_increase:
                    parts.append(f"FiO2 +{vae_data.fio2_increase:.0f}%")
                if vae_data.peep_increase:
                    parts.append(f"PEEP +{vae_data.peep_increase:.0f}")
                return ", ".join(parts)
            return "Ventilator-associated condition detected"

        elif candidate.hai_type == HAIType.CAUTI:
            cauti_data = getattr(candidate, "_cauti_data", None)
            if cauti_data:
                parts = [
                    f"Positive urine culture ({candidate.culture.organism or 'organism pending'})",
                    f"with urinary catheter in place {cauti_data.catheter_days} days",
                ]
                if cauti_data.culture_cfu_ml:
                    parts.append(f"({cauti_data.culture_cfu_ml:,} CFU/mL)")
                return " ".join(parts)
            parts = [f"Positive urine culture ({candidate.culture.organism or 'organism pending'})"]
            if candidate.device_days_at_culture:
                parts.append(f"with catheter in place {candidate.device_days_at_culture} days")
            return " ".join(parts)

        elif candidate.hai_type == HAIType.CDI:
            cdi_data = getattr(candidate, "_cdi_data", None)
            if cdi_data:
                onset_display = {"ho": "HO-CDI", "co": "CO-CDI", "co_hcfa": "CO-HCFA-CDI"}
                onset = onset_display.get(cdi_data.onset_type, cdi_data.onset_type.upper())
                parts = [f"Positive C. diff {cdi_data.test_result.test_type}"]
                parts.append(f"specimen day {cdi_data.specimen_day}")
                parts.append(f"({onset})")
                if cdi_data.is_recurrent:
                    parts.append(f"RECURRENT ({cdi_data.days_since_last_cdi} days since last)")
                elif cdi_data.is_duplicate:
                    parts.append("DUPLICATE")
                else:
                    parts.append("INCIDENT")
                return ", ".join(parts)
            return "Positive C. difficile test detected"

        else:
            # CLABSI summary
            parts = [
                f"Positive blood culture ({candidate.culture.organism or 'organism pending'})",
                f"with central line in place {candidate.device_days_at_culture} days",
            ]
            if candidate.device_info:
                parts.append(f"({candidate.device_info.device_type})")
            return " ".join(parts)
