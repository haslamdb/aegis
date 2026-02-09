"""
ABX Indication Monitoring - Views

Dashboard views and API endpoints for antibiotic indication monitoring.
Tracks LLM-extracted clinical syndromes and CCHMC guideline concordance.
"""

import csv
from io import StringIO

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta

from apps.authentication.decorators import physician_or_higher_required
from apps.alerts.models import (
    Alert, AlertStatus, AlertSeverity, AlertType, ResolutionReason,
)

from .models import (
    IndicationCandidate, IndicationReview,
    CandidateStatus, SyndromeDecision, AgentDecision,
    AgentCategoryChoice,
)


INDICATION_RESOLUTION_REASONS = [
    (ResolutionReason.THERAPY_CHANGED, 'Therapy Changed / De-escalated'),
    (ResolutionReason.THERAPY_STOPPED, 'Therapy Stopped'),
    (ResolutionReason.CLINICAL_JUSTIFICATION, 'Clinical Justification'),
    (ResolutionReason.DISCUSSED_WITH_TEAM, 'Discussed with Team'),
    (ResolutionReason.MESSAGED_TEAM, 'Messaged Team'),
    (ResolutionReason.ESCALATED_TO_ATTENDING, 'Escalated to Attending'),
    (ResolutionReason.NO_ACTION_NEEDED, 'No Action Needed'),
    (ResolutionReason.FALSE_POSITIVE, 'False Positive'),
    (ResolutionReason.OTHER, 'Other'),
]

ACTIVE_STATUSES = [
    CandidateStatus.PENDING,
    CandidateStatus.ALERTED,
]

ABX_ALERT_TYPES = [
    AlertType.ABX_NO_INDICATION,
    AlertType.ABX_NEVER_APPROPRIATE,
    AlertType.ABX_OFF_GUIDELINE,
]


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
@physician_or_higher_required
def dashboard(request):
    """Indication monitoring dashboard with pending queue and statistics."""

    candidates = IndicationCandidate.objects.filter(
        status__in=ACTIVE_STATUSES,
    )

    # Apply filters
    category = request.GET.get('category')
    if category:
        candidates = candidates.filter(syndrome_category=category)

    agent_cat = request.GET.get('agent_category')
    if agent_cat:
        candidates = candidates.filter(cchmc_agent_category=agent_cat)

    medication = request.GET.get('medication')
    if medication:
        candidates = candidates.filter(medication_name=medication)

    candidates = candidates.order_by('-created_at')

    # Stats
    all_active = IndicationCandidate.objects.filter(status__in=ACTIVE_STATUSES)

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    reviewed_today = IndicationReview.objects.filter(
        reviewed_at__gte=today_start,
    ).count()

    red_flag_count = all_active.filter(
        indication_not_documented=True,
    ).count() + all_active.filter(
        likely_viral=True,
    ).count() + all_active.filter(
        never_appropriate=True,
    ).count() + all_active.filter(
        asymptomatic_bacteriuria=True,
    ).count()

    off_guideline_count = all_active.filter(
        cchmc_agent_category=AgentCategoryChoice.OFF_GUIDELINE,
    ).count()

    stats = {
        'pending_count': all_active.count(),
        'red_flag_count': red_flag_count,
        'off_guideline_count': off_guideline_count,
        'reviewed_today': reviewed_today,
    }

    # Build filter options
    categories = sorted(set(
        all_active.exclude(syndrome_category='').values_list('syndrome_category', flat=True)
    ))
    medications = sorted(set(
        all_active.values_list('medication_name', flat=True)
    ))

    context = {
        'candidates': candidates,
        'stats': stats,
        'categories': categories,
        'medications': medications,
        'current_filters': {
            'category': category,
            'agent_category': agent_cat,
            'medication': medication,
        },
    }

    return render(request, 'abx_indications/dashboard.html', context)


@login_required
@physician_or_higher_required
def candidate_detail(request, pk):
    """Show candidate detail with extraction results and review form."""

    candidate = get_object_or_404(
        IndicationCandidate.objects.prefetch_related('reviews', 'llm_calls'),
        id=pk,
    )

    reviews = candidate.reviews.order_by('-reviewed_at')
    llm_calls = candidate.llm_calls.order_by('-created_at')
    audit_log = []
    if candidate.alert:
        audit_log = candidate.alert.audit_log.order_by('-performed_at')

    # Get syndrome choices for correction dropdown
    from .logic.taxonomy import INDICATION_TAXONOMY
    syndrome_choices = [
        (key, mapping.display_name, mapping.category.value)
        for key, mapping in INDICATION_TAXONOMY.items()
    ]

    context = {
        'candidate': candidate,
        'reviews': reviews,
        'llm_calls': llm_calls,
        'audit_log': audit_log,
        'resolution_reasons': INDICATION_RESOLUTION_REASONS,
        'syndrome_choices': syndrome_choices,
        'syndrome_decisions': SyndromeDecision.choices,
        'agent_decisions': AgentDecision.choices,
    }

    return render(request, 'abx_indications/detail.html', context)


