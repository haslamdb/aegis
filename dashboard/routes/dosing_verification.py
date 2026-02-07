"""Dosing Verification routes for the dashboard.

Handles antimicrobial dosing verification alerts and ASP review workflow.
"""

import json
import logging
from datetime import datetime
from io import StringIO
import csv

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app, Response

from common.dosing_verification import DoseAlertStore
from common.dosing_verification.models import (
    DoseAlertSeverity, DoseAlertStatus, DoseFlagType, DoseResolution
)

from common.metrics_store import MetricsStore
from common.metrics_store.models import ActivityType, ModuleSource
from common.alert_store.models import AlertType
from common.alert_store import AlertStore
from dashboard.services.user import get_user_from_request
from dashboard.utils.api_response import api_success, api_error

logger = logging.getLogger(__name__)

dosing_verification_bp = Blueprint(
    "dosing_verification", __name__, url_prefix="/dosing-verification"
)




def _get_dose_alert_store():
    """Get the dose alert store, initializing if needed."""
    if not hasattr(current_app, "dose_alert_store"):
        current_app.dose_alert_store = DoseAlertStore(
            db_path=current_app.config.get("DOSE_ALERT_DB_PATH")
        )
    return current_app.dose_alert_store


def _get_metrics_store():
    """Get the metrics store."""
    if not hasattr(current_app, "metrics_store"):
        current_app.metrics_store = MetricsStore(
            db_path=current_app.config.get("METRICS_DB_PATH")
        )
    return current_app.metrics_store


