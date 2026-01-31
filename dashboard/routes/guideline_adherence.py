"""Routes for Guideline Adherence module.

This module tracks adherence to evidence-based clinical guidelines/bundles
at the population level for quality improvement and JC reporting.
"""

import sys
from pathlib import Path
from flask import Blueprint, render_template, current_app, request, redirect, url_for, flash, jsonify

# Add paths for guideline adherence imports
GUIDELINE_PATH = Path(__file__).parent.parent.parent / "guideline-adherence"
if str(GUIDELINE_PATH) not in sys.path:
    sys.path.insert(0, str(GUIDELINE_PATH))

try:
    from guideline_adherence import GUIDELINE_BUNDLES
    from guideline_src.episode_db import EpisodeDB, EpisodeAssessment, EpisodeReview
    from guideline_src.config import Config as adherence_config
except ImportError:
    GUIDELINE_BUNDLES = {}
    EpisodeDB = None
    EpisodeAssessment = None
    EpisodeReview = None
    adherence_config = None


# ============================================================================
# OVERRIDE REASON TAXONOMY (HAI-style)
# ============================================================================

GUIDELINE_OVERRIDE_REASONS = {
    "extraction_error": "LLM misread clinical documentation",
    "element_detection_error": "LLM missed or incorrectly detected an element",
    "timing_error": "LLM got timing/sequence wrong",
    "clinical_judgment": "Clinical context not captured in notes",
    "documentation_gap": "Key documentation not available",
    "rule_interpretation": "Different interpretation of guideline",
    "patient_specific": "Patient-specific factors justify deviation",
    "other": "Other (please specify)",
}

DEVIATION_TYPES = {
    "documentation": "Documentation gap (element may have been done)",
    "timing": "Timing deviation (done outside recommended window)",
    "missing_element": "Required element not completed",
    "clinical_judgment": "Intentional deviation with clinical rationale",
}

# Import training collector for review functionality
try:
    from guideline_src.nlp.training_collector import (
        get_training_collector,
        get_guideline_review_collector,
        OVERRIDE_REASONS,
        MISSED_FINDING_OPTIONS,
    )
    TRAINING_COLLECTOR_AVAILABLE = True
except ImportError:
    TRAINING_COLLECTOR_AVAILABLE = False
    get_training_collector = None
    get_guideline_review_collector = None
    OVERRIDE_REASONS = {}
    MISSED_FINDING_OPTIONS = []


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

    # Get training collector for extraction status
    collector = None
    if TRAINING_COLLECTOR_AVAILABLE:
        collector = get_training_collector()

    episodes = []
    if db:
        try:
            # Get active episodes
            raw_episodes = db.get_active_episodes(limit=100)

            # Filter by bundle if specified
            if bundle_filter:
                raw_episodes = [ep for ep in raw_episodes if ep.bundle_id == bundle_filter]

            # Enrich with latest results and extraction status
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

                # Check extraction status
                extraction_status = "not_analyzed"
                extraction_record = None
                if collector:
                    extraction_record = collector.get_record_by_episode(ep.id)
                    if extraction_record:
                        if extraction_record.human_reviewed:
                            extraction_status = "reviewed"
                        else:
                            extraction_status = "pending_review"

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
                    "extraction_status": extraction_status,
                    "extracted_appearance": extraction_record.extracted_appearance if extraction_record else None,
                    "extraction_confidence": extraction_record.extraction_confidence if extraction_record else None,
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


