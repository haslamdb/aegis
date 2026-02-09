"""
Guideline Adherence - Views

Dashboard views and API endpoints for clinical guideline bundle compliance monitoring.
"""

import csv
from io import StringIO

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta

from apps.authentication.decorators import can_manage_guideline_adherence
from apps.alerts.models import (
    Alert, AlertStatus, AlertSeverity, AlertType, ResolutionReason,
)

from .models import (
    BundleEpisode, ElementResult, EpisodeAssessment, EpisodeReview,
    EpisodeStatus, ElementCheckStatus, AdherenceLevel, ReviewDecision,
)


GUIDELINE_RESOLUTION_REASONS = [
    (ResolutionReason.ACCEPTED, 'Recommendation Accepted'),
    (ResolutionReason.CLINICAL_JUSTIFICATION, 'Clinical Justification'),
    (ResolutionReason.DISCUSSED_WITH_TEAM, 'Discussed with Team'),
    (ResolutionReason.MESSAGED_TEAM, 'Messaged Team'),
    (ResolutionReason.ESCALATED_TO_ATTENDING, 'Escalated to Attending'),
    (ResolutionReason.NO_ACTION_NEEDED, 'No Action Needed'),
    (ResolutionReason.FALSE_POSITIVE, 'False Positive'),
    (ResolutionReason.OTHER, 'Other'),
]

GA_ALERT_TYPES = [
    AlertType.GUIDELINE_ADHERENCE,
    AlertType.BUNDLE_INCOMPLETE,
]


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
@can_manage_guideline_adherence
def dashboard(request):
    """Compliance stats, active episodes, bundle cards."""
    from .bundles import GUIDELINE_BUNDLES, get_enabled_bundles

    active_episodes = BundleEpisode.objects.filter(
        status=EpisodeStatus.ACTIVE,
    ).order_by('-created_at')[:20]

    # Stats
    all_active = BundleEpisode.objects.filter(status=EpisodeStatus.ACTIVE)
    completed_30d = BundleEpisode.objects.filter(
        status__in=[EpisodeStatus.COMPLETE, EpisodeStatus.CLOSED],
        completed_at__gte=timezone.now() - timedelta(days=30),
    )
    active_alerts = Alert.objects.active().filter(alert_type__in=GA_ALERT_TYPES)

    # Overall compliance from completed episodes
    total_completed = completed_30d.count()
    full_adherence = completed_30d.filter(adherence_level=AdherenceLevel.FULL).count()
    overall_compliance = round(
        (full_adherence / total_completed * 100) if total_completed > 0 else 0, 1
    )

    # Per-bundle compliance
    bundle_stats = []
    for bundle in get_enabled_bundles():
        bundle_completed = completed_30d.filter(bundle_id=bundle.bundle_id)
        b_total = bundle_completed.count()
        b_full = bundle_completed.filter(adherence_level=AdherenceLevel.FULL).count()
        b_active = all_active.filter(bundle_id=bundle.bundle_id).count()
        bundle_stats.append({
            'bundle': bundle,
            'total_episodes': b_total,
            'full_adherence': b_full,
            'compliance_pct': round((b_full / b_total * 100) if b_total > 0 else 0, 1),
            'active_count': b_active,
        })

    stats = {
        'overall_compliance': overall_compliance,
        'bundles_tracked': len(get_enabled_bundles()),
        'active_episodes': all_active.count(),
        'active_alerts': active_alerts.count(),
        'completed_30d': total_completed,
    }

    context = {
        'stats': stats,
        'bundle_stats': bundle_stats,
        'active_episodes': active_episodes,
    }

    return render(request, 'guideline_adherence/dashboard.html', context)


@login_required
@can_manage_guideline_adherence
def active_episodes(request):
    """Filterable episode list with LLM status."""
    episodes = BundleEpisode.objects.filter(
        status=EpisodeStatus.ACTIVE,
    ).prefetch_related('element_results')

    # Filters
    bundle_id = request.GET.get('bundle')
    if bundle_id:
        episodes = episodes.filter(bundle_id=bundle_id)

    review_status = request.GET.get('review_status')
    if review_status:
        episodes = episodes.filter(review_status=review_status)

    episodes = episodes.order_by('-created_at')

    # Get bundle options for filter
    from .bundles import get_enabled_bundles
    bundles = get_enabled_bundles()

    context = {
        'episodes': episodes,
        'bundles': bundles,
        'current_filters': {
            'bundle': bundle_id,
            'review_status': review_status,
        },
    }

    return render(request, 'guideline_adherence/active_episodes.html', context)


