"""
Dosing Verification Dashboard - Views

Dashboard views and API endpoints for dosing verification alerts.
All data comes from the unified Alert model filtered by DOSING_* alert types.
"""

import csv
from io import StringIO

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta

from apps.authentication.decorators import physician_or_higher_required
from apps.alerts.models import (
    Alert, AlertStatus, AlertSeverity, AlertType, ResolutionReason,
)
from .alert_models import DoseFlagType


# All dosing-related alert types
DOSING_ALERT_TYPES = [
    AlertType.DOSING_ALLERGY,
    AlertType.DOSING_RENAL,
    AlertType.DOSING_AGE,
    AlertType.DOSING_WEIGHT,
    AlertType.DOSING_INTERACTION,
    AlertType.DOSING_ROUTE,
    AlertType.DOSING_INDICATION,
    AlertType.DOSING_DURATION,
    AlertType.DOSING_EXTENDED_INFUSION,
]

# Map DoseFlagType values to AlertType values
FLAG_TYPE_TO_ALERT_TYPE = {
    DoseFlagType.ALLERGY_CONTRAINDICATED.value: AlertType.DOSING_ALLERGY,
    DoseFlagType.ALLERGY_CROSS_REACTIVITY.value: AlertType.DOSING_ALLERGY,
    DoseFlagType.NO_RENAL_ADJUSTMENT.value: AlertType.DOSING_RENAL,
    DoseFlagType.EXCESSIVE_RENAL_ADJUSTMENT.value: AlertType.DOSING_RENAL,
    DoseFlagType.AGE_DOSE_MISMATCH.value: AlertType.DOSING_AGE,
    DoseFlagType.WEIGHT_DOSE_MISMATCH.value: AlertType.DOSING_WEIGHT,
    DoseFlagType.MAX_DOSE_EXCEEDED.value: AlertType.DOSING_WEIGHT,
    DoseFlagType.DRUG_INTERACTION.value: AlertType.DOSING_INTERACTION,
    DoseFlagType.WRONG_ROUTE.value: AlertType.DOSING_ROUTE,
    DoseFlagType.SUBTHERAPEUTIC_DOSE.value: AlertType.DOSING_INDICATION,
    DoseFlagType.SUPRATHERAPEUTIC_DOSE.value: AlertType.DOSING_INDICATION,
    DoseFlagType.WRONG_INTERVAL.value: AlertType.DOSING_INDICATION,
    DoseFlagType.CONTRAINDICATED.value: AlertType.DOSING_INDICATION,
    DoseFlagType.DURATION_EXCESSIVE.value: AlertType.DOSING_DURATION,
    DoseFlagType.DURATION_INSUFFICIENT.value: AlertType.DOSING_DURATION,
    DoseFlagType.EXTENDED_INFUSION_CANDIDATE.value: AlertType.DOSING_EXTENDED_INFUSION,
}

# Dosing-relevant resolution reasons for the resolve form
DOSING_RESOLUTION_REASONS = [
    (ResolutionReason.DOSE_ADJUSTED, 'Dose Adjusted'),
    (ResolutionReason.INTERVAL_ADJUSTED, 'Interval Adjusted'),
    (ResolutionReason.ROUTE_CHANGED, 'Route Changed'),
    (ResolutionReason.THERAPY_CHANGED, 'Therapy Changed'),
    (ResolutionReason.THERAPY_STOPPED, 'Therapy Stopped'),
    (ResolutionReason.CLINICAL_JUSTIFICATION, 'Clinical Justification'),
    (ResolutionReason.DISCUSSED_WITH_TEAM, 'Discussed with Team'),
    (ResolutionReason.MESSAGED_TEAM, 'Messaged Team'),
    (ResolutionReason.ESCALATED_TO_ATTENDING, 'Escalated to Attending'),
    (ResolutionReason.NO_ACTION_NEEDED, 'No Action Needed'),
    (ResolutionReason.FALSE_POSITIVE, 'False Positive'),
    (ResolutionReason.PATIENT_DISCHARGED, 'Patient Discharged'),
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
    """Dosing Verification dashboard with active alerts and statistics."""

    # Get active dosing alerts
    alerts = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status__in=ACTIVE_STATUSES,
    )

    # Apply severity filter
    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    # Apply alert type filter (e.g. dosing_renal, dosing_allergy)
    alert_type = request.GET.get('type')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)

    # Apply flag type filter (from details JSONField)
    flag_type = request.GET.get('flag_type')
    if flag_type:
        alerts = alerts.filter(details__flag_type=flag_type)

    # Apply drug filter
    drug = request.GET.get('drug')
    if drug:
        alerts = alerts.filter(details__drug__icontains=drug)

    # Sort: severity desc, then created_at desc
    alerts = alerts.order_by('-severity', '-created_at')

    # Get all active (unfiltered) for stats
    all_active = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status__in=ACTIVE_STATUSES,
    )

    # Resolved today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_today_count = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=today_start,
    ).count()

    # Statistics
    stats = {
        'active_count': all_active.count(),
        'critical_count': all_active.filter(severity=AlertSeverity.CRITICAL).count(),
        'high_count': all_active.filter(severity=AlertSeverity.HIGH).count(),
        'resolved_today': resolved_today_count,
    }

    # Build unique drug list for filter dropdown
    drug_list = set()
    for alert in all_active:
        if alert.details and alert.details.get('drug'):
            drug_list.add(alert.details['drug'])
    drug_list = sorted(drug_list)

    context = {
        'alerts': alerts,
        'stats': stats,
        'drug_list': drug_list,
        'flag_type_options': DoseFlagType.all_options(),
        'dosing_alert_types': [(t.value, t.label) for t in DOSING_ALERT_TYPES],
        'current_filters': {
            'severity': severity,
            'type': alert_type,
            'flag_type': flag_type,
            'drug': drug,
        },
    }

    return render(request, 'dosing/dashboard.html', context)


