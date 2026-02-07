"""Routes for ASP/IP Action Analytics dashboard.

Provides a unified view of all ASP and Infection Prevention actions
across the AEGIS platform, aggregating data from the existing
provider_activity, provider_sessions, and metrics_daily_snapshot tables.
"""

import csv
import io
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from flask import Blueprint, render_template, request, Response

from dashboard.utils.api_response import api_success, api_error

logger = logging.getLogger(__name__)

# Add common to path
_common_path = Path(__file__).parent.parent.parent / "common"
if str(_common_path.parent) not in sys.path:
    sys.path.insert(0, str(_common_path.parent))

from common.metrics_store import MetricsStore, ActionAnalyzer


def _get_analyzer():
    """Get ActionAnalyzer instance."""
    return ActionAnalyzer()


action_analytics_bp = Blueprint(
    "action_analytics", __name__, url_prefix="/action-analytics"
)


# =============================================================================
# Phase 1: Core Dashboard
# =============================================================================

@action_analytics_bp.route("/")
def dashboard():
    """Render the main Action Analytics dashboard."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)

        summary = analyzer.get_action_summary(days=days)
        module_breakdown = analyzer.get_module_breakdown(days=days)
        activity_types = analyzer.get_activity_type_breakdown(days=days)
        daily_trends = analyzer.get_daily_action_trends(days=days)
        recent_actions = analyzer.get_recent_actions(limit=20)

        return render_template(
            "action_analytics_dashboard.html",
            summary=summary,
            module_breakdown=module_breakdown,
            activity_types=activity_types,
            daily_trends=daily_trends,
            recent_actions=recent_actions,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error loading action analytics dashboard: {e}")
        return render_template(
            "action_analytics_dashboard.html",
            summary={},
            module_breakdown=[],
            activity_types=[],
            daily_trends=[],
            recent_actions=[],
            days=30,
            error=str(e),
        )


@action_analytics_bp.route("/api/summary")
def api_action_summary():
    """JSON endpoint for action summary data."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        summary = analyzer.get_action_summary(days=days)
        return api_success(data=summary)
    except Exception as e:
        logger.error(f"Error in action summary API: {e}")
        return api_error(str(e), 500)


# =============================================================================
# Phase 2: Recommendations
# =============================================================================

@action_analytics_bp.route("/recommendations")
def recommendations():
    """Render the recommendation type breakdown page."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)

        rec_data = analyzer.get_recommendation_breakdown(days=days)

        return render_template(
            "action_analytics_recommendations.html",
            rec_data=rec_data,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error loading recommendations: {e}")
        return render_template(
            "action_analytics_recommendations.html",
            rec_data={"by_type": [], "total": 0, "total_accepted": 0, "overall_acceptance_rate": 0},
            days=30,
            error=str(e),
        )


@action_analytics_bp.route("/api/recommendations")
def api_recommendations():
    """JSON endpoint for recommendation breakdown."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_recommendation_breakdown(days=days)
        return api_success(data=data)
    except Exception as e:
        return api_error(str(e), 500)


# =============================================================================
# Phase 2: Approvals
# =============================================================================

@action_analytics_bp.route("/approvals")
def approvals():
    """Render the approval workflow analytics page."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)

        approval_data = analyzer.get_approval_metrics(days=days)

        return render_template(
            "action_analytics_approvals.html",
            approval_data=approval_data,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error loading approvals analytics: {e}")
        return render_template(
            "action_analytics_approvals.html",
            approval_data={"available": False, "error": str(e)},
            days=30,
            error=str(e),
        )


@action_analytics_bp.route("/api/approvals")
def api_approvals():
    """JSON endpoint for approval metrics."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_approval_metrics(days=days)
        return api_success(data=data)
    except Exception as e:
        return api_error(str(e), 500)


# =============================================================================
# Phase 2: Therapy Changes
# =============================================================================

@action_analytics_bp.route("/therapy-changes")
def therapy_changes():
    """Render the therapy change tracking page."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)

        therapy_data = analyzer.get_therapy_change_metrics(days=days)

        return render_template(
            "action_analytics_therapy_changes.html",
            therapy_data=therapy_data,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error loading therapy changes: {e}")
        return render_template(
            "action_analytics_therapy_changes.html",
            therapy_data={"total_suggestions": 0, "total_changes": 0, "overall_change_rate": 0, "by_module": [], "by_unit": []},
            days=30,
            error=str(e),
        )


@action_analytics_bp.route("/api/therapy-changes")
def api_therapy_changes():
    """JSON endpoint for therapy change metrics."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_therapy_change_metrics(days=days)
        return api_success(data=data)
    except Exception as e:
        return api_error(str(e), 500)


