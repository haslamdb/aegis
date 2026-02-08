"""
Drug-Bug Mismatch Dashboard - Views

Dashboard views and API endpoints for drug-bug mismatch alerts.
All data comes from the unified Alert model filtered by alert_type=DRUG_BUG_MISMATCH.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count

from apps.authentication.decorators import physician_or_higher_required
from apps.alerts.models import (
    Alert, AlertStatus, AlertSeverity, AlertType, ResolutionReason,
)


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
@physician_or_higher_required
def dashboard(request):
    """Drug-Bug Mismatch dashboard with active alerts and statistics."""

    # Get active drug-bug mismatch alerts
    alerts = Alert.objects.filter(
        alert_type=AlertType.DRUG_BUG_MISMATCH,
        status__in=[
            AlertStatus.PENDING,
            AlertStatus.SENT,
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.IN_PROGRESS,
            AlertStatus.SNOOZED,
        ]
    )

    # Apply severity filter
    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    # Apply mismatch type filter (from details JSONField)
    mismatch_type = request.GET.get('mismatch_type')
    if mismatch_type:
        alerts = alerts.filter(details__mismatch_type=mismatch_type)

    # Sort: severity desc, then created_at desc
    alerts = alerts.order_by('-severity', '-created_at')

    # Get all active (unfiltered) for stats
    all_active = Alert.objects.filter(
        alert_type=AlertType.DRUG_BUG_MISMATCH,
        status__in=[
            AlertStatus.PENDING,
            AlertStatus.SENT,
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.IN_PROGRESS,
            AlertStatus.SNOOZED,
        ]
    )

    # Resolved today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_today_count = Alert.objects.filter(
        alert_type=AlertType.DRUG_BUG_MISMATCH,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=today_start,
    ).count()

    # Statistics
    stats = {
        'active_count': all_active.count(),
        'critical_count': all_active.filter(severity=AlertSeverity.HIGH).count(),
        'warning_count': all_active.filter(severity=AlertSeverity.MEDIUM).count(),
        'resolved_today': resolved_today_count,
    }

    # Mismatch type counts from details JSONField
    mismatch_counts = {'resistant': 0, 'intermediate': 0, 'no_coverage': 0}
    for alert in all_active:
        if alert.details:
            mt = alert.details.get('mismatch_type')
            if mt in mismatch_counts:
                mismatch_counts[mt] += 1

    context = {
        'alerts': alerts,
        'stats': stats,
        'mismatch_counts': mismatch_counts,
        'current_severity': severity,
        'current_mismatch_type': mismatch_type,
    }

    return render(request, 'drug_bug/dashboard.html', context)


@login_required
@physician_or_higher_required
def history(request):
    """Show resolved drug-bug mismatch alerts."""

    alerts = Alert.objects.filter(
        alert_type=AlertType.DRUG_BUG_MISMATCH,
        status=AlertStatus.RESOLVED,
    ).select_related('resolved_by')

    # Apply filters
    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    resolution = request.GET.get('resolution')
    if resolution:
        alerts = alerts.filter(resolution_reason=resolution)

    # Sort by resolved_at desc
    alerts = alerts.order_by('-resolved_at')

    context = {
        'alerts': alerts,
        'resolution_reasons': ResolutionReason.choices,
        'current_severity': severity,
        'current_resolution': resolution,
    }

    return render(request, 'drug_bug/history.html', context)


@login_required
@physician_or_higher_required
def help_page(request):
    """Drug-Bug Mismatch help page."""
    return render(request, 'drug_bug/help.html')


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_stats(request):
    """Get drug-bug mismatch statistics (JSON)."""

    # Active alerts
    active = Alert.objects.filter(
        alert_type=AlertType.DRUG_BUG_MISMATCH,
        status__in=[
            AlertStatus.PENDING,
            AlertStatus.SENT,
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.IN_PROGRESS,
            AlertStatus.SNOOZED,
        ]
    )

    # Resolved today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_today = Alert.objects.filter(
        alert_type=AlertType.DRUG_BUG_MISMATCH,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=today_start,
    ).count()

    # Mismatch type counts
    mismatch_counts = {'resistant': 0, 'intermediate': 0, 'no_coverage': 0}
    for alert in active:
        if alert.details:
            mt = alert.details.get('mismatch_type')
            if mt in mismatch_counts:
                mismatch_counts[mt] += 1

    data = {
        'active_count': active.count(),
        'by_severity': {
            'high': active.filter(severity=AlertSeverity.HIGH).count(),
            'medium': active.filter(severity=AlertSeverity.MEDIUM).count(),
            'low': active.filter(severity=AlertSeverity.LOW).count(),
        },
        'by_mismatch_type': mismatch_counts,
        'resolved_today': resolved_today,
    }

    return JsonResponse({'success': True, 'stats': data})


@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_export(request):
    """Export drug-bug mismatch alerts as JSON."""

    status_filter = request.GET.get('status', 'active')

    if status_filter == 'resolved':
        alerts = Alert.objects.filter(
            alert_type=AlertType.DRUG_BUG_MISMATCH,
            status=AlertStatus.RESOLVED,
        ).order_by('-resolved_at')
    else:
        alerts = Alert.objects.filter(
            alert_type=AlertType.DRUG_BUG_MISMATCH,
            status__in=[
                AlertStatus.PENDING,
                AlertStatus.SENT,
                AlertStatus.ACKNOWLEDGED,
                AlertStatus.IN_PROGRESS,
                AlertStatus.SNOOZED,
            ]
        ).order_by('-created_at')

    limit = int(request.GET.get('limit', 100))
    alerts = alerts[:limit]

    data = [{
        'id': str(alert.id),
        'severity': alert.severity,
        'status': alert.status,
        'patient_mrn': alert.patient_mrn,
        'patient_name': alert.patient_name,
        'title': alert.title,
        'summary': alert.summary,
        'details': alert.details,
        'created_at': alert.created_at.isoformat(),
        'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
        'resolution_reason': alert.resolution_reason,
    } for alert in alerts]

    return JsonResponse({
        'success': True,
        'count': len(data),
        'alerts': data,
    })
