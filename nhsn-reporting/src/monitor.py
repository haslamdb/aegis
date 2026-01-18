"""NHSN HAI Candidate Monitor.

Main service that orchestrates:
1. Rule-based candidate detection
2. Note retrieval for LLM context
3. LLM classification (future phase)
4. Routing to IP review queue
"""

import logging
import time
from datetime import datetime, timedelta

from common.alert_store import AlertStore, AlertType

from .config import Config
from .db import NHSNDatabase
from .models import (
    HAICandidate,
    HAIType,
    CandidateStatus,
)
from .candidates import CLABSICandidateDetector

logger = logging.getLogger(__name__)


class NHSNMonitor:
    """Monitor for NHSN HAI candidate detection and classification."""

    def __init__(
        self,
        db: NHSNDatabase | None = None,
        alert_store: AlertStore | None = None,
        lookback_hours: int | None = None,
    ):
        """Initialize the monitor.

        Args:
            db: NHSN database instance. Creates default if None.
            alert_store: Shared alert store. Creates default if None.
            lookback_hours: Hours to look back for new cultures. Uses config if None.
        """
        self.db = db or NHSNDatabase(Config.NHSN_DB_PATH)
        self.alert_store = alert_store or AlertStore(db_path=Config.ALERT_DB_PATH)
        self.lookback_hours = lookback_hours or Config.LOOKBACK_HOURS

        # Initialize detectors for each HAI type
        self.detectors = {
            HAIType.CLABSI: CLABSICandidateDetector(),
            # Future: CAUTI, SSI, VAE detectors
        }

        # Track processed cultures to avoid duplicates within session
        self._processed_cultures: set[str] = set()

    def run_once(self, dry_run: bool = False) -> int:
        """Run a single detection cycle.

        Args:
            dry_run: If True, don't save candidates or create alerts.

        Returns:
            Number of new candidates identified.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=self.lookback_hours)

        logger.info(f"Starting detection cycle: {start_date} to {end_date}")

        total_candidates = 0

        for hai_type, detector in self.detectors.items():
            logger.info(f"Running {hai_type.value} detection...")

            try:
                candidates = detector.detect_candidates(start_date, end_date)
                new_count = self._process_candidates(candidates, dry_run=dry_run)
                total_candidates += new_count

                logger.info(
                    f"{hai_type.value}: {len(candidates)} candidates found, "
                    f"{new_count} new"
                )

            except Exception as e:
                logger.error(f"Error in {hai_type.value} detection: {e}", exc_info=True)

        logger.info(f"Detection cycle complete: {total_candidates} new candidates")
        return total_candidates

    def _process_candidates(
        self,
        candidates: list[HAICandidate],
        dry_run: bool = False,
    ) -> int:
        """Process detected candidates.

        Args:
            candidates: List of candidates from detector.
            dry_run: If True, don't persist anything.

        Returns:
            Number of new candidates processed.
        """
        new_count = 0

        for candidate in candidates:
            # Skip if already processed this session
            if candidate.culture.fhir_id in self._processed_cultures:
                continue

            # Check if already in database
            if self.db.check_candidate_exists(
                candidate.hai_type, candidate.culture.fhir_id
            ):
                logger.debug(
                    f"Candidate already exists: {candidate.culture.fhir_id}"
                )
                continue

            # Skip if already alerted in shared store
            if self.alert_store.check_if_alerted(
                AlertType.NHSN_CLABSI, candidate.culture.fhir_id
            ):
                logger.debug(
                    f"Alert already exists for: {candidate.culture.fhir_id}"
                )
                continue

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would create candidate: "
                    f"Patient={candidate.patient.mrn}, "
                    f"Organism={candidate.culture.organism}, "
                    f"Device days={candidate.device_days_at_culture}, "
                    f"Meets criteria={candidate.meets_initial_criteria}"
                )
            else:
                # Save to NHSN database
                self.db.save_candidate(candidate)

                # Create alert in shared store for dashboard visibility
                if candidate.meets_initial_criteria:
                    self._create_alert(candidate)
                    # Send email notification for new HAI candidate
                    self._send_new_candidate_email(candidate)

                logger.info(
                    f"Created candidate: {candidate.id} "
                    f"(Patient={candidate.patient.mrn})"
                )

            self._processed_cultures.add(candidate.culture.fhir_id)
            new_count += 1

        return new_count

    def _create_alert(self, candidate: HAICandidate) -> None:
        """Create alert in shared store for dashboard visibility."""
        title = f"CLABSI Candidate: {candidate.patient.name or candidate.patient.mrn}"
        summary = self._build_summary(candidate)

        self.alert_store.save_alert(
            alert_type=AlertType.NHSN_CLABSI,
            source_id=candidate.culture.fhir_id,
            severity="warning",
            patient_id=candidate.patient.fhir_id,
            patient_mrn=candidate.patient.mrn,
            patient_name=candidate.patient.name,
            title=title,
            summary=summary,
            content={
                "candidate_id": candidate.id,
                "hai_type": candidate.hai_type.value,
                "organism": candidate.culture.organism,
                "device_days": candidate.device_days_at_culture,
                "device_type": candidate.device_info.device_type if candidate.device_info else None,
                "culture_date": candidate.culture.collection_date.isoformat(),
            },
        )

    def _build_summary(self, candidate: HAICandidate) -> str:
        """Build alert summary text."""
        parts = [
            f"Positive blood culture ({candidate.culture.organism or 'organism pending'})",
            f"with central line in place {candidate.device_days_at_culture} days",
        ]

        if candidate.device_info:
            parts.append(f"({candidate.device_info.device_type})")

        return " ".join(parts)

    def _send_new_candidate_email(self, candidate: HAICandidate) -> None:
        """Send email notification for new HAI candidate."""
        if not Config.is_email_configured():
            return

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            subject = f"New CLABSI Candidate: {candidate.patient.mrn} - {candidate.culture.organism or 'Organism Pending'}"

            body = f"""