# =============================================================================
# Phase 3: Unit Analysis
# =============================================================================

@action_analytics_bp.route("/by-unit")
def by_unit():
    """Render the unit-level analysis page."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)

        unit_metrics = analyzer.get_unit_metrics(days=days)
        service_metrics = analyzer.get_service_metrics(days=days)

        return render_template(
            "action_analytics_by_unit.html",
            unit_metrics=unit_metrics,
            service_metrics=service_metrics,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error loading unit analysis: {e}")
        return render_template(
            "action_analytics_by_unit.html",
            unit_metrics=[],
            service_metrics=[],
            days=30,
            error=str(e),
        )


@action_analytics_bp.route("/api/by-unit")
def api_by_unit():
    """JSON endpoint for unit metrics."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = {
            "units": analyzer.get_unit_metrics(days=days),
            "services": analyzer.get_service_metrics(days=days),
        }
        return api_success(data=data)
    except Exception as e:
        return api_error(str(e), 500)


# =============================================================================
# Phase 3: Time Analysis
# =============================================================================

@action_analytics_bp.route("/time-spent")
def time_spent():
    """Render the time/workload analysis page."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)

        time_data = analyzer.get_time_analysis(days=days)
        provider_workload = analyzer.get_provider_workload(days=days)

        return render_template(
            "action_analytics_time_spent.html",
            time_data=time_data,
            provider_workload=provider_workload,
            days=days,
        )
    except Exception as e:
        logger.error(f"Error loading time analysis: {e}")
        return render_template(
            "action_analytics_time_spent.html",
            time_data={"by_module": [], "by_activity_type": [], "total_hours": 0, "session_stats": {}},
            provider_workload=[],
            days=30,
            error=str(e),
        )


@action_analytics_bp.route("/api/time-spent")
def api_time_spent():
    """JSON endpoint for time analysis."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_time_analysis(days=days)
        return api_success(data=data)
    except Exception as e:
        return api_error(str(e), 500)


# =============================================================================
# CSV Export Endpoints
# =============================================================================

def _make_csv_response(rows: list[dict], filename: str) -> Response:
    """Create a CSV download response from a list of dicts."""
    if not rows:
        return Response("No data", mimetype="text/plain")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@action_analytics_bp.route("/export/actions.csv")
def export_actions_csv():
    """Export recent actions to CSV."""
    try:
        analyzer = _get_analyzer()
        actions = analyzer.get_recent_actions(limit=500)
        # Remove nested details dict for CSV
        for a in actions:
            a.pop("details", None)
        return _make_csv_response(actions, "action_analytics_actions.csv")
    except Exception as e:
        logger.error(f"Error exporting actions: {e}")
        return api_error(str(e), 500)


@action_analytics_bp.route("/export/by-unit.csv")
def export_unit_csv():
    """Export unit metrics to CSV."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_unit_metrics(days=days)
        return _make_csv_response(data, "action_analytics_by_unit.csv")
    except Exception as e:
        logger.error(f"Error exporting unit metrics: {e}")
        return api_error(str(e), 500)


@action_analytics_bp.route("/export/time-spent.csv")
def export_time_csv():
    """Export time analysis to CSV."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_time_analysis(days=days)
        return _make_csv_response(data.get("by_module", []), "action_analytics_time.csv")
    except Exception as e:
        logger.error(f"Error exporting time data: {e}")
        return api_error(str(e), 500)


@action_analytics_bp.route("/export/therapy-changes.csv")
def export_therapy_csv():
    """Export therapy change metrics to CSV."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_therapy_change_metrics(days=days)
        return _make_csv_response(data.get("by_module", []), "action_analytics_therapy_changes.csv")
    except Exception as e:
        logger.error(f"Error exporting therapy changes: {e}")
        return api_error(str(e), 500)


@action_analytics_bp.route("/export/recommendations.csv")
def export_recommendations_csv():
    """Export recommendation breakdown to CSV."""
    try:
        analyzer = _get_analyzer()
        days = request.args.get("days", 30, type=int)
        data = analyzer.get_recommendation_breakdown(days=days)
        return _make_csv_response(data.get("by_type", []), "action_analytics_recommendations.csv")
    except Exception as e:
        logger.error(f"Error exporting recommendations: {e}")
        return api_error(str(e), 500)
