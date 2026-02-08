"""
ASP Alerts Dashboard - Views

Dashboard views and API endpoints for managing ASP bacteremia alerts.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta

from apps.authentication.decorators import physician_or_higher_required
from apps.alerts.models import Alert, AlertStatus, AlertSeverity, AlertType


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
@physician_or_higher_required
def index(request):
    """Redirect to active alerts page"""
    return redirect('asp_alerts:active')


@login_required
@physician_or_higher_required
def active_alerts(request):
    """List active (non-resolved) alerts with filtering and sorting"""

    # Get base queryset - active alerts only
    alerts = Alert.objects.filter(
        alert_type__in=[
            AlertType.DRUG_BUG_MISMATCH,
            AlertType.CULTURE_NO_THERAPY,
            AlertType.BROAD_SPECTRUM_USAGE,
        ],
        status__in=[
            AlertStatus.PENDING,
            AlertStatus.SENT,
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.SNOOZED,
        ]
    ).select_related('created_by', 'assigned_to')

    # Apply filters
    alert_type = request.GET.get('type')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)

    mrn = request.GET.get('mrn')
    if mrn:
        alerts = alerts.filter(patient_mrn__icontains=mrn)

    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    # Apply sorting (default: type priority, then severity)
    sort_by = request.GET.get('sort', 'priority')
    if sort_by == 'severity':
        alerts = alerts.order_by('-severity', '-created_at')
    elif sort_by == 'patient':
        alerts = alerts.order_by('patient_name')
    elif sort_by == 'created':
        alerts = alerts.order_by('-created_at')
    else:  # priority (default)
        alerts = alerts.order_by('alert_type', '-severity', '-created_at')

    context = {
        'alerts': alerts,
        'alert_types': AlertType.choices,
        'severities': AlertSeverity.choices,
        'current_filters': {
            'type': alert_type,
            'mrn': mrn,
            'severity': severity,
            'sort': sort_by,
        }
    }

    return render(request, 'asp_alerts/active.html', context)


@login_required
@physician_or_higher_required
def alert_history(request):
    """List resolved alerts with filtering"""

    # Get resolved alerts
    alerts = Alert.objects.filter(
        alert_type__in=[
            AlertType.DRUG_BUG_MISMATCH,
            AlertType.CULTURE_NO_THERAPY,
            AlertType.BROAD_SPECTRUM_USAGE,
        ],
        status=AlertStatus.RESOLVED
    ).select_related('created_by', 'resolved_by')

    # Apply filters
    alert_type = request.GET.get('type')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)

    mrn = request.GET.get('mrn')
    if mrn:
        alerts = alerts.filter(patient_mrn__icontains=mrn)

    # Date range filter (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    alerts = alerts.filter(resolved_at__gte=start_date)

    # Sort by resolution date (newest first)
    alerts = alerts.order_by('-resolved_at')

    context = {
        'alerts': alerts,
        'alert_types': AlertType.choices,
        'days': days,
        'current_filters': {
            'type': alert_type,
            'mrn': mrn,
            'days': days,
        }
    }

    return render(request, 'asp_alerts/history.html', context)


@login_required
@physician_or_higher_required
def alert_detail(request, alert_id):
    """Show detailed alert view with clinical context, audit log, and actions"""

    alert = get_object_or_404(
        Alert.objects.select_related('created_by', 'assigned_to', 'resolved_by'),
        id=alert_id
    )

    # Get audit entries
    audit_entries = alert.audit_entries.order_by('-timestamp')

    context = {
        'alert': alert,
        'audit_entries': audit_entries,
    }

    return render(request, 'asp_alerts/detail.html', context)


@login_required
@physician_or_higher_required
def culture_detail(request, culture_id):
    """Display blood culture results with susceptibility panel"""

    # TODO: Fetch from FHIR DiagnosticReport resource
    # For now, show placeholder
    context = {
        'culture_id': culture_id,
        'error': 'FHIR integration not yet implemented'
    }

    return render(request, 'asp_alerts/culture_detail.html', context)


@login_required
@physician_or_higher_required
def medications_detail(request, patient_id):
    """Display patient's current antibiotic medications"""

    # TODO: Fetch from FHIR MedicationRequest resources
    # For now, show placeholder
    context = {
        'patient_id': patient_id,
        'error': 'FHIR integration not yet implemented'
    }

    return render(request, 'asp_alerts/medications.html', context)


