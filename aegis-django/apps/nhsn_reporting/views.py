"""Views for NHSN Reporting module."""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.authentication.decorators import can_manage_nhsn_reporting

from .models import (
    NHSNEvent, DenominatorMonthly,
    AUMonthlySummary, AUAntimicrobialUsage,
    ARQuarterlySummary, ARIsolate, ARPhenotypeSummary,
    SubmissionAudit,
)
from .services import NHSNReportingService
from .logic import config as cfg


def _get_service():
    return NHSNReportingService()


@login_required
@can_manage_nhsn_reporting
def dashboard(request):
    """Overview: AU summary, AR summary, denominators, recent events."""
    service = _get_service()
    stats = service.get_stats()
    recent_submissions = SubmissionAudit.objects.all()[:10]

    context = {
        'stats': stats,
        'recent_submissions': recent_submissions,
        'clarity_configured': cfg.is_clarity_configured(),
        'direct_configured': cfg.is_direct_configured(),
    }
    return render(request, 'nhsn_reporting/dashboard.html', context)


@login_required
@can_manage_nhsn_reporting
def au_detail(request):
    """Antibiotic Usage detail with DOT/DDD breakdown."""
    month_filter = request.GET.get('month', '')
    location_filter = request.GET.get('location', '')

    summaries = AUMonthlySummary.objects.all().prefetch_related('usage_records')
    if month_filter:
        summaries = summaries.filter(reporting_month=month_filter)
    if location_filter:
        summaries = summaries.filter(location_code=location_filter)

    # Get available months and locations for filters
    months = AUMonthlySummary.objects.values_list('reporting_month', flat=True).distinct().order_by('-reporting_month')
    locations = AUMonthlySummary.objects.values_list('location_code', flat=True).distinct().order_by('location_code')

    context = {
        'summaries': summaries,
        'months': months,
        'locations': locations,
        'month_filter': month_filter,
        'location_filter': location_filter,
    }
    return render(request, 'nhsn_reporting/au_detail.html', context)


@login_required
@can_manage_nhsn_reporting
def ar_detail(request):
    """Antimicrobial Resistance: isolates, phenotypes, quarterly."""
    quarter_filter = request.GET.get('quarter', '')
    location_filter = request.GET.get('location', '')

    summaries = ARQuarterlySummary.objects.all().prefetch_related('isolates', 'phenotypes')
    if quarter_filter:
        summaries = summaries.filter(reporting_quarter=quarter_filter)
    if location_filter:
        summaries = summaries.filter(location_code=location_filter)

    quarters = ARQuarterlySummary.objects.values_list('reporting_quarter', flat=True).distinct().order_by('-reporting_quarter')
    locations = ARQuarterlySummary.objects.values_list('location_code', flat=True).distinct().order_by('location_code')

    context = {
        'summaries': summaries,
        'quarters': quarters,
        'locations': locations,
        'quarter_filter': quarter_filter,
        'location_filter': location_filter,
    }
    return render(request, 'nhsn_reporting/ar_detail.html', context)


@login_required
@can_manage_nhsn_reporting
def hai_events(request):
    """Confirmed HAI events for submission."""
    status_filter = request.GET.get('status', '')
    events = NHSNEvent.objects.all().select_related('candidate')

    if status_filter == 'unreported':
        events = events.filter(reported=False)
    elif status_filter == 'reported':
        events = events.filter(reported=True)

    context = {
        'events': events,
        'status_filter': status_filter,
        'unreported_count': NHSNEvent.objects.filter(reported=False).count(),
        'reported_count': NHSNEvent.objects.filter(reported=True).count(),
    }
    return render(request, 'nhsn_reporting/hai_events.html', context)


