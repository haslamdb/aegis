"""Routes for unified ASP/IP Metrics dashboard.

This module provides a unified view of metrics across all ASP and IP
monitoring modules, including workload tracking, intervention targeting,
and trending analysis.
"""

import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Blueprint, current_app, render_template, request, jsonify, Response

from dashboard.utils.api_response import api_success, api_error

logger = logging.getLogger(__name__)

# Add common to path for metrics_store package
_common_path = Path(__file__).parent.parent.parent / "common"
if str(_common_path.parent) not in sys.path:
    sys.path.insert(0, str(_common_path.parent))

from common.metrics_store import (
    MetricsStore,
    MetricsAggregator,
    MetricsReporter,
    InterventionType,
    TargetType,
    TargetStatus,
)


def _get_metrics_store():
    """Get MetricsStore instance."""
    return MetricsStore()


def _get_aggregator():
    """Get MetricsAggregator instance."""
    return MetricsAggregator()


def _get_reporter():
    """Get MetricsReporter instance."""
    return MetricsReporter()


asp_metrics_bp = Blueprint(
    "asp_metrics", __name__, url_prefix="/asp-metrics"
)


# =============================================================================
# Main Dashboard
# =============================================================================

@asp_metrics_bp.route("/")
def dashboard():
    """Render the main unified ASP/IP metrics dashboard."""
    try:
        aggregator = _get_aggregator()
        days = int(request.args.get("days", 30))

        # Get unified metrics
        metrics = aggregator.get_unified_metrics(days=days)

        # Get location and service scores
        location_scores = aggregator.calculate_location_scores(days=days)
        service_scores = aggregator.calculate_service_scores(days=days)

        # Get resolution patterns
        patterns = aggregator.get_alert_resolution_patterns(days=days)

        return render_template(
            "asp_metrics_dashboard.html",
            metrics=metrics,
            location_scores=location_scores[:10],
            service_scores=service_scores[:10],
            resolution_patterns=patterns,
            days=days,
        )

    except Exception as e:
        logger.error(f"Error loading ASP metrics dashboard: {e}")
        return render_template(
            "asp_metrics_dashboard.html",
            metrics={},
            location_scores=[],
            service_scores=[],
            resolution_patterns={},
            days=30,
            error=str(e),
        )


# =============================================================================
# Workload Dashboard
# =============================================================================

@asp_metrics_bp.route("/workload")
def workload():
    """Render the provider workload dashboard."""
    try:
        store = _get_metrics_store()
        days = int(request.args.get("days", 30))

        # Get workload by provider
        provider_workload = store.get_provider_workload(days=days)

        # Get activity by location
        activity_by_location = store.get_activity_by_location(days=days)

        # Get activity summary
        activity_summary = store.get_activity_summary(days=days)

        return render_template(
            "asp_metrics_workload.html",
            provider_workload=provider_workload,
            activity_by_location=activity_by_location,
            activity_summary=activity_summary,
            days=days,
        )

    except Exception as e:
        logger.error(f"Error loading workload dashboard: {e}")
        return render_template(
            "asp_metrics_workload.html",
            provider_workload=[],
            activity_by_location=[],
            activity_summary={},
            days=30,
            error=str(e),
        )


# =============================================================================
# Intervention Targets Dashboard
# =============================================================================

@asp_metrics_bp.route("/targets")
def targets():
    """Render the intervention targets dashboard."""
    try:
        store = _get_metrics_store()
        aggregator = _get_aggregator()

        # Get filter from query params
        status_filter = request.args.get("status")
        if status_filter:
            status_list = [TargetStatus(status_filter)]
        else:
            status_list = [
                TargetStatus.IDENTIFIED,
                TargetStatus.PLANNED,
                TargetStatus.IN_PROGRESS,
            ]

        # Get existing targets
        targets = store.list_intervention_targets(status=status_list, limit=50)

        # Get intervention summary
        intervention_summary = store.get_intervention_summary(days=90)

        return render_template(
            "asp_metrics_targets.html",
            targets=targets,
            intervention_summary=intervention_summary,
            status_filter=status_filter,
        )

    except Exception as e:
        logger.error(f"Error loading targets dashboard: {e}")
        return render_template(
            "asp_metrics_targets.html",
            targets=[],
            intervention_summary={},
            status_filter=None,
            error=str(e),
        )


