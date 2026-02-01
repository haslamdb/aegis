"""Outbreak Detection routes for the dashboard."""

import sys
from pathlib import Path

# Add outbreak-detection to path
_outbreak_path = Path(__file__).parent.parent.parent / "outbreak-detection"
if str(_outbreak_path) not in sys.path:
    sys.path.insert(0, str(_outbreak_path))

from flask import Blueprint, render_template, request, jsonify, current_app

from outbreak_src.db import OutbreakDatabase
from outbreak_src.config import config as outbreak_config
from outbreak_src.models import ClusterStatus, ClusterSeverity
from outbreak_src.detector import OutbreakDetector
from dashboard.services.user import get_user_from_request

outbreak_detection_bp = Blueprint("outbreak_detection", __name__, url_prefix="/outbreak-detection")


def get_outbreak_db():
    """Get or create Outbreak database instance."""
    if not hasattr(current_app, "outbreak_db"):
        current_app.outbreak_db = OutbreakDatabase(outbreak_config.DB_PATH)
    return current_app.outbreak_db


@outbreak_detection_bp.route("/")
def dashboard():
    """Outbreak detection dashboard overview."""
    try:
        db = get_outbreak_db()

        # Get summary stats
        stats = db.get_summary_stats()

        # Get active clusters
        active_clusters = db.get_active_clusters()

        # Get pending alerts
        pending_alerts = db.get_pending_alerts()

        return render_template(
            "outbreak_dashboard.html",
            stats=stats,
            active_clusters=active_clusters,
            pending_alerts=pending_alerts,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading outbreak dashboard: {e}")
        return render_template(
            "outbreak_dashboard.html",
            stats={
                "active_clusters": 0,
                "investigating_clusters": 0,
                "resolved_clusters": 0,
                "pending_alerts": 0,
                "by_type": {},
                "by_severity": {},
            },
            active_clusters=[],
            pending_alerts=[],
            error=str(e),
        )


@outbreak_detection_bp.route("/clusters")
def clusters_list():
    """List all outbreak clusters."""
    try:
        db = get_outbreak_db()

        # Get filter parameters
        status_filter = request.args.get("status", "active")

        try:
            status = ClusterStatus(status_filter)
        except ValueError:
            status = ClusterStatus.ACTIVE

        clusters = db.get_all_clusters(status=status)

        return render_template(
            "outbreak_clusters.html",
            clusters=clusters,
            current_status=status_filter,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading clusters: {e}")
        return render_template(
            "outbreak_clusters.html",
            clusters=[],
            error=str(e),
        )


@outbreak_detection_bp.route("/clusters/<cluster_id>")
def cluster_detail(cluster_id: str):
    """Show cluster details."""
    try:
        db = get_outbreak_db()

        cluster = db.get_cluster(cluster_id)
        if not cluster:
            return render_template(
                "outbreak_cluster_not_found.html",
                cluster_id=cluster_id,
            ), 404

        return render_template(
            "outbreak_cluster_detail.html",
            cluster=cluster,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading cluster: {e}")
        return render_template(
            "outbreak_cluster_detail.html",
            cluster=None,
            error=str(e),
        )


@outbreak_detection_bp.route("/clusters/<cluster_id>/resolve", methods=["POST"])
def resolve_cluster(cluster_id: str):
    """Resolve an outbreak cluster."""
    try:
        db = get_outbreak_db()
        user = get_user_from_request()

        cluster = db.get_cluster(cluster_id)
        if not cluster:
            return jsonify({"error": "Cluster not found"}), 404

        resolution_notes = request.form.get("notes")
        resolved_by = request.form.get("reviewer") or user.get("name", "Unknown")

        detector = OutbreakDetector(db)
        success = detector.resolve_cluster(
            cluster_id=cluster_id,
            resolved_by=resolved_by,
            notes=resolution_notes,
        )

        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to resolve cluster"}), 500
    except Exception as e:
        current_app.logger.error(f"Error resolving cluster: {e}")
        return jsonify({"error": str(e)}), 500


@outbreak_detection_bp.route("/alerts")
def alerts_list():
    """List all alerts."""
    try:
        db = get_outbreak_db()

        # Get pending alerts
        pending = db.get_pending_alerts()

        # Get recent acknowledged alerts
        with db._get_connection() as conn:
            acknowledged_rows = conn.execute(
                """
                SELECT * FROM outbreak_alerts
                WHERE acknowledged = 1
                ORDER BY acknowledged_at DESC
                LIMIT 50
                """
            ).fetchall()
            acknowledged = [dict(row) for row in acknowledged_rows]

        return render_template(
            "outbreak_alerts.html",
            pending_alerts=pending,
            acknowledged_alerts=acknowledged,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading alerts: {e}")
        return render_template(
            "outbreak_alerts.html",
            pending_alerts=[],
            acknowledged_alerts=[],
            error=str(e),
        )


@outbreak_detection_bp.route("/alerts/<alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    try:
        db = get_outbreak_db()
        user = get_user_from_request()

        acknowledged_by = request.form.get("reviewer") or user.get("name", "Unknown")
        db.acknowledge_alert(alert_id, acknowledged_by)

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error acknowledging alert: {e}")
        return jsonify({"error": str(e)}), 500


@outbreak_detection_bp.route("/run", methods=["POST"])
def run_detection():
    """Manually trigger outbreak detection."""
    try:
        db = get_outbreak_db()
        detector = OutbreakDetector(db)

        days = int(request.form.get("days", "14"))
        result = detector.run_detection(days=days)

        return jsonify({
            "success": True,
            "result": result,
        })
    except Exception as e:
        current_app.logger.error(f"Error running detection: {e}")
        return jsonify({"error": str(e)}), 500


# API endpoints

@outbreak_detection_bp.route("/api/stats")
def api_stats():
    """Get current stats as JSON."""
    try:
        db = get_outbreak_db()
        stats = db.get_summary_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@outbreak_detection_bp.route("/api/active-clusters")
def api_active_clusters():
    """Get active clusters as JSON."""
    try:
        db = get_outbreak_db()
        clusters = db.get_active_clusters()
        return jsonify([c.to_dict() for c in clusters])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@outbreak_detection_bp.route("/help")
def help_page():
    """Outbreak detection help and demo guide."""
    return render_template("outbreak_help.html")
