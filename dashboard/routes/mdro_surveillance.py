"""MDRO Surveillance routes for the dashboard."""

import sys
from pathlib import Path

# Add mdro-surveillance to path
_mdro_path = Path(__file__).parent.parent.parent / "mdro-surveillance"
if str(_mdro_path) not in sys.path:
    sys.path.insert(0, str(_mdro_path))

from flask import Blueprint, render_template, request, jsonify, current_app

from mdro_src.db import MDRODatabase
from mdro_src.config import config as mdro_config
from mdro_src.classifier import MDROType
from mdro_src.models import TransmissionStatus
from dashboard.services.user import get_user_from_request
from dashboard.utils.api_response import api_success, api_error

mdro_surveillance_bp = Blueprint("mdro_surveillance", __name__, url_prefix="/mdro-surveillance")


def get_mdro_db():
    """Get or create MDRO database instance."""
    if not hasattr(current_app, "mdro_db"):
        current_app.mdro_db = MDRODatabase(mdro_config.DB_PATH)
    return current_app.mdro_db


def _log_mdro_activity(
    activity_type: str,
    entity_id: str,
    entity_type: str,
    action_taken: str,
    provider_id: str | None = None,
    provider_name: str | None = None,
    patient_mrn: str | None = None,
    location_code: str | None = None,
    service: str | None = None,
    outcome: str | None = None,
    details: dict | None = None,
) -> None:
    """Log activity to the unified metrics store. Fire-and-forget."""
    try:
        from common.metrics_store import MetricsStore, ActivityType, ModuleSource
        store = MetricsStore()
        store.log_activity(
            activity_type=activity_type,
            module=ModuleSource.MDRO_SURVEILLANCE,
            provider_id=provider_id,
            provider_name=provider_name,
            entity_id=entity_id,
            entity_type=entity_type,
            action_taken=action_taken,
            outcome=outcome,
            patient_mrn=patient_mrn,
            location_code=location_code,
            service=service,
            details=details,
        )
    except Exception:
        pass


@mdro_surveillance_bp.route("/")
def dashboard():
    """MDRO surveillance dashboard overview."""
    try:
        db = get_mdro_db()

        # Get summary stats
        stats = db.get_summary_stats(days=30)

        # Get recent cases
        recent_cases = db.get_recent_cases(days=7)

        # Get trend data
        trend_data = db.get_trend_data(days=30)

        return render_template(
            "mdro_dashboard.html",
            stats=stats,
            recent_cases=recent_cases,
            trend_data=trend_data,
            mdro_types=[t.value for t in MDROType],
        )
    except Exception as e:
        current_app.logger.error(f"Error loading MDRO dashboard: {e}")
        return render_template(
            "mdro_dashboard.html",
            stats={
                "total_cases": 0,
                "by_type": {},
                "by_unit": {},
                "healthcare_onset": 0,
                "community_onset": 0,
            },
            recent_cases=[],
            trend_data=[],
            mdro_types=[t.value for t in MDROType],
            error=str(e),
        )


@mdro_surveillance_bp.route("/cases")
def cases_list():
    """List all MDRO cases with filtering."""
    try:
        db = get_mdro_db()

        # Get filter parameters
        mdro_type_filter = request.args.get("type")
        unit_filter = request.args.get("unit")
        days = int(request.args.get("days", "30"))

        mdro_type = MDROType(mdro_type_filter) if mdro_type_filter else None

        cases = db.get_recent_cases(
            days=days,
            mdro_type=mdro_type,
            unit=unit_filter,
        )

        stats = db.get_summary_stats(days=days)

        # Get unique units for filter dropdown
        units = set(c.unit for c in cases if c.unit)

        return render_template(
            "mdro_cases.html",
            cases=cases,
            stats=stats,
            units=sorted(units),
            mdro_types=[t.value for t in MDROType],
            current_type=mdro_type_filter,
            current_unit=unit_filter,
            current_days=days,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading MDRO cases: {e}")
        return render_template(
            "mdro_cases.html",
            cases=[],
            stats={},
            units=[],
            mdro_types=[t.value for t in MDROType],
            error=str(e),
        )


@mdro_surveillance_bp.route("/cases/<case_id>")
def case_detail(case_id: str):
    """Show MDRO case details."""
    try:
        db = get_mdro_db()

        case = db.get_case(case_id)
        if not case:
            return render_template(
                "mdro_case_not_found.html",
                case_id=case_id,
            ), 404

        # Get patient's prior cases
        prior_cases = db.get_patient_prior_cases(case.patient_id)
        prior_cases = [c for c in prior_cases if c.id != case.id]

        _log_mdro_activity(
            activity_type="view",
            entity_id=case_id,
            entity_type="mdro_case",
            action_taken="viewed_case",
        )

        return render_template(
            "mdro_case_detail.html",
            case=case,
            prior_cases=prior_cases,
            transmission_statuses=[s.value for s in TransmissionStatus],
        )
    except Exception as e:
        current_app.logger.error(f"Error loading MDRO case: {e}")
        return render_template(
            "mdro_case_detail.html",
            case=None,
            error=str(e),
        )


@mdro_surveillance_bp.route("/cases/<case_id>/review", methods=["POST"])
def review_case(case_id: str):
    """Submit a review for an MDRO case."""
    try:
        db = get_mdro_db()
        user = get_user_from_request()

        case = db.get_case(case_id)
        if not case:
            return api_error("Case not found", 404)

        decision = request.form.get("decision")
        notes = request.form.get("notes")
        reviewer = request.form.get("reviewer") or user.get("name", "Unknown")

        review_id = db.save_review(
            case_id=case_id,
            reviewer=reviewer,
            decision=decision,
            notes=notes,
        )

        _log_mdro_activity(
            activity_type="review",
            entity_id=case_id,
            entity_type="mdro_case",
            action_taken=decision,
            provider_name=reviewer,
            outcome=decision,
            details={"notes": notes[:200] if notes else None, "review_id": review_id},
        )

        return api_success(data={"review_id": review_id})
    except Exception as e:
        current_app.logger.error(f"Error saving review: {e}")
        return api_error(str(e), 500)


@mdro_surveillance_bp.route("/analytics")
def analytics():
    """MDRO analytics and reporting."""
    try:
        db = get_mdro_db()

        days = int(request.args.get("days", "30"))

        stats = db.get_summary_stats(days=days)
        trend_data = db.get_trend_data(days=days)

        return render_template(
            "mdro_analytics.html",
            stats=stats,
            trend_data=trend_data,
            current_days=days,
            mdro_types=[t.value for t in MDROType],
        )
    except Exception as e:
        current_app.logger.error(f"Error loading analytics: {e}")
        return render_template(
            "mdro_analytics.html",
            stats={},
            trend_data=[],
            error=str(e),
        )


# API endpoints

@mdro_surveillance_bp.route("/api/stats")
def api_stats():
    """Get current stats as JSON."""
    try:
        db = get_mdro_db()
        days = int(request.args.get("days", "30"))
        stats = db.get_summary_stats(days=days)
        return api_success(data=stats)
    except Exception as e:
        return api_error(str(e), 500)


@mdro_surveillance_bp.route("/api/export")
def api_export():
    """Export cases for outbreak detection module."""
    try:
        db = get_mdro_db()
        days = int(request.args.get("days", "14"))
        cases = db.get_cases_for_export(days=days)
        return api_success(data=cases)
    except Exception as e:
        return api_error(str(e), 500)


@mdro_surveillance_bp.route("/help")
def help_page():
    """MDRO surveillance help and demo guide."""
    return render_template("mdro_help.html")