@guideline_adherence_bp.route("/episode/<int:episode_id>/detail")
def episode_detail_full(episode_id):
    """HAI-style detail/review page for an episode.

    Shows LLM assessment, element status, and allows human review.
    """
    db = get_episode_db()

    if not db:
        flash("Database not available", "error")
        return redirect(url_for("guideline_adherence.active_episodes"))

    try:
        # Get episode
        ep = db.get_episode(episode_id)
        if not ep:
            return render_template(
                "guideline_adherence_episode_not_found.html",
                episode_id=episode_id
            ), 404

        # Get element results
        element_results = db.get_element_results(episode_id)

        # Get assessments and reviews
        assessments = db.get_assessments_for_episode(episode_id)
        reviews = db.get_reviews_for_episode(episode_id)

        # Get bundle definition
        bundle = GUIDELINE_BUNDLES.get(ep.bundle_id)

        # Build episode dict
        episode = {
            "id": ep.id,
            "patient_id": ep.patient_id,
            "patient_mrn": ep.patient_mrn or ep.patient_id,
            "encounter_id": ep.encounter_id,
            "bundle_id": ep.bundle_id,
            "bundle_name": ep.bundle_name,
            "status": ep.status,
            "trigger_type": ep.trigger_type,
            "trigger_code": ep.trigger_code,
            "trigger_description": ep.trigger_description,
            "trigger_time": ep.trigger_time,
            "patient_age_days": ep.patient_age_days,
            "patient_unit": ep.patient_unit,
            "adherence_pct": ep.adherence_percentage or 0,
            "adherence_level": ep.adherence_level,
            "review_status": ep.review_status,
            "overall_determination": ep.overall_determination,
            "last_assessment_at": ep.last_assessment_at,
        }

        # Build results list
        results = []
        for r in element_results:
            results.append({
                "id": r.id,
                "element_id": r.element_id,
                "element_name": r.element_name,
                "element_description": r.element_description,
                "status": r.status,
                "value": r.value,
                "notes": r.notes,
                "deadline": r.deadline,
                "required": r.required,
            })

        # Get latest assessment for display
        latest_assessment = None
        if assessments:
            a = assessments[0]
            latest_assessment = {
                "id": a.id,
                "assessment_type": a.assessment_type,
                "primary_determination": a.primary_determination,
                "confidence": a.confidence,
                "reasoning": a.reasoning,
                "supporting_evidence": a.supporting_evidence,
                "extraction_data": a.extraction_data,
                "model_used": a.model_used,
                "response_time_ms": a.response_time_ms,
                "created_at": a.created_at,
            }

        return render_template(
            "guideline_adherence_episode_detail.html",
            episode=episode,
            results=results,
            assessments=assessments,
            latest_assessment=latest_assessment,
            reviews=reviews,
            bundle=bundle,
            override_reasons=GUIDELINE_OVERRIDE_REASONS,
            deviation_types=DEVIATION_TYPES,
        )

    except Exception as e:
        current_app.logger.error(f"Error loading episode detail {episode_id}: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error loading episode: {e}", "error")
        return redirect(url_for("guideline_adherence.active_episodes"))


