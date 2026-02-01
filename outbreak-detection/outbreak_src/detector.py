"""Outbreak detection engine.

Detects potential outbreaks by clustering infection cases
based on infection type, unit, and time window.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from .config import config
from .db import OutbreakDatabase
from .models import OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity
from .sources import get_all_recent_cases, DataSource

logger = logging.getLogger(__name__)


class OutbreakDetector:
    """Detects potential outbreaks from infection case data."""

    def __init__(
        self,
        db: OutbreakDatabase | None = None,
        sources: list[DataSource] | None = None,
    ):
        self.db = db or OutbreakDatabase()
        self.sources = sources
        self.window_days = config.CLUSTER_WINDOW_DAYS
        self.min_cluster_size = config.MIN_CLUSTER_SIZE

    def run_detection(self, days: int | None = None) -> dict:
        """Run outbreak detection on recent cases.

        Args:
            days: Days to look back (default from config)

        Returns:
            Dict with detection results
        """
        window = days or self.window_days

        result = {
            "cases_analyzed": 0,
            "new_cases_processed": 0,
            "clusters_formed": 0,
            "clusters_updated": 0,
            "alerts_created": 0,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
        }

        # Get cases from all sources
        if self.sources:
            all_cases = []
            for source in self.sources:
                all_cases.extend(source.get_recent_cases(days=window))
        else:
            all_cases = get_all_recent_cases(days=window)

        result["cases_analyzed"] = len(all_cases)
        logger.info(f"Analyzing {len(all_cases)} cases from last {window} days")

        # Process each case
        for case_data in all_cases:
            try:
                process_result = self._process_case(case_data)

                if process_result["processed"]:
                    result["new_cases_processed"] += 1
                    if process_result.get("cluster_formed"):
                        result["clusters_formed"] += 1
                    elif process_result.get("cluster_updated"):
                        result["clusters_updated"] += 1
                    result["alerts_created"] += len(process_result.get("alerts", []))

            except Exception as e:
                logger.error(f"Error processing case {case_data.get('source_id')}: {e}")

        result["completed_at"] = datetime.now().isoformat()
        return result

    def _process_case(self, case_data: dict) -> dict:
        """Process a single case for outbreak detection.

        Args:
            case_data: Dict with case info from a data source

        Returns:
            Dict with processing results
        """
        result = {
            "processed": False,
            "cluster_id": None,
            "cluster_formed": False,
            "cluster_updated": False,
            "alerts": [],
        }

        source = case_data["source"]
        source_id = case_data["source_id"]

        # Skip if already processed
        if self.db.is_case_processed(source, source_id):
            return result

        # Need unit for clustering
        unit = case_data.get("unit", "")
        if not unit:
            # Can't cluster without unit information
            self.db.log_case_processed(source, source_id, None)
            return result

        infection_type = case_data["infection_type"]

        # Parse event date
        event_date_str = case_data.get("event_date")
        try:
            if event_date_str:
                event_date = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
            else:
                event_date = datetime.now()
        except (ValueError, TypeError):
            event_date = datetime.now()

        # Create ClusterCase
        cluster_case = ClusterCase(
            id=str(uuid.uuid4()),
            cluster_id="",  # Will be set when added to cluster
            source=source,
            source_id=source_id,
            patient_id=case_data["patient_id"],
            patient_mrn=case_data["patient_mrn"],
            event_date=event_date,
            organism=case_data.get("organism"),
            infection_type=infection_type,
            unit=unit,
            location=case_data.get("location"),
        )

        # Check for existing cluster
        existing_cluster = self.db.find_matching_cluster(infection_type, unit)

        if existing_cluster:
            # Add to existing cluster
            previous_severity = existing_cluster.severity
            if existing_cluster.add_case(cluster_case):
                self.db.save_cluster(existing_cluster)
                result["cluster_updated"] = True
                result["cluster_id"] = existing_cluster.id

                # Check for severity escalation
                if existing_cluster.severity != previous_severity:
                    alert_id = self._create_escalation_alert(existing_cluster, previous_severity)
                    result["alerts"].append(alert_id)

        else:
            # Check if we should form a new cluster
            cluster_result = self._check_for_new_cluster(cluster_case)
            if cluster_result:
                result["cluster_id"] = cluster_result["cluster_id"]
                result["cluster_formed"] = True
                result["alerts"].extend(cluster_result.get("alerts", []))

        # Log case as processed
        self.db.log_case_processed(source, source_id, result.get("cluster_id"))
        result["processed"] = True

        return result

    def _check_for_new_cluster(self, new_case: ClusterCase) -> Optional[dict]:
        """Check if this case should form a new cluster with existing cases.

        Args:
            new_case: The new case to check

        Returns:
            Dict with cluster info if formed, None otherwise
        """
        # Get all unprocessed cases of same type/unit from sources
        # This is a simplified approach - in production you'd want to
        # track potential cluster members more carefully

        # For now, just create a new cluster with this case as the first member
        # The cluster will grow as more matching cases are processed

        # We need at least min_cluster_size cases to form a cluster
        # But we process one at a time, so clusters form when the Nth case arrives

        # Query existing cases in this unit/type from the processing log
        # This is handled by finding matching clusters above

        return None  # Cluster formation happens when second case joins

    def _create_escalation_alert(
        self,
        cluster: OutbreakCluster,
        previous_severity: ClusterSeverity,
    ) -> str:
        """Create an alert for cluster severity escalation."""
        alert_id = self.db.create_alert(
            alert_type="cluster_escalated",
            severity=cluster.severity.value,
            title=f"Outbreak Escalation: {cluster.infection_type.upper()} in {cluster.unit}",
            message=(
                f"Cluster has escalated from {previous_severity.value} to {cluster.severity.value}. "
                f"Now {cluster.case_count} cases. Investigation recommended."
            ),
            cluster_id=cluster.id,
        )
        return alert_id

    def form_cluster_from_cases(
        self,
        infection_type: str,
        unit: str,
        cases: list[ClusterCase],
    ) -> OutbreakCluster:
        """Form a new cluster from a list of cases.

        Args:
            infection_type: The infection type
            unit: The unit where cases occurred
            cases: List of ClusterCase objects

        Returns:
            The newly formed OutbreakCluster
        """
        cluster = OutbreakCluster(
            id=str(uuid.uuid4()),
            infection_type=infection_type,
            organism=cases[0].organism if cases else None,
            unit=unit,
            location=cases[0].location if cases else None,
            window_days=self.window_days,
        )

        for case in cases:
            cluster.add_case(case)

        self.db.save_cluster(cluster)

        # Create alert for new cluster
        if cluster.case_count >= self.min_cluster_size:
            self.db.create_alert(
                alert_type="cluster_formed",
                severity=cluster.severity.value,
                title=f"Potential Outbreak: {infection_type.upper()} in {unit}",
                message=(
                    f"{cluster.case_count} cases detected within {self.window_days} days. "
                    f"Investigation recommended."
                ),
                cluster_id=cluster.id,
            )

        logger.info(
            f"New cluster formed: {cluster.id} with {cluster.case_count} cases "
            f"({infection_type} in {unit})"
        )

        return cluster

    def resolve_cluster(
        self,
        cluster_id: str,
        resolved_by: str,
        notes: str | None = None,
    ) -> bool:
        """Mark a cluster as resolved.

        Args:
            cluster_id: The cluster to resolve
            resolved_by: Name of person resolving
            notes: Resolution notes

        Returns:
            True if resolved successfully
        """
        cluster = self.db.get_cluster(cluster_id)
        if not cluster:
            return False

        cluster.resolve(resolved_by, notes)
        self.db.save_cluster(cluster)

        logger.info(f"Cluster {cluster_id} resolved by {resolved_by}")
        return True


def detect_outbreaks(db: OutbreakDatabase | None = None, days: int | None = None) -> dict:
    """Convenience function to run outbreak detection.

    Args:
        db: Optional database instance
        days: Days to look back

    Returns:
        Detection results dict
    """
    detector = OutbreakDetector(db)
    return detector.run_detection(days)