New CLABSI Candidate Detected

Patient Information:
  - Name: {candidate.patient.name or 'Unknown'}
  - MRN: {candidate.patient.mrn}
  - Location: {candidate.patient.location or 'Unknown'}

Culture Information:
  - Organism: {candidate.culture.organism or 'Pending identification'}
  - Collection Date: {candidate.culture.collection_date.strftime('%Y-%m-%d %H:%M')}

Central Line Information:
  - Device Type: {candidate.device_info.device_type if candidate.device_info else 'Unknown'}
  - Device Days at Culture: {candidate.device_days_at_culture}
  - Insertion Date: {candidate.device_info.insertion_date.strftime('%Y-%m-%d') if candidate.device_info and candidate.device_info.insertion_date else 'Unknown'}

This candidate requires IP review.

Review in Dashboard: {Config.DASHBOARD_BASE_URL}/nhsn/candidates/{candidate.id}
"""

            # Parse recipient list (can be comma-separated)
            recipients = [
                email.strip()
                for email in Config.NHSN_NOTIFICATION_EMAIL.split(',')
                if email.strip()
            ]

            msg = MIMEMultipart()
            msg['From'] = f"{Config.SENDER_NAME} <{Config.SENDER_EMAIL}>"
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                server.starttls()
                # Login if credentials provided
                if Config.SMTP_USERNAME and Config.SMTP_PASSWORD:
                    server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
                server.sendmail(Config.SENDER_EMAIL, recipients, msg.as_string())

            logger.info(f"Sent email notification for candidate {candidate.id} to {recipients}")

        except Exception as e:
            logger.warning(f"Failed to send email notification: {e}")

    def run_continuous(self, interval_seconds: int | None = None) -> None:
        """Run continuous monitoring loop.

        Args:
            interval_seconds: Seconds between checks. Uses config if None.
        """
        interval = interval_seconds or Config.POLL_INTERVAL
        logger.info(f"Starting continuous monitoring (interval: {interval}s)")

        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}", exc_info=True)

            logger.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)

    def get_pending_candidates(
        self, hai_type: HAIType | None = None
    ) -> list[HAICandidate]:
        """Get candidates pending classification.

        Args:
            hai_type: Filter by HAI type. All types if None.

        Returns:
            List of pending candidates.
        """
        return self.db.get_candidates_by_status(CandidateStatus.PENDING, hai_type)

    def get_candidates_for_review(
        self, hai_type: HAIType | None = None
    ) -> list[HAICandidate]:
        """Get candidates pending IP review.

        Args:
            hai_type: Filter by HAI type. All types if None.

        Returns:
            List of candidates pending review.
        """
        return self.db.get_candidates_by_status(CandidateStatus.PENDING_REVIEW, hai_type)

    def get_recent_candidates(
        self, limit: int = 100, hai_type: HAIType | None = None
    ) -> list[HAICandidate]:
        """Get recent candidates for dashboard display.

        Args:
            limit: Maximum number to return.
            hai_type: Filter by HAI type. All types if None.

        Returns:
            List of recent candidates.
        """
        return self.db.get_recent_candidates(limit, hai_type)

    def get_stats(self) -> dict:
        """Get summary statistics for dashboard."""
        return self.db.get_summary_stats()