@login_required
@physician_or_higher_required
def reports(request):
    """Analytics and reporting dashboard"""

    # Date range (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Get alert statistics
    asp_alerts = Alert.objects.filter(
        alert_type__in=[AlertType.DRUG_BUG_MISMATCH, AlertType.CULTURE_NO_THERAPY, AlertType.BROAD_SPECTRUM_USAGE],
        created_at__gte=start_date
    )

    total_alerts = asp_alerts.count()

    # Group by severity
    by_severity = asp_alerts.values('severity').annotate(
        count=Count('id')
    ).order_by('-severity')

    # Group by status
    by_status = asp_alerts.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    # Group by type
    by_type = asp_alerts.values('alert_type').annotate(
        count=Count('id')
    ).order_by('alert_type')

    # Resolution reasons (for resolved alerts)
    resolved_alerts = asp_alerts.filter(status=AlertStatus.RESOLVED)
    by_resolution = resolved_alerts.values('resolution_reason').annotate(
        count=Count('id')
    ).order_by('-count')

    context = {
        'days': days,
        'total_alerts': total_alerts,
        'by_severity': by_severity,
        'by_status': by_status,
        'by_type': by_type,
        'by_resolution': by_resolution,
        'resolved_count': resolved_alerts.count(),
        'active_count': total_alerts - resolved_alerts.count(),
    }

    return render(request, 'asp_alerts/reports.html', context)