def _log_activity(activity_type, alert_id, action_taken, outcome=None, patient_mrn=None):
    """Log activity to MetricsStore."""
    try:
        user = get_user_from_request(default="unknown")
        metrics = _get_metrics_store()
        metrics.log_activity(
            provider_id=user,
            activity_type=activity_type,
            module=ModuleSource.DOSING_VERIFICATION,
            entity_id=alert_id,
            entity_type="dose_alert",
            action_taken=action_taken,
            outcome=outcome,
            patient_mrn=patient_mrn,
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")


# Page Routes

@dosing_verification_bp.route("/")
def index():
    """Redirect to active alerts dashboard."""
    return redirect(url_for("dosing_verification.active"))


@dosing_verification_bp.route("/active")
def active():
    """Active dose alerts list with filters."""
    try:
        store = _get_dose_alert_store()

        # Get filter parameters
        severity = request.args.get("severity", "")
        flag_type = request.args.get("flag_type", "")
        drug = request.args.get("drug", "")

        # Build filter kwargs
        filter_kwargs = {}
        if severity:
            filter_kwargs["severity"] = severity
        if flag_type:
            filter_kwargs["flag_type"] = flag_type
        if drug:
            filter_kwargs["drug"] = drug

        # Get alerts and stats
        alerts = store.list_active(**filter_kwargs)
        stats = store.get_stats()

        # Get unique drugs for filter dropdown
        all_alerts = store.list_active()
        unique_drugs = sorted(set(alert.drug for alert in all_alerts if alert.drug))
        drug_options = [(d, d) for d in unique_drugs]

        return render_template(
            "dosing_dashboard.html",
            alerts=alerts,
            stats=stats,
            current_severity=severity,
            current_flag_type=flag_type,
            current_drug=drug,
            severity_options=DoseAlertSeverity.all_options(),
            flag_type_options=DoseFlagType.all_options(),
            drug_options=drug_options,
        )

    except Exception as e:
        logger.error(f"Error loading active alerts: {e}")
        return render_template(
            "dosing_dashboard.html",
            alerts=[],
            stats={},
            current_severity="",
            current_flag_type="",
            current_drug="",
            severity_options=DoseAlertSeverity.all_options(),
            flag_type_options=DoseFlagType.all_options(),
            drug_options=[],
            error=str(e),
        )


@dosing_verification_bp.route("/alert/<alert_id>")
def alert_detail(alert_id):
    """Alert detail page with full clinical context and ASP review workflow."""
    try:
        store = _get_dose_alert_store()

        alert = store.get_alert(alert_id)
        if not alert:
            return render_template(
                "dosing_alert_not_found.html",
                alert_id=alert_id,
            ), 404

        # Get audit log
        audit_log = store.get_audit_log(alert_id)

        # Parse JSON fields
        patient_factors = {}
        assessment = {}
        if hasattr(alert, 'patient_factors') and alert.patient_factors:
            try:
                patient_factors = json.loads(alert.patient_factors)
            except (json.JSONDecodeError, TypeError):
                pass

        if hasattr(alert, 'assessment_details') and alert.assessment_details:
            try:
                assessment = json.loads(alert.assessment_details)
            except (json.JSONDecodeError, TypeError):
                pass

        # Log view activity
        _log_activity(
            activity_type=ActivityType.REVIEW,
            alert_id=alert_id,
            action_taken="viewed",
            patient_mrn=getattr(alert, 'patient_mrn', None),
        )

        return render_template(
            "dosing_alert_detail.html",
            alert=alert,
            patient_factors=patient_factors,
            assessment=assessment,
            audit_log=audit_log,
            resolution_options=DoseResolution.all_options(),
        )

    except Exception as e:
        logger.error(f"Error loading alert {alert_id}: {e}", exc_info=True)
        # Return simple error message
        return f"<h1>Error</h1><p>Could not load alert {alert_id}: {str(e)}</p>", 500


@dosing_verification_bp.route("/history")
def history():
    """Resolved alerts with filters."""
    try:
        store = _get_dose_alert_store()

        # Get filter parameters
        days = int(request.args.get("days", "30"))
        resolution = request.args.get("resolution", "")
        severity = request.args.get("severity", "")
        drug = request.args.get("drug", "")

        # Build filter kwargs
        filter_kwargs = {"days_back": days}
        if resolution:
            filter_kwargs["resolution"] = resolution
        if severity:
            filter_kwargs["severity"] = severity
        if drug:
            filter_kwargs["drug"] = drug

        # Get resolved alerts
        alerts = store.list_resolved(**filter_kwargs)

        # Get stats
        stats = store.get_stats()

        # Get unique drugs for filter dropdown
        all_resolved = store.list_resolved(days_back=days)
        unique_drugs = sorted(set(alert.drug for alert in all_resolved if alert.drug))
        drug_options = [(d, d) for d in unique_drugs]

        return render_template(
            "dosing_history.html",
            alerts=alerts,
            stats=stats,
            days_back=days,
            current_days=days,
            current_resolution=resolution,
            current_severity=severity,
            current_drug=drug,
            resolution_options=DoseResolution.all_options(),
            severity_options=DoseAlertSeverity.all_options(),
            drug_options=drug_options,
        )

    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return render_template(
            "dosing_history.html",
            alerts=[],
            stats={},
            days_back=30,
            current_days=30,
            current_resolution="",
            current_severity="",
            current_drug="",
            resolution_options=DoseResolution.all_options(),
            severity_options=DoseAlertSeverity.all_options(),
            drug_options=[],
            error=str(e),
        )


@dosing_verification_bp.route("/reports")
def reports():
    """Analytics dashboard for dosing verification."""
    try:
        store = _get_dose_alert_store()

        days = int(request.args.get("days", "30"))
        analytics = store.get_analytics(days=days)

        return render_template(
            "dosing_reports.html",
            analytics=analytics,
            days=days,
            current_days=days,
        )

    except Exception as e:
        logger.error(f"Error loading reports: {e}")
        return render_template(
            "dosing_reports.html",
            analytics={},
            error=str(e),
        )


@dosing_verification_bp.route("/help")
def help_page():
    """Help documentation page."""
    return render_template("dosing_help.html")


# API Endpoints

@dosing_verification_bp.route("/api/stats")
def api_stats():
    """Get alert statistics as JSON."""
    try:
        store = _get_dose_alert_store()
        stats = store.get_stats()
        return api_success(data=stats)
    except Exception as e:
        logger.error(f"API stats error: {e}")
        return api_error(str(e), 500)


@dosing_verification_bp.route("/api/alerts")
def api_alerts():
    """Get active alerts as JSON."""
    try:
        store = _get_dose_alert_store()

        # Get filter parameters
        severity = request.args.get("severity")
        flag_type = request.args.get("flag_type")

        filter_kwargs = {}
        if severity:
            filter_kwargs["severity"] = severity
        if flag_type:
            filter_kwargs["flag_type"] = flag_type

        alerts = store.list_active(**filter_kwargs)

        # Convert to JSON-serializable format
        alert_dicts = []
        for alert in alerts:
            if hasattr(alert, 'to_dict'):
                alert_dicts.append(alert.to_dict())
            else:
                # Fallback for placeholder
                alert_dicts.append({})

        return api_success(data=alert_dicts)

    except Exception as e:
        logger.error(f"API alerts error: {e}")
        return api_error(str(e), 500)


@dosing_verification_bp.route("/api/<alert_id>/acknowledge", methods=["POST"])
def api_acknowledge(alert_id):
    """Acknowledge an alert."""
    try:
        store = _get_dose_alert_store()
        user = get_user_from_request(default="unknown")

        success = store.acknowledge(alert_id, by=user)

        if success:
            _log_activity(
                activity_type=ActivityType.ACKNOWLEDGMENT,
                alert_id=alert_id,
                action_taken="acknowledged",
            )

        # Check if this is a form submission or API call
        wants_redirect = request.content_type and "form" in request.content_type

        if wants_redirect:
            if success:
                return redirect(url_for("dosing_verification.alert_detail", alert_id=alert_id) + "?msg=acknowledged")
            return redirect(url_for("dosing_verification.alert_detail", alert_id=alert_id) + "?msg=acknowledge_failed")

        # API response
        if success:
            return api_success(data={"alert_id": alert_id, "status": "acknowledged"})
        else:
            return api_error("Failed to acknowledge alert", 400)

    except Exception as e:
        logger.error(f"API acknowledge error: {e}")
        return api_error(str(e), 500)


@dosing_verification_bp.route("/api/<alert_id>/resolve", methods=["POST"])
def api_resolve(alert_id):
    """Resolve an alert with a resolution reason."""
    try:
        store = _get_dose_alert_store()

        # Handle form data or JSON (harmonized pattern)
        if request.content_type and "form" in request.content_type:
            data = request.form.to_dict()
            resolution = data.get("resolution")
            notes = data.get("resolution_notes", "")
        else:
            data = request.json or {}
            resolution = data.get("resolution")
            notes = data.get("notes", "")

        user = get_user_from_request(default="unknown")

        if not resolution:
            return api_error("resolution is required", 400)

        success = store.resolve(
            alert_id=alert_id,
            by=user,
            resolution=resolution,
            notes=notes,
        )

        if success:
            _log_activity(
                activity_type=ActivityType.RESOLUTION,
                alert_id=alert_id,
                action_taken="resolved",
                outcome=resolution,
            )

        # Check if this is a form submission or API call
        wants_redirect = request.content_type and "form" in request.content_type

        if wants_redirect:
            if success:
                return redirect(url_for("dosing_verification.alert_detail", alert_id=alert_id) + "?msg=resolved")
            return redirect(url_for("dosing_verification.alert_detail", alert_id=alert_id) + "?msg=resolve_failed")

        # API response
        if success:
            return api_success(data={
                "alert_id": alert_id,
                "status": "resolved",
                "resolution": resolution,
            })
        else:
            return api_error("Failed to resolve alert", 400)

    except Exception as e:
        logger.error(f"API resolve error: {e}")
        return api_error(str(e), 500)


@dosing_verification_bp.route("/api/<alert_id>/note", methods=["POST"])
def api_add_note(alert_id):
    """Add a note to an alert."""
    try:
        store = _get_dose_alert_store()

        # Handle form data or JSON (harmonized pattern)
        if request.content_type and "form" in request.content_type:
            note = request.form.get("note", "").strip()
        else:
            data = request.json or {}
            note = data.get("note", "").strip()

        user = get_user_from_request(default="unknown")

        if not note:
            return api_error("note is required", 400)

        success = store.add_note(
            alert_id=alert_id,
            by=user,
            note=note,
        )

        if success:
            _log_activity(
                activity_type=ActivityType.REVIEW,
                alert_id=alert_id,
                action_taken="note_added",
            )

        # Check if this is a form submission or API call
        wants_redirect = request.content_type and "form" in request.content_type

        if wants_redirect:
            if success:
                return redirect(url_for("dosing_verification.alert_detail", alert_id=alert_id) + "?msg=note_added")
            return redirect(url_for("dosing_verification.alert_detail", alert_id=alert_id) + "?msg=note_failed")

        # API response
        if success:
            return api_success(data={"alert_id": alert_id, "note_added": True})
        else:
            return api_error("Failed to add note", 400)

    except Exception as e:
        logger.error(f"API add note error: {e}")
        return api_error(str(e), 500)


# CSV Export Routes

@dosing_verification_bp.route("/export/active.csv")
def export_active_csv():
    """Export active alerts to CSV."""
    try:
        store = _get_dose_alert_store()
        alerts = store.list_active()

        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "Alert ID", "Patient MRN", "Patient Name", "Drug", "Flag Type",
            "Severity", "Expected Dose", "Actual Dose", "Created At", "Status"
        ])

        # Write data rows
        for alert in alerts:
            writer.writerow([
                getattr(alert, 'id', ''),
                getattr(alert, 'patient_mrn', ''),
                getattr(alert, 'patient_name', ''),
                getattr(alert, 'drug', ''),
                DoseFlagType.display_name(getattr(alert, 'flag_type', '')),
                getattr(alert, 'severity', '').title(),
                getattr(alert, 'expected_dose', ''),
                getattr(alert, 'actual_dose', ''),
                getattr(alert, 'created_at', ''),
                getattr(alert, 'status', '').title(),
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=dosing_active.csv"}
        )

    except Exception as e:
        logger.error(f"CSV export error: {e}")
        return api_error(str(e), 500)


@dosing_verification_bp.route("/export/history.csv")
def export_history_csv():
    """Export resolved alerts to CSV."""
    try:
        store = _get_dose_alert_store()
        days = int(request.args.get("days", "30"))
        alerts = store.list_resolved(days_back=days)

        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "Alert ID", "Patient MRN", "Patient Name", "Drug", "Flag Type",
            "Severity", "Expected Dose", "Actual Dose", "Created At",
            "Resolved At", "Resolved By", "Resolution", "Notes"
        ])

        # Write data rows
        for alert in alerts:
            writer.writerow([
                getattr(alert, 'id', ''),
                getattr(alert, 'patient_mrn', ''),
                getattr(alert, 'patient_name', ''),
                getattr(alert, 'drug', ''),
                DoseFlagType.display_name(getattr(alert, 'flag_type', '')),
                getattr(alert, 'severity', '').title(),
                getattr(alert, 'expected_dose', ''),
                getattr(alert, 'actual_dose', ''),
                getattr(alert, 'created_at', ''),
                getattr(alert, 'resolved_at', ''),
                getattr(alert, 'resolved_by', ''),
                DoseResolution.display_name(getattr(alert, 'resolution', '')),
                getattr(alert, 'resolution_notes', ''),
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=dosing_history.csv"}
        )

    except Exception as e:
        logger.error(f"CSV export error: {e}")
        return api_error(str(e), 500)
