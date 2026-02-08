"""
HAI Detection Dashboard - Views

Dashboard views and API endpoints for HAI detection candidates.
Uses custom HAI models (HAICandidate, HAIClassification, HAIReview)
for the multi-stage detection/classification/review pipeline.
"""

import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q, Avg, F

from apps.authentication.decorators import can_manage_hai_detection
from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus

from .models import (
    HAICandidate, HAIClassification, HAIReview, LLMAuditLog,
    HAIType, CandidateStatus, ClassificationDecision,
    ReviewerDecision, ReviewQueueType, OverrideReasonCategory,
)

logger = logging.getLogger(__name__)

# HAI alert types for Alert model integration
HAI_ALERT_TYPES = [
    AlertType.CLABSI,
    AlertType.SSI,
    AlertType.CAUTI,
    AlertType.VAE,
    AlertType.CDI,
]

# Active statuses for candidates
ACTIVE_STATUSES = [
    CandidateStatus.PENDING,
    CandidateStatus.CLASSIFIED,
    CandidateStatus.PENDING_REVIEW,
]

# Resolved statuses
RESOLVED_STATUSES = [
    CandidateStatus.CONFIRMED,
    CandidateStatus.REJECTED,
]

# HAI type display info
HAI_TYPE_INFO = [
    ('', 'All Types'),
    ('clabsi', 'CLABSI'),
    ('ssi', 'SSI'),
    ('cauti', 'CAUTI'),
    ('vae', 'VAE'),
    ('cdi', 'CDI'),
]


def _get_summary_stats(days=30):
    """Get summary statistics for the dashboard."""
    cutoff = timezone.now() - timedelta(days=days)

    total_active = HAICandidate.objects.filter(status__in=ACTIVE_STATUSES).count()
    pending_review = HAICandidate.objects.filter(status=CandidateStatus.PENDING_REVIEW).count()
    pending_classification = HAICandidate.objects.filter(status=CandidateStatus.PENDING).count()
    confirmed = HAICandidate.objects.filter(
        status=CandidateStatus.CONFIRMED, updated_at__gte=cutoff
    ).count()
    rejected = HAICandidate.objects.filter(
        status=CandidateStatus.REJECTED, updated_at__gte=cutoff
    ).count()

    # LLM accuracy: compare classification decisions with final IP decisions
    total_reviewed = HAIReview.objects.filter(reviewed=True, reviewed_at__gte=cutoff).count()
    overrides = HAIReview.objects.filter(reviewed=True, is_override=True, reviewed_at__gte=cutoff).count()
    accuracy_pct = round(100 * (total_reviewed - overrides) / max(total_reviewed, 1), 1)

    # By HAI type
    by_type = {}
    for hai_type in HAIType:
        by_type[hai_type.value] = {
            'active': HAICandidate.objects.filter(
                hai_type=hai_type, status__in=ACTIVE_STATUSES
            ).count(),
            'confirmed': HAICandidate.objects.filter(
                hai_type=hai_type, status=CandidateStatus.CONFIRMED, updated_at__gte=cutoff
            ).count(),
            'rejected': HAICandidate.objects.filter(
                hai_type=hai_type, status=CandidateStatus.REJECTED, updated_at__gte=cutoff
            ).count(),
        }

    return {
        'total_active': total_active,
        'pending_review': pending_review,
        'pending_classification': pending_classification,
        'confirmed': confirmed,
        'rejected': rejected,
        'total_reviewed': total_reviewed,
        'overrides': overrides,
        'accuracy_pct': accuracy_pct,
        'by_type': by_type,
    }


@login_required
@can_manage_hai_detection
def dashboard(request):
    """HAI detection dashboard with active candidates and stats."""
    hai_type_filter = request.GET.get('type', '')

    candidates = HAICandidate.objects.filter(
        status__in=ACTIVE_STATUSES
    ).select_related().order_by('-created_at')

    if hai_type_filter:
        candidates = candidates.filter(hai_type=hai_type_filter)

    candidates = candidates[:50]

    # Attach latest classification info
    candidate_list = []
    for c in candidates:
        classification = c.latest_classification
        candidate_list.append({
            'candidate': c,
            'classification': classification,
        })

    stats = _get_summary_stats()

    return render(request, 'hai_detection/dashboard.html', {
        'candidates': candidate_list,
        'stats': stats,
        'hai_type_filter': hai_type_filter,
        'hai_types': HAI_TYPE_INFO,
    })


