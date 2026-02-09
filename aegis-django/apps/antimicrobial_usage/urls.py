"""
Antimicrobial Usage Alerts - URL Configuration
"""

from django.urls import path
from . import views

app_name = 'antimicrobial_usage'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard, name='dashboard'),
    path('alert/<uuid:alert_id>/', views.alert_detail, name='detail'),
    path('history/', views.history, name='history'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/<uuid:alert_id>/acknowledge/', views.api_acknowledge, name='api_acknowledge'),
    path('api/<uuid:alert_id>/resolve/', views.api_resolve, name='api_resolve'),
    path('api/<uuid:alert_id>/add-note/', views.api_add_note, name='api_add_note'),

    # CSV export
    path('api/export/', views.api_export, name='api_export'),
]