@asp_metrics_bp.route("/targets/<int:target_id>")
def target_detail(target_id: int):
    """Render detail view for a single intervention target."""
    try:
        store = _get_metrics_store()
        target = store.get_intervention_target(target_id)

        if not target:
            return render_template(
                "asp_metrics_target_not_found.html",
                target_id=target_id,
            ), 404

        # Get related sessions
        sessions = store.list_intervention_sessions(
            target_type=target.target_type,
            target_id=target.target_id,
            limit=20,
        )

        # Get outcomes
        outcomes = store.list_intervention_outcomes(target_id=target_id)

        return render_template(
            "asp_metrics_target_detail.html",
            target=target,
            sessions=sessions,
            outcomes=outcomes,
        )

    except Exception as e:
        logger.error(f"Error loading target {target_id}: {e}")
        return render_template(
            "asp_metrics_target_not_found.html",
            target_id=target_id,
            error=str(e),
        ), 500


@asp_metrics_bp.route("/targets/<int:target_id>/update", methods=["POST"])
def update_target(target_id: int):
    """Update an intervention target's status."""
    try:
        store = _get_metrics_store()
        data = request.get_json() or {}

        status = data.get("status")
        assigned_to = data.get("assigned_to")
        current_value = data.get("current_value")

        # Parse dates if provided
        planned_date = None
        if data.get("planned_date"):
            planned_date = date.fromisoformat(data["planned_date"])

        started_date = None
        if data.get("started_date"):
            started_date = date.fromisoformat(data["started_date"])

        completed_date = None
        if data.get("completed_date"):
            completed_date = date.fromisoformat(data["completed_date"])

        success = store.update_intervention_target(
            target_id=target_id,
            status=status,
            assigned_to=assigned_to,
            current_value=float(current_value) if current_value else None,
            planned_date=planned_date,
            started_date=started_date,
            completed_date=completed_date,
        )

        if success:
            return api_success(message="Target updated")
        else:
            return api_error("Target not found", 404)

    except Exception as e:
        logger.error(f"Error updating target {target_id}: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/targets/identify", methods=["POST"])
def identify_targets():
    """Run intervention target identification."""
    try:
        aggregator = _get_aggregator()
        data = request.get_json() or {}

        # Get thresholds from request or use defaults
        thresholds = {
            "inappropriate_threshold": float(data.get("inappropriate_threshold", 15.0)),
            "adherence_threshold": float(data.get("adherence_threshold", 80.0)),
            "response_time_threshold_hours": float(data.get("response_time_threshold_hours", 4.0)),
            "therapy_change_threshold": float(data.get("therapy_change_threshold", 20.0)),
        }

        new_targets = aggregator.identify_intervention_targets(**thresholds)

        return api_success(data={
            "new_targets": len(new_targets),
            "targets": [t.to_dict() for t in new_targets],
        })

    except Exception as e:
        logger.error(f"Error identifying targets: {e}")
        return api_error(str(e), 500)


# =============================================================================
# Trends Dashboard
# =============================================================================

@asp_metrics_bp.route("/trends")
def trends():
    """Render the trending analysis dashboard."""
    try:
        store = _get_metrics_store()

        # Get recent daily snapshots
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        snapshots = store.list_daily_snapshots(
            start_date=start_date,
            end_date=end_date,
        )

        # Prepare data for charts
        snapshot_data = [s.to_dict() for s in snapshots]

        return render_template(
            "asp_metrics_trends.html",
            snapshots=snapshot_data,
            start_date=start_date,
            end_date=end_date,
        )

    except Exception as e:
        logger.error(f"Error loading trends dashboard: {e}")
        return render_template(
            "asp_metrics_trends.html",
            snapshots=[],
            start_date=date.today() - timedelta(days=90),
            end_date=date.today(),
            error=str(e),
        )


@asp_metrics_bp.route("/trends/compare", methods=["POST"])
def compare_periods():
    """Compare metrics between two time periods."""
    try:
        aggregator = _get_aggregator()
        data = request.get_json()

        metric_name = data.get("metric_name", "alerts_created")
        period1_start = date.fromisoformat(data["period1_start"])
        period1_end = date.fromisoformat(data["period1_end"])
        period2_start = date.fromisoformat(data["period2_start"])
        period2_end = date.fromisoformat(data["period2_end"])

        comparison = aggregator.get_trending_comparison(
            metric_name=metric_name,
            period1_start=period1_start,
            period1_end=period1_end,
            period2_start=period2_start,
            period2_end=period2_end,
        )

        return api_success(data={"comparison": comparison})

    except Exception as e:
        logger.error(f"Error comparing periods: {e}")
        return api_error(str(e), 500)


# =============================================================================
# Interventions Dashboard
# =============================================================================

