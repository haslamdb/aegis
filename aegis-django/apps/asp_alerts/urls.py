"""
ASP Alerts Dashboard - URL Configuration
"""

from django.urls import path
from . import views

app_name = 'asp_alerts'

urlpatterns = [
    # Dashboard views
    path('', views.index, name='index'),
    path('active/', views.active_alerts, name='active'),
    path('history/', views.alert_history, name='history'),
    path('alerts/<uuid:alert_id>/', views.alert_detail, name='detail'),
    path('culture/<str:culture_id>/', views.culture_detail, name='culture'),
    path('patient/<str:patient_id>/medications/', views.medications_detail, name='medications'),
    path('reports/', views.reports, name='reports'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/acknowledge/<uuid:alert_id>/', views.api_acknowledge, name='api_acknowledge'),
    path('api/snooze/<uuid:alert_id>/', views.api_snooze, name='api_snooze'),
    path('api/resolve/<uuid:alert_id>/', views.api_resolve, name='api_resolve'),
    path('api/alerts/', views.api_list_alerts, name='api_list'),
    path('api/alerts/<uuid:alert_id>/', views.api_alert_detail, name='api_detail'),
    path('api/alerts/<uuid:alert_id>/status/', views.api_update_status, name='api_status'),
    path('api/alerts/<uuid:alert_id>/notes/', views.api_add_note, name='api_notes'),
    path('api/stats/', views.api_stats, name='api_stats'),
]