@login_required
@can_manage_hai_detection
def candidate_detail(request, candidate_id):
    """Detailed view of an HAI candidate with classification and review."""
    candidate = get_object_or_404(HAICandidate, id=candidate_id)

    # Get classifications (most recent first)
    classifications = candidate.classifications.order_by('-created_at')
    latest_classification = classifications.first()

    # Get reviews
    reviews = candidate.reviews.order_by('-created_at')
    pending_review = candidate.pending_review

    # Extract data for template
    extraction_data = None
    rules_result = None
    if latest_classification:
        extraction_data = latest_classification.extraction_data
        rules_result = latest_classification.rules_result

    # Type-specific data from JSONField
    type_specific = candidate.type_specific_data or {}

    return render(request, 'hai_detection/candidate_detail.html', {
        'candidate': candidate,
        'classification': latest_classification,
        'classifications': classifications,
        'reviews': reviews,
        'pending_review': pending_review,
        'extraction_data': extraction_data,
        'rules_result': rules_result,
        'type_specific': type_specific,
        'override_categories': OverrideReasonCategory.choices,
    })


@login_required
@can_manage_hai_detection
def history(request):
    """Resolved candidates (confirmed/rejected)."""
    hai_type_filter = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')
    days = request.GET.get('days', '90')

    try:
        days_int = min(max(int(days), 1), 365)
    except ValueError:
        days_int = 90

    cutoff = timezone.now() - timedelta(days=days_int)

    candidates = HAICandidate.objects.filter(
        status__in=RESOLVED_STATUSES,
        updated_at__gte=cutoff,
    ).order_by('-updated_at')

    if hai_type_filter:
        candidates = candidates.filter(hai_type=hai_type_filter)
    if status_filter:
        candidates = candidates.filter(status=status_filter)

    candidates = candidates[:200]

    # Attach review info
    candidate_list = []
    for c in candidates:
        review = c.latest_review
        classification = c.latest_classification
        candidate_list.append({
            'candidate': c,
            'review': review,
            'classification': classification,
        })

    return render(request, 'hai_detection/history.html', {
        'candidates': candidate_list,
        'hai_type_filter': hai_type_filter,
        'status_filter': status_filter,
        'days': days,
        'hai_types': HAI_TYPE_INFO,
    })


@login_required
@can_manage_hai_detection
def reports(request):
    """HAI reports and analytics."""
    days = request.GET.get('days', '30')
    try:
        days_int = min(max(int(days), 1), 365)
    except ValueError:
        days_int = 30

    cutoff = timezone.now() - timedelta(days=days_int)

    stats = _get_summary_stats(days_int)

    # Override statistics
    override_stats = _get_override_stats(cutoff)
    recent_overrides = _get_recent_overrides(cutoff, limit=10)

    # HAI rates by type
    hai_rates = {}
    for hai_type in HAIType:
        confirmed = HAICandidate.objects.filter(
            hai_type=hai_type, status=CandidateStatus.CONFIRMED, updated_at__gte=cutoff
        ).count()
        total = HAICandidate.objects.filter(
            hai_type=hai_type, updated_at__gte=cutoff,
            status__in=[CandidateStatus.CONFIRMED, CandidateStatus.REJECTED],
        ).count()
        hai_rates[hai_type.value] = {
            'confirmed': confirmed,
            'total': total,
            'rate': round(100 * confirmed / max(total, 1), 1),
        }

    return render(request, 'hai_detection/reports.html', {
        'stats': stats,
        'override_stats': override_stats,
        'recent_overrides': recent_overrides,
        'hai_rates': hai_rates,
        'days': days,
        'hai_types': HAI_TYPE_INFO,
    })


@login_required
@can_manage_hai_detection
def help_page(request):
    """NHSN criteria documentation and workflow guide."""
    return render(request, 'hai_detection/help.html')


# --- API Endpoints ---

