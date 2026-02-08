"""Views for Action Analytics dashboard."""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from datetime import datetime, timedelta

from apps.authentication.decorators import physician_or_higher_required
from .analytics import ActionAnalyzer


@login_required
@physician_or_higher_required
def overview(request):
    """Action Analytics overview dashboard."""
    # Get date range from query params
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_overview()
    
    context = {
        'data': data,
        'days': days,
    }
    return render(request, 'action_analytics/overview.html', context)


@login_required
@physician_or_higher_required
def by_module(request):
    """Actions by module dashboard."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_actions_by_module()
    
    context = {
        'data': data,
        'days': days,
    }
    return render(request, 'action_analytics/by_module.html', context)


@login_required
@physician_or_higher_required
def time_spent(request):
    """Time spent analysis dashboard."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_time_spent_analysis()
    
    context = {
        'data': data,
        'days': days,
    }
    return render(request, 'action_analytics/time_spent.html', context)


@login_required
@physician_or_higher_required
def productivity(request):
    """User productivity dashboard."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_user_productivity()
    
    context = {
        'data': data,
        'days': days,
    }
    return render(request, 'action_analytics/productivity.html', context)


# JSON API endpoints
@login_required
def api_overview(request):
    """JSON API for overview data."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_overview()
    
    return JsonResponse(data, safe=False)


@login_required
def api_by_module(request):
    """JSON API for by-module data."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_actions_by_module()
    
    return JsonResponse(data, safe=False)


@login_required
def api_time_spent(request):
    """JSON API for time spent data."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_time_spent_analysis()
    
    return JsonResponse(data, safe=False)


@login_required
def api_productivity(request):
    """JSON API for productivity data."""
    days = int(request.GET.get('days', 30))
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    analyzer = ActionAnalyzer(start_date, end_date)
    data = analyzer.get_user_productivity()
    
    return JsonResponse(data, safe=False)
