"""Routes for Surgical Prophylaxis module.

This module provides monitoring and validation of surgical antibiotic
prophylaxis following ASHP/IDSA/SHEA/SIS guidelines.
"""

import sys
from pathlib import Path
from flask import Blueprint, render_template, current_app, request
from datetime import datetime, timedelta

# Add paths for surgical prophylaxis imports
SURGICAL_PATH = Path(__file__).parent.parent.parent / "surgical-prophylaxis"
if str(SURGICAL_PATH) not in sys.path:
    sys.path.insert(0, str(SURGICAL_PATH))

try:
    from src.database import ProphylaxisDatabase
    from src.config import get_config
except ImportError:
    ProphylaxisDatabase = None
    get_config = None


surgical_prophylaxis_bp = Blueprint(
    "surgical_prophylaxis", __name__, url_prefix="/surgical-prophylaxis"
)


def get_db():
    """Get database instance."""
    if ProphylaxisDatabase is None:
        return None
    return ProphylaxisDatabase()


@surgical_prophylaxis_bp.route("/")
def dashboard():
    """Render the Surgical Prophylaxis dashboard with real data."""
    db = get_db()

    metrics = {
        "total_cases": 0,
        "compliant_cases": 0,
        "bundle_rate": 0,
        "avg_score": 0,
        "excluded_cases": 0,
        "pending_alerts": 0,
    }
    recent_cases = []
    element_rates = {}
    active_alerts = []
    category_stats = []

    if db:
        try:
            # Get compliance summary for last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            summary = db.get_compliance_summary(start_date, end_date)

            metrics = {
                "total_cases": summary.get("total_cases", 0),
                "compliant_cases": summary.get("compliant_cases", 0),
                "bundle_rate": round(summary.get("bundle_compliance_rate", 0), 1),
                "avg_score": round(summary.get("avg_compliance_score", 0), 1),
                "excluded_cases": summary.get("excluded_cases", 0),
                "evaluated_cases": summary.get("evaluated_cases", 0),
            }
            element_rates = summary.get("element_rates", {})

            # Get recent non-compliant cases
            non_compliant = db.get_non_compliant_cases(start_date, end_date, limit=10)
            for case in non_compliant:
                recent_cases.append({
                    "case_id": case.get("case_id"),
                    "patient_mrn": case.get("patient_mrn"),
                    "procedure": case.get("procedure_description", "")[:40],
                    "category": case.get("procedure_category", ""),
                    "score": round(case.get("compliance_score", 0), 0),
                    "scheduled_time": case.get("scheduled_or_time"),
                    "indication_status": case.get("indication_status"),
                    "agent_status": case.get("agent_status"),
                    "timing_status": case.get("timing_status"),
                    "dosing_status": case.get("dosing_status"),
                })

            # Get pending alerts
            alerts = db.get_pending_alerts()
            metrics["pending_alerts"] = len(alerts)
            for alert in alerts[:10]:
                active_alerts.append({
                    "alert_id": alert.get("alert_id"),
                    "case_id": alert.get("case_id"),
                    "patient_mrn": alert.get("patient_mrn"),
                    "procedure": alert.get("procedure_description", "")[:30],
                    "alert_type": alert.get("alert_type"),
                    "severity": alert.get("alert_severity"),
                    "message": alert.get("alert_message", "")[:60],
                    "alert_time": alert.get("alert_time"),
                })

            # Get stats by procedure category
            categories = ["cardiac", "orthopedic", "gastrointestinal_colorectal", "neurosurgery", "ent", "hepatobiliary"]
            for cat in categories:
                cat_summary = db.get_compliance_summary(start_date, end_date, procedure_category=cat)
                if cat_summary.get("total_cases", 0) > 0:
                    category_stats.append({
                        "category": cat.replace("_", " ").title(),
                        "total_cases": cat_summary.get("total_cases", 0),
                        "compliance_rate": round(cat_summary.get("bundle_compliance_rate", 0), 1),
                    })

        except Exception as e:
            current_app.logger.error(f"Error loading surgical prophylaxis data: {e}")
            import traceback
            traceback.print_exc()

    return render_template(
        "surgical_prophylaxis_dashboard.html",
        metrics=metrics,
        element_rates=element_rates,
        recent_cases=recent_cases,
        active_alerts=active_alerts,
        category_stats=category_stats,
    )