@login_required
@can_manage_guideline_adherence
def episode_detail(request, pk):
    """Two-column: elements + review sidebar."""
    episode = get_object_or_404(
        BundleEpisode.objects.prefetch_related(
            'element_results', 'assessments', 'reviews',
        ),
        id=pk,
    )

    elements = episode.element_results.all().order_by('element_id')
    assessments = episode.assessments.order_by('-created_at')
    reviews = episode.reviews.order_by('-reviewed_at')
    latest_assessment = assessments.first()

    # Get related alerts
    alerts = Alert.objects.filter(
        alert_type__in=GA_ALERT_TYPES,
        source_module='guideline_adherence',
        source_id=str(episode.id),
    ).order_by('-created_at')

    context = {
        'episode': episode,
        'elements': elements,
        'assessments': assessments,
        'reviews': reviews,
        'latest_assessment': latest_assessment,
        'alerts': alerts,
        'resolution_reasons': GUIDELINE_RESOLUTION_REASONS,
        'review_decisions': ReviewDecision.choices,
    }

    return render(request, 'guideline_adherence/episode_detail.html', context)


@login_required
@can_manage_guideline_adherence
def bundle_detail(request, bundle_id):
    """Bundle info, element compliance, recent episodes."""
    from .bundles import get_bundle

    bundle = get_bundle(bundle_id)
    if not bundle:
        from django.http import Http404
        raise Http404("Bundle not found")

    # Recent episodes for this bundle
    recent_episodes = BundleEpisode.objects.filter(
        bundle_id=bundle_id,
    ).order_by('-created_at')[:20]

    # Element compliance rates (last 30 days)
    completed = BundleEpisode.objects.filter(
        bundle_id=bundle_id,
        status__in=[EpisodeStatus.COMPLETE, EpisodeStatus.CLOSED],
        completed_at__gte=timezone.now() - timedelta(days=30),
    )

    element_stats = []
    for elem in bundle.elements:
        results = ElementResult.objects.filter(
            episode__in=completed,
            element_id=elem.element_id,
            status__in=[ElementCheckStatus.MET, ElementCheckStatus.NOT_MET],
        )
        total = results.count()
        met = results.filter(status=ElementCheckStatus.MET).count()
        element_stats.append({
            'element': elem,
            'total': total,
            'met': met,
            'compliance_pct': round((met / total * 100) if total > 0 else 0, 1),
        })

    context = {
        'bundle': bundle,
        'recent_episodes': recent_episodes,
        'element_stats': element_stats,
    }

    return render(request, 'guideline_adherence/bundle_detail.html', context)


@login_required
@can_manage_guideline_adherence
def metrics(request):
    """Compliance trends, per-bundle/element breakdown."""
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    completed = BundleEpisode.objects.filter(
        status__in=[EpisodeStatus.COMPLETE, EpisodeStatus.CLOSED],
        completed_at__gte=start_date,
    )

    total = completed.count()
    full = completed.filter(adherence_level=AdherenceLevel.FULL).count()
    partial = completed.filter(adherence_level=AdherenceLevel.PARTIAL).count()
    low = completed.filter(adherence_level=AdherenceLevel.LOW).count()

    # Per-bundle breakdown
    from .bundles import get_enabled_bundles
    bundle_metrics = []
    for bundle in get_enabled_bundles():
        b_completed = completed.filter(bundle_id=bundle.bundle_id)
        b_total = b_completed.count()
        b_full = b_completed.filter(adherence_level=AdherenceLevel.FULL).count()
        bundle_metrics.append({
            'bundle': bundle,
            'total': b_total,
            'full': b_full,
            'compliance_pct': round((b_full / b_total * 100) if b_total > 0 else 0, 1),
        })

    # Review stats
    reviews = EpisodeReview.objects.filter(reviewed_at__gte=start_date)
    review_count = reviews.count()
    override_count = reviews.filter(is_override=True).count()

    context = {
        'days': days,
        'total': total,
        'full': full,
        'partial': partial,
        'low': low,
        'overall_compliance': round((full / total * 100) if total > 0 else 0, 1),
        'bundle_metrics': bundle_metrics,
        'review_count': review_count,
        'override_count': override_count,
        'override_rate': round((override_count / review_count * 100) if review_count > 0 else 0, 1),
    }

    return render(request, 'guideline_adherence/metrics.html', context)


@login_required
@can_manage_guideline_adherence
def history(request):
    """All episodes (active + completed)."""
    episodes = BundleEpisode.objects.all()

    # Filters
    status = request.GET.get('status')
    if status:
        episodes = episodes.filter(status=status)

    bundle_id = request.GET.get('bundle')
    if bundle_id:
        episodes = episodes.filter(bundle_id=bundle_id)

    adherence = request.GET.get('adherence')
    if adherence:
        episodes = episodes.filter(adherence_level=adherence)

    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    episodes = episodes.filter(created_at__gte=start_date)

    episodes = episodes.order_by('-created_at')

    from .bundles import get_enabled_bundles

    context = {
        'episodes': episodes,
        'bundles': get_enabled_bundles(),
        'days': days,
        'current_filters': {
            'status': status,
            'bundle': bundle_id,
            'adherence': adherence,
            'days': days,
        },
    }

    return render(request, 'guideline_adherence/history.html', context)


@login_required
@can_manage_guideline_adherence
def help_page(request):
    """Bundle reference, element descriptions, workflow guide."""
    from .bundles import GUIDELINE_BUNDLES

    context = {
        'bundles': GUIDELINE_BUNDLES,
    }

    return render(request, 'guideline_adherence/help.html', context)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@can_manage_guideline_adherence