@login_required
@physician_or_higher_required
def alert_detail(request, alert_id):
    """Show detailed dosing alert view with patient factors and dose comparison."""

    alert = get_object_or_404(
        Alert.objects.select_related('resolved_by', 'acknowledged_by'),
        id=alert_id,
    )

    # Get audit entries
    audit_log = alert.audit_log.order_by('-performed_at')

    # Extract structured data from details JSONField
    details = alert.details or {}
    patient_factors = details.get('patient_factors', {})
    assessment = details.get('assessment', {})
    all_flags = details.get('flags', [])

    # Add display names to flags
    for flag in all_flags:
        flag['flag_type_display'] = DoseFlagType.display_name(flag.get('flag_type', ''))

    context = {
        'alert': alert,
        'audit_log': audit_log,
        'resolution_reasons': DOSING_RESOLUTION_REASONS,
        'patient_factors': patient_factors,
        'assessment': assessment,
        'all_flags': all_flags,
        'details': details,
    }

    return render(request, 'dosing/detail.html', context)


@login_required
@physician_or_higher_required
def history(request):
    """Show resolved dosing alerts."""

    alerts = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status=AlertStatus.RESOLVED,
    ).select_related('resolved_by')

    # Apply filters
    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    resolution = request.GET.get('resolution')
    if resolution:
        alerts = alerts.filter(resolution_reason=resolution)

    drug = request.GET.get('drug')
    if drug:
        alerts = alerts.filter(details__drug__icontains=drug)

    # Date range filter (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    alerts = alerts.filter(resolved_at__gte=start_date)

    # Sort by resolved_at desc
    alerts = alerts.order_by('-resolved_at')

    context = {
        'alerts': alerts,
        'resolution_reasons': DOSING_RESOLUTION_REASONS,
        'days': days,
        'current_filters': {
            'severity': severity,
            'resolution': resolution,
            'drug': drug,
            'days': days,
        },
    }

    return render(request, 'dosing/history.html', context)