@login_required
@can_manage_hai_detection
def api_stats(request):
    """Get HAI statistics as JSON."""
    try:
        stats = _get_summary_stats()
        return JsonResponse({'success': True, 'data': stats})
    except Exception as e:
        logger.error(f"Error getting HAI stats: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@can_manage_hai_detection
def api_candidates(request):
    """Get candidates as JSON."""
    try:
        limit = int(request.GET.get('limit', 100))
        candidates = HAICandidate.objects.order_by('-created_at')[:limit]

        data = [{
            'id': str(c.id),
            'hai_type': c.hai_type,
            'patient_mrn': c.patient_mrn,
            'patient_name': c.patient_name,
            'organism': c.organism,
            'culture_date': c.culture_date.isoformat(),
            'device_days': c.device_days_at_culture,
            'status': c.status,
            'created_at': c.created_at.isoformat(),
        } for c in candidates]

        return JsonResponse({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"Error getting candidates: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@can_manage_hai_detection
@require_http_methods(["POST"])
def api_submit_review(request, candidate_id):
    """Submit IP review for a candidate."""
    import json

    try:
        candidate = get_object_or_404(HAICandidate, id=candidate_id)
        data = json.loads(request.body) if request.body else {}

        reviewer = request.user.get_full_name() or request.user.username
        decision = data.get('decision')
        notes = data.get('notes', '')
        override_reason = data.get('override_reason', '')
        override_reason_category = data.get('override_reason_category', '')
        extraction_corrections = data.get('extraction_corrections')

        if not decision:
            return JsonResponse({'success': False, 'error': 'decision is required'}, status=400)

        # Map form decision to ReviewerDecision
        decision_map = {
            'confirmed': ReviewerDecision.CONFIRMED,
            'rejected': ReviewerDecision.REJECTED,
            'mbi_lcbi': ReviewerDecision.REJECTED,
            'secondary': ReviewerDecision.REJECTED,
            'needs_more_info': ReviewerDecision.NEEDS_MORE_INFO,
            'superficial_ssi': ReviewerDecision.CONFIRMED,
            'deep_ssi': ReviewerDecision.CONFIRMED,
            'organ_space_ssi': ReviewerDecision.CONFIRMED,
        }

        if decision not in decision_map:
            return JsonResponse({'success': False, 'error': f'Invalid decision: {decision}'}, status=400)

        decision_enum = decision_map[decision]

        # Determine override status
        latest_classification = candidate.latest_classification
        llm_decision = ''
        classification = None
        is_override = False

        if latest_classification:
            classification = latest_classification
            llm_decision = latest_classification.decision

            confirm_decisions = ['confirmed', 'superficial_ssi', 'deep_ssi', 'organ_space_ssi']
            reject_decisions = ['rejected', 'mbi_lcbi', 'secondary']
            if llm_decision == ClassificationDecision.HAI_CONFIRMED and decision in reject_decisions:
                is_override = True
            elif llm_decision == ClassificationDecision.NOT_HAI and decision in confirm_decisions:
                is_override = True

        # Build review notes
        decision_notes_map = {
            'confirmed': 'HAI confirmed by IP review.',
            'rejected': 'Not HAI.',
            'mbi_lcbi': 'Not CLABSI - classified as MBI-LCBI.',
            'secondary': 'Not CLABSI - secondary to another infection source.',
            'needs_more_info': 'Additional review required.',
            'superficial_ssi': 'SSI confirmed - Superficial Incisional SSI.',
            'deep_ssi': 'SSI confirmed - Deep Incisional SSI.',
            'organ_space_ssi': 'SSI confirmed - Organ/Space SSI.',
        }
        full_notes = f"{decision_notes_map.get(decision, '')} {notes}".strip()

        # Create the review
        review = HAIReview.objects.create(
            candidate=candidate,
            classification=classification,
            queue_type=ReviewQueueType.IP_REVIEW,
            reviewed=decision != 'needs_more_info',
            reviewer=reviewer,
            reviewer_decision=decision_enum,
            reviewer_notes=full_notes,
            llm_decision=llm_decision,
            is_override=is_override,
            override_reason=override_reason if is_override else '',
            override_reason_category=override_reason_category if is_override else '',
            extraction_corrections=extraction_corrections if is_override else None,
            reviewed_at=timezone.now() if decision != 'needs_more_info' else None,
        )

        # Update candidate status for final decisions
        final_decisions = [
            'confirmed', 'rejected', 'mbi_lcbi', 'secondary',
            'superficial_ssi', 'deep_ssi', 'organ_space_ssi',
        ]
        if decision in final_decisions:
            if decision in ['confirmed', 'superficial_ssi', 'deep_ssi', 'organ_space_ssi']:
                candidate.status = CandidateStatus.CONFIRMED
            else:
                candidate.status = CandidateStatus.REJECTED
            candidate.save(update_fields=['status', 'updated_at'])

            # Update corresponding Alert if it exists
            try:
                alert = Alert.objects.filter(
                    source_module='hai_detection',
                    source_id=str(candidate.id),
                ).first()
                if alert:
                    if candidate.status == CandidateStatus.CONFIRMED:
                        alert.status = AlertStatus.RESOLVED
                        alert.resolution_reason = 'accepted'
                    else:
                        alert.status = AlertStatus.RESOLVED
                        alert.resolution_reason = 'false_positive'
                    alert.resolution_notes = full_notes
                    alert.resolved_at = timezone.now()
                    alert.save(update_fields=[
                        'status', 'resolution_reason', 'resolution_notes', 'resolved_at',
                    ])
            except Exception as e:
                logger.warning(f"Failed to update Alert for candidate {candidate.id}: {e}")

        return JsonResponse({
            'success': True,
            'data': {
                'new_status': candidate.status,
                'is_override': is_override,
                'llm_decision': llm_decision,
            },
        })

    except Exception as e:
        logger.error(f"Error submitting review for {candidate_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@can_manage_hai_detection
def api_override_stats(request):
    """Get LLM classification override statistics."""
    try:
        cutoff = timezone.now() - timedelta(days=90)
        stats = _get_override_stats(cutoff)
        return JsonResponse({'success': True, 'data': stats})
    except Exception as e:
        logger.error(f"Error getting override stats: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@can_manage_hai_detection
def api_recent_overrides(request):
    """Get recent override details."""
    try:
        limit = int(request.GET.get('limit', 20))
        cutoff = timezone.now() - timedelta(days=90)
        overrides = _get_recent_overrides(cutoff, limit=limit)
        return JsonResponse({'success': True, 'data': overrides})
    except Exception as e:
        logger.error(f"Error getting recent overrides: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# --- Helper functions ---

def _get_override_stats(cutoff):
    """Get override statistics for the given period."""
    reviews = HAIReview.objects.filter(reviewed=True, reviewed_at__gte=cutoff)

    total = reviews.count()
    overrides = reviews.filter(is_override=True).count()
    accepted = total - overrides

    # By LLM decision
    by_llm_decision = {}
    for decision in ClassificationDecision:
        llm_reviews = reviews.filter(llm_decision=decision)
        llm_total = llm_reviews.count()
        llm_overrides = llm_reviews.filter(is_override=True).count()
        if llm_total > 0:
            by_llm_decision[decision.value] = {
                'total': llm_total,
                'overrides': llm_overrides,
                'acceptance_rate': round(100 * (llm_total - llm_overrides) / llm_total, 1),
            }

    # By override category
    by_category = {}
    override_reviews = reviews.filter(is_override=True).exclude(override_reason_category='')
    for category in OverrideReasonCategory:
        count = override_reviews.filter(override_reason_category=category).count()
        if count > 0:
            by_category[category.value] = {
                'count': count,
                'label': category.label,
            }

    return {
        'total_reviews': total,
        'completed_reviews': total,
        'total_overrides': overrides,
        'accepted_classifications': accepted,
        'acceptance_rate_pct': round(100 * accepted / max(total, 1), 1),
        'override_rate_pct': round(100 * overrides / max(total, 1), 1),
        'by_llm_decision': by_llm_decision,
        'by_category': by_category,
    }


def _get_recent_overrides(cutoff, limit=10):
    """Get recent override details."""
    overrides = HAIReview.objects.filter(
        reviewed=True,
        is_override=True,
        reviewed_at__gte=cutoff,
    ).select_related('candidate', 'classification').order_by('-reviewed_at')[:limit]

    return [{
        'review_id': str(o.id),
        'candidate_id': str(o.candidate_id),
        'hai_type': o.candidate.hai_type,
        'patient_mrn': o.candidate.patient_mrn,
        'organism': o.candidate.organism,
        'llm_decision': o.llm_decision,
        'reviewer_decision': o.reviewer_decision,
        'reviewer': o.reviewer,
        'override_reason': o.override_reason,
        'override_reason_category': o.override_reason_category,
        'reviewed_at': o.reviewed_at.isoformat() if o.reviewed_at else None,
    } for o in overrides]
