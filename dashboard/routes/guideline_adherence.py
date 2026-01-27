"""Routes for Guideline Adherence module.

This module tracks adherence to evidence-based clinical guidelines/bundles
at the population level for quality improvement and JC reporting.
"""

import sys
from pathlib import Path
from flask import Blueprint, render_template, current_app, request

# Add paths for guideline adherence imports
GUIDELINE_PATH = Path(__file__).parent.parent.parent / "guideline-adherence"
if str(GUIDELINE_PATH) not in sys.path:
    sys.path.insert(0, str(GUIDELINE_PATH))

try:
    from guideline_adherence import GUIDELINE_BUNDLES
    from guideline_src.episode_db import EpisodeDB
    from guideline_src.config import Config as adherence_config
except ImportError:
    GUIDELINE_BUNDLES = {}
    EpisodeDB = None
    adherence_config = None


guideline_adherence_bp = Blueprint(
    "guideline_adherence", __name__, url_prefix="/guideline-adherence"
)


def get_episode_db():
    """Get episode database instance."""
    if EpisodeDB is None:
        return None
    return EpisodeDB()


@guideline_adherence_bp.route("/")
def dashboard():
    """Render the Guideline Adherence dashboard with real data."""
    db = get_episode_db()

    # Get metrics
    metrics = None
    active_episodes = []
    bundle_stats = []
    active_alerts = []

    if db:
        try:
            # Get active episodes (returns BundleEpisode objects)
            episodes = db.get_active_episodes(limit=10)
            for ep in episodes:
                active_episodes.append({
                    "id": ep.id,
                    "patient_id": ep.patient_id,
                    "patient_mrn": ep.patient_mrn or ep.patient_id,
                    "patient_name": ep.patient_id,  # Use patient_id as name for now
                    "bundle_id": ep.bundle_id,
                    "bundle_name": ep.bundle_name,
                    "status": ep.status,
                    "adherence_pct": ep.adherence_percentage or 0,
                    "trigger_time": ep.trigger_time.isoformat() if ep.trigger_time else None,
                })

            # Get active alerts
            alerts = db.get_active_alerts(limit=10)
            for alert in alerts:
                active_alerts.append({
                    "id": alert.id,
                    "patient_id": alert.patient_id,
                    "bundle_name": alert.bundle_name,
                    "element_name": alert.element_name,
                    "severity": alert.severity,
                    "message": alert.message,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                })

            # Get adherence stats by bundle (completed episodes)
            stats = db.get_adherence_stats(days=30)

            # Get per-bundle stats - include both completed and active episodes
            for bundle_id, bundle in GUIDELINE_BUNDLES.items():
                bundle_stat = stats.get(bundle_id, {})

                # Get active episodes for this bundle
                active_for_bundle = [ep for ep in episodes if ep.bundle_id == bundle_id]
                active_count = len(active_for_bundle)

                # Calculate compliance including active episodes
                completed_episodes = bundle_stat.get("total_episodes", 0)
                completed_avg = bundle_stat.get("avg_adherence_percentage", 0) or 0

                # Combine active + completed for overall compliance
                if active_for_bundle:
                    active_adherences = [ep.adherence_percentage or 0 for ep in active_for_bundle]
                    active_avg = sum(active_adherences) / len(active_adherences)

                    # Weighted average of completed and active
                    total_count = completed_episodes + active_count
                    if total_count > 0:
                        avg_compliance = (
                            (completed_avg * completed_episodes) + (active_avg * active_count)
                        ) / total_count
                    else:
                        avg_compliance = 0
                else:
                    avg_compliance = completed_avg

                bundle_stats.append({
                    "bundle_id": bundle_id,
                    "bundle_name": bundle.name,
                    "total_episodes": completed_episodes + active_count,
                    "active_episodes": active_count,
                    "avg_compliance": round(avg_compliance, 1),
                    "element_count": len(bundle.elements),
                })

            # Overall metrics - include active episodes in totals
            completed_total = sum(s.get("total_episodes", 0) for s in stats.values())
            total_alerts = len(alerts)
            metrics = {
                "total_episodes": completed_total + len(episodes),
                "active_episodes": len(episodes),
                "active_alerts": total_alerts,
            }
        except Exception as e:
            current_app.logger.error(f"Error loading adherence data: {e}")
            import traceback
            traceback.print_exc()

    return render_template(
        "guideline_adherence_dashboard.html",
        metrics=metrics,
        active_episodes=active_episodes,
        active_alerts=active_alerts,
        bundle_stats=bundle_stats,
        bundles=GUIDELINE_BUNDLES,
    )