@surgical_prophylaxis_bp.route("/cases")
def case_list():
    """Show list of all evaluated cases."""
    db = get_db()

    days = request.args.get("days", 30, type=int)
    category = request.args.get("category")
    status = request.args.get("status")  # compliant, non_compliant, excluded

    cases = []
    if db:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            if status == "non_compliant":
                raw_cases = db.get_non_compliant_cases(start_date, end_date, limit=100)
            else:
                raw_cases = db.get_cases_by_date_range(start_date, end_date)
                # Get evaluations for each case
                enriched = []
                for case in raw_cases:
                    eval_data = db.get_latest_evaluation(case.case_id)
                    if eval_data:
                        case_dict = {
                            "case_id": case.case_id,
                            "patient_mrn": case.patient_mrn,
                            "procedure_description": case.procedure_description,
                            "procedure_category": case.procedure_category.value if case.procedure_category else None,
                            "scheduled_or_time": case.scheduled_or_time.isoformat() if case.scheduled_or_time else None,
                            "compliance_score": eval_data.get("compliance_score", 0),
                            "bundle_compliant": eval_data.get("bundle_compliant"),
                            "excluded": eval_data.get("excluded"),
                        }
                        enriched.append(case_dict)
                raw_cases = enriched

            for case in raw_cases:
                if isinstance(case, dict):
                    cases.append({
                        "case_id": case.get("case_id"),
                        "patient_mrn": case.get("patient_mrn"),
                        "procedure": case.get("procedure_description", "")[:50],
                        "category": case.get("procedure_category", ""),
                        "scheduled_time": case.get("scheduled_or_time"),
                        "score": round(case.get("compliance_score", 0), 0),
                        "compliant": case.get("bundle_compliant"),
                        "excluded": case.get("excluded"),
                    })

        except Exception as e:
            current_app.logger.error(f"Error loading cases: {e}")
            import traceback
            traceback.print_exc()

    return render_template(
        "surgical_prophylaxis_cases.html",
        cases=cases,
        current_days=days,
        current_category=category,
        current_status=status,
    )


@surgical_prophylaxis_bp.route("/case/<case_id>")
def case_detail(case_id):
    """Show detailed evaluation for a specific case."""
    db = get_db()

    case = None
    evaluation = None

    if db:
        try:
            case_obj = db.get_case(case_id)
            if case_obj:
                case = {
                    "case_id": case_obj.case_id,
                    "patient_mrn": case_obj.patient_mrn,
                    "encounter_id": case_obj.encounter_id,
                    "procedure_description": case_obj.procedure_description,
                    "procedure_category": case_obj.procedure_category.value if case_obj.procedure_category else None,
                    "cpt_codes": case_obj.cpt_codes,
                    "surgeon_name": case_obj.surgeon_name,
                    "location": case_obj.location,
                    "scheduled_or_time": case_obj.scheduled_or_time.isoformat() if case_obj.scheduled_or_time else None,
                    "actual_incision_time": case_obj.actual_incision_time.isoformat() if case_obj.actual_incision_time else None,
                    "surgery_end_time": case_obj.surgery_end_time.isoformat() if case_obj.surgery_end_time else None,
                    "patient_weight_kg": case_obj.patient_weight_kg,
                    "patient_age_years": case_obj.patient_age_years,
                    "is_emergency": case_obj.is_emergency,
                    "has_beta_lactam_allergy": case_obj.has_beta_lactam_allergy,
                    "mrsa_colonized": case_obj.mrsa_colonized,
                }

            eval_data = db.get_latest_evaluation(case_id)
            if eval_data:
                evaluation = {
                    "evaluation_time": eval_data.get("evaluation_time"),
                    "bundle_compliant": eval_data.get("bundle_compliant"),
                    "compliance_score": eval_data.get("compliance_score"),
                    "elements_met": eval_data.get("elements_met"),
                    "elements_total": eval_data.get("elements_total"),
                    "excluded": eval_data.get("excluded"),
                    "exclusion_reason": eval_data.get("exclusion_reason"),
                    "elements": [
                        {"name": "Indication", "status": eval_data.get("indication_status"), "details": eval_data.get("indication_details")},
                        {"name": "Agent Selection", "status": eval_data.get("agent_status"), "details": eval_data.get("agent_details")},
                        {"name": "Pre-op Timing", "status": eval_data.get("timing_status"), "details": eval_data.get("timing_details")},
                        {"name": "Dosing", "status": eval_data.get("dosing_status"), "details": eval_data.get("dosing_details")},
                        {"name": "Redosing", "status": eval_data.get("redosing_status"), "details": eval_data.get("redosing_details")},
                        {"name": "Discontinuation", "status": eval_data.get("discontinuation_status"), "details": eval_data.get("discontinuation_details")},
                    ],
                }

        except Exception as e:
            current_app.logger.error(f"Error loading case {case_id}: {e}")
            import traceback
            traceback.print_exc()

    if not case:
        return render_template("surgical_prophylaxis_case_not_found.html", case_id=case_id), 404

    return render_template(
        "surgical_prophylaxis_case_detail.html",
        case=case,
        evaluation=evaluation,
    )


@surgical_prophylaxis_bp.route("/alerts")
def alert_list():
    """Show pending alerts for review."""
    db = get_db()
    alerts = []

    if db:
        try:
            raw_alerts = db.get_pending_alerts()
            for alert in raw_alerts:
                alerts.append({
                    "alert_id": alert.get("alert_id"),
                    "case_id": alert.get("case_id"),
                    "patient_mrn": alert.get("patient_mrn"),
                    "procedure": alert.get("procedure_description", "")[:40],
                    "alert_type": alert.get("alert_type"),
                    "severity": alert.get("alert_severity"),
                    "message": alert.get("alert_message"),
                    "element_name": alert.get("element_name"),
                    "alert_time": alert.get("alert_time"),
                })
        except Exception as e:
            current_app.logger.error(f"Error loading alerts: {e}")
            import traceback
            traceback.print_exc()

    return render_template(
        "surgical_prophylaxis_alerts.html",
        alerts=alerts,
    )


@surgical_prophylaxis_bp.route("/help")
def help_page():
    """Render the help page for Surgical Prophylaxis."""
    return render_template("surgical_prophylaxis_help.html")
