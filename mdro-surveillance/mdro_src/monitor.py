"""MDRO Surveillance Monitor Service.

Polls FHIR server for new microbiology cultures and processes them
for MDRO detection.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from .classifier import MDROClassifier
from .config import config
from .db import MDRODatabase
from .fhir_client import MDROFHIRClient, CultureResult
from .models import MDROCase, TransmissionStatus

logger = logging.getLogger(__name__)


class MDROMonitor:
    """Monitor service for MDRO surveillance."""

    def __init__(
        self,
        db: MDRODatabase | None = None,
        fhir_client: MDROFHIRClient | None = None,
    ):
        self.db = db or MDRODatabase()
        self.fhir = fhir_client or MDROFHIRClient()
        self.classifier = MDROClassifier()

    def run_once(self, hours_back: int | None = None) -> dict:
        """Run a single polling cycle.

        Args:
            hours_back: Hours to look back (default from config)

        Returns:
            Dict with processing results
        """
        hours = hours_back or config.LOOKBACK_HOURS

        result = {
            "cultures_checked": 0,
            "new_mdro_cases": 0,
            "skipped_already_processed": 0,
            "skipped_not_mdro": 0,
            "errors": [],
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
        }

        try:
            # Get recent cultures from FHIR
            cultures = self.fhir.get_recent_cultures(hours_back=hours)
            result["cultures_checked"] = len(cultures)

            logger.info(f"Found {len(cultures)} cultures in last {hours} hours")

            for culture in cultures:
                try:
                    process_result = self._process_culture(culture)

                    if process_result["status"] == "already_processed":
                        result["skipped_already_processed"] += 1
                    elif process_result["status"] == "not_mdro":
                        result["skipped_not_mdro"] += 1
                    elif process_result["status"] == "new_case":
                        result["new_mdro_cases"] += 1

                except Exception as e:
                    logger.error(f"Error processing culture {culture.fhir_id}: {e}")
                    result["errors"].append({
                        "culture_id": culture.fhir_id,
                        "error": str(e),
                    })

        except Exception as e:
            logger.error(f"Error fetching cultures: {e}")
            result["errors"].append({
                "stage": "fetch_cultures",
                "error": str(e),
            })

        result["completed_at"] = datetime.now().isoformat()
        return result

    def _process_culture(self, culture: CultureResult) -> dict:
        """Process a single culture result.

        Args:
            culture: The culture to process

        Returns:
            Dict with processing status and details
        """
        # Check if already processed
        if self.db.culture_already_processed(culture.fhir_id):
            return {"status": "already_processed"}

        # Classify for MDRO
        classification = self.classifier.classify(
            culture.organism,
            culture.susceptibilities,
        )

        # Log that we processed this culture
        self.db.log_culture_processed(
            culture.fhir_id,
            classification.is_mdro,
            classification.mdro_type.value if classification.mdro_type else None,
        )

        if not classification.is_mdro:
            return {"status": "not_mdro"}

        # Create MDRO case
        case = self._create_case(culture, classification)

        # Classify transmission (community vs healthcare onset)
        transmission_status = self._classify_transmission(case)
        case.transmission_status = transmission_status

        self.db.save_case(case)

        logger.info(
            f"New MDRO case: {case.mdro_type.value} - {case.organism} "
            f"(Patient {case.patient_mrn}, Unit: {case.unit})"
        )

        return {
            "status": "new_case",
            "case_id": case.id,
            "mdro_type": case.mdro_type.value,
            "transmission_status": transmission_status.value,
        }

    def _classify_transmission(self, case: MDROCase) -> TransmissionStatus:
        """Classify transmission as community or healthcare onset.

        Healthcare onset: Culture collected > 48 hours (2 days) after admission
        Community onset: Culture collected <= 48 hours after admission
        """
        if case.days_since_admission is not None:
            if case.days_since_admission > 2:
                return TransmissionStatus.HEALTHCARE_ONSET
            else:
                return TransmissionStatus.COMMUNITY_ONSET

        # If no admission info, default to pending
        return TransmissionStatus.PENDING

    def _create_case(self, culture: CultureResult, classification) -> MDROCase:
        """Create an MDROCase from culture and classification."""
        # Calculate days since admission if we have dates
        days_since_admission = None
        admission_date = None

        if culture.encounter_id:
            admission_date = self.fhir.get_patient_admission_date(
                culture.patient_id,
                culture.encounter_id,
            )
            if admission_date and culture.collection_date:
                delta = culture.collection_date - admission_date
                days_since_admission = delta.days

        # Check for prior MDRO history
        prior_cases = self.db.get_patient_prior_cases(culture.patient_id)
        prior_history = len(prior_cases) > 0
        is_new = not any(
            c.mdro_type == classification.mdro_type
            for c in prior_cases
        )

        return MDROCase(
            id=str(uuid.uuid4()),
            patient_id=culture.patient_id,
            patient_mrn=culture.patient_mrn,
            patient_name=culture.patient_name,
            culture_id=culture.fhir_id,
            culture_date=culture.collection_date,
            specimen_type=culture.specimen_type or "",
            organism=classification.organism,
            mdro_type=classification.mdro_type,
            resistant_antibiotics=classification.resistant_antibiotics,
            classification_reason=classification.classification_reason,
            location=culture.location or "",
            unit=culture.unit or "",
            admission_date=admission_date,
            days_since_admission=days_since_admission,
            is_new=is_new,
            prior_history=prior_history,
        )

    def run_continuous(self, interval_minutes: int | None = None):
        """Run continuous monitoring loop.

        Args:
            interval_minutes: Minutes between polls (default from config)
        """
        interval = interval_minutes or config.POLL_INTERVAL_MINUTES

        logger.info(f"Starting MDRO monitor (polling every {interval} minutes)")

        while True:
            try:
                result = self.run_once()

                logger.info(
                    f"Polling complete: {result['new_mdro_cases']} new cases"
                )

                if result["errors"]:
                    logger.warning(f"Errors during polling: {len(result['errors'])}")

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

            time.sleep(interval * 60)


def run_monitor(once: bool = False, hours_back: int | None = None) -> dict | None:
    """Run the MDRO monitor.

    Args:
        once: If True, run once and return. If False, run continuously.
        hours_back: Hours to look back (default from config)

    Returns:
        Result dict if once=True, None otherwise
    """
    monitor = MDROMonitor()

    if once:
        return monitor.run_once(hours_back)
    else:
        monitor.run_continuous()
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MDRO Surveillance Monitor")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--hours", type=int, help="Hours to look back")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    run_monitor(once=args.once, hours_back=args.hours)
