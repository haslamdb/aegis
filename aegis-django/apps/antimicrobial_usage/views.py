"""
Antimicrobial Usage Alerts - Views

Dashboard views and API endpoints for broad-spectrum antibiotic duration monitoring.
All data comes from the unified Alert model filtered by BROAD_SPECTRUM_USAGE alert type.
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


USAGE_RESOLUTION_REASONS = [
    (ResolutionReason.THERAPY_CHANGED, 'Therapy Changed / De-escalated'),
    (ResolutionReason.THERAPY_STOPPED, 'Therapy Stopped'),
    (ResolutionReason.CLINICAL_JUSTIFICATION, 'Clinical Justification'),
    (ResolutionReason.DISCUSSED_WITH_TEAM, 'Discussed with Team'),
    (ResolutionReason.MESSAGED_TEAM, 'Messaged Team'),
    (ResolutionReason.CULTURE_PENDING, 'Culture Pending'),
    (ResolutionReason.ESCALATED_TO_ATTENDING, 'Escalated to Attending'),
    (ResolutionReason.NO_ACTION_NEEDED, 'No Action Needed'),
    (ResolutionReason.PATIENT_DISCHARGED, 'Patient Discharged'),
    (ResolutionReason.FALSE_POSITIVE, 'False Positive'),
    (ResolutionReason.OTHER, 'Other'),
]

ACTIVE_STATUSES = [
    AlertStatus.PENDING,
    AlertStatus.SENT,
    AlertStatus.ACKNOWLEDGED,
    AlertStatus.IN_PROGRESS,
    AlertStatus.SNOOZED,
]


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
@physician_or_higher_required
def dashboard(request):
    """Antimicrobial usage dashboard with active alerts and statistics."""

    alerts = Alert.objects.filter(
        alert_type=AlertType.BROAD_SPECTRUM_USAGE,
        status__in=ACTIVE_STATUSES,
    )

    # Apply severity filter
    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    # Apply medication filter
    medication = request.GET.get('medication')
    if medication:
        alerts = alerts.filter(details__medication_name=medication)

    # Sort: severity desc, then created_at desc
    alerts = alerts.order_by('-severity', '-created_at')

    # Get all active (unfiltered) for stats
    all_active = Alert.objects.filter(
        alert_type=AlertType.BROAD_SPECTRUM_USAGE,
        status__in=ACTIVE_STATUSES,
    )

    # Resolved today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_today_count = Alert.objects.filter(
        alert_type=AlertType.BROAD_SPECTRUM_USAGE,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=today_start,
    ).count()

    stats = {
        'active_count': all_active.count(),
        'critical_count': all_active.filter(severity=AlertSeverity.CRITICAL).count(),
        'high_count': all_active.filter(severity=AlertSeverity.HIGH).count(),
        'resolved_today': resolved_today_count,
    }

    # Build unique medication list for filter dropdown
    med_list = set()
    for alert in all_active:
        if alert.details and alert.details.get('medication_name'):
            med_list.add(alert.details['medication_name'])
    med_list = sorted(med_list)

    context = {
        'alerts': alerts,
        'stats': stats,
        'med_list': med_list,
        'current_filters': {
            'severity': severity,
            'medication': medication,
        },
    }

    return render(request, 'antimicrobial_usage/dashboard.html', context)


@login_required
@physician_or_higher_required
def alert_detail(request, alert_id):
    """Show detailed alert view with medication info and duration."""

    alert = get_object_or_404(
        Alert.objects.select_related('resolved_by', 'acknowledged_by'),
        id=alert_id,
    )

    audit_log = alert.audit_log.order_by('-performed_at')
    details = alert.details or {}

    # Calculate duration progress for visual bar
    threshold = details.get('threshold_hours', 72)
    duration = details.get('duration_hours', 0)
    # Cap at 200% for display
    duration_pct = min(duration / threshold * 100, 200) if threshold else 0
    threshold_pct = 100  # threshold is always at 100% mark

    context = {
        'alert': alert,
        'audit_log': audit_log,
        'resolution_reasons': USAGE_RESOLUTION_REASONS,
        'details': details,
        'duration_pct': duration_pct,
        'threshold_pct': threshold_pct,
        'duration_days': round(duration / 24, 1) if duration else 0,
    }

    return render(request, 'antimicrobial_usage/detail.html', context)


@login_required
@physician_or_higher_required
def history(request):
    """Show resolved antimicrobial usage alerts."""

    alerts = Alert.objects.filter(
        alert_type=AlertType.BROAD_SPECTRUM_USAGE,
        status=AlertStatus.RESOLVED,
    ).select_related('resolved_by')

    # Apply filters
    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    resolution = request.GET.get('resolution')
    if resolution:
        alerts = alerts.filter(resolution_reason=resolution)

    medication = request.GET.get('medication')
    if medication:
        alerts = alerts.filter(details__medication_name=medication)

    # Date range filter (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    alerts = alerts.filter(resolved_at__gte=start_date)

    alerts = alerts.order_by('-resolved_at')

    context = {
        'alerts': alerts,
        'resolution_reasons': USAGE_RESOLUTION_REASONS,
        'days': days,
        'current_filters': {
            'severity': severity,
            'resolution': resolution,
            'medication': medication,
            'days': days,
        },
    }

    return render(request, 'antimicrobial_usage/history.html', context)


@login_required
@physician_or_higher_required
def help_page(request):
    """Help and documentation page for antimicrobial usage monitoring."""
    return render(request, 'antimicrobial_usage/help.html')


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_stats(request):
    """Get antimicrobial usage statistics (JSON)."""

    active = Alert.objects.filter(
        alert_type=AlertType.BROAD_SPECTRUM_USAGE,
        status__in=ACTIVE_STATUSES,
    )

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_today = Alert.objects.filter(
        alert_type=AlertType.BROAD_SPECTRUM_USAGE,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=today_start,
    ).count()

    # By medication
    by_medication = {}
    for alert in active:
        med_name = (alert.details or {}).get('medication_name', 'Unknown')
        by_medication[med_name] = by_medication.get(med_name, 0) + 1

    data = {
        'active_count': active.count(),
        'by_severity': {
            'critical': active.filter(severity=AlertSeverity.CRITICAL).count(),
            'high': active.filter(severity=AlertSeverity.HIGH).count(),
        },
        'by_medication': by_medication,
        'resolved_today': resolved_today,
    }

    return JsonResponse({'success': True, 'stats': data})


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_acknowledge(request, alert_id):
    """Acknowledge an antimicrobial usage alert."""

    alert = get_object_or_404(Alert, id=alert_id)
    ip_address = request.META.get('REMOTE_ADDR')

    try:
        alert.acknowledge(request.user, ip_address=ip_address)
        return JsonResponse({
            'success': True,
            'message': 'Alert acknowledged',
            'alert_id': str(alert.id),
            'status': alert.status,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_resolve(request, alert_id):
    """Resolve an antimicrobial usage alert with documented reason."""

    alert = get_object_or_404(Alert, id=alert_id)
    ip_address = request.META.get('REMOTE_ADDR')

    reason = request.POST.get('reason')
    notes = request.POST.get('notes', '')

    if not reason:
        return JsonResponse({
            'success': False,
            'error': 'Resolution reason required',
        }, status=400)

    try:
        alert.resolve(request.user, reason, notes, ip_address=ip_address)
        return JsonResponse({
            'success': True,
            'message': 'Alert resolved',
            'alert_id': str(alert.id),
            'status': alert.status,
            'resolution_reason': alert.resolution_reason,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_add_note(request, alert_id):
    """Add a note to an antimicrobial usage alert."""

    alert = get_object_or_404(Alert, id=alert_id)
    ip_address = request.META.get('REMOTE_ADDR')

    note_text = request.POST.get('note')
    if not note_text:
        return JsonResponse({
            'success': False,
            'error': 'Note text required',
        }, status=400)

    try:
        if not alert.details:
            alert.details = {}

        if 'notes' not in alert.details:
            alert.details['notes'] = []

        alert.details['notes'].append({
            'user': request.user.username,
            'timestamp': timezone.now().isoformat(),
            'text': note_text,
        })

        alert.save(update_fields=['details'])

        alert.create_audit_entry(
            action='note_added',
            user=request.user,
            ip_address=ip_address,
            extra_details={'note': note_text},
        )

        return JsonResponse({
            'success': True,
            'message': 'Note added',
            'alert_id': str(alert.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)


# ============================================================================
# CSV EXPORT
# ============================================================================

def _generate_csv_rows(alerts, include_resolution=False):
    """Generate CSV rows from alert queryset."""
    output = StringIO()
    writer = csv.writer(output)

    headers = [
        'Alert ID', 'Severity', 'Status',
        'Patient MRN', 'Patient Name', 'Location',
        'Medication', 'Duration (hours)', 'Threshold (hours)',
        'Dose', 'Route', 'Start Date',
        'Recommendation', 'Created At',
    ]
    if include_resolution:
        headers.extend(['Resolved At', 'Resolution Reason', 'Resolved By', 'Resolution Notes'])

    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for alert in alerts:
        details = alert.details or {}
        row = [
            str(alert.id),
            alert.severity,
            alert.status,
            alert.patient_mrn or '',
            alert.patient_name or '',
            alert.patient_location or '',
            details.get('medication_name', ''),
            details.get('duration_hours', ''),
            details.get('threshold_hours', ''),
            details.get('dose', ''),
            details.get('route', ''),
            details.get('start_date', ''),
            details.get('recommendation', ''),
            alert.created_at.strftime('%Y-%m-%d %H:%M:%S') if alert.created_at else '',
        ]
        if include_resolution:
            row.extend([
                alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else '',
                alert.get_resolution_reason_display() if alert.resolution_reason else '',
                alert.resolved_by.username if alert.resolved_by else '',
                alert.resolution_notes or '',
            ])

        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


@login_required
@physician_or_higher_required
def api_export(request):
    """Export antimicrobial usage alerts as CSV."""

    export_type = request.GET.get('type', 'active')

    if export_type == 'history':
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        alerts = Alert.objects.filter(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            status=AlertStatus.RESOLVED,
            resolved_at__gte=start_date,
        ).select_related('resolved_by').order_by('-resolved_at')
        filename = 'antimicrobial_usage_history.csv'
        include_resolution = True
    else:
        alerts = Alert.objects.filter(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            status__in=ACTIVE_STATUSES,
        ).order_by('-severity', '-created_at')
        filename = 'antimicrobial_usage_active.csv'
        include_resolution = False

    response = StreamingHttpResponse(
        _generate_csv_rows(alerts, include_resolution=include_resolution),
        content_type='text/csv',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
