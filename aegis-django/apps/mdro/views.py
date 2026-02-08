"""
MDRO Surveillance Dashboard - Views

Dashboard views and API endpoints for MDRO case tracking and review.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from apps.authentication.decorators import physician_or_higher_required
from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus

from .models import (
    MDROCase, MDROReview, MDROTypeChoices, TransmissionStatusChoices,
    MDRO_TYPE_FULL_NAMES,
)


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
@physician_or_higher_required
def dashboard(request):
    """MDRO Surveillance dashboard with overview stats and recent cases."""

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)

    recent_qs = MDROCase.objects.filter(culture_date__gte=thirty_days_ago)

    # Stats
    stats = {
        'total_cases': recent_qs.count(),
        'healthcare_onset': recent_qs.filter(
            transmission_status=TransmissionStatusChoices.HEALTHCARE
        ).count(),
        'community_onset': recent_qs.filter(
            transmission_status=TransmissionStatusChoices.COMMUNITY
        ).count(),
    }

    # Cases by MDRO type
    by_type_qs = recent_qs.values('mdro_type').annotate(
        count=Count('id')
    ).order_by('-count')
    stats['by_type'] = {row['mdro_type']: row['count'] for row in by_type_qs}

    # Cases by unit
    by_unit_qs = recent_qs.exclude(unit='').values('unit').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    stats['by_unit'] = {row['unit']: row['count'] for row in by_unit_qs}

    # Recent cases (last 7 days)
    recent_cases = MDROCase.objects.filter(
        culture_date__gte=seven_days_ago
    ).order_by('-culture_date')[:10]

    context = {
        'stats': stats,
        'recent_cases': recent_cases,
        'mdro_type_names': MDRO_TYPE_FULL_NAMES,
    }

    return render(request, 'mdro/dashboard.html', context)


@login_required
@physician_or_higher_required
def cases_list(request):
    """List MDRO cases with filtering."""

    cases = MDROCase.objects.all()

    # Filter by MDRO type
    mdro_type = request.GET.get('type', '')
    if mdro_type:
        cases = cases.filter(mdro_type=mdro_type)

    # Filter by unit
    unit = request.GET.get('unit', '')
    if unit:
        cases = cases.filter(unit=unit)

    # Filter by time period
    days = int(request.GET.get('days', 30))
    cutoff = timezone.now() - timedelta(days=days)
    cases = cases.filter(culture_date__gte=cutoff)

    # Compute stats for the filtered set
    stats = {
        'healthcare_onset': cases.filter(
            transmission_status=TransmissionStatusChoices.HEALTHCARE
        ).count(),
        'community_onset': cases.filter(
            transmission_status=TransmissionStatusChoices.COMMUNITY
        ).count(),
    }

    # Get available units for filter dropdown
    units = MDROCase.objects.exclude(unit='').values_list(
        'unit', flat=True
    ).distinct().order_by('unit')

    # Get available MDRO types
    mdro_types = [choice[0] for choice in MDROTypeChoices.choices]

    context = {
        'cases': cases.order_by('-culture_date'),
        'stats': stats,
        'mdro_types': mdro_types,
        'units': units,
        'current_type': mdro_type,
        'current_unit': unit,
        'current_days': days,
    }

    return render(request, 'mdro/cases.html', context)


@login_required
@physician_or_higher_required
def case_detail(request, case_id):
    """Show detailed MDRO case view with susceptibility data and review form."""

    case = get_object_or_404(MDROCase, id=case_id)

    # Get prior cases for this patient (excluding current case)
    prior_cases = MDROCase.objects.filter(
        patient_id=case.patient_id
    ).exclude(id=case.id).order_by('-culture_date')

    # Get reviews for this case
    reviews = case.reviews.all()

    context = {
        'case': case,
        'prior_cases': prior_cases,
        'reviews': reviews,
        'mdro_type_names': MDRO_TYPE_FULL_NAMES,
    }

    return render(request, 'mdro/case_detail.html', context)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def review_case(request, case_id):
    """Submit a review for an MDRO case."""

    case = get_object_or_404(MDROCase, id=case_id)

    reviewer = request.POST.get('reviewer', '').strip()
    decision = request.POST.get('decision', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not reviewer:
        return JsonResponse({
            'success': False,
            'error': 'Reviewer name is required'
        }, status=400)

    if not decision:
        return JsonResponse({
            'success': False,
            'error': 'Decision is required'
        }, status=400)

    # Create review record
    MDROReview.objects.create(
        case=case,
        reviewer=reviewer,
        decision=decision,
        notes=notes,
    )

    # Update case review status
    case.reviewed_by = request.user
    case.reviewed_at = timezone.now()
    if notes:
        case.notes = notes
    case.save(update_fields=['reviewed_by', 'reviewed_at', 'notes'])

    return JsonResponse({
        'success': True,
        'message': 'Review submitted successfully',
        'case_id': str(case.id),
        'decision': decision,
    })


@login_required
@physician_or_higher_required
def analytics(request):
    """Analytics and trend charts."""

    days = int(request.GET.get('days', 30))
    cutoff = timezone.now() - timedelta(days=days)

    cases = MDROCase.objects.filter(culture_date__gte=cutoff)

    # Overall stats
    stats = {
        'total_cases': cases.count(),
        'healthcare_onset': cases.filter(
            transmission_status=TransmissionStatusChoices.HEALTHCARE
        ).count(),
        'community_onset': cases.filter(
            transmission_status=TransmissionStatusChoices.COMMUNITY
        ).count(),
    }

    # By type
    by_type_qs = cases.values('mdro_type').annotate(
        count=Count('id')
    ).order_by('-count')
    stats['by_type'] = {row['mdro_type']: row['count'] for row in by_type_qs}

    # By unit
    by_unit_qs = cases.exclude(unit='').values('unit').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    stats['by_unit'] = {row['unit']: row['count'] for row in by_unit_qs}

    # Trend data: daily counts by type
    from django.db.models.functions import TruncDate
    trend_qs = cases.annotate(
        date=TruncDate('culture_date')
    ).values('date', 'mdro_type').annotate(
        count=Count('id')
    ).order_by('date')

    trend_data = list(trend_qs)
    for row in trend_data:
        row['date'] = row['date'].strftime('%Y-%m-%d') if row['date'] else ''

    mdro_types = [choice[0] for choice in MDROTypeChoices.choices]

    context = {
        'stats': stats,
        'trend_data': trend_data,
        'mdro_types': mdro_types,
        'current_days': days,
    }

    return render(request, 'mdro/analytics.html', context)


@login_required
@physician_or_higher_required
def help_page(request):
    """Help and documentation page."""
    return render(request, 'mdro/help.html')


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_stats(request):
    """Get MDRO surveillance statistics (API endpoint)."""

    days = int(request.GET.get('days', 30))
    cutoff = timezone.now() - timedelta(days=days)

    cases = MDROCase.objects.filter(culture_date__gte=cutoff)

    total = cases.count()
    healthcare = cases.filter(
        transmission_status=TransmissionStatusChoices.HEALTHCARE
    ).count()
    community = cases.filter(
        transmission_status=TransmissionStatusChoices.COMMUNITY
    ).count()

    by_type = {}
    for row in cases.values('mdro_type').annotate(count=Count('id')):
        by_type[row['mdro_type']] = row['count']

    by_unit = {}
    for row in cases.exclude(unit='').values('unit').annotate(count=Count('id')).order_by('-count')[:10]:
        by_unit[row['unit']] = row['count']

    return JsonResponse({
        'success': True,
        'stats': {
            'days': days,
            'total_cases': total,
            'healthcare_onset': healthcare,
            'community_onset': community,
            'by_type': by_type,
            'by_unit': by_unit,
        }
    })


@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_export(request):
    """Export MDRO cases as JSON (API endpoint)."""

    days = int(request.GET.get('days', 14))
    cutoff = timezone.now() - timedelta(days=days)

    cases = MDROCase.objects.filter(culture_date__gte=cutoff).order_by('-culture_date')

    data = [{
        'id': str(case.id),
        'patient_id': case.patient_id,
        'patient_mrn': case.patient_mrn,
        'culture_id': case.culture_id,
        'culture_date': case.culture_date.isoformat(),
        'organism': case.organism,
        'mdro_type': case.mdro_type,
        'resistant_antibiotics': case.resistant_antibiotics,
        'susceptibilities': case.susceptibilities,
        'classification_reason': case.classification_reason,
        'unit': case.unit,
        'location': case.location,
        'transmission_status': case.transmission_status,
        'days_since_admission': case.days_since_admission,
        'is_new': case.is_new,
        'prior_history': case.prior_history,
        'created_at': case.created_at.isoformat(),
    } for case in cases]

    return JsonResponse({
        'success': True,
        'days': days,
        'count': len(data),
        'cases': data,
    })