@login_required
@physician_or_higher_required
def reports(request):
    """Analytics and reporting dashboard for dosing verification."""

    # Date range (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Get dosing alerts in period
    dosing_alerts = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        created_at__gte=start_date,
    )

    total_alerts = dosing_alerts.count()

    # Group by severity
    by_severity = dosing_alerts.values('severity').annotate(
        count=Count('id')
    ).order_by('-severity')

    # Group by alert type
    by_type = dosing_alerts.values('alert_type').annotate(
        count=Count('id')
    ).order_by('-count')

    # Resolution reasons (for resolved alerts)
    resolved_alerts = dosing_alerts.filter(status=AlertStatus.RESOLVED)
    resolved_count = resolved_alerts.count()
    by_resolution = resolved_alerts.values('resolution_reason').annotate(
        count=Count('id')
    ).order_by('-count')

    # Clinical impact: count dose/interval/route adjustments
    dose_adjusted = resolved_alerts.filter(resolution_reason=ResolutionReason.DOSE_ADJUSTED).count()
    interval_adjusted = resolved_alerts.filter(resolution_reason=ResolutionReason.INTERVAL_ADJUSTED).count()
    route_changed = resolved_alerts.filter(resolution_reason=ResolutionReason.ROUTE_CHANGED).count()
    therapy_changed = resolved_alerts.filter(resolution_reason=ResolutionReason.THERAPY_CHANGED).count()
    action_count = dose_adjusted + interval_adjusted + route_changed + therapy_changed

    # Top flagged drugs from details JSONField
    drug_counts = {}
    for alert in dosing_alerts:
        if alert.details and alert.details.get('drug'):
            d = alert.details['drug']
            drug_counts[d] = drug_counts.get(d, 0) + 1
    top_drugs = sorted(drug_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    context = {
        'days': days,
        'total_alerts': total_alerts,
        'by_severity': by_severity,
        'by_type': by_type,
        'by_resolution': by_resolution,
        'resolved_count': resolved_count,
        'active_count': total_alerts - resolved_count,
        'dose_adjusted': dose_adjusted,
        'interval_adjusted': interval_adjusted,
        'route_changed': route_changed,
        'therapy_changed': therapy_changed,
        'action_count': action_count,
        'action_rate': round(action_count / resolved_count * 100, 1) if resolved_count > 0 else 0,
        'top_drugs': top_drugs,
    }

    return render(request, 'dosing/reports.html', context)


@login_required
@physician_or_higher_required
def help_page(request):
    """Help and documentation page for dosing verification."""
    return render(request, 'dosing/help.html')


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_stats(request):
    """Get dosing verification statistics (JSON)."""

    active = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status__in=ACTIVE_STATUSES,
    )

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_today = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=today_start,
    ).count()

    data = {
        'active_count': active.count(),
        'by_severity': {
            'critical': active.filter(severity=AlertSeverity.CRITICAL).count(),
            'high': active.filter(severity=AlertSeverity.HIGH).count(),
            'medium': active.filter(severity=AlertSeverity.MEDIUM).count(),
            'low': active.filter(severity=AlertSeverity.LOW).count(),
        },
        'resolved_today': resolved_today,
    }

    return JsonResponse({'success': True, 'stats': data})


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_acknowledge(request, alert_id):
    """Acknowledge a dosing alert."""

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
    """Resolve a dosing alert with documented reason."""

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
    """Add a note to a dosing alert."""

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
# CSV EXPORTS
# ============================================================================

def _generate_csv_rows(alerts, include_resolution=False):
    """Generate CSV rows from alert queryset."""
    output = StringIO()
    writer = csv.writer(output)

    headers = [
        'Alert ID', 'Alert Type', 'Severity', 'Status',
        'Patient MRN', 'Patient Name', 'Location',
        'Drug', 'Flag Type', 'Issue', 'Expected', 'Actual',
        'Rule Source', 'Created At',
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
            alert.get_alert_type_display(),
            alert.severity,
            alert.status,
            alert.patient_mrn or '',
            alert.patient_name or '',
            alert.patient_location or '',
            details.get('drug', ''),
            DoseFlagType.display_name(details.get('flag_type', '')),
            alert.summary,
            details.get('expected_dose', ''),
            details.get('actual_dose', ''),
            details.get('rule_source', ''),
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
def export_active_csv(request):
    """Export active dosing alerts as CSV."""

    alerts = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status__in=ACTIVE_STATUSES,
    ).order_by('-severity', '-created_at')

    response = StreamingHttpResponse(
        _generate_csv_rows(alerts, include_resolution=False),
        content_type='text/csv',
    )
    response['Content-Disposition'] = 'attachment; filename="dosing_active_alerts.csv"'
    return response


@login_required
@physician_or_higher_required
def export_history_csv(request):
    """Export resolved dosing alerts as CSV."""

    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    alerts = Alert.objects.filter(
        alert_type__in=DOSING_ALERT_TYPES,
        status=AlertStatus.RESOLVED,
        resolved_at__gte=start_date,
    ).select_related('resolved_by').order_by('-resolved_at')

    response = StreamingHttpResponse(
        _generate_csv_rows(alerts, include_resolution=True),
        content_type='text/csv',
    )
    response['Content-Disposition'] = 'attachment; filename="dosing_history_alerts.csv"'
    return response
