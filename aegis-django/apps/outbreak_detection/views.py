"""
Views for Outbreak Detection module.

Provides dashboard, cluster management, alerts, and API endpoints
for the outbreak detection workflow.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404

from apps.alerts.models import Alert, AlertAudit, AlertStatus
from apps.authentication.decorators import can_manage_outbreak_detection

from .models import OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity
from .services import OutbreakDetectionService

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Page Views
# ------------------------------------------------------------------

@can_manage_outbreak_detection
def dashboard(request):
    """Outbreak detection dashboard overview."""
    service = OutbreakDetectionService()
    stats = service.get_stats()

    active_clusters = OutbreakCluster.objects.filter(
        status__in=[ClusterStatus.ACTIVE, ClusterStatus.INVESTIGATING],
    ).order_by('-severity', '-last_case_date')

    pending_alerts = Alert.objects.filter(
        source_module='outbreak_detection',
        status=AlertStatus.PENDING,
    ).order_by('-created_at')[:10]

    return render(request, 'outbreak_detection/dashboard.html', {
        'stats': stats,
        'active_clusters': active_clusters,
        'pending_alerts': pending_alerts,
    })


@can_manage_outbreak_detection
def clusters_list(request):
    """List all outbreak clusters with status filter."""
    status_filter = request.GET.get('status', 'active')

    # Validate status
    valid_statuses = {s.value for s in ClusterStatus}
    if status_filter not in valid_statuses:
        status_filter = 'active'

    clusters = OutbreakCluster.objects.filter(
        status=status_filter,
    ).order_by('-severity', '-last_case_date')

    return render(request, 'outbreak_detection/clusters.html', {
        'clusters': clusters,
        'current_status': status_filter,
        'statuses': ClusterStatus,
    })


@can_manage_outbreak_detection
def cluster_detail(request, cluster_id):
    """Show cluster details with cases and investigation form."""
    cluster = get_object_or_404(OutbreakCluster, id=cluster_id)
    cases = cluster.cases.order_by('-event_date')

    # Get associated alerts
    alerts = Alert.objects.filter(
        source_module='outbreak_detection',
        source_id=str(cluster_id),
    ).order_by('-created_at')

    return render(request, 'outbreak_detection/cluster_detail.html', {
        'cluster': cluster,
        'cases': cases,
        'alerts': alerts,
    })


@can_manage_outbreak_detection
def update_cluster_status(request, cluster_id):
    """Update cluster status (confirm, investigate, resolve, or not outbreak)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    cluster = get_object_or_404(OutbreakCluster, id=cluster_id)

    new_status = request.POST.get('status')
    notes = request.POST.get('notes', '')
    decision = request.POST.get('decision', '')
    reviewer = request.POST.get('reviewer', '') or request.user.get_full_name() or request.user.username
    override_reason = request.POST.get('override_reason', '')

    service = OutbreakDetectionService()

    if new_status == 'not_outbreak':
        full_notes = f"[NOT AN OUTBREAK] {override_reason}"
        if notes:
            full_notes += f"\n{notes}"
        success = service.resolve_cluster(cluster.id, reviewer, full_notes)
    elif new_status == 'resolved':
        success = service.resolve_cluster(cluster.id, reviewer, notes)
    else:
        success = service.update_cluster_status(
            cluster.id, new_status, notes=notes, updated_by=reviewer,
        )

    if success:
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'error': 'Failed to update status'}, status=500)


@can_manage_outbreak_detection
def alerts_list(request):
    """List pending and acknowledged outbreak alerts."""
    pending = Alert.objects.filter(
        source_module='outbreak_detection',
        status=AlertStatus.PENDING,
    ).order_by('-created_at')

    acknowledged = Alert.objects.filter(
        source_module='outbreak_detection',
        status=AlertStatus.ACKNOWLEDGED,
    ).order_by('-updated_at')[:50]

    return render(request, 'outbreak_detection/alerts.html', {
        'pending_alerts': pending,
        'acknowledged_alerts': acknowledged,
    })


@can_manage_outbreak_detection
def acknowledge_alert(request, alert_id):
    """Acknowledge an outbreak alert."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    alert = get_object_or_404(Alert, id=alert_id, source_module='outbreak_detection')
    reviewer = request.user.get_full_name() or request.user.username

    alert.status = AlertStatus.ACKNOWLEDGED
    alert.save(update_fields=['status', 'updated_at'])

    AlertAudit.objects.create(
        alert=alert,
        action='acknowledged',
        performed_by=reviewer,
        details=f"Alert acknowledged by {reviewer}",
    )

    return JsonResponse({'status': 'ok'})


@can_manage_outbreak_detection
def help_page(request):
    """Outbreak detection help and documentation."""
    return render(request, 'outbreak_detection/help.html')


# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------

@can_manage_outbreak_detection
def api_stats(request):
    """Get current outbreak detection stats as JSON."""
    service = OutbreakDetectionService()
    stats = service.get_stats()
    return JsonResponse(stats)


@can_manage_outbreak_detection
def api_active_clusters(request):
    """Get active clusters as JSON."""
    clusters = OutbreakCluster.objects.filter(
        status__in=[ClusterStatus.ACTIVE, ClusterStatus.INVESTIGATING],
    ).order_by('-severity', '-last_case_date')

    data = []
    for c in clusters:
        data.append({
            'id': str(c.id),
            'infection_type': c.infection_type,
            'organism': c.organism,
            'unit': c.unit,
            'case_count': c.case_count,
            'severity': c.severity,
            'status': c.status,
            'first_case_date': c.first_case_date.isoformat() if c.first_case_date else None,
            'last_case_date': c.last_case_date.isoformat() if c.last_case_date else None,
            'created_at': c.created_at.isoformat(),
        })

    return JsonResponse({'clusters': data})
