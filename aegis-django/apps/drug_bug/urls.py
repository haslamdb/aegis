"""
Drug-Bug Mismatch - URL Configuration
"""

from django.urls import path
from . import views

app_name = 'drug_bug'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard, name='dashboard'),
    path('history/', views.history, name='history'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/export/', views.api_export, name='api_export'),
]
