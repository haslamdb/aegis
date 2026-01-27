"""Report generation for ASP/IP metrics.

Provides CSV export and formatted reports for leadership and operational use.
"""

import csv
import io
import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any

from .models import DailySnapshot, InterventionTarget, ProviderActivity
from .store import MetricsStore
from .aggregator import MetricsAggregator

logger = logging.getLogger(__name__)


class MetricsReporter:
    """Generates reports and exports from ASP/IP metrics data."""

    def __init__(
        self,
        metrics_store: MetricsStore | None = None,
        aggregator: MetricsAggregator | None = None,
    ):
        """Initialize reporter.

        Args:
            metrics_store: MetricsStore instance
            aggregator: MetricsAggregator instance
        """
        self.store = metrics_store or MetricsStore()
        self.aggregator = aggregator or MetricsAggregator(metrics_store=self.store)

    def generate_weekly_summary(self, week_end_date: date | None = None) -> dict[str, Any]:
        """Generate a weekly summary report for leadership.

        Args:
            week_end_date: End date for the week (defaults to last Sunday)

        Returns:
            Dict with weekly summary data
        """
        if week_end_date is None:
            # Find last Sunday
            today = date.today()
            days_since_sunday = today.weekday() + 1  # Monday=0, so Sunday was 1 day ago on Monday
            if days_since_sunday == 7:
                days_since_sunday = 0  # Today is Sunday
            week_end_date = today - timedelta(days=days_since_sunday)

        week_start_date = week_end_date - timedelta(days=6)

        # Get snapshots for this week
        snapshots = self.store.list_daily_snapshots(
            start_date=week_start_date,
            end_date=week_end_date,
        )

        # Get previous week for comparison
        prev_week_end = week_start_date - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)
        prev_snapshots = self.store.list_daily_snapshots(
            start_date=prev_week_start,
            end_date=prev_week_end,
        )

        def sum_metric(snaps: list[DailySnapshot], attr: str) -> int:
            return sum(getattr(s, attr) or 0 for s in snaps)

        def avg_metric(snaps: list[DailySnapshot], attr: str) -> float | None:
            values = [getattr(s, attr) for s in snaps if getattr(s, attr) is not None]
            return sum(values) / len(values) if values else None

        # Alert metrics
        alerts_created = sum_metric(snapshots, "alerts_created")
        alerts_resolved = sum_metric(snapshots, "alerts_resolved")
        prev_alerts_created = sum_metric(prev_snapshots, "alerts_created")
        prev_alerts_resolved = sum_metric(prev_snapshots, "alerts_resolved")

        # HAI metrics
        hai_candidates = sum_metric(snapshots, "hai_candidates_created")
        hai_confirmed = sum_metric(snapshots, "hai_confirmed")
        prev_hai_candidates = sum_metric(prev_snapshots, "hai_candidates_created")

        # Review metrics
        total_reviews = sum_metric(snapshots, "total_reviews")
        indication_reviews = sum_metric(snapshots, "indication_reviews")
        prev_total_reviews = sum_metric(prev_snapshots, "total_reviews")

        # Rates
        inappropriate_rate = avg_metric(snapshots, "inappropriate_rate")
        bundle_adherence = avg_metric(snapshots, "bundle_adherence_rate")

        # Provider workload for the week
        workload = self.store.get_provider_workload(days=7)

        # Active intervention targets
        from .models import TargetStatus
        active_targets = self.store.list_intervention_targets(
            status=[TargetStatus.IDENTIFIED, TargetStatus.PLANNED, TargetStatus.IN_PROGRESS]
        )

        def calc_change(current: int | float | None, previous: int | float | None) -> float | None:
            if current is None or previous is None or previous == 0:
                return None
            return round((current - previous) / previous * 100, 1)

        return {
            "report_title": "Weekly ASP/IP Summary",
            "generated_at": datetime.now().isoformat(),
            "period": {
                "start": week_start_date.isoformat(),
                "end": week_end_date.isoformat(),
                "days": 7,
            },
            "alerts": {
                "created": alerts_created,
                "resolved": alerts_resolved,
                "created_change_pct": calc_change(alerts_created, prev_alerts_created),
                "resolved_change_pct": calc_change(alerts_resolved, prev_alerts_resolved),
            },
            "hai": {
                "candidates_identified": hai_candidates,
                "confirmed": hai_confirmed,
                "change_pct": calc_change(hai_candidates, prev_hai_candidates),
            },
            "reviews": {
                "total": total_reviews,
                "indication_reviews": indication_reviews,
                "change_pct": calc_change(total_reviews, prev_total_reviews),
            },
            "rates": {
                "inappropriate_abx_pct": round(inappropriate_rate, 1) if inappropriate_rate else None,
                "bundle_adherence_pct": round(bundle_adherence, 1) if bundle_adherence else None,
            },
            "workload": {
                "total_providers": len(workload),
                "top_reviewers": workload[:5],
            },
            "intervention_targets": {
                "total_active": len(active_targets),
                "high_priority": len([t for t in active_targets if t.priority_score and t.priority_score > 10]),
            },
            "data_quality": {
                "days_with_data": len(snapshots),
                "data_completeness_pct": round(len(snapshots) / 7 * 100, 0),
            },
        }

    def generate_location_scorecard(
        self,
        location_code: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Generate a scorecard for a specific location/unit.

        Args:
            location_code: The location code to report on
            days: Number of days to include

        Returns:
            Dict with location-specific metrics
        """
        start_date = date.today() - timedelta(days=days)
        end_date = date.today()

        # Get activities for this location
        activities = self.store.list_activities(
            location_code=location_code,
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        # Aggregate by type
        activity_by_type = {}
        for a in activities:
            atype = a.activity_type if isinstance(a.activity_type, str) else a.activity_type.value
            activity_by_type[atype] = activity_by_type.get(atype, 0) + 1

        # Get intervention targets for this location
        from .models import TargetType
        targets = self.store.list_intervention_targets(
            target_type=TargetType.UNIT,
        )
        location_targets = [t for t in targets if t.target_id == location_code]

        # Get intervention sessions
        sessions = self.store.list_intervention_sessions(
            target_type=TargetType.UNIT,
            target_id=location_code,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "report_title": f"Location Scorecard: {location_code}",
            "generated_at": datetime.now().isoformat(),
            "location_code": location_code,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days,
            },
            "activity": {
                "total": len(activities),
                "by_type": activity_by_type,
                "unique_providers": len(set(a.provider_id for a in activities if a.provider_id)),
            },
            "intervention_targets": [t.to_dict() for t in location_targets],
            "intervention_sessions": [s.to_dict() for s in sessions],
        }

    def generate_provider_activity_report(
        self,
        provider_id: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Generate an activity report for providers.

        Args:
            provider_id: Optional specific provider (None for all)
            days: Number of days to include

        Returns:
            Dict with provider activity data
        """
        workload = self.store.get_provider_workload(
            days=days,
            provider_id=provider_id,
        )

        activity_summary = self.store.get_activity_summary(days=days)

        return {
            "report_title": "Provider Activity Report",
            "generated_at": datetime.now().isoformat(),
            "period_days": days,
            "providers": workload,
            "summary": {
                "total_activities": activity_summary.get("total_activities", 0),
                "unique_providers": activity_summary.get("unique_providers", 0),
                "by_module": activity_summary.get("by_module", {}),
            },
        }

    def export_activities_to_csv(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        module: str | None = None,
    ) -> str:
        """Export activities to CSV format.

        Args:
            start_date: Start date filter
            end_date: End date filter
            module: Optional module filter

        Returns:
            CSV string
        """
        from .models import ModuleSource

        module_filter = None
        if module:
            module_filter = module

        activities = self.store.list_activities(
            module=module_filter,
            start_date=start_date,
            end_date=end_date,
            limit=100000,
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "id",
            "performed_at",
            "provider_id",
            "provider_name",
            "provider_role",
            "activity_type",
            "module",
            "entity_id",
            "entity_type",
            "action_taken",
            "outcome",
            "patient_mrn",
            "location_code",
            "service",
            "duration_minutes",
        ])

        # Data rows
        for a in activities:
            writer.writerow([
                a.id,
                a.performed_at.isoformat() if a.performed_at else "",
                a.provider_id or "",
                a.provider_name or "",
                a.provider_role or "",
                a.activity_type if isinstance(a.activity_type, str) else a.activity_type.value,
                a.module if isinstance(a.module, str) else a.module.value,
                a.entity_id or "",
                a.entity_type or "",
                a.action_taken or "",
                a.outcome or "",
                a.patient_mrn or "",
                a.location_code or "",
                a.service or "",
                a.duration_minutes or "",
            ])

        return output.getvalue()

    def export_snapshots_to_csv(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> str:
        """Export daily snapshots to CSV format.

        Args:
            start_date: Start date filter
            end_date: End date filter

        Returns:
            CSV string
        """
        snapshots = self.store.list_daily_snapshots(
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "snapshot_date",
            "alerts_created",
            "alerts_resolved",
            "alerts_acknowledged",
            "avg_time_to_ack_minutes",
            "avg_time_to_resolve_minutes",
            "hai_candidates_created",
            "hai_candidates_reviewed",
            "hai_confirmed",
            "hai_override_count",
            "bundle_episodes_active",
            "bundle_alerts_created",
            "bundle_adherence_rate",
            "indication_reviews",
            "appropriate_count",
            "inappropriate_count",
            "inappropriate_rate",
            "total_reviews",
            "unique_reviewers",
            "total_interventions",
        ])

        # Data rows
        for s in snapshots:
            writer.writerow([
                s.snapshot_date.isoformat() if s.snapshot_date else "",
                s.alerts_created,
                s.alerts_resolved,
                s.alerts_acknowledged,
                s.avg_time_to_ack_minutes or "",
                s.avg_time_to_resolve_minutes or "",
                s.hai_candidates_created,
                s.hai_candidates_reviewed,
                s.hai_confirmed,
                s.hai_override_count,
                s.bundle_episodes_active,
                s.bundle_alerts_created,
                s.bundle_adherence_rate or "",
                s.indication_reviews,
                s.appropriate_count,
                s.inappropriate_count,
                s.inappropriate_rate or "",
                s.total_reviews,
                s.unique_reviewers,
                s.total_interventions,
            ])

        return output.getvalue()

    def export_targets_to_csv(self) -> str:
        """Export intervention targets to CSV format.

        Returns:
            CSV string
        """
        targets = self.store.list_intervention_targets(limit=10000)

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "id",
            "target_type",
            "target_id",
            "target_name",
            "issue_type",
            "issue_description",
            "priority_score",
            "baseline_value",
            "target_value",
            "current_value",
            "metric_name",
            "metric_unit",
            "status",
            "assigned_to",
            "identified_date",
            "planned_date",
            "started_date",
            "completed_date",
        ])

        # Data rows
        for t in targets:
            writer.writerow([
                t.id,
                t.target_type if isinstance(t.target_type, str) else t.target_type.value,
                t.target_id or "",
                t.target_name or "",
                t.issue_type if isinstance(t.issue_type, str) else t.issue_type.value,
                t.issue_description or "",
                t.priority_score or "",
                t.baseline_value or "",
                t.target_value or "",
                t.current_value or "",
                t.metric_name or "",
                t.metric_unit or "",
                t.status if isinstance(t.status, str) else t.status.value,
                t.assigned_to or "",
                t.identified_date.isoformat() if t.identified_date else "",
                t.planned_date.isoformat() if t.planned_date else "",
                t.started_date.isoformat() if t.started_date else "",
                t.completed_date.isoformat() if t.completed_date else "",
            ])

        return output.getvalue()

    def export_sessions_to_csv(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> str:
        """Export intervention sessions to CSV format.

        Args:
            start_date: Start date filter
            end_date: End date filter

        Returns:
            CSV string
        """
        sessions = self.store.list_intervention_sessions(
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "id",
            "session_type",
            "session_date",
            "target_type",
            "target_id",
            "target_name",
            "topic",
            "attendees_count",
            "conducted_by",
            "notes",
        ])

        # Data rows
        for s in sessions:
            writer.writerow([
                s.id,
                s.session_type if isinstance(s.session_type, str) else s.session_type.value,
                s.session_date.isoformat() if s.session_date else "",
                s.target_type if isinstance(s.target_type, str) else s.target_type.value,
                s.target_id or "",
                s.target_name or "",
                s.topic or "",
                len(s.attendees) if s.attendees else 0,
                s.conducted_by or "",
                s.notes[:100] if s.notes else "",
            ])

        return output.getvalue()
