"""
Views for Surgical Prophylaxis module.

Provides dashboard, case detail, compliance analysis, real-time monitoring,
and API endpoints for the ASHP bundle compliance workflow.
"""

import csv
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertStatus, AlertType, AlertSeverity
from apps.authentication.decorators import can_manage_surgical_prophylaxis

from .models import (
    SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication,
    ComplianceMetric, SurgicalJourney, PatientLocation,
    PreOpCheck, AlertEscalation, ComplianceStatus, ProcedureCategory,
)
from .services import SurgicalProphylaxisService

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Page Views
# ------------------------------------------------------------------

@can_manage_surgical_prophylaxis
def dashboard(request):
    """Surgical prophylaxis dashboard with compliance stats and pending alerts."""
    service = SurgicalProphylaxisService()
    stats = service.get_stats()

    pending_alerts = Alert.objects.filter(
        alert_type=AlertType.SURGICAL_PROPHYLAXIS,
        status=AlertStatus.PENDING,
    ).order_by('-created_at')[:10]

    recent_evaluations = ProphylaxisEvaluation.objects.select_related(
        'case'
    ).order_by('-evaluation_time')[:10]

    return render(request, 'surgical_prophylaxis/dashboard.html', {
        'stats': stats,
        'pending_alerts': pending_alerts,
        'recent_evaluations': recent_evaluations,
    })


@can_manage_surgical_prophylaxis
def case_detail(request, pk):
    """Show case with 7-element evaluation, medications, and timeline."""
    case = get_object_or_404(SurgicalCase, id=pk)
    evaluations = case.evaluations.order_by('-evaluation_time')
    medications = case.medications.order_by('event_time')

    # Get latest evaluation
    latest_eval = evaluations.first()

    # Get associated alerts
    alerts = Alert.objects.filter(
        alert_type=AlertType.SURGICAL_PROPHYLAXIS,
        source_id=case.case_id,
    ).order_by('-created_at')

    return render(request, 'surgical_prophylaxis/case_detail.html', {
        'case': case,
        'latest_eval': latest_eval,
        'evaluations': evaluations,
        'medications': medications,
        'alerts': alerts,
    })


@can_manage_surgical_prophylaxis
def compliance(request):
    """Historical compliance trends with per-element breakdown."""
    # Get procedure category filter
    category_filter = request.GET.get('category', '')

    # Recent evaluations for stats
    evaluations = ProphylaxisEvaluation.objects.select_related('case')
    if category_filter:
        evaluations = evaluations.filter(case__procedure_category=category_filter)

    recent_evals = evaluations.order_by('-evaluation_time')[:100]

    # Calculate aggregate stats
    total = recent_evals.count()
    if total > 0:
        compliant = sum(1 for e in recent_evals if e.bundle_compliant)
        excluded = sum(1 for e in recent_evals if e.excluded)
        assessed = total - excluded

        compliance_rate = (compliant / assessed * 100) if assessed > 0 else 0

        # Per-element rates
        element_rates = {}
        for name, field in [
            ('Indication', 'indication_result'),
            ('Agent Selection', 'agent_result'),
            ('Pre-op Timing', 'timing_result'),
            ('Dosing', 'dosing_result'),
            ('Redosing', 'redosing_result'),
            ('Post-op Continuation', 'postop_result'),
            ('Discontinuation', 'discontinuation_result'),
        ]:
            met = sum(1 for e in recent_evals if getattr(e, field, {}).get('status') == ComplianceStatus.MET)
            applicable = sum(1 for e in recent_evals
                           if getattr(e, field, {}).get('status') not in (ComplianceStatus.NOT_APPLICABLE, None, ''))
            element_rates[name] = (met / applicable * 100) if applicable > 0 else 0
    else:
        compliance_rate = 0
        assessed = 0
        compliant = 0
        excluded = 0
        element_rates = {}

    # Cases by category
    category_stats = {}
    for cat in ProcedureCategory:
        cat_evals = [e for e in recent_evals if e.case.procedure_category == cat.value]
        if cat_evals:
            cat_assessed = sum(1 for e in cat_evals if not e.excluded)
            cat_compliant = sum(1 for e in cat_evals if e.bundle_compliant)
            category_stats[cat.label] = {
                'total': len(cat_evals),
                'compliant': cat_compliant,
                'rate': (cat_compliant / cat_assessed * 100) if cat_assessed > 0 else 0,
            }

    return render(request, 'surgical_prophylaxis/compliance.html', {
        'total': total,
        'assessed': assessed,
        'compliant': compliant,
        'excluded': excluded,
        'compliance_rate': compliance_rate,
        'element_rates': element_rates,
        'category_stats': category_stats,
        'categories': ProcedureCategory,
        'current_category': category_filter,
    })


