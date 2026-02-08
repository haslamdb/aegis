"""
Dosing Verification Dashboard - URL Configuration
"""

from django.urls import path
from . import views

app_name = 'dosing'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard, name='dashboard'),
    path('alert/<uuid:alert_id>/', views.alert_detail, name='detail'),
    path('history/', views.history, name='history'),
    path('reports/', views.reports, name='reports'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/<uuid:alert_id>/acknowledge/', views.api_acknowledge, name='api_acknowledge'),
    path('api/<uuid:alert_id>/resolve/', views.api_resolve, name='api_resolve'),
    path('api/<uuid:alert_id>/note/', views.api_add_note, name='api_note'),

    # CSV exports
    path('export/active.csv', views.export_active_csv, name='export_active'),
    path('export/history.csv', views.export_history_csv, name='export_history'),
]
