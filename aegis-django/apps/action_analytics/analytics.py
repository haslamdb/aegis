"""Analytics aggregator for ASP/IP action tracking."""

from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from apps.metrics.models import ProviderActivity, DailySnapshot
from apps.alerts.models import Alert


class ActionAnalyzer:
    """Aggregates and analyzes ASP/IP actions from metrics data."""

    def __init__(self, start_date=None, end_date=None):
        """Initialize with optional date range."""
        self.start_date = start_date or (timezone.now() - timedelta(days=30)).date()
        self.end_date = end_date or timezone.now().date()

    def get_overview(self):
        """Get overview statistics."""
        activities = ProviderActivity.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        total_actions = activities.count()
        unique_patients = activities.values('patient_mrn').distinct().count()
        avg_duration = activities.aggregate(Avg('duration_seconds'))['duration_seconds__avg'] or 0
        
        # Actions by module
        by_module = activities.values('module').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Actions by user
        by_user = activities.values('user__username').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        return {
            'total_actions': total_actions,
            'unique_patients': unique_patients,
            'avg_duration_seconds': round(avg_duration, 1),
            'by_module': list(by_module),
            'by_user': list(by_user),
            'date_range': {
                'start': self.start_date,
                'end': self.end_date,
            }
        }

    def get_actions_by_type(self):
        """Get actions grouped by type."""
        activities = ProviderActivity.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        by_type = activities.values('action_type').annotate(
            count=Count('id'),
            total_duration=Sum('duration_seconds')
        ).order_by('-count')
        
        return list(by_type)

    def get_actions_by_module(self):
        """Get actions grouped by module."""
        activities = ProviderActivity.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        by_module = activities.values('module').annotate(
            count=Count('id'),
            unique_patients=Count('patient_mrn', distinct=True),
            total_duration=Sum('duration_seconds')
        ).order_by('-count')
        
        return list(by_module)

    def get_time_spent_analysis(self):
        """Analyze time spent on different activities."""
        activities = ProviderActivity.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        time_by_module = activities.values('module').annotate(
            total_seconds=Sum('duration_seconds'),
            avg_seconds=Avg('duration_seconds'),
            count=Count('id')
        ).order_by('-total_seconds')
        
        return {
            'by_module': list(time_by_module),
            'total_time_seconds': activities.aggregate(Sum('duration_seconds'))['duration_seconds__sum'] or 0,
        }

    def get_daily_trend(self):
        """Get daily trend of actions."""
        activities = ProviderActivity.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        daily = activities.annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        return list(daily)

    def get_user_productivity(self):
        """Get productivity metrics by user."""
        activities = ProviderActivity.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        by_user = activities.values(
            'user__username',
            'user__first_name',
            'user__last_name',
            'user__role'
        ).annotate(
            total_actions=Count('id'),
            unique_patients=Count('patient_mrn', distinct=True),
            total_time=Sum('duration_seconds'),
            avg_time=Avg('duration_seconds')
        ).order_by('-total_actions')
        
        return list(by_user)