@login_required
@physician_or_higher_required
def help_page(request):
    """Help and documentation page"""
    return render(request, 'asp_alerts/help.html')


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_acknowledge(request, alert_id):
    """Acknowledge an alert"""

    alert = get_object_or_404(Alert, id=alert_id)

    try:
        alert.acknowledge(request.user)
        return JsonResponse({
            'success': True,
            'message': 'Alert acknowledged',
            'alert_id': str(alert.id),
            'status': alert.status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_snooze(request, alert_id):
    """Snooze an alert for N hours"""

    alert = get_object_or_404(Alert, id=alert_id)

    # Get snooze duration from request
    hours = int(request.POST.get('hours', 4))
    until = timezone.now() + timedelta(hours=hours)

    try:
        alert.snooze(request.user, until)
        return JsonResponse({
            'success': True,
            'message': f'Alert snoozed for {hours} hours',
            'alert_id': str(alert.id),
            'status': alert.status,
            'snoozed_until': alert.snoozed_until.isoformat() if alert.snoozed_until else None
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_resolve(request, alert_id):
    """Resolve an alert with documented reason"""

    alert = get_object_or_404(Alert, id=alert_id)

    reason = request.POST.get('reason')
    notes = request.POST.get('notes', '')

    if not reason:
        return JsonResponse({
            'success': False,
            'error': 'Resolution reason required'
        }, status=400)

    try:
        alert.resolve(request.user, reason, notes)
        return JsonResponse({
            'success': True,
            'message': 'Alert resolved',
            'alert_id': str(alert.id),
            'status': alert.status,
            'resolution_reason': alert.resolution_reason
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_list_alerts(request):
    """List alerts with filters (API endpoint)"""

    # Get base queryset
    alerts = Alert.objects.filter(
        alert_type__in=[AlertType.DRUG_BUG_MISMATCH, AlertType.CULTURE_NO_THERAPY, AlertType.BROAD_SPECTRUM_USAGE]
    )

    # Apply filters
    status = request.GET.get('status')
    if status:
        alerts = alerts.filter(status=status)

    alert_type = request.GET.get('type')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)

    severity = request.GET.get('severity')
    if severity:
        alerts = alerts.filter(severity=severity)

    # Limit results
    limit = int(request.GET.get('limit', 100))
    alerts = alerts.order_by('-created_at')[:limit]

    # Serialize
    data = [{
        'id': str(alert.id),
        'alert_type': alert.alert_type,
        'severity': alert.severity,
        'status': alert.status,
        'patient_mrn': alert.patient_mrn,
        'patient_name': alert.patient_name,
        'message': alert.message,
        'created_at': alert.created_at.isoformat(),
        'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
    } for alert in alerts]

    return JsonResponse({
        'success': True,
        'count': len(data),
        'alerts': data
    })


@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_alert_detail(request, alert_id):
    """Get single alert details (API endpoint)"""

    alert = get_object_or_404(Alert, id=alert_id)

    data = {
        'id': str(alert.id),
        'alert_type': alert.alert_type,
        'severity': alert.severity,
        'status': alert.status,
        'patient_mrn': alert.patient_mrn,
        'patient_name': alert.patient_name,
        'patient_location': alert.patient_location,
        'message': alert.message,
        'details': alert.details,
        'recommendations': alert.recommendations,
        'created_at': alert.created_at.isoformat(),
        'acknowledged_at': alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
        'resolution_reason': alert.resolution_reason,
        'resolution_notes': alert.resolution_notes,
        'created_by': alert.created_by.username if alert.created_by else None,
        'assigned_to': alert.assigned_to.username if alert.assigned_to else None,
        'resolved_by': alert.resolved_by.username if alert.resolved_by else None,
    }

    return JsonResponse({
        'success': True,
        'alert': data
    })


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_update_status(request, alert_id):
    """Update alert status (API endpoint)"""

    alert = get_object_or_404(Alert, id=alert_id)

    new_status = request.POST.get('status')
    if not new_status:
        return JsonResponse({
            'success': False,
            'error': 'Status required'
        }, status=400)

    try:
        alert.status = new_status
        alert.save(update_fields=['status'])

        return JsonResponse({
            'success': True,
            'message': 'Status updated',
            'alert_id': str(alert.id),
            'status': alert.status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["POST"])
def api_add_note(request, alert_id):
    """Add a note to an alert (API endpoint)"""

    alert = get_object_or_404(Alert, id=alert_id)

    note_text = request.POST.get('note')
    if not note_text:
        return JsonResponse({
            'success': False,
            'error': 'Note text required'
        }, status=400)

    try:
        # Add note to alert details (append to existing notes)
        if not alert.details:
            alert.details = {}

        if 'notes' not in alert.details:
            alert.details['notes'] = []

        alert.details['notes'].append({
            'user': request.user.username,
            'timestamp': timezone.now().isoformat(),
            'text': note_text
        })

        alert.save(update_fields=['details'])

        return JsonResponse({
            'success': True,
            'message': 'Note added',
            'alert_id': str(alert.id)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@physician_or_higher_required
@require_http_methods(["GET"])
def api_stats(request):
    """Get alert statistics (API endpoint)"""

    # Date range (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Get alerts
    asp_alerts = Alert.objects.filter(
        alert_type__in=[AlertType.DRUG_BUG_MISMATCH, AlertType.CULTURE_NO_THERAPY, AlertType.BROAD_SPECTRUM_USAGE],
        created_at__gte=start_date
    )

    total_alerts = asp_alerts.count()
    pending = asp_alerts.filter(status=AlertStatus.PENDING).count()
    acknowledged = asp_alerts.filter(status=AlertStatus.ACKNOWLEDGED).count()
    resolved = asp_alerts.filter(status=AlertStatus.RESOLVED).count()

    critical = asp_alerts.filter(severity=AlertSeverity.CRITICAL).count()
    warning = asp_alerts.filter(severity=AlertSeverity.WARNING).count()
    info = asp_alerts.filter(severity=AlertSeverity.INFO).count()

    data = {
        'days': days,
        'total_alerts': total_alerts,
        'by_status': {
            'pending': pending,
            'acknowledged': acknowledged,
            'resolved': resolved,
        },
        'by_severity': {
            'critical': critical,
            'warning': warning,
            'info': info,
        }
    }

    return JsonResponse({
        'success': True,
        'stats': data
    })