@asp_metrics_bp.route("/interventions")
def interventions():
    """Render the intervention sessions dashboard."""
    try:
        store = _get_metrics_store()

        # Get filter params
        session_type = request.args.get("session_type")

        # Get recent sessions
        sessions = store.list_intervention_sessions(
            session_type=session_type,
            limit=50,
        )

        # Get intervention summary
        intervention_summary = store.get_intervention_summary(days=90)

        return render_template(
            "asp_metrics_interventions.html",
            sessions=sessions,
            intervention_summary=intervention_summary,
            session_type_filter=session_type,
            intervention_types=[(t.value, t.name.replace("_", " ").title()) for t in InterventionType],
            target_types=[(t.value, t.name.replace("_", " ").title()) for t in TargetType],
        )

    except Exception as e:
        logger.error(f"Error loading interventions dashboard: {e}")
        return render_template(
            "asp_metrics_interventions.html",
            sessions=[],
            intervention_summary={},
            session_type_filter=None,
            intervention_types=[],
            target_types=[],
            error=str(e),
        )


@asp_metrics_bp.route("/interventions/log", methods=["POST"])
def log_intervention():
    """Log a new intervention session."""
    try:
        store = _get_metrics_store()
        data = request.get_json()

        session_type = data.get("session_type")
        session_date_str = data.get("session_date")
        target_type = data.get("target_type")
        target_id = data.get("target_id")
        target_name = data.get("target_name")
        topic = data.get("topic")
        attendees = data.get("attendees", [])
        notes = data.get("notes")
        conducted_by = data.get("conducted_by")
        related_alerts = data.get("related_alerts", [])
        related_targets = data.get("related_targets", [])

        if not session_type:
            return api_error("Session type required", 400)

        if not session_date_str:
            return api_error("Session date required", 400)

        session_date = date.fromisoformat(session_date_str)

        session_id = store.create_intervention_session(
            session_type=session_type,
            session_date=session_date,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            topic=topic,
            attendees=attendees,
            notes=notes,
            related_alerts=related_alerts,
            related_targets=[int(t) for t in related_targets] if related_targets else None,
            conducted_by=conducted_by,
        )

        return api_success(data={"session_id": session_id}, message="Intervention session logged")

    except Exception as e:
        logger.error(f"Error logging intervention: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/interventions/<int:session_id>")
def intervention_detail(session_id: int):
    """View detail for a single intervention session."""
    try:
        store = _get_metrics_store()
        session = store.get_intervention_session(session_id)

        if not session:
            return render_template(
                "asp_metrics_intervention_not_found.html",
                session_id=session_id,
            ), 404

        # Get related outcomes
        outcomes = store.list_intervention_outcomes(session_id=session_id)

        return render_template(
            "asp_metrics_intervention_detail.html",
            session=session,
            outcomes=outcomes,
        )

    except Exception as e:
        logger.error(f"Error loading intervention {session_id}: {e}")
        return render_template(
            "asp_metrics_intervention_not_found.html",
            session_id=session_id,
            error=str(e),
        ), 500


# =============================================================================
# LLM Performance Dashboard
# =============================================================================