@guideline_adherence_bp.route("/active")
def active_episodes():
    """Show patients with active bundles being monitored."""
    db = get_episode_db()
    bundle_filter = request.args.get("bundle")

    episodes = []
    if db:
        try:
            # Get active episodes
            raw_episodes = db.get_active_episodes(limit=100)

            # Filter by bundle if specified
            if bundle_filter:
                raw_episodes = [ep for ep in raw_episodes if ep.bundle_id == bundle_filter]

            # Enrich with latest results
            for ep in raw_episodes:
                results = db.get_element_results(ep.id)
                result_list = []
                for r in results:
                    result_list.append({
                        "element_name": r.element_name,
                        "status": r.status,
                        "value": r.value,
                        "checked_at": r.created_at.isoformat() if r.created_at else None,
                    })

                episodes.append({
                    "id": ep.id,
                    "patient_id": ep.patient_id,
                    "patient_mrn": ep.patient_mrn or ep.patient_id,
                    "patient_name": ep.patient_id,
                    "bundle_id": ep.bundle_id,
                    "bundle_name": ep.bundle_name,
                    "status": ep.status,
                    "adherence_pct": ep.adherence_percentage or 0,
                    "trigger_time": ep.trigger_time.isoformat() if ep.trigger_time else None,
                    "results": result_list,
                })

        except Exception as e:
            current_app.logger.error(f"Error loading active episodes: {e}")
            import traceback
            traceback.print_exc()

    return render_template(
        "guideline_adherence_active.html",
        episodes=episodes,
        bundles=GUIDELINE_BUNDLES,
        current_bundle=bundle_filter,
    )


@guideline_adherence_bp.route("/episode/<int:episode_id>")
def episode_detail(episode_id):
    """Show element timeline for a specific episode."""
    db = get_episode_db()

    episode = None
    results = []
    bundle = None
    nlp_assessment = None

    if db:
        try:
            ep = db.get_episode(episode_id)
            if ep:
                episode = {
                    "id": ep.id,
                    "patient_id": ep.patient_id,
                    "bundle_id": ep.bundle_id,
                    "bundle_name": ep.bundle_name,
                    "status": ep.status,
                    "adherence_pct": ep.adherence_percentage or 0,
                    "trigger_time": ep.trigger_time.isoformat() if ep.trigger_time else None,
                    "trigger_type": ep.trigger_type,
                    "trigger_code": ep.trigger_code,
                    "trigger_description": ep.trigger_description,
                }

                # Parse clinical context for NLP assessment
                if ep.clinical_context:
                    import json
                    try:
                        nlp_assessment = json.loads(ep.clinical_context)
                    except json.JSONDecodeError:
                        nlp_assessment = None

                raw_results = db.get_element_results(episode_id)
                for r in raw_results:
                    results.append({
                        "element_name": r.element_name,
                        "status": r.status,
                        "value": r.value,
                        "deadline": r.deadline.isoformat() if r.deadline else None,
                        "checked_at": r.created_at.isoformat() if r.created_at else None,
                        "notes": r.notes,
                    })
                bundle = GUIDELINE_BUNDLES.get(ep.bundle_id)
        except Exception as e:
            current_app.logger.error(f"Error loading episode {episode_id}: {e}")
            import traceback
            traceback.print_exc()

    if not episode:
        return render_template("guideline_adherence_episode_not_found.html", episode_id=episode_id), 404

    return render_template(
        "guideline_adherence_episode.html",
        episode=episode,
        results=results,
        bundle=bundle,
        nlp_assessment=nlp_assessment,
    )