@login_required
@can_manage_nhsn_reporting
def denominators(request):
    """Device-days, patient-days, utilization ratios."""
    month_filter = request.GET.get('month', '')
    location_filter = request.GET.get('location', '')

    denoms = DenominatorMonthly.objects.all()
    if month_filter:
        denoms = denoms.filter(month=month_filter)
    if location_filter:
        denoms = denoms.filter(location_code=location_filter)

    months = DenominatorMonthly.objects.values_list('month', flat=True).distinct().order_by('-month')
    locations = DenominatorMonthly.objects.values_list('location_code', flat=True).distinct().order_by('location_code')

    context = {
        'denominators': denoms,
        'months': months,
        'locations': locations,
        'month_filter': month_filter,
        'location_filter': location_filter,
    }
    return render(request, 'nhsn_reporting/denominators.html', context)


@login_required
@can_manage_nhsn_reporting
def submission(request):
    """Unified submission page: CSV export, DIRECT submit, mark submitted."""
    audit_log = SubmissionAudit.objects.all()[:25]
    unreported = NHSNEvent.objects.filter(reported=False)

    context = {
        'audit_log': audit_log,
        'unreported_events': unreported,
        'unreported_count': unreported.count(),
        'direct_configured': cfg.is_direct_configured(),
    }
    return render(request, 'nhsn_reporting/submission.html', context)


@login_required
@can_manage_nhsn_reporting
def help_page(request):
    """NHSN reporting guide."""
    return render(request, 'nhsn_reporting/help.html')


# ---- API Endpoints ----

@login_required
@can_manage_nhsn_reporting
def api_stats(request):
    """JSON summary stats."""
    service = _get_service()
    stats = service.get_stats()
    return JsonResponse(stats)


@login_required
@can_manage_nhsn_reporting
def api_au_export(request):
    """CSV AU export."""
    period = request.GET.get('period', '')
    location = request.GET.get('location', '')
    service = _get_service()
    csv_data = service.export_csv('au', period, location)

    response = HttpResponse(csv_data, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="nhsn_au_{period or "all"}.csv"'
    service.log_submission('csv_export', 'au', period, request.user.username, 0)
    return response


@login_required
@can_manage_nhsn_reporting
def api_ar_export(request):
    """CSV AR export."""
    period = request.GET.get('period', '')
    location = request.GET.get('location', '')
    service = _get_service()
    csv_data = service.export_csv('ar', period, location)

    response = HttpResponse(csv_data, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="nhsn_ar_{period or "all"}.csv"'
    service.log_submission('csv_export', 'ar', period, request.user.username, 0)
    return response


@login_required
@can_manage_nhsn_reporting
@require_POST
def api_hai_export(request):
    """CSV HAI events export."""
    service = _get_service()
    csv_data = service.export_csv('hai')

    response = HttpResponse(csv_data, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="nhsn_hai_events.csv"'
    service.log_submission('csv_export', 'hai', '', request.user.username, 0)
    return response


@login_required
@can_manage_nhsn_reporting
@require_POST
def api_mark_submitted(request):
    """Mark events as submitted."""
    try:
        data = json.loads(request.body)
        event_ids = data.get('event_ids', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not event_ids:
        return JsonResponse({'error': 'No event IDs provided'}, status=400)

    service = _get_service()
    count = service.mark_submitted(event_ids, request.user.username)
    return JsonResponse({'success': True, 'marked_count': count})


@login_required
@can_manage_nhsn_reporting
@require_POST
def api_direct_submit(request):
    """Submit via DIRECT protocol."""
    try:
        data = json.loads(request.body)
        event_ids = data.get('event_ids', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not event_ids:
        return JsonResponse({'error': 'No event IDs provided'}, status=400)

    service = _get_service()
    result = service.submit_via_direct(event_ids, request.user.username)
    return JsonResponse(result)


@login_required
@can_manage_nhsn_reporting
@require_POST
def api_test_direct(request):
    """Test DIRECT connection."""
    service = _get_service()
    success, message = service.test_direct_connection()
    return JsonResponse({'success': success, 'message': message})