@asp_metrics_bp.route("/llm-performance")
def llm_performance():
    """Cross-module LLM extraction performance dashboard."""
    days = request.args.get("days", 30, type=int)
    module_filter = request.args.get("module")
    try:
        from common.llm_tracking import LLMDecisionTracker
        tracker = LLMDecisionTracker()

        # Overall accuracy stats
        overall_stats = tracker.get_accuracy_stats(module=module_filter, days=days)

        # Module comparison
        module_comparison = tracker.get_module_comparison(days=days)

        # Confidence calibration
        calibration = tracker.get_confidence_calibration(module=module_filter, days=days)

        # Recent overrides
        overrides = tracker.list_decisions(
            module=module_filter,
            outcome="overridden",
            limit=20,
        )

        return render_template(
            "asp_metrics_llm_performance.html",
            stats=overall_stats,
            module_comparison=module_comparison,
            calibration=calibration,
            recent_overrides=overrides,
            current_days=days,
            current_module=module_filter,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading LLM performance: {e}")
        return render_template(
            "asp_metrics_llm_performance.html",
            stats={"total_reviewed": 0, "acceptance_rate": None, "override_rate": None, "override_reasons": {}},
            module_comparison=[],
            calibration=[],
            recent_overrides=[],
            current_days=days,
            current_module=module_filter,
            error=str(e),
        )


# =============================================================================
# API Endpoints
# =============================================================================

@asp_metrics_bp.route("/api/unified-metrics")
def api_unified_metrics():
    """API endpoint for unified metrics."""
    try:
        aggregator = _get_aggregator()
        days = int(request.args.get("days", 30))
        metrics = aggregator.get_unified_metrics(days=days)
        return api_success(data=metrics)
    except Exception as e:
        logger.error(f"Error in unified metrics API: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/api/provider-workload")
def api_provider_workload():
    """API endpoint for provider workload data."""
    try:
        store = _get_metrics_store()
        days = int(request.args.get("days", 30))
        provider_id = request.args.get("provider_id")

        workload = store.get_provider_workload(days=days, provider_id=provider_id)
        return api_success(data=workload)
    except Exception as e:
        logger.error(f"Error in provider workload API: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/api/intervention-targets")
def api_intervention_targets():
    """API endpoint for intervention targets."""
    try:
        store = _get_metrics_store()
        status = request.args.get("status")

        if status:
            targets = store.list_intervention_targets(status=TargetStatus(status))
        else:
            targets = store.list_intervention_targets(
                status=[TargetStatus.IDENTIFIED, TargetStatus.PLANNED, TargetStatus.IN_PROGRESS]
            )

        return api_success(data=[t.to_dict() for t in targets])
    except Exception as e:
        logger.error(f"Error in intervention targets API: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/api/activity-summary")
def api_activity_summary():
    """API endpoint for activity summary."""
    try:
        store = _get_metrics_store()
        days = int(request.args.get("days", 30))
        summary = store.get_activity_summary(days=days)
        return api_success(data=summary)
    except Exception as e:
        logger.error(f"Error in activity summary API: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/api/llm-stats")
def api_llm_stats():
    """Get LLM accuracy stats as JSON."""
    try:
        from common.llm_tracking import LLMDecisionTracker
        tracker = LLMDecisionTracker()
        days = int(request.args.get("days", "30"))
        module = request.args.get("module")

        stats = tracker.get_accuracy_stats(module=module, days=days)
        return api_success(data=stats)
    except Exception as e:
        return api_error(str(e), 500)


@asp_metrics_bp.route("/api/snapshots")
def api_snapshots():
    """API endpoint for daily snapshots."""
    try:
        store = _get_metrics_store()
        days = int(request.args.get("days", 30))

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        snapshots = store.list_daily_snapshots(
            start_date=start_date,
            end_date=end_date,
        )
        return api_success(data=[s.to_dict() for s in snapshots])
    except Exception as e:
        logger.error(f"Error in snapshots API: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/api/create-snapshot", methods=["POST"])
def api_create_snapshot():
    """API endpoint to manually create a daily snapshot."""
    try:
        aggregator = _get_aggregator()
        data = request.get_json() or {}

        snapshot_date_str = data.get("date")
        if snapshot_date_str:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        else:
            snapshot_date = date.today() - timedelta(days=1)

        snapshot = aggregator.create_daily_snapshot(snapshot_date)
        return api_success(data={"snapshot": snapshot.to_dict()})
    except Exception as e:
        logger.error(f"Error creating snapshot: {e}")
        return api_error(str(e), 500)


# =============================================================================
# Export and Report Endpoints
# =============================================================================

@asp_metrics_bp.route("/api/weekly-summary")
def api_weekly_summary():
    """API endpoint for weekly summary report."""
    try:
        reporter = _get_reporter()
        week_end_str = request.args.get("week_end")
        week_end = date.fromisoformat(week_end_str) if week_end_str else None
        summary = reporter.generate_weekly_summary(week_end_date=week_end)
        return api_success(data=summary)
    except Exception as e:
        logger.error(f"Error generating weekly summary: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/export/activities.csv")
def export_activities_csv():
    """Export activities to CSV."""
    try:
        reporter = _get_reporter()

        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        module = request.args.get("module")

        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None

        csv_data = reporter.export_activities_to_csv(
            start_date=start_date,
            end_date=end_date,
            module=module,
        )

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=activities.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting activities: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/export/snapshots.csv")
def export_snapshots_csv():
    """Export daily snapshots to CSV."""
    try:
        reporter = _get_reporter()

        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")

        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None

        csv_data = reporter.export_snapshots_to_csv(
            start_date=start_date,
            end_date=end_date,
        )

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=daily_snapshots.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting snapshots: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/export/targets.csv")
def export_targets_csv():
    """Export intervention targets to CSV."""
    try:
        reporter = _get_reporter()
        csv_data = reporter.export_targets_to_csv()

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=intervention_targets.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting targets: {e}")
        return api_error(str(e), 500)


@asp_metrics_bp.route("/export/sessions.csv")
def export_sessions_csv():
    """Export intervention sessions to CSV."""
    try:
        reporter = _get_reporter()

        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")

        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None

        csv_data = reporter.export_sessions_to_csv(
            start_date=start_date,
            end_date=end_date,
        )

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=intervention_sessions.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting sessions: {e}")
        return api_error(str(e), 500)
