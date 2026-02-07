"""Cross-module metrics aggregation for ASP/IP monitoring.

Provides daily snapshot creation, intervention target identification,
and trending analysis across all monitoring modules.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any

from .models import (
    DailySnapshot,
    InterventionTarget,
    TargetType,
    TargetStatus,
    IssueType,
)
from .store import MetricsStore

logger = logging.getLogger(__name__)


@dataclass
class LocationScore:
    """Aggregated score for a hospital location/unit."""
    location_code: str
    location_name: str | None = None
    total_score: float = 0.0
    inappropriate_abx_rate: float | None = None
    bundle_adherence_rate: float | None = None
    hai_rate: float | None = None
    alert_response_time_minutes: float | None = None
    therapy_change_rate: float | None = None
    total_alerts: int = 0
    total_reviews: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass
class ServiceScore:
    """Aggregated score for a medical service."""
    service_name: str
    total_score: float = 0.0
    inappropriate_abx_rate: float | None = None
    bundle_adherence_rate: float | None = None
    total_orders: int = 0
    total_reviews: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass
class ResolutionPatterns:
    """Analysis of alert resolution patterns."""
    total_resolved: int = 0
    resolution_breakdown: dict[str, int] = field(default_factory=dict)
    avg_time_to_resolve_minutes: float | None = None
    therapy_change_rate: float | None = None
    by_alert_type: dict[str, dict] = field(default_factory=dict)


class MetricsAggregator:
    """Aggregates metrics across all ASP/IP modules for unified reporting.

    This class pulls data from individual module databases and creates
    unified daily snapshots and intervention targets.
    """

    def __init__(
        self,
        metrics_store: MetricsStore | None = None,
        alert_db_path: str | None = None,
        hai_db_path: str | None = None,
        adherence_db_path: str | None = None,
        indication_db_path: str | None = None,
    ):
        """Initialize the aggregator.

        Args:
            metrics_store: MetricsStore instance (creates new if None)
            alert_db_path: Path to alert store database
            hai_db_path: Path to HAI detection database
            adherence_db_path: Path to guideline adherence database
            indication_db_path: Path to indication monitoring database
        """
        self.metrics_store = metrics_store or MetricsStore()

        # Store paths for lazy initialization of module databases
        self._alert_db_path = alert_db_path
        self._hai_db_path = hai_db_path
        self._adherence_db_path = adherence_db_path
        self._indication_db_path = indication_db_path

    def _get_alert_store(self):
        """Get AlertStore instance."""
        try:
            from common.alert_store import AlertStore
            return AlertStore(db_path=self._alert_db_path)
        except Exception as e:
            logger.warning(f"Failed to get AlertStore: {e}")
            return None

    def _get_hai_db(self):
        """Get HAI database instance."""
        try:
            from hai_src.db import HAIDatabase
            db_path = self._hai_db_path or os.path.expanduser(
                os.environ.get("HAI_DB_PATH", "~/.aegis/hai.db")
            )
            return HAIDatabase(db_path)
        except Exception as e:
            logger.warning(f"Failed to get HAI database: {e}")
            return None

    def _get_adherence_db(self):
        """Get guideline adherence database instance."""
        try:
            from guideline_src.episode_db import EpisodeDB
            return EpisodeDB(db_path=self._adherence_db_path)
        except Exception as e:
            logger.warning(f"Failed to get adherence database: {e}")
            return None

    def _get_indication_db(self):
        """Get indication database instance."""
        try:
            from au_alerts_src.indication_db import IndicationDatabase
            return IndicationDatabase(db_path=self._indication_db_path)
        except Exception as e:
            logger.warning(f"Failed to get indication database: {e}")
            return None

    def _get_drug_bug_db_path(self):
        """Get drug-bug alert data from the shared alert store."""
        # Drug-bug uses the same AlertStore, so we reuse _get_alert_store()
        return self._get_alert_store()

    def _get_mdro_db(self):
        """Get MDRO database instance."""
        try:
            from mdro_src.db import MDRODatabase
            from mdro_src.config import config as mdro_config
            db_path = os.path.expanduser(
                os.environ.get("MDRO_DB_PATH", mdro_config.DB_PATH)
            )
            return MDRODatabase(db_path)
        except Exception as e:
            logger.warning(f"Failed to get MDRO database: {e}")
            return None

    def _get_outbreak_db(self):
        """Get Outbreak database instance."""
        try:
            from outbreak_src.db import OutbreakDatabase
            from outbreak_src.config import config as outbreak_config
            db_path = os.path.expanduser(
                os.environ.get("OUTBREAK_DB_PATH", outbreak_config.DB_PATH)
            )
            return OutbreakDatabase(db_path)
        except Exception as e:
            logger.warning(f"Failed to get Outbreak database: {e}")
            return None

    def _get_surgical_db(self):
        """Get Surgical Prophylaxis database instance."""
        try:
            from src.database import ProphylaxisDatabase
            return ProphylaxisDatabase()
        except Exception as e:
            logger.warning(f"Failed to get Surgical Prophylaxis database: {e}")
            return None

    def create_daily_snapshot(self, snapshot_date: date | None = None) -> DailySnapshot:
        """Create a daily metrics snapshot from all modules.

        Args:
            snapshot_date: Date for snapshot (defaults to yesterday)

        Returns:
            DailySnapshot with aggregated metrics
        """
        if snapshot_date is None:
            snapshot_date = date.today() - timedelta(days=1)

        snapshot = DailySnapshot(snapshot_date=snapshot_date)

        # Aggregate from each module
        self._aggregate_alert_metrics(snapshot, snapshot_date)
        self._aggregate_hai_metrics(snapshot, snapshot_date)
        self._aggregate_adherence_metrics(snapshot, snapshot_date)
        self._aggregate_indication_metrics(snapshot, snapshot_date)
        self._aggregate_drug_bug_metrics(snapshot, snapshot_date)
        self._aggregate_mdro_metrics(snapshot, snapshot_date)
        self._aggregate_outbreak_metrics(snapshot, snapshot_date)
        self._aggregate_surgical_metrics(snapshot, snapshot_date)
        self._aggregate_activity_metrics(snapshot, snapshot_date)

        # Save the snapshot
        self.metrics_store.save_daily_snapshot(snapshot)

        logger.info(f"Created daily snapshot for {snapshot_date}")
        return snapshot

    def _aggregate_alert_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate metrics from the alert store."""
        alert_store = self._get_alert_store()
        if not alert_store:
            return

        try:
            import sqlite3
            with sqlite3.connect(alert_store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                date_str = snapshot_date.isoformat()

                # Alerts created on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM alerts WHERE date(created_at) = ?",
                    (date_str,)
                )
                snapshot.alerts_created = cursor.fetchone()[0]

                # Alerts resolved on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM alerts WHERE date(resolved_at) = ?",
                    (date_str,)
                )
                snapshot.alerts_resolved = cursor.fetchone()[0]

                # Alerts acknowledged on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM alerts WHERE date(acknowledged_at) = ?",
                    (date_str,)
                )
                snapshot.alerts_acknowledged = cursor.fetchone()[0]

                # Average time to acknowledge (for alerts acknowledged on this date)
                cursor.execute(
                    """
                    SELECT AVG(
                        CAST((julianday(acknowledged_at) - julianday(created_at)) * 24 * 60 AS REAL)
                    )
                    FROM alerts
                    WHERE date(acknowledged_at) = ? AND acknowledged_at IS NOT NULL
                    """,
                    (date_str,)
                )
                result = cursor.fetchone()[0]
                snapshot.avg_time_to_ack_minutes = round(result, 1) if result else None

                # Average time to resolve (for alerts resolved on this date)
                cursor.execute(
                    """
                    SELECT AVG(
                        CAST((julianday(resolved_at) - julianday(created_at)) * 24 * 60 AS REAL)
                    )
                    FROM alerts
                    WHERE date(resolved_at) = ? AND resolved_at IS NOT NULL
                    """,
                    (date_str,)
                )
                result = cursor.fetchone()[0]
                snapshot.avg_time_to_resolve_minutes = round(result, 1) if result else None

        except Exception as e:
            logger.error(f"Error aggregating alert metrics: {e}")

    def _aggregate_hai_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate metrics from the HAI detection module."""
        hai_db = self._get_hai_db()
        if not hai_db:
            return

        try:
            import sqlite3
            with sqlite3.connect(hai_db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                date_str = snapshot_date.isoformat()

                # Candidates created on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM hai_candidates WHERE date(created_at) = ?",
                    (date_str,)
                )
                snapshot.hai_candidates_created = cursor.fetchone()[0]

                # Candidates reviewed on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM hai_reviews WHERE date(reviewed_at) = ?",
                    (date_str,)
                )
                snapshot.hai_candidates_reviewed = cursor.fetchone()[0]

                # Confirmed HAI on this date
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM hai_candidates
                    WHERE status = 'confirmed'
                    AND date(created_at) = ?
                    """,
                    (date_str,)
                )
                snapshot.hai_confirmed = cursor.fetchone()[0]

                # Overrides on this date
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM hai_reviews
                    WHERE is_override = 1 AND date(reviewed_at) = ?
                    """,
                    (date_str,)
                )
                snapshot.hai_override_count = cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"Error aggregating HAI metrics: {e}")

    def _aggregate_adherence_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate metrics from the guideline adherence module."""
        adherence_db = self._get_adherence_db()
        if not adherence_db:
            return

        try:
            import sqlite3
            with sqlite3.connect(adherence_db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                date_str = snapshot_date.isoformat()

                # Active bundle episodes
                cursor.execute(
                    "SELECT COUNT(*) FROM bundle_episodes WHERE status = 'active'"
                )
                snapshot.bundle_episodes_active = cursor.fetchone()[0]

                # Bundle alerts created on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM bundle_alerts WHERE date(created_at) = ?",
                    (date_str,)
                )
                snapshot.bundle_alerts_created = cursor.fetchone()[0]

                # Average adherence rate for episodes completed on this date
                cursor.execute(
                    """
                    SELECT AVG(adherence_percentage)
                    FROM bundle_episodes
                    WHERE date(completed_at) = ?
                    AND adherence_percentage IS NOT NULL
                    """,
                    (date_str,)
                )
                result = cursor.fetchone()[0]
                snapshot.bundle_adherence_rate = round(result, 1) if result else None

        except Exception as e:
            logger.error(f"Error aggregating adherence metrics: {e}")

    def _aggregate_indication_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate metrics from the indication monitoring module."""
        indication_db = self._get_indication_db()
        if not indication_db:
            return

        try:
            import sqlite3
            with sqlite3.connect(indication_db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                date_str = snapshot_date.isoformat()

                # Reviews on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM indication_reviews WHERE date(reviewed_at) = ?",
                    (date_str,)
                )
                snapshot.indication_reviews = cursor.fetchone()[0]

                # Classification breakdown for orders on this date
                cursor.execute(
                    """
                    SELECT
                        SUM(CASE WHEN final_classification IN ('A', 'S', 'P') THEN 1 ELSE 0 END) as appropriate,
                        SUM(CASE WHEN final_classification = 'N' THEN 1 ELSE 0 END) as inappropriate
                    FROM indication_candidates
                    WHERE date(created_at) = ?
                    """,
                    (date_str,)
                )
                row = cursor.fetchone()
                snapshot.appropriate_count = row["appropriate"] or 0
                snapshot.inappropriate_count = row["inappropriate"] or 0

                total = snapshot.appropriate_count + snapshot.inappropriate_count
                if total > 0:
                    snapshot.inappropriate_rate = round(
                        snapshot.inappropriate_count / total * 100, 1
                    )

        except Exception as e:
            logger.error(f"Error aggregating indication metrics: {e}")

    def _aggregate_drug_bug_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate drug-bug mismatch metrics from the alert store."""
        alert_store = self._get_alert_store()
        if not alert_store:
            return
        try:
            import sqlite3
            with sqlite3.connect(alert_store.db_path) as conn:
                cursor = conn.cursor()
                date_str = snapshot_date.isoformat()

                # Drug-bug alerts created on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM alerts WHERE alert_type = 'drug_bug_mismatch' AND date(created_at) = ?",
                    (date_str,)
                )
                snapshot.drug_bug_alerts_created = cursor.fetchone()[0]

                # Drug-bug alerts resolved on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM alerts WHERE alert_type = 'drug_bug_mismatch' AND date(resolved_at) = ?",
                    (date_str,)
                )
                snapshot.drug_bug_alerts_resolved = cursor.fetchone()[0]

                # Drug-bug alerts resolved with therapy_changed reason
                cursor.execute(
                    """SELECT COUNT(*) FROM alerts
                    WHERE alert_type = 'drug_bug_mismatch'
                    AND date(resolved_at) = ?
                    AND resolution_reason IN ('therapy_changed', 'therapy_stopped')""",
                    (date_str,)
                )
                snapshot.drug_bug_therapy_changed_count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error aggregating drug-bug metrics: {e}")

    def _aggregate_mdro_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate MDRO surveillance metrics."""
        mdro_db = self._get_mdro_db()
        if not mdro_db:
            return
        try:
            import sqlite3
            with sqlite3.connect(mdro_db.db_path) as conn:
                cursor = conn.cursor()
                date_str = snapshot_date.isoformat()

                # MDRO cases identified on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM mdro_cases WHERE date(identified_at) = ?",
                    (date_str,)
                )
                snapshot.mdro_cases_identified = cursor.fetchone()[0]

                # Cases reviewed on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM mdro_reviews WHERE date(reviewed_at) = ?",
                    (date_str,)
                )
                snapshot.mdro_cases_reviewed = cursor.fetchone()[0]

                # Confirmed cases
                cursor.execute(
                    "SELECT COUNT(*) FROM mdro_cases WHERE status = 'confirmed' AND date(identified_at) = ?",
                    (date_str,)
                )
                snapshot.mdro_confirmed = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error aggregating MDRO metrics: {e}")

    def _aggregate_outbreak_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate outbreak detection metrics."""
        outbreak_db = self._get_outbreak_db()
        if not outbreak_db:
            return
        try:
            import sqlite3
            with sqlite3.connect(outbreak_db.db_path) as conn:
                cursor = conn.cursor()
                date_str = snapshot_date.isoformat()

                # Active clusters as of this date
                cursor.execute(
                    "SELECT COUNT(*) FROM outbreak_clusters WHERE status IN ('active', 'investigating')"
                )
                snapshot.outbreak_clusters_active = cursor.fetchone()[0]

                # Alerts triggered on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM outbreak_alerts WHERE date(created_at) = ?",
                    (date_str,)
                )
                snapshot.outbreak_alerts_triggered = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error aggregating outbreak metrics: {e}")

    def _aggregate_surgical_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate surgical prophylaxis metrics."""
        surgical_db = self._get_surgical_db()
        if not surgical_db:
            return
        try:
            import sqlite3
            with sqlite3.connect(surgical_db.db_path) as conn:
                cursor = conn.cursor()
                date_str = snapshot_date.isoformat()

                # Cases evaluated on this date
                cursor.execute(
                    "SELECT COUNT(*) FROM surgical_cases WHERE date(scheduled_or_time) = ?",
                    (date_str,)
                )
                snapshot.surgical_prophylaxis_cases = cursor.fetchone()[0]

                # Compliant cases
                cursor.execute(
                    """SELECT COUNT(*) FROM compliance_evaluations ce
                    JOIN surgical_cases sc ON ce.case_id = sc.case_id
                    WHERE ce.bundle_compliant = 1
                    AND date(sc.scheduled_or_time) = ?""",
                    (date_str,)
                )
                snapshot.surgical_prophylaxis_compliant = cursor.fetchone()[0]

                # Calculate compliance rate
                if snapshot.surgical_prophylaxis_cases > 0:
                    snapshot.surgical_prophylaxis_compliance_rate = round(
                        snapshot.surgical_prophylaxis_compliant / snapshot.surgical_prophylaxis_cases * 100, 1
                    )
        except Exception as e:
            logger.error(f"Error aggregating surgical prophylaxis metrics: {e}")

    def _aggregate_activity_metrics(self, snapshot: DailySnapshot, snapshot_date: date) -> None:
        """Aggregate human activity metrics from the unified metrics store."""
        try:
            activities = self.metrics_store.list_activities(
                start_date=snapshot_date,
                end_date=snapshot_date,
                limit=10000,
            )

            snapshot.total_reviews = sum(
                1 for a in activities if a.activity_type in ("review", "acknowledgment", "resolution")
            )

            provider_ids = set(a.provider_id for a in activities if a.provider_id)
            snapshot.unique_reviewers = len(provider_ids)

            snapshot.total_interventions = sum(
                1 for a in activities if a.activity_type == "intervention"
            )

            # Build location breakdown
            by_location: dict[str, dict] = {}
            for a in activities:
                if a.location_code:
                    if a.location_code not in by_location:
                        by_location[a.location_code] = {"activities": 0, "reviews": 0}
                    by_location[a.location_code]["activities"] += 1
                    if a.activity_type in ("review", "acknowledgment", "resolution"):
                        by_location[a.location_code]["reviews"] += 1
            snapshot.by_location = by_location

            # Build service breakdown
            by_service: dict[str, dict] = {}
            for a in activities:
                if a.service:
                    if a.service not in by_service:
                        by_service[a.service] = {"activities": 0, "reviews": 0}
                    by_service[a.service]["activities"] += 1
                    if a.activity_type in ("review", "acknowledgment", "resolution"):
                        by_service[a.service]["reviews"] += 1
            snapshot.by_service = by_service

        except Exception as e:
            logger.error(f"Error aggregating activity metrics: {e}")

    def calculate_location_scores(self, days: int = 30) -> list[LocationScore]:
        """Calculate aggregate scores by hospital location.

        Args:
            days: Number of days to include in analysis

        Returns:
            List of LocationScore objects sorted by total_score descending
        """
        scores: dict[str, LocationScore] = {}

        # Get indication data by location
        indication_db = self._get_indication_db()
        if indication_db:
            try:
                location_data = indication_db.get_usage_by_location(days=days)
                for loc in location_data:
                    code = loc["location"]
                    if code not in scores:
                        scores[code] = LocationScore(location_code=code)

                    # Calculate inappropriate rate
                    total = loc["total_orders"]
                    if total > 0:
                        rate = loc["inappropriate"] / total * 100
                        scores[code].inappropriate_abx_rate = round(rate, 1)
                        scores[code].total_alerts += total

                        # Add to score (higher inappropriate = worse)
                        scores[code].total_score += rate

                        if rate > 15:
                            scores[code].issues.append(f"High inappropriate ABX rate: {rate:.1f}%")

            except Exception as e:
                logger.error(f"Error getting location indication data: {e}")

        # Get activity data by location
        activity_by_location = self.metrics_store.get_activity_by_location(days=days)
        for loc in activity_by_location:
            code = loc["location_code"]
            if code not in scores:
                scores[code] = LocationScore(location_code=code)
            scores[code].total_reviews = loc["reviews"]

        # Sort by total score (highest = needs most attention)
        result = sorted(scores.values(), key=lambda x: x.total_score, reverse=True)
        return result

    def calculate_service_scores(self, days: int = 30) -> list[ServiceScore]:
        """Calculate aggregate scores by medical service.

        Args:
            days: Number of days to include in analysis

        Returns:
            List of ServiceScore objects sorted by total_score descending
        """
        scores: dict[str, ServiceScore] = {}

        # Get indication data by service
        indication_db = self._get_indication_db()
        if indication_db:
            try:
                service_data = indication_db.get_usage_by_service(days=days)
                for svc in service_data:
                    name = svc["service"]
                    if name not in scores:
                        scores[name] = ServiceScore(service_name=name)

                    total = svc["total_orders"]
                    scores[name].total_orders = total
                    if total > 0:
                        rate = svc["inappropriate"] / total * 100
                        scores[name].inappropriate_abx_rate = round(rate, 1)
                        scores[name].total_score += rate

                        if rate > 15:
                            scores[name].issues.append(f"High inappropriate ABX rate: {rate:.1f}%")

            except Exception as e:
                logger.error(f"Error getting service indication data: {e}")

        # Sort by total score
        result = sorted(scores.values(), key=lambda x: x.total_score, reverse=True)
        return result

    def get_alert_resolution_patterns(self, days: int = 30) -> ResolutionPatterns:
        """Analyze alert resolution patterns.

        Args:
            days: Number of days to include

        Returns:
            ResolutionPatterns with breakdown of how alerts are being resolved
        """
        patterns = ResolutionPatterns()

        alert_store = self._get_alert_store()
        if not alert_store:
            return patterns

        try:
            analytics = alert_store.get_analytics(days=days)

            patterns.total_resolved = analytics.get("total_resolved", 0)

            # Build resolution breakdown
            for item in analytics.get("resolution_breakdown", []):
                patterns.resolution_breakdown[item["reason"]] = item["count"]

            # Calculate therapy change rate
            therapy_changed = patterns.resolution_breakdown.get("therapy_changed", 0)
            therapy_stopped = patterns.resolution_breakdown.get("therapy_stopped", 0)
            total_resolved = patterns.total_resolved
            if total_resolved > 0:
                patterns.therapy_change_rate = round(
                    (therapy_changed + therapy_stopped) / total_resolved * 100, 1
                )

            # Get average resolution time
            response_times = analytics.get("response_times", {})
            patterns.avg_time_to_resolve_minutes = response_times.get("avg_time_to_resolve_minutes")

        except Exception as e:
            logger.error(f"Error getting resolution patterns: {e}")

        return patterns

    def identify_intervention_targets(
        self,
        inappropriate_threshold: float = 15.0,
        adherence_threshold: float = 80.0,
        response_time_threshold_hours: float = 4.0,
        therapy_change_threshold: float = 20.0,
    ) -> list[InterventionTarget]:
        """Identify locations/services that need intervention.

        Args:
            inappropriate_threshold: % inappropriate above which to flag
            adherence_threshold: % adherence below which to flag
            response_time_threshold_hours: Hours response time above which to flag
            therapy_change_threshold: % therapy change rate below which to flag

        Returns:
            List of InterventionTarget objects sorted by priority
        """
        targets: list[InterventionTarget] = []
        today = date.today()

        # Check locations for high inappropriate ABX rate
        location_scores = self.calculate_location_scores(days=30)
        for loc in location_scores:
            if loc.inappropriate_abx_rate and loc.inappropriate_abx_rate > inappropriate_threshold:
                # Check if we already have an active target for this
                existing = self.metrics_store.list_intervention_targets(
                    target_type=TargetType.UNIT,
                    status=[TargetStatus.IDENTIFIED, TargetStatus.PLANNED, TargetStatus.IN_PROGRESS],
                )
                already_tracked = any(
                    t.target_id == loc.location_code and t.issue_type == IssueType.HIGH_INAPPROPRIATE_ABX.value
                    for t in existing
                )

                if not already_tracked:
                    # Create new target
                    priority = (loc.inappropriate_abx_rate - inappropriate_threshold) * 2
                    target_id = self.metrics_store.create_intervention_target(
                        target_type=TargetType.UNIT,
                        target_id=loc.location_code,
                        target_name=loc.location_name or loc.location_code,
                        issue_type=IssueType.HIGH_INAPPROPRIATE_ABX,
                        issue_description=f"Inappropriate antibiotic rate of {loc.inappropriate_abx_rate:.1f}% exceeds threshold of {inappropriate_threshold}%",
                        priority_score=priority,
                        priority_reason=f"Rate {loc.inappropriate_abx_rate:.1f}% - threshold {inappropriate_threshold}% = +{loc.inappropriate_abx_rate - inappropriate_threshold:.1f}pp",
                        baseline_value=loc.inappropriate_abx_rate,
                        target_value=inappropriate_threshold,
                        metric_name="inappropriate_abx_rate",
                        metric_unit="percent",
                        identified_date=today,
                    )
                    target = self.metrics_store.get_intervention_target(target_id)
                    if target:
                        targets.append(target)

        # Check services for high inappropriate ABX rate
        service_scores = self.calculate_service_scores(days=30)
        for svc in service_scores:
            if svc.inappropriate_abx_rate and svc.inappropriate_abx_rate > inappropriate_threshold:
                existing = self.metrics_store.list_intervention_targets(
                    target_type=TargetType.SERVICE,
                    status=[TargetStatus.IDENTIFIED, TargetStatus.PLANNED, TargetStatus.IN_PROGRESS],
                )
                already_tracked = any(
                    t.target_id == svc.service_name and t.issue_type == IssueType.HIGH_INAPPROPRIATE_ABX.value
                    for t in existing
                )

                if not already_tracked:
                    priority = (svc.inappropriate_abx_rate - inappropriate_threshold) * 2
                    target_id = self.metrics_store.create_intervention_target(
                        target_type=TargetType.SERVICE,
                        target_id=svc.service_name,
                        target_name=svc.service_name,
                        issue_type=IssueType.HIGH_INAPPROPRIATE_ABX,
                        issue_description=f"Inappropriate antibiotic rate of {svc.inappropriate_abx_rate:.1f}% exceeds threshold of {inappropriate_threshold}%",
                        priority_score=priority,
                        priority_reason=f"Rate {svc.inappropriate_abx_rate:.1f}% - threshold {inappropriate_threshold}% = +{svc.inappropriate_abx_rate - inappropriate_threshold:.1f}pp",
                        baseline_value=svc.inappropriate_abx_rate,
                        target_value=inappropriate_threshold,
                        metric_name="inappropriate_abx_rate",
                        metric_unit="percent",
                        identified_date=today,
                    )
                    target = self.metrics_store.get_intervention_target(target_id)
                    if target:
                        targets.append(target)

        # Check overall therapy change rate
        patterns = self.get_alert_resolution_patterns(days=30)
        if patterns.therapy_change_rate is not None and patterns.therapy_change_rate < therapy_change_threshold:
            existing = self.metrics_store.list_intervention_targets(
                issue_type=IssueType.LOW_THERAPY_CHANGE_RATE,
                status=[TargetStatus.IDENTIFIED, TargetStatus.PLANNED, TargetStatus.IN_PROGRESS],
            )
            if not existing:
                priority = (therapy_change_threshold - patterns.therapy_change_rate)
                target_id = self.metrics_store.create_intervention_target(
                    target_type=TargetType.DEPARTMENT,
                    target_id="asp_program",
                    target_name="ASP Program Overall",
                    issue_type=IssueType.LOW_THERAPY_CHANGE_RATE,
                    issue_description=f"Therapy change rate of {patterns.therapy_change_rate:.1f}% is below target of {therapy_change_threshold}%",
                    priority_score=priority,
                    priority_reason=f"Target {therapy_change_threshold}% - actual {patterns.therapy_change_rate:.1f}% = -{therapy_change_threshold - patterns.therapy_change_rate:.1f}pp",
                    baseline_value=patterns.therapy_change_rate,
                    target_value=therapy_change_threshold,
                    metric_name="therapy_change_rate",
                    metric_unit="percent",
                    identified_date=today,
                )
                target = self.metrics_store.get_intervention_target(target_id)
                if target:
                    targets.append(target)

        # Sort by priority score
        targets.sort(key=lambda t: t.priority_score or 0, reverse=True)
        return targets

    def get_unified_metrics(self, days: int = 30) -> dict[str, Any]:
        """Get unified metrics across all modules for dashboard display.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with cross-module metrics
        """
        metrics = {
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
        }

        # Activity summary
        activity_summary = self.metrics_store.get_activity_summary(days=days)
        metrics["activity"] = activity_summary

        # Intervention summary
        intervention_summary = self.metrics_store.get_intervention_summary(days=days)
        metrics["interventions"] = intervention_summary

        # Provider workload
        workload = self.metrics_store.get_provider_workload(days=days)
        metrics["provider_workload"] = workload[:10]  # Top 10

        # Location scores
        location_scores = self.calculate_location_scores(days=days)
        metrics["location_scores"] = [
            {
                "location_code": s.location_code,
                "total_score": s.total_score,
                "inappropriate_abx_rate": s.inappropriate_abx_rate,
                "issues": s.issues,
            }
            for s in location_scores[:10]  # Top 10 needing attention
        ]

        # Resolution patterns
        patterns = self.get_alert_resolution_patterns(days=days)
        metrics["resolution_patterns"] = {
            "total_resolved": patterns.total_resolved,
            "breakdown": patterns.resolution_breakdown,
            "therapy_change_rate": patterns.therapy_change_rate,
            "avg_time_to_resolve_minutes": patterns.avg_time_to_resolve_minutes,
        }

        # Active intervention targets
        active_targets = self.metrics_store.list_intervention_targets(
            status=[TargetStatus.IDENTIFIED, TargetStatus.PLANNED, TargetStatus.IN_PROGRESS],
            limit=20,
        )
        metrics["active_targets"] = [t.to_dict() for t in active_targets]

        return metrics

    def get_trending_comparison(
        self,
        metric_name: str,
        period1_start: date,
        period1_end: date,
        period2_start: date,
        period2_end: date,
    ) -> dict[str, Any]:
        """Compare metrics between two time periods.

        Args:
            metric_name: Name of metric to compare
            period1_start: Start of first period (baseline)
            period1_end: End of first period
            period2_start: Start of second period (comparison)
            period2_end: End of second period

        Returns:
            Dictionary with comparison data
        """
        # Get snapshots for both periods
        period1_snapshots = self.metrics_store.list_daily_snapshots(
            start_date=period1_start,
            end_date=period1_end,
        )
        period2_snapshots = self.metrics_store.list_daily_snapshots(
            start_date=period2_start,
            end_date=period2_end,
        )

        def avg_metric(snapshots: list[DailySnapshot], attr: str) -> float | None:
            values = [getattr(s, attr) for s in snapshots if getattr(s, attr) is not None]
            if values:
                return sum(values) / len(values)
            return None

        period1_value = avg_metric(period1_snapshots, metric_name)
        period2_value = avg_metric(period2_snapshots, metric_name)

        absolute_change = None
        percent_change = None
        if period1_value is not None and period2_value is not None:
            absolute_change = period2_value - period1_value
            if period1_value != 0:
                percent_change = (period2_value - period1_value) / period1_value * 100

        return {
            "metric_name": metric_name,
            "period1": {
                "start": period1_start.isoformat(),
                "end": period1_end.isoformat(),
                "value": period1_value,
                "data_points": len(period1_snapshots),
            },
            "period2": {
                "start": period2_start.isoformat(),
                "end": period2_end.isoformat(),
                "value": period2_value,
                "data_points": len(period2_snapshots),
            },
            "absolute_change": absolute_change,
            "percent_change": percent_change,
        }