@require_http_methods(["GET"])
def api_stats(request):
    """JSON compliance stats."""
    active = BundleEpisode.objects.filter(status=EpisodeStatus.ACTIVE).count()
    completed_30d = BundleEpisode.objects.filter(
        status__in=[EpisodeStatus.COMPLETE, EpisodeStatus.CLOSED],
        completed_at__gte=timezone.now() - timedelta(days=30),
    )
    total = completed_30d.count()
    full = completed_30d.filter(adherence_level=AdherenceLevel.FULL).count()
    alerts = Alert.objects.active().filter(alert_type__in=GA_ALERT_TYPES).count()

    return JsonResponse({
        'success': True,
        'stats': {
            'active_episodes': active,
            'completed_30d': total,
            'full_adherence': full,
            'overall_compliance': round((full / total * 100) if total > 0 else 0, 1),
            'active_alerts': alerts,
        },
    })


@login_required
@can_manage_guideline_adherence
@require_http_methods(["POST"])
def api_review(request, pk):
    """Submit review decision for an episode."""
    episode = get_object_or_404(BundleEpisode, id=pk)

    reviewer_decision = request.POST.get('reviewer_decision')
    if not reviewer_decision:
        return JsonResponse({'success': False, 'error': 'Decision required'}, status=400)

    try:
        # Get latest assessment for comparison
        latest_assessment = episode.assessments.order_by('-created_at').first()
        llm_decision = ''
        if latest_assessment:
            llm_decision = latest_assessment.primary_determination

        is_override = (
            llm_decision != ''
            and reviewer_decision != llm_decision
        )

        review = EpisodeReview.objects.create(
            episode=episode,
            assessment=latest_assessment,
            reviewer=request.user.username,
            reviewer_decision=reviewer_decision,
            llm_decision=llm_decision,
            is_override=is_override,
            override_reason_category=request.POST.get('override_reason', ''),
            deviation_type=request.POST.get('deviation_type', ''),
            notes=request.POST.get('notes', ''),
        )

        # Update episode
        episode.review_status = 'reviewed'
        episode.overall_determination = reviewer_decision
        episode.save(update_fields=['review_status', 'overall_determination', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': 'Review submitted',
            'episode_id': str(episode.id),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@can_manage_guideline_adherence
@require_http_methods(["POST"])
def api_acknowledge(request, pk):
    """Acknowledge a guideline alert."""
    alert = get_object_or_404(Alert, id=pk, alert_type__in=GA_ALERT_TYPES)

    try:
        ip_address = request.META.get('REMOTE_ADDR')
        alert.acknowledge(request.user, ip_address=ip_address)
        return JsonResponse({'success': True, 'message': 'Alert acknowledged'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@can_manage_guideline_adherence
@require_http_methods(["POST"])
def api_resolve(request, pk):
    """Resolve a guideline alert."""
    alert = get_object_or_404(Alert, id=pk, alert_type__in=GA_ALERT_TYPES)

    reason = request.POST.get('reason')
    notes = request.POST.get('notes', '')
    ip_address = request.META.get('REMOTE_ADDR')

    if not reason:
        return JsonResponse({'success': False, 'error': 'Resolution reason required'}, status=400)

    try:
        alert.resolve(request.user, reason, notes, ip_address=ip_address)
        return JsonResponse({'success': True, 'message': 'Alert resolved'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@can_manage_guideline_adherence
def api_export(request):
    """CSV export of episodes."""
    export_type = request.GET.get('type', 'active')

    if export_type == 'history':
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        episodes = BundleEpisode.objects.filter(
            created_at__gte=start_date,
        ).order_by('-created_at')
        filename = 'guideline_episodes_history.csv'
    else:
        episodes = BundleEpisode.objects.filter(
            status=EpisodeStatus.ACTIVE,
        ).order_by('-created_at')
        filename = 'guideline_episodes_active.csv'

    def generate_rows():
        output = StringIO()
        writer = csv.writer(output)

        headers = [
            'Episode ID', 'Patient MRN', 'Patient Name', 'Unit',
            'Bundle', 'Trigger', 'Trigger Time', 'Status',
            'Adherence %', 'Adherence Level', 'Elements Met',
            'Elements Not Met', 'Elements Pending', 'Created At',
        ]
        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for ep in episodes:
            writer.writerow([
                str(ep.id),
                ep.patient_mrn,
                ep.patient_name,
                ep.patient_unit,
                ep.bundle_name,
                ep.trigger_description,
                ep.trigger_time.strftime('%Y-%m-%d %H:%M') if ep.trigger_time else '',
                ep.status,
                ep.adherence_percentage,
                ep.adherence_level,
                ep.elements_met,
                ep.elements_not_met,
                ep.elements_pending,
                ep.created_at.strftime('%Y-%m-%d %H:%M') if ep.created_at else '',
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    response = StreamingHttpResponse(generate_rows(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
