"""Bundle Trigger Monitor Service.

Polls FHIR server for events that should trigger bundle monitoring:
- New diagnoses (ICD-10 codes)
- Specific orders (medications, labs)
- Lab results
- Vital signs

When a trigger is detected, creates a bundle episode and begins
tracking element compliance.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import sys
from pathlib import Path

# Add parent path for imports
GUIDELINE_ADHERENCE_PATH = Path(__file__).parent.parent
if str(GUIDELINE_ADHERENCE_PATH) not in sys.path:
    sys.path.insert(0, str(GUIDELINE_ADHERENCE_PATH))

from guideline_adherence import GUIDELINE_BUNDLES, GuidelineBundle, BundleElement

from .config import config
from .episode_db import EpisodeDB, BundleEpisode, ElementResult, BundleAlert, BundleTrigger

logger = logging.getLogger(__name__)


class BundleTriggerMonitor:
    """Monitors for bundle triggers and manages episode tracking.

    This service polls FHIR for new events that should trigger bundle
    monitoring, creates episodes, tracks element compliance, and
    generates alerts when elements are not met.
    """

    def __init__(
        self,
        fhir_client,
        db: Optional[EpisodeDB] = None,
        poll_interval_seconds: int = 60,
    ):
        """Initialize the bundle monitor.

        Args:
            fhir_client: FHIR client for data access.
            db: Episode database. Creates new if not provided.
            poll_interval_seconds: How often to poll for new triggers.
        """
        self.fhir_client = fhir_client
        self.db = db or EpisodeDB()
        self.poll_interval = poll_interval_seconds
        self.bundles = GUIDELINE_BUNDLES
        self._running = False

        # Load element checkers
        self._checkers = {}
        self._load_checkers()

    def _load_checkers(self):
        """Load element checkers for each bundle type."""
        try:
            from .checkers.febrile_infant_checker import FebrileInfantChecker
            self._checkers["febrile_infant_2024"] = FebrileInfantChecker(self.fhir_client)
        except ImportError:
            logger.warning("Could not load FebrileInfantChecker")

        try:
            from .checkers.hsv_checker import HSVChecker
            self._checkers["neonatal_hsv_2024"] = HSVChecker(self.fhir_client)
        except ImportError:
            logger.warning("Could not load HSVChecker")

        try:
            from .checkers.cdiff_testing_checker import CDiffTestingChecker
            self._checkers["cdiff_testing_2024"] = CDiffTestingChecker(self.fhir_client)
        except ImportError:
            logger.warning("Could not load CDiffTestingChecker")

    def run(self, once: bool = False):
        """Run the monitoring loop.

        Args:
            once: If True, run one cycle and exit.
        """
        self._running = True
        logger.info("Bundle Trigger Monitor starting...")

        while self._running:
            try:
                cycle_start = datetime.now()

                # Poll for new triggers
                self._poll_diagnosis_triggers()
                self._poll_order_triggers()
                self._poll_lab_triggers()

                # Check element status for active episodes
                self._check_active_episodes()

                # Check for overdue elements and generate alerts
                self._check_overdue_elements()

                if once:
                    break

                # Wait for next poll interval
                elapsed = (datetime.now() - cycle_start).total_seconds()
                sleep_time = max(0, self.poll_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except KeyboardInterrupt:
                logger.info("Received interrupt, stopping...")
                self._running = False
            except Exception as e:
                logger.exception(f"Error in monitoring cycle: {e}")
                if once:
                    raise
                time.sleep(self.poll_interval)

        logger.info("Bundle Trigger Monitor stopped.")

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False

    # =========================================================================
    # TRIGGER POLLING
    # =========================================================================

    def _poll_diagnosis_triggers(self):
        """Poll for new diagnoses that should trigger bundles."""
        logger.debug("Polling for diagnosis triggers...")

        # Get last poll time
        last_poll = self.db.get_last_poll_time("diagnosis")
        if not last_poll:
            # Default to last 24 hours on first run
            last_poll = datetime.now() - timedelta(hours=24)

        # Get diagnosis triggers
        triggers = self.db.get_triggers_by_type("diagnosis")
        if not triggers:
            logger.debug("No diagnosis triggers configured")
            return

        # Build list of ICD-10 patterns to search for
        icd10_patterns = [t.trigger_code for t in triggers if t.trigger_code]

        # Query FHIR for new conditions
        conditions = self.fhir_client.get_recent_conditions(
            since_time=last_poll,
            icd10_patterns=icd10_patterns,
        )

        new_episodes = 0
        for condition in conditions:
            patient_id = condition.get("patient_id")
            encounter_id = condition.get("encounter_id")
            icd10_code = condition.get("code")
            recorded_time = condition.get("recorded_time")

            if not all([patient_id, encounter_id, icd10_code]):
                continue

            # Find matching triggers
            matching_bundles = self._match_triggers(
                triggers, icd10_code, patient_id, encounter_id
            )

            for bundle_id, trigger in matching_bundles:
                # Check if episode already exists
                existing = self.db.get_active_episode(
                    patient_id, encounter_id, bundle_id
                )
                if existing:
                    logger.debug(f"Episode already exists for {patient_id}/{bundle_id}")
                    continue

                # Create new episode
                episode = self._create_episode(
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                    bundle_id=bundle_id,
                    trigger_type="diagnosis",
                    trigger_code=icd10_code,
                    trigger_description=trigger.trigger_description,
                    trigger_time=recorded_time or datetime.now(),
                )

                if episode:
                    new_episodes += 1
                    logger.info(
                        f"Created episode for {patient_id}: {bundle_id} "
                        f"(trigger: {icd10_code})"
                    )

        # Update poll time
        self.db.update_poll_time("diagnosis", datetime.now(), new_episodes)
        logger.debug(f"Diagnosis poll complete: {new_episodes} new episodes")

    def _poll_order_triggers(self):
        """Poll for new orders that should trigger bundles."""
        logger.debug("Polling for order triggers...")

        last_poll = self.db.get_last_poll_time("order")
        if not last_poll:
            last_poll = datetime.now() - timedelta(hours=24)

        # Get medication and order triggers
        med_triggers = self.db.get_triggers_by_type("medication")
        order_triggers = self.db.get_triggers_by_type("order")
        triggers = med_triggers + order_triggers

        if not triggers:
            logger.debug("No order triggers configured")
            return

        # Query FHIR for new medication orders
        orders = self.fhir_client.get_recent_medication_orders(since_time=last_poll)

        new_episodes = 0
        for order in orders:
            patient_id = order.get("patient_id")
            encounter_id = order.get("encounter_id")
            medication_name = order.get("medication_name", "").lower()
            order_time = order.get("order_time")

            if not all([patient_id, encounter_id, medication_name]):
                continue

            # Find matching triggers
            for trigger in triggers:
                if trigger.trigger_code and trigger.trigger_code.lower() in medication_name:
                    # Check age criteria
                    if not self._check_age_criteria(patient_id, trigger):
                        continue

                    # Check if episode already exists
                    existing = self.db.get_active_episode(
                        patient_id, encounter_id, trigger.bundle_id
                    )
                    if existing:
                        continue

                    # Create new episode
                    episode = self._create_episode(
                        patient_id=patient_id,
                        encounter_id=encounter_id,
                        bundle_id=trigger.bundle_id,
                        trigger_type="medication",
                        trigger_code=medication_name,
                        trigger_description=trigger.trigger_description,
                        trigger_time=order_time or datetime.now(),
                    )

                    if episode:
                        new_episodes += 1
                        logger.info(
                            f"Created episode for {patient_id}: {trigger.bundle_id} "
                            f"(trigger: {medication_name})"
                        )

        self.db.update_poll_time("order", datetime.now(), new_episodes)
        logger.debug(f"Order poll complete: {new_episodes} new episodes")

    def _poll_lab_triggers(self):
        """Poll for lab orders/results that should trigger bundles."""
        logger.debug("Polling for lab triggers...")

        last_poll = self.db.get_last_poll_time("lab")
        if not last_poll:
            last_poll = datetime.now() - timedelta(hours=24)

        triggers = self.db.get_triggers_by_type("lab")
        if not triggers:
            logger.debug("No lab triggers configured")
            return

        # Get LOINC codes from triggers
        loinc_codes = [t.trigger_code for t in triggers if t.trigger_code]

        # Query FHIR for lab orders with these LOINC codes
        lab_orders = self.fhir_client.get_recent_lab_orders(
            since_time=last_poll,
            loinc_codes=loinc_codes,
        )

        new_episodes = 0
        for lab in lab_orders:
            patient_id = lab.get("patient_id")
            encounter_id = lab.get("encounter_id")
            loinc_code = lab.get("loinc_code")
            order_time = lab.get("order_time")

            if not all([patient_id, encounter_id, loinc_code]):
                continue

            # Find matching trigger
            for trigger in triggers:
                if trigger.trigger_code == loinc_code:
                    # Check age criteria
                    if not self._check_age_criteria(patient_id, trigger):
                        continue

                    # Check if episode already exists
                    existing = self.db.get_active_episode(
                        patient_id, encounter_id, trigger.bundle_id
                    )
                    if existing:
                        continue

                    # Create new episode
                    episode = self._create_episode(
                        patient_id=patient_id,
                        encounter_id=encounter_id,
                        bundle_id=trigger.bundle_id,
                        trigger_type="lab",
                        trigger_code=loinc_code,
                        trigger_description=trigger.trigger_description,
                        trigger_time=order_time or datetime.now(),
                    )

                    if episode:
                        new_episodes += 1
                        logger.info(
                            f"Created episode for {patient_id}: {trigger.bundle_id} "
                            f"(trigger: LOINC {loinc_code})"
                        )

        self.db.update_poll_time("lab", datetime.now(), new_episodes)
        logger.debug(f"Lab poll complete: {new_episodes} new episodes")

    def _match_triggers(
        self,
        triggers: list[BundleTrigger],
        code: str,
        patient_id: str,
        encounter_id: str,
    ) -> list[tuple[str, BundleTrigger]]:
        """Find triggers that match a given code.

        Args:
            triggers: List of triggers to check.
            code: Code to match (ICD-10, LOINC, etc.).
            patient_id: Patient ID for age checking.
            encounter_id: Encounter ID.

        Returns:
            List of (bundle_id, trigger) tuples for matches.
        """
        matches = []

        for trigger in triggers:
            # Check code match
            if trigger.trigger_code:
                pattern = trigger.trigger_code.replace("%", ".*")
                if not re.match(pattern, code, re.IGNORECASE):
                    continue

            # Check pattern match
            if trigger.trigger_pattern:
                if not re.match(trigger.trigger_pattern, code, re.IGNORECASE):
                    continue

            # Check age criteria
            if not self._check_age_criteria(patient_id, trigger):
                continue

            matches.append((trigger.bundle_id, trigger))

        return matches

    def _check_age_criteria(self, patient_id: str, trigger: BundleTrigger) -> bool:
        """Check if patient meets age criteria for trigger.

        Args:
            patient_id: Patient ID.
            trigger: Trigger with age criteria.

        Returns:
            True if age criteria met or no criteria specified.
        """
        if trigger.age_min_days is None and trigger.age_max_days is None:
            return True

        # Get patient age
        patient = self.fhir_client.get_patient(patient_id)
        if not patient or not patient.get("birth_date"):
            return True  # Allow if can't determine age

        birth_date = patient["birth_date"]
        age_days = (datetime.now().date() - birth_date).days

        if trigger.age_min_days is not None and age_days < trigger.age_min_days:
            return False

        if trigger.age_max_days is not None and age_days > trigger.age_max_days:
            return False

        return True

    # =========================================================================
    # EPISODE MANAGEMENT
    # =========================================================================

    def _create_episode(
        self,
        patient_id: str,
        encounter_id: str,
        bundle_id: str,
        trigger_type: str,
        trigger_code: str,
        trigger_description: str,
        trigger_time: datetime,
    ) -> Optional[BundleEpisode]:
        """Create a new bundle episode.

        Args:
            patient_id: FHIR patient ID.
            encounter_id: FHIR encounter ID.
            bundle_id: Bundle to track.
            trigger_type: Type of trigger (diagnosis, order, lab).
            trigger_code: Code that triggered the bundle.
            trigger_description: Description of trigger.
            trigger_time: When the trigger occurred.

        Returns:
            Created BundleEpisode or None if bundle not found.
        """
        bundle = self.bundles.get(bundle_id)
        if not bundle:
            logger.warning(f"Bundle not found: {bundle_id}")
            return None

        # Get patient info
        patient = self.fhir_client.get_patient(patient_id)
        patient_mrn = patient.get("mrn") if patient else None
        patient_age_days = None
        patient_age_months = None

        if patient and patient.get("birth_date"):
            birth_date = patient["birth_date"]
            patient_age_days = (trigger_time.date() - birth_date).days
            patient_age_months = patient_age_days / 30.44

        # Create episode
        episode = BundleEpisode(
            patient_id=patient_id,
            patient_mrn=patient_mrn,
            encounter_id=encounter_id,
            bundle_id=bundle_id,
            bundle_name=bundle.name,
            trigger_type=trigger_type,
            trigger_code=trigger_code,
            trigger_description=trigger_description,
            trigger_time=trigger_time,
            patient_age_days=patient_age_days,
            patient_age_months=patient_age_months,
            elements_total=len(bundle.elements),
        )

        episode_id = self.db.save_episode(episode)
        episode.id = episode_id

        # Initialize element results
        self._initialize_element_results(episode, bundle)

        return episode

    def _initialize_element_results(self, episode: BundleEpisode, bundle: GuidelineBundle):
        """Initialize element result records for an episode.

        Args:
            episode: The episode to initialize.
            bundle: The bundle definition.
        """
        for element in bundle.elements:
            # Calculate deadline if time window specified
            deadline = None
            if element.time_window_hours:
                deadline = episode.trigger_time + timedelta(hours=element.time_window_hours)

            result = ElementResult(
                episode_id=episode.id,
                element_id=element.element_id,
                element_name=element.name,
                element_description=element.description,
                required=element.required,
                time_window_hours=element.time_window_hours,
                deadline=deadline,
                status="pending",
            )

            self.db.save_element_result(result)

    # =========================================================================
    # ELEMENT CHECKING
    # =========================================================================

    def _check_active_episodes(self):
        """Check element status for all active episodes."""
        episodes = self.db.get_active_episodes()
        logger.debug(f"Checking {len(episodes)} active episodes...")

        for episode in episodes:
            self._check_episode_elements(episode)

    def _check_episode_elements(self, episode: BundleEpisode):
        """Check all elements for an episode.

        Args:
            episode: Episode to check.
        """
        bundle = self.bundles.get(episode.bundle_id)
        if not bundle:
            return

        checker = self._checkers.get(episode.bundle_id)
        element_results = self.db.get_element_results(episode.id)

        elements_met = 0
        elements_not_met = 0
        elements_pending = 0
        elements_na = 0

        for result in element_results:
            # Skip if already resolved
            if result.status in ["met", "not_met", "na"]:
                if result.status == "met":
                    elements_met += 1
                elif result.status == "not_met":
                    elements_not_met += 1
                else:
                    elements_na += 1
                continue

            # Find the bundle element definition
            element = next(
                (e for e in bundle.elements if e.element_id == result.element_id),
                None,
            )

            if not element:
                continue

            # Check element status
            if checker:
                check_result = checker.check(
                    element=element,
                    patient_id=episode.patient_id,
                    trigger_time=episode.trigger_time,
                    age_days=episode.patient_age_days,
                )

                # Update result
                result.status = check_result.status.value
                result.completed_at = check_result.completed_at
                result.value = str(check_result.value) if check_result.value else None
                result.notes = check_result.notes

                self.db.save_element_result(result)

            # Count status
            if result.status == "met":
                elements_met += 1
            elif result.status == "not_met":
                elements_not_met += 1
            elif result.status == "na":
                elements_na += 1
            else:
                elements_pending += 1

        # Update episode totals
        elements_applicable = elements_met + elements_not_met + elements_pending
        adherence_pct = (
            round(elements_met / elements_applicable * 100, 1)
            if elements_applicable > 0
            else 100.0
        )

        episode.elements_applicable = elements_applicable
        episode.elements_met = elements_met
        episode.elements_not_met = elements_not_met
        episode.elements_pending = elements_pending
        episode.adherence_percentage = adherence_pct

        if adherence_pct == 100:
            episode.adherence_level = "full"
        elif adherence_pct > 50:
            episode.adherence_level = "partial"
        else:
            episode.adherence_level = "low"

        # Check if episode is complete (no pending elements)
        if elements_pending == 0:
            episode.status = "completed"
            episode.completed_at = datetime.now()

        self.db.save_episode(episode)

    # =========================================================================
    # ALERT GENERATION
    # =========================================================================

    def _check_overdue_elements(self):
        """Check for overdue elements and generate alerts."""
        overdue = self.db.get_overdue_elements()
        logger.debug(f"Found {len(overdue)} overdue elements")

        for result in overdue:
            # Get episode info
            episode = self.db.get_episode(result.episode_id)
            if not episode:
                continue

            # Check if alert already exists for this element
            # (simple deduplication - could be more sophisticated)

            # Create alert
            severity = "critical" if result.required else "warning"

            alert = BundleAlert(
                episode_id=episode.id,
                element_result_id=result.id,
                patient_id=episode.patient_id,
                patient_mrn=episode.patient_mrn,
                encounter_id=episode.encounter_id,
                bundle_id=episode.bundle_id,
                bundle_name=episode.bundle_name,
                element_id=result.element_id,
                element_name=result.element_name,
                alert_type="element_overdue",
                severity=severity,
                title=f"Overdue: {result.element_name}",
                message=(
                    f"Bundle element '{result.element_name}' for {episode.bundle_name} "
                    f"is past deadline. Deadline was {result.deadline}. "
                    f"Patient: {episode.patient_mrn or episode.patient_id}"
                ),
            )

            self.db.save_alert(alert)

            # Update element status to not_met
            result.status = "not_met"
            result.notes = f"Deadline passed: {result.deadline}"
            self.db.save_element_result(result)

            logger.warning(
                f"Alert: {result.element_name} overdue for patient "
                f"{episode.patient_mrn or episode.patient_id}"
            )

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def manually_trigger_bundle(
        self,
        patient_id: str,
        encounter_id: str,
        bundle_id: str,
        reason: str = "Manual trigger",
    ) -> Optional[BundleEpisode]:
        """Manually trigger a bundle for a patient.

        Args:
            patient_id: FHIR patient ID.
            encounter_id: FHIR encounter ID.
            bundle_id: Bundle to trigger.
            reason: Reason for manual trigger.

        Returns:
            Created episode or None.
        """
        return self._create_episode(
            patient_id=patient_id,
            encounter_id=encounter_id,
            bundle_id=bundle_id,
            trigger_type="manual",
            trigger_code="MANUAL",
            trigger_description=reason,
            trigger_time=datetime.now(),
        )

    def get_episode_status(self, episode_id: int) -> dict:
        """Get detailed status for an episode.

        Args:
            episode_id: Episode ID.

        Returns:
            Dict with episode and element details.
        """
        episode = self.db.get_episode(episode_id)
        if not episode:
            return {}

        elements = self.db.get_element_results(episode_id)

        return {
            "episode": {
                "id": episode.id,
                "patient_id": episode.patient_id,
                "patient_mrn": episode.patient_mrn,
                "bundle_id": episode.bundle_id,
                "bundle_name": episode.bundle_name,
                "trigger_type": episode.trigger_type,
                "trigger_time": episode.trigger_time.isoformat() if episode.trigger_time else None,
                "status": episode.status,
                "adherence_percentage": episode.adherence_percentage,
                "adherence_level": episode.adherence_level,
            },
            "elements": [
                {
                    "element_id": e.element_id,
                    "name": e.element_name,
                    "required": e.required,
                    "status": e.status,
                    "deadline": e.deadline.isoformat() if e.deadline else None,
                    "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                    "value": e.value,
                    "notes": e.notes,
                }
                for e in elements
            ],
            "summary": {
                "total": len(elements),
                "met": sum(1 for e in elements if e.status == "met"),
                "not_met": sum(1 for e in elements if e.status == "not_met"),
                "pending": sum(1 for e in elements if e.status == "pending"),
                "na": sum(1 for e in elements if e.status == "na"),
            },
        }