@guideline_adherence_bp.route("/api/episodes/<int:episode_id>/review", methods=["POST"])
def api_submit_episode_review(episode_id):
    """Submit review for an episode (HAI-style API)."""
    db = get_episode_db()

    if not db:
        return jsonify({"error": "Database not available"}), 500

    if not EpisodeReview:
        return jsonify({"error": "EpisodeReview not available"}), 500

    try:
        data = request.json or {}

        reviewer = data.get("reviewer")
        decision = data.get("decision")

        if not reviewer:
            return jsonify({"error": "reviewer is required"}), 400
        if not decision:
            return jsonify({"error": "decision is required"}), 400

        # Validate decision
        valid_decisions = ["guideline_appropriate", "guideline_deviation", "needs_more_info"]
        if decision not in valid_decisions:
            return jsonify({"error": f"Invalid decision: {decision}"}), 400

        # Get latest assessment to detect override
        assessments = db.get_assessments_for_episode(episode_id)
        llm_decision = None
        assessment_id = None
        is_override = False

        if assessments:
            latest = assessments[0]
            assessment_id = latest.id
            llm_decision = latest.primary_determination

            # Determine if this is an override
            if llm_decision and llm_decision != decision:
                # Override cases:
                # - LLM said appropriate, reviewer says deviation
                # - LLM said deviation, reviewer says appropriate
                if llm_decision != "pending" and decision != "needs_more_info":
                    is_override = True

        # Create review
        review = EpisodeReview(
            episode_id=episode_id,
            reviewer=reviewer,
            reviewer_decision=decision,
            deviation_type=data.get("deviation_type"),
            llm_decision=llm_decision,
            is_override=is_override,
            override_reason_category=data.get("override_reason_category") if is_override else None,
            extraction_corrections=data.get("extraction_corrections") if is_override else None,
            notes=data.get("notes"),
            assessment_id=assessment_id,
        )

        review_id = db.save_review(review)

        # Log training data if override
        if is_override and TRAINING_COLLECTOR_AVAILABLE and assessments:
            try:
                _log_guideline_review_training(episode_id, review, assessments[0])
            except Exception as e:
                current_app.logger.warning(f"Failed to log training data: {e}")

        return jsonify({
            "success": True,
            "review_id": review_id,
            "is_override": is_override,
            "llm_decision": llm_decision,
        })

    except Exception as e:
        current_app.logger.error(f"Error submitting review: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _log_guideline_review_training(episode_id, review, assessment):
    """Log guideline review for training data capture."""
    if not get_guideline_review_collector:
        return

    try:
        collector = get_guideline_review_collector()
        collector.log_guideline_review(
            episode_id=episode_id,
            llm_determination=assessment.primary_determination,
            llm_confidence=assessment.confidence,
            human_determination=review.reviewer_decision,
            is_override=review.is_override,
            override_reason=review.override_reason_category,
            corrections=review.extraction_corrections,
            deviation_type=review.deviation_type,
            reviewer=review.reviewer,
        )
    except Exception as e:
        current_app.logger.warning(f"Failed to log guideline review training: {e}")


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


@guideline_adherence_bp.route("/review")
def review_queue():
    """Show the clinical appearance review queue."""
    if not TRAINING_COLLECTOR_AVAILABLE:
        return render_template(
            "guideline_adherence_review.html",
            queue=[],
            stats=None,
            error="Training collector not available",
        )

    try:
        collector = get_training_collector()
        queue = collector.get_review_queue(limit=50)
        stats = collector.get_stats()

        # Enrich queue with episode details
        db = get_episode_db()
        if db:
            for item in queue:
                if item.get("episode_id"):
                    ep = db.get_episode(item["episode_id"])
                    if ep:
                        item["patient_mrn"] = ep.patient_mrn
                        item["bundle_name"] = ep.bundle_name
                        item["trigger_time"] = ep.trigger_time.isoformat() if ep.trigger_time else None

        return render_template(
            "guideline_adherence_review.html",
            queue=queue,
            stats=stats,
            error=None,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading review queue: {e}")
        import traceback
        traceback.print_exc()
        return render_template(
            "guideline_adherence_review.html",
            queue=[],
            stats=None,
            error=str(e),
        )


@guideline_adherence_bp.route("/episode/<int:episode_id>/review", methods=["GET", "POST"])
def episode_review(episode_id):
    """Review clinical appearance extraction for an episode."""
    if not TRAINING_COLLECTOR_AVAILABLE:
        flash("Training collector not available", "error")
        return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

    db = get_episode_db()
    collector = get_training_collector()

    # Get episode
    episode = None
    if db:
        ep = db.get_episode(episode_id)
        if ep:
            episode = {
                "id": ep.id,
                "patient_id": ep.patient_id,
                "patient_mrn": ep.patient_mrn,
                "bundle_id": ep.bundle_id,
                "bundle_name": ep.bundle_name,
                "trigger_time": ep.trigger_time.isoformat() if ep.trigger_time else None,
            }

    if not episode:
        flash("Episode not found", "error")
        return redirect(url_for("guideline_adherence.active_episodes"))

    # Get extraction record for this episode
    record = collector.get_record_by_episode(episode_id)

    if request.method == "POST":
        # Process review submission
        reviewer_id = request.form.get("reviewer_id", "unknown")
        appearance_decision = request.form.get("appearance_decision")
        override_reason = request.form.get("override_reason")
        override_reason_text = request.form.get("override_reason_text", "")
        missed_findings = request.form.getlist("missed_findings")
        false_positives = request.form.getlist("false_positives")
        review_notes = request.form.get("review_notes", "")

        if not record:
            flash("No extraction record found for this episode", "error")
            return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

        try:
            collector.log_human_review(
                record_id=record.id,
                reviewer_id=reviewer_id,
                appearance_decision=appearance_decision,
                override_reason=override_reason if appearance_decision != "confirm" else None,
                override_reason_text=override_reason_text if override_reason == "other" else None,
                missed_findings=missed_findings,
                false_positives=false_positives,
                review_notes=review_notes,
            )
            flash("Review submitted successfully", "success")
            return redirect(url_for("guideline_adherence.review_queue"))
        except Exception as e:
            current_app.logger.error(f"Error submitting review: {e}")
            flash(f"Error submitting review: {e}", "error")

    # GET request - show review form
    return render_template(
        "guideline_adherence_review_episode.html",
        episode=episode,
        record=record,
        override_reasons=OVERRIDE_REASONS,
        missed_finding_options=MISSED_FINDING_OPTIONS,
    )


@guideline_adherence_bp.route("/training/stats")
def training_stats():
    """Show training data collection statistics."""
    if not TRAINING_COLLECTOR_AVAILABLE:
        return render_template(
            "guideline_adherence_training_stats.html",
            stats=None,
            error="Training collector not available",
        )

    try:
        collector = get_training_collector()
        stats = collector.get_stats()

        return render_template(
            "guideline_adherence_training_stats.html",
            stats=stats,
            error=None,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading training stats: {e}")
        return render_template(
            "guideline_adherence_training_stats.html",
            stats=None,
            error=str(e),
        )


@guideline_adherence_bp.route("/episode/<int:episode_id>/analyze", methods=["GET", "POST"])
def analyze_episode(episode_id):
    """Run LLM extraction on an episode's clinical notes.

    Automatically retrieves notes via FHIR and runs tiered LLM analysis.
    Uses demo mode with sample notes if no FHIR server is available.
    """
    if not TRAINING_COLLECTOR_AVAILABLE:
        flash("Training collector not available", "error")
        return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

    db = get_episode_db()
    collector = get_training_collector()

    # Get episode
    episode = None
    ep = None
    if db:
        ep = db.get_episode(episode_id)
        if ep:
            episode = {
                "id": ep.id,
                "patient_id": ep.patient_id,
                "patient_mrn": ep.patient_mrn,
                "bundle_id": ep.bundle_id,
                "bundle_name": ep.bundle_name,
                "trigger_time": ep.trigger_time,
                "patient_age_days": ep.patient_age_days,
            }

    if not episode:
        flash("Episode not found", "error")
        return redirect(url_for("guideline_adherence.active_episodes"))

    # Check if already analyzed
    existing_record = collector.get_record_by_episode(episode_id)

    # For GET requests, show confirmation page
    # For POST requests, run the analysis
    if request.method == "POST":
        try:
            # Import FHIR client and extractor
            from guideline_src.fhir_client import get_fhir_client
            from guideline_src.nlp.clinical_impression import get_tiered_clinical_impression_extractor
            from datetime import timedelta

            # Get extractor
            extractor = get_tiered_clinical_impression_extractor()
            if not extractor:
                flash("LLM extractor not available", "error")
                return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

            # Try real FHIR first, fall back to demo mode
            use_demo = request.form.get("use_demo", "false") == "true"
            fhir_client = get_fhir_client(demo_mode=use_demo)

            # Retrieve clinical notes automatically
            trigger_time = episode["trigger_time"]
            notes = fhir_client.get_recent_notes(
                patient_id=episode["patient_id"],
                since_time=trigger_time - timedelta(hours=24) if trigger_time else None,
                since_hours=48,
            )

            if not notes:
                # Try demo mode if no notes found
                if not use_demo:
                    flash("No clinical notes found. Trying demo mode...", "warning")
                    fhir_client = get_fhir_client(demo_mode=True)
                    notes = fhir_client.get_recent_notes(
                        patient_id=episode["patient_id"],
                        since_time=trigger_time - timedelta(hours=24) if trigger_time else None,
                        since_hours=48,
                    )

                if not notes:
                    flash("No clinical notes available for analysis", "error")
                    return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

            # Extract note texts
            note_texts = [n.get("text", "") for n in notes if n.get("text")]
            if not note_texts:
                flash("Clinical notes have no text content", "error")
                return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

            # Run tiered extraction
            result = extractor.extract(
                notes=note_texts,
                episode_id=episode_id,
                patient_id=episode["patient_id"],
                patient_mrn=episode["patient_mrn"],
                patient_age_days=episode.get("patient_age_days"),
            )

            flash(
                f"Analysis complete: {result.appearance.value} ({result.confidence} confidence). "
                f"Analyzed {len(note_texts)} note(s). Response time: {result.response_time_ms}ms",
                "success"
            )
            return redirect(url_for("guideline_adherence.episode_review", episode_id=episode_id))

        except Exception as e:
            current_app.logger.error(f"Error running extraction: {e}")
            import traceback
            traceback.print_exc()
            flash(f"Error running extraction: {e}", "error")
            return redirect(url_for("guideline_adherence.episode_detail", episode_id=episode_id))

    # GET request - show confirmation page with note preview
    notes_preview = []
    try:
        from guideline_src.fhir_client import get_fhir_client
        from datetime import timedelta

        # Try to fetch notes for preview
        fhir_client = get_fhir_client(demo_mode=False)
        trigger_time = episode["trigger_time"]
        notes = fhir_client.get_recent_notes(
            patient_id=episode["patient_id"],
            since_time=trigger_time - timedelta(hours=24) if trigger_time else None,
            since_hours=48,
        )

        if notes:
            for n in notes[:5]:  # Show up to 5 notes
                notes_preview.append({
                    "type": n.get("type", "Note"),
                    "date": n.get("date"),
                    "author": n.get("author"),
                    "text_preview": (n.get("text", "")[:200] + "...") if len(n.get("text", "")) > 200 else n.get("text", ""),
                })
    except Exception:
        pass  # Preview is optional

    return render_template(
        "guideline_adherence_analyze.html",
        episode=episode,
        existing_record=existing_record,
        notes_preview=notes_preview,
        notes_available=len(notes_preview) > 0,
    )


@guideline_adherence_bp.route("/help")
def help_page():
    """Render the help page for Guideline Adherence."""
    return render_template(
        "guideline_adherence_help.html",
        bundles=GUIDELINE_BUNDLES,
    )