@login_required
@physician_or_higher_required
def history(request):
    """Show reviewed indication candidates."""

    candidates = IndicationCandidate.objects.filter(
        status__in=[CandidateStatus.REVIEWED, CandidateStatus.AUTO_ACCEPTED],
    ).prefetch_related('reviews')

    # Filters
    category = request.GET.get('category')
    if category:
        candidates = candidates.filter(syndrome_category=category)

    agent_decision = request.GET.get('agent_decision')
    if agent_decision:
        candidates = candidates.filter(reviews__agent_decision=agent_decision)

    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    candidates = candidates.filter(created_at__gte=start_date)

    candidates = candidates.order_by('-created_at')

    context = {
        'candidates': candidates,
        'days': days,
        'current_filters': {
            'category': category,
            'agent_decision': agent_decision,
            'days': days,
        },
    }

    return render(request, 'abx_indications/history.html', context)


@login_required
@physician_or_higher_required
def help_page(request):
    """Help page with taxonomy reference and workflow guide."""
    from .logic.taxonomy import INDICATION_TAXONOMY, IndicationCategory

    # Group syndromes by category
    by_category = {}
    for key, mapping in INDICATION_TAXONOMY.items():
        cat = mapping.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            'id': mapping.indication_id,
            'name': mapping.display_name,
            'never_appropriate': mapping.never_appropriate,
            'has_guidelines': bool(mapping.guideline_disease_ids),
            'notes': mapping.notes,
        })

    context = {
        'taxonomy_by_category': by_category,
        'categories': [(c.value, c.name.replace('_', ' ').title()) for c in IndicationCategory],
    }

    return render(request, 'abx_indications/help.html', context)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_stats(request):
    """Get indication monitoring statistics (JSON)."""
    from .services import IndicationMonitorService

    service = IndicationMonitorService()
    stats = service.get_stats()

    return JsonResponse({'success': True, 'stats': stats})


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_review(request, pk):
    """Submit a review for an indication candidate."""

    candidate = get_object_or_404(IndicationCandidate, id=pk)

    syndrome_decision = request.POST.get('syndrome_decision')
    if not syndrome_decision:
        return JsonResponse({'success': False, 'error': 'Syndrome decision required'}, status=400)

    confirmed_syndrome = request.POST.get('confirmed_syndrome', '')
    confirmed_syndrome_display = request.POST.get('confirmed_syndrome_display', '')
    agent_decision = request.POST.get('agent_decision', '')
    agent_notes = request.POST.get('agent_notes', '')
    is_override = request.POST.get('is_override') == 'true'
    notes = request.POST.get('notes', '')

    try:
        review = IndicationReview.objects.create(
            candidate=candidate,
            reviewer=request.user,
            syndrome_decision=syndrome_decision,
            confirmed_syndrome=confirmed_syndrome,
            confirmed_syndrome_display=confirmed_syndrome_display,
            agent_decision=agent_decision,
            agent_notes=agent_notes,
            is_override=is_override,
            notes=notes,
        )

        candidate.status = CandidateStatus.REVIEWED
        candidate.save(update_fields=['status'])

        # If there's an associated alert, resolve it
        if candidate.alert and candidate.alert.status != AlertStatus.RESOLVED:
            ip_address = request.META.get('REMOTE_ADDR')
            candidate.alert.resolve(
                request.user,
                ResolutionReason.ACCEPTED,
                notes=f"Reviewed: {review.get_syndrome_decision_display()}",
                ip_address=ip_address,
            )

        return JsonResponse({
            'success': True,
            'message': 'Review submitted',
            'candidate_id': str(candidate.id),
            'status': candidate.status,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_acknowledge(request, pk):
    """Acknowledge an indication alert."""

    candidate = get_object_or_404(IndicationCandidate, id=pk)
    if not candidate.alert:
        return JsonResponse({'success': False, 'error': 'No alert associated'}, status=400)

    ip_address = request.META.get('REMOTE_ADDR')

    try:
        candidate.alert.acknowledge(request.user, ip_address=ip_address)
        return JsonResponse({
            'success': True,
            'message': 'Alert acknowledged',
            'candidate_id': str(candidate.id),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_resolve(request, pk):
    """Resolve an indication alert."""

    candidate = get_object_or_404(IndicationCandidate, id=pk)
    if not candidate.alert:
        return JsonResponse({'success': False, 'error': 'No alert associated'}, status=400)

    reason = request.POST.get('reason')
    notes = request.POST.get('notes', '')
    ip_address = request.META.get('REMOTE_ADDR')

    if not reason:
        return JsonResponse({'success': False, 'error': 'Resolution reason required'}, status=400)

    try:
        candidate.alert.resolve(request.user, reason, notes, ip_address=ip_address)
        return JsonResponse({
            'success': True,
            'message': 'Alert resolved',
            'candidate_id': str(candidate.id),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_add_note(request, pk):
    """Add a note to an indication candidate's alert."""

    candidate = get_object_or_404(IndicationCandidate, id=pk)
    if not candidate.alert:
        return JsonResponse({'success': False, 'error': 'No alert associated'}, status=400)

    note_text = request.POST.get('note')
    if not note_text:
        return JsonResponse({'success': False, 'error': 'Note text required'}, status=400)

    ip_address = request.META.get('REMOTE_ADDR')

    try:
        if not candidate.alert.details:
            candidate.alert.details = {}

        if 'notes' not in candidate.alert.details:
            candidate.alert.details['notes'] = []

        candidate.alert.details['notes'].append({
            'user': request.user.username,
            'timestamp': timezone.now().isoformat(),
            'text': note_text,
        })

        candidate.alert.save(update_fields=['details'])

        candidate.alert.create_audit_entry(
            action='note_added',
            user=request.user,
            ip_address=ip_address,
            extra_details={'note': note_text},
        )

        return JsonResponse({
            'success': True,
            'message': 'Note added',
            'candidate_id': str(candidate.id),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ============================================================================
# CSV EXPORT
# ============================================================================

def _generate_csv_rows(candidates, include_review=False):
    """Generate CSV rows from candidate queryset."""
    output = StringIO()
    writer = csv.writer(output)

    headers = [
        'Candidate ID', 'Patient MRN', 'Patient Name', 'Location',
        'Medication', 'Syndrome', 'Confidence', 'Category',
        'Agent Category', 'Red Flags', 'Status', 'Created At',
    ]
    if include_review:
        headers.extend(['Review Decision', 'Agent Decision', 'Reviewed By', 'Reviewed At'])

    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for candidate in candidates:
        red_flags = []
        if candidate.indication_not_documented:
            red_flags.append('No indication')
        if candidate.likely_viral:
            red_flags.append('Likely viral')
        if candidate.never_appropriate:
            red_flags.append('Never appropriate')
        if candidate.asymptomatic_bacteriuria:
            red_flags.append('ASB')

        row = [
            str(candidate.id),
            candidate.patient_mrn,
            candidate.patient_name,
            candidate.location,
            candidate.medication_name,
            candidate.clinical_syndrome_display,
            candidate.syndrome_confidence,
            candidate.syndrome_category,
            candidate.cchmc_agent_category,
            '; '.join(red_flags) if red_flags else '',
            candidate.status,
            candidate.created_at.strftime('%Y-%m-%d %H:%M:%S') if candidate.created_at else '',
        ]

        if include_review:
            review = candidate.latest_review
            if review:
                row.extend([
                    review.get_syndrome_decision_display(),
                    review.get_agent_decision_display() if review.agent_decision else '',
                    review.reviewer.username if review.reviewer else 'System',
                    review.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if review.reviewed_at else '',
                ])
            else:
                row.extend(['', '', '', ''])

        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


@login_required
@physician_or_higher_required
def api_export(request):
    """Export indication candidates as CSV."""

    export_type = request.GET.get('type', 'active')

    if export_type == 'history':
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        candidates = IndicationCandidate.objects.filter(
            status__in=[CandidateStatus.REVIEWED, CandidateStatus.AUTO_ACCEPTED],
            created_at__gte=start_date,
        ).prefetch_related('reviews').order_by('-created_at')
        filename = 'abx_indications_history.csv'
        include_review = True
    else:
        candidates = IndicationCandidate.objects.filter(
            status__in=ACTIVE_STATUSES,
        ).order_by('-created_at')
        filename = 'abx_indications_active.csv'
        include_review = False

    response = StreamingHttpResponse(
        _generate_csv_rows(candidates, include_review=include_review),
        content_type='text/csv',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