@guideline_adherence_bp.route("/metrics")
def compliance_metrics():
    """Show aggregate compliance rates and trends."""
    db = get_episode_db()
    bundle_filter = request.args.get("bundle")
    days = request.args.get("days", 30, type=int)

    metrics = None
    bundle_metrics = []

    if db:
        try:
            # Get adherence stats (completed/closed episodes)
            stats = db.get_adherence_stats(days=days)

            # Get active episodes to include in counts
            active_episodes = db.get_active_episodes(limit=1000)

            # Filter by bundle if specified
            if bundle_filter:
                active_episodes = [ep for ep in active_episodes if ep.bundle_id == bundle_filter]

            # Calculate overall metrics
            completed_total = sum(s.get("total_episodes", 0) for s in stats.values())
            active_total = len(active_episodes)

            # Get element-level compliance rates from element results
            element_rates = db.get_element_compliance_rates(days=days, bundle_id=bundle_filter)

            metrics = {
                "episode_counts": {
                    "total": completed_total + active_total,
                    "active": active_total,
                    "complete": completed_total,
                },
                "element_rates": element_rates,
            }

            # Per-bundle breakdown (only if no bundle filter)
            if not bundle_filter:
                for bundle_id, bundle in GUIDELINE_BUNDLES.items():
                    bundle_stat = stats.get(bundle_id, {})
                    active_for_bundle = [ep for ep in active_episodes if ep.bundle_id == bundle_id]
                    bundle_element_rates = db.get_element_compliance_rates(days=days, bundle_id=bundle_id)

                    bundle_metrics.append({
                        "bundle_id": bundle_id,
                        "bundle_name": bundle.name,
                        "metrics": {
                            "episode_counts": {
                                "total": bundle_stat.get("total_episodes", 0) + len(active_for_bundle),
                                "active": len(active_for_bundle),
                                "complete": bundle_stat.get("total_episodes", 0),
                            },
                            "element_rates": bundle_element_rates,
                        },
                    })
        except Exception as e:
            current_app.logger.error(f"Error loading metrics: {e}")
            import traceback
            traceback.print_exc()

    return render_template(
        "guideline_adherence_metrics.html",
        metrics=metrics,
        bundle_metrics=bundle_metrics,
        bundles=GUIDELINE_BUNDLES,
        current_bundle=bundle_filter,
        current_days=days,
    )


@guideline_adherence_bp.route("/bundle/<bundle_id>")
def bundle_detail(bundle_id):
    """Show details and element compliance for a specific bundle."""
    bundle = GUIDELINE_BUNDLES.get(bundle_id)
    if not bundle:
        return render_template("guideline_adherence_bundle_not_found.html", bundle_id=bundle_id), 404

    db = get_adherence_db()
    metrics = None
    recent_episodes = []

    if db:
        try:
            metrics = db.get_compliance_metrics(bundle_id=bundle_id, days=30)
            recent_episodes = [
                e for e in db.get_active_episodes(bundle_id=bundle_id)
            ][:10]
        except Exception as e:
            current_app.logger.error(f"Error loading bundle data: {e}")

    return render_template(
        "guideline_adherence_bundle.html",
        bundle=bundle,
        metrics=metrics,
        recent_episodes=recent_episodes,
    )


@guideline_adherence_bp.route("/help")
def help_page():
    """Render the help page for Guideline Adherence."""
    return render_template(
        "guideline_adherence_help.html",
        bundles=GUIDELINE_BUNDLES,
    )