@can_manage_surgical_prophylaxis
def realtime(request):
    """Active surgical journeys with location tracking and escalations."""
    active_journeys = SurgicalJourney.objects.filter(
        completed_at__isnull=True,
    ).order_by('-created_at')

    recent_completed = SurgicalJourney.objects.filter(
        completed_at__isnull=False,
    ).order_by('-completed_at')[:10]

    pending_escalations = AlertEscalation.objects.filter(
        escalated=False,
        delivery_status='sent',
    ).select_related('journey').order_by('-sent_at')[:20]

    return render(request, 'surgical_prophylaxis/realtime.html', {
        'active_journeys': active_journeys,
        'recent_completed': recent_completed,
        'pending_escalations': pending_escalations,
    })


@can_manage_surgical_prophylaxis
def help_page(request):
    """ASHP bundle reference and workflow guide."""
    return render(request, 'surgical_prophylaxis/help.html')


# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------

@can_manage_surgical_prophylaxis
def api_stats(request):
    """Get current compliance stats as JSON."""
    service = SurgicalProphylaxisService()
    stats = service.get_stats()
    return JsonResponse(stats)


@can_manage_surgical_prophylaxis
def api_acknowledge(request, pk):
    """Acknowledge a surgical prophylaxis alert."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    alert = get_object_or_404(
        Alert, id=pk, alert_type=AlertType.SURGICAL_PROPHYLAXIS,
    )
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


@can_manage_surgical_prophylaxis
def api_resolve(request, pk):
    """Resolve a surgical prophylaxis alert."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    alert = get_object_or_404(
        Alert, id=pk, alert_type=AlertType.SURGICAL_PROPHYLAXIS,
    )
    reviewer = request.user.get_full_name() or request.user.username
    notes = request.POST.get('notes', '')
    reason = request.POST.get('reason', 'resolved')

    alert.status = AlertStatus.RESOLVED
    alert.resolution_reason = reason
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['status', 'resolution_reason', 'resolved_at', 'updated_at'])

    AlertAudit.objects.create(
        alert=alert,
        action='resolved',
        performed_by=reviewer,
        details=f"Resolved by {reviewer}. {notes}".strip(),
    )

    return JsonResponse({'status': 'ok'})


@can_manage_surgical_prophylaxis
def api_add_note(request, pk):
    """Add a note to a surgical prophylaxis alert."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    alert = get_object_or_404(
        Alert, id=pk, alert_type=AlertType.SURGICAL_PROPHYLAXIS,
    )
    reviewer = request.user.get_full_name() or request.user.username
    note = request.POST.get('note', '')

    if not note:
        return JsonResponse({'error': 'Note text required'}, status=400)

    AlertAudit.objects.create(
        alert=alert,
        action='note_added',
        performed_by=reviewer,
        details=note,
    )

    return JsonResponse({'status': 'ok'})


@can_manage_surgical_prophylaxis
def api_export(request):
    """Export evaluation data as CSV."""
    evaluations = ProphylaxisEvaluation.objects.select_related(
        'case'
    ).order_by('-evaluation_time')[:500]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="prophylaxis_evaluations.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Case ID', 'Patient MRN', 'Procedure', 'Category',
        'Evaluation Time', 'Bundle Compliant', 'Compliance Score',
        'Indication', 'Agent', 'Timing', 'Dosing',
        'Redosing', 'Post-op', 'Discontinuation',
        'Excluded', 'Exclusion Reason',
    ])

    for ev in evaluations:
        writer.writerow([
            ev.case.case_id,
            ev.case.patient_mrn,
            ev.case.procedure_description,
            ev.case.get_procedure_category_display(),
            ev.evaluation_time.strftime('%Y-%m-%d %H:%M'),
            ev.bundle_compliant,
            f"{ev.compliance_score:.1f}",
            ev.indication_result.get('status', ''),
            ev.agent_result.get('status', ''),
            ev.timing_result.get('status', ''),
            ev.dosing_result.get('status', ''),
            ev.redosing_result.get('status', ''),
            ev.postop_result.get('status', ''),
            ev.discontinuation_result.get('status', ''),
            ev.excluded,
            ev.exclusion_reason,
        ])

    return response
